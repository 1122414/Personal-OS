# Agent result text is not file evidence

- Signals: Codex reports file creation or modification, while the Task and Review pages say no separate artifact exists.
- Mechanism: an Agent's natural-language result is stored on `AgentRun` and `Task`, but does not populate `Artifact` or `ArtifactCreated` events by itself.
- Diagnosis: compare the reported path with the actual workspace, then inspect `agent_run`, `artifact`, and activity records. A valid result summary does not prove that a file changed.
- Handling: capture a bounded file metadata snapshot before and after each run, record created/modified/deleted files as artifacts, and show them next to the Agent result before approval. Treat the snapshot as evidence to inspect, not proof that the changes are correct.
- Limits: hidden paths, dependency/build directories, and workspaces over 20,000 visible files may be incomplete. A file modified and restored with the same size and timestamp can also evade this comparison.
- Supporting case: the 2026-09-23 browser acceptance run created `hello.txt`, but Review showed no artifact. A subsequent run modified that file; the updated Review showed `hello.txt · 修改 · 待审核`, and approval changed its status.
- Verification: `tests/test_store.py::StoreTests.test_agent_result_waits_for_user_review` and the isolated browser acceptance run; verified once.

## Failure-path counterexample (2026-09-29)

The [project audit](../../2026-09-29_project-audit-and-first-use.md), R04, re-ran the existing successful-run test and separately simulated a process that creates a visible file and then exits with code 1. The file existed and the task became Blocked, but no Artifact was recorded. At baseline `5205d68`, `Store._run_codex` only compares snapshots on success; cancellation/interruption can also return before that comparison.

The successful-run method remains useful but is not complete coverage of execution evidence. Inspect the real workspace even when a run failed or was canceled. A future repair should collect evidence for all terminal states after the process has stopped, retaining failure status and accounting for concurrent changes. The failure-path defect was verified once; cancellation/interruption omissions are code-based inferences here, not independently reproduced runs. No repair was applied in the audit.

## Repair verification (2026-09-29)

The repair persists the baseline on AgentRun and collects evidence after process termination on both success and error paths. Startup recovery collects missing evidence once and explicitly labels it as recovered, because other changes may have occurred since interruption. Overlapping workspaces cannot run concurrently inside this application. This does not prevent edits by external tools.

`tests/test_repairs.py` now covers failed/canceled processes, timeout, and restart after Running/Canceled records, alongside existing successful and client-close tests. All passed in the repair validation; these are simulated subprocesses and isolated workspaces, not evidence of a real cloud model's correctness. The old failure-path omission is repaired; metadata snapshot limitations still apply.
