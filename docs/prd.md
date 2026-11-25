# Product requirements

Build an openly available, clone-and-run incident lab for junior DevOps engineers and instructors. Entry skills are basic shell, HTTP, and container concepts. By the end, learners should trace a request, isolate failure by layer, correlate logs and metrics, repair a Kubernetes workload, and demonstrate recovery.

## User journey

Clone repository → check prerequisites → provision local cluster → inspect healthy traffic → start a lab → investigate with optional hints → make a repair → verify recovery → reset → write a short incident report.

## Scope

- Core release includes k3d/K3s, a synthetic Orders API, PostgreSQL, repeatable traffic, Prometheus/Grafana, Elasticsearch/Kibana, and twelve independently resettable labs.
- Supply complete starter dashboards, saved searches, alerts, student and instructor guides, host troubleshooting and a blind capstone.
- Preserve the blind capstone until instructor reveal: public catalog/status views must not expose its numeric ID, and status/diagnostics must not expose its active title or selected worker.
- Local learning is the primary workflow. Three real Linux VMs, richer tracing, and hosted classroom delivery are future enhancements.

## Release outcomes

- A supported clean host needs only documented prerequisites and the quickstart. One command provisions dashboards and baseline traffic.
- Every published exercise produces a detectable fault and passes fault → recovery → reset testing. Reset preserves history and seeded data.
- At least one student completes an exercise and capstone using student materials. Record where they got stuck and fix onboarding friction.
- Publish measured startup time, memory, CPU and disk usage alongside the supported platform matrix.
