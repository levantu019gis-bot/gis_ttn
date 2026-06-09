# Story 9.3: Configure Historical Loading Mode for Ingestion

Status: review

## Story

As an Operator,
I want an explicit choice to load or not load historical images,
so that I can keep the current simple workflow or opt into historical comparison deliberately.

## Acceptance Criteria

1. Given historical loading is disabled, when ingestion runs, then the app scans and matches only current-session imagery, no historical registry query is executed, and Review/Edit, render, export, and validation behave like the current workspace-only workflow.
2. Given historical loading is enabled, when ingestion starts, then the app displays or applies the configured target scope and image selection settings before querying history.
3. Given no historical database path is configured, when the Operator enables historical loading, then the app reports a clear validation issue or setup message and does not silently fall back to an unknown database location.
4. Given the historical loading mode is changed in config or setup UI, when downstream code reads the setting, then it receives the saved value through config/service boundaries and no PySide widget reads or writes config JSON directly.

## Tasks / Subtasks

- [x] Add historical loading config schema with safe defaults (AC: 1, 2, 4)
  - [x] Add project-level `historical_loading` config with `enabled=false` default.
  - [x] Add target scope values `targets_with_current_matches` and `all_enabled_targets`.
  - [x] Add image selection settings for `latest_date`, `latest_images`, `date_range`, and `lookback_days`.
  - [x] Keep persisted field names `snake_case` and reject unknown fields through Pydantic.
- [x] Validate database-path requirements through config service boundary (AC: 3, 4)
  - [x] Resolve configured registry database paths relative to `config.json` without checking JSON directly from UI.
  - [x] When historical loading is enabled but registry/path is missing, return a blocking Vietnamese config issue.
  - [x] Do not create or guess any database path during config validation.
- [x] Gate ingestion historical behavior behind a service-friendly plan (AC: 1, 2)
  - [x] Build a historical loading plan from config, matching results, target scope, and image selection.
  - [x] Ensure disabled historical loading never calls a historical loader/query hook.
  - [x] Emit an explicit progress/setup message for disabled and enabled modes.
  - [x] Leave actual historical image loading/copy/merge to Story 9.4.
- [x] Add focused tests and regressions (AC: 1, 2, 3, 4)
  - [x] Test config defaults preserve current workspace-only behavior.
  - [x] Test valid/invalid image selection config combinations.
  - [x] Test config service returns a blocking issue when loading is enabled without a registry database path.
  - [x] Test ingestion does not call the historical loader when disabled.
  - [x] Test ingestion builds and passes the expected plan when enabled.

## Dev Notes

### Scope

Story 9.3 is the configuration and ingestion gate only. Do not query SQLite directly from ingestion, do not copy historical imagery into workspace cache, do not merge historical layers into compositions, and do not add temporal compare UI. Those are Stories 9.4 through 9.8.

### Architecture Requirements

- Keep `ProjectConfig` as the persisted schema owner for project-level historical loading settings.
- Keep path resolution and validation in `config/service.py`; PySide widgets must not parse or write `config.json`.
- Keep ingestion orchestration in `jobs/ingestion_job.py`; lower-level ingestion modules should remain focused on scan/match/cache/composition.
- If a future historical query is needed, ingestion should call a service-friendly hook/plan rather than importing SQLite or reaching around `HistoryService`.
- Current behavior must remain unchanged when `historical_loading.enabled=false`.

### Proposed Config Contract

Add a separate project-level object:

```json
{
  "historical_registry": {
    "enabled": false,
    "database_path": null
  },
  "historical_loading": {
    "enabled": false,
    "target_scope": "targets_with_current_matches",
    "image_selection": {
      "mode": "latest_date"
    }
  }
}
```

Mode-specific validation:

- `latest_date`: no extra selector value is required.
- `latest_images`: `limit_per_target` is required and must be positive.
- `date_range`: `start_date` and `end_date` are required and `start_date <= end_date`.
- `lookback_days`: `lookback_days` is required and must be positive; anchor can be `today` or `current_session_latest_date`.

### Existing Code Patterns To Preserve

- `ConfigLoadResult` already carries config, enabled targets, resolved target paths, template metadata, and issues.
- `run_ingestion_job()` currently owns the high-level pipeline: scan current imagery, match targets, populate cache, create compositions.
- Progress messages are plain `ProgressEvent` objects and are safe for the Setup UI to display without UI reading config JSON.
- Story 9.1 introduced `HistoricalRegistryConfig`; Story 9.3 should not overload that field with ingestion-mode semantics.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 9, Story 9.3 and HIR-FR2/HIR-FR3/HIR-FR4/HIR-FR9/HIR-UX3.
- `_bmad-output/implementation-artifacts/epic-9-context.md` - historical loading modes and target/image selection design.
- `_bmad-output/implementation-artifacts/9-1-add-sqlite-history-service-and-registry-schema.md` - registry service/schema foundation.
- `_bmad-output/implementation-artifacts/9-2-record-included-compositions-into-history.md` - previous history service integration pattern.
- `src/thucthengay/models/config.py` - project config schema.
- `src/thucthengay/config/service.py` - config loading, path resolution, and structured issues.
- `src/thucthengay/jobs/ingestion_job.py` - ingestion orchestration and progress events.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `conda run -n ttn-env python -m pytest tests\unit\test_models.py tests\unit\test_config_service.py tests\unit\test_ingestion_job.py -q`
- `conda run -n ttn-env python -m ruff check src\thucthengay\models\config.py src\thucthengay\models\__init__.py src\thucthengay\config\service.py src\thucthengay\history src\thucthengay\jobs\ingestion_job.py tests\unit\test_models.py tests\unit\test_config_service.py tests\unit\test_ingestion_job.py`
- `conda run -n ttn-env python -m pytest -q`
- `conda run -n ttn-env python -m ruff check .`
- `conda run -n ttn-env python -m thucthengay --smoke`

### Completion Notes List

- Story context created from Epic 9 requirements and existing 9.1/9.2 implementation patterns.
- Added `historical_loading` config schema with explicit disabled default, target scope, selection modes, and mode-specific validation.
- Config service now resolves `historical_registry.database_path` relative to config and returns a blocking Vietnamese issue when loading is enabled without a configured registry database path.
- Added `HistoricalLoadingPlan`/`HistoricalLoadingResult` as service-friendly ingestion contracts for Story 9.4.
- Ingestion now emits explicit historical-mode progress messages, never calls a historical loader when disabled, and passes a resolved plan when enabled.

### File List

- `_bmad-output/implementation-artifacts/9-3-configure-historical-loading-mode-for-ingestion.md`
- `src/thucthengay/config/service.py`
- `src/thucthengay/history/__init__.py`
- `src/thucthengay/history/loading.py`
- `src/thucthengay/jobs/ingestion_job.py`
- `src/thucthengay/models/__init__.py`
- `src/thucthengay/models/config.py`
- `tests/unit/test_config_service.py`
- `tests/unit/test_ingestion_job.py`
- `tests/unit/test_models.py`

## Change Log

- 2026-06-09: Created story context for implementation.
- 2026-06-09: Implemented historical loading config and ingestion gate; status moved to review.
