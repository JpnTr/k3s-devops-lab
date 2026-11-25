# 11 · Metrics scrape failure

**Estimated time:** 15 minutes (not trialed). **Prerequisite:** healthy baseline and Prometheus access.

**Symptom:** API requests and logs work, but fresh application metric samples disappear.

1. **Hint 1 · Layer:** inspect the Prometheus target state.
2. **Hint 2 · Evidence:** compare the target scrape path with the API `/metrics` route.
3. **Hint 3 · Focus:** Prometheus Status → Targets, then `k -n lab get svc orders-api -o yaml`.

**Negative control:** application traffic and logs stay healthy during the scrape fault.

**Repair:** `k apply -f deploy/api.yaml` restores the scrape annotation. Verify the target is up and a fresh sample exists, run `make lab-verify LAB=11`, then reset.
