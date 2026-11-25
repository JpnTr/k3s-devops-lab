# 07 · Database pool saturation

**Estimated time:** 15 minutes (not trialed). **Prerequisite:** healthy baseline and Grafana access.

**Symptom:** a bounded burst produces slow or failed database-backed requests.

1. **Hint 1 · Layer:** inspect the application database pool.
2. **Hint 2 · Evidence:** correlate pool capacity, wait duration, timeout count, and HTTP failures.
3. **Hint 3 · Focus:** Grafana pool panels and API logs with `error.type: db_pool_timeout`.

**Negative control:** PostgreSQL remains Ready; the fault is pool pressure, not a database process outage.

**Repair:** `k apply -f deploy/api.yaml` restores pool capacity and removes the hold. Run a normal request burst, `make lab-verify LAB=07`, then reset.
