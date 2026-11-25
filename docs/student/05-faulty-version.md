# 05 · Faulty API version

**Estimated time:** 15 minutes (not trialed). **Prerequisite:** healthy baseline, Grafana/Kibana access, and `k()` from the [workbook](README.md).

**Symptom:** a subset of Orders requests fails while process probes and rollout remain healthy.

1. **Hint 1 · Layer:** compare request outcomes by application version.
2. **Hint 2 · Evidence:** inspect structured logs, metrics, and rollout history.
3. **Hint 3 · Focus:** filter Kibana for `service.name: orders-api and http.response.status_code >= 500`, then compare `service.version` and `k -n lab rollout history deploy/orders-api`.

**Negative control:** v1 and liveness remain healthy; the failures are deterministic per request ID and correlated with v2.

**Repair:** `k apply -f deploy/api.yaml` restores the baseline v1 pod template. Confirm fresh requests succeed and the v2 evidence remains searchable. Run `make lab-verify LAB=05`, then reset.
