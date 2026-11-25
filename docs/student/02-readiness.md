# 02 · Readiness rollout

**Estimated time:** 10 minutes (not trialed). **Prerequisite:** healthy baseline and `k()` from the [workbook](README.md).

**Symptom:** new API pods run but do not become Ready; old replicas continue serving.

1. **Hint 1 · Layer:** inspect rollout health and distinguish readiness from liveness.
2. **Hint 2 · Evidence:** check probe failure events for the new ReplicaSet.
3. **Hint 3 · Focus:** compare `k -n lab get deploy orders-api -o yaml` with `k -n lab describe pods -l app.kubernetes.io/name=orders-api`.

**Negative control:** confirm old replicas keep serving ingress while the rollout stalls.

**Repair:** `k apply -f deploy/api.yaml` restores `/readyz`. Run `make lab-verify LAB=02` to check the rollout, ready endpoints, liveness, and database-backed Orders route, then `make lab-reset`.
