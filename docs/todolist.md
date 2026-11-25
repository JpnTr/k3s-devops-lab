# Implementation milestones

This checklist reports authored state separately from runtime evidence. Per the
repository owner's instruction, no local project commands, tests, Docker, or
cluster operations were run during this implementation. Checkboxes therefore
remain open until the corresponding public Make targets have actually passed.

- [ ] **M1: Bootable workload.** Source authored: pinned version manifest,
  preflight, isolated k3d configuration and kubeconfig, API, PostgreSQL,
  ingress, DNS checks, and traffic workload. Still needs clean start, repeated
  `make up`, `make doctor`, and confirmed teardown on a supported host.
- [ ] **M2: Observability.** Source authored: Prometheus, Grafana, Fluent Bit,
  Elasticsearch/Kibana, Grafana dashboards, Kibana saved-search and Lens trend
  dashboard, alert rules, index lifecycle, and bootstrap. Imports, fresh
  request IDs, metrics, targets, alerts, and UI behavior still need runtime
  checks.
- [ ] **M3: Incident runner plus first class.** Source authored: lifecycle,
  private context, mutation lock, status, scenario detection, recovery checks,
  reset, and labs 01–12. Still needs public target execution and observed
  recovery for each scenario.
- [ ] **M4: Full catalog.** Source authored: twelve student briefs, instructor
  answer key, fault inputs, and two-pass integration runner. Still needs
  `make lab-suite` twice-per-scenario evidence and a review of diagnostics
  output in a real lab.
- [ ] **M5: Public release candidate.** The public repository now exists.
  Draft release docs and community templates exist. Still needs fresh-host and
  supported-platform checks, classroom trial, measured resource and duration
  records, screenshots, and the repository owner's license decision.

## Future feature backlog

These are planned discussions and are not implemented. Keep the current local
k3d workflow as the supported baseline until a separate real-server profile is
designed and validated.

- [ ] **F1: K3s operations labs.** Add exercises for joining an agent,
  diagnosing node health, draining/replacing a node, and practicing server or
  datastore recovery. Define safe lab topology, reset behavior, and measurable
  acceptance checks before implementation.
- [ ] **F2: Infrastructure-as-code examples.** Add optional Terraform examples
  for provisioning a small VM-based K3s cluster. Select the first target
  environment after discussing learner needs; keep provider examples separate
  and document cost, access, teardown, and supported versions.
- [ ] **F3: Network and security labs.** Add guided exercises for firewall
  rules, private API access, TLS, secrets, backups, and restore. Specify threat
  boundaries and ensure every fault is reversible and isolated to lab-owned
  resources.
- [ ] **F4: Deployment comparison guide.** Explain differences between local
  k3d and K3s on servers, including node lifecycle, networking, storage,
  ingress/load balancers, costs, and failure modes. Link it from the docs
  index and keep claims tied to the supported deployment profiles.

Feature completion requires its acceptance criteria, affected technical docs,
and actual verification evidence to be recorded here. Until then, leave the
checkbox open and state any blockers.

## Execution record

### 2026-11-25 — source authoring only

- Project commands run: none. The user explicitly instructed not to run the
  project locally. Read-only source inspection used `cat`, `sed`, and `rg`; file
  changes were made with patches. No Make target, application command, parser,
  build, test, Docker, or cluster operation was executed.
- Files and evidence: implementation files were authored and inspected as
  text; no runtime or static validation results are claimed.
- Follow-up source audit: added Kibana table dashboard references and checks
  for their embedded saved-object links; aligned Fluent Bit metadata fields and
  image pins; pinned PostgreSQL/Elasticsearch away from worker-drain eviction;
  opened the API pool lazily after database DNS resolution; made teardown
  cleanup retryable after cluster deletion; added a per-cluster private owner
  marker with fail-closed handling for malformed marker data; routed suite
  repairs through the mutation lock; made capstone reset restore two-worker
  placement; made repeated baseline reconciliation rerun Kibana bootstrap;
  pinned CI actions by verified commit; converted tests to discoverable
  `unittest` cases; expanded API contract coverage for malformed/oversized
  bodies, untrusted request IDs, deterministic failure behavior, and stable
  database error codes; added referenced Kibana Lens trend charts for request,
  error, and indexed-event volume, with static checks for their data layers and
  dashboard references plus a unit contract for the dashboard chart refs. These
  changes have not been executed. Reclassified unmeasured CPU/RAM/disk values
  from preflight rejection thresholds to warnings and expanded the host matrix
  with command, version, artifact, and measurement fields. No host results were
  added. Clarified that preflight disk figures measure the host filesystem
  containing the checkout, not Docker image-store capacity. Strengthened
  scenario 01/02/04/08/09/12 recovery evidence with repeated
  ingress, ready-endpoint, and database-backed requests where those exercises
  require service recovery. Latency recovery now requires three successful fast
  Orders responses; memory recovery checks restart-count stability for 15
  seconds; metrics recovery requires a successful request and a newly timestamped
  Prometheus series after scrape recovery; DNS recovery checks a fresh request
  ID's indexed log for absence of the DNS error code. Updated the database
  lifecycle spec to document the 1,000-row generated-order cap, fixture
  retention, 2 GiB PVC request, and runtime checks still needed. Extended the
  suite to verify generated orders survive repeated `make up` and each of the
  24 resets using fresh synthetic SKUs, and a request ID remains indexed after
  the complete two-pass suite. Suite persistence writes now go through the
  controller's identity-checked port-forward to the lab Service, not a raw
  host-port request. Extended `make doctor` with a Kibana API check that the
  dashboard is present and references all three Lens charts, a Grafana API
  check for both provisioned dashboards, and a Prometheus API check for all four
  alert rule names. Static validation now rejects duplicate saved-object IDs
  and alert names, and checks internal Markdown heading fragments using the
  same fenced-code-aware heading parser for catalog instructor anchors and
  ordinary document links. Added focused regression tests for duplicate
  headings and fenced-code boundaries; these and the validator remain unrun.
  Alert firing and thresholds remain unverified. Added contributor setup
  instructions for the pinned Python dependencies required by `validate`,
  `test`, and `lint`, matching the CI install step. Added fail-closed `.lab/`
  symlink guards, restrictive permissions for private files, and narrowed
  teardown cleanup to known controller files, with regression tests for
  preserving unknown entries; these remain unrun. Recovery verification for
  scenarios 01/02/09 now explicitly requires the expected two API replicas,
  Ready pods, and ready Service endpoints; a unit contract was added but not run.
  Lab 12 detection now waits for a Pending API replacement and exactly one
  available replica after the recorded worker is drained; its recovery check
  requires exactly two available replicas, two ready endpoints, spread over
  schedulable workers, and healthy requests. Added detector and worker-placement
  unit coverage; all checks remain unrun.
  Scenario 05 now records a failed request ID and waits for matching v2
  `synthetic_failure`/503 evidence in Elasticsearch before activation and after
  rollback; added a field-level matching unit contract, not run.
  Scenario 07 now activates only on a recorded `db_pool_timeout` 503 and checks
  that same event remains indexed after recovery; added a field-level unit
  contract, not run.
  Scenario 04 activation now requires the ingress 404 and a successful direct
  Service `/livez` negative control; added a predicate unit contract, not run.
  Scenario 03 now requires healthy API liveness and an indexed `db_dns_error`
  for the exact failed request ID. Scenario 10 checks Elasticsearch cluster
  health before classifying missing ingestion, and scenario 11 requires live
  API traffic plus an indexed log while Prometheus reports the target down.
  Updated instructor and contributor testing notes and added a static detector
  contract; all changes remain unrun.
  Updated `make help` to include the public validation and integration targets
  already described in the README and testing guide, with a static contract for
  declared target/help alignment; included `help` itself and documented the
  command in both references. Not executed.
  Updated the contributor PyYAML pin from 6.0.2 to 6.0.4 after checking the
  upstream PyPI release files for CPython 3.14 wheels; documented the pin
  rationale. This is metadata evidence only; contributor installation and the
  validation targets remain unrun.
  Confirmed the pinned Python 3.14.10 slim Bookworm base tag and Docker image
  architectures against the official Python image inventory; this does not
  verify a pull, digest, or build.
  Added unrun validation and unit contracts requiring exact direct Python
  dependency pins, matching API/CI Python versions, and CI installation of both
  requirement files. The transitive dependency lock remains an explicit release gap.
  Tightened labs 02 and 09 detection to require their exact injected probe or
  node-selector fault, a stalled replacement in the expected state, two ready
  old endpoints, and a successful Orders request. Added predicate coverage and
  aligned the scenario catalog and instructor notes; not run.
  Continued scenario contract audit: labs 01, 03, 04, 05, 06, 08, 10, and 11 now
  require the exact injected selector, DB host, ingress host, delay, memory
  settings, collector output, or scrape path along with their symptom evidence.
  Added focused predicate contracts and updated the catalog/testing notes;
  none were executed.
  Recovery now additionally requires restored API Service selection, DB host,
  v1/failure settings, baseline memory allocation/limit, Fluent Bit ES output,
  and Prometheus scrape annotations. Extended API baseline mocks and added an
  unrun recovery-wiring contract.
  Lab 12 recovery now waits for the API rollout before checking readiness and
  worker spread, avoiding an immediate false failure after uncordon. Added an
  unrun contract for the rollout wait, and asserted the wait is in recovery
  verification rather than the fault detector so the Pending fault can still
  activate. No tests were run.
  Database bootstrap now reapplies the local app-role password on each run.
  `make up` now deletes the prior completed bootstrap Job before applying it so
  the idempotent SQL actually reruns against the retained PVC.
  Initial credentials are created before cluster provisioning; malformed
  credentials always fail closed, and missing credentials fail closed when the
  cluster may retain a PVC. Added static contracts for password reconciliation,
  fixture idempotency, and the credential lifecycle including first-run creation
  and restrictive file mode; none were executed.
- Follow-up source audit: reviewed controller lifecycle, public command
  declarations, application/API behavior, and release evidence without
  executing project code. Confirmed from the [official Psycopg pool API](https://www.psycopg.org/psycopg3/docs/api/pool.html)
  that `ConnectionPool.open()` is safe to call on an already-open pool, which
  supports lazy opening after DB DNS resolution. This documentation evidence
  does not validate the pinned package or runtime behavior. No host-test results
  or publication/license decisions are recorded as complete.
  The same API review found that PostgreSQL `timestamptz` response formatting
  depended on the database session timezone despite the UTC contract. Both
  order response paths now normalize timestamps to UTC `Z` form, with a focused
  unit contract and API documentation update. The test was authored but not run.
  The Kibana doctor check now also verifies the four provisioned saved searches,
  as well as the dashboard's Lens references. Updated its public target docs and
  added an unrun static contract; the saved-object endpoint is marked deprecated
  upstream and requires review before a future Kibana upgrade.
  Public issue-template inspection found Helm listed as a prerequisite even
  though the lab does not use it; the template now requests Docker, k3d, K3s,
  kubectl, Python, Make, OS release, and architecture. No checks were run.
  Scenario review found Lab 04 recovery could pass with the injected wrong-host
  rule still present alongside an added correct route. Verification now requires
  the canonical one-rule host/path/backend spec before checking ingress and
  direct-Service success; the regression contract is unrun.
  Verifier review also tightened baseline restoration for Labs 05–09 and 12:
  fault-only environment values must be absent, the explicit pool size must be
  five, the allocation and memory limit must match baseline, and worker
  placement selectors must be exact. `make up` now refuses to mutate a cluster
  recorded in teardown. Added unrun predicate/lifecycle contracts.
  Recovery checks for Labs 03, 06, and 07 now wait for the API rollout and
  baseline replicas; Lab 10 waits for the Fluent Bit DaemonSet rollout before
  testing fresh log ingestion. Added unrun wiring assertions and aligned
  instructor recovery instructions.
  Suite review found that its new-order sentinel check searched only the oldest
  100 Orders, so it could miss every newly inserted row on a populated lab. The
  API now exposes a bounded, parameterized exact-SKU filter and suite checks use
  it; API and suite-wiring contracts were added but not run.
  Instructor documentation now identifies the scenario-specific negative
  controls the runner actually checks. Lab 03 detection now requires exactly one
  Ready PostgreSQL pod as well as the exact DNS error, preventing an unrelated
  database outage from activating the DNS exercise; the predicate contract and
  student/instructor notes are unrun/source aligned.
  The implementation rule requiring render/validation before applying was not
  wired into the controller. Baseline, reset, repair, and declarative scenario
  paths now issue a server-side dry-run through the dedicated kubeconfig first;
  `make validate` checks local Kustomize resource/generator references. Added an
  unrun contract; live API admission behavior and all public targets remain
  unverified.
  Lifecycle review found that an interrupted pre-baseline start could leave
  `cluster_owned_intent` without a cluster and make confirmed teardown refuse.
  Teardown now cleans known private state when the dedicated cluster is absent,
  and re-runs owner-token validation before deleting an existing cluster. Added
  unrun regression contracts for an absent cluster, deletion retry with no
  namespace, malformed k3d list output, and owner-token checks on visible nodes
  in an incomplete cluster. Partial-cluster cleanup is implemented only after
  the private kubeconfig, expected node names, and every visible node's owner
  label are confirmed; the failure-injection integration check remains unrun.
  Added a regression contract that kubectl helpers always pass the lab's
  private kubeconfig and explicit context, while k3d commands receive a
  separate private kubeconfig and k3d is configured not to update or switch
  the caller's default kubeconfig/context. This test is authored but unrun.
  Reviewed the current Make target list against the README and release protocol:
  lint, validate, unit tests, preflight, up, doctor, two-pass lab suite, repeat
  up, and confirmed teardown are documented. The user-requested no-run
  constraint leaves every command result and every host/runtime gate pending;
  this text audit does not substitute for those checks.
  Instructor-document review found the blind capstone required a UTC window
  without explaining how to obtain it privately. Added instructor-only start
  and status steps that source the window from recorded UTC state while keeping
  the scenario ID hidden from learners. Documentation change only; no exercise
  or runtime validation was performed.
  Capstone pre-drain review found `worker_candidate()` previously accepted
  merely two distinct ready-pod node names, which could include a non-worker or
  a drifted replica count. It now requires the healthy API/endpoints baseline,
  exactly two Ready schedulable labeled agents, a two-replica worker-selected
  Deployment, and one Ready API replica on each agent before drain. Added
  unrun unit/static contracts and aligned the architecture, testing, and
  instructor documentation. No drain, test, or cluster operation was run.
  The same pre-drain gate now also requires successful API liveness and a
  database-backed Orders request, so the worker fault is not introduced on an
  already unhealthy service. Added an unrun ordering contract and updated the
  runbook text; runtime acceptance remains pending.
  Teardown documentation review found README's claim that all lifecycle state
  is deleted did not match the controller and existing contract: teardown
  writes a minimal `state.json` with `state: absent` and leaves the lock file,
  while removing credentials and kubeconfig/owner files and preserving unknown
  entries. Updated README and database lifecycle text; no teardown was run.
  Preflight source review found that k3d, kubectl, and Python versions were
  documented as pinned but not enforced. It now compares local version output
  to the explicit tool/runtime pins before Docker inspection; static
  manifest-alignment checks and unrun parser/order contracts were added.
  Updated target and compatibility documentation. No local version command or
  public target was run.
  Static validator source review also found malformed `versions.yaml` root or
  `images`/`tools` shapes could raise incidental attribute errors instead of a
  validation diagnostic. It now rejects those structures through its normal
  error report; this handling has not been executed.
  Release-document review found `CODE_OF_CONDUCT.md` claimed to follow
  Contributor Covenant 2.1 while containing only a brief summary. It now labels
  itself as a draft, links the complete proposed upstream text, and leaves
  adoption/contact decisions with the repository owner. Documentation-only;
  no publication action was taken.
  Security-policy review found it directed reports to an unconfigured hosting
  contact. It now labels itself as a draft and states the private contact and
  response process the owner must configure before publication.
  Release guardrail review found Fluent Bit's node log mounts and writable tail
  database path were not documented. Added the k3d-node scope, read-only log
  mounts, limited RBAC verbs, writable state path, and an unrun manifest/docs
  contract. No cluster permission inspection was run.
  Cluster-version review found `up` trusted recorded node ownership without
  checking the pinned K3s runtime. It now requires exactly the expected server
  and two agents, all reporting the pinned kubelet version; teardown can bypass
  only that version comparison after the same node-name, ownership-token, and
  namespace identity checks. Added unrun node-version and static pin-alignment
  contracts and documented the K3s `+k3sN` report form. No cluster was created
  or queried.
  Added an unrun contract proving the stale-version teardown override still
  requires the dedicated context, owner token on every expected node, and the
  lab namespace identity marker. No identity check was executed against a
  cluster.
  Lifecycle state review found valid JSON arrays/scalars passed through
  `read_state()` and then failed later at `.get()` call sites. The reader now
  rejects non-object JSON and handles decoding errors as controller errors;
  added unrun regression coverage. No state file was created or read during
  project execution.
  README prerequisites now list the exact enforced k3d, kubectl, and Python
  pins and distinguish them from the in-cluster K3s image; Docker version
  requirements remain unmeasured. No prerequisites or host matrix were run.
  Official k3d docs specify Docker Engine 20.10.5 as the k3d 5.x minimum. Added
  a server-version parser and preflight rejection below that threshold, parser
  contracts, official install/release links, and a note that the threshold is
  not platform support evidence. No local Docker version was inspected.
- Compatibility research: component compatibility references and selected
  versions are recorded in `docs/techstack.md` and `docs/dependency-inventory.md`.
  These references support version selection, not validation of this lab.
- Upstream security review: documented the open community report of high
  severity findings in k3d v5.9.0 and made owner review plus patched-version
  disposition a public-release gate. The report was not independently tested.
  Rechecked the official k3d releases page and issue #1731 on 2026-11-25: v5.9.0
  remains listed as latest, and the open report's later update adds two
  findings to the initial 25. No replacement pin was selected without an
  upstream patched release and compatibility evidence; owner security review
  remains a publication blocker.
- Link review: opened the official Kubernetes kubectl install URL listed in
  README; it redirects to the current Kubernetes “Install Tools” page. This
  verifies the destination exists, not the pinned kubectl release or any local
  installation. No project command was run.
- CI source review: the Python dependency cache key previously tracked only
  `requirements-dev.txt`; it now tracks both runtime and development pins, with
  a static contract authored. Checked the setup-python documentation for
  multiline dependency-path support. The contract and workflow have not been
  run.
- Dependency validation review: exact pins did not reject duplicate package
  names written with normalized spelling. The source validator and an unrun
  static contract now reject duplicates in each requirement file.
- Dependency reference review: added PyPI release pages for the HTTPX and Ruff
  development pins. This documents upstream release artifacts only; installation
  and execution under the pinned Python are still unverified.
- Dependency inventory now distinguishes container/runtime pins from
  contributor/test pins and documents duplicate-name validation alongside the
  existing unresolved transitive-lock limitation. No installer or validator
  was run.
- Compatibility-link review: replaced k3d `stable` documentation links with
  v5.9.0-specific config, cluster-create, version, and requirements references.
  Those upstream pages document the exact fields/flags and Docker floor used by
  the pinned integration. This is source-reference evidence only; nothing was
  run locally.
- Compatibility-link contract: added an unrun assertion that README and the
  technology record retain the v5.9.0-specific references and do not revert to
  the moving `stable` documentation path.
- Blind-capstone review: public `lab-status` and diagnostics exposed the active
  lab ID/title and selected worker. They now redact those fields for Lab 12 and
  lifecycle status uses a safe-field allowlist. Aligned PRD, architecture,
  student/instructor guidance, and added unrun state-view/catalog contracts; no
  capstone was run.
- Follow-up catalog review found `make lab-list` still mapped the blind
  capstone title to ID 12. Public output now labels it `CAPSTONE` without a
  number, with an unrun formatting/wiring contract and student-doc update.
- Repository publishing preference: removed the GitHub Actions pipeline and
  its workflow-specific validation/docs; Make targets remain documented for
  manual checks. No pipeline or project check was run.
- Scenario alignment review: added an unrun contract requiring the maintainer
  suite references and IDs to match the 12-item catalog and to check unrepaired
  failure before repair and successful verification on both passes. No scenario
  was executed.
- Release-check review: expanded the clean-host protocol to list every public
  target, including helper/status/diagnostics commands, and call for diagnostics
  privacy review; explicitly added contributor dependency installation before
  checks. No release check was run.
- Host matrix: no host was tested. See `docs/host-matrix.md`.
- Timing/resource proposals: catalog durations and host resource thresholds
  remain planning estimates; no measurements or classroom trial exist.
- Concrete blockers: runtime checks require execution on a permitted host with
  Docker, k3d, kubectl, and the pinned tools. License ownership remains with
  the repository owner.

### 2026-11-25 — public repository creation and push

- Commands actually run: `git init -b main`,
  `gh repo create JpnTr/k3s-devops-lab --public --source . --remote origin`,
  `git add -A`, `git commit -m "Implement K3s DevOps Lab"`, and
  `git push -u origin main`.
- Results: GitHub returned `https://github.com/JpnTr/k3s-devops-lab`; commit
  `73fb4c1` was pushed to `main`, and the branch tracks `origin/main`.
- No project checks, builds, dependency installs, Docker commands, or cluster
  operations were run. The repository has no CI pipeline. Milestones remain
  open pending their documented evidence.

### 2026-11-25 — bug/feature workflow and backlog

- Updated `AGENTS.md`, `docs/rules.md`, `docs/bugs.md`, and the documentation
  index with bug triage, bug-log updates, technical-document alignment,
  verification evidence, and feature completion rules.
- Added F1–F4 to this checklist: K3s operations labs, Terraform examples,
  network/security labs, and a deployment comparison guide. All remain
  proposed and unchecked; no implementation or acceptance review was done.
- Reviewed the documentation diff with `git diff`. No project checks, tests,
  builds, Docker, or cluster commands were run.

## Required evidence to close milestones

Record the date, host/OS/architecture, exact command, exit status, relevant
output, and artifact path for each check. Run only on the dedicated lab cluster
created by this repository. Never claim a host as supported based on source
inspection alone.
