# Scenario implementation status

All twelve fault inputs are wired to the controller's catalog, symptom
detector, recovery verifier, reset path, student page, instructor runbook, and
two-pass integration runner. Lab 12 is deliberately applied as a guarded
imperative worker operation rather than applying its descriptive marker YAML.

These are authored contracts only. They have not been parsed, applied, or run
against Kubernetes. Keep the individual repair instructions aligned with the
baseline manifests and rerun `make lab-suite` twice on a disposable dedicated
lab before claiming scenario acceptance.
