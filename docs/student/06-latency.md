# 06 · Slow GET requests

**Estimated time:** 15 minutes (not trialed). **Prerequisite:** healthy baseline, sustained traffic, Grafana/Kibana access, and `k()` from the [workbook](README.md).

**Symptom:** GET `/orders` succeeds but p95 latency rises.

1. **Hint 1 · Layer:** inspect route latency, not only status codes.
2. **Hint 2 · Evidence:** compare the incident window with the recent baseline and examine slow request IDs.
3. **Hint 3 · Focus:** Grafana p95 by route; Kibana `service.name: orders-api and url.path: "/orders"` sorted by `event.duration`.

**Repair:** `k apply -f deploy/api.yaml` removes the injected delay. Allow the dashboard query window to recover; verify repeated fast responses with `make lab-verify LAB=06`, then reset. The 500 ms alert value is provisional and not calibrated.
