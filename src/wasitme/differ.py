"""
The Core Attribution Engine for wasitme.
Authored on behalf of Nithin K (Team Lead & Product Owner).

INVARIANTS:
- PURE FUNCTIONS ONLY: Zero I/O, zero network, zero subprocess, zero wall-clock reads.
- 100% DETERMINISTIC: Same two snapshots ALWAYS produce the identical DiffResult.
- Sub-second performance on 500+ resources.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from wasitme.models import (
    DiffResult,
    Issue,
    IssueKind,
    Snapshot,
)


def is_metric_worsened(baseline_issue: Issue, current_issue: Issue) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether an issue present in both baseline and current has worsened.
    Returns (True, reason) if worsened, otherwise (False, None).
    """
    b_metrics = baseline_issue.metrics or {}
    c_metrics = current_issue.metrics or {}

    # 1. Restart Spike Check: delta >= 3
    b_restarts = b_metrics.get("restarts", 0)
    c_restarts = c_metrics.get("restarts", 0)
    if isinstance(b_restarts, (int, float)) and isinstance(c_restarts, (int, float)):
        delta = c_restarts - b_restarts
        if delta >= 3:
            return True, f"Restart count spiked by +{delta} (was {b_restarts}, now {c_restarts})"

    # 2. Workload Availability Check: more unavailable replicas
    b_unavail = b_metrics.get("unavailable", 0)
    c_unavail = c_metrics.get("unavailable", 0)
    if isinstance(b_unavail, (int, float)) and isinstance(c_unavail, (int, float)):
        if c_unavail > b_unavail:
            return (
                True,
                f"Unavailable replicas worsened: {c_unavail} missing (was {b_unavail})",
            )

    # 3. HTTP Status Transition Check: 2xx -> 4xx or 5xx
    b_status = b_metrics.get("status_mode", 200)
    c_status = c_metrics.get("status_mode", 200)
    if isinstance(b_status, int) and isinstance(c_status, int):
        if b_status < 400 and c_status >= 400:
            return True, f"HTTP status degraded from {b_status} to {c_status}"

    # 4. HTTP Latency Check: p50 more than doubled AND above 500ms
    b_p50 = b_metrics.get("p50_ms", 0.0)
    c_p50 = c_metrics.get("p50_ms", 0.0)
    if isinstance(b_p50, (int, float)) and isinstance(c_p50, (int, float)):
        if c_p50 > 500.0 and (b_p50 > 0.0 and c_p50 > (2.0 * b_p50)):
            return (
                True,
                f"HTTP latency degraded: p50 is {c_p50:.1f}ms (>2x baseline {b_p50:.1f}ms and >500ms)",
            )

    # 5. Warning Event Spike Check: count increased significantly (> 5 events after baseline)
    if baseline_issue.kind == IssueKind.WARNING_EVENT:
        b_count = b_metrics.get("count", 0)
        c_count = c_metrics.get("count", 0)
        if isinstance(b_count, int) and isinstance(c_count, int):
            if (c_count - b_count) >= 5:
                return True, f"Warning event count spiked by +{c_count - b_count}"

    return False, None


def diff_snapshots(
    baseline: Snapshot,
    current: Snapshot,
    unsettled_workloads: Optional[List[str]] = None,
) -> DiffResult:
    """
    Diffs baseline and current snapshots into 3 attribution buckets:
    - BROKE_AFTER (Regressions)
    - ALREADY_BROKEN (Pre-existing issues that did not worsen)
    - FIXED (Baseline issues resolved)
    """
    baseline_issues_by_key: Dict[str, Issue] = {i.key: i for i in baseline.issues}
    current_issues_by_key: Dict[str, Issue] = {i.key: i for i in current.issues}

    b_keys: Set[str] = set(baseline_issues_by_key.keys())
    c_keys: Set[str] = set(current_issues_by_key.keys())

    broke_after: List[Issue] = []
    already_broken: List[Issue] = []
    fixed: List[Issue] = []

    # 1. Newly introduced issues: in C but not in B
    new_keys = c_keys - b_keys
    for k in sorted(new_keys):
        broke_after.append(current_issues_by_key[k])

    # 2. Fixed issues: in B but not in C
    fixed_keys = b_keys - c_keys
    for k in sorted(fixed_keys):
        fixed.append(baseline_issues_by_key[k])

    # 3. Common issues: in both B and C
    common_keys = b_keys & c_keys
    for k in sorted(common_keys):
        b_issue = baseline_issues_by_key[k]
        c_issue = current_issues_by_key[k]

        worsened, reason = is_metric_worsened(b_issue, c_issue)
        if worsened:
            # Upgrade issue detail with worsening reason
            augmented_detail = f"{c_issue.detail} [{reason}]"
            worsened_issue = Issue(
                key=c_issue.key,
                kind=c_issue.kind,
                severity=c_issue.severity,
                detail=augmented_detail,
                metrics=c_issue.metrics,
            )
            broke_after.append(worsened_issue)
        else:
            already_broken.append(c_issue)

    # Sort each bucket: 'error' severity first, then alphabetically by key
    def issue_sort_key(item: Issue) -> Tuple[int, str]:
        severity_rank = 0 if item.severity == "error" else 1
        return (severity_rank, item.key)

    broke_after.sort(key=issue_sort_key)
    already_broken.sort(key=issue_sort_key)
    fixed.sort(key=issue_sort_key)

    # Determine Verdict and Exit Code
    if broke_after:
        verdict = "REGRESSION_DETECTED"
        exit_code = 1
    elif already_broken:
        verdict = "PREEXISTING_ISSUES_ONLY"
        exit_code = 0
    else:
        verdict = "CLEAN"
        exit_code = 0

    return DiffResult(
        verdict=verdict,
        broke_after=broke_after,
        already_broken=already_broken,
        fixed=fixed,
        baseline_taken_at=baseline.taken_at,
        current_taken_at=current.taken_at,
        exit_code=exit_code,
        unsettled=unsettled_workloads or [],
    )
