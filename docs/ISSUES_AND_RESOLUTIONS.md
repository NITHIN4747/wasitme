# Engineering Challenges, Blockers & Resolutions — wasitme

**Project:** `wasitme` (Kubernetes Deploy Blame Attribution Engine)  
**Team Lead & Product Owner:** Nithin K  
**Version:** 1.0 (v0.1.0 Release)  
**Date:** 22 Nov 2026  

---

## 📋 Overview

During the design, architecture, and parallel engineering of `wasitme`, several critical technical challenges and potential blockers were identified. This document details each problem, the architectural analysis, the chosen resolution strategy, and how it was successfully verified.

---

## 1. The Rolling Update Pod Identity Problem (Core Attribution)

### 🔴 The Challenge / Blocker
In Kubernetes, when a `Deployment` executes a rolling update or pod restart:
- Old pods are destroyed, and new pods are spawned with dynamically randomized hash suffixes (e.g. `api-gateway-784f9b8c-x12y` is terminated and replaced by `api-gateway-893c5d6f-z98w`).
- If health issues were keyed on raw pod names (like standard diff tools do), a pre-existing crashlooping pod would register as **"FIXED"** (because the old pod name disappeared) while the newly spawned pod would register as **"BROKE AFTER YOUR CHANGE"** (because the new pod name appeared).
- This would produce a **100% false positive regression rate**, rendering blame attribution useless on real-world rollouts.

### 💡 Plan & Solution
1. **Ownership Hierarchy Resolution (`K8sCollector._resolve_owner`):**
   - Implemented dynamic traversal of Kubernetes `ownerReferences`.
   - When inspecting a pod owned by a `ReplicaSet`, the collector extracts the parent `Deployment` name (by parsing `ownerReferences` or stripping the pod-template-hash suffix).
   - For `Jobs` launched by a `CronJob`, it elevates ownership to the root `CronJob`.
2. **Stable Composite Issue Keying:**
   - Pod-level and workload-level issues are **strictly keyed on:**
     ```
     f"{issue_kind}:{namespace}:{owner_kind}:{owner_name}"
     ```
   - Pod names are **never** included in the identity key.
3. **Verification:**
   - Authored named test `test_pod_replaced_same_crashloop_persists_remains_already_broken` in `tests/test_edge_cases.py`.
   - Verified that when every pod in a deployment is replaced with a new name, an ongoing crashloop remains classified under `ALREADY BROKEN`.

---

## 2. Differ Determinism & Test Hermeticity

### 🔴 The Challenge / Blocker
If the diffing logic performed live I/O, subprocess execution, or read system wall-clock timestamps:
- Diffs between the same two snapshot files would become non-deterministic.
- Unit testing would require running Kubernetes clusters, leading to slow and flaky CI test runs.
- Race conditions could occur if the cluster state changed between the start and finish of diff calculations.

### 💡 Plan & Solution
1. **Strict I/O-Free Purity Invariant (ADR-003):**
   - `src/wasitme/differ.py` was architected with **zero I/O dependencies**. It imports only dataclasses from `models.py` and standard Python types.
   - It performs in-memory set differences ($B \setminus C$, $C \setminus B$, $B \cap C$) and dictionary lookups.
2. **Sub-Second Performance Guarantee:**
   - Built with pure $O(1)$ dictionary key lookups.
   - Benchmarked in `test_large_namespace_500_pods_performance`: diffing 500 pods and dozens of issues finishes in **0.05 seconds** (40x faster than the 2.0-second performance ceiling).
3. **Verification:**
   - `differ.py` achieved **100% line and branch test coverage** in pytest.

---

## 3. Transient Flapping of HTTP Health Probes

### 🔴 The Challenge / Blocker
Synthetic HTTP health checks are prone to transient network blips (e.g., DNS resolution delays, single dropped packets, or momentary 500 error spikes). If a single dropped request flipped a check to `HTTP_DOWN`, a deployment could be falsely flagged as a regression, failing CI/CD builds.

### 💡 Plan & Solution
1. **5-Sample Majority Consensus:**
   - `src/wasitme/collectors/http.py` runs **5 consecutive samples** against target endpoints.
   - Computes `status_mode` using `collections.Counter(statuses).most_common(1)[0]`.
   - A single anomalous 500 or timeout surrounded by four 200 OK responses maintains a majority status of 200 OK.
2. **$p50$ Median Latency Calculation:**
   - Instead of mean latency (which is skewed by single outliers), calculates median $p50$ response time.
   - Only flags `HTTP_DEGRADED` if the response time more than doubles **AND** exceeds 500 ms.
3. **Verification:**
   - Verified via `test_flapping_http_majority_agreement` in `tests/test_edge_cases.py`.

---

## 4. Subprocess Execution & Command Injection Protection

### 🔴 The Challenge / Blocker
The CLI needs to accept user-provided flags (namespaces, label selectors, contexts) and execute system commands. Concatenating strings into shell commands (`shell=True`) would create severe command injection vulnerabilities.

### 💡 Plan & Solution
1. **Fortified Subprocess Layer (`src/wasitme/runner.py`):**
   - Enforced `shell=False` across all subprocess invocations.
   - Executable arguments are passed strictly as safe arrays: `["kubectl", "get", resource, "-n", namespace, "-o", "json"]`.
2. **Resource Allowlist:**
   - Validates requested resources against an immutable set: `{"pods", "deployments", "statefulsets", "daemonsets", "nodes", "events", "namespaces"}`.
   - Any attempt to query `secrets` or invalid resources raises `KubectlError` with exit code 2 immediately.
3. **Actionable Exit Code 2 Mapping:**
   - Missing `kubectl` -> guides user to installation docs.
   - Unauthorized / Forbidden -> guides user to check RBAC and tokens.
   - Timeouts -> caps at 15s with connectivity guidance.
   - Memory bounds -> output capped at 10 MB per call.
4. **Verification:**
   - Verified via `tests/test_runner.py` (`test_unauthorized_resource_rejected`).

---

## 5. False Alarms from Cloud Autoscaler Node Churn

### 🔴 The Challenge / Blocker
Modern Kubernetes clusters on AWS/GCP use autoscalers (Karpenter or Cluster Autoscaler) that frequently terminate idle nodes and provision new ones. If a node disappearing were treated as a failure, routine scale-down events would trigger false regression alerts.

### 💡 Plan & Solution
1. **Decoupled Node Life-Cycle:**
   - Node issue keys are structured as `f"NODE:{node_name}"` and `f"PRESSURE:{pressure_type}:{node_name}"`.
   - A node cleanly leaving the cluster is simply removed from the current node set. It is only considered an issue if it transitions into `NotReady` or reports pressure flags (`MemoryPressure`, `DiskPressure`, `PIDPressure`).
2. **Verification:**
   - Verified in `test_node_added_or_removed_normal_churn`: adding or removing healthy nodes produces zero regressions and a `CLEAN` verdict.

---

## 6. Settle Windows for Mid-Rollout Pods

### 🔴 The Challenge / Blocker
When a deployment rollout is actively in progress:
- Newly scheduled pods may legitimately spend a few seconds in `Pending` (scheduling) or `ContainerCreating` (image pull).
- Diffing immediately after `kubectl apply` without waiting could capture transitory pod initialization as a regression.

### 💡 Plan & Solution
1. **Settle Flags & Settle Windows:**
   - Implemented `--wait DURATION` (e.g. `--wait 15s`) to allow pods to settle.
   - Implemented `--rollout KIND/NAME` to monitor `kubectl rollout status` before triggering capture.
   - Introduced the `UNSETTLED` bucket: workloads detected mid-rollout without a wait window are reported explicitly with a warning rather than guessing or prematurely failing.
2. **Verification:**
   - Verified via `test_pod_pending_during_rollout_not_regression_when_unsettled`.

---

## 7. Zero Cloud Cost Guarantee & AWS Watchdog

### 🔴 The Challenge / Blocker
Testing against real cloud infrastructure (like AWS EKS) can quickly exhaust free credits or incur surprise charges if resources (load balancers, NAT gateways, EC2 nodes) are left running unattended.

### 💡 Plan & Solution
1. **Hermetic Local Testing:**
   - All unit tests and edge cases run locally in-memory or on local Docker `kind` clusters in GitHub Actions ($0 cost).
2. **Automated Cloud Watchdog (`scripts/aws_watchdog.py`):**
   - Authored by Rakul Preet Singh (AWS Cloud Watchdog).
   - Scans AWS Cost Explorer, Budgets, EC2, and EKS clusters using read-only calls.
   - Validates $0.00 spent and alerts if any rogue instance is detected outside demo recording windows.
3. **Verification:**
   - Running `scripts/aws_watchdog.py` confirms clean status: `"All cloud resources clean ($0.00 spend verified)."`

---

## 8. Package Environment & Strict Type Hygiene

### 🔴 The Challenge / Blocker
Initial tests in the clean Python 3.14 environment encountered missing local packages, unused variables flagged by `ruff`, and strict `mypy` annotations.

### 💡 Plan & Solution
1. Configured modern packaging using `pyproject.toml` with `hatchling` and pinned dependencies (`typer`, `rich`).
2. Automated local environment bootstrap using `uv venv` and `uv pip install -e ".[dev]"`.
3. Adjusted lint rules for Typer's functional option defaults (`B008`) and exception chaining (`B904`).
4. Re-ran linters and achieved:
   - `ruff check`: **0 errors**.
   - `mypy strict`: **0 errors**.
   - `pytest`: **27/27 tests passed** with **100% coverage on `differ.py`**.

---

## 🏁 Summary Table of Issues & Resolutions

| # | Challenge / Blocker | Root Cause | Resolution Strategy | Test Evidence |
|---|---|---|---|---|
| **1** | Rolling update pod replacement false regressions | Pod names have dynamic random hashes on every deploy | Elevated ownership resolution to Deployment; key on `(kind, namespace, owner_kind, owner_name)` | `test_pod_replaced_same_crashloop_persists_remains_already_broken` |
| **2** | Differ non-determinism | External I/O or timing in diff logic | Pure functional `differ.py` with 0 I/O imports; in-memory set operations | `test_clean_diff_no_issues`, 100% differ coverage |
| **3** | Flapping HTTP endpoints | Transient single-packet drops / timeouts | 5-sample prober with majority vote consensus and $p50$ latency | `test_flapping_http_majority_agreement` |
| **4** | Command injection risks | Shell execution of user input | `shell=False`, array execution, 10MB buffer cap, strict resource allowlist | `test_unauthorized_resource_rejected` |
| **5** | Autoscaler node churn | Nodes dynamically joining/leaving | Separated node departure from node condition pressure flags | `test_node_added_or_removed_normal_churn` |
| **6** | Transitory pod startup errors | Capturing diff during active image pulling | Added `--wait`, `--rollout`, and explicit `UNSETTLED` warning bucket | `test_pod_pending_during_rollout_not_regression_when_unsettled` |
| **7** | Surprise cloud costs | Unmonitored cloud resources | Local `kind` CI, $0 budget alert template, `scripts/aws_watchdog.py` | `scripts/aws_watchdog.py` clean exit |
| **8** | Environment & type strictness | Missing dev packages & strict mypy checks | Packaged with `uv`, refined ruff rules, strict type annotations | 27/27 pytest, 0 ruff errors, 0 mypy errors |
