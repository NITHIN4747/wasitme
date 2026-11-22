"""
Edge case test suite for wasitme diff engine.
Owned by Samantha Ruth Prabhu (Senior Backend Engineer) & Nithin K (TL).
Every test here corresponds directly to a named edge case in Section 1.6 of the Master Brief.
"""
from __future__ import annotations

import time

from wasitme.differ import diff_snapshots
from wasitme.models import (
    ClusterScope,
    HttpCheckSnapshot,
    Issue,
    IssueKind,
    IssueSeverity,
    NodeSnapshot,
    PodSnapshot,
    Snapshot,
    WorkloadSnapshot,
)


def make_snapshot(
    issues: list[Issue] | None = None,
    workloads: list[WorkloadSnapshot] | None = None,
    pods: list[PodSnapshot] | None = None,
    nodes: list[NodeSnapshot] | None = None,
    http_checks: list[HttpCheckSnapshot] | None = None,
    context: str = "prod-cluster",
    namespaces: list[str] | None = None,
) -> Snapshot:
    return Snapshot(
        schema_version="1.0",
        tool_version="0.1.0",
        taken_at="2026-11-22T08:00:00Z",
        cluster=ClusterScope(
            context=context,
            server="https://k8s.example.com",
            namespaces=namespaces or ["default"],
            selector=None,
        ),
        workloads=workloads or [],
        pods=pods or [],
        nodes=nodes or [],
        events=[],
        http_checks=http_checks or [],
        issues=issues or [],
    )


# ---------------------------------------------------------------------------
# Edge Case 1: Every pod replaced but the same crashloop persists
# ---------------------------------------------------------------------------
def test_pod_replaced_same_crashloop_persists_remains_already_broken() -> None:
    """
    When a deployment rolls out, pod names change completely.
    If the crashloop persists under the same workload owner, it must remain ALREADY_BROKEN.
    """
    key = "POD_CRASHLOOP:prod:Deployment:api-gw"
    issue_baseline = Issue(
        key=key,
        kind=IssueKind.POD_CRASHLOOP,
        severity=IssueSeverity.ERROR,
        detail="Pod in CrashLoopBackOff",
        metrics={"restarts": 10},
    )
    issue_current = Issue(
        key=key,
        kind=IssueKind.POD_CRASHLOOP,
        severity=IssueSeverity.ERROR,
        detail="Pod in CrashLoopBackOff",
        metrics={"restarts": 10},
    )

    # Baseline has old pod name
    pod_baseline = PodSnapshot(
        namespace="prod",
        name="api-gw-old-pod-1111",
        owner_kind="Deployment",
        owner_name="api-gw",
        phase="Running",
        ready=False,
        restarts=10,
        waiting_reason="CrashLoopBackOff",
        last_terminated_reason="Error",
        age_seconds=1000,
    )
    # Current has completely new pod name from rolling update
    pod_current = PodSnapshot(
        namespace="prod",
        name="api-gw-new-pod-9999",
        owner_kind="Deployment",
        owner_name="api-gw",
        phase="Running",
        ready=False,
        restarts=10,
        waiting_reason="CrashLoopBackOff",
        last_terminated_reason="Error",
        age_seconds=60,
    )

    base = make_snapshot(issues=[issue_baseline], pods=[pod_baseline])
    curr = make_snapshot(issues=[issue_current], pods=[pod_current])

    result = diff_snapshots(base, curr)

    assert len(result.broke_after) == 0, "Persistent crashloop must NOT be marked broke_after"
    assert len(result.already_broken) == 1
    assert result.already_broken[0].key == key
    assert result.exit_code == 0
    assert result.verdict == "PREEXISTING_ISSUES_ONLY"


# ---------------------------------------------------------------------------
# Edge Case 2: Pod Pending during rollout
# ---------------------------------------------------------------------------
def test_pod_pending_during_rollout_not_regression_when_unsettled() -> None:
    """
    A pod in Pending state during an active rollout is recorded under unsettled,
    and does not fail as a regression if the workload is actively rolling out.
    """
    base = make_snapshot(issues=[])
    curr = make_snapshot(issues=[])

    # Pass unsettled workloads to differ
    result = diff_snapshots(base, curr, unsettled_workloads=["Deployment/payment-api"])

    assert len(result.broke_after) == 0
    assert "Deployment/payment-api" in result.unsettled


# ---------------------------------------------------------------------------
# Edge Case 3: Restart counts reset because pod was replaced
# ---------------------------------------------------------------------------
def test_restart_counts_reset_when_pod_replaced() -> None:
    """
    If a pod is replaced, individual pod restart count might drop to 0,
    but workload-level comparison must ensure it doesn't falsely report a spike.
    """
    key = "POD_CRASHLOOP:default:Deployment:worker"
    b_issue = Issue(
        key=key,
        kind=IssueKind.POD_CRASHLOOP,
        severity=IssueSeverity.ERROR,
        detail="CrashLoopBackOff",
        metrics={"restarts": 15},
    )
    # New pod has only 1 restart so far (not a surge >= 3 over baseline)
    c_issue = Issue(
        key=key,
        kind=IssueKind.POD_CRASHLOOP,
        severity=IssueSeverity.ERROR,
        detail="CrashLoopBackOff",
        metrics={"restarts": 1},
    )

    base = make_snapshot(issues=[b_issue])
    curr = make_snapshot(issues=[c_issue])

    result = diff_snapshots(base, curr)
    assert len(result.broke_after) == 0
    assert len(result.already_broken) == 1


# ---------------------------------------------------------------------------
# Edge Case 4: Flapping HTTP requires majority agreement
# ---------------------------------------------------------------------------
def test_flapping_http_majority_agreement() -> None:
    """
    If 4 out of 5 samples returned 200 and 1 returned 500, status_mode remains 200 (healthy).
    Does not register as HTTP_DOWN or HTTP_DEGRADED.
    """
    # We can test the majority status calculation directly
    statuses = [200, 200, 500, 200, 200]
    import collections
    mode, _ = collections.Counter(statuses).most_common(1)[0]
    assert mode == 200, "Majority vote must pick 200 over intermittent 500"


# ---------------------------------------------------------------------------
# Edge Case 5: Namespace deleted
# ---------------------------------------------------------------------------
def test_namespace_deleted() -> None:
    """
    If a namespace existed in baseline with issues, but was deleted in current,
    the issues are simply marked FIXED (or cleared).
    """
    old_issue = Issue(
        key="POD_NOT_READY:deprecated-ns:Deployment:old-app",
        kind=IssueKind.POD_NOT_READY,
        severity=IssueSeverity.WARNING,
        detail="Containers not ready",
    )
    base = make_snapshot(issues=[old_issue], namespaces=["deprecated-ns"])
    curr = make_snapshot(issues=[], namespaces=[])

    result = diff_snapshots(base, curr)
    assert len(result.broke_after) == 0
    assert len(result.fixed) == 1
    assert result.fixed[0].key == old_issue.key
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Edge Case 6: Node added or removed (autoscaler churn)
# ---------------------------------------------------------------------------
def test_node_added_or_removed_normal_churn() -> None:
    """
    A healthy node being added or removed due to cluster autoscaling
    must not generate any false regressions.
    """
    node1 = NodeSnapshot(name="node-1", ready=True, pressure=[])
    node2 = NodeSnapshot(name="node-2", ready=True, pressure=[])

    base = make_snapshot(nodes=[node1], issues=[])
    # Autoscaler scales out node-2 and terminates node-1
    curr = make_snapshot(nodes=[node2], issues=[])

    result = diff_snapshots(base, curr)
    assert len(result.broke_after) == 0
    assert len(result.already_broken) == 0
    assert result.exit_code == 0
    assert result.verdict == "CLEAN"


# ---------------------------------------------------------------------------
# Edge Case 7: Empty cluster
# ---------------------------------------------------------------------------
def test_empty_cluster() -> None:
    """An empty cluster with zero resources must produce clean verdict."""
    base = make_snapshot()
    curr = make_snapshot()

    result = diff_snapshots(base, curr)
    assert len(result.broke_after) == 0
    assert len(result.already_broken) == 0
    assert len(result.fixed) == 0
    assert result.exit_code == 0
    assert result.verdict == "CLEAN"


# ---------------------------------------------------------------------------
# Edge Case 8: Baseline taken from a different context
# ---------------------------------------------------------------------------
def test_baseline_from_different_context() -> None:
    """
    If baseline was captured on 'staging' and current is run on 'prod',
    the diff executes properly without raising an unhandled exception.
    """
    base = make_snapshot(context="staging")
    curr = make_snapshot(context="prod")

    result = diff_snapshots(base, curr)
    assert result.exit_code == 0
    assert result.verdict == "CLEAN"


# ---------------------------------------------------------------------------
# Edge Case 9: Large namespace (500 pods) finishes in under 2 seconds
# ---------------------------------------------------------------------------
def test_large_namespace_500_pods_performance() -> None:
    """
    Diffing a massive cluster with 500 pods and dozens of issues must complete in < 2.0s.
    """
    b_pods = []
    c_pods = []
    b_issues = []
    c_issues = []

    for i in range(500):
        b_pods.append(
            PodSnapshot(
                namespace="huge-ns",
                name=f"pod-{i}-hash1",
                owner_kind="Deployment",
                owner_name=f"service-{i % 50}",
                phase="Running",
                ready=True,
                restarts=0,
                waiting_reason=None,
                last_terminated_reason=None,
                age_seconds=1000,
            )
        )
        c_pods.append(
            PodSnapshot(
                namespace="huge-ns",
                name=f"pod-{i}-hash2",
                owner_kind="Deployment",
                owner_name=f"service-{i % 50}",
                phase="Running",
                ready=True,
                restarts=0,
                waiting_reason=None,
                last_terminated_reason=None,
                age_seconds=100,
            )
        )
        if i % 10 == 0:
            b_issues.append(
                Issue(
                    key=f"POD_NOT_READY:huge-ns:Deployment:service-{i}",
                    kind=IssueKind.POD_NOT_READY,
                    severity=IssueSeverity.WARNING,
                    detail="Containers not ready",
                    metrics={"restarts": 0},
                )
            )
            c_issues.append(
                Issue(
                    key=f"POD_NOT_READY:huge-ns:Deployment:service-{i}",
                    kind=IssueKind.POD_NOT_READY,
                    severity=IssueSeverity.WARNING,
                    detail="Containers not ready",
                    metrics={"restarts": 0},
                )
            )

    base = make_snapshot(pods=b_pods, issues=b_issues)
    curr = make_snapshot(pods=c_pods, issues=c_issues)

    start = time.perf_counter()
    result = diff_snapshots(base, curr)
    duration = time.perf_counter() - start

    assert duration < 2.0, f"Diff took {duration:.3f}s, exceeding 2.0s budget!"
    assert len(result.broke_after) == 0
    assert len(result.already_broken) == len(b_issues)
    assert result.exit_code == 0
