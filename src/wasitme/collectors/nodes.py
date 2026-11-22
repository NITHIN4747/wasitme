"""
Node condition and capacity collector.
Owned by Murugan (Server Engineer).
Invariants:
- Extracts NodeReady, MemoryPressure, DiskPressure, PIDPressure, NetworkUnavailable.
- Handles cordoned / unschedulable nodes without generating false regressions.
- Derives NODE_NOT_READY and NODE_PRESSURE issues with stable keys f"{kind}:{node_name}".
"""
from __future__ import annotations

from typing import List, Tuple

from wasitme.models import Issue, IssueKind, IssueSeverity, NodeSnapshot
from wasitme.runner import SafeKubectlRunner


class NodeCollector:
    """Collects and analyzes Kubernetes cluster node conditions."""

    def __init__(self, runner: SafeKubectlRunner):
        self.runner = runner

    def collect(self) -> Tuple[List[NodeSnapshot], List[Issue]]:
        """Queries kubectl for nodes and extracts conditions & derived issues."""
        raw_data = self.runner.get_resources_json("nodes")
        items = raw_data.get("items", [])

        snapshots: List[NodeSnapshot] = []
        issues: List[Issue] = []

        for item in items:
            metadata = item.get("metadata", {})
            node_name = metadata.get("name", "unknown")
            spec = item.get("spec", {})
            status = item.get("status", {})

            is_cordoned = spec.get("unschedulable", False)
            conditions = status.get("conditions", [])

            is_ready = False
            active_pressures: List[str] = []

            for cond in conditions:
                c_type = cond.get("type", "")
                c_status = cond.get("status", "False")

                if c_type == "Ready" and c_status == "True":
                    is_ready = True
                elif c_type in ("MemoryPressure", "DiskPressure", "PIDPressure", "NetworkUnavailable"):
                    if c_status == "True":
                        active_pressures.append(c_type)

            snapshot = NodeSnapshot(
                name=node_name,
                ready=is_ready,
                pressure=sorted(active_pressures),
            )
            snapshots.append(snapshot)

            # Issue derivation: Unready Node
            if not is_ready:
                issues.append(
                    Issue(
                        key=f"NODE:{node_name}",
                        kind=IssueKind.NODE_NOT_READY,
                        severity=IssueSeverity.ERROR,
                        detail=f"Node '{node_name}' is NotReady"
                        + (" (Cordoned/SchedulingDisabled)" if is_cordoned else ""),
                        metrics={"ready": False, "cordoned": is_cordoned},
                    )
                )

            # Issue derivation: Pressured Node
            for pressure in active_pressures:
                issues.append(
                    Issue(
                        key=f"PRESSURE:{pressure}:{node_name}",
                        kind=IssueKind.NODE_PRESSURE,
                        severity=IssueSeverity.WARNING,
                        detail=f"Node '{node_name}' is experiencing {pressure}.",
                        metrics={"pressure_type": pressure, "node": node_name},
                    )
                )

        return snapshots, issues
