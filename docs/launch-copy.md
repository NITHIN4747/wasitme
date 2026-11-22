# Launch Copy & Community Announcements — wasitme

**Author:** Ronaldo (Product Engineer)  
**Approver:** Nithin K (Team Lead & Product Owner)  
**Status:** Frozen (Phase 0)  

---

## 1. Product Hunt Copy

### Tagline (< 60 chars)
> **Did your deploy break it, or was it already broken?**

### Description
**Problem:** You deploy a routine fix to a shared staging or production Kubernetes cluster, and alerts fire. You're blamed for breaking the service—only to spend an hour digging through logs to prove the crashloop was already happening before you even ran `kubectl apply`.

**Solution:** `wasitme` is an open-source Python CLI that takes a quick snapshot of your Kubernetes namespace (and HTTP endpoints) before your deploy, then diffs the live cluster state afterward. It groups everything into 3 unambiguous buckets:
- 🔴 **BROKE AFTER YOUR CHANGE** (New crashloops, restart spikes, or degraded endpoints)
- 🟡 **ALREADY BROKEN** (Pre-existing issues that did not worsen)
- 🟢 **FIXED** (Issues you resolved)

**Who it's for:** Platform engineers, SREs, and developers deploying to shared clusters who need instant blame attribution without installing cluster agents or opening heavy dashboards.

### First Comment (Maker Comment by Nithin K)
```text
Hey Product Hunt! 👋 I'm Nithin, maker of wasitme.

How many times have you deployed a change to a Kubernetes cluster, noticed a failing pod, and wondered: "Did I cause that, or was it already on fire?"

I built wasitme to solve that exact moment of post-deploy dread. 

Most diff tools compare raw YAML text or count resource dumps, which fail the moment Kubernetes replaces pod names during a rolling update. wasitme re-keys pod issues by workload ownership, accounts for restart spikes and replica availability, and runs without installing any agents or CRDs in your cluster.

It's completely free, MIT-licensed, and written in Python with zero heavy dependencies (just Typer and Rich). You can try it right now without even having a Kubernetes cluster running:

$ pipx install wasitme
$ wasitme demo --scenario crashloop

I'd love your feedback, feature ideas, and contributions!
```

---

## 2. Show HN Copy

### Title
> **Show HN: wasitme – Did your deploy break it, or was it already broken?**

### Body
```text
Hi HN,

Whenever you deploy to a shared or staging Kubernetes cluster, there is almost always background noise: a pre-existing crashlooping cron job, an evicted pod from yesterday, or a flaky third-party service.

When your deployment finishes and something is red, you're forced to do forensics: was this crashloop caused by my new container image, or was it already broken before I started?

I built wasitme (MIT licensed CLI) to answer this in 5 seconds.

How it works:
1. Before deploying: `wasitme snapshot -n my-app --url health=https://api.my-app.com/healthz`
   (Captures workload replica states, pod health, restart totals, new warning events, and synthetic HTTP latencies to .wasitme-snapshot.json)
2. Deploy your app: `kubectl apply -f ...`
3. After deploying: `wasitme diff --wait 15s --fail-on regression`

It categorizes all health anomalies into 3 buckets:
- BROKE AFTER YOUR CHANGE (regressions that fail CI with exit code 1)
- ALREADY BROKEN (pre-existing issues that did not worsen)
- FIXED (issues that your deploy resolved)

Key engineering details:
- Pod names change during rolling updates. wasitme resolves ownership hierarchies (Pod -> ReplicaSet -> Deployment) so pod rotation doesn't trick the diff engine.
- Purely client-side and deterministic: No cluster agents, no CRDs, read-only `kubectl get -o json` subprocesses.
- Exit code 0 on clean/pre-existing issues, exit code 1 on new regressions.

You can test the offline demo immediately:
$ pipx install wasitme
$ wasitme demo

Code & architecture: https://github.com/nithink/wasitme
Would love your thoughts, critique on edge-case diffing rules, and feedback!
```
