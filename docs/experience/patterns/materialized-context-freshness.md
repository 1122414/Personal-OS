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

## Workspace recall extension (2026-09-29)

The weekly review is also a materialized view. `server/recall.py` rechecks record content, feedback and currently active personal states before showing a stored candidate; age and cooldown filters run before the final three-item cap. An ended or expired state stops influencing fresh advice, while the state snapshot stored on an earlier assistant response remains historical evidence. `tests/test_recall.py` verifies these boundaries, including edits after review generation, no-new-project filtering, and an expired state leaving a confirmed plan untouched. These deterministic cases are verified once; long-term recommendation usefulness is not established.

## Empty-cache and historical-source boundaries (2026-09-29)

Maintenance regressions exposed two distinct cache boundaries: `recall_tick` treated an empty eligibility check as the week's completed review, while summary generation reconstructed record context from currently linked records instead of the versions stored on messages. Empty review rows can now be filled in place when eligible material appears; nonempty rows remain sealed even after feedback hides all items. Summary snapshots now retain historical record versions before adding current records, distinguish user text from imported sources, and version the source contract so old reports become stale without overwriting manual sections.

Verified once by `test_empty_week_can_later_generate_but_handled_review_is_not_refilled`, `test_legacy_empty_review_is_filled_in_place`, `test_summary_retains_record_snapshot_after_edit_and_unlink`, and `test_historical_import_is_not_user_intent_and_clipping_is_visible`. The summary context budget still bounds how much raw history can be supplied; this repair does not imply unlimited recall.
