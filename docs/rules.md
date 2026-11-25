# Implementation rules

- Keep one known-good baseline. Render and validate it before applying. Reset restores only lab-owned configuration and retains practice data.
- Use pinned inputs and stable resource names. Avoid abandoned configuration and unused scripts. Prefer declarative provisioning for dashboard and monitoring assets.
- Never mutate the default Kubernetes context or tunnel lab services to external networks. Validate all inputs before shell execution.
- Use bounded waits and observable success conditions. A scenario is incomplete if it only changes a manifest and never proves the symptom.
- Match docs to behavior. Update the PRD, architecture, contract docs, lab pages and checklist as relevant when modifying behavior.
- Keep credentials, identifiers from other environments, personal information and dependency binaries out of the repository. Use synthetic fixtures and validate automated issue attachments.

## Bug-fix workflow

1. Search `docs/bugs.md` for the same symptom, component, scenario, or likely
   cause before changing code.
2. If a matching bug exists, use its recorded reproduction, diagnosis, and fix
   approach. Confirm the current source still matches the recorded conditions;
   revise the approach if it does not.
3. If no matching bug exists, investigate from the evidence and choose a
   minimal fix. Add a bug-log entry with a stable ID, status, severity, affected
   versions/platforms, reproduction, expected and actual behavior, sanitized
   evidence, and fix reference.
4. Update all affected technical documents in the same change. This may include
   architecture, API/database/observability contracts, scenario briefs,
   instructor notes, compatibility, host support, and release guidance.
5. Add or update regression coverage. For scenarios, keep the student brief,
   instructor notes, detector, verifier, reset, and tests aligned.
6. Record commands actually run, outcomes, and remaining blockers in
   `docs/todolist.md`. Keep checks open if they were not run or did not pass.
   Link the fix and verification evidence from `docs/bugs.md`.

## Feature workflow

- Before implementation, add the feature to `docs/todolist.md` with a clear
  scope, dependencies, and acceptance criteria. Read the relevant design docs.
- Implement in small, reviewable steps. Update all technical documents that
  describe affected behavior, interfaces, supported platforms, operations, or
  safety boundaries. Update student and instructor materials when learning
  behavior changes.
- Add suitable automated or manual verification instructions. Record only
  checks actually performed, their results, and concrete blockers in the
  checklist.
- Mark a feature complete only after its acceptance criteria and required
  evidence are satisfied. Code or documentation being written alone does not
  count as completion.
