# Epic 9 Context: Historical Image Registry and Temporal Compare View

<!-- Compiled from planning analysis and Epic 9 requirements. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Epic 9 adds two related capabilities:

1. An optional SQLite-backed historical image registry so the Operator can reuse imagery that was previously included for a target in older workspaces.
2. A Review/Edit temporal comparison mode that can split the map frame into two panes and render two selected time points for the same target.

The Operator must have two clear historical loading modes:

- `Không tải ảnh lịch sử`: keep the current workspace-only ingestion/review/render/export behavior.
- `Tải ảnh lịch sử`: query the historical registry, load eligible historical images into the current workspace cache, and expose them for review/comparison.

Workspace JSON remains the source of truth for the current session. SQLite is a long-lived reference registry, not a replacement for `WorkspaceService` or composition JSON.

## Stories

- Story 9.1: Add SQLite History Service and Registry Schema
- Story 9.2: Record Included Compositions into History
- Story 9.3: Configure Historical Loading Mode for Ingestion
- Story 9.4: Load Historical Imagery into New Workspace Ingestion
- Story 9.5: Validate and Repair Historical Image Paths
- Story 9.6: Surface Historical Imagery Status in Review/Edit and Ingest Summary
- Story 9.7: Add Temporal Compare Controls in Review/Edit
- Story 9.8: Render and Export Split Map Frame for Temporal Comparison

## Requirements & Constraints

The historical registry is optional and must not change current behavior when disabled. When enabled, it stores included target imagery across workspaces: target identity, capture date/time, cloud percent, source paths, workspace/composition provenance, and inclusion timestamps.

Historical loading must be explicit. When disabled, ingestion must not query SQLite and must create the same current-session compositions as today. When enabled, historical loading should be configurable by target scope:

- `targets_with_current_matches`: default; load history only for targets that matched at least one current-session image.
- `all_enabled_targets`: explicitly load history for every enabled target.

Historical loading should also be configurable by image selection:

- `latest_date`: load all historical images from each target's latest capture date.
- `latest_images`: load newest N historical images per target.
- `date_range`: load historical images inside an inclusive date range.
- `lookback_days`: load historical images inside a lookback window anchored to today or the current session latest capture date.

Historical and current-session imagery must be deduplicated before composition creation. A historical image already present in current-session matches should appear only once for the same target/date.

Historical image paths must be validated before being added to workspace cache. Missing or unreadable paths create structured issues with Vietnamese message/remediation and must not silently disappear.

## Temporal Compare Design

Comparison mode belongs in Review/Edit and is per selected composition/target. It must not affect the existing single-map workflow when disabled.

Controls should stay close to the GIS canvas:

```text
[ ] So sánh 2 thời điểm    Kiểu chia: [Dọc: Trái/Phải] [Ngang: Trên/Dưới]

Khung A: [date/time | current/historical | cloud] [chọn ảnh...]
Khung B: [date/time | current/historical | cloud] [chọn ảnh...]
```

When comparison mode is enabled:

- `vertical` orientation means left/right panes.
- `horizontal` orientation means top/bottom panes.
- Pane A and Pane B options are selected from the current target's current-session and loaded historical imagery.
- Each option must show target, capture date/time, source kind, cloud percent where available, and missing/unreadable status where relevant.
- Fewer than two usable images should produce an informational UI state, not block normal single-map review when comparison is off.

MVP scope should compare the same target at two time points. Cross-target comparison should be deferred unless a later story explicitly requires it.

## Technical Decisions

Add a core module such as `src/thucthengay/history/` with a `HistoryService` as the only SQLite access boundary. PySide UI must not query or mutate SQLite directly.

Use Python's built-in `sqlite3`, schema migrations, transactions, parameter binding, foreign keys, and short write operations. WAL mode is acceptable only for local database files; do not force WAL when the configured database path is on a network share.

Keep workspace isolation: historical images that are available should be copied into the current workspace cache before review/render/export, consistent with the existing cache/composition pipeline.

Recommended registry tables:

- `schema_version`
- `target_history`
- `image_asset`
- `target_image_history`
- `include_event`

History should be recorded only after a composition passes validation and is included. Skipped compositions and failed validation attempts must not create included-history entries.

Comparison state should be persisted through workspace-owned models/services, not UI-only state. Expected state fields:

- `comparison.enabled`
- `comparison.orientation`: `vertical` or `horizontal`
- `comparison.pane_a.layer_id`
- `comparison.pane_b.layer_id`
- optional pane labels/metadata derived from selected layers

Render business logic must remain outside PySide widgets. Comparison rendering should extend render/model service boundaries so Review/Edit preview and final export use the same comparison state.

## Integration Points

Current ingestion pipeline:

```text
scan_imagery_folder
-> match_imagery_to_targets
-> populate_workspace_cache
-> create_target_date_compositions
```

Epic 9 target pipeline when historical loading is enabled:

```text
scan current imagery
-> match current imagery
-> load historical imagery for configured target scope and image selection
-> validate/repair historical paths
-> merge and dedupe current + historical imagery
-> copy available historical/current imagery into workspace cache
-> create target-date compositions
```

Review include flow should eventually be orchestrated through a service boundary:

```text
validate composition
-> workspace.apply_include_transition
-> history.record_included_composition
```

If history recording fails after workspace include succeeds, the workspace include remains valid and the UI surfaces a non-blocking warning.

Comparison render/export flow:

```text
read composition comparison state
-> validate selected pane layers
-> build single-map render spec when comparison is disabled
-> build comparison render inputs when enabled
-> render split map frame for preview/final output
-> export PPTX using the same final map image
```

## UX & Interaction Patterns

Ingest summary should show current images scanned, current images matched, historical images loaded, historical images skipped, and historical path issues.

Review/Edit layer rows should distinguish current-session and historical layers using text/icon indicators, not color alone.

Warnings panel should show missing/unreadable historical paths with target/composition/layer context and a repair action where available.

Path repair should support:

- single-file replacement
- bulk old-prefix to new-prefix replacement with preview and explicit confirmation

If no historical images match the configured target scope and image selection, this should be an informational result, not a blocking error.

Comparison controls should be dense and operational: avoid a wizard, avoid a large marketing/help panel, and keep normal Include/Validate visible. Pane labels are required because the exported comparison image must remain understandable without relying on color.

## Cross-Story Dependencies

Story 9.1 creates the service/schema foundation. Story 9.2 depends on the service and review include flow. Story 9.3 makes historical loading explicit and gates the rest of ingestion behavior. Story 9.4 depends on service queries and ingestion/cache/composition integration. Story 9.5 depends on historical loading and shared Issue patterns. Story 9.6 depends on metadata surfaced by Stories 9.4 and 9.5. Story 9.7 depends on loaded current/historical layer metadata and workspace persistence. Story 9.8 depends on Story 9.7 comparison state and the render/export boundaries from Epics 5-7.
