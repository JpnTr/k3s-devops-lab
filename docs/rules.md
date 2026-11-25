# Implementation rules

- Keep one known-good baseline. Render and validate it before applying. Reset restores only lab-owned configuration and retains practice data.
- Use pinned inputs and stable resource names. Avoid abandoned configuration and unused scripts. Prefer declarative provisioning for dashboard and monitoring assets.
- Never mutate the default Kubernetes context or tunnel lab services to external networks. Validate all inputs before shell execution.
- Use bounded waits and observable success conditions. A scenario is incomplete if it only changes a manifest and never proves the symptom.
- Match docs to behavior. Update the PRD, architecture, contract docs, lab pages and checklist as relevant when modifying behavior.
- Keep credentials, identifiers from other environments, personal information and dependency binaries out of the repository. Use synthetic fixtures and validate automated issue attachments.
