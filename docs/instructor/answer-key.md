# Instructor answer key · SPOILERS

These are expected diagnoses, not evidence that the implementation has passed the scenario acceptance criteria. Use a short UTC dashboard window and retain the fault interval. Require students to gather two evidence sources, state impact, make a scoped repair, and demonstrate sustained recovery.

| Lab | Root cause | Expected evidence | Repair | Negative control / recovery |
|---|---|---|---|---|
| 01 | Service selector matches no pod | Ready pods, empty EndpointSlices, ingress failure | Restore selector | Direct pod responds; ingress returns repeatedly |
| 02 | Invalid readiness path blocks new replicas | Probe events and stalled rollout | Restore `/readyz` | Old replicas serve throughout; new replicas become ready |
| 03 | API database hostname is nonexistent | API DNS error; PostgreSQL service name resolves | Restore service DNS name | Liveness remains healthy; DB-backed GET succeeds |
| 04 | Ingress host rule differs from Host header | Host 404 with direct Service success | Restore `orders.lab.test` | Direct Service stays healthy |
| 05 | v2 deterministically returns a subset of 503s | Failures grouped by version; rollout history | Roll back to v1 | Keep old logs searchable; new requests succeed |
| 06 | GET delay increases route latency | p95 spike and slow request IDs | Remove delay | Successful status remains; p95 returns after window clears |
| 07 | Low pool capacity and connection hold create waits | Pool wait/timeouts track errors | Restore pool/burst values | Normal requests and recovery burst have no timeouts |
| 08 | Startup allocation exceeds API memory limit | OOMKilled and restart count growth | Restore memory and remove allocation | No new restarts during observation |
| 09 | Node selector matches no workers | Pending pods and scheduling events | Restore placement policy | Old replicas remain; rollout completes |
| 10 | Collector no longer forwards logs | ID in stdout, absent in Elasticsearch | Restore collection | A new ID arrives; do not require backfill |
| 11 | Prometheus scrape endpoint is wrong | Target down and missing fresh app samples | Restore `/metrics` | API traffic/logging stay healthy |
| 12 | Verified worker is drained, leaving one API replica and a Pending replacement | Eviction/scheduler events, one ready replica, and Orders still responding | Uncordon exact recorded node and restore both replicas | Node schedulable; two Ready replicas spread across workers; requests succeed |

## Instructor runbook and evidence queries

Define this helper in a student terminal before using kubectl:

```sh
k() { kubectl --kubeconfig .lab/kubeconfig --context k3d-k3s-devops-lab "$@"; }
```

Use a UTC time range covering start and recovery. Each scenario page links these diagnosis and repair steps. The thresholds below are provisional until a classroom runtime trial measures them.

### 01 Service endpoints

Expected observations: the Service selector is `app.kubernetes.io/name=deliberately-absent`, API pods remain Ready, and no EndpointSlice address is ready. Check the [Grafana API Overview](../../observability/orders-overview.json) and API liveness. Negative control: `k -n lab get pods -l app.kubernetes.io/name=orders-api` still shows Ready replicas. Repair with `k apply -f deploy/api.yaml`. The verifier requires ready endpoints, five successful `/livez` responses, and three successful database-backed `/orders` responses through the original ingress host.

### 02 Readiness rollout

Expected observations: `k -n lab rollout status deploy/orders-api --timeout=5s` times out, and `k -n lab describe pod <new-pod>` shows readiness probe 404 events for the configured `/wrong-ready-path`. Two old replicas and their Service endpoints remain Ready and serve Orders. Repair with `k apply -f deploy/api.yaml`; the verifier checks the restored `/readyz` probe, completed rollout, ready endpoints, ingress liveness, and a successful database-backed `/orders` response.

### 03 Database DNS

Expected observations: `DB_HOST` is `postgres-missing.lab.svc.cluster.local`, API `/livez` stays 200, `/orders` returns 503 with an indexed `db_dns_error` for that exact request ID, and PostgreSQL is Ready. From an API pod, compare `socket.getaddrinfo` for the configured hostname and `postgres.lab.svc.cluster.local`. Repair with `k apply -f deploy/api.yaml`; wait for the API rollout and two ready baseline replicas, then require DB-backed GET success and no new `db_dns_error` request logs.

### 04 Ingress host

Expected observations: the Ingress rule is set to `wrong.lab.test`; the original Host header receives Traefik 404, while API and direct Service remain healthy. Repair with `k apply -f deploy/ingress.yaml`. Verify the original host/path returns 200. Direct Service is the negative control.

### 05 Faulty version

Kibana KQL: `service.name: orders-api and http.response.status_code >= 500`; group by `service.version`. The injected v2 setting is `FAULT_FAIL_PERCENT=35`; the detector requires indexed `synthetic_failure`/503 evidence for the exact failed request ID. Compare `k -n lab rollout history deploy/orders-api`. Faults are deterministic by request ID, so use generated and host traffic. Repair with `k apply -f deploy/api.yaml`, verify the pod template is v1, the failure setting is removed, and fresh requests succeed. Preserve the v2 interval in Elasticsearch after rollback.

### 06 Latency

The injected `FAULT_DELAY_GET=0.8` makes successful Orders requests exceed 700 ms. Grafana p95 query: `histogram_quantile(0.95, sum by (le,route) (rate(orders_http_request_duration_seconds_bucket[5m])))`. Kibana KQL: `service.name: orders-api and url.path: "/orders"`; sort by `event.duration`. Repair with `k apply -f deploy/api.yaml`. The verifier waits for the API rollout and two ready baseline replicas, checks three successful fast `/orders` responses, and then waits for the p95 series to recover; both the 700 ms direct-response bound and histogram threshold need calibration before release.

### 07 Pool saturation

Compare `orders_db_pool_in_use`, `orders_db_pool_capacity`, `rate(orders_db_pool_timeouts_total[1m])`, and API `error.type: db_pool_timeout`. PostgreSQL Ready is a negative control. Repair with `k apply -f deploy/api.yaml`; wait for the API rollout and two ready baseline replicas, then verify a normal request burst and no fresh timeout errors.

### 08 Memory pressure

The fault sets the API limit to 128 MiB and startup allocation to 512 MiB. Check `k -n lab get pods -l app.kubernetes.io/name=orders-api -o json` for `lastState.terminated.reason: OOMKilled`, restart deltas, and Grafana Kubernetes Health. Other services should remain healthy. Repair with `k apply -f deploy/api.yaml`; the verifier requires a completed rollout, no current API OOM termination, stable restart counts over a 15-second observation window, liveness, and a successful database-backed `/orders` response.

### 09 Scheduling

Inspect Pending pods, `k -n lab describe pod <pending-pod>`, and scheduler events for the `lab.k3s-devops.invalid/worker=nowhere` selector. Two old replicas and their Service endpoints should keep serving due to `maxUnavailable: 0`. Repair with `k apply -f deploy/api.yaml`; verify rollout and ready endpoints.

### 10 Log collection

Generate a fresh request ID. Confirm it appears in API container stdout and not in Kibana. The faulted ConfigMap sends Fluent Bit output to stdout; the controller confirms Elasticsearch cluster health before comparing the request, so an Elasticsearch outage cannot activate this scenario. Fluent Bit pods and Elasticsearch remain up. Repair with `k apply -k observability`; the verifier waits for the DaemonSet rollout before issuing a fresh request ID and checking its arrival. Do not rely on backfill.

### 11 Metrics scrape

Prometheus Status → Targets should show the `lab/orders-api` target down on `/missing-metrics`, the Service's configured scrape path. The detector also requires successful API traffic and an indexed request log while the target is down. Repair with `k apply -f deploy/api.yaml`; wait for discovery refresh, issue a successful `/orders` request, then require the target up and an `orders_http_requests_total{route="/orders"}` sample.

### 12 Worker capstone (SPOILER)

The instructor starts the worker operation and gives only a symptom plus UTC window. Before draining, the runner requires a healthy API/endpoints baseline, successful `/livez` and database-backed `/orders` requests, exactly two Ready and schedulable labeled agents, a two-replica worker-selected Deployment, and exactly one Ready API replica on each agent. It records the selected agent in `.lab/state.json`, then cordons and drains it. Activation waits until one API replica is Ready, the replacement is Pending, and Orders still responds. Require impact, at least two evidence sources, root cause, scoped repair, and sustained recovery. Repair with `k uncordon <recorded-worker>`; verification waits for two Ready replicas spread across both schedulable workers plus successful requests. Reset also uncordons the exact recorded worker, rolls the API, and confirms the same placement baseline.

Common wrong hypotheses to test: database outage vs DNS/pool layer (PostgreSQL Ready); API crash vs readiness stall (process running); ingress vs Service (direct Service works); logging vs scraping (stdout/API remain healthy); and a failed rollout vs a scheduling constraint (Pending events identify the scheduler). Provide the next hint only after the learner names the evidence they need.

The runner automates scenario-specific controls: a Ready PostgreSQL pod and API liveness during database DNS failure, direct Service health during ingress failure, API stdout plus healthy Elasticsearch during collection failure, and successful API traffic plus indexed logs during scrape failure. It also requires healthy old replicas during readiness/scheduling rollouts. Instructors can independently compare DNS resolution from the API pod and discuss alternatives that the runner does not explicitly probe.
