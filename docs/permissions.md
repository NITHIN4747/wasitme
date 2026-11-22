# Kubernetes Least-Privilege Permissions for wasitme

**Author:** Sunil Chhetri (Cloud Engineer — AWS / EKS)  
**Security Invariant:** Read-only access. Zero cluster mutations. Zero secrets access.  

---

## 1. Minimal ClusterRole

`wasitme` only requires `get` and `list` permissions on core workload and node resources. It explicitly **excludes** `secrets` and mutation verbs (`create`, `update`, `patch`, `delete`).

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: wasitme-readonly
rules:
  - apiGroups: [""]
    resources:
      - pods
      - pods/status
      - nodes
      - nodes/status
      - events
      - namespaces
    verbs: ["get", "list"]
  - apiGroups: ["apps"]
    resources:
      - deployments
      - statefulsets
      - daemonsets
      - replicasets
    verbs: ["get", "list"]
```

---

## 2. ClusterRoleBinding

Bind this role to your developer group, CI service account, or IAM user:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: wasitme-readonly-binding
subjects:
  - kind: Group
    name: "system:authenticated"  # Or specific ServiceAccount / User
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: wasitme-readonly
  apiGroup: rbac.authorization.k8s.io
```

---

## 3. AWS EKS Access Instructions

When connecting to AWS EKS:
1. Ensure your local AWS CLI is authenticated:
   ```bash
   aws sts get-caller-identity
   ```
2. Update your local kubeconfig:
   ```bash
   aws eks update-kubeconfig --region <REGION> --name <CLUSTER_NAME>
   ```
3. Test read-only connectivity:
   ```bash
   kubectl auth can-i get pods --all-namespaces
   # Expected output: yes
   kubectl auth can-i get secrets --all-namespaces
   # Expected output: no (proves least privilege)
   ```
