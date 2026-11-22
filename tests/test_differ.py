"""
Unit tests for wasitme.differ attribution engine.
Targeting >= 95% coverage on differ.py.
"""
from __future__ import annotations

from wasitme.differ import diff_snapshots, is_metric_worsened
from wasitme.models import (
    ClusterScope,
    Issue,
    IssueKind,
    IssueSeverity,
    Snapshot,
)


def create_test_snapshot(issues: list[Issue]) -> Snapshot:
    return Snapshot(
        schema_version="1.0",
        tool_version="0.1.0",
        taken_at="2026-11-22T08:00:00Z",
        cluster=ClusterScope(
            context="test-ctx",
            server="https://k8s.test",
            namespaces=["test-ns"],
            selector=None,
        ),
        workloads=[],
        pods=[],
        nodes=[],
        events=[],
        http_checks=[],
        issues=issues,
    )


def test_clean_diff_no_issues() -> None:
    snap_a = create_test_snapshot([])
    snap_b = create_test_snapshot([])
    result = diff_snapshots(snap_a, snap_b)

    assert result.verdict == "CLEAN"
    assert result.exit_code == 0
    assert len(result.broke_after) == 0
    assert len(result.already_broken) == 0
    assert len(result.fixed) == 0


def test_new_regression_detected() -> None:
    new_issue = Issue(
        key="POD_CRASHLOOP:test-ns:Deployment:billing",
        kind=IssueKind.POD_CRASHLOOP,
        severity=IssueSeverity.ERROR,
        detail="CrashLoopBackOff",
    )
    snap_a = create_test_snapshot([])
    snap_b = create_test_snapshot([new_issue])

    result = diff_snapshots(snap_a, snap_b)
    assert result.verdict == "REGRESSION_DETECTED"
    assert result.exit_code == 1
    assert len(result.broke_after) == 1
    assert result.broke_after[0].key == new_issue.key


def test_issue_fixed() -> None:
    old_issue = Issue(
        key="POD_NOT_READY:test-ns:Deployment:auth",
        kind=IssueKind.POD_NOT_READY,
        severity=IssueSeverity.WARNING,
        detail="Not ready",
    )
    snap_a = create_test_snapshot([old_issue])
    snap_b = create_test_snapshot([])

    result = diff_snapshots(snap_a, snap_b)
    assert result.verdict == "CLEAN"
    assert result.exit_code == 0
    assert len(result.fixed) == 1
    assert result.fixed[0].key == old_issue.key


def test_preexisting_issue_not_worsened() -> None:
    issue_a = Issue(
        key="POD_CRASHLOOP:test-ns:Deployment:logger",
        kind=IssueKind.POD_CRASHLOOP,
        severity=IssueSeverity.ERROR,
        detail="Pre-existing crashloop",
        metrics={"restarts": 5},
    )
    issue_b = Issue(
        key="POD_CRASHLOOP:test-ns:Deployment:logger",
        kind=IssueKind.POD_CRASHLOOP,
        severity=IssueSeverity.ERROR,
        detail="Pre-existing crashloop",
        metrics={"restarts": 6},  # Only +1 restart, not a spike >= 3
    )

    snap_a = create_test_snapshot([issue_a])
    snap_b = create_test_snapshot([issue_b])

    result = diff_snapshots(snap_a, snap_b)
    assert result.verdict == "PREEXISTING_ISSUES_ONLY"
    assert result.exit_code == 0
    assert len(result.already_broken) == 1
    assert len(result.broke_after) == 0


def test_restart_spike_qualifies_as_broke_after() -> None:
    issue_a = Issue(
        key="POD_CRASHLOOP:test-ns:Deployment:logger",
        kind=IssueKind.POD_CRASHLOOP,
        severity=IssueSeverity.ERROR,
        detail="Crashloop",
        metrics={"restarts": 2},
    )
    issue_b = Issue(
        key="POD_CRASHLOOP:test-ns:Deployment:logger",
        kind=IssueKind.POD_CRASHLOOP,
        severity=IssueSeverity.ERROR,
        detail="Crashloop",
        metrics={"restarts": 7},  # Delta +5 >= 3
    )

    snap_a = create_test_snapshot([issue_a])
    snap_b = create_test_snapshot([issue_b])

    result = diff_snapshots(snap_a, snap_b)
    assert result.verdict == "REGRESSION_DETECTED"
    assert result.exit_code == 1
    assert len(result.broke_after) == 1
    assert "Restart count spiked" in result.broke_after[0].detail


def test_http_status_degradation_qualifies_as_broke_after() -> None:
    issue_a = Issue(
        key="HTTP:checkout",
        kind=IssueKind.HTTP_DEGRADED,
        severity=IssueSeverity.WARNING,
        detail="Latency slow",
        metrics={"status_mode": 200, "p50_ms": 300},
    )
    issue_b = Issue(
        key="HTTP:checkout",
        kind=IssueKind.HTTP_DEGRADED,
        severity=IssueSeverity.ERROR,
        detail="Failing",
        metrics={"status_mode": 500, "p50_ms": 300},
    )

    worsened, reason = is_metric_worsened(issue_a, issue_b)
    assert worsened is True
    assert "HTTP status degraded from 200 to 500" in (reason or "")


def test_http_latency_doubled_above_500ms() -> None:
    issue_a = Issue(
        key="HTTP:api",
        kind=IssueKind.HTTP_DEGRADED,
        severity=IssueSeverity.WARNING,
        detail="Healthy",
        metrics={"p50_ms": 200.0},
    )
    issue_b = Issue(
        key="HTTP:api",
        kind=IssueKind.HTTP_DEGRADED,
        severity=IssueSeverity.WARNING,
        detail="Slow",
        metrics={"p50_ms": 600.0},  # >2x and >500ms
    )

    worsened, reason = is_metric_worsened(issue_a, issue_b)
    assert worsened is True
    assert "HTTP latency degraded" in (reason or "")


def test_workload_unavailable_replica_increase() -> None:
    issue_a = Issue(
        key="WORKLOAD_UNAVAILABLE:default:Deployment:web",
        kind=IssueKind.WORKLOAD_UNAVAILABLE,
        severity=IssueSeverity.ERROR,
        detail="1 replica missing",
        metrics={"unavailable": 1},
    )
    issue_b = Issue(
        key="WORKLOAD_UNAVAILABLE:default:Deployment:web",
        kind=IssueKind.WORKLOAD_UNAVAILABLE,
        severity=IssueSeverity.ERROR,
        detail="3 replicas missing",
        metrics={"unavailable": 3},
    )

    worsened, reason = is_metric_worsened(issue_a, issue_b)
    assert worsened is True
    assert "Unavailable replicas worsened" in (reason or "")


def test_warning_event_count_spike() -> None:
    issue_a = Issue(
        key="WARNING_EVENT:default:BackOff:Pod/worker",
        kind=IssueKind.WARNING_EVENT,
        severity=IssueSeverity.WARNING,
        detail="BackOff",
        metrics={"count": 2},
    )
    issue_b = Issue(
        key="WARNING_EVENT:default:BackOff:Pod/worker",
        kind=IssueKind.WARNING_EVENT,
        severity=IssueSeverity.WARNING,
        detail="BackOff",
        metrics={"count": 10},  # Spike >= 5
    )

    worsened, reason = is_metric_worsened(issue_a, issue_b)
    assert worsened is True
    assert "Warning event count spiked" in (reason or "")

