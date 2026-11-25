# K3s DevOps Lab

A local incident-response lab for junior DevOps engineers and instructors. It builds a dedicated k3d/K3s cluster with a synthetic Orders API, PostgreSQL, Traefik ingress, Prometheus, Grafana, Fluent Bit, Elasticsearch, and Kibana. Twelve labs introduce reversible faults and ask learners to diagnose, repair, verify, and reset the system.

**Implementation status:** the command controller, manifests, scenario inputs, observability assets, student briefs, instructor key, and tests have been authored. They have not been run in a cluster or validated locally. This repository has no CI pipeline; run the documented checks manually. Treat all timing and resource figures as planning hypotheses. See [the milestone evidence](docs/todolist.md) and [host matrix](docs/host-matrix.md).

## Requirements

Linux amd64 is the initial target. macOS arm64, Windows/WSL2, and other architectures are candidates until they complete the release protocol. Install Docker Engine/Desktop with its CLI, Make, and these exact host tool versions:

| Host tool | Required version |
| --- | --- |
| Docker Engine/Desktop | Server version `20.10.5` or newer; see [Docker installation docs](https://docs.docker.com/engine/install/) |
| k3d | [`v5.9.0`](https://github.com/k3d-io/k3d/releases/tag/v5.9.0); see the [v5.9.0 install and requirements guide](https://k3d.io/v5.9.0/) |
| kubectl | [`v1.36.6`](https://kubernetes.io/docs/tasks/tools/); see [official install guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/) |
| Python | [`3.14.10`](https://www.python.org/downloads/release/python-31410/) |

`make preflight` enforces the k3d, kubectl, and Python versions plus the Docker
minimum. The Docker minimum comes from k3d's documented requirement and is not
a tested platform baseline. The K3s runtime is supplied by
the pinned `rancher/k3s:v1.36.6-k3s1` node image; it is not a separate host
install. The full image inventory is in [`versions.yaml`](versions.yaml), and
upstream compatibility sources are listed in [the tech stack record](docs/techstack.md).
Docker version requirements, the pin set, and image architecture manifests
still need runtime verification. The current k3d pin also has an open security
review item described below.

The initial preflight estimates are 4 CPUs and 12 GiB of Docker VM resources, plus 25 GiB free on the host filesystem containing the checkout. They are unmeasured hypotheses: preflight reports when a host is below them but does not use them as support gates. The filesystem figure is only a host-side proxy; Docker image-store capacity is not measured. Measure actual startup time and resource use before publishing support requirements.

## Quickstart

```sh
make preflight
make up
make doctor
make urls
```

`make up` creates only the named `k3s-devops-lab` cluster, writes kubeconfig files under the ignored `.lab/` directory, and never switches or updates the caller's default context. Add `127.0.0.1 orders.lab.test` to the local hosts file if you want browser access by hostname. To probe without editing hosts, use:

```sh
curl -i -H 'Host: orders.lab.test' http://127.0.0.1:8080/orders
```

If a previous teardown was interrupted, finish it with `make down CONFIRM=yes` before running `make up` again; the controller refuses to reconcile a cluster while teardown is recorded as in progress.

Use the dedicated kubeconfig when inspecting the cluster:

```sh
kubectl --kubeconfig .lab/kubeconfig --context k3d-k3s-devops-lab get pods -A
```

Open Grafana and Kibana on `http://127.0.0.1:3000` and `http://127.0.0.1:5601` using the port-forward commands printed by `make urls`. Grafana's local login is `labadmin`; its generated password is in the ignored `.lab/credentials.json`. Kibana has local-only unauthenticated access inside this dedicated lab.

## Run an incident

```sh
make lab-list
make lab-start LAB=03
# Investigate and repair the responsible lab resource.
make lab-verify LAB=03
make lab-reset
```

See the [student workbook](docs/student/README.md) and the [12 incident briefs](docs/student/). `make lab-suite` is the maintainer integration command: it checks repeated `make up`, generated-order persistence, and retained log history; performs two passes across all 12 incidents; tests that unrepaired faults fail recovery checks; applies learner-style repairs; and confirms an order survives each reset. It mutates only the dedicated lab cluster and should be run only on a disposable lab installation.

## Teardown and data

`make lab-reset` restores lab-owned configuration and retains seeded orders, recent generated orders, and observability history. `make down CONFIRM=yes` deletes the dedicated cluster, its PVCs, local credentials, owner marker, and kubeconfig files. It leaves a minimal `state.json` marked `absent` plus the mutation lock in `.lab/`; unknown files and directories there are preserved. The caller's normal kubeconfig is not used by the controller. Do not use teardown when the cluster identity check fails.

## Public targets

For contributor checks, install the pinned Python dependencies first:

```sh
python -m pip install -r app/requirements.txt -r requirements-dev.txt
```

This is needed for the API contract tests, YAML validation, and Ruff. The lab
controller itself uses Python's standard library.

| Target | Purpose |
| --- | --- |
| `help` | List public Make targets |
| `preflight` | Require the pinned k3d, kubectl, and Python versions plus the documented Docker minimum; check tools and Docker; report Docker VM CPU/RAM and checkout-filesystem free space against planning estimates; check loopback ports |
| `up` | Create or reconcile the dedicated healthy baseline and observability stack; refuse a cluster whose node kubelet version differs from the K3s pin |
| `doctor` | Check ingress, database-backed reads, DNS, indexed request ID, Grafana dashboards, Kibana dashboard/charts/saved searches, Prometheus samples, and loaded alert rules |
| `urls` | Print API and loopback UI access instructions |
| `lab-list` / `lab-status` | Show catalog and a safe lifecycle summary; the blind capstone catalog entry omits its numeric ID, and status hides its active ID, title, and selected worker |
| `lab-start LAB=NN` | Apply a scenario fault and wait for its symptom |
| `lab-verify LAB=NN` | Check learner repair without fixing the fault |
| `lab-reset` | Restore the baseline and verify recovery while retaining data/history |
| `diagnostics` | Write a reduced local diagnostics bundle for review before sharing; blind capstone ID, title, and selected worker are redacted |
| `down CONFIRM=yes` | Delete the named cluster and its lab-owned data |
| `validate` / `lint` / `test` | Check assets, Kustomize references, Markdown, and exact direct Python pins; run Ruff undefined/unused-name checks plus bytecode compilation; and run unit tests |
| `lab-suite` | Run each scenario twice on an existing lab cluster |

## Release and ownership

Compatibility links, dependency inventory, issue/PR templates, contribution and security drafts are present. See [public release requirements](docs/public-release.md) for pending runtime checks, classroom trial, screenshots, resource measurements, and policy review. The repository owner must choose the license and publication contact; no license is selected.

The pinned k3d v5.9.0 tool has an open community [Trivy report alleging 25 high-severity findings, with two more added in a later update](https://github.com/k3d-io/k3d/issues/1731). The upstream releases page still identifies v5.9.0 as latest. This project has not independently reproduced the report or verified fixes; owner review and a documented disposition are required before publication.

See the [documentation index](docs/README.md) for architecture, scenario,
instructor, testing, compatibility, and release documents.
