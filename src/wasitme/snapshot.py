"""
Snapshot manager and orchestrator.
Owned by Samantha Ruth Prabhu (Senior Backend Engineer).
Invariants:
- Gathers data from K8sCollector, NodeCollector, and HttpProber.
- Produces valid, sanitized Snapshot objects conforming to Schema Version 1.0.
- Handles snapshot serialization and deserialization with strict major version checking.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Dict, List, Optional

from wasitme.collectors.http import HttpProber
from wasitme.collectors.k8s import K8sCollector
from wasitme.collectors.nodes import NodeCollector
from wasitme.models import (
    ClusterScope,
    HttpCheckSnapshot,
    Issue,
    Snapshot,
)
from wasitme.runner import SafeKubectlRunner

CURRENT_SCHEMA_VERSION = "1.0"
TOOL_VERSION = "0.1.0"


class SnapshotError(Exception):
    def __init__(self, message: str, exit_code: int = 3, next_step: str = ""):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.next_step = next_step


class SnapshotManager:
    """Orchestrates collection of cluster state and snapshot file I/O."""

    def __init__(self, runner: SafeKubectlRunner):
        self.runner = runner
        self.k8s_collector = K8sCollector(runner)
        self.node_collector = NodeCollector(runner)
        self.http_prober = HttpProber()

    def capture(
        self,
        namespaces: Optional[List[str]] = None,
        selector: Optional[str] = None,
        http_urls: Optional[Dict[str, str]] = None,
    ) -> Snapshot:
        """Captures full live cluster snapshot."""
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cluster_info = self.runner.get_cluster_context()

        scope = ClusterScope(
            context=cluster_info.get("context", "default"),
            server=cluster_info.get("server", "unknown"),
            namespaces=namespaces or ["default"],
            selector=selector,
        )

        all_issues: List[Issue] = []

        # 1. Collect K8s Pods, Workloads, Warning Events
        workloads, pods, events, k8s_issues = self.k8s_collector.collect(scope)
        all_issues.extend(k8s_issues)

        # 2. Collect Nodes (Cluster-wide)
        nodes, node_issues = self.node_collector.collect()
        all_issues.extend(node_issues)

        # 3. Collect HTTP Probes if provided
        http_snaps: List[HttpCheckSnapshot] = []
        if http_urls:
            for name, url in http_urls.items():
                h_snap, h_issue = self.http_prober.probe(name, url)
                http_snaps.append(h_snap)
                if h_issue:
                    all_issues.append(h_issue)

        # Deduplicate issues by key, keeping highest severity if duplicated
        deduped_issues: Dict[str, Issue] = {}
        for issue in all_issues:
            if issue.key not in deduped_issues:
                deduped_issues[issue.key] = issue
            else:
                existing = deduped_issues[issue.key]
                if existing.severity != "error" and issue.severity == "error":
                    deduped_issues[issue.key] = issue

        return Snapshot(
            schema_version=CURRENT_SCHEMA_VERSION,
            tool_version=TOOL_VERSION,
            taken_at=now_utc,
            cluster=scope,
            workloads=workloads,
            pods=pods,
            nodes=nodes,
            events=events,
            http_checks=http_snaps,
            issues=list(deduped_issues.values()),
        )

    @staticmethod
    def save(snapshot: Snapshot, output_path: str = ".wasitme-snapshot.json") -> Path:
        """Writes snapshot to disk as formatted JSON."""
        target = Path(output_path)
        data = snapshot.to_dict()
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return target

    @staticmethod
    def load(file_path: str) -> Snapshot:
        """Reads and validates snapshot from disk."""
        target = Path(file_path)
        if not target.exists():
            raise SnapshotError(
                message=f"Snapshot file not found: '{file_path}'.",
                exit_code=3,
                next_step="Run 'wasitme snapshot' first to capture a baseline snapshot.",
            )

        try:
            content = target.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as e:
            raise SnapshotError(
                message=f"Corrupt or invalid JSON in snapshot file '{file_path}': {e}",
                exit_code=3,
                next_step="Delete the corrupted file and re-take baseline using 'wasitme snapshot'.",
            )

        # Validate Schema Version
        schema_v = data.get("schema_version")
        if not schema_v:
            raise SnapshotError(
                message=f"Missing 'schema_version' in snapshot file '{file_path}'.",
                exit_code=3,
                next_step="Re-take snapshot using current wasitme version.",
            )

        file_major = schema_v.split(".")[0]
        current_major = CURRENT_SCHEMA_VERSION.split(".")[0]
        if file_major != current_major:
            raise SnapshotError(
                message=f"Incompatible snapshot schema major version '{schema_v}' (expected '{CURRENT_SCHEMA_VERSION}').",
                exit_code=3,
                next_step="Re-take baseline snapshot using 'wasitme snapshot' matching your CLI version.",
            )

        try:
            return Snapshot.from_dict(data)
        except Exception as e:
            raise SnapshotError(
                message=f"Snapshot structure validation failed: {e}",
                exit_code=3,
                next_step="Ensure snapshot file was generated by wasitme and not manually modified.",
            )
