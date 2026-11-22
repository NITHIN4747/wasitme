# DECISION-001 — Pod and Workload Issue Keying

**Date:** 2026-11-22  
**Decided by:** Nithin K (Team Lead & Product Owner)  
**Status:** ACCEPTED | **Reversible:** NO  

## Decision
Issue keys for pod-level and workload-level issues must key on `f"{kind}:{namespace}:{owner_kind}:{owner_name}"`, never on the pod name itself.

## Reason
During a standard Kubernetes rolling update, every pod is replaced with new pods having randomized hashes (e.g. `api-worker-6789f-ab12`). Keying by pod name causes all old issues to register as "FIXED" and all new issues to register as "BROKE AFTER", totally corrupting the attribution engine.

## Alternatives Rejected
1. **Raw pod name as key:** Rejected because pod rotation causes 100% false positives/negatives.
2. **Container image digest as key:** Rejected because deployment updates the image digest, breaking correlation across the deployment boundary.

## Impact
- `collectors/k8s.py`: Must resolve ReplicaSet owners to parent Deployments.
- `differ.py`: Indexes baseline and current issues using this composite key.
