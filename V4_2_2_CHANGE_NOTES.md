# v4.2.2 Change Notes

## JSON -> PostgreSQL target safety

- `PostgreSQL Settings` is now the only source of truth for JSON import target scope/database.
- The JSON import page shows a read-only target summary: Scope, Database, and Host.
- No second 21MM / 24MM / Common selector was added to the JSON import page.
- Batch preflight checks every selected JSON `project_code` before PostgreSQL writes.
- Mixed-scope batches are rejected before any file is imported.
- 21MM / 24MM reject JSON without `project_code`.
- Common accepts legacy generic JSON without `project_code` and assigns `COMMON` during import.
- The worker performs full JSON/model validation for the whole batch before entering the write phase.
- PostgreSQL writes use an explicit connection built from the current visible Settings fields, so the current Settings database is the actual import target even before saving the config file.
- Existing `project_info` storage guard remains active and rejects a manually selected wrong database.

No database schema change is included in v4.2.2.
