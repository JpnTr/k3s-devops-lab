# Manual verification

No checks have been run for the current source. The exact record belongs in
[`todolist.md`](todolist.md); never infer a pass from authored configuration.

## Public Make targets

Run `make help` to list the public Make targets.

Install the checked-in dependency pins before running contributor checks:

```sh
python -m pip install -r app/requirements.txt -r requirements-dev.txt
```

- `make lint`: Ruff undefined/unused-name checks and Python bytecode compilation
  for application, controller, and tests.
- `make validate`: parse YAML, JSON, NDJSON and verify local Kustomize resource
  and generator-file references (including saved-object panel
  references and required Kibana Lens charts), compare external manifest image
  pins, require exact direct Python dependency pins and matching API/controller
  Python versions, check expected Grafana dashboard UIDs and alert rule names,
  check scenario catalog files and
  instructor anchors, and resolve internal Markdown files and heading
  fragments.
- `make test`: API and static contract unit tests, including the required
  alignment between the 12-entry scenario catalog and two-pass suite with an
  unrepaired negative check before learner repair, plus checks that k3d
  compatibility links stay pinned to v5.9.0, public status/diagnostics
  redaction and catalog ID hiding for the blind capstone, and Markdown heading
  anchor behavior for duplicate headings and fenced code blocks, symlink
  rejection and restricted permissions for private lab state, and preservation
  of unknown `.lab/` entries during teardown cleanup. It checks that `make help`
  includes the declared public targets. Scenario 01/02/09 recovery
  requires two available API replicas, Ready pods, and ready Service endpoints.
  Lab 12 contracts cover actual scheduling impact, exactly two recovery
  replicas/endpoints, and separate Ready replicas on two schedulable workers.
  Lab 05 requires the exact failed v2 request ID and matching structured 503
  evidence in Elasticsearch before activation and after rollback.
  Lab 07 requires an indexed `db_pool_timeout` response for fault detection and
  retains that request evidence through successful recovery.
  Lab 04 requires an ingress 404 with a healthy direct-Service `/livez` control.
  Lab 03 requires an indexed `db_dns_error` for the exact failed request while
  API liveness remains healthy and PostgreSQL has exactly one Ready pod. Lab 10 checks Elasticsearch cluster health
  before diagnosing missing log ingestion; Lab 11 requires successful API
  requests and an indexed log while the scrape target is down. Lab 02 binds
  detection to the injected readiness path and an unready replacement while
  the two old endpoints still serve; Lab 09 binds it to the no-match worker
  selector, a Pending replacement, and the same healthy old-replica control.
  Labs 01, 03, 04, 05, 06, 08, 10, and 11 also require their exact injected
  selector, DB host, ingress host, delay, memory settings, collector output, or
  scrape path with the corresponding symptom and negative controls.
  Recovery checks confirm the baseline Service selector and worker placement,
  DB host, exact Ingress rule, v1/failure settings, absence of injected delay and
  pool hold, baseline memory allocation/limit, Fluent Bit output, and scrape
  annotations are restored where those scenarios mutate them. `make up` refuses
  to reconcile a cluster while recorded teardown is in progress. Labs 03, 06,
  and 07 require a completed API rollout and healthy baseline replicas before
  recovery traffic; Lab 10 requires the Fluent Bit DaemonSet rollout before
  checking a new indexed request.
- `make lab-suite`: on an existing disposable lab, run all 12 scenarios twice,
  require unrepaired recovery checks to fail, then apply learner repairs and
  check recovery/reset. It also creates synthetic orders to verify that repeat
  `make up` and every reset preserve generated data, and checks a stable request
  ID remains indexed after all scenario resets.
- `make doctor`: verify the dashboard import exists in Kibana and references all
  three expected Lens charts, and confirm all four saved searches are imported;
  this checks saved objects without claiming UI rendering or interaction was
  tested. It checks the two Grafana dashboards
  through Grafana's API, and checks that all four Prometheus alert rules are
  loaded; alert threshold firing and recovery still need measured runtime
  trials.
- `make preflight`: require exact k3d, kubectl, and Python pins plus k3d's
  documented minimum Docker Engine version before checking Docker resources
  and host ports. This confirms local version strings only;
  compatibility and host support still require the release checks below.

No CI pipeline is configured. The clean-host release trial
must install the checked-in contributor pins with
`python -m pip install -r app/requirements.txt -r requirements-dev.txt`, then
cover every public target: `make help`, `make lint`, `make validate`,
`make test`, `make preflight`,
`make up`, `make doctor`, `make urls`, `make lab-list`, `make lab-status`,
`make diagnostics`, `make lab-suite` (including start/verify/reset for all 12
scenarios), repeated `make up`, and `make down CONFIRM=yes`. Review diagnostics
for sensitive data before sharing. Repeat the full applicable target set on
each advertised platform.

## Integration acceptance

- Fresh cluster and repeated up; caller kubeconfig/current context remain unchanged. Record observed host and Docker resources; preflight reports Docker VM CPU/RAM plus host checkout-filesystem free space, not Docker image-store capacity. Its resource figures are warnings until trials establish requirements.
- Check that fresh and reused clusters report the pinned K3s kubelet version on exactly the three expected nodes; verify that an identity-proven stale-version cluster can still be deleted.
- Before baseline, reset, and declarative scenario mutations, the controller uses the dedicated cluster context for server-side dry-run validation. Observing that validation succeed remains a runtime acceptance check.
- Ingress request, DNS probe, database read/write, fresh ID in Elasticsearch,
  Prometheus sample, dashboard provisioning, and alert behavior.
- Idempotent database bootstrap with app-role password reconciliation against
  the stored Secret, fail-closed behavior for malformed credentials and missing
  credentials on a persistent cluster, first-run credential creation with
  private permissions, fixture retention, and generated-order pruning under
  repeated provisioning and reset. Repeated `make up` must rerun the bootstrap
  Job against the existing PVC.
- For each scenario: healthy → fault detected → verifier fails before repair →
  learner repair → verifier succeeds → reset succeeds. Run every scenario twice.
- Before the Lab 12 worker drain, require exactly two Ready, schedulable labeled
  lab agents, exactly two API replicas selected for lab workers, and exactly one
  Ready replica placed on each agent, plus successful `/livez` and database-
  backed `/orders` requests. Refuse the drain when baseline readiness, traffic,
  or placement has drifted.
- Competing mutations, interrupted start, failed reset retry, wrong cluster
  identity, missing Docker, port collisions, and interrupted cleanup.
- Confirm teardown can clean private controller files after an interrupted
  cluster creation that left no named cluster, while preserving unknown `.lab/`
  entries. If a named cluster exists, require the private owner token to be
  re-established before deletion.
- The maintainer suite routes learner repairs through the controller's
  mutation lock and lab identity check; each suite subprocess has a 900-second
  ceiling, which remains a provisional limit until trial timings are measured.
- Reset retains seeded orders and previous logs; teardown removes only the
  dedicated lab and its data, removes known controller-owned `.lab/` files, and
  preserves unknown local entries.
- The maintainer suite checks that generated sentinel orders remain visible
  after repeated `make up` and after each of the 24 scenario resets; `lab-reset`
  separately confirms all seeded fixture SKUs. At suite end, it checks that the
  initial sentinel request ID is still indexed in Elasticsearch.
- Review diagnostics output before sharing. Record exact command, status, host,
  OS, architecture, versions, startup time, and measured CPU, memory, and disk.

Tune timeouts and resource requirements from measurements. No advertised host
or platform support is established until the matching evidence is recorded.
