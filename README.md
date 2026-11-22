# wasitme

**Did your change break this, or was it already broken?**

`wasitme` is an open-source Python CLI that takes a pre-deploy snapshot of a Kubernetes namespace, diffs it against live state after deployment, and attributes health issues into three clear buckets:

```
Verdict: REGRESSION DETECTED (1 regression, 2 pre-existing, 1 fixed)

🔴 BROKE AFTER YOUR CHANGE
  • Pod/auth-service [CrashLoopBackOff] (owner: Deployment/auth-service)
    ExitCode: 137 | RestartDelta: +4

🟡 ALREADY BROKEN
  • Pod/payment-worker [CrashLoopBackOff] (owner: Deployment/payment-worker)
    Pre-existing crashloop unchanged since 2026-11-22T08:14:22Z
  • WarningEvent/billing-cron [FailedMount]
    MountVolume.SetUp failed for volume "data-vol"

🟢 FIXED
  • Workload/frontend [WorkloadUnavailable]
    Replicas available restored: 3/3 desired
```

No cluster agents. No CRDs. No dashboards. Just `kubectl` access and pure attribution.

---

## ⚡ 60-Second Quickstart

### 1. Installation
Install `wasitme` using `pipx` (recommended) or `pip`:

```bash
pipx install wasitme
```

### 2. Try the Offline Demo (No Cluster Needed)
```bash
wasitme demo --scenario crashloop
```

### 3. Real Deployment Flow

#### Step A: Snapshot Before Deploy
```bash
wasitme snapshot -n my-app --url health=https://api.example.com/healthz
# Saved baseline to .wasitme-snapshot.json
```

#### Step B: Perform Your Deploy
```bash
kubectl apply -f k8s/deployment.yaml
```

#### Step C: Run the Attribution Diff
```bash
wasitme diff --wait 15s --fail-on regression
```
Exit code `0` = Clean or pre-existing issues only.  
Exit code `1` = Regression introduced by your deploy.

---

## 🔍 How It Differs

| Feature | wasitme | kubectl-snapshot | Traditional APM / Prometheus |
|---|---|---|---|
| **Primary Goal** | **Deploy Blame Attribution** | Forensics state capture | Real-time time-series telemetry |
| **Attribution Buckets** | 🔴 Broken After<br>🟡 Already Broken<br>🟢 Fixed | None (single state dump or raw count diff) | None (alerts on raw thresholds) |
| **Rollout Pod Re-keying** | Handles pod replacements via workload ownership | Raw pod name matching (trips on replica rotation) | Metric-level aggregations |
| **Cluster Footprint** | Zero (Client-side CLI) | Zero (Client-side CLI) | Heavy (agents, daemonsets, storage) |
| **Synthetic HTTP Checks** | Built-in stdlib prober | None | Separate probe system required |
| **Status** | Active, MIT | Dormant (~6 months) | Active |

### Why not `kubectl-snapshot`?
`kubectl-snapshot` (written in Go) is a forensics tool that captures a comprehensive point-in-time snapshot of resources and outputs count deltas. However, when pods are rotated during a standard deployment rollout, raw pod names change, making simple name matching misleading. `wasitme` solves this by keying issues on **workload owners**, tracking metric worsening (restart deltas, replica availability), and integrating synthetic HTTP checks directly into the diff.

---

## ⚠️ Limitations

- **Read-Only Inspection:** `wasitme` only queries Kubernetes state via `kubectl get -o json`. It does not parse application logs, eBPF network flows, or kernel metrics.
- **Single Namespace Focus (Default):** While `-A` (all namespaces) is supported, `wasitme` v0.1.0 is optimized for targeted namespace rollouts.
- **Short-Lived Rollout Settling:** Transitory container initialization or pod scheduling delays during an active rollout are mitigated by `--wait` and `--rollout`, but extremely long initialization hooks should be accounted for using appropriate `--wait` durations.
- **Platform Support:** Linux and macOS (Python 3.11+). Windows is unsupported in v0.1.0.

---

## 📄 License
MIT © Nithin K
