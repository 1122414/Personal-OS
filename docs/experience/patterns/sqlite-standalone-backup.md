# Standalone SQLite backups must not depend on WAL sidecars

- Signal: the backup API returns a file, but opening that file read-only for restore fails with a read-only database error.
- Mechanism: a connection context manager commits/rolls back but does not close the connection. A copied database retaining WAL mode can require sidecars when opened later, so the existence of the main file alone does not prove a standalone backup is usable.
- Handling: use SQLite's backup API under the store lock, set the destination to DELETE journal mode, explicitly close it, then validate/open it read-only. Preserve a separate current-state backup before restore; reject restore while asynchronous jobs are active.
- Supporting case: initial R12 restore regression failed while the destination retained WAL mode. `Store.create_backup` now closes a standalone destination; the restore roundtrip and restoring the pre-restore copy both pass in `tests/test_repairs.py::RepairTests.test_archive_reopen_and_backup_restore_preserve_recovery_copy`.
- Scope: local database contents only, not workspace files or Obsidian notes. File creation in production was verified, but production restore was deliberately not performed. Verified once in an isolated restore exercise, 2026-09-29.
