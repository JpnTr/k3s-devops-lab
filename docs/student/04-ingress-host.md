# 04 · Ingress host mismatch

**Estimated time:** 10 minutes (not trialed). **Prerequisite:** healthy baseline and `k()` from the [workbook](README.md).

**Symptom:** the original host returns a Traefik 404 while `/livez` through a direct Service port-forward returns 200.

1. **Hint 1 · Layer:** inspect host-based ingress routing.
2. **Hint 2 · Evidence:** compare the request Host header with the Ingress rule.
3. **Hint 3 · Focus:** `k -n lab get ingress orders-api -o yaml`; make a temporary direct Service port-forward as a negative control.

**Repair:** `k apply -f deploy/ingress.yaml` restores `orders.lab.test`. Repeatedly probe `/livez` through the original Host header, run `make lab-verify LAB=04`, then reset.
