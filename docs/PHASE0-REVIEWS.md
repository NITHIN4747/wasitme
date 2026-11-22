# Phase 0 Cross-Specialist Contract Reviews — wasitme

**Date:** 2026-11-22  
**Status:** All 4 Reviews Completed & Approved  
**Target:** PRD.md, SPEC.md, ARCHITECTURE.md, DESIGN.md  

---

## 1. Review by Trisha Krishnan (Linux Systems Engineer)

**Focus:** `runner.py`, safe subprocess boundaries, signal handling, and environment isolation.

### Findings:
- ✅ **Allowlist Verification:** SPEC.md and ARCHITECTURE.md mandate that `runner.py` only executes `kubectl get ... -o json`. This prevents any accidental write/mutation commands.
- ✅ **No `shell=True`:** Confirmed that all commands must use list arguments `["kubectl", "get", ...]` with strict type enforcement.
- 💡 **Recommendation (Incorporated):** Ensure `runner.py` explicitly captures both `stdout` and `stderr` and maps non-zero return codes specifically:
  - Return code 127 / FileNotFoundError -> `ExitCode 2` with message "kubectl binary not found".
  - stderr containing "Unauthorized" / "Forbidden" -> `ExitCode 2` with message "Kubernetes API forbidden. Check your RBAC or token credentials".
  - stderr containing "timed out" -> `ExitCode 2` with message "Kubernetes API server timed out".
- **Verdict:** **APPROVED (No Blockers).**

---

## 2. Review by Murugan (Server Engineer)

**Focus:** Node condition parsing, cluster autoscaling churn, and false-positive traps.

### Findings:
- ✅ **Node Readiness & Pressure:** Confirmed `Ready`, `MemoryPressure`, `DiskPressure`, and `PIDPressure` are extracted into `NodeSnapshot`.
- 💡 **Autoscaling Trap Clarification (Incorporated into differ rules):** In clouds with cluster autoscalers (such as AWS Karpenter or Cluster Autoscaler), nodes constantly join and terminate. A node disappearing is NOT automatically a cluster regression unless workloads hosted on it become unavailable or enter crashloop.
- **Node Issue Key Rule:** Node issue keys are strictly `f"{kind}:{node_name}"`. If a node shuts down normally, it is removed from the current snapshot; it should not flag as `BROKE AFTER` unless it enters an explicit unready/pressured state before dying.
- **Verdict:** **APPROVED (No Blockers).**

---

## 3. Review by Jyothika (Networking Engineer)

**Focus:** Synthetic HTTP checks, URL redaction, flapping protection, and timeouts.

### Findings:
- ✅ **Standard Library Invariant:** Confirmed only `urllib.request` is used, maintaining 0 additional dependencies.
- ✅ **URL Sanitization Invariant:** Basic auth credentials (`https://user:password@host/...`) and URL query strings are stripped before recording into the snapshot.
- ✅ **Flapping Protection:** 5 samples per check with majority vote (`status_mode`) and $p50$ latency calculation prevents spurious alerts from a single dropped packet.
- 💡 **Redirect Policy (Incorporated):** `urllib` prober must disallow cross-origin or insecure HTTP downgrade redirects unless explicitly requested.
- **Verdict:** **APPROVED (No Blockers).**

---

## 4. Review by Sunil Chhetri (Cloud Engineer — AWS / EKS)

**Focus:** Least-privilege permissions, EKS compatibility, and zero-cost guarantee.

### Findings:
- ✅ **Zero Cost:** Confirmed that `wasitme` requires zero AWS API calls. It operates purely over standard Kubernetes TLS API via existing `kubectl` context.
- ✅ **Least-Privilege ClusterRole:** A simple read-only `ClusterRole` with `verbs: ["get", "list"]` on `pods`, `deployments`, `statefulsets`, `daemonsets`, `nodes`, `events` is 100% sufficient. No access to `secrets` is requested or required.
- ✅ **EKS Context Handling:** `runner.py` works seamlessly with standard AWS EKS contexts generated via `aws eks update-kubeconfig`.
- **Verdict:** **APPROVED (No Blockers).**

---

## Summary Gate 0 Recommendation
All four reviewing engineers (Trisha Krishnan, Murugan, Jyothika, Sunil Chhetri) have signed off on the contracts. `docs/SPEC.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, and `docs/DESIGN.md` are ready to be frozen by Team Lead & Product Owner Nithin K.
