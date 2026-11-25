# Observability provisioning inputs

These files define an initial Prometheus scrape and alert rules, two Grafana
dashboards, Fluent Bit collection, Elasticsearch index/retention templates,
and Kibana saved searches plus an incident dashboard with request, error, and
indexed-event trend charts. `make up` applies the assets as part of the
baseline; no dashboard, import, scrape, query, or alert behavior has been run
or verified.

Fluent Bit runs as a DaemonSet on the k3d nodes. It mounts each node's
`/var/log/containers` and `/var/log/pods` directories read-only to collect
synthetic lab container logs. These are paths inside the k3d node containers,
not host operating-system log directories. It also mounts
`/var/lib/fluent-bit` read/write for its tail offset database, so it can resume
after a pod restart. Its ClusterRole is limited to `get`, `list`, and `watch`
for namespaces, pods, and nodes; it has no Kubernetes write verbs. Review
these hostPath and RBAC permissions before adapting the collector beyond this
local lab.

The local Elasticsearch and Kibana services are unauthenticated and intended
only for this synthetic, single-user lab. Elasticsearch is cluster-internal;
Kibana access is via a loopback-bound port-forward. Do not expose either
service to an external network. Review this design before adapting it for any
shared or production use. Alert thresholds and retention are initial proposals,
not measurements.
