# Host test matrix

No host has completed the clean-host or runtime test protocol yet. Linux amd64 is the intended first platform. macOS arm64, Windows with WSL2, and other hosts remain candidates only. Do not advertise these as supported until `docs/testing.md` is followed and all release checks pass. Resource figures are planning hypotheses until actual trials provide measurements.

| Platform candidate | Host and OS version | Architecture | Docker Engine/Desktop and VM allocation | k3d / K3s / kubectl / Python versions | Public targets and result | Setup duration / peak CPU / peak RAM / disk | Evidence artifact |
|---|---|---|---|---|---|---|---|
| Linux amd64 (initial target) | Not tested | — | — | — | Pending | Not measured | — |
| macOS arm64 (candidate) | Not tested | — | — | — | Pending | Not measured | — |
| Windows with WSL2 (candidate) | Not tested | — | — | — | Pending | Not measured | — |

For each trial, include the exact host model or VM type, OS release, Docker
configuration, tool versions, date, exact command and exit status, sanitized
command transcript or evidence artifact, and any failure. Install the checked-in contributor pins
with `python -m pip install -r app/requirements.txt -r requirements-dev.txt`,
then exercise every public target on a clean host: `make help`, `make lint`,
`make validate`, `make test`, `make preflight`,
`make up`, `make doctor`, `make urls`, `make lab-list`, `make lab-status`,
`make diagnostics`, the two-pass `make lab-suite` (which exercises
`lab-start`/`lab-verify`/`lab-reset`), repeated `make up`, and finally
`make down CONFIRM=yes`. Review diagnostics output for sensitive data before
sharing it. A platform is supported only after every required target passes
and the repository owner reviews the evidence.

Measure startup from the `make up` invocation to its successful completion.
Collect Docker VM peak CPU and memory during provisioning and a complete
two-pass suite; record host checkout-filesystem free space separately from
Docker image-store and persistent-volume usage. Preflight reports only the
first of those disk measures. Report measurement method and tool alongside each
value. Do not write the current preflight estimates into the result columns as
if they were observations.
