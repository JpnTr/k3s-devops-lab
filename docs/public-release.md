# Public GitHub release

## Repository assets

The repository contains draft README, host matrix, lab catalog, contribution
links, teardown instructions, contribution/security/community documents,
changelog, issue/PR templates, and dependency inventory. Quickstart, platform
matrix, resource figures, and runtime screenshots remain pending because no
host checks have been run. Keep the project's LICENSE choice pending owner
selection. Apache-2.0 is a proposed option for original project code and docs.
Confirm upstream image and artifact distribution terms before bundling any
dependency.

## Local lab guardrails

Treat all workloads and records as synthetic. Bind interfaces to loopback, generate local credentials where the stack requires them, and keep state, passwords, kubeconfig, environment files and diagnostics out of Git. Provide a redacted diagnostics command for public issues. Scope collector permissions to what collection needs and document any required host log mounts. Refuse to run faults or destructive operations against a cluster lacking the expected local identity checks.

## Release checks

Tag only verified versions. Run a clean clone without maintainer credentials and exercise every public Make target, including the two-pass scenario suite and confirmed teardown, on every platform advertised as supported. Review diagnostics for sensitive data before sharing. Follow every README command. Publish exact prerequisites, release limitations, checksums for any distributed assets, and a way to reproduce reported issues. Accept scenario contributions only when student materials, fault detection, repair checks, and reset coverage ship together.

Before release, review the [reported high-severity findings against k3d
v5.9.0](https://github.com/k3d-io/k3d/issues/1731). At the 2026-11-25 source
review, the upstream releases page still identified v5.9.0 as latest. The open
community Trivy issue lists 25 initial findings and two more in a later update;
this project has not independently reproduced the report or verified a fixed
release. Record the reviewed artifact/version and disposition. Do not treat the
current pin as security-cleared.
