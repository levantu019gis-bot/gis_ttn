# Epic 8 Context: Config Manager Tab

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Epic 8 adds a dedicated Config tab so the Operator can create, open, inspect, edit, validate, back up, save, and save-as project `config.json` files inside the desktop app. The aim is to make target/group/defaults/patterns/geometry maintenance safe and visible without requiring raw JSON editing as the normal workflow.

## Stories

- Story 8.1: Build Config Editor Service and Draft State
- Story 8.2: Add Config Tab Shell, Toolbar, and Status Summary
- Story 8.3: Implement Group Sidebar and Target Table
- Story 8.4: Implement Target Inspector Editing and Delete
- Story 8.5: Implement GeoJSON Import and Export for Target Geometry
- Story 8.6: Implement Defaults, Filename Patterns, and Raw JSON Views
- Story 8.7: Wire Config Validation Issues and Downstream Refresh Cues

## Requirements & Constraints

Config editing must keep persisted, draft, and validated states separate. The UI must clearly show dirty, valid, warning, and error states, and must protect reload, save, replacement, and destructive operations with confirmation where appropriate.

The editor must expose config summary metrics: target count, enabled target count, group count, unique PPTX template count, geometry count, warning count, and error count. Large configs must be browsable by group, preserving the existing group key/title and per-group `sort_order` behavior used elsewhere in the app.

Target editing must support `id`, `enabled`, `group.key`, `sort_order`, `name`, `alias`, `coordinate`, `scale`, target grid interval, export template/TXT fields, and placeholder values. Placeholder UI must show only `field` and editable `value`; it must not expose an internal id column as the primary interaction.

Geometry maintenance is intentionally narrow: the inspector must provide only `Import GeoJSON` and `Export GeoJSON`. Imported geometry is stored in `metadata.geojson_geometry`. Export should produce valid GeoJSON with a target-based filename, and missing geometry must surface as a clear issue.

Defaults and filename patterns need dedicated views. Defaults include shared grid label format/style, frame reference values, advanced grid style values, date/time formats, and map background color. Editing shared defaults must be visibly separate from per-target grid overrides. Filename pattern testing must show parsed date, parsed time, cloud percent, and make the filename-derived UTC plus 7-hour local conversion visible.

Raw JSON is read-only in the MVP. Validation issues must include severity, issue id, Vietnamese message/remediation, and context, and blocking errors must be distinguishable by text/icon as well as styling.

When saved config changes can affect Review/Edit or Export, the app should show a concise downstream refresh cue explaining what should be reloaded, re-ingested, revalidated, or preflighted.

## Technical Decisions

Config editing belongs behind `ConfigEditorService` in `src/thucthengay/config/`. PySide UI in `src/thucthengay/editor/` must not read or write config JSON directly. Save and backup operations must use atomic writes and config-relative path resolution consistent with the existing config service boundaries.

Validation should reuse existing Pydantic models and shared `Issue` patterns rather than duplicating schema logic in widgets. User-facing validation and remediation text should be Vietnamese.

Downstream Review/Edit and Export must receive saved config through existing config service boundaries. No downstream UI should parse the config JSON file directly.

## UX & Interaction Patterns

The approved layout uses top app tabs, a Config toolbar, summary stats, a left group sidebar, central workarea tabs, a right target inspector, and a bottom validation issues panel.

The target toolbar should stay narrow and include `Thêm target`. Bulk actions such as `Nhân bản`, `Đánh lại sort_order`, and `Di chuyển group` are intentionally out of scope for the MVP.

The UI should use concise labels and empty states, visible selected states that do not rely only on color, middle-elided or wrapped long paths/text where needed, stable row heights, and explicit confirmation for destructive actions. Status must not rely on color alone.

## Cross-Story Dependencies

Story 8.1 is the service foundation for the remaining UI stories. Stories 8.2 and 8.3 establish the tab shell, toolbar, summary, group sidebar, and target table that later stories extend. Story 8.4 depends on target selection from the table. Story 8.5 depends on the target inspector. Story 8.6 adds shared config section views beside target editing. Story 8.7 depends on validation data, target navigation, and save events from the earlier stories.
