# Materialized context can outlive its source facts

## Signals and mechanism

A task completion counter disagrees with the Daily Log body, a saved Morning Brief still recommends a completed task, or Project Pulse remains unchanged after progress. Persisting generated text does not keep it synchronized with the events and objects from which it was generated.

In the reviewed implementation, `Store.draft_log` returns the existing draft unless explicitly asked to regenerate, `Store.brief` returns stored priorities without revalidating task state, and `daily_automation` only generates a pulse when the project has no pulse. A related provenance problem is that `generate_brief` labels the latest available log as `yesterday_log` without requiring a past date or confirmation.

## Diagnosis and handling

1. Check event/object facts separately from their generated summaries. Preserve a user-edited draft during diagnosis.
2. Exercise the order “generate → mutate source facts → read/confirm,” in addition to the normal “finish work → generate” path.
3. Capture model input with a stub to verify dates, confirmation state, and excluded objects without sending real user context to a model.
4. For a future fix, define a source version or event watermark and an explicit stale-state/refresh policy. Revalidate brief task eligibility at use time. Choose prior confirmed logs explicitly and retain their dates.
5. Do not silently regenerate over manual edits or sealed logs. Test preservation of edits, late events, and date boundaries before claiming a fix.

## Supporting case and limits

The [2026-09-29 project audit](../../2026-09-29_project-audit-and-first-use.md), R01 and R02, reproduced a History counter of one completed task while its draft still said none and listed that task as unfinished. A temporary Store fixture returned a Done task in its saved brief; confirmation rejected it. Captured generation input used a current-day unconfirmed draft as `yesterday_log`.

These are verified-once defects at code baseline `5205d68`, not repaired behavior. Project Pulse staleness was verified by inspecting its generation condition, not by a multi-day experiment. Existing `tests/test_store.py::StoreTests.test_daily_loop_persists_and_generates_from_events` covers the normal ordering but does not cover late events. Shared symptoms alone do not justify applying the same remedy to every cached value; plans and sealed records have different ownership rules.

## Repair verification (2026-09-29)

The repaired Daily Log stores source event IDs, refuses stale confirmation, preserves old drafts in revisions, and checks that manual acknowledgement refers to the exact event set the user saw. The brief filters current task eligibility and ignored intelligence, while model input selects a confirmed log from before today with its date. Project Pulse has a generated timestamp/stale flag; automatic regeneration is bounded to one daily attempt and preserves manual text.

Validated by `tests/test_repairs.py` (late events, concurrent events during edit, prior confirmed context, ignored intelligence, and pulse staleness) plus an isolated browser sequence. This is verified once per repair scenario; multi-day/sleep behavior remains unverified. New source events after a sealed log do not authorize rewriting that sealed text.
