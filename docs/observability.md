# Observability specification

The current source includes the two Grafana dashboards, Prometheus scrape/rule
configuration, four Kibana saved searches, three Kibana Lens time-series
visualizations, and a dashboard containing the searches and charts. These
saved objects have not been imported or checked against a running stack.

## Prometheus and Grafana

Provision data source and stable dashboard IDs during up. Exclude probes and scrapes from user-request SLIs. Normalize route labels and keep request IDs out of metrics.

| Signal | Contract |
| --- | --- |
| Requests | orders_http_requests_total by method, normalized route, status and version. Rate over 1m. Divide 5xx rate by total rate with explicit no-traffic handling. |
| Latency | orders_http_request_duration_seconds histogram. Use histogram_quantile over matching bucket rates, retaining le and route. Show p50/p95/p99 by route. |
| Pool | orders_db_pool_in_use and orders_db_pool_capacity gauges, orders_db_pool_wait_seconds histogram, orders_db_pool_timeouts_total counter. |
| Cluster | Ready replicas versus desired, restarts, last termination reason, pod and container CPU/memory against requests or limits, node readiness and pending workloads. Document each source. |
| Collection | Show scrape health and distinguish missing samples from legitimate zero traffic. |

Ship API Overview and Kubernetes Health. Include namespace, route, pod and version filters where applicable. Start with 5xx over 5% and p95 over 500 ms as provisional alert thresholds. Calibrate with representative traffic, sustained windows and minimum request volume. Supply firing and recovery checks. Separate missing telemetry alerts from request error alerts. No external notification service is required.

## Elasticsearch and Kibana

Provision a versioned index template and data view for orders logs, then import stable saved objects with references checked. Use structured fields @timestamp (UTC date), service.name and service.version (keyword), log.level (keyword), http.response.status_code (integer), url.path (keyword for these synthetic routes), event.duration (long in nanoseconds), error.type (keyword), message, http.request.id (keyword), and the Kubernetes filter's `kubernetes.namespace_name` and `kubernetes.pod_name` fields (keywords). Set explicit retention and bounded storage. Verify the collector can parse CRI-wrapped JSON and enrich logs on every intended node.

| Saved view | Learner task |
| --- | --- |
| API Incident Overview | Inspect recent API requests in a saved-search table and compare them with the request-volume trend. |
| Failed Requests | Find request ID, status, duration, version, pod, and error type in the saved-search table; compare the 5xx trend. |
| Database Timeouts | Filter dependency errors and compare them with application logs. |
| Ingestion Health | Inspect latest events and compare with a fresh known request ID and indexed-event trend. |

The dashboard charts request volume, 5xx volume, and indexed log-event volume
over the selected time range. Grafana remains the source for latency and
Prometheus scrape-health analysis.

Example Discover filters to validate against the provisioned mappings:

```text
service.name: "orders-api" and http.response.status_code >= 500
service.name: "orders-api" and service.version: "v2"
http.request.id: "replace-with-probe-id"
```

After bootstrap, send a fresh request, look up its ID in Elasticsearch, validate dashboard references, and verify recent time series in Prometheus. Smoke test the UIs manually at release. Keep past logs visible after reset and document UTC time windows and the expected ingestion delay.
