# Technology and compatibility

| Layer | Initial choice |
| --- | --- |
| Host | Docker, k3d, kubectl, Make and Python 3 standard library for orchestration |
| Runtime | K3s with its bundled Traefik and CoreDNS |
| App | Python, FastAPI, Uvicorn, psycopg pool and Prometheus client |
| Data | PostgreSQL, single instance with local persistence |
| Metrics | Prometheus, kube-state-metrics and Grafana; source resource usage from kubelet/cAdvisor where verified |
| Logs | Fluent Bit as a node collector, single-node Elasticsearch and matching Kibana |
| Delivery | Pin images and language dependencies. Keep a single version manifest and platform test record; run public checks manually. |

The initial versions are pinned in `versions.yaml` and Python requirements. The
compatibility references below informed selection. Runtime integration,
registry manifests, image architectures, saved object import, and required
kernel settings remain unverified. Document exactly what learners must install
and how to check Docker VM settings without changing the host automatically.

## Authoritative compatibility references

Use upstream documentation as the source of truth and record the exact page/version checked when pins change:

- [k3d v5.9.0 release](https://github.com/k3d-io/k3d/releases/tag/v5.9.0), [v5.9.0 config reference](https://k3d.io/v5.9.0/usage/configfile/), and [v5.9.0 cluster-create flags](https://k3d.io/v5.9.0/usage/commands/k3d_cluster_create/): the config reference documents K3s node labels and separate kubeconfig update/switch settings; the command reference documents node-label filters and the kubeconfig-switch/update flags used by the controller. The upstream releases page currently identifies v5.9.0 as latest.
- [k3d v5.9.0 requirements](https://k3d.io/v5.9.0/) and [v5.9.0 version command](https://k3d.io/v5.9.0/usage/commands/k3d_version/), plus the [kubectl version command](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_version/): the pinned k3d docs state the Docker Engine 20.10.5 minimum and document version output; the controller compares k3d and kubectl client versions with repository pins. The Docker threshold is a compatibility floor, not a host support result.
- [k3d issue #1731](https://github.com/k3d-io/k3d/issues/1731): the open community Trivy report filed 2026-10-21 alleges 25 high-severity findings in the v5.9.0 Linux amd64 release binary and adds two findings in a 2026-10-26 update. The report lists fixed versions for the affected dependencies, but neither the findings nor fixes have been independently reproduced here. The repository owner must review the affected artifact and disposition before publication. Pin compatibility does not imply a security approval.
- [K3s releases](https://github.com/k3s-io/k3s/releases) and [Kubernetes version skew](https://kubernetes.io/releases/version-skew-policy/): the chosen Kubernetes/kubectl minor is 1.36.
- [K3s v1.36 release notes](https://docs.k3s.io/release-notes/v1.36.X) and [Kubernetes Node status](https://kubernetes.io/docs/reference/node/node-status/): K3s reports release versions with `+k3sN`; Kubernetes publishes the kubelet version in node status, which the controller compares with the pinned K3s image version when establishing cluster identity.
- [K3s server roles](https://docs.k3s.io/installation/server-roles): server nodes are schedulable by default; this lab pins its stateful local-PVC workloads there to keep worker-drain exercises from evicting them.
- [kube-state-metrics compatibility matrix](https://github.com/kubernetes/kube-state-metrics#versioning): v2.20.0 uses client-go 1.36, matching the selected cluster minor.
- [Elastic support matrix](https://www.elastic.co/support/matrix) and [Kibana version guidance](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-kibana): Elasticsearch and Kibana use the same exact 9.4.10 version.
- [Kibana Lens saved-object model](https://www.elastic.co/docs/extend/kibana/key-concepts/ui/lens) and [saved-object import/export](https://www.elastic.co/docs/extend/kibana/key-concepts/saved-objects/export): Lens charts are imported with the index-pattern references needed by their dashboard panels; Kibana migrations remain responsible for compatibility with the selected release.
- [Kibana get-saved-object API](https://www.elastic.co/docs/api/kibana/operation/operation-get-saved-objects-type-id): `make doctor` checks the imported dashboard and four saved searches through this endpoint. Elastic marks the legacy endpoint deprecated; confirm its supported replacement for a future Kibana pin before upgrading.
- [Prometheus releases](https://github.com/prometheus/prometheus/releases) and [configuration reference](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).
- [Prometheus HTTP API rules endpoint](https://prometheus.io/docs/prometheus/latest/querying/api/#rules): `make doctor` checks the four named alert rules are loaded via `/api/v1/rules`; this does not verify that their thresholds fire correctly, and the API page notes that this endpoint has weaker stability guarantees than the core API.
- [Grafana releases](https://github.com/grafana/grafana/releases) and [provisioning documentation](https://grafana.com/docs/grafana/latest/administration/provisioning/).
- [Grafana Dashboard HTTP API](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/dashboard/) and [API authentication](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/authentication/): `make doctor` reads the two provisioned dashboards using the `/apis/dashboard.grafana.app/v1` endpoint and local Basic auth. This API is available in Grafana 12+; Grafana 13 deprecates legacy `/api` routes.
- [Fluent Bit supported releases](https://github.com/fluent/fluent-bit/blob/master/MAINTENANCE.md) and [Kubernetes filter](https://docs.fluentbit.io/manual/data-pipeline/filters/kubernetes).
- [Fluent Bit Kubernetes metadata fields](https://docs.fluentbit.io/manual/data-pipeline/filters/kubernetes): the collector emits `namespace_name` and `pod_name` beneath its `kubernetes` record field; the index template and saved searches use those field names.
- [PostgreSQL 18.7 release notes](https://www.postgresql.org/docs/release/18.7/) and [official image tags](https://github.com/docker-library/official-images/blob/master/library/postgres).
- [Official PostgreSQL image documentation](https://github.com/docker-library/docs/blob/master/postgres/content.md): PostgreSQL 18 uses version-specific `PGDATA` below `/var/lib/postgresql`; the PVC mount targets that volume root.
- [Python 3.14.10-slim-bookworm Dockerfile](https://github.com/docker-library/python/blob/master/3.14/slim-bookworm/Dockerfile) and [official Python image architecture inventory](https://github.com/docker-library/official-images/blob/master/library/python): the selected base tag exists in the upstream inventory; this does not verify a live pull or pinned digest.
- [PyYAML 6.0.4 on PyPI](https://pypi.org/project/PyYAML/6.0.4/): current release files include CPython 3.14 wheels for Linux amd64/arm64 and macOS arm64/x86-64, matching the contributor runtime's Python version and candidate host architectures. The prior development pin, 6.0.2, had release wheels only through CPython 3.13; it was replaced to avoid requiring an unverified source build on Python 3.14.
- [FastAPI releases](https://github.com/fastapi/fastapi/releases), [Uvicorn release notes](https://github.com/Kludex/uvicorn/blob/main/docs/release-notes.md), [Psycopg supported systems](https://www.psycopg.org/psycopg3/docs/basic/install.html#supported-systems), and [Prometheus Python client](https://github.com/prometheus/client_python/releases).
- [HTTPX 0.28.1 on PyPI](https://pypi.org/project/httpx/0.28.1/) and [Ruff 0.9.2 on PyPI](https://pypi.org/project/ruff/0.9.2/): exact development pins used by the API test client and lint target, respectively. The wheel/install behavior for the pinned Python version remains untested.
- [Psycopg pool API](https://www.psycopg.org/psycopg3/docs/api/pool.html): a pool created with `open=False` must be opened before `getconn()`; the API opens it lazily after successful database DNS resolution.

Sources were checked on 2026-11-25 and informed the pins in `versions.yaml` and `app/requirements.txt`; the k3d release page and issue #1731 were rechecked on 2026-11-25. This establishes upstream release-line compatibility only. Registry tag existence, image architecture manifests, full deployment integration, and runtime behavior remain unverified. Recheck these pages before release. The reported k3d v5.9.0 security findings are an explicit release review item; do not describe the current tool pin set as security-cleared.

Make Linux amd64 first-class. Verify macOS arm64 before claiming support. Treat Windows with WSL2 and other platforms as documented candidates until tested. Start performance trials with 4 CPUs and 12 GiB available to the Docker VM, plus 25 GiB free on the host filesystem containing the checkout as a storage proxy. These are planning estimates; preflight does not measure Docker image-store capacity. Tune and publish observed requirements. A future lightweight profile may omit components only if it clearly reports unavailable exercises.
