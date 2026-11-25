# 08 · API memory pressure

**Estimated time:** 15 minutes (not trialed). **Prerequisite:** healthy baseline and `k()` from the [workbook](README.md).

**Symptom:** API restart counts rise while PostgreSQL and other services remain available.

1. **Hint 1 · Layer:** inspect container termination and restart history.
2. **Hint 2 · Evidence:** compare `lastState.terminated.reason` and restart deltas.
3. **Hint 3 · Focus:** `k -n lab get pods -l app.kubernetes.io/name=orders-api -o json` and Grafana Kubernetes Health.

**Repair:** `k apply -f deploy/api.yaml` restores baseline memory limits and removes startup allocation. Run `make lab-verify LAB=08` to check a healthy rollout, no current OOM-killed API containers, stable restart counts during a short observation window, and a successful database-backed Orders request; then reset.
