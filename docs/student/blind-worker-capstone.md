# Blind worker capstone

**Estimated time:** 20 minutes (not trialed). **Prerequisite:** the instructor starts the exercise and gives only a symptom plus a UTC window.

**Symptom:** the API is still responding through one replica, while the other API replica is Pending and worker availability or workload placement differs from the healthy baseline.

The public `make lab-status` and `make diagnostics` views omit this exercise's
ID, title, and selected worker until the instructor reveals the verification
step. Do not inspect the instructor's terminal or private `.lab/state.json`.

1. **Hint 1 · Layer:** compare node health with workload placement.
2. **Hint 2 · Evidence:** inspect recent scheduling events and compare them with current replica availability.
3. **Hint 3 · Focus:** compare `k get nodes -o wide`, `k -n lab get pods -o wide`, and recent events. Confirm any candidate belongs to this lab before proposing a repair.

Do not drain or delete nodes during diagnosis. Propose a scoped repair only after identifying the affected lab worker and confirming remaining API capacity. The instructor will reveal the exercise ID when it is time to run `make lab-verify LAB=12`; then confirm recovery and finish with `make lab-reset`.

The instructor answer key is in the [instructor guide](../instructor/answer-key.md#12-worker-capstone-spoiler).
