"""
Kubernetes Pod, Workload, and Event collector.
Owned by Samantha Ruth Prabhu (Senior Backend Engineer).
Invariants:
- Resolves ReplicaSet owners to parent Deployments.
- Excludes completed/succeeded CronJob pods and completed init containers.
- Keys pod and workload issues on (kind, namespace, owner_kind, owner_name), NEVER on pod name.
- Derives all standard issue kinds cleanly without crashing on missing JSON fields.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple

from wasitme.models import (
    ClusterScope,
    EventSnapshot,
    Issue,
    IssueKind,
    IssueSeverity,
    PodSnapshot,
    WorkloadSnapshot,
)
from wasitme.runner import SafeKubectlRunner


class K8sCollector:
    """Collects and derives issues for Pods, Workloads, and Events."""

    def __init__(self, runner: SafeKubectlRunner):
        self.runner = runner

    def collect(
        self, scope: ClusterScope
    ) -> Tuple[List[WorkloadSnapshot], List[PodSnapshot], List[EventSnapshot], List[Issue]]:
        workloads: List[WorkloadSnapshot] = []
        pods: List[PodSnapshot] = []
        events: List[EventSnapshot] = []
        issues: List[Issue] = []

        target_ns_list = scope.namespaces if scope.namespaces else [None]

        for ns in target_ns_list:
            # 1. Collect Workloads (Deployments, StatefulSets, DaemonSets)
            wl_raw = self.runner.get_resources_json(
                "deployments,statefulsets,daemonsets",
                namespace=ns,
                selector=scope.selector,
            )
            wl_snaps, wl_issues = self._parse_workloads(wl_raw)
            workloads.extend(wl_snaps)
            issues.extend(wl_issues)

            # 2. Collect Pods
            pod_raw = self.runner.get_resources_json(
                "pods",
                namespace=ns,
                selector=scope.selector,
            )
            pod_snaps, pod_issues = self._parse_pods(pod_raw)
            pods.extend(pod_snaps)
            issues.extend(pod_issues)

            # 3. Collect Warning Events
            event_raw = self.runner.get_resources_json(
                "events",
                namespace=ns,
                selector=scope.selector,
            )
            event_snaps, event_issues = self._parse_events(event_raw)
            events.extend(event_snaps)
            issues.extend(event_issues)

        # Aggregate total restarts into WorkloadSnapshots
        workload_restarts: Dict[Tuple[str, str, str], int] = {}
        for p in pods:
            wl_key = (p.namespace, p.owner_kind, p.owner_name)
            workload_restarts[wl_key] = workload_restarts.get(wl_key, 0) + p.restarts

        for w in workloads:
            key = (w.namespace, w.kind, w.name)
            if key in workload_restarts:
                w.restarts_total = workload_restarts[key]

        return workloads, pods, events, issues

    def _resolve_owner(self, metadata: Dict[str, Any]) -> Tuple[str, str]:
        """Resolves pod controller owner, elevating ReplicaSet to Deployment when possible."""
        owner_refs = metadata.get("ownerReferences", [])
        if not owner_refs:
            return "Pod", metadata.get("name", "unknown")

        primary = owner_refs[0]
        o_kind = primary.get("kind", "Unknown")
        o_name = primary.get("name", "unknown")

        if o_kind == "ReplicaSet":
            # Strip trailing pod-template-hash (e.g. 'my-dep-79f8b449b' -> 'my-dep')
            parts = o_name.rsplit("-", 1)
            if len(parts) == 2 and len(parts[1]) in (9, 10):
                return "Deployment", parts[0]
            return "Deployment", o_name

        if o_kind == "Job":
            # Check for CronJob parent
            parts = o_name.rsplit("-", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return "CronJob", parts[0]
            return "Job", o_name

        return o_kind, o_name

    def _parse_workloads(self, raw_data: Dict[str, Any]) -> Tuple[List[WorkloadSnapshot], List[Issue]]:
        snapshots: List[WorkloadSnapshot] = []
        issues: List[Issue] = []

        items = raw_data.get("items", [])
        for item in items:
            kind = item.get("kind", "Deployment")
            meta = item.get("metadata", {})
            name = meta.get("name", "")
            ns = meta.get("namespace", "default")
            spec = item.get("spec", {})
            status = item.get("status", {})

            if kind == "DaemonSet":
                desired = status.get("desiredNumberScheduled", 0)
                available = status.get("numberAvailable", 0)
            else:
                desired = spec.get("replicas", 1)
                available = status.get("availableReplicas", 0) or 0

            snap = WorkloadSnapshot(
                namespace=ns,
                kind=kind,
                name=name,
                desired=desired,
                available=available,
                restarts_total=0,  # Will be populated from pods
            )
            snapshots.append(snap)

            # Issue derivation: Unavailable workload replicas
            if desired > 0 and available < desired:
                issues.append(
                    Issue(
                        key=f"WORKLOAD_UNAVAILABLE:{ns}:{kind}:{name}",
                        kind=IssueKind.WORKLOAD_UNAVAILABLE,
                        severity=IssueSeverity.ERROR,
                        detail=f"Workload {kind}/{name} in {ns} has {available}/{desired} available replicas.",
                        metrics={
                            "desired": desired,
                            "available": available,
                            "unavailable": desired - available,
                        },
                    )
                )

        return snapshots, issues

    def _parse_pods(self, raw_data: Dict[str, Any]) -> Tuple[List[PodSnapshot], List[Issue]]:
        snapshots: List[PodSnapshot] = []
        issues: List[Issue] = []

        items = raw_data.get("items", [])
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        for item in items:
            meta = item.get("metadata", {})
            pod_name = meta.get("name", "")
            ns = meta.get("namespace", "default")
            status = item.get("status", {})
            phase = status.get("phase", "Unknown")

            owner_kind, owner_name = self._resolve_owner(meta)

            # Exclude completed/succeeded CronJobs or Pods
            if phase == "Succeeded":
                continue
            if owner_kind == "CronJob" and phase in ("Succeeded", "Completed"):
                continue

            creation_ts_str = meta.get("creationTimestamp")
            age_seconds = 0
            if creation_ts_str:
                try:
                    c_dt = datetime.datetime.fromisoformat(creation_ts_str.replace("Z", "+00:00"))
                    age_seconds = max(0, int((now_utc - c_dt).total_seconds()))
                except Exception:
                    age_seconds = 0

            # Inspect container statuses
            c_statuses = status.get("containerStatuses", [])
            total_restarts = 0
            all_ready = True if c_statuses else False
            waiting_reason: Optional[str] = None
            terminated_reason: Optional[str] = None
            exit_code: Optional[int] = None

            for cs in c_statuses:
                total_restarts += cs.get("restartCount", 0)
                if not cs.get("ready", False):
                    all_ready = False

                state = cs.get("state", {})
                waiting = state.get("waiting")
                if waiting:
                    waiting_reason = waiting.get("reason", "Waiting")

                terminated = state.get("terminated")
                if terminated:
                    terminated_reason = terminated.get("reason")
                    exit_code = terminated.get("exitCode")

                # Also check lastState if available
                last_state = cs.get("lastState", {}).get("terminated")
                if last_state and not terminated_reason:
                    terminated_reason = last_state.get("reason")
                    if exit_code is None:
                        exit_code = last_state.get("exitCode")

            snap = PodSnapshot(
                namespace=ns,
                name=pod_name,
                owner_kind=owner_kind,
                owner_name=owner_name,
                phase=phase,
                ready=all_ready,
                restarts=total_restarts,
                waiting_reason=waiting_reason,
                last_terminated_reason=terminated_reason,
                age_seconds=age_seconds,
            )
            snapshots.append(snap)

            # Base key for pod issues (NEVER uses pod_name)
            base_key = f"{ns}:{owner_kind}:{owner_name}"

            # Derive Issues
            if waiting_reason in ("CrashLoopBackOff", "Error") or terminated_reason in ("CrashLoopBackOff", "Error"):
                issues.append(
                    Issue(
                        key=f"POD_CRASHLOOP:{base_key}",
                        kind=IssueKind.POD_CRASHLOOP,
                        severity=IssueSeverity.ERROR,
                        detail=f"Pod owned by {owner_kind}/{owner_name} is in CrashLoopBackOff.",
                        metrics={
                            "restarts": total_restarts,
                            "exit_code": exit_code,
                            "waiting_reason": waiting_reason,
                        },
                    )
                )
            elif waiting_reason in ("ImagePullBackOff", "ErrImagePull"):
                issues.append(
                    Issue(
                        key=f"POD_IMAGE_PULL:{base_key}",
                        kind=IssueKind.POD_IMAGE_PULL,
                        severity=IssueSeverity.ERROR,
                        detail=f"Pod owned by {owner_kind}/{owner_name} failed image pull ({waiting_reason}).",
                        metrics={"reason": waiting_reason},
                    )
                )
            elif terminated_reason == "OOMKilled" or exit_code == 137:
                issues.append(
                    Issue(
                        key=f"POD_OOMKILLED:{base_key}",
                        kind=IssueKind.POD_OOMKILLED,
                        severity=IssueSeverity.ERROR,
                        detail=f"Pod owned by {owner_kind}/{owner_name} was OOMKilled (ExitCode 137).",
                        metrics={"restarts": total_restarts, "exit_code": exit_code},
                    )
                )
            elif phase == "Pending":
                issues.append(
                    Issue(
                        key=f"POD_PENDING:{base_key}",
                        kind=IssueKind.POD_PENDING,
                        severity=IssueSeverity.WARNING,
                        detail=f"Pod owned by {owner_kind}/{owner_name} is in Pending state.",
                        metrics={"age_seconds": age_seconds},
                    )
                )
            elif phase == "Running" and not all_ready:
                issues.append(
                    Issue(
                        key=f"POD_NOT_READY:{base_key}",
                        kind=IssueKind.POD_NOT_READY,
                        severity=IssueSeverity.WARNING,
                        detail=f"Pod owned by {owner_kind}/{owner_name} is Running but containers are not ready.",
                        metrics={"restarts": total_restarts},
                    )
                )

        return snapshots, issues

    def _parse_events(self, raw_data: Dict[str, Any]) -> Tuple[List[EventSnapshot], List[Issue]]:
        snapshots: List[EventSnapshot] = []
        issues: List[Issue] = []

        items = raw_data.get("items", [])
        for item in items:
            e_type = item.get("type", "Normal")
            if e_type != "Warning":
                continue  # Only capture Warning events

            meta = item.get("metadata", {})
            ns = meta.get("namespace", "default")
            inv_obj = item.get("involvedObject", {})
            obj_kind = inv_obj.get("kind", "Object")
            obj_name = inv_obj.get("name", "unknown")
            reason = item.get("reason", "Warning")
            count = item.get("count", 1) or 1
            last_seen = item.get("lastTimestamp") or meta.get("creationTimestamp") or ""

            # Attempt to resolve owner of object if object is pod
            owner_label = f"{obj_kind}/{obj_name}"
            snap = EventSnapshot(
                namespace=ns,
                object=owner_label,
                reason=reason,
                type="Warning",
                count=count,
                last_seen=last_seen,
            )
            snapshots.append(snap)

            # Issue key keys on (reason, namespace, owner_label)
            issues.append(
                Issue(
                    key=f"WARNING_EVENT:{ns}:{reason}:{owner_label}",
                    kind=IssueKind.WARNING_EVENT,
                    severity=IssueSeverity.WARNING,
                    detail=f"Warning event '{reason}' on {owner_label}: {item.get('message', '')}",
                    metrics={"count": count, "last_seen": last_seen, "reason": reason},
                )
            )

        return snapshots, issues
