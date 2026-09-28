# Experience index

| Mechanism | Applicability signals | Validation | Entry |
|---|---|---|---|
| Separate product identity from a personal theme | Interpreting 博士, Skadi artwork, theme copy, or user-provided mockups as universal product requirements | User clarification confirmed once, 2026-09-23 | [Personalization boundaries](patterns/personalization-boundaries.md) |
| Agent result text is not file evidence | Agent says it changed files, or a failed run leaves files, but Review has no artifact row | Success, failure, cancellation, timeout and restart tests passed 2026-09-29; metadata limits remain | [Agent artifact evidence](patterns/agent-artifact-evidence.md) |
| Python bytecode changes a signed app bundle | A bundled Python service runs, then `codesign --verify` fails | Rebuilt and verified before and after native launch, 2026-09-23 | [Bundled Python signature](patterns/bundled-python-signature.md) |
| Nested minimum heights can restore whole-window scrolling | Desktop shell grows beyond the window despite a fixed sidebar | Native window visual check verified once, 2026-09-23 | [Fixed window layout](patterns/fixed-window-layout.md) |
| Materialized context outlives source facts | Daily Log disagrees with completion events; saved Brief includes Done tasks; latest log is mislabeled as yesterday | Repaired and verified in isolated tests/UI 2026-09-29; multi-day runtime not yet tested | [Materialized context freshness](patterns/materialized-context-freshness.md) |
| SQLite backup retains WAL requirements | A created backup fails when opened read-only for restore | Isolated roundtrip and reverse restore verified once, 2026-09-29 | [Standalone SQLite backup](patterns/sqlite-standalone-backup.md) |
| External source and user state have different ownership | Batch import orders old records first or overwrites concurrent feedback | Fixture tests and real WorkBuddy 5.6.2 import verified once, 2026-09-29 | [External session import](patterns/external-session-import.md) |
