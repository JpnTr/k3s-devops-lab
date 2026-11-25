# Student workbook

## Start from a healthy system

Run `make preflight`, `make up`, `make doctor`, and `make urls`. Confirm `doctor` passes before beginning. The lab controller uses its own ignored `.lab/kubeconfig`; use this shell helper for your inspection commands so your normal Kubernetes context is untouched:

```sh
k() { kubectl --kubeconfig .lab/kubeconfig --context k3d-k3s-devops-lab "$@"; }
```

The Orders API is at `http://127.0.0.1:8080` with Host header `orders.lab.test`. Send a healthy request and save the `X-Request-ID`:

```sh
curl -i -H 'Host: orders.lab.test' http://127.0.0.1:8080/orders
```

Open Grafana and Kibana using the loopback port-forward commands from `make urls`. Set a short recent UTC range. Find the request ID in Kibana and relate the `/orders` metric series in Grafana. The local Grafana password is in `.lab/credentials.json`.

## Work an incident

Start a listed incident with `make lab-start LAB=NN`. Capture its UTC window and the visible symptom. The instructor starts the blind capstone and reveals its ID only at verification time. Use the three hints in order: affected layer, evidence source, then a focused inspection. Compare healthy negative controls such as direct Service access during an ingress fault, API liveness during database trouble, stdout during a collector fault, or application traffic during a scrape fault.

Repair the smallest responsible object using the incident page, then run `make lab-verify LAB=NN`. Verification observes recovery and does not repair anything. Finish with `make lab-reset`; it checks recovery, keeps the practice orders and telemetry history, and clears the active incident only after those checks pass.

Write a short incident report with UTC impact window, affected users/requests, two evidence sources, root cause, scoped repair, sustained recovery evidence, and reset result. Sample logs and traffic are synthetic. All times in output are UTC.

## Incident pages

- [01 Service endpoints](01-service-endpoints.md)
- [02 Readiness rollout](02-readiness.md)
- [03 Database DNS](03-database-dns.md)
- [04 Ingress host](04-ingress-host.md)
- [05 Faulty version](05-faulty-version.md)
- [06 Latency](06-latency.md)
- [07 Pool saturation](07-pool.md)
- [08 Memory pressure](08-memory.md)
- [09 Scheduling](09-scheduling.md)
- [10 Log collection](10-logging.md)
- [11 Metrics scrape](11-metrics.md)
- [Blind worker capstone](blind-worker-capstone.md)

The walkthrough and estimated exercise durations have not yet been trialed with learners.
