# Standalone SQLite backups must not depend on WAL sidecars

- Signal: the backup API returns a file, but opening that file read-only for restore fails with a read-only database error.
- Mechanism: a connection context manager commits/rolls back but does not close the connection. A copied database retaining WAL mode can require sidecars when opened later, so the existence of the main file alone does not prove a standalone backup is usable.
- Handling: use SQLite's backup API under the store lock, set the destination to DELETE journal mode, explicitly close it, then validate/open it read-only. Preserve a separate current-state backup before restore; reject restore while asynchronous jobs are active.
- Supporting case: initial R12 restore regression failed while the destination retained WAL mode. `Store.create_backup` now closes a standalone destination; the restore roundtrip and restoring the pre-restore copy both pass in `tests/test_repairs.py::RepairTests.test_archive_reopen_and_backup_restore_preserve_recovery_copy`.
- Scope: local database contents only, not workspace files or Obsidian notes. File creation in production was verified, but production restore was deliberately not performed. Verified once in an isolated restore exercise, 2026-09-29.

## Attachments added in A1 (2026-09-29)

Original record images/PDFs now live in `material_blobs` inside the database, so SQLite backup/restore includes their bytes. State responses exclude those bytes; JSON export explicitly base64-encodes them. Restoring a pre-attachment database must re-create the empty table before further uploads. Verified once by `tests/test_workspace.py::WorkspaceTests.test_A09_save_is_distinct_from_parse_and_use_and_original_is_in_backup` and `test_restore_pre_attachment_database_recreates_blob_table`. External project workspace files and Obsidian files remain outside this backup boundary.
