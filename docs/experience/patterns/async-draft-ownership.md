# Async responses must own an input revision

## Signals and mechanism

An unsent learning question disappears after switching to materials, a successful slow request clears text entered while it was pending, or an older detail request overwrites a newer response. These have related ownership boundaries: transient components should not own topic-wide drafts, and a delayed callback cannot assume it still owns the current input or view.

## Diagnosis and handling

Keep text, selected material IDs, request IDs and draft revisions at the keyed topic workspace. A successful send clears only its submitted revision; failures keep the idempotency key unless the payload changes. Remove selections only when their material leaves the topic. For detail reads, assign a request sequence and ignore obsolete results and errors. Stop the loader on unmount, including reload attempts made by late mutation callbacks; restart it during effect setup for React Strict Mode.

## Supporting case and verification

The browser reproduced the old “type → materials → chat → empty input” path on 2026-09-29. After the repair, “chat → materials → summary → chat” retained both the question and its selected material. Deterministic cases in [learning-state.test.js](../../../tests/frontend/learning-state.test.js) cover successful/failed sends, edits while waiting, changes away and back, unlinking selected materials, reversed response order, obsolete errors and stopped/restarted loaders.

Verification: unit scenarios and the tab-switch UI path verified once. Browser delayed-send and failure-retry checks were interrupted and then blocked during browser restoration; do not infer those UI paths passed from reducer tests alone. This pattern is applied to the learning workspace, not to every other async editor in the application.

## Applicability limits

The draft lives in the mounted topic workspace; navigating to another topic, reloading, or exiting the app does not persist it. Request sequencing does not prove server-side write ordering or solve retries for non-idempotent APIs. These require separate acceptance criteria.
