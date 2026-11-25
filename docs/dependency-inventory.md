# Dependency inventory

Container pins are recorded in [`versions.yaml`](../versions.yaml) and
`app/requirements.txt`; contributor and test pins are in
`requirements-dev.txt`. The selected compatibility references and rationale
are in [`techstack.md`](techstack.md). Selection is based on upstream
documentation, but this repository has not installed or run these versions.
Container tags and multi-architecture availability are also unverified.

Direct Python runtime and development dependencies are exact-pinned, and the
source-only validator rejects duplicate normalized package names. It is also
configured to compare external manifest image references with `versions.yaml`
and check the API Dockerfile base pin, but it has not been executed. Transitive
dependency trees are not yet captured in a lock file; reproducible dependency
installation is a release gap. PyYAML is pinned to 6.0.4 because its PyPI
release includes CPython 3.14 wheels for the target Linux architectures.
Before publication, verify image
digests, signatures/provenance, platform manifests, licenses, and transitive
dependency licenses against the actual artifacts. No third-party dependency
binaries are bundled in the repository.

No CI workflow is configured; manual release checks are described in
`docs/testing.md` and `docs/public-release.md`.

The release owner must review all upstream terms before distributing images or
other dependency artifacts. The repository license has not been selected.
