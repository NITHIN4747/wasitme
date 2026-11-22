"""
Safe subprocess boundary for kubectl execution.
Owned by Trisha Krishnan (Linux Systems Engineer).
Invariants:
- Never use shell=True.
- Only allowlist 'kubectl get ... -o json' and 'kubectl config ...'.
- Maps all environment, timeout, and authorization failures to exit code 2 with actionable guidance.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional


class KubectlError(Exception):
    def __init__(self, message: str, exit_code: int = 2, next_step: str = ""):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.next_step = next_step


class SafeKubectlRunner:
    """Safe runner that executes strictly allowlisted read-only kubectl commands."""

    ALLOWED_GET_RESOURCES = {
        "pods",
        "deployments",
        "statefulsets",
        "daemonsets",
        "nodes",
        "events",
        "namespaces",
        "all",
    }

    def __init__(
        self,
        context: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        timeout_seconds: int = 15,
        max_output_bytes: int = 10 * 1024 * 1024,  # 10 MB limit
    ):
        self.context = context
        self.kubeconfig = kubeconfig
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def _resolve_kubectl_path(self) -> str:
        kubectl_path = shutil.which("kubectl")
        if not kubectl_path:
            raise KubectlError(
                message="Unable to find 'kubectl' binary on system PATH.",
                exit_code=2,
                next_step="Install kubectl (https://kubernetes.io/docs/tasks/tools/) or check your $PATH environment variable.",
            )
        return kubectl_path

    def get_cluster_context(self) -> Dict[str, str]:
        """Queries active context and cluster API server URL."""
        kubectl = self._resolve_kubectl_path()
        cmd = [kubectl, "config", "view", "--minify", "-o", "json"]
        if self.context:
            cmd.extend(["--context", self.context])

        out = self._run_command(cmd)
        try:
            data = json.loads(out)
            ctx_name = data.get("current-context", "default")
            clusters = data.get("clusters", [])
            server = clusters[0]["cluster"]["server"] if clusters else "unknown"
            return {"context": ctx_name, "server": server}
        except Exception:
            return {"context": self.context or "current", "server": "unknown"}

    def get_resources_json(
        self,
        resources: str,
        namespace: Optional[str] = None,
        selector: Optional[str] = None,
        all_namespaces: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes 'kubectl get <resources> -o json'.
        Validates resource types against allowlist.
        """
        # Validate resource allowlist
        requested_types = [r.strip().lower() for r in resources.split(",")]
        for r_type in requested_types:
            base_type = r_type.split("/")[0]
            if base_type not in self.ALLOWED_GET_RESOURCES:
                raise KubectlError(
                    message=f"Unauthorized resource type requested: '{r_type}'.",
                    exit_code=2,
                    next_step=f"Only the following resources are permitted: {', '.join(sorted(self.ALLOWED_GET_RESOURCES))}.",
                )

        kubectl = self._resolve_kubectl_path()
        cmd: List[str] = [kubectl, "get", resources, "-o", "json"]

        if all_namespaces:
            cmd.append("-A")
        elif namespace:
            cmd.extend(["-n", namespace])

        if selector:
            cmd.extend(["-l", selector])

        if self.context:
            cmd.extend(["--context", self.context])

        raw_output = self._run_command(cmd)

        try:
            parsed: Dict[str, Any] = json.loads(raw_output)
            return parsed
        except json.JSONDecodeError as e:
            raise KubectlError(
                message=f"Failed to parse JSON response from kubectl: {e}",
                exit_code=2,
                next_step="Verify cluster responsiveness and kubectl output sanity.",
            )

    def _run_command(self, cmd: List[str]) -> str:
        env = dict(os.environ)
        if self.kubeconfig:
            env["KUBECONFIG"] = self.kubeconfig

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise KubectlError(
                message=f"kubectl command timed out after {self.timeout_seconds} seconds.",
                exit_code=2,
                next_step="Check if the Kubernetes API server is reachable or increase timeout.",
            )
        except FileNotFoundError:
            raise KubectlError(
                message="kubectl executable not found.",
                exit_code=2,
                next_step="Install kubectl or add it to PATH.",
            )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "unauthorized" in stderr.lower() or "forbidden" in stderr.lower():
                raise KubectlError(
                    message=f"Kubernetes authorization error: {stderr}",
                    exit_code=2,
                    next_step="Check cluster RBAC permissions or renew authentication tokens.",
                )
            if "not found" in stderr.lower() and "namespace" in stderr.lower():
                raise KubectlError(
                    message=f"Kubernetes namespace not found: {stderr}",
                    exit_code=2,
                    next_step="Check namespace name spelling or create namespace.",
                )
            if "connection refused" in stderr.lower() or "was refused" in stderr.lower():
                raise KubectlError(
                    message=f"Unable to connect to Kubernetes cluster: {stderr}",
                    exit_code=2,
                    next_step="Check your VPN, network connection, or API server endpoint.",
                )

            raise KubectlError(
                message=f"kubectl command failed with exit code {result.returncode}: {stderr}",
                exit_code=2,
                next_step="Review the error above and verify kubectl connectivity.",
            )

        if len(result.stdout.encode("utf-8")) > self.max_output_bytes:
            raise KubectlError(
                message=f"kubectl output exceeded limit of {self.max_output_bytes} bytes.",
                exit_code=2,
                next_step="Use a label selector (-l) or narrow down target namespaces.",
            )

        return result.stdout
