# Terminal UX & Visual Design Specification — wasitme

**Document ID:** DESIGN-001  
**Author:** Alia Bhatt (Senior UI/UX Designer)  
**Approver:** Nithin K (Team Lead & Product Owner)  
**Status:** Frozen (Phase 0)  

---

## 1. Information Hierarchy of Diff Output

The user must understand their deployment's health in **under 3 seconds**.

```
[1. Prominent Verdict Banner] -> One unambiguous status line with counts
[2. 🔴 BROKE AFTER YOUR CHANGE] -> Highlighted first (Errors above Warnings)
[3. 🟡 ALREADY BROKEN]          -> Pre-existing background noise (collapsed in concise mode)
[4. 🟢 FIXED]                   -> Resolved baseline issues
[5. Summary & Context Footer]   -> Baseline timestamp vs Current timestamp, duration
```

### Hierarchy Rules:
1. **Verdict Always First:** The top line states the outcome and bucket tallies. If a regression exists, this line demands immediate attention.
2. **Order of Buckets:**
   - `BROKE AFTER YOUR CHANGE` is always printed first.
   - `ALREADY BROKEN` is printed second.
   - `FIXED` is printed third.
3. **Internal Severity Sorting:** Inside each bucket, `severity == "error"` is sorted above `severity == "warning"`.
4. **Default vs Verbose Mode:**
   - **Default:** Shows all items in `BROKE AFTER` and `FIXED`. Summarizes `ALREADY BROKEN` with a count and top 3 items if $> 5$ items exist.
   - **Verbose (`--verbose` / `-v`):** Unpacks every single item in all buckets, including full container restart counts, last seen event timestamps, and HTTP response latencies.

---

## 2. Color & Symbol Matrix (Accessibility & Terminal Modes)

Meaning is **never** conveyed through color alone. Every state has an explicit icon, a text label, and an accessible fallback for 16-color, light backgrounds, `NO_COLOR`, and ASCII-only terminals.

| Bucket / State | Modern 256/TrueColor (Dark) | 16-Color Terminal | Light Terminal Background | NO_COLOR / Plain ASCII |
|---|---|---|---|---|
| **BROKE AFTER** | `[bold red] [!] BROKE` | `red [!] BROKE` | `[bold #b30000] [!] BROKE` | `[!] BROKE AFTER` |
| **ALREADY BROKEN** | `[yellow] [~] PRE-EXISTING` | `yellow [~] PRE-EXISTING` | `[#8a6d00] [~] PRE-EXISTING` | `[~] ALREADY BROKEN` |
| **FIXED** | `[bold green] [+] FIXED` | `green [+] FIXED` | `[bold #137333] [+] FIXED` | `[+] FIXED` |
| **UNSETTLED** | `[bold magenta] [?] UNSETTLED` | `magenta [?] UNSETTLED` | `[#6200ea] [?] UNSETTLED` | `[?] UNSETTLED` |
| **CLEAN VERDICT**| `[bold green] [OK] NO REGRESSIONS` | `green [OK] NO REGRESSIONS` | `[bold #137333] [OK] NO REGRESSIONS` | `[OK] NO REGRESSIONS` |
| **REGRESSION** | `[bold white on red] [FAIL] REGRESSION DETECTED` | `red [FAIL] REGRESSION DETECTED` | `white on #b30000 [FAIL] REGRESSION` | `[FAIL] REGRESSION DETECTED` |

### Environmental Fallbacks:
- If `os.environ.get("NO_COLOR")` is set or stdout is not a TTY:
  - All ANSI color codes are stripped.
  - Bracket symbols (`[!]`, `[~]`, `[+]`, `[OK]`, `[FAIL]`) guarantee accessibility.

---

## 3. Copy & Error Message Guidelines

Every error message emitted by `wasitme` must answer three questions:
1. **What happened?** (Plain English description of the failure)
2. **Why did it happen?** (Root cause: network, auth, bad syntax, cluster status)
3. **What to do next?** (Exact shell command or remediating step)

### Standard Template:
```text
Error: <WHAT HAPPENED>
Reason: <WHY IT HAPPENED>
Next Step: <EXACT ACTION TO RESOLVE>
```

---

## 4. Text Mockups of 6 Key Screens

### Screen 1: Clean Deployment Run (Exit Code 0)
```text
wasitme diff --wait 10s

[OK] VERDICT: CLEAN (0 regressions, 0 pre-existing, 1 fixed)
Baseline: 2026-11-22T08:00:00Z (prod) | Current: 2026-11-22T08:05:00Z (prod)

🟢 FIXED (1)
  • Workload/frontend-web [Deployment]
    Available replicas restored: 3/3 desired

Deploy verification successful. No regressions detected.
```

---

### Screen 2: Regression Detected (Exit Code 1)
```text
wasitme diff --wait 15s

[FAIL] VERDICT: REGRESSION DETECTED (2 regressions, 1 pre-existing, 0 fixed)
Baseline: 2026-11-22T08:00:00Z (prod) | Current: 2026-11-22T08:05:00Z (prod)

🔴 BROKE AFTER YOUR CHANGE (2)
  • Pod/auth-service [CrashLoopBackOff]
    Owner: Deployment/auth-service | ExitCode: 137 (OOMKilled)
    Restarts: 4 (surged +4 since baseline)
  • HttpCheck/api-health [HTTP_DEGRADED]
    Endpoint: https://api.example.com/healthz
    Status moved from 200 OK -> 503 Service Unavailable | Latency: 1240ms (was 120ms)

🟡 ALREADY BROKEN (1)
  • WarningEvent/payment-gateway [FailedMount]
    Owner: Deployment/payment-gateway | Count: 14 (pre-existing since baseline)

Action: Review the 2 regressions above. Your deployment introduced new failures.
```

---

### Screen 3: Pre-Existing Issues Only (Exit Code 0)
```text
wasitme diff --wait 10s

[OK] VERDICT: CLEAN (0 regressions, 2 pre-existing, 0 fixed)
Baseline: 2026-11-22T08:00:00Z (staging) | Current: 2026-11-22T08:05:00Z (staging)

🟡 ALREADY BROKEN (2)
  • Pod/legacy-worker [CrashLoopBackOff]
    Owner: Deployment/legacy-worker | Restarts: 112 (unchanged rate)
  • Node/ip-10-0-1-42.ec2.internal [DiskPressure]
    Kubelet has DiskPressure condition active

Note: 2 issues were detected, but all were already present in baseline. No new regressions.
```

---

### Screen 4: Unsettled Rollout Warning
```text
wasitme diff

[?] VERDICT: UNSETTLED ROLLOUT DETECTED (1 workload mid-rollout)

⚠️  UNSETTLED WORKLOADS:
  • Deployment/checkout-api
    Desired: 5 | Updated: 2 | Available: 3
    Status: Rollout still in progress (pods in ContainerCreating / Pending)

Warning: Rollout is actively settling. Diff results may contain transitory state.
Next Step: Run 'wasitme diff --rollout deployment/checkout-api' or use '--wait 30s'.
```

---

### Screen 5: Environment Error — `kubectl` Missing (Exit Code 2)
```text
wasitme snapshot -n my-app

Error: Unable to locate 'kubectl' binary on PATH.
Reason: wasitme requires kubectl to query the cluster state.
Next Step: Install kubectl (https://kubernetes.io/docs/tasks/tools/) or ensure it is added to your shell PATH environment variable.
```

---

### Screen 6: Offline Demo Execution
```text
wasitme demo --scenario crashloop

Running offline demo scenario: 'crashloop'...
Loaded bundled fixtures: [baseline: fixtures/clean.json, current: fixtures/crashloop.json]

[FAIL] VERDICT: REGRESSION DETECTED (1 regression, 0 pre-existing, 0 fixed)

🔴 BROKE AFTER YOUR CHANGE (1)
  • Pod/order-processor [CrashLoopBackOff]
    Owner: Deployment/order-processor | ExitCode: 1
    Reason: BackOff (Container failed: 'database connection refused')

Demo completed in 0.08s (purely offline).
Run 'wasitme --help' to see all commands.
```

---

## 5. Viewport Adaptation (80 vs 120 Columns)

### 80-Column Layout (Default):
- Single-column card style with indented details.
- Long URLs or error strings truncate with an ellipsis `...`.
- Tables wrap details beneath titles.

### 120-Column Layout (Expanded / CI):
- Multi-column table layout with dedicated columns: `RESOURCE`, `KIND`, `OWNER`, `SEVERITY`, `METRICS DELTA`, `DETAILS`.
- Full URL paths and event reasons displayed without truncation.

---

## 6. Logo Design Brief (1:1 SVG Specification)
- **Symbolism:** Two interlocking geometric brackets forming a clean delta checkpoint $(\Delta)$. The left side is solid (representing the immutable baseline), the right side dynamically resolves into a balanced status ring.
- **Palette:** Minimal monochrome with dual high-contrast fills: `#FFFFFF` (dark mode) / `#090A0F` (light mode) with an accent `#2563EB` (Cobalt Blue).
- **Format:** Pure SVG (`<svg viewBox="0 0 128 128">`), zero embedded raster images, zero typography/letters.
