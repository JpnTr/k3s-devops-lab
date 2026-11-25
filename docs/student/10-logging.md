# 10 · Log collection stopped

**Estimated time:** 15 minutes (not trialed). **Prerequisite:** healthy baseline and Kibana access.

**Symptom:** a fresh API request appears in API stdout but not Elasticsearch.

1. **Hint 1 · Layer:** separate application logging from log ingestion.
2. **Hint 2 · Evidence:** search the API container output by request ID, then search Kibana for the same ID.
3. **Hint 3 · Focus:** inspect Fluent Bit DaemonSet pods and `k -n observability get configmap fluent-bit-config -o yaml`.

**Negative control:** API request returns 200 and Elasticsearch/Kibana remain reachable.

**Repair:** `k apply -k observability` restores the collector config, then `k -n observability rollout status ds/fluent-bit`. A new request ID must arrive in Elasticsearch without backfill. Run `make lab-verify LAB=10`, then reset.
