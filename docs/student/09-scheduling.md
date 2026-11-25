# 09 · Unschedulable rollout

**Estimated time:** 10 minutes (not trialed). **Prerequisite:** healthy baseline and `k()` from the [workbook](README.md).

**Symptom:** new API pods remain Pending while existing replicas serve requests.

1. **Hint 1 · Layer:** inspect the scheduler and pod placement constraints.
2. **Hint 2 · Evidence:** read Pending pod events and compare selectors with node labels.
3. **Hint 3 · Focus:** `k -n lab get pods -o wide` and `k -n lab describe pod <pending-pod>`.

**Repair:** `k apply -f deploy/api.yaml` restores the worker selector. Run `make lab-verify LAB=09` to check rollout completion, ready endpoints, liveness, and a database-backed Orders request, then reset.
