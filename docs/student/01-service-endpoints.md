# 01 · Service has no endpoints

**Estimated time:** 10 minutes (not trialed). **Prerequisite:** healthy baseline and `k()` from the [workbook](README.md).

**Symptom:** ingress loses the API backend while API pods are Ready.

1. **Hint 1 · Layer:** check the Service-to-pod selection path.
2. **Hint 2 · Evidence:** compare the Service selector with pod labels and inspect ready EndpointSlice addresses.
3. **Hint 3 · Focus:** `k -n lab get svc orders-api -o yaml` and `k -n lab get endpointslice -l kubernetes.io/service-name=orders-api -o yaml`.

**Negative control:** inspect a pod's readiness and liveness; the process is healthy even though ingress has no endpoints.

**Repair:** `k apply -f deploy/api.yaml` restores the API Service selector and deployment. Verify ready endpoints and repeated Host-header ingress 200s with `make lab-verify LAB=01`; then `make lab-reset`.
