# Async responses must own an input revision

## Signals and mechanism

An unsent learning question disappears after switching to materials, a successful slow request clears text entered while it was pending, or an older detail request overwrites a newer response. These have related ownership boundaries: transient components should not own topic-wide drafts, and a delayed callback cannot assume it still owns the current input or view.

## Diagnosis and handling

Keep text, selected material IDs, request IDs and draft revisions at the keyed topic workspace. A successful send clears only its submitted revision; failures keep the idempotency key unless the payload changes. Remove selections only when their material leaves the topic. For detail reads, assign a request sequence and ignore obsolete results and errors. Stop the loader on unmount, including reload attempts made by late mutation callbacks; restart it during effect setup for React Strict Mode.

## Supporting case and verification

The browser reproduced the old “type → materials → chat → empty input” path on 2026-09-29. After the repair, “chat → materials → summary → chat” retained both the question and its selected material. Deterministic cases in [learning-state.test.js](../../../tests/frontend/learning-state.test.js) cover successful/failed sends, edits while waiting, changes away and back, unlinking selected materials, reversed response order, obsolete errors and stopped/restarted loaders.

Verification: unit scenarios and the tab-switch UI path verified once. The resumed in-app browser check on 2026-09-29 held a successful send response, entered a second question, and verified the second question survived. A simulated HTTP 503 retained that input; retry produced one saved question and then cleared the composer. Page identity, screenshot, DOM and console checks passed with fixed offline Agent replies. The earlier browser restoration blocker is resolved. This pattern was first applied to the learning workspace. The global workspace snapshot path is covered by the extension below; other editors still require their own draft-lifetime checks.

## Applicability limits

The draft lives in the mounted topic workspace; navigating to another topic, reloading, or exiting the app does not persist it. Request sequencing does not prove server-side write ordering or solve retries for non-idempotent APIs. These require separate acceptance criteria.

## Global snapshots and overlapping writes

The follow-up browser test reproduced a saved record appearing and then disappearing when a pre-save poll returned; SQLite still contained the record. A later poll can hide this regression quickly, so release the captured response before the next poll and check the named item immediately. Do not restore unsafe code merely to reproduce it.

The global coordinator in [workspaceRequests.js](../../../src/workspaceRequests.js) invalidates reads when a mutation starts. A single mutation can publish its response directly. When writes overlap, neither launch order nor response order establishes which snapshot is newest: wait for all writes to settle, then read once. Skip background reads while writes are pending. A failed reconciliation read returns a warning without converting the completed write into a failure or repeating it. Track outstanding operations independently, and cancel notification timers when their notice changes. Summary autosave uses the same coordinator while retaining local error handling.

Verified once in 8 deterministic cases in [workspace-requests.test.js](../../../tests/frontend/workspace-requests.test.js), plus browser flows for old-poll replay, overlapping record/state writes, persistent error notification, quiet summary autosave, and summary revision conflict preserving typed input. The global strategy intentionally defers visible snapshots during overlapping writes. Its coverage is one mounted app instance; it does not establish distributed write ordering or persist unsent drafts across restarts.
