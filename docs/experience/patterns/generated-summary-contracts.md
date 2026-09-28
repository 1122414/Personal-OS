# Generated summaries need an output contract

- Signals: a requirement says “automatically summarize” or “save a report,” while agreement hides uncertainty about what the reader actually receives.
- Mechanism: a resumption brief, study note, and activity report serve different purposes. Without a reader task and content standard, the same implementation can produce a plausible but unusable artifact.
- Diagnosis and handling: specify the generating runtime, source scope, trigger, target length, section semantics, evidence for importance, provenance, human-edit ownership, failure/staleness states, and an example before implementation. Treat rendering separately from content quality.
- Applicability limits: word budgets and section counts are product-specific defaults, not universal rules. Do not infer mastery from an assistant explanation; distinguish explanation, self-report, and observed exercises.
- Supporting case: in the [2026-09-29 discussion](../../../.grill/personal-workspace-next-stage.md), the user challenged a vague editable-summary proposal and required authorship, shape, length, focus, Markdown, and UI to be concrete. The [specification](../../2026-09-29_personal-workspace-next-stage.md) records the contract and pending acceptance scenarios.
- Verification status: clarified and accepted as a design direction once. Implementation and real-user quality remain unverified; the word budgets are not empirically validated.
