# Story 9.1: Add SQLite History Service and Registry Schema

Status: review

## Story

As an Operator,
I want the app to remember included target imagery across workspaces,
so that future workspaces can reuse relevant historical images without manually searching old folders.

## Acceptance Criteria

1. Given historical registry is enabled in config, when `HistoryService` opens the configured SQLite database, then it creates or migrates the schema for target history, image assets, target-image links, include events, and schema version, and all writes run inside transactions with SQLite parameter binding.
2. Given historical registry is disabled or no database path is configured, when ingestion/review runs, then the app continues to behave exactly like the current workspace-only workflow, and no SQLite file is created implicitly outside the configured/default project data location.
3. Given the database is located on a network share, when the service initializes SQLite pragmas, then WAL mode is not forced, and the service uses short transactions, `foreign_keys=ON`, and a busy timeout.
4. Given core modules need registry access, when they load or record history, then they call `HistoryService`, and PySide UI widgets do not query or mutate SQLite directly.

## Tasks / Subtasks

- [x] Add history config schema without changing default behavior (AC: 2)
  - [x] Add optional historical registry config fields to `ProjectConfig` with safe disabled defaults.
  - [x] Keep config validation headless and JSON fields in `snake_case`.
  - [x] Add model tests for enabled/disabled/default config behavior.
- [x] Add SQLite history service boundary and schema migration (AC: 1, 3, 4)
  - [x] Create `src/thucthengay/history/` with `HistoryService` and public package exports.
  - [x] Implement schema creation/migration for `schema_version`, `target_history`, `image_asset`, `target_image_history`, and `include_event`.
  - [x] Use `sqlite3`, parameter binding, transactions, `PRAGMA foreign_keys=ON`, and busy timeout.
  - [x] Do not import PySide6 or `thucthengay.editor` from the history module.
- [x] Implement disabled/no-path behavior (AC: 2)
  - [x] Provide a no-op/disabled construction path that does not create a database file.
  - [x] Ensure opening requires an explicit configured path when enabled.
  - [x] Add tests proving disabled/no-path paths do not create SQLite files.
- [x] Add focused tests and boundary guards (AC: 1, 3, 4)
  - [x] Test schema is created and idempotent across repeated initialization.
  - [x] Test foreign key enforcement and transaction rollback on write failure.
  - [x] Test WAL is not forced for network-share paths.
  - [x] Add/import-boundary test preventing UI dependencies in `history`.

## Dev Notes

### Scope

Story 9.1 is only the foundation. Do not record included compositions yet, do not query history during ingestion, do not modify Review/Edit UI, and do not add comparison rendering. Those are Stories 9.2 through 9.8.

### Architecture Requirements

- Add a core module: `src/thucthengay/history/`.
- `HistoryService` is the only SQLite access boundary. Core modules will call it in later stories.
- PySide UI must not query or mutate SQLite directly.
- Workspace JSON remains the source of truth for the current session. SQLite is a long-lived reference registry only.
- Use Python stdlib `sqlite3`; do not add dependencies.
- Use short transactions and parameter binding. Do not build SQL from user values.
- Do not force WAL mode. WAL may be added later only behind a local-file decision; for this story, keep journal mode default/delete-safe and verify no `PRAGMA journal_mode=WAL` is issued.

### Proposed Config Contract

Add an optional project-level config object, default disabled:

```json
{
  "historical_registry": {
    "enabled": false,
    "database_path": null
  }
}
```

Rules:

- Missing `historical_registry` means disabled.
- `enabled=false` with no path is valid and must not create a DB.
- `enabled=true` requires `database_path`.
- Paths remain config-relative when later resolved by config/service code. This story may keep the model as a string and let service callers pass a resolved `Path`.

### Schema Contract

Minimum tables:

- `schema_version`: one row tracking integer schema version.
- `target_history`: stable target identity fields such as `target_id`, `target_name`, `target_alias`, created/updated timestamps.
- `image_asset`: image identity and metadata such as source path, cache path/provenance path, capture date/time, cloud percent, created/updated timestamps.
- `target_image_history`: link table for target-to-image association, latest include metadata, unique target/image pair.
- `include_event`: append-only trace of include events with workspace path, composition id, target/image link, included timestamp.

Keep column names `snake_case`. Prefer ISO text for timestamps/dates/times for inspectability.

### Existing Code Patterns To Preserve

- Models live in `src/thucthengay/models/` and use Pydantic v2 with `ConfigDict(extra="forbid")`.
- Project config is loaded through `src/thucthengay/config/service.py`; UI does not parse config JSON directly.
- Core modules must not import `PySide6` or `thucthengay.editor`.
- Tests belong in `tests/unit/` and should not require real GeoTIFFs, GUI event loops, network, or LAN paths.
- Default commands: `conda run -n ttn-env python -m pytest ...` and `conda run -n ttn-env ruff check ...`.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 9, Story 9.1 and HIR-FR1/HIR-FR2/HIR-AR1/HIR-AR2.
- `_bmad-output/implementation-artifacts/epic-9-context.md` - Epic 9 technical decisions and cross-story dependencies.
- `_bmad-output/project-context.md` - module ownership, config/workspace boundaries, testing rules.
- `_bmad-output/planning-artifacts/architecture.md` - layered architecture and core/UI boundary rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `conda run -n ttn-env python -m pytest tests\unit\test_models.py tests\unit\test_history_service.py -q`
- `conda run -n ttn-env python -m pytest tests\unit -q`
- `conda run -n ttn-env python -m pytest -q`
- `conda run -n ttn-env ruff check .`
- `conda run -n ttn-env python -m thucthengay --smoke`

### Completion Notes List

- Added optional `historical_registry` config object with disabled default and validation requiring `database_path` when enabled.
- Added `HistoryService` as the SQLite access boundary with no-op disabled mode, explicit database initialization, schema versioning, and idempotent schema creation.
- Created registry tables for target history, image assets, target-image links, include events, and schema version using short SQLite transactions.
- Set required connection pragmas (`foreign_keys=ON`, `busy_timeout`) without forcing WAL mode.
- Added tests for config defaults/validation, schema idempotency, foreign-key enforcement, transaction rollback, no-op disabled behavior, non-WAL journal mode, and UI import boundaries.

### File List

- `src/thucthengay/history/__init__.py`
- `src/thucthengay/history/service.py`
- `src/thucthengay/models/__init__.py`
- `src/thucthengay/models/config.py`
- `tests/unit/test_history_service.py`
- `tests/unit/test_models.py`

## Change Log

- 2026-06-09: Created story context for implementation.
- 2026-06-09: Implemented Story 9.1 SQLite history registry schema and service boundary; status moved to review.
