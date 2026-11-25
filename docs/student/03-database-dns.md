# 03 · Database DNS failure

**Estimated time:** 10 minutes (not trialed). **Prerequisite:** healthy baseline and `k()` from the [workbook](README.md).

**Symptom:** database-backed Orders requests return a stable dependency error.

1. **Hint 1 · Layer:** follow the API-to-PostgreSQL name-resolution path.
2. **Hint 2 · Evidence:** compare the configured database hostname with the Service and CoreDNS results.
3. **Hint 3 · Focus:** `k -n lab get deploy orders-api -o yaml`; resolve the configured hostname and `postgres.lab.svc.cluster.local` from an API pod.

**Negative control:** `/livez` remains 200 and PostgreSQL stays Ready. Compare resolution of the faulty hostname with the PostgreSQL Service name from an API pod.

**Repair:** `k apply -f deploy/api.yaml` restores `DB_HOST`. Verify GET `/orders` returns 200 and no fresh DNS error remains, then `make lab-verify LAB=03` and `make lab-reset`.
