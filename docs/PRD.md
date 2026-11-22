# Product Requirements Document (PRD) — wasitme

**Version:** 1.0  
**Status:** Frozen (Phase 0)  
**Author:** Ronaldo (Product Engineer)  
**Approver:** Nithin K (Team Lead & Product Owner)  
**Package Name:** `wasitme` | **License:** MIT  

---

## 1. Product Vision & Attribution Promise

### 1.1 The Attribution Promise
**"Did my change break this, or was it already broken?"**

`wasitme` is an open-source Python CLI designed for platform engineers, SREs, and developers deploying to shared or resource-constrained Kubernetes clusters. It eliminates post-deployment finger-pointing by capturing a pre-deploy baseline snapshot and diffing it against the live post-deploy state to classify all discovered issues into three unmistakable buckets:
1. 🔴 **BROKE AFTER YOUR CHANGE** (New regressions or significantly worsened existing issues)
2. 🟡 **ALREADY BROKEN** (Pre-existing issues that did not worsen)
3. 🟢 **FIXED** (Baseline issues resolved by the change)

### 1.2 Core Value Proposition
- **Zero Cluster Footprint:** No CRDs, no cluster agents, no background daemons, no database. Only requires read-only `kubectl` access.
- **Pure Blame Attribution:** Unlike monitoring systems (Prometheus/Datadog) that report global metrics or point-in-time diff tools that dump raw YAML changes, `wasitme` specifically attributes health degradation to the deployment event.
- **Fast Feedback Loop:** Runs locally in seconds, works seamlessly in CI/CD pipelines with deterministic exit codes.

---

## 2. User Stories & Acceptance Criteria

### US-1: Post-Deploy Regression Check in Shared Staging
> **As an** application developer deploying a service to a noisy shared staging cluster,  
> **I want to** run `wasitme diff` against a baseline snapshot taken before my deploy,  
> **So that** I know immediately if the pod crashloop was caused by my new image or existed prior to my deployment.

#### Acceptance Criteria (US-1):
1. **Pre-deploy Snapshot:** Running `wasitme snapshot -n staging` completes in under 5 seconds and generates `.wasitme-snapshot.json` containing workloads, pods, warning events, and HTTP checks.
2. **Attribution Accuracy:** If a deployment `api-gateway` was in `CrashLoopBackOff` before the deployment and remains in `CrashLoopBackOff` with identical replica count and restart rate, it is classified under `ALREADY BROKEN`.
3. **Rollout Pod Replacement Edge Case:** Even though Kubernetes replaced all pod names (`api-gateway-748bf-abc` replaced by `api-gateway-893ca-xyz`), the crashloop is attributed to the owner workload (`Deployment/api-gateway`) and marked `ALREADY BROKEN`.
4. **Clean Exit Code:** If no regressions occurred, the command exits with code `0`.

---

### US-2: Automated CI/CD Deployment Gate
> **As a** DevOps / platform engineer running GitHub Actions deployment pipelines,  
> **I want to** execute `wasitme diff --fail-on regression --wait 30s` post-rollout,  
> **So that** the deployment pipeline automatically fails if my commit introduced a crashloop, image pull error, or latency degradation.

#### Acceptance Criteria (US-2):
1. **Regression Detection:** If a new `POD_IMAGE_PULL` or `POD_CRASHLOOP` appears after the baseline, or if restart counts surge by $\ge 3$, `wasitme` prints the regression in the `BROKE AFTER YOUR CHANGE` bucket.
2. **Deterministic Exit Codes:**
   - Exit code `0`: No regressions detected (pre-existing issues allowed).
   - Exit code `1`: At least one regression detected in `BROKE AFTER YOUR CHANGE`.
   - Exit code `2`: Environment or usage error (e.g. `kubectl` missing or unauthorized).
   - Exit code `3`: Malformed or incompatible snapshot file.
3. **Markdown Output:** Supports `--format md` to emit GitHub PR / job summary markdown without ANSI escape codes.
4. **Settlement Period:** Honors `--wait 30s` to allow pods to settle before capturing the post-deploy state.

---

### US-3: Zero-Setup Offline Trial
> **As a** platform engineer evaluating `wasitme` on a laptop with no active Kubernetes cluster or network connection,  
> **I want to** run `wasitme demo`,  
> **So that** I can experience the CLI's UX, diffing logic, and visual output within 10 seconds.

#### Acceptance Criteria (US-3):
1. **Completely Offline:** `wasitme demo` executes bundled sanitized scenario fixtures (`crashloop`, `clean`, `preexisting`) without spawning subprocesses or opening network sockets.
2. **Execution Time:** Demo finishes in under 2 seconds.
3. **Visual Clarity:** Renders colored terminal tables adhering to `docs/DESIGN.md`, showing the verdict and three buckets. Supports `NO_COLOR` and non-TTY environments.

---

## 3. Scope of v0.1.0

### 3.1 In Scope
- **Commands:** `snapshot`, `diff`, `demo`, `version`.
- **Resources Monitored:**
  - Pods: status, restart count spikes, waiting/terminated reasons.
  - Workloads: `Deployment`, `StatefulSet`, `DaemonSet` desired vs available replicas.
  - Nodes: readiness status and pressure flags (`MemoryPressure`, `DiskPressure`, `PIDPressure`).
  - Warning Events: warning-type events occurring strictly after baseline timestamp.
  - HTTP Probes: optional synthetic health check endpoints (5 samples, p50 latency, status codes).
- **Formats:** `terminal` (Rich), `md` (Markdown), `json` (Machine-readable).
- **Distribution:** PyPI package installable via `pipx install wasitme`.

### 3.2 Explicitly Out of Scope
- No in-product web server or dashboard UI.
- No direct AWS, GCP, or Azure API calls (strictly read-only `kubectl` subprocesses).
- No cluster mutation (`apply`, `delete`, `patch`, `create`).
- No reading Kubernetes `Secret` objects.
- No persistence beyond local snapshot JSON files.
- No telemetry, analytics, or remote tracking.
- No Windows support for v0.1.0 (Linux & macOS only).

---

## 4. Logo Requirements (Input to Alia Bhatt, Senior UI/UX Designer)
1. **Aspect Ratio:** Exact 1:1 square vector graphic (SVG).
2. **Text Constraint:** Must NOT contain any text, typography, or letterforms.
3. **Scalability:** Must be instantly recognizable and crisp down to 16x16 px (browser favicon, terminal tab) and up to 512x512 px (social preview).
4. **Theme Compatibility:** Dual theme support (readable on dark `#0d1117` and light `#ffffff` backgrounds).
5. **Metaphor:** Balance between checkpoint/snapshot diffing and attribution (e.g., split lens, balance scale, or binary delta attribution mark).
