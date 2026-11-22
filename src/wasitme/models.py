"""
Core data models and schemas for wasitme.
Frozen against docs/SPEC.md (Schema Version 1.0).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class IssueKind(str, Enum):
    POD_CRASHLOOP = "POD_CRASHLOOP"
    POD_IMAGE_PULL = "POD_IMAGE_PULL"
    POD_OOMKILLED = "POD_OOMKILLED"
    POD_NOT_READY = "POD_NOT_READY"
    POD_PENDING = "POD_PENDING"
    RESTART_SPIKE = "RESTART_SPIKE"
    WORKLOAD_UNAVAILABLE = "WORKLOAD_UNAVAILABLE"
    NODE_NOT_READY = "NODE_NOT_READY"
    NODE_PRESSURE = "NODE_PRESSURE"
    WARNING_EVENT = "WARNING_EVENT"
    HTTP_DOWN = "HTTP_DOWN"
    HTTP_DEGRADED = "HTTP_DEGRADED"


class Bucket(str, Enum):
    BROKE_AFTER = "BROKE_AFTER"
    ALREADY_BROKEN = "ALREADY_BROKEN"
    FIXED = "FIXED"


@dataclass(frozen=True)
class Issue:
    key: str  # Deterministic composite key: e.g. "POD_CRASHLOOP:default:Deployment:auth"
    kind: IssueKind
    severity: IssueSeverity
    detail: str
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind.value,
            "severity": self.severity.value,
            "detail": self.detail,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Issue:
        return cls(
            key=data["key"],
            kind=IssueKind(data["kind"]),
            severity=IssueSeverity(data["severity"]),
            detail=data["detail"],
            metrics=data.get("metrics", {}),
        )


@dataclass
class WorkloadSnapshot:
    namespace: str
    kind: str  # Deployment, StatefulSet, DaemonSet
    name: str
    desired: int
    available: int
    restarts_total: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PodSnapshot:
    namespace: str
    name: str
    owner_kind: str
    owner_name: str
    phase: str
    ready: bool
    restarts: int
    waiting_reason: Optional[str]
    last_terminated_reason: Optional[str]
    age_seconds: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NodeSnapshot:
    name: str
    ready: bool
    pressure: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EventSnapshot:
    namespace: str
    object: str  # Kind/name
    reason: str
    type: str  # "Warning"
    count: int
    last_seen: str  # ISO 8601 UTC

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HttpCheckSnapshot:
    name: str
    url: str  # Sanitized/redacted
    samples: int
    ok_count: int
    status_mode: int
    p50_ms: float
    error: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClusterScope:
    context: str
    server: str
    namespaces: List[str]
    selector: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Snapshot:
    schema_version: str
    tool_version: str
    taken_at: str  # ISO 8601 UTC
    cluster: ClusterScope
    workloads: List[WorkloadSnapshot]
    pods: List[PodSnapshot]
    nodes: List[NodeSnapshot]
    events: List[EventSnapshot]
    http_checks: List[HttpCheckSnapshot]
    issues: List[Issue]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "taken_at": self.taken_at,
            "cluster": self.cluster.to_dict(),
            "workloads": [w.to_dict() for w in self.workloads],
            "pods": [p.to_dict() for p in self.pods],
            "nodes": [n.to_dict() for n in self.nodes],
            "events": [e.to_dict() for e in self.events],
            "http_checks": [h.to_dict() for h in self.http_checks],
            "issues": [i.to_dict() for i in self.issues],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Snapshot:
        cluster_data = data["cluster"]
        cluster = ClusterScope(
            context=cluster_data.get("context", ""),
            server=cluster_data.get("server", ""),
            namespaces=cluster_data.get("namespaces", []),
            selector=cluster_data.get("selector"),
        )
        workloads = [WorkloadSnapshot(**w) for w in data.get("workloads", [])]
        pods = [PodSnapshot(**p) for p in data.get("pods", [])]
        nodes = [NodeSnapshot(**n) for n in data.get("nodes", [])]
        events = [EventSnapshot(**e) for e in data.get("events", [])]
        http_checks = [HttpCheckSnapshot(**h) for h in data.get("http_checks", [])]
        issues = [Issue.from_dict(i) for i in data.get("issues", [])]

        return cls(
            schema_version=data["schema_version"],
            tool_version=data["tool_version"],
            taken_at=data["taken_at"],
            cluster=cluster,
            workloads=workloads,
            pods=pods,
            nodes=nodes,
            events=events,
            http_checks=http_checks,
            issues=issues,
        )


@dataclass
class DiffResult:
    verdict: str  # "REGRESSION_DETECTED" | "CLEAN" | "PREEXISTING_ISSUES_ONLY"
    broke_after: List[Issue]
    already_broken: List[Issue]
    fixed: List[Issue]
    baseline_taken_at: str
    current_taken_at: str
    exit_code: int
    unsettled: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "baseline_taken_at": self.baseline_taken_at,
            "current_taken_at": self.current_taken_at,
            "summary": {
                "broke_after_count": len(self.broke_after),
                "already_broken_count": len(self.already_broken),
                "fixed_count": len(self.fixed),
            },
            "broke_after": [i.to_dict() for i in self.broke_after],
            "already_broken": [i.to_dict() for i in self.already_broken],
            "fixed": [i.to_dict() for i in self.fixed],
            "unsettled": self.unsettled,
        }
