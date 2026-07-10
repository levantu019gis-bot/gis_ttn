---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/prds/prd-3.ThucTheNgay-2026-05-23/prd.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/architecture.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/ux-design-specification.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/config-manager-tab-design.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/config-manager-ui-mockup.html
  - D:/0.TU_KHONG_XOA/1.NCPT/1.TTN/0.Download_Img/download_satellite_images_by_geojson.py
  - D:/0.TU_KHONG_XOA/1.NCPT/1.TTN/0.Download_Img/satellite_download_config.json
---

# 3.ThucTheNgay - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for 3.ThucTheNgay, decomposing the requirements from the PRD, UX Design, and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Load target config JSON with enabled targets, view/grid/export/template settings, and GeoJSON paths; report unreadable or invalid required fields; only ingest enabled targets; sort targets by `sort_order`.

FR2: Allow Operator to select imagery input folder local/LAN and workspace folder; display selected paths before ingestion; require explicit confirmation before clearing existing workspace/cache/compositions/renders/exports.

FR3: Recursively scan GeoTIFF imagery, parse PlanetScope-style filename metadata, check intersection with each target GeoJSON boundary, copy matching imagery into target cache, preserve cloud percent as display metadata, and mark unparsed metadata for manual correction.

FR4: Create one composition JSON for each target-date with matched images; split multi-date target imagery into separate compositions; initialize new compositions as reviewed=false, ready=false, include=false; default layer order newest on top.

FR5: Show ingestion progress with scanned image count, matched image count, targets with images, warning count, current target, and matched count for current target; surface ingest warnings in summary/warnings UI.

FR6: Maintain workspace structure containing manifest.json, cache/, compositions/, renders/, and exports/; use `WorkspaceService` as source of truth for composition/status/review_order/validation_summary.

FR7: Persist composition status fields reviewed, ready, include, review_order, notes; enforce right/up/left review state transitions exactly as PRD defines.

FR8: Persist validation summary only in composition JSON; recompute detailed issues when selecting, reviewing, or exporting; mark composition needs_revalidation after layer/view/grid/metadata changes.

FR9: Provide Review/Edit target-composition tree with queue filters: Tất cả, Chưa duyệt, Ready, Include, Có warning, Có error; show status/issue indicators and aggregate counts.

FR10: Show/edit layer stack with visibility, order, timestamp/cloud/status; persist layer order; compute time label from visible/selected valid layers; produce validation error when no layer is visible.

FR11: Provide GIS editor for pan/zoom under fixed map frame; initialize view from target coordinate and scale; persist source-of-truth view center/scale; keep rotation at 0 without MVP UI; support mouse wheel zoom and optional zoom slider.

FR12: Allow per-composition grid interval override using DMS fields; default from target config; persist override in composition without changing target config; use configured label format default dms_full.

FR13: Show slide preview that updates when view/layer/grid/metadata changes; use debounce/cache to avoid lag; keep preview close to final export for center/scale, layer order, grid, and background.

FR14: Support manual metadata correction for layer capture date/time; persist metadata_status/source; confirm file move when edited date changes cache folder; block ready until metadata can produce time label.

FR15: Render map output from composition state, target config, target PPTX map-frame bounds, and output size; use view center/scale, visible layer order, coordinate frame labels, background, map frame aspect; derive the raster read window from center/scale and map-frame physical size; do not render boundary/north arrow/scale bar in MVP; record final PNG width/height in render log.

FR16: Provide hybrid preview/final render pipeline; two-stage GIS preview with interactive low-res and settled high-res; final render at template output quality; ignore/cancel stale render jobs; first slice must keep preview/final aligned on center/scale/layer/grid.

FR17: Produce structured Issue objects with issue_id, severity, scope, target/composition/layer refs, Vietnamese message/remediation, and blocking flag; severity=error blocks ready/export.

FR18: Validate when selecting composition, when pressing right arrow/include, and during export preflight; failed right-arrow validation must not set ready/include or move to next composition.

FR19: Surface issues in tree/layer UI and Warnings panel; support navigation from aggregate issue to related target/composition/layer.

FR20: Load target-specific one-slide PowerPoint template directly from target config; config includes template_pptx_file and PPTX shape-id replacement mapping for map frame and text/image placeholders; template missing/invalid or unresolved required shape ids are blocking errors.

FR21: Export one combined PPTX from included compositions sorted by review_order; each composition copies the only slide from its target-specific PPTX template; target templates must share compatible base/theme/master where required by the copy implementation; replace map image/text placeholders by configured PPTX element ids.

FR22: Export TXT with one line per included composition using configured txt_line_template; time label from visible valid layers; unresolved required placeholders are validation errors; optional fields render empty only when marked optional.

FR23: Show export summary and write logs next to output; summary includes slide count, target count, skipped, warnings, output paths; log maps compositions exported/skipped and issue summary.

### NonFunctional Requirements

NFR1: Editor interactions with large GeoTIFFs must remain responsive using cache/downsample and two-stage render; exact latency targets are calibrated with real imagery.

NFR2: Workspace writes must avoid corrupting composition JSON; failed writes must not leave partial invalid JSON.

NFR3: Workspace artifacts must be manually inspectable and recoverable where possible.

NFR4: Export log must trace composition to slide/TXT line and skipped reason.

NFR5: App must work with local/LAN files and require no network for MVP.

NFR6: Critical validation errors must include Vietnamese remediation text.

NFR7: UI must support keyboard review workflow and visible status; status must not rely on color alone.

NFR8: App must remain desktop-first and support adaptive splitter layouts at minimum 1280x720, recommended 1440x900+.

NFR9: Confirm dialogs for destructive operations must focus safe/default action and use explicit action labels.

### Additional Requirements

AR1: Initialize project with custom Python package scaffold using `uv init --app`; first implementation story should establish `pyproject.toml`, package layout, dependencies, pytest, ruff.

AR2: Use layered package architecture: models, config, workspace, ingestion, gis, render, validation, export, jobs, editor, utils.

AR3: Use Pydantic models for config, workspace, composition, layer, target export template mapping, issue, render result, export log.

AR4: All workspace read/write operations must go through `WorkspaceService`; UI must not parse/write JSON directly.

AR5: JSON writes must be atomic using temp file and replace.

AR6: Core services must be testable without UI; render/export/validation must not depend on Qt widgets.

AR7: Long-running ingestion/render/export operations must use job/progress model and deliver progress safely to Qt main thread.

AR8: Use rasterio/GDAL for raster metadata/read windows, shapely for geometry/intersection, pyproj for CRS transforms.

AR9: Store target coordinate as geographic `[lon, lat]`; store composition view as `center` `[lon, lat]` plus `scale`, where `scale` is the map scale denominator such as `50000` for 1:50,000; render derives the geographic map window from center/scale/template map-frame physical size and converts it to raster CRS/read window as needed.

AR10: Isolate PPTX slide-copy risk in `export/pptx_slide_copy.py`; start with one-slide export vertical slice.

AR11: User project data lives outside application source tree: `project_data/config.json`, `targets/`, `templates/`, `imagery/`, `workspace/`.

AR12: Paths in config resolve relative to config file; workspace stores workspace-relative paths where possible.

AR13: Tests must include fixtures for configs, GeoJSON, GeoTIFF, templates, and workspaces; integration tests cover ingest->workspace, final PNG render, one-slide export.

AR14: Exact render latency budgets, metadata override reuse, and automated UI testing are deferred.

AR15: Map-surround rendering must match the operator's PPTX map panel structure: full white surround, outer coordinate frame, DMS labels, and an inset raster panel; preview and final render should share this layout contract.

AR16: PPTX template placeholder mapping must tolerate volatile PowerPoint shape ids by resolving configured placeholders from stable template metadata when available, especially shape names such as `ttn:map_image`, while preserving element-id replacement for export.

AR17: Windows executable packaging uses PyInstaller tooling run on Windows/Miniconda; one-folder output is the preferred default for PySide6/GDAL/rasterio stability, and a packaged smoke check is required before marking distribution ready.

### UX Design Requirements

UX-DR1: Implement Mode Switcher for Setup, Review/Edit, Export with active/disabled/has-warning/has-error states and tooltip explaining disabled states.

UX-DR2: Implement Path Picker Row with label, read-only path field, browse button, validation indicator, middle-elided long paths, and full-path tooltip.

UX-DR3: Implement Ingestion Progress Panel showing scanned, matched, targets with images, warnings, current target, current target matched count, and idle/running/success/warning/error states.

UX-DR4: Implement Composition Tree Item with expand indicator, severity icon, label/date/time, status badge, issue count, selected state, and issue tooltip.

UX-DR5: Implement Queue Filter Bar with filters Tất cả, Chưa duyệt, Ready, Include, Có warning, Có error and clear-filter empty state.

UX-DR6: Implement Layer Row with visibility control, order control, timestamp, cloud percent, metadata status, short filename, action menu, and full filename/path tooltip.

UX-DR7: Implement Slide Preview Panel with loading, stale/needs_update, rendered, and render_error states, updated through debounce.

UX-DR8: Implement GIS Editor Canvas with raster layers, fixed map frame overlay, grid labels, loading overlay, render quality indicator, mouse pan, wheel zoom, optional slider zoom.

UX-DR9: Implement Warning/Issue Row with severity icon, message, scope label, target/composition/layer reference, remediation, and jump action.

UX-DR10: Implement Review Action Bar with Previous, Skip, Include/Validate, Revalidate where needed; mirror keyboard shortcuts Right/Up/Left.

UX-DR11: Implement Metadata Editor for capture date/time correction, parsed source display, cloud percent, source/status, save/cancel, and confirm move when date changes cache folder.

UX-DR12: Implement Export Summary Metrics for included slides, targets, skipped, warnings, errors, and preflight state.

UX-DR13: Implement Export Plan Row with slide number, target alias/title, date/time label, template status, issue count, and jump back to composition on issue.

UX-DR14: Enforce UX consistency patterns: one primary action per mode, danger confirm dialogs, no silent state, issue-to-object navigation, progress with counters, explicit empty states.

UX-DR15: Enforce accessibility/keyboard patterns: icon tooltips, status not color-only, shortcut hints, focus order tree->layers->GIS editor->review actions->warnings, and text input arrow-key protection.

UX-DR16: Enforce desktop adaptive layout: splitter min/max sizes, no viewport font scaling, elide+tooltip for long text, stable row heights, no nested cards.

### Config Manager Requirements Addendum

CM-FR1: Provide a dedicated `Config` tab in the main app flow so the Operator can create, open, inspect, edit, validate, back up, save, and save-as a project `config.json` without editing raw JSON as the primary workflow.

CM-FR2: Maintain persisted, draft, and validated config states separately; show dirty/valid/warning/error status clearly; protect reload, save, and destructive operations with appropriate confirmation.

CM-FR3: Display config summary metrics, group navigation, target filtering, and a target table grouped by `group.key`/`group.title`, preserving the local per-group `sort_order` model already used by Review/Edit.

CM-FR4: Allow editing target fields through an inspector: `id`, `enabled`, `group.key`, `sort_order`, `name`, `alias`, `coordinate`, `scale`, `grid.interval`, export template/TXT fields, and placeholder values.

CM-FR5: Allow deleting the selected target from the inspector with a danger confirmation, including a warning when an open workspace may contain compositions for that target.

CM-FR6: Allow importing and exporting target geometry as GeoJSON through exactly two geometry actions: `Import GeoJSON` and `Export GeoJSON`, persisted as `metadata.geojson_geometry`.

CM-FR7: Provide editable views for default grid/frame/export settings and filename patterns, including a filename pattern test area that makes the UTC filename plus 7-hour local-time behavior visible.

CM-FR8: Provide a read-only Raw JSON view and a Validation Issues panel with severity, issue id, Vietnamese message/remediation, and navigation to the affected target or group where possible.

CM-AR1: Implement config editing behind a `ConfigEditorService` in `src/thucthengay/config/`; PySide UI in `src/thucthengay/editor/` must not read or write config JSON directly.

CM-AR2: Save operations must use atomic writes and config-relative path resolution consistent with existing `ConfigService`; validation should reuse existing models and issue patterns rather than duplicating schema logic in widgets.

CM-UX1: Match the approved mockup layout: top app tabs, config toolbar, summary stats, left group sidebar, central workarea tabs, right target inspector, and bottom validation issues panel.

CM-UX2: Keep the target toolbar intentionally narrow with `Thêm target`; removed bulk actions `Nhân bản`, `Đánh lại sort_order`, and `Di chuyển group` must not appear in the MVP.

CM-UX3: In the inspector, `Placeholders` shows only `field` and editable `value`; geometry shows only `Import GeoJSON` and `Export GeoJSON`, with no geometry preview or copy button.

### Historical Image Registry Requirements Addendum

HIR-FR1: Provide an optional SQLite-backed historical image registry that stores images included for each target across workspaces, including target identity, capture date/time, cloud percent where available, source paths, workspace/composition provenance, and timestamps.

HIR-FR2: Keep the workspace JSON as the source of truth for the current session; the SQLite registry is a long-lived reference source used to seed new workspaces with relevant historical imagery.

HIR-FR3: When a new workspace ingestion runs, load historical imagery according to configurable target scope: only targets with current-session matches by default, or all enabled targets when explicitly configured.

HIR-FR4: When loading historical imagery, support configurable image selection modes: latest capture date, latest N images, explicit date range, and lookback-days window anchored either to today or the current session latest capture date.

HIR-FR5: Merge current-session imagery and historical imagery into target-date compositions with deterministic deduplication so the same source image is not duplicated for the same target/date.

HIR-FR6: Validate historical image paths before adding them to a workspace; missing or unreadable paths must create structured issues with Vietnamese remediation and must not silently disappear.

HIR-FR7: Allow Operators to repair missing historical image paths, including single-file replacement and bulk path-prefix replacement, then revalidate and persist repaired paths to the registry.

HIR-FR8: Record historical registry entries only after a composition successfully passes validation and is included; skipped or validation-failed compositions must not be written as included history.

HIR-FR9: Provide an explicit application/workspace option to load or not load historical images during ingestion; when disabled, ingestion, Review/Edit, render, and export must behave like the current workspace-only workflow.

HIR-FR10: Provide a Review/Edit comparison mode that can be toggled on or off per composition; when off, the map frame remains the current single-map frame, and when on, the map frame is split into two comparison panes.

HIR-FR11: Support both comparison split orientations: vertical split for left/right panes and horizontal split for top/bottom panes.

HIR-FR12: In comparison mode, allow the Operator to choose which target-date image/layer is displayed in each pane from the selected target's current-session and loaded historical imagery.

HIR-AR1: Implement registry access behind a `HistoryService` in a new core module such as `src/thucthengay/history/`; PySide UI must not query or mutate SQLite directly.

HIR-AR2: Use Python's built-in `sqlite3` with schema migrations, transactions, parameter binding, foreign keys, and short write operations; WAL mode is allowed only for local database files and must be avoided or configurable for network-share database locations.

HIR-AR3: Historical images loaded into a workspace should be copied into workspace cache before review/render/export when available, preserving the existing workspace isolation and render/export reliability.

HIR-AR4: Comparison rendering must be implemented through render/model service boundaries, not by duplicating render business logic inside PySide widgets; final export must use the same comparison state as Review/Edit preview.

HIR-UX1: Ingest summary and Review/Edit must distinguish current-session imagery from historical imagery through text/icon status, not color alone.

HIR-UX2: Missing historical paths must be visible in the Warnings panel and navigable to the affected target/composition/layer, with a clear repair action.

HIR-UX3: Historical loading controls must make the two modes explicit: `Không tải ảnh lịch sử` and `Tải ảnh lịch sử`, with the disabled path presented as the safe/default current workflow unless project config says otherwise.

HIR-UX4: Comparison controls must stay close to the GIS canvas and expose only the required decisions: enable comparison, split orientation, Pane A image/time, and Pane B image/time.

HIR-UX5: Comparison panes must show visible labels for target, capture date/time, current/historical source, cloud percent where available, and missing/unreadable status where relevant.

### Satellite Download Tab Requirements Addendum

SDT-FR1: Provide a dedicated satellite image download tab in the main app flow, positioned as the outermost tab adjacent to the `Config` tab, so the Operator can run the download workflow without leaving the application.

SDT-FR2: Allow the Operator to select one or more input GeoJSON files explicitly; the UI must not require or expose a GeoJSON folder input for the primary workflow.

SDT-FR3: Allow the Operator to select multiple source image folders, including local or LAN paths, and preserve each source folder identity for output structuring and manifest reporting.

SDT-FR4: Allow the Operator to select one output folder where downloaded/copied imagery is written.

SDT-FR5: Reuse the satellite download logic from `0.Download_Img/download_satellite_images_by_geojson.py`: load GeoJSON geometries, scan configured GeoTIFF extensions recursively, read raster CRS/bounds with rasterio, transform GeoJSON geometry when needed, test intersection, parse filename date/time/cloud metadata from configurable patterns, apply cloud filters, use a raster metadata cache, and copy matched images.

SDT-FR6: Write copied images under the output folder using the structure `<output>/<geojson_name>/<source_folder_name>/...`, where `geojson_name` is derived from the selected GeoJSON filename and `source_folder_name` matches the selected source image folder name using the same safe/unique naming behavior as the script.

SDT-FR7: When a single source image intersects multiple selected GeoJSON files, copy/report it under each matching GeoJSON output branch unless an explicit deduplication option is later added; this preserves the requested per-GeoJSON output structure.

SDT-FR8: Provide download options equivalent to the script where applicable: extensions, filename format rules with optional `max_cloud_percent`, overwrite existing outputs, dry-run, include-boundary-touch, preserve source tree under each source folder, and write manifest.

SDT-FR9: Show progress while scanning/downloading with counters for total images, scanned images, matched images, downloaded/copied images, skipped existing, skipped cloud, failed images, metadata cache hits/misses, current source folder, and current GeoJSON/match context.

SDT-FR10: Write a manifest CSV in the output folder for each run, including status, source folder, source path, destination path, matched GeoJSON, filename-format match status/rule, capture datetime, cloud percent, max cloud percent, and error message.

SDT-FR11: Surface configuration/path/raster errors as structured Vietnamese issues or status messages; failed images must not abort the whole run unless the initial run configuration is invalid.

SDT-FR12: Allow cancellation of a running download job and report whether the run completed, failed, or was cancelled, including any partial output and manifest state.

SDT-FR13: Keep the satellite download workflow independent from workspace ingestion unless the Operator later selects the downloaded output as an imagery input folder; the download tab must not mutate workspace manifest/compositions/history directly.

SDT-AR1: Implement the reusable download engine in a core module such as `src/thucthengay/download/`; PySide widgets must not contain raster scanning, CRS transform, copy, manifest, or cache business logic.

SDT-AR2: Long-running download execution must use the existing job/progress pattern and deliver progress safely to the Qt main thread.

SDT-AR3: The raster metadata cache should be stored under the selected output folder, keyed by source path, file size, and mtime, and must use short SQLite transactions with parameter binding.

SDT-AR4: Tests for the download engine must use temp directories and lightweight generated GeoTIFF/GeoJSON fixtures; tests must not depend on LAN paths, real production imagery, or network availability.

SDT-UX1: The tab layout must use path picker/list controls for GeoJSON files, source image folders, and output folder, with add/remove/clear actions, validation indicators, middle-elided long paths, and full-path tooltips.

SDT-UX2: The download action area must show one primary action, clear disabled reasons, progress percentage/counters, current activity text, cancel when safe, and a completion summary with manifest/output links.

SDT-UX3: Status must not rely on color alone; errors and warnings must include icons/text and Vietnamese remediation.

### Render Pipeline Refactor Requirements Addendum

RPR-FR1: Provide render performance instrumentation that records timing for raster window reads, resampling, raster-to-uint8 scaling, QImage conversion, QPixmap conversion, paint/composite steps, cache hit/miss counts, and `rasterio.read()` calls during pan/zoom workflows.

RPR-FR2: Provide a diagnostic path for checking GeoTIFF overview/COG readiness, including available overview levels, raster dimensions, block/tile layout where available, and actionable warnings when large rasters lack usable overviews.

RPR-FR3: Provide tooling or service support to prepare imagery for efficient rendering by creating COG outputs or external overviews, while preserving the existing workspace/cache source-of-truth contracts and never mutating production source imagery without an explicit operator/developer action.

RPR-FR4: Persist or cache raster overview metadata so repeated render operations do not reopen datasets only to discover overview levels.

RPR-FR5: Introduce a fixed map-space tile index that converts a viewport/scale request into deterministic tile keys independent from the current frame, so pan/zoom reuses decoded spatial data.

RPR-FR6: Introduce a byte-budgeted tile cache keyed by raster/file signature, overview/LOD level, tile coordinates, style-affecting parameters where needed, and invalidated only when source signature or render-affecting parameters change.

RPR-FR7: Decode missing tiles asynchronously with prioritization near the viewport center, cooperative cancellation for obsolete requests, and no stale tile application after the view changes.

RPR-FR8: Compose the GIS canvas from cached tiles so pan operations reuse existing decoded tiles and decode only newly exposed tile bands where practical.

RPR-FR9: Implement partial repaint after tile rendering is stable, reusing the previous frame buffer for small pan deltas and recompositing only exposed regions unless zoom or large movement requires a full redraw.

RPR-FR10: Add progressive LOD refinement so lower-resolution cached tiles can appear immediately during fast pan/zoom and be replaced by correct-resolution tiles when available.

RPR-FR11: Reassess GPU/OpenGL only after instrumentation shows the remaining bottleneck is texture/pixmap upload or composition rather than raster decode/resampling.

RPR-AR1: Keep render business logic in `src/thucthengay/render/` and job orchestration in `src/thucthengay/jobs/`; PySide widgets may request render work and display results but must not own raster/tile decode logic.

RPR-AR2: Keep final export fidelity stable: tile-based preview optimization must not change final render output unless a story explicitly updates and verifies the final render contract.

RPR-AR3: Tile cache and scheduler tests must use generated lightweight raster fixtures and deterministic viewport/tile coordinates; they must not depend on real LAN imagery.

RPR-AR4: Epic 11 performance changes must preserve the existing map frame contract exactly. No adjustment may change or affect map-frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or any existing map-surround spacing unless a separate non-performance story explicitly approves and verifies that visual/layout change.

RPR-UX1: During render diagnostics and progressive rendering, the UI must show clear loading/quality/status text without relying on color alone and without blocking normal Review/Edit actions longer than necessary.

### FR Coverage Map

FR1: Epic 1 - Load target config.
FR2: Epic 1 - Select input/workspace folders and confirm workspace clear.
FR3: Epic 2 - Scan/match GeoTIFF imagery.
FR4: Epic 2 - Create target-date compositions.
FR5: Epic 2 - Show ingestion progress and warnings.
FR6: Epic 1 - Maintain workspace structure.
FR7: Epic 1 - Persist composition status.
FR8: Epic 1 - Persist validation summary.
FR9: Epic 3 - Target-composition navigation.
FR10: Epic 3 - Layer stack editing.
FR11: Epic 3 - GIS editor view center/scale editing.
FR12: Epic 3 - Grid override editing.
FR13: Epic 3 - Slide preview.
FR14: Epic 4 - Manual metadata correction.
FR15: Epic 5 - Render map output from composition.
FR16: Epic 5 - Hybrid preview/final render pipeline.
FR17: Epic 4 - Structured issues.
FR18: Epic 4 - Validation timing and gating.
FR19: Epic 4 - Issues surfaced in UI.
FR20: Epic 6 - Target-specific one-slide PPTX template and element-id replacement map.
FR21: Epic 6 - Combined PPTX export.
FR22: Epic 6 - TXT export.
FR23: Epic 6 - Export summary and logs.
AR15: Epic 7 - Map-surround render hardening.
AR16: Epic 7 - PPTX placeholder auto-match hardening.
AR17: Epic 7 - Windows packaging readiness.
CM-FR1-CM-FR8: Epic 8 - Config Manager tab.
CM-AR1-CM-AR2: Epic 8 - Config editing service and UI boundary.
CM-UX1-CM-UX3: Epic 8 - Approved Config Manager layout and interactions.
HIR-FR1-HIR-FR12: Epic 9 - Historical image registry, workspace seeding, and temporal comparison.
HIR-AR1-HIR-AR4: Epic 9 - SQLite service boundary, migrations, cache integration, and comparison render boundary.
HIR-UX1-HIR-UX5: Epic 9 - Historical imagery visibility, explicit loading mode, and comparison UX.
SDT-FR1-SDT-FR13: Epic 10 - In-app satellite image download workflow.
SDT-AR1-SDT-AR4: Epic 10 - Download engine/service boundary, progress jobs, SQLite metadata cache, and fixture-based tests.
SDT-UX1-SDT-UX3: Epic 10 - Download tab path controls, progress/cancel/summary UX, and accessible status messaging.
RPR-FR1-RPR-FR11: Epic 11 - Render pipeline performance refactor and tile-based preview architecture.
RPR-AR1-RPR-AR4: Epic 11 - Render service boundaries, final output stability, fixture-based tile tests, and strict map-frame invariance.
RPR-UX1: Epic 11 - Render diagnostics/progressive status UX.


## Epic List

### Epic 1: Project Setup, Schemas, and Workspace Foundation

Operator có thể mở app/project scaffold, dùng cấu trúc dữ liệu chuẩn, load config, resolve paths, và tạo/đọc/ghi workspace/composition JSON an toàn. Epic này tạo nền để mọi epic sau dùng chung state đúng cách.

**FRs covered:** FR1, FR2, FR6, FR7, FR8
**Key architecture/UX coverage:** AR1, AR2, AR3, AR4, AR5, AR11, AR12, UX-DR1, UX-DR2

### Epic 2: Data Ingestion to Composition Workspace

Operator có thể chọn bộ ảnh GeoTIFF, chạy `Lấy dữ liệu`, theo dõi progress, và nhận workspace có cache ảnh + compositions theo target-date.

**FRs covered:** FR3, FR4, FR5
**Key architecture/UX coverage:** AR7, AR8, AR13, UX-DR3

### Epic 3: Review/Edit Workstation Core

Operator có thể duyệt composition trong Review/Edit, xem tree/filter/layers, bật tắt và sắp xếp layer, pan/zoom map dưới frame cố định, chỉnh grid, xem preview, và dùng review action bar để include/skip/quay lại.

**FRs covered:** FR9, FR10, FR11, FR12, FR13
**Key architecture/UX coverage:** UX-DR4, UX-DR5, UX-DR6, UX-DR7, UX-DR8, UX-DR10, UX-DR14, UX-DR15, UX-DR16

### Epic 4: Validation, Warnings, and Metadata Correction

Operator thấy lỗi/warning đúng ngữ cảnh, có remediation tiếng Việt, có thể sửa metadata layer, và app chặn ready/export khi có lỗi blocking.

**FRs covered:** FR14, FR17, FR18, FR19
**Key architecture/UX coverage:** UX-DR9, UX-DR11, NFR6, NFR7

### Epic 5: Rendering Pipeline and Map Output Fidelity

Operator có preview đáng tin và app tạo được PNG final từ composition state, với shared render math, grid/background/layer order đúng, preview/final alignment, và render job không apply stale result.

**FRs covered:** FR15, FR16
**Key architecture/UX coverage:** AR8, AR9, AR13, NFR1

### Epic 6: Report Export and Completion Evidence

Operator có thể chạy preflight, xem export plan, xuất một PPTX tổng hợp + TXT theo review_order, dùng target-specific one-slide PPTX template với replacement theo element id, và nhận summary/log rõ ràng sau export.

**FRs covered:** FR20, FR21, FR22, FR23
**Key architecture/UX coverage:** AR10, UX-DR12, UX-DR13, NFR4

### Epic 7: Post-MVP Hardening and Distribution Readiness

Operator có output bản đồ khớp template thực tế hơn, config kiểm soát được các tham số frame mặc định, template PPTX bền hơn khi PowerPoint đổi shape id, và dự án có tooling đóng gói `.exe` Windows để chuẩn bị bàn giao.

**FRs covered:** FR15, FR16, FR20, FR21
**Key architecture/UX coverage:** AR15, AR16, AR17, NFR1, NFR4

### Epic 8: Config Manager Tab

Operator có thể tạo, mở, kiểm tra, chỉnh sửa, backup và lưu `config.json` bằng giao diện trong app, quản lý target/group/defaults/patterns/geometry an toàn, và không cần sửa JSON thô cho các thao tác thường ngày.

**FRs covered:** CM-FR1, CM-FR2, CM-FR3, CM-FR4, CM-FR5, CM-FR6, CM-FR7, CM-FR8
**Key architecture/UX coverage:** CM-AR1, CM-AR2, CM-UX1, CM-UX2, CM-UX3, NFR2, NFR6, NFR7, NFR9

### Epic 9: Historical Image Registry and Temporal Compare View

Operator co the chon ro co tai anh lich su hay khong, dung lai anh da include trong cac workspace truoc, va so sanh hai thoi diem trong cung khung ban do khi can.

**FRs covered:** HIR-FR1, HIR-FR2, HIR-FR3, HIR-FR4, HIR-FR5, HIR-FR6, HIR-FR7, HIR-FR8, HIR-FR9, HIR-FR10, HIR-FR11, HIR-FR12
**Key architecture/UX coverage:** HIR-AR1, HIR-AR2, HIR-AR3, HIR-AR4, HIR-UX1, HIR-UX2, HIR-UX3, HIR-UX4, HIR-UX5, NFR2, NFR3, NFR5, NFR6, NFR7, NFR9

### Epic 10: Satellite Image Download Tab

Operator co the chon nhieu file GeoJSON, nhieu folder anh nguon, va mot folder output de tai/copy anh ve tinh giao cat voi khu vuc quan tam ngay trong app, voi output duoc to chuc theo tung GeoJSON va tung folder anh nguon.

**FRs covered:** SDT-FR1, SDT-FR2, SDT-FR3, SDT-FR4, SDT-FR5, SDT-FR6, SDT-FR7, SDT-FR8, SDT-FR9, SDT-FR10, SDT-FR11, SDT-FR12, SDT-FR13
**Key architecture/UX coverage:** SDT-AR1, SDT-AR2, SDT-AR3, SDT-AR4, SDT-UX1, SDT-UX2, SDT-UX3, AR7, AR8, NFR5, NFR6, NFR7, NFR8

### Epic 11: Render Pipeline Performance Refactor

Operator can pan/zoom large satellite imagery smoothly because render work is measured first, GeoTIFF overviews are prepared or detected, decoded raster data is cached by stable map-space tiles, and the GIS canvas reuses cached tiles instead of rerendering the whole frame after every view change.

**FRs covered:** RPR-FR1, RPR-FR2, RPR-FR3, RPR-FR4, RPR-FR5, RPR-FR6, RPR-FR7, RPR-FR8, RPR-FR9, RPR-FR10, RPR-FR11
**Key architecture/UX coverage:** RPR-AR1, RPR-AR2, RPR-AR3, RPR-AR4, RPR-UX1, AR7, AR8, NFR1, NFR5, NFR7, NFR8

## Epic 1: Project Setup, Schemas, and Workspace Foundation

**Goal:** Operator có thể mở app/project scaffold, dùng cấu trúc dữ liệu chuẩn, load config, resolve paths, và tạo/đọc/ghi workspace/composition JSON an toàn.

### Story 1.1: Initialize Application Scaffold and Quality Tooling

As a Developer,
I want a clean Python desktop application scaffold with standard tooling,
So that future stories can be implemented consistently and tested without ad hoc setup.

**Requirement References:** AR1, AR2, AR6

**Acceptance Criteria:**

**Given** the repository has no finalized application scaffold
**When** the developer initializes the app structure
**Then** the project contains `pyproject.toml`, source package layout, test layout, and configured dependencies for PySide6, Pydantic, pytest, and ruff
**And** the package follows the architecture modules: `models`, `config`, `workspace`, `ingestion`, `gis`, `render`, `validation`, `export`, `jobs`, `editor`, and `utils`

**Given** the scaffold is present
**When** the developer runs the test and lint commands documented for the project
**Then** the commands execute against the package without requiring network access or external project data
**And** at least one smoke test verifies the package can be imported

**Given** future implementation stories depend on core modules
**When** modules are created in the scaffold
**Then** non-UI core modules do not import Qt widgets
**And** UI entrypoint code is isolated from model/workspace/config services

### Story 1.2: Define Core Pydantic Models

As a Developer,
I want typed Pydantic models for project config and workspace state,
So that application services share one validated data contract.

**Requirement References:** AR3, AR11, AR12, FR6, FR17, FR20

**Acceptance Criteria:**

**Given** config and workspace JSON data is loaded by services
**When** the data is parsed
**Then** Pydantic models validate target config, workspace manifest, composition, layer, target export template mapping, issue, render result, and export log structures
**And** validation errors identify the field path that failed

**Given** a target config contains PowerPoint template references
**When** the config model is parsed
**Then** each target supports target-specific one-slide PPTX template fields and element-id placeholder mappings
**And** the model can represent `template_pptx_file`, `geojson_file`, target identity, enabled state, `sort_order`, target `coordinate` `[lon, lat]`, target `scale` as a positive map scale denominator, and target grid interval

**Given** a composition is represented in JSON
**When** it is parsed or serialized
**Then** the model includes target/date identity, layer list, view center/scale, grid override, status fields, validation summary, and workspace-relative artifact references where applicable
**And** defaults match the PRD: `reviewed=false`, `ready=false`, `include=false`, and newest layer ordering can be represented

**Given** an issue is produced by validation
**When** it is serialized
**Then** it includes `issue_id`, `severity`, `scope`, target/composition/layer references, Vietnamese message/remediation, and `blocking`

### Story 1.3: Load and Validate Project Config

As an Operator,
I want the app to load a project config file and validate target references,
So that only usable enabled targets enter the workflow.

**Requirement References:** FR1, FR20, AR12, NFR6

**Acceptance Criteria:**

**Given** the Operator selects a readable `config.json`
**When** the app loads the config
**Then** it resolves config-relative paths for target GeoJSON and template PPTX files
**And** it includes only targets where `enabled=true`
**And** it sorts enabled targets by `sort_order`

**Given** a config file is missing a required field or contains invalid data
**When** the app attempts to load it
**Then** the load fails with a structured issue or validation result
**And** the message explains the required correction in Vietnamese

**Given** an enabled target omits `coordinate`, `scale`, or `grid.interval`, or provides invalid values
**When** the config is validated
**Then** the load fails with a structured issue tied to the target field path
**And** the Vietnamese remediation explains that `coordinate` must be `[lon, lat]`, `scale` must be a positive map scale denominator, and grid interval must be valid DMS-compatible configuration

**Given** an enabled target references a missing GeoJSON or template PPTX file
**When** the config is validated
**Then** the target receives a blocking validation issue
**And** ingestion/export cannot proceed for that target until the reference is fixed

**Given** a target references a PPTX template path and element-id mapping
**When** export preparation validates the target
**Then** the PPTX path resolves relative to the config file
**And** missing or invalid PPTX templates or required element ids are treated as blocking errors

### Story 1.4: Select Project Paths in Setup Mode

As an Operator,
I want to select the project config, imagery input folder, and workspace folder in Setup mode,
So that I can verify the project inputs before ingestion changes any files.

**Requirement References:** FR2, UX-DR1, UX-DR2, UX-DR14, UX-DR16, NFR5, NFR9

**Acceptance Criteria:**

**Given** the application opens in Setup mode
**When** the Operator views the path selection area
**Then** it shows path picker rows for config file, imagery input folder, and workspace folder
**And** each row has a label, read-only path field, browse button, validation indicator, middle-elided long path display, and full path tooltip

**Given** a selected path is missing, unreadable, or not the expected type
**When** the path row validates
**Then** the row displays a non-color-only invalid status
**And** the primary ingestion action remains disabled with a tooltip explaining the blocker

**Given** all required paths are valid
**When** Setup validation completes
**Then** the app enables the next available setup action
**And** the selected paths are visible before any workspace clear or ingestion operation begins

**Given** a long local or LAN path is selected
**When** the path row is narrower than the full text
**Then** the path is elided without changing row height
**And** the full path remains available through tooltip or equivalent detail display

### Story 1.5: Create and Manage Workspace Structure

As an Operator,
I want the app to create and manage a predictable workspace folder,
So that project state and generated artifacts are inspectable and recoverable.

**Requirement References:** FR2, FR6, AR4, AR5, AR11, AR12, NFR2, NFR3, NFR9

**Acceptance Criteria:**

**Given** the Operator selects a valid workspace folder
**When** workspace initialization runs
**Then** `WorkspaceService` creates or verifies `manifest.json`, `cache/`, `compositions/`, `renders/`, and `exports/`
**And** all workspace reads and writes go through `WorkspaceService`

**Given** a workspace already contains app-owned data
**When** the Operator starts an operation that would clear cache, compositions, renders, or exports
**Then** the app shows an explicit confirmation dialog
**And** the safe/default action avoids destructive clearing
**And** destructive action labels name what will be cleared

**Given** the app writes manifest or composition JSON
**When** a write succeeds
**Then** the file is written atomically using a temporary file and replace operation
**And** failed writes do not leave partial invalid JSON at the final path

**Given** a workspace path is later reopened
**When** `WorkspaceService` loads it
**Then** the manifest and known subfolders are detected
**And** recoverable missing folders are recreated without changing composition state

### Story 1.6: Persist Composition Status and Review State

As an Operator,
I want review status and keyboard decisions to persist per composition,
So that I can resume the review workflow without losing decisions.

**Requirement References:** FR7, AR4, UX-DR10, UX-DR15, NFR7

**Acceptance Criteria:**

**Given** a composition JSON exists in the workspace
**When** the Operator changes notes or status through the app
**Then** `reviewed`, `ready`, `include`, `review_order`, and `notes` are persisted through `WorkspaceService`
**And** reloading the workspace restores the same values

**Given** the Operator uses the right-arrow include action after a caller has supplied a passing validation gate result
**When** the status transition is applied
**Then** the composition is marked reviewed and ready according to the PRD transition rules
**And** include/review_order are updated consistently with the include action
**And** this story persists the transition only; full validation rule evaluation is implemented in Epic 4

**Given** the Operator uses the up-arrow skip action
**When** the skip transition is applied
**Then** the composition is marked reviewed but not included
**And** the app advances according to the review queue behavior

**Given** the Operator uses the left-arrow previous action
**When** a previous composition exists
**Then** the app navigates back without corrupting the current composition status
**And** no text input field consumes review shortcuts while focused for text editing

### Story 1.7: Persist Validation Summary and Revalidation State

As an Operator,
I want validation status to persist without storing stale detailed issue lists,
So that the workspace shows reliable status while detailed issues are recalculated when needed.

**Requirement References:** FR8, FR18, AR4, NFR2

**Acceptance Criteria:**

**Given** a validation service contract returns detailed issues and a summary for a composition
**When** the composition is saved
**Then** only the validation summary is persisted in composition JSON
**And** detailed issue lists remain derived state owned by the validation service
**And** Epic 1 defines the storage contract without implementing the full readiness rules

**Given** layer, view center/scale, grid override, or metadata changes
**When** the change is saved
**Then** the composition is marked `needs_revalidation=true`
**And** tree/status indicators can show that the prior validation is stale

**Given** a composition has a persisted validation summary
**When** the workspace is reloaded
**Then** aggregate status and counts can be displayed from the summary
**And** the app does not treat stale summaries as export-ready proof when `needs_revalidation=true`

**Given** a validation summary is stored for a composition
**When** UI or export code reads the composition state
**Then** it can distinguish clean, warning, error, and stale validation states from the persisted summary
**And** full blocking behavior for include/export decisions is implemented by Epic 4 validation stories

## Epic 2: Data Ingestion to Composition Workspace

**Goal:** Operator có thể chọn bộ ảnh GeoTIFF, chạy `Lấy dữ liệu`, theo dõi progress, và nhận workspace có cache ảnh + compositions theo target-date.

### Story 2.1: Scan Imagery Folder and Extract GeoTIFF Metadata

As an Operator,
I want the app to scan my imagery folder and extract required GeoTIFF metadata,
So that usable imagery can enter the workflow even when separate metadata files are missing.

**Requirement References:** FR3, FR14, AR7, AR8, AR13, NFR5

**Acceptance Criteria:**

**Given** the Operator has selected a valid imagery input folder
**When** ingestion scans the folder
**Then** it recursively discovers supported GeoTIFF files
**And** it ignores unsupported files without failing the entire ingestion run

**Given** a GeoTIFF has PlanetScope-style filename metadata or an available sidecar metadata file
**When** metadata extraction runs
**Then** the app parses capture date/time, cloud percent when available, and source identifiers from that metadata source
**And** the layer records the metadata source used for each parsed field

**Given** a GeoTIFF has no usable sidecar metadata file
**When** metadata extraction runs
**Then** the app uses `rasterio` to read required information directly from the GeoTIFF, including CRS, bounds or transform, width/height, band count, nodata when available, and embedded tags when available
**And** the file can continue to target matching when a valid footprint can be derived

**Given** capture date/time or cloud percent cannot be derived from filename, sidecar metadata, or embedded GeoTIFF tags
**When** the layer metadata is created
**Then** the missing fields are marked with `metadata_status=needs_manual_correction` where required by later workflow
**And** ingestion creates a warning rather than failing the entire run

**Given** a GeoTIFF cannot be opened or has no valid geospatial footprint
**When** metadata extraction attempts to process it
**Then** ingestion records a warning with the file path and reason
**And** the invalid file is excluded from target matching

### Story 2.2: Match Imagery to Enabled Target Boundaries

As an Operator,
I want scanned imagery matched to enabled target boundaries,
So that each target only receives imagery that intersects its configured area.

**Requirement References:** FR1, FR3, AR8, AR12

**Acceptance Criteria:**

**Given** enabled targets have valid GeoJSON boundary files
**When** ingestion loads target boundaries
**Then** it reads each GeoJSON through the config-resolved path
**And** it prepares geometries for intersection checks without changing the source GeoJSON files

**Given** scanned imagery has a valid footprint and CRS
**When** ingestion compares imagery against targets
**Then** it transforms geometries as needed using `pyproj`/rasterio CRS metadata
**And** it records a match when the imagery footprint intersects the target boundary

**Given** a target is disabled in config
**When** matching runs
**Then** no imagery is matched to that target
**And** no compositions are created for that target

**Given** a target boundary is missing, invalid, or cannot be transformed
**When** matching reaches that target
**Then** ingestion records a blocking target-level issue or warning appropriate to the failure
**And** processing continues for other valid targets where possible

### Story 2.3: Copy Matched Imagery into Workspace Cache

As an Operator,
I want matched imagery copied into the workspace cache,
So that the project can be reviewed from a stable app-owned workspace.

**Requirement References:** FR2, FR3, FR6, AR4, AR11, AR12, NFR2, NFR3

**Acceptance Criteria:**

**Given** imagery has been matched to one or more targets
**When** cache population runs
**Then** the app copies matched files into `workspace/cache/` using a deterministic target/date-oriented structure
**And** it preserves source file path, cached file path, metadata source, capture metadata, and cloud percent where available in layer records

**Given** the same source image is encountered again for the same target/date
**When** cache population runs
**Then** the app avoids duplicate cache entries where file identity can be established
**And** the resulting layer list remains deterministic across repeated ingestion runs

**Given** a source file cannot be copied due to permission, missing file, or IO failure
**When** cache population attempts the copy
**Then** ingestion records a warning with the source path and reason
**And** the failed file is not included in composition layer records

**Given** the workspace cache already contains prior app-owned imagery
**When** ingestion would clear or replace it
**Then** the operation only proceeds after the explicit workspace clear confirmation defined in Epic 1
**And** the summary records that cache contents were recreated

### Story 2.4: Create Target-Date Composition JSON Files

As an Operator,
I want matched imagery grouped into target-date compositions,
So that each report slide can be reviewed as a separate unit of work.

**Requirement References:** FR4, FR6, FR7, FR8, AR4, AR5, AR12

**Acceptance Criteria:**

**Given** matched cached imagery exists for a target across one or more capture dates
**When** composition creation runs
**Then** the app creates one composition JSON per target-date
**And** multi-date imagery for the same target is split into separate compositions

**Given** a new composition is created
**When** its default state is initialized
**Then** `reviewed=false`, `ready=false`, `include=false`, and `needs_revalidation=true`
**And** `review_order` is unset until review/include behavior assigns it
**And** `view.center` is initialized from the target config coordinate and `view.scale` is initialized from the target scale denominator
**And** the initial grid interval comes from target grid config unless a composition override is later saved

**Given** multiple layers exist in a composition
**When** the layer stack is initialized
**Then** newest valid capture time appears on top by default
**And** layers with missing required capture time are retained but marked for metadata correction and validation warnings

**Given** composition JSON is written to the workspace
**When** the write completes
**Then** it is saved through `WorkspaceService` using atomic write behavior
**And** paths inside the composition prefer workspace-relative references where possible

### Story 2.5: Run Ingestion as Progress Job

As an Operator,
I want ingestion to run with visible progress,
So that large imagery folders do not make the desktop app feel stalled.

**Requirement References:** FR5, AR7, UX-DR3, NFR1

**Acceptance Criteria:**

**Given** the Operator starts `Lấy dữ liệu`
**When** ingestion begins
**Then** it runs through the app job/progress model instead of blocking the UI thread
**And** progress updates are delivered safely to the Qt main thread

**Given** ingestion is running
**When** progress changes
**Then** the UI can display scanned image count, matched image count, targets with images, warning count, current target, and matched count for the current target
**And** the progress model supports idle, running, success, warning, and error states

**Given** ingestion encounters warnings for specific files or targets
**When** progress is reported
**Then** warning counts update without stopping the whole job unless a fatal setup-level error occurs
**And** warnings remain available for the post-ingestion summary

**Given** ingestion is superseded by a new run or cancelled by the operator where cancellation is supported
**When** a stale progress update arrives
**Then** the app ignores stale updates for the previous job
**And** workspace state is not marked complete until the active job finishes successfully or with warnings

### Story 2.6: Show Ingestion Summary and Warnings

As an Operator,
I want a clear ingestion summary after `Lấy dữ liệu`,
So that I know what was created and what needs attention before review.

**Requirement References:** FR5, FR6, FR19, UX-DR3, UX-DR9, UX-DR14, NFR6

**Acceptance Criteria:**

**Given** ingestion completes successfully or with warnings
**When** the summary is shown
**Then** it displays scanned images, matched images, targets with images, created compositions, warning count, and workspace path
**And** the summary distinguishes success-with-warnings from hard failure

**Given** warnings were produced during scan, metadata extraction, matching, or cache copy
**When** the Operator opens the warning list
**Then** each warning includes scope, affected target/composition/layer/file when known, Vietnamese message, and remediation text where actionable
**And** warnings can be surfaced later in Review/Edit where they relate to a composition or layer

**Given** no imagery matches any enabled target
**When** ingestion completes
**Then** the summary shows an explicit empty state
**And** it explains likely causes such as disabled targets, non-intersecting imagery, invalid GeoTIFF footprints, or incorrect input folder

**Given** compositions were created
**When** the Operator proceeds to Review/Edit
**Then** the workspace manifest and composition index provide the created target-date compositions to the next mode
**And** no UI code reads raw composition JSON directly outside `WorkspaceService`

## Epic 3: Review/Edit Workstation Core

**Goal:** Operator có thể duyệt composition trong Review/Edit, xem tree/filter/layers, bật tắt và sắp xếp layer, pan/zoom map dưới frame cố định, chỉnh grid, xem preview, và dùng review action bar để include/skip/quay lại.

### Story 3.1: Build Review/Edit Layout and Composition Tree

As an Operator,
I want a Review/Edit workstation with a target-composition tree,
So that I can navigate review work by target and date with clear status context.

**Requirement References:** FR6, FR8, FR9, UX-DR4, UX-DR16, NFR7, NFR8

**Acceptance Criteria:**

**Given** the workspace contains target-date compositions
**When** the Operator enters Review/Edit mode
**Then** the UI shows a desktop splitter layout with composition tree, layer/editor workspace, preview, actions, and warnings areas
**And** splitter min/max sizes keep content usable at 1280x720 and recommended 1440x900+ layouts

**Given** compositions are loaded from the workspace
**When** the tree is populated
**Then** targets can expand to show composition rows ordered by configured target order and composition date/review order as applicable
**And** each row shows label/date/time, status badge, severity icon, issue count, selected state, and tooltip with issue summary where available

**Given** a composition row is selected
**When** selection changes
**Then** the app loads the composition through `WorkspaceService`
**And** detail panels update without UI code reading raw JSON directly

**Given** status or issue severity is displayed
**When** the Operator views the row
**Then** status is conveyed through text/icon as well as color
**And** row height remains stable when indicators change

### Story 3.2: Add Queue Filters and Empty States

As an Operator,
I want queue filters for review status and issue severity,
So that I can focus on the compositions that need action.

**Requirement References:** FR8, FR9, UX-DR5, UX-DR14

**Acceptance Criteria:**

**Given** the Review/Edit tree has loaded compositions
**When** the filter bar is shown
**Then** it provides filters: `Tất cả`, `Chưa duyệt`, `Ready`, `Include`, `Có warning`, and `Có error`
**And** each filter can show an aggregate count where the data is available

**Given** the Operator selects a filter
**When** the filter is applied
**Then** the tree only shows matching compositions while preserving target grouping where useful
**And** clearing the filter returns to the full queue without losing selection state when the selected composition remains visible

**Given** a filter has no matching compositions
**When** the filtered view is rendered
**Then** the UI shows an explicit empty state explaining that no compositions match the filter
**And** the empty state does not obscure the filter controls

**Given** validation summary or review status changes
**When** the tree model refreshes
**Then** filter counts and visible rows update consistently
**And** stale validation state can be represented distinctly from clean ready state

### Story 3.3: Implement Layer Stack Controls

As an Operator,
I want to control layer visibility and order for a composition,
So that the selected image stack reflects what should appear on the report slide.

**Requirement References:** FR8, FR10, FR17, AR4, UX-DR6, UX-DR15, UX-DR16

**Acceptance Criteria:**

**Given** a composition has one or more layers
**When** the layer stack is displayed
**Then** each layer row shows visibility control, order control, timestamp, cloud percent, metadata status, short filename, action menu, and full filename/path tooltip
**And** long filenames are elided without changing row height

**Given** the Operator toggles layer visibility
**When** the change is saved
**Then** the composition layer visibility is persisted through `WorkspaceService`
**And** the composition is marked `needs_revalidation=true`

**Given** the Operator changes layer order
**When** the change is saved
**Then** the new order is persisted in the composition JSON
**And** subsequent preview/render operations use the persisted layer order

**Given** no layer remains visible
**When** validation is triggered for the composition
**Then** validation produces a blocking error
**And** the layer stack and tree expose the issue in a non-color-only way

### Story 3.4: Implement GIS Editor Canvas View Controls

As an Operator,
I want to pan and zoom imagery under a fixed map frame,
So that I can choose the exact target-centered map view used in the slide map.

**Requirement References:** FR8, FR11, FR16, AR9, UX-DR8, NFR1

**Acceptance Criteria:**

**Given** a selected composition has visible raster layers
**When** the GIS editor canvas loads
**Then** it displays raster layers under a fixed map frame overlay
**And** it shows loading/error/empty states when raster data is not ready or unavailable

**Given** the Operator pans or zooms the canvas
**When** the interaction completes
**Then** the source-of-truth `view.center` `[lon, lat]` and `view.scale` are persisted in the composition
**And** rotation remains fixed at 0 with no MVP rotation UI

**Given** the Operator uses mouse wheel zoom or optional zoom slider
**When** zoom changes
**Then** `view.scale` changes while the map frame aspect is preserved according to target PPTX map-frame bounds/config
**And** the composition is marked `needs_revalidation=true` and preview stale/needs update

**Given** raster rendering is in progress
**When** a newer canvas interaction supersedes an older render request
**Then** stale render results are ignored
**And** the canvas does not apply a result for an outdated center/scale state

### Story 3.5: Implement Per-Composition Grid Override Controls

As an Operator,
I want to override grid interval per composition,
So that grid labels fit the selected map view without changing target defaults.

**Requirement References:** FR8, FR12, UX-DR14

**Acceptance Criteria:**

**Given** a selected composition has no grid override
**When** grid controls are shown
**Then** they display target config defaults
**And** the label format defaults to `dms_full` unless configured otherwise

**Given** the Operator edits DMS interval fields
**When** the override is saved
**Then** the override is persisted only in the composition JSON
**And** target config defaults remain unchanged

**Given** a grid override is invalid or outside allowed limits
**When** the Operator attempts to save or validate
**Then** the UI shows a validation message in Vietnamese
**And** invalid values do not silently change render output

**Given** grid settings change
**When** the composition state is saved
**Then** the preview is marked stale or updated through debounce
**And** the composition is marked `needs_revalidation=true`

### Story 3.6: Implement Slide Preview Panel with Debounced Updates

As an Operator,
I want a slide preview that tracks my composition changes,
So that I can judge whether the report slide will look correct before export.

**Requirement References:** FR13, FR15, FR16, UX-DR7, NFR1

**Acceptance Criteria:**

**Given** a composition is selected
**When** the preview panel loads
**Then** it can show loading, stale/needs_update, rendered, and render_error states
**And** each state is visually and textually distinguishable

**Given** layer visibility/order, view center/scale, grid override, or metadata changes
**When** the change occurs
**Then** preview updates are debounced to avoid excessive rendering
**And** stale preview state is shown until the latest render completes

**Given** a preview render completes for the current composition state
**When** the result is applied
**Then** the preview reflects center/scale, layer order, grid, and background close to final export expectations
**And** the applied result is not older than the current composition revision

**Given** preview rendering fails
**When** the error state is shown
**Then** the UI displays a Vietnamese message and actionable remediation where possible
**And** the Operator can continue editing the composition

### Story 3.7: Implement Review Action Bar and Keyboard Workflow

As an Operator,
I want review actions and keyboard shortcuts for include, skip, and previous,
So that I can process many compositions efficiently without losing validation safety.

**Requirement References:** FR7, FR18, UX-DR10, UX-DR14, UX-DR15, NFR7

**Acceptance Criteria:**

**Given** a composition is selected
**When** the Review Action Bar is shown
**Then** it provides Previous, Skip, Include/Validate, and Revalidate actions where applicable
**And** there is only one primary action for the current review context

**Given** the Operator presses Right or clicks Include/Validate
**When** the validation service contract returns a passing gate result
**Then** the app applies the include/ready transition through workspace services
**And** advances according to the review queue behavior

**Given** the Operator presses Right or clicks Include/Validate
**When** the validation service contract returns blocking issues
**Then** the app does not mark the composition ready or included
**And** it keeps the composition selected and exposes the returned blocking issues
**And** this story wires the UI to the validation contract while Epic 4 implements the full validation rules

**Given** the Operator presses Up or clicks Skip
**When** the skip action is valid
**Then** the app marks the composition reviewed but not included
**And** persists the transition through `WorkspaceService`

**Given** the Operator presses Left or clicks Previous
**When** a previous composition exists
**Then** the app navigates back without changing include/ready status unless an explicit action is taken
**And** keyboard shortcuts do not fire while a text input needs arrow keys for editing

## Epic 4: Validation, Warnings, and Metadata Correction

**Goal:** Operator thấy lỗi/warning đúng ngữ cảnh, có remediation tiếng Việt, có thể sửa metadata layer, và app chặn ready/export khi có lỗi blocking.

### Story 4.1: Define Validation Engine and Issue Schema

As an Operator,
I want validation results to be structured and actionable,
So that every warning or error clearly explains what is wrong and how to fix it.

**Requirement References:** FR8, FR17, FR19, AR3, AR6, UX-DR9, NFR6

**Acceptance Criteria:**

**Given** validation detects a problem in project, target, composition, or layer data
**When** an issue is created
**Then** it includes `issue_id`, `severity`, `scope`, target/composition/layer references where applicable, Vietnamese message, Vietnamese remediation, and `blocking`
**And** `severity=error` maps to blocking behavior unless explicitly modeled otherwise

**Given** an issue is serialized or passed to UI components
**When** it is consumed by tree, layer, warning panel, or export preflight
**Then** the same issue schema is used across modules
**And** UI components do not invent independent issue shapes

**Given** validation logic runs in core services
**When** tests instantiate the validation service
**Then** the service can run without Qt widget dependencies
**And** fixtures can assert issue IDs, severity, blocking flag, and Vietnamese remediation text

**Given** multiple issues are produced for one composition
**When** a validation summary is computed
**Then** it includes aggregate warning/error counts and blocking status
**And** the detailed issue list can be recomputed later from current state

### Story 4.2: Validate Composition Readiness Rules

As an Operator,
I want the app to check whether a composition is actually ready,
So that invalid slides cannot be marked ready or exported by accident.

**Requirement References:** FR10, FR12, FR14, FR17, FR18, FR20, NFR6

**Acceptance Criteria:**

**Given** a composition has no visible layers
**When** readiness validation runs
**Then** it produces a blocking error tied to the composition/layer stack
**And** the remediation tells the Operator to enable at least one valid layer

**Given** visible layers cannot produce a valid time label because required capture date/time is missing or invalid
**When** readiness validation runs
**Then** it produces a blocking error tied to the affected layer(s)
**And** the remediation points to metadata correction

**Given** grid override, view center/scale, or map frame settings are invalid
**When** readiness validation runs
**Then** it produces blocking issues where the invalid state would affect render/export correctness
**And** the issue references the composition and field area where the fix is needed

**Given** target-specific PPTX template or required element-id mapping is missing or invalid for the composition target
**When** readiness or export validation checks template readiness
**Then** it produces a blocking error
**And** the issue explains that the target PPTX reference or element-id mapping must be fixed

**Given** a composition has `needs_revalidation=true`
**When** readiness status is evaluated
**Then** the app does not treat previous validation summary as proof of readiness
**And** revalidation is required before ready/include/export decisions

### Story 4.3: Run Validation on Select, Include, and Export Preflight

As an Operator,
I want validation to run at the moments where decisions are made,
So that stale or invalid state cannot slip into ready or export output.

**Requirement References:** FR8, FR18, FR21, AR4, NFR2

**Acceptance Criteria:**

**Given** the Operator selects a composition
**When** selection completes
**Then** detailed validation issues are recomputed for that composition
**And** validation summary is persisted through `WorkspaceService`

**Given** the Operator presses Right or clicks Include/Validate
**When** validation passes with no blocking errors
**Then** the app may set ready/include according to review workflow rules
**And** the validation summary records the passing state

**Given** the Operator presses Right or clicks Include/Validate
**When** validation returns a blocking error
**Then** the app does not set `ready=true` or `include=true`
**And** the selected composition remains active for correction

**Given** export preflight starts
**When** included compositions are checked
**Then** detailed validation is recomputed for each included composition
**And** any blocking error prevents export from starting

**Given** validation details are recomputed
**When** the workspace is saved
**Then** only the summary is persisted in composition JSON
**And** detailed issues remain derived state for the current app session/UI

### Story 4.4: Surface Issues in Tree, Layer UI, and Warnings Panel

As an Operator,
I want issues shown where I can act on them,
So that I can jump from a warning or error to the related target, composition, or layer.

**Requirement References:** FR9, FR17, FR19, UX-DR4, UX-DR6, UX-DR9, UX-DR14, NFR7

**Acceptance Criteria:**

**Given** validation issues exist for a composition
**When** the Review/Edit tree renders
**Then** tree rows show severity icons, issue counts, and status text without relying on color alone
**And** tooltips or detail affordances expose the issue summary

**Given** an issue belongs to a layer
**When** the layer stack renders
**Then** the affected layer row shows a non-color-only issue indicator
**And** the indicator can expose the Vietnamese message/remediation

**Given** the Warnings panel is open
**When** issues are listed
**Then** each issue row shows severity icon, message, scope label, target/composition/layer reference, remediation, and jump action
**And** row content remains readable at the supported desktop minimum width

**Given** the Operator activates a jump action from an issue row
**When** the referenced object exists
**Then** the app navigates to the relevant target/composition/layer and selects or highlights it
**And** if the object no longer exists, the UI explains that the issue reference is stale

### Story 4.5: Implement Metadata Editor for Capture Date/Time Correction

As an Operator,
I want to correct layer capture metadata manually,
So that imagery without complete metadata can still produce valid slide time labels.

**Requirement References:** FR8, FR14, FR22, UX-DR11, NFR6

**Acceptance Criteria:**

**Given** a selected layer has parsed or missing metadata
**When** the Metadata Editor opens
**Then** it shows capture date/time fields, parsed source display, cloud percent, metadata source/status, and save/cancel actions
**And** the UI distinguishes parsed, manually corrected, and needs-manual-correction states

**Given** the Operator enters a valid capture date/time
**When** the change is saved
**Then** the layer metadata is persisted through `WorkspaceService`
**And** `metadata_status` and metadata source reflect manual correction

**Given** the Operator enters an invalid date/time or required metadata remains missing
**When** they attempt to save
**Then** the editor shows a Vietnamese validation message
**And** invalid metadata is not persisted as valid corrected metadata

**Given** layer metadata changes
**When** the composition is saved
**Then** the composition is marked `needs_revalidation=true`
**And** preview/time label state is refreshed or marked stale as appropriate

### Story 4.6: Confirm Cache Move When Corrected Date Changes

As an Operator,
I want date corrections that affect cache grouping to be explicit,
So that manual metadata fixes do not silently move files or change composition grouping.

**Requirement References:** FR2, FR4, FR6, FR8, FR14, AR4, AR5, NFR2, NFR9

**Acceptance Criteria:**

**Given** the Operator changes a layer capture date to a different target-date grouping
**When** they save the correction
**Then** the app shows a confirmation dialog before moving cached files or regrouping the layer
**And** the safe/default action cancels the move/regroup operation

**Given** the Operator confirms the date-changing correction
**When** the app applies it
**Then** cached path references, composition layer membership, and affected composition summaries are updated through workspace services
**And** the operation is atomic enough that failed updates do not leave invalid composition JSON

**Given** the move or regroup operation cannot be completed safely
**When** the app detects the failure
**Then** it blocks the correction from being treated as fully applied
**And** it shows Vietnamese remediation explaining how to resolve the file/workspace issue

**Given** a date correction changes which composition should contain the layer
**When** regrouping completes
**Then** source and destination compositions are marked `needs_revalidation=true`
**And** review/include status is not silently promoted by the metadata correction

## Epic 5: Rendering Pipeline and Map Output Fidelity

**Goal:** Operator có preview đáng tin và app tạo được PNG final từ composition state, với shared render math, grid/background/layer order đúng, preview/final alignment, và render job không apply stale result.

### Story 5.1: Build Shared Render Specification from Composition State

As a Developer,
I want a shared render specification derived from composition state,
So that preview and final rendering use the same source of truth.

**Requirement References:** FR12, FR13, FR15, FR16, AR6, AR9

**Acceptance Criteria:**

**Given** a composition, target config, target PPTX map-frame bounds, and requested output size are available
**When** the render spec builder runs
**Then** it produces a normalized render spec containing view center, scale denominator, template map-frame physical size/aspect, derived geographic map window, visible layers in draw order, grid settings, background settings, output dimensions, and template references
**And** the spec uses composition `view.center` `[lon, lat]` and `view.scale` as the persisted source of truth, interpreting scale as the map scale denominator

**Given** a composition has hidden layers or custom layer ordering
**When** the render spec is built
**Then** hidden layers are excluded from drawing
**And** visible layers preserve persisted layer order from the composition

**Given** a composition has a per-composition grid override
**When** the render spec is built
**Then** the override is used instead of target defaults
**And** target defaults remain unchanged

**Given** required render inputs are missing or invalid
**When** the render spec builder runs
**Then** it returns structured errors or issues rather than partially rendering unknown state
**And** the render code remains usable in tests without Qt widget dependencies

### Story 5.2: Implement Raster Window and CRS Transform Rendering Core

As an Operator,
I want raster imagery rendered from the selected target-centered map view,
So that the map output matches the area I framed in Review/Edit.

**Requirement References:** FR11, FR15, AR8, AR9, NFR1

**Acceptance Criteria:**

**Given** the render spec contains view center, scale denominator, derived geographic map window, and visible raster layers
**When** the rendering core prepares a layer
**Then** it uses rasterio/GDAL metadata and `pyproj` transformations as needed to convert the derived geographic map window to the raster CRS/read window
**And** it handles rasters whose CRS differs from the geographic CRS used by composition view center

**Given** multiple visible layers overlap the output area
**When** the renderer composites them
**Then** it draws layers in the render spec order with the newest/default-top behavior preserved when no user override exists
**And** hidden layers do not affect the output pixels

**Given** the derived map window only partially overlaps a raster
**When** the renderer reads the raster window
**Then** it clips to available raster bounds
**And** fills non-covered areas with configured background rather than failing the whole render

**Given** a raster cannot be opened or read during rendering
**When** rendering reaches that layer
**Then** the renderer returns a structured render error or issue with the affected layer reference
**And** callers can decide whether preview shows an error or validation blocks export

### Story 5.3: Render Grid and Map Background Without MVP Extras

As an Operator,
I want grid labels and map background rendered consistently,
So that the exported map follows the configured slide style without unsupported extras.

**Requirement References:** FR12, FR15, AR13

**Acceptance Criteria:**

**Given** the render spec includes grid settings
**When** the map is rendered
**Then** the renderer draws grid lines and labels according to interval and label format, defaulting to `dms_full` where configured
**And** labels align with the rendered geographic map window

**Given** the render spec includes background settings
**When** raster coverage does not fill the whole output frame
**Then** uncovered areas render using the configured background
**And** the output does not expose transparent or uninitialized pixels unless explicitly configured

**Given** MVP render output is requested
**When** rendering completes
**Then** boundary overlay, north arrow, and scale bar are not rendered
**And** tests or render log make this MVP behavior explicit to avoid accidental inclusion

**Given** grid settings are invalid
**When** the renderer attempts to draw the grid
**Then** rendering returns a structured error rather than silently drawing an incorrect grid
**And** the error can be surfaced as a Vietnamese remediation through validation/UI layers

### Story 5.4: Implement Two-Stage Preview Rendering Jobs

As an Operator,
I want preview rendering to update quickly while I edit,
So that pan/zoom/layer changes feel responsive without sacrificing settled preview quality.

**Requirement References:** FR13, FR16, AR7, UX-DR7, UX-DR8, NFR1

**Acceptance Criteria:**

**Given** the Operator changes layer visibility/order, view center/scale, grid, or metadata affecting preview
**When** preview rendering is requested
**Then** the app schedules a low-resolution interactive preview first
**And** schedules a settled higher-resolution preview after debounce

**Given** the Operator continues editing while preview jobs are running
**When** an older preview job completes after a newer request exists
**Then** the app ignores the stale result
**And** only applies results matching the current composition/render revision

**Given** a preview render is running in a background job
**When** progress or result updates are emitted
**Then** updates are delivered safely to the Qt main thread
**And** core render services remain independent from Qt widgets

**Given** preview rendering fails
**When** the preview panel receives the failure
**Then** it shows render_error state with actionable Vietnamese text where possible
**And** the Operator can continue editing and trigger a later preview

### Story 5.5: Implement Final PNG Rendering and Render Log

As an Operator,
I want final map PNGs generated at template output quality,
So that exported PPTX slides use reliable image assets.

**Requirement References:** FR15, FR16, FR21, AR12, NFR4

**Acceptance Criteria:**

**Given** a composition passes render readiness validation
**When** final render runs
**Then** it creates a PNG using target config, target PPTX map-frame bounds, output size, visible layers, view center/scale, coordinate frame labels, background, and map frame aspect from the shared render spec
**And** the output dimensions match the requested template output quality

**Given** final PNG rendering succeeds
**When** the result is recorded
**Then** the render log includes output path, PNG width/height, composition reference, render spec revision or hash, visible layer references, and timestamp
**And** the composition can reference the final render artifact through workspace-relative path where possible

**Given** final rendering fails
**When** the failure is recorded
**Then** the render log includes the composition reference and failure reason
**And** export can block or skip according to preflight/export rules rather than embedding a missing image

**Given** final render output already exists for an older composition revision
**When** the composition state has changed
**Then** the app treats the prior render as stale
**And** a fresh final render is required before export uses the asset

### Story 5.6: Verify Preview/Final Alignment with Fixtures

As a Developer,
I want tests that compare preview and final render behavior,
So that future changes do not break map output fidelity.

**Requirement References:** FR13, FR15, FR16, AR13

**Acceptance Criteria:**

**Given** test fixtures include config, GeoJSON, GeoTIFF, target PPTX/export mapping, and workspace composition data
**When** render tests run
**Then** they cover render spec creation, raster window selection, layer ordering, grid rendering, and final PNG output
**And** tests can run without launching the Qt UI

**Given** the same composition state is rendered as preview and final output
**When** alignment checks compare the two outputs at appropriate tolerances
**Then** they confirm center/scale, layer order, grid placement, and background behavior remain consistent
**And** known resolution differences between preview and final are accounted for explicitly

**Given** a composition includes hidden layers and reordered visible layers
**When** fixtures are rendered
**Then** tests verify hidden layers do not appear and visible order affects output as expected
**And** newest-on-top default behavior is covered when no manual order override exists

**Given** invalid render inputs are supplied in fixtures
**When** render services run
**Then** tests assert structured errors or issues are returned
**And** no partial final PNG is treated as successful output

## Epic 6: Report Export and Completion Evidence

**Goal:** Operator có thể chạy preflight, xem export plan, xuất một PPTX tổng hợp + TXT theo review_order, dùng target-specific one-slide PPTX template với replacement theo element id, và nhận summary/log rõ ràng sau export.

### Story 6.1: Load Target-Specific One-Slide PowerPoint Templates

As an Operator,
I want each target to point directly to its own one-slide PowerPoint template,
So that report slides can follow target-specific layout rules and replace known PPTX elements by id while still exporting into one combined PPTX.

**Requirement References:** FR20, FR21, AR10, AR12, NFR6

**Acceptance Criteria:**

**Given** a target config references a `template_pptx_file`
**When** export preparation loads the target
**Then** it resolves the target-specific PPTX path relative to the config file
**And** it validates the PPTX contains exactly one template slide for export use
**And** it loads the configured PPTX element-id mapping for map frame and text/image placeholders from target export config

**Given** target export config maps report fields to PowerPoint element ids
**When** placeholders are resolved
**Then** element id lookup is the primary replacement mechanism
**And** shape names may be recorded only as diagnostics for human troubleshooting, not as the authoritative lookup key

**Given** the referenced PPTX is missing, has zero slides, has more than one slide, or lacks a required element id
**When** preflight validates the target
**Then** it creates a blocking issue tied to the target/composition using that template
**And** the Vietnamese remediation explains which PPTX path or element-id mapping must be fixed

**Given** multiple targets use different template files
**When** export preflight checks compatibility
**Then** it verifies the templates satisfy the documented compatible base/theme/master assumption where the implementation can detect it
**And** incompatibility or unknown compatibility is surfaced before export rather than failing silently during slide copy

### Story 6.2: Build Export Preflight and Export Plan UI

As an Operator,
I want to see a preflight summary and export plan before exporting,
So that I can fix blocking issues and understand exactly what will be generated.

**Requirement References:** FR18, FR20, FR21, FR22, FR23, UX-DR12, UX-DR13, UX-DR14

**Acceptance Criteria:**

**Given** the Operator enters Export mode
**When** export preflight runs
**Then** it validates included compositions, target-specific PPTX templates, required element-id mappings, required renders, TXT placeholders, and blocking composition issues
**And** it recomputes detailed validation for included compositions rather than trusting stale summaries

**Given** preflight completes
**When** the Export Summary Metrics are shown
**Then** they include included slides, target count, skipped count, warning count, error count, and preflight state
**And** blocking errors disable the final export action with a tooltip or message explaining why

**Given** included compositions are available
**When** the Export Plan is rendered
**Then** each row shows slide number, target alias/title, date/time label, template status, issue count, and jump back action to the composition
**And** rows are sorted by `review_order`

**Given** a plan row has an issue
**When** the Operator activates its jump action
**Then** the app navigates back to the related Review/Edit composition or target context
**And** the issue remains visible for correction

### Story 6.3: Generate Final Renders for Included Compositions

As an Operator,
I want export to use current final map renders,
So that the PPTX contains the same map state I approved during review.

**Requirement References:** FR15, FR16, FR21, FR23, NFR4

**Acceptance Criteria:**

**Given** an included composition has no current final PNG render
**When** export preparation runs
**Then** the app requests final rendering using the shared render pipeline from Epic 5
**And** export waits for a successful current render before using the image

**Given** an included composition has a stale final render
**When** preflight or export detects the stale revision
**Then** it schedules or requires a fresh render
**And** it does not embed the stale PNG into PPTX output

**Given** final render generation fails for an included composition
**When** export preparation records the result
**Then** export is blocked or the composition is skipped only according to explicit preflight/export rules
**And** the failure appears in summary/log with composition reference and remediation where possible

**Given** final render succeeds
**When** export continues
**Then** the PPTX export receives the workspace-relative or resolved final PNG path
**And** the render log can trace the PNG to its composition and render spec revision

### Story 6.4: Export Combined PPTX from Target-Specific Sample Slides

As an Operator,
I want one combined PowerPoint report created from target-specific sample slides,
So that the final report is ordered and ready for delivery.

**Requirement References:** FR20, FR21, AR10, AR13

**Acceptance Criteria:**

**Given** preflight has passed and final renders exist for included compositions
**When** PPTX export runs
**Then** it creates one combined PPTX containing one slide per included composition
**And** slides are ordered by composition `review_order`

**Given** each included composition belongs to a target
**When** its slide is created
**Then** the exporter copies the only slide from that target's template PPTX
**And** replaces the map image placeholder with the composition final PNG

**Given** text placeholders are configured as PPTX element-id mappings in target export config
**When** the exporter creates a slide
**Then** it replaces configured placeholders using composition, target, layer/time label, and export context values
**And** unresolved required placeholders create blocking export errors

**Given** PowerPoint slide-copy logic is needed
**When** the implementation adds it
**Then** risky copy behavior is isolated in `export/pptx_slide_copy.py`
**And** an initial vertical-slice test covers at least one target, one sample slide, and one exported slide

### Story 6.5: Export TXT Report Lines

As an Operator,
I want a TXT report generated alongside the PPTX,
So that each included composition has a corresponding text line for downstream reporting.

**Requirement References:** FR14, FR21, FR22, AR13

**Acceptance Criteria:**

**Given** included compositions are sorted by `review_order`
**When** TXT export runs
**Then** it writes one line per included composition in the same order as the PPTX slides
**And** each line is rendered from the configured `txt_line_template`

**Given** the TXT template references required placeholders
**When** placeholder values are resolved
**Then** missing required values produce validation/export errors
**And** export does not silently write unresolved placeholder tokens

**Given** the TXT template references optional placeholders
**When** optional values are missing
**Then** they render empty only when marked optional by configuration
**And** this behavior is covered by tests or export validation fixtures

**Given** a line requires a time label
**When** the line is rendered
**Then** the time label comes from visible valid layers according to composition state
**And** unresolved metadata required for the time label blocks export with remediation pointing to metadata correction

### Story 6.6: Write Export Summary and Trace Log

As an Operator,
I want export summary and logs written next to the output files,
So that I can verify what was generated and diagnose skipped or failed items.

**Requirement References:** FR23, NFR4, NFR6

**Acceptance Criteria:**

**Given** export completes successfully, with warnings, or with recoverable skipped items
**When** the export summary is shown and written
**Then** it includes slide count, target count, skipped count, warnings, errors if any, PPTX output path, TXT output path, and log path
**And** the UI distinguishes success, success-with-warnings, and failure states

**Given** compositions are exported or skipped
**When** the trace log is written
**Then** it maps each composition to PPTX slide number, TXT line number, exported/skipped status, and skipped reason where applicable
**And** it includes an issue summary for warnings/errors encountered during preflight/export

**Given** an output file cannot be written due to permission, locked file, or missing folder
**When** export attempts to write it
**Then** the app reports a blocking export error with Vietnamese remediation
**And** it does not report export success for incomplete outputs

**Given** export artifacts are written into the workspace or selected output folder
**When** the operation finishes
**Then** output paths are recorded in workspace/export state or export log as appropriate
**And** the Operator can inspect the files outside the application

## Epic 7: Post-MVP Hardening and Distribution Readiness

**Goal:** Operator có output bản đồ và export template ổn định hơn theo dữ liệu thực tế, đồng thời dự án có bước chuẩn bị đóng gói Windows executable.

### Story 7.1: Implement Map Surround Layout

As an Operator,
I want preview and final map output to use the same map-surround structure as the PPTX template,
So that exported map images align visually with the intended report design.

**Requirement References:** FR13, FR15, FR16, AR15, NFR1

**Acceptance Criteria:**

**Given** a valid render spec
**When** `render_map()` returns an image
**Then** the canvas dimensions remain `spec.output_width x spec.output_height`
**And** the output includes a white surround, outer frame, inner raster panel, and DMS coordinate labels.

**Given** GIS Editor displays a completed render
**When** the render pixmap is shown
**Then** it displays the full map-surround image without adding a second decorative frame.

**Current Status:** done. Implementation tracked in `_bmad-output/implementation-artifacts/spec-map-surround-layout.md`.

### Story 7.2: Expose Frame Render Defaults in Config

As an Operator,
I want frame layout and label defaults visible in `config.json`,
So that render defaults can be reviewed and tuned without editing private Python constants.

**Requirement References:** FR12, FR15, AR15

**Acceptance Criteria:**

**Given** `config.json` has `defaults.grid.style`
**When** target grid style is resolved
**Then** the renderer receives configured defaults for supported label formats, frame tick limits, reference geometry, stroke widths, tick lengths, label font size, and label font path.

**Given** a minimal test config omits those style values
**When** render code resolves frame settings
**Then** safe fallback defaults preserve existing behavior.

**Current Status:** done. Implementation tracked in `_bmad-output/implementation-artifacts/spec-configurable-frame-defaults.md`.

### Story 7.3: Auto-Resolve PPTX Placeholders from Shape Metadata

As an Operator,
I want the app to recover template placeholder mappings when PowerPoint changes shape ids,
So that changing a PPTX template does not require manually repairing every target config id.

**Requirement References:** FR20, FR21, AR16, NFR6

**Acceptance Criteria:**

**Given** config contains stale element ids and the PPTX shapes are named `ttn:<field>`
**When** project config loads
**Then** target template metadata resolves placeholders to current PPTX element ids before export validation.

**Given** two shapes match the same required placeholder
**When** config loads
**Then** the loader emits a blocking ambiguity issue instead of guessing.

**Given** a legacy template still has valid configured ids
**When** no stable selector/name match exists
**Then** the configured element ids remain supported.

**Current Status:** done. Implementation tracked in `_bmad-output/implementation-artifacts/spec-pptx-placeholder-auto-match.md`.

### Story 7.4: Package Windows Executable Tooling

As an Operator,
I want a repeatable Windows `.exe` packaging command,
So that the desktop app can be prepared for use outside the development shell.

**Requirement References:** AR17, NFR5

**Acceptance Criteria:**

**Given** the project is checked out on Windows with Miniconda
**When** `scripts/build_windows_exe.ps1` runs in `ttn-env`
**Then** PyInstaller builds `dist\ThucTheNgay\ThucTheNgay.exe` by default
**And** the script runs `ThucTheNgay.exe --smoke` unless `-SkipSmoke` is provided.

**Given** the app depends on PySide6/GDAL/rasterio
**When** the executable starts
**Then** bundled PROJ/GDAL data and relevant native DLL paths are configured before runtime imports.

**Current Status:** review. Tooling exists, but final Windows `.exe` build and packaged smoke verification must be run on Windows before this story can be marked `done`.

## Epic 8: Config Manager Tab

**Goal:** Operator có thể tạo, mở, kiểm tra, chỉnh sửa, backup và lưu `config.json` bằng giao diện trong app, quản lý target/group/defaults/patterns/geometry an toàn, và không cần sửa JSON thô cho các thao tác thường ngày.

### Story 8.1: Build Config Editor Service and Draft State

As an Operator,
I want config editing to go through a safe service layer,
So that UI changes can be validated, saved, backed up, or discarded without corrupting `config.json`.

**Requirement References:** CM-FR1, CM-FR2, CM-AR1, CM-AR2, NFR2, NFR6, NFR9

**Acceptance Criteria:**

**Given** an existing `config.json`
**When** `ConfigEditorService` loads it
**Then** the service exposes persisted config, draft config, validation result, source path, dirty state, and summary metrics
**And** config-relative paths continue to resolve consistently with existing `ConfigService`.

**Given** no config is loaded
**When** the Operator creates a new config
**Then** the service creates a valid minimal draft with defaults, filename patterns, and an empty target list
**And** the draft is marked dirty until saved.

**Given** a draft has been edited
**When** save, save-as, or backup is requested
**Then** writes are atomic
**And** backup filenames use a timestamped pattern such as `config.backup.YYYYMMDD-HHMMSS.json`
**And** failed writes leave the previous persisted file intact.

**Given** a draft has validation issues
**When** validation runs
**Then** the service returns structured issues with severity, issue id, Vietnamese message/remediation, and target/group context where available
**And** the UI can distinguish blocking errors from warnings.

### Story 8.2: Add Config Tab Shell, Toolbar, and Status Summary

As an Operator,
I want a dedicated Config tab with clear file actions and status,
So that I know which config is loaded and whether changes are safe to use downstream.

**Requirement References:** CM-FR1, CM-FR2, CM-FR8, CM-UX1, UX-DR1, UX-DR14, UX-DR16

**Acceptance Criteria:**

**Given** the app shell is shown
**When** the main tabs are rendered
**Then** `Config` appears in the main flow between `Setup` and `Review/Edit`
**And** the tab uses the approved layout from `config-manager-ui-mockup.html`.

**Given** the Config tab is active
**When** no config is loaded
**Then** the toolbar offers `Tạo mới`, `Mở config`, and disabled save-dependent actions
**And** the page explains the empty state through concise labels rather than raw JSON.

**Given** a config is loaded
**When** the Operator edits, validates, reloads, saves, saves-as, or backs up
**Then** toolbar buttons and status pills reflect loaded path, dirty state, validation state, warnings, and blocking errors
**And** reload prompts before discarding unsaved changes.

**Given** summary stats are visible
**When** targets, groups, geometry, templates, or validation issues change
**Then** stats update for target count, enabled count, group count, unique PPTX templates, geometry count, and warning/error count.

### Story 8.3: Implement Group Sidebar and Target Table

As an Operator,
I want to browse config targets by group and inspect their status in a table,
So that large configs remain easy to scan and adjust.

**Requirement References:** CM-FR3, CM-UX1, CM-UX2, UX-DR14, UX-DR15, UX-DR16

**Acceptance Criteria:**

**Given** a config has target groups
**When** the Config tab loads
**Then** the left sidebar lists groups by `group.key` order with `group.title`, key, and target count
**And** group rows provide visible selected state without relying on color alone.

**Given** the Operator selects a group or filter
**When** the target table refreshes
**Then** it shows only matching targets
**And** targets within the selected group are sorted by their local `sort_order`.

**Given** the target table is shown
**When** rows are rendered
**Then** the columns are `Bật`, `Order`, `ID`, `Tên hiển thị`, `Alias`, `Scale`, `Grid`, and `Status`
**And** the target toolbar contains `Thêm target` without `Nhân bản`, `Đánh lại sort_order`, or `Di chuyển group`.

**Given** the Operator selects a target row
**When** the selection changes
**Then** the Target Inspector displays that target
**And** related validation issues can be highlighted or navigated to.

### Story 8.4: Implement Target Inspector Editing and Delete

As an Operator,
I want to edit the selected target in an inspector,
So that target details can be corrected without touching JSON.

**Requirement References:** CM-FR4, CM-FR5, CM-UX1, CM-UX2, CM-UX3, NFR6, NFR9

**Acceptance Criteria:**

**Given** a target is selected
**When** the inspector opens
**Then** it shows editable fields for `id`, `enabled`, `group.key`, `sort_order`, `name`, `alias`, `coordinate`, `scale`, target grid interval, export template/TXT, and placeholder values
**And** it offers `Xóa target`, `Reset`, and `Apply`.

**Given** the Operator edits target information
**When** `Apply` is clicked
**Then** changes update the in-memory draft only
**And** target-level validation runs for id uniqueness, coordinate range, positive scale, valid grid interval, group mapping, template path, TXT placeholders, and local group sort order.

**Given** the Operator clicks `Reset`
**When** unsaved inspector edits exist
**Then** the inspector reverts to the target state from the draft before those inspector edits
**And** the whole config is not reloaded from disk.

**Given** the Operator clicks `Xóa target`
**When** the target may have existing workspace compositions
**Then** a danger confirmation identifies the target id/name and warns about downstream reload/review/export impact
**And** deletion proceeds only after explicit confirmation.

**Given** the inspector shows `Placeholders`
**When** the placeholder table is rendered
**Then** it has only `field` and editable `value`
**And** it does not show an `id` column.

### Story 8.5: Implement GeoJSON Import and Export for Target Geometry

As an Operator,
I want to import and export target geometry from the inspector,
So that target boundaries can be maintained without exposing raw geometry text.

**Requirement References:** CM-FR6, CM-UX3, CM-AR1, CM-AR2, NFR6, NFR9

**Acceptance Criteria:**

**Given** a target is selected
**When** the Geometry section is rendered
**Then** it contains only `Import GeoJSON` and `Export GeoJSON`
**And** it does not show a geometry preview, geometry text box, or copy geometry button.

**Given** the Operator imports a GeoJSON file
**When** the file contains a single Geometry or single Feature
**Then** the geometry is stored in `metadata.geojson_geometry` on the draft target
**And** the target is validated immediately.

**Given** the selected target already has geometry
**When** the Operator imports a replacement geometry
**Then** the app asks for confirmation before replacing it.

**Given** the Operator exports geometry
**When** the selected target has `metadata.geojson_geometry`
**Then** the app writes a valid GeoJSON file with a suggested filename based on `target.id`
**And** export is disabled or reports a clear issue when geometry is missing.

### Story 8.6: Implement Defaults, Filename Patterns, and Raw JSON Views

As an Operator,
I want dedicated views for shared config sections,
So that default grid/export behavior and filename parsing can be managed consistently.

**Requirement References:** CM-FR7, CM-FR8, CM-UX1, UX-DR14, UX-DR16

**Acceptance Criteria:**

**Given** the Operator opens the `Defaults` sub-tab
**When** config defaults are loaded
**Then** the UI exposes default grid label format/style, frame reference values, advanced grid style values, date format, time format, and map background color
**And** changes update the draft through the config editor service.

**Given** target grid overrides exist
**When** defaults are edited
**Then** the UI clearly distinguishes shared defaults from per-target `grid.interval`
**And** it does not silently overwrite target overrides.

**Given** the Operator opens `Filename Patterns`
**When** a sample filename is tested
**Then** parsed date, parsed time, and cloud percent are shown
**And** the UI makes the `UTC filename + 7 giờ` conversion visible for filename-derived capture time.

**Given** the Operator opens `Raw JSON`
**When** the draft changes
**Then** the read-only JSON view reflects the current draft
**And** raw JSON editing is not available in the MVP.

### Story 8.7: Wire Config Validation Issues and Downstream Refresh Cues

As an Operator,
I want config problems and downstream impacts to be visible,
So that changes to targets, groups, geometry, templates, or defaults do not surprise Review/Edit and Export.

**Requirement References:** CM-FR2, CM-FR8, CM-AR1, CM-AR2, UX-DR9, UX-DR14, NFR6, NFR7

**Acceptance Criteria:**

**Given** validation issues exist
**When** the Validation Issues panel is shown
**Then** each issue row includes severity, issue id, Vietnamese message/remediation, and context
**And** blocking errors are distinguishable from warnings by text/icon as well as styling.

**Given** an issue references a target or group
**When** the Operator activates that issue
**Then** the Config tab selects the affected target or group where possible
**And** the inspector/table scrolls to the relevant item when available.

**Given** the Operator saves config changes
**When** an open workspace may be affected by changed enabled status, deleted targets, group/sort order, geometry, template, placeholders, defaults, or filename patterns
**Then** the app shows a concise refresh cue explaining which downstream area should be reloaded, re-ingested, revalidated, or preflighted.

**Given** Review/Edit or Export uses config after a Config tab save
**When** downstream code refreshes config
**Then** it receives the saved config through existing config service boundaries
**And** no downstream UI reads the config JSON file directly.

## Epic 9: Historical Image Registry and Temporal Compare View

**Goal:** Operator có thể chọn rõ có tải ảnh lịch sử hay không, dùng lại ảnh đã từng Include cho target trong các workspace trước, và khi cần có thể bật chế độ so sánh 2 thời điểm trong cùng khung bản đồ. Khi chế độ so sánh tắt, Review/Edit, render, và export giữ hành vi một khung bản đồ như hiện tại. Khi bật, khung bản đồ được chia thành 2 phần theo chiều dọc hoặc chiều ngang, mỗi phần hiển thị ảnh/layer của cùng target tại một thời điểm được chỉ định. Workspace JSON hiện tại vẫn là source of truth cho phiên làm việc; SQLite chỉ là registry tham chiếu dài hạn.

### Story 9.1: Add SQLite History Service and Registry Schema

As an Operator,
I want the app to remember included target imagery across workspaces,
So that future workspaces can reuse relevant historical images without manually searching old folders.

**Requirement References:** HIR-FR1, HIR-FR2, HIR-AR1, HIR-AR2, NFR2, NFR3, NFR5

**Acceptance Criteria:**

**Given** historical registry is enabled in config
**When** `HistoryService` opens the configured SQLite database
**Then** it creates or migrates the schema for target history, image assets, target-image links, include events, and schema version
**And** all writes run inside transactions with SQLite parameter binding.

**Given** historical registry is disabled or no database path is configured
**When** ingestion/review runs
**Then** the app continues to behave exactly like the current workspace-only workflow
**And** no SQLite file is created implicitly outside the configured/default project data location.

**Given** the database is located on a network share
**When** the service initializes SQLite pragmas
**Then** WAL mode is not forced
**And** the service uses short transactions, `foreign_keys=ON`, and a busy timeout.

**Given** core modules need registry access
**When** they load or record history
**Then** they call `HistoryService`
**And** PySide UI widgets do not query or mutate SQLite directly.

### Story 9.2: Record Included Compositions into History

As an Operator,
I want included compositions to be saved into historical registry,
So that images I approved can appear in future workspaces.

**Requirement References:** HIR-FR1, HIR-FR8, HIR-AR1, NFR4

**Acceptance Criteria:**

**Given** a composition passes validation and Include/Validate succeeds
**When** the include transition is persisted
**Then** the app records target id/name/alias, composition id, capture date/time, cloud percent, source path, cache path, and workspace path for each included layer.

**Given** a composition is skipped or validation fails
**When** review actions complete
**Then** no included-history event is recorded for that composition.

**Given** the same target/image is included again later
**When** the registry write runs
**Then** the existing target-image link is updated with latest inclusion metadata
**And** a separate include event is appended for traceability.

**Given** history recording fails after workspace include succeeds
**When** the app reports the action result
**Then** the composition remains included in the workspace
**And** the Operator sees a non-blocking warning explaining that history was not updated.

### Story 9.3: Configure Historical Loading Mode for Ingestion

As an Operator,
I want an explicit choice to load or not load historical images,
So that I can keep the current simple workflow or opt into historical comparison deliberately.

**Requirement References:** HIR-FR2, HIR-FR3, HIR-FR4, HIR-FR9, HIR-UX3, NFR5

**Acceptance Criteria:**

**Given** historical loading is disabled
**When** ingestion runs
**Then** the app scans and matches only current-session imagery
**And** no historical registry query is executed
**And** Review/Edit, render, export, and validation behave like the current workspace-only workflow.

**Given** historical loading is enabled
**When** ingestion starts
**Then** the app displays or applies the configured target scope and image selection settings before querying history.

**Given** no historical database path is configured
**When** the Operator enables historical loading
**Then** the app reports a clear validation issue or setup message
**And** does not silently fall back to an unknown database location.

**Given** the historical loading mode is changed in config or setup UI
**When** downstream code reads the setting
**Then** it receives the saved value through config/service boundaries
**And** no PySide widget reads or writes config JSON directly.

### Story 9.4: Load Historical Imagery into New Workspace Ingestion

As an Operator,
I want new workspaces to include relevant historical imagery for targets in scope,
So that I can compare current and previous satellite scenes in the same review queue.

**Requirement References:** HIR-FR2, HIR-FR3, HIR-FR4, HIR-FR5, HIR-FR9, HIR-AR3, HIR-UX1

**Acceptance Criteria:**

**Given** current-session imagery has been matched to targets
**When** historical loading runs with `target_scope=targets_with_current_matches`
**Then** history is queried only for targets that have at least one current-session match.

**Given** historical loading runs with `target_scope=all_enabled_targets`
**When** ingestion creates composition inputs
**Then** history is queried for every enabled target in the loaded config.

**Given** `image_selection.mode=latest_date`
**When** history is queried for a target
**Then** all available historical images from that target's latest capture date are loaded.

**Given** `image_selection.mode=latest_images`
**When** `limit_per_target` is set
**Then** only the newest N historical images for each target are loaded.

**Given** `image_selection.mode=date_range`
**When** `start_date` and `end_date` are set
**Then** only historical images with capture dates inside the inclusive range are loaded.

**Given** `image_selection.mode=lookback_days`
**When** an anchor is configured as `today` or `current_session_latest_date`
**Then** only historical images inside the computed lookback window are loaded.

**Given** a historical image is also present in current-session matches
**When** composition inputs are merged
**Then** the image appears only once for the same target/date.

### Story 9.5: Validate and Repair Historical Image Paths

As an Operator,
I want missing historical paths to be detected and repairable,
So that moved LAN/local imagery can be reused without corrupting the current workspace.

**Requirement References:** HIR-FR6, HIR-FR7, HIR-UX2, NFR6, NFR7, NFR9

**Acceptance Criteria:**

**Given** a historical image path no longer exists
**When** historical loading validates registry entries
**Then** the app creates a structured warning issue with target, image, path, Vietnamese message, and remediation
**And** the missing image is not copied into workspace cache until repaired.

**Given** a historical image path exists but cannot be opened as a usable GeoTIFF
**When** validation runs
**Then** the app creates a structured warning or error issue based on whether review/export can safely continue.

**Given** the Operator repairs one missing image path
**When** the selected replacement file is accepted
**Then** the app revalidates the file, updates the registry path in a transaction, and refreshes the affected workspace issue.

**Given** many historical paths share an old prefix
**When** the Operator applies a bulk path-prefix replacement
**Then** the app previews affected rows and requires explicit confirmation before updating the registry.

### Story 9.6: Surface Historical Imagery Status in Review/Edit and Ingest Summary

As an Operator,
I want historical imagery to be visibly distinguishable from current-session imagery,
So that I understand which layers are new, historical, missing, or repaired while reviewing.

**Requirement References:** HIR-UX1, HIR-UX2, UX-DR3, UX-DR6, UX-DR9, UX-DR14, UX-DR15

**Acceptance Criteria:**

**Given** ingestion completes with historical loading enabled
**When** the summary is shown
**Then** it displays current images scanned, current images matched, historical images loaded, historical images skipped, and historical path issues.

**Given** a composition contains historical layers
**When** the layer stack is rendered
**Then** each layer shows a text/icon source indicator such as current or historical
**And** status does not rely on color alone.

**Given** historical path issues exist
**When** the Warnings panel is rendered
**Then** issue rows identify the affected target/composition/layer and offer navigation or repair where available.

**Given** historical settings produce no matching historical imagery
**When** ingestion completes
**Then** the app reports that no historical images matched the configured target scope and image selection
**And** this is informational rather than blocking.

### Story 9.7: Add Temporal Compare Controls in Review/Edit

As an Operator,
I want to enable a two-time comparison for the selected target,
So that I can choose which current or historical image appears in each map pane.

**Requirement References:** HIR-FR10, HIR-FR11, HIR-FR12, HIR-UX4, HIR-UX5, UX-DR3, UX-DR6, UX-DR14

**Acceptance Criteria:**

**Given** a composition is selected in Review/Edit
**When** comparison mode is off
**Then** the GIS canvas, layer stack, grid controls, Include/Validate behavior, and export preview remain the current single-map workflow.

**Given** comparison mode is enabled
**When** the comparison control panel is shown
**Then** it exposes only these primary controls: enable/disable comparison, split orientation, Pane A image/time, and Pane B image/time.

**Given** comparison mode is enabled
**When** the Operator selects split orientation
**Then** `vertical` shows left/right panes
**And** `horizontal` shows top/bottom panes.

**Given** current and historical imagery are available for the selected target
**When** the Operator opens the Pane A or Pane B selector
**Then** options are grouped or labelled by capture date/time
**And** each option shows current/historical source, cloud percent where available, and missing/unreadable status where relevant.

**Given** fewer than two usable images are available for the selected target
**When** comparison mode is enabled
**Then** the UI explains that two usable time points are required
**And** this does not block normal single-map review when comparison mode is disabled.

**Given** the Operator changes comparison pane selection or orientation
**When** the change is saved
**Then** the comparison state is persisted in workspace/composition state through `WorkspaceService`
**And** the composition is marked for revalidation when the change affects render/export output.

### Story 9.8: Render and Export Split Map Frame for Temporal Comparison

As an Operator,
I want the final map output to show two selected time points in one split map frame,
So that the exported report can compare target imagery across time without manual PowerPoint editing.

**Requirement References:** HIR-FR10, HIR-FR11, HIR-FR12, HIR-AR4, HIR-UX5, AR15, NFR2, NFR3

**Acceptance Criteria:**

**Given** comparison mode is disabled
**When** preview or final render runs
**Then** the renderer uses the existing single-map `RenderSpec` behavior.

**Given** comparison mode is enabled with valid Pane A and Pane B selections
**When** preview render runs
**Then** the GIS canvas shows the map frame split according to the selected orientation
**And** each pane renders only the selected image/layer set for its configured time point.

**Given** comparison mode is enabled
**When** final render/export runs
**Then** the exported map image uses the same comparison state as Review/Edit preview
**And** PPTX export inserts the split comparison render into the existing map placeholder.

**Given** comparison mode is enabled
**When** grid/frame rendering is applied
**Then** each pane has clear map-frame boundaries and coordinate context
**And** pane labels identify target, capture date/time, current/historical source, and cloud percent where available.

**Given** a selected historical image becomes missing or unreadable
**When** validation/preflight runs
**Then** the app creates a structured issue pointing to the affected pane and layer
**And** export is blocked only when the selected comparison output cannot be rendered safely.

**Given** comparison rendering processes large rasters
**When** preview/final render runs
**Then** existing cancellation, cache, max-pixel, and memory safeguards continue to apply
**And** PySide widgets do not duplicate render business logic.

## Epic 10: Satellite Image Download Tab

**Goal:** Operator co the chon nhieu file GeoJSON, nhieu folder anh nguon, va mot folder output de tai/copy anh ve tinh giao cat voi khu vuc quan tam ngay trong app. Ket qua duoc luu theo cau truc `<output>/<geojson_name>/<source_folder_name>/...`, co progress, manifest, loi/remediation ro rang, va khong lam thay doi workspace ingestion hien tai cho den khi Operator chu dong dung output do lam input.

### Story 10.1: Extract Reusable Satellite Download Engine

As a Developer,
I want the existing satellite download script logic extracted into a reusable core service,
So that the app can run the same scan/intersection/copy workflow without embedding business logic in PySide widgets.

**Requirement References:** SDT-FR5, SDT-FR8, SDT-FR13, SDT-AR1, SDT-AR4, AR2, AR8

**Acceptance Criteria:**

**Given** the app needs to run satellite download from UI and tests
**When** the reusable download module is added
**Then** it exposes typed request/result/progress models for GeoJSON files, image folders, output folder, extensions, filename format rules, overwrite, dry-run, include-boundary-touch, preserve-source-tree, and write-manifest options
**And** the core module does not import PySide6 or `thucthengay.editor`.

**Given** a download request is built
**When** paths are relative or absolute
**Then** the service resolves and validates selected GeoJSON files, source image folders, and output folder consistently
**And** invalid initial configuration returns a clear error before scanning starts.

**Given** the old CLI script remains available in `0.Download_Img`
**When** the app implementation is added
**Then** the implementation either reuses extracted logic or ports it into `src/thucthengay/download/` with equivalent behavior covered by tests
**And** no production test depends on the real LAN folders from the script config.

### Story 10.2: Match Source GeoTIFFs Against Explicit GeoJSON Files

As an Operator,
I want selected GeoJSON files to be matched directly against selected source image folders,
So that I can download imagery for exactly the AOI files I chose.

**Requirement References:** SDT-FR2, SDT-FR3, SDT-FR5, SDT-FR7, SDT-FR11, SDT-AR3, SDT-AR4, NFR5, NFR6

**Acceptance Criteria:**

**Given** the Operator selects one or more GeoJSON files
**When** the download run starts
**Then** the engine loads only those explicit files
**And** it does not require or scan a GeoJSON folder input in the primary workflow.

**Given** a GeoJSON file contains a FeatureCollection, Feature, or geometry object
**When** the engine loads AOIs
**Then** valid non-empty geometries are merged per GeoJSON file for matching
**And** invalid or unreadable GeoJSON produces a Vietnamese configuration error that identifies the file.

**Given** source image folders contain GeoTIFF files recursively
**When** the scan runs
**Then** the engine reads raster CRS/bounds with rasterio, transforms each GeoJSON geometry to the raster CRS when needed, and tests intersection using the include-boundary-touch option.

**Given** a source image intersects multiple selected GeoJSON files
**When** matching completes
**Then** the result records every matched GeoJSON for that image
**And** the image is eligible for output under each matched GeoJSON branch.

**Given** a raster cannot be opened or has no usable CRS
**When** the engine scans it
**Then** the run records a failed-image row with the error
**And** scanning continues for the remaining images.

### Story 10.3: Parse Filename Metadata and Apply Cloud Filters

As an Operator,
I want the download run to parse capture time and cloud percent from known filename patterns,
So that high-cloud scenes can be skipped and the manifest contains useful metadata.

**Requirement References:** SDT-FR5, SDT-FR8, SDT-FR9, SDT-FR10, SDT-FR11

**Acceptance Criteria:**

**Given** filename format rules are configured
**When** a candidate image filename is evaluated
**Then** the first matching rule extracts capture date/time and cloud percent using the supported tokens `yyyyMMdd`, `hhMMss`, `cloud-percent`, `cloud_percent`, and `*`
**And** the matched rule name is recorded for manifest output.

**Given** a matched filename rule has `max_cloud_percent`
**When** the image cloud percent exceeds the threshold
**Then** the image is skipped with status `skipped_cloud`
**And** the run increments skipped-cloud progress counters.

**Given** no filename rule matches
**When** the image otherwise intersects a GeoJSON
**Then** the image can still be copied unless a future option explicitly requires metadata parsing
**And** the manifest records that filename format was not matched.

**Given** multiple filename rules could overlap
**When** options are validated or the run starts
**Then** the app surfaces a non-blocking warning that an earlier rule may hide a later rule
**And** the warning includes remediation to reorder the rules.

### Story 10.4: Write Output Tree and Manifest Per Download Run

As an Operator,
I want downloaded imagery organized by GeoJSON and source folder,
So that each AOI output can be inspected or used as an input folder later.

**Requirement References:** SDT-FR4, SDT-FR6, SDT-FR7, SDT-FR8, SDT-FR10, SDT-FR13, NFR3

**Acceptance Criteria:**

**Given** a selected GeoJSON file named `all_processed.geojson` and a source folder named `20260613`
**When** an intersecting image is copied
**Then** its destination starts with `<output>/all_processed/20260613/`
**And** when preserve-source-tree is enabled, the image's relative path under the source folder is preserved below that branch.

**Given** two selected GeoJSON files or source folders have the same sanitized name
**When** output branches are built
**Then** the engine assigns stable unique safe names using suffixes
**And** the manifest records the source path and matched GeoJSON so the branch remains traceable.

**Given** the destination file already exists and overwrite is disabled
**When** the engine would copy the file
**Then** it records `skipped_existing`
**And** it does not overwrite the existing file.

**Given** dry-run is enabled
**When** the engine processes matching images
**Then** it records the destination path that would be used
**And** it does not create or overwrite image files.

**Given** write-manifest is enabled
**When** the run finishes or is cancelled after processing at least one candidate
**Then** a CSV manifest is written in the output folder
**And** the manifest includes status, source folder, source path, destination path, matched GeoJSON, filename-format fields, capture datetime, cloud percent, max cloud percent, and error.

### Story 10.5: Run Satellite Download as a Progress Job

As an Operator,
I want long download runs to show progress and allow safe cancellation,
So that scanning large LAN imagery folders does not freeze the application.

**Requirement References:** SDT-FR9, SDT-FR11, SDT-FR12, SDT-AR2, UX-DR14, NFR5, NFR8

**Acceptance Criteria:**

**Given** a download run is started from the UI
**When** the job runs
**Then** it executes outside the Qt main thread using the existing job/progress pattern
**And** UI actions that would conflict with the running job are disabled.

**Given** images are being scanned
**When** progress events are emitted
**Then** they include percentage when computable, stage, current activity text, total images, scanned images, matched images, downloaded/copied images, skipped existing, skipped cloud, failed images, metadata cache hits/misses, current source folder, and current GeoJSON or match context when known.

**Given** the Operator cancels the job
**When** cancellation is observed between candidates
**Then** the job stops after the current safe unit of work
**And** the final result reports cancelled state, partial counters, partial output, and manifest path if written.

**Given** a non-fatal raster/copy error occurs
**When** the job continues
**Then** progress and final summary include the failure count
**And** the detailed error is available in the manifest or issue/status detail.

### Story 10.6: Add Satellite Download Tab UI

As an Operator,
I want a dedicated tab for satellite image download next to Config,
So that I can configure and run downloads without editing JSON or running a batch script.

**Requirement References:** SDT-FR1, SDT-FR2, SDT-FR3, SDT-FR4, SDT-FR8, SDT-UX1, SDT-UX2, SDT-UX3, UX-DR1, UX-DR2, UX-DR14, UX-DR16

**Acceptance Criteria:**

**Given** the app shell renders top-level tabs
**When** the satellite download feature is available
**Then** a new tab is shown at the outer edge adjacent to `Config`
**And** the tab label clearly identifies the download function.

**Given** the Operator opens the download tab
**When** the form is rendered
**Then** it provides explicit controls to add/remove/clear multiple GeoJSON files
**And** it does not show a GeoJSON folder picker for the primary workflow.

**Given** the Operator configures source imagery
**When** source inputs are rendered
**Then** the UI allows adding/removing/clearing multiple image folders
**And** each row shows a validation indicator, middle-elided path, and full-path tooltip.

**Given** the Operator configures output
**When** output input is rendered
**Then** the UI provides one output folder picker
**And** the form explains through labels/status that copied images will be grouped by GeoJSON name then source folder name.

**Given** required inputs are missing or invalid
**When** the Operator views the primary action
**Then** the Download action is disabled or blocked with a visible Vietnamese reason
**And** status does not rely on color alone.

### Story 10.7: Wire Download Run Results, Summary, and App Boundaries

As an Operator,
I want clear completion evidence after a download run,
So that I know what was copied, skipped, failed, and where to use the output next.

**Requirement References:** SDT-FR10, SDT-FR11, SDT-FR12, SDT-FR13, SDT-UX2, SDT-UX3, NFR3, NFR6, NFR7

**Acceptance Criteria:**

**Given** a download run succeeds
**When** the job finishes
**Then** the tab shows a completion summary with total scanned, matched, copied/downloaded, skipped existing, skipped cloud, failed, cache hits/misses, output folder, and manifest path.

**Given** the run finishes with warnings or failed images
**When** the summary is shown
**Then** it identifies the failure count and provides Vietnamese remediation to inspect the manifest and verify unreadable paths, permissions, CRS, filename rules, or disk space.

**Given** the run is cancelled
**When** the summary is shown
**Then** it clearly states that output may be partial
**And** it still reports partial counters and manifest path if available.

**Given** the download tab writes output files
**When** the run completes
**Then** it does not mutate workspace `manifest.json`, `cache/`, `compositions/`, `renders/`, `exports/`, or historical SQLite state
**And** the Operator can later choose the output branch as an imagery input folder through the existing ingest workflow.

### Story 10.8: Add Download Engine and UI Regression Tests

As a Developer,
I want focused tests for the download tab workflow,
So that future changes do not break GeoJSON-file selection, output structure, progress, or app boundaries.

**Requirement References:** SDT-FR2, SDT-FR3, SDT-FR6, SDT-FR7, SDT-FR9, SDT-FR10, SDT-FR13, SDT-AR4

**Acceptance Criteria:**

**Given** generated GeoTIFF and GeoJSON fixtures are available in a temp test directory
**When** the download engine runs against intersecting and non-intersecting rasters
**Then** tests verify matching, CRS transform behavior where practical, copied output structure, cloud skip behavior, and manifest rows.

**Given** one image intersects two GeoJSON files
**When** the engine writes outputs
**Then** tests verify that each matched GeoJSON branch receives or reports the image according to the configured output behavior.

**Given** a run uses multiple source image folders
**When** output branches are generated
**Then** tests verify safe/unique source folder branch naming and preserve-source-tree behavior.

**Given** the job wrapper is tested without a real Qt event loop
**When** progress events are collected
**Then** tests verify counters and stage messages include enough detail for the UI progress panel.

**Given** UI tests instantiate the download tab
**When** GeoJSON files, image folders, and output folder are added or removed
**Then** tests verify control state, disabled reasons, and that no workspace service write is triggered by the download workflow.

## Epic 11: Render Pipeline Performance Refactor

**Goal:** Improve Review/Edit GIS canvas responsiveness for large satellite imagery by measuring current bottlenecks, ensuring rasters have usable overview pyramids, and replacing whole-frame preview rerendering with stable tile-indexed decode/cache/composition behavior.

**Mandatory Epic Constraint:** Epic 11 is a performance/refactor epic only. Every implementation story must preserve the current map-frame visual/layout contract exactly: frame shape, size, aspect, outer frame, inner raster panel, coordinate labels, tick placement, label format/text, temporal-compare pane gap, pane boundaries, and spacing must not change as a side effect of diagnostics, overview handling, tile cache, scheduling, partial repaint, progressive LOD, or any future GPU decision.

### Story 11.1: Instrument Render Pipeline and Establish Baseline Metrics

As a Developer,
I want render performance instrumentation around the current preview pipeline,
So that optimization work is driven by measured bottlenecks instead of guesses.

**Requirement References:** RPR-FR1, RPR-FR2, RPR-AR1, RPR-AR4, RPR-UX1

**Acceptance Criteria:**

**Given** render diagnostics are enabled for Review/Edit preview
**When** a composition is rendered, panned, and zoomed
**Then** the diagnostic output records timing for raster window reads, resampling/scaling, QImage conversion, QPixmap conversion, paint/composite work, cache hits/misses, output dimensions, and total render latency.

**Given** diagnostics are disabled
**When** normal Review/Edit rendering runs
**Then** the render behavior and UI remain unchanged except for negligible instrumentation overhead.

**Given** a diagnostic run includes large GeoTIFF inputs
**When** the diagnostic summary is written
**Then** it reports whether each raster has usable overview levels and records enough file signature data to compare later runs.

**Given** a developer runs focused tests
**When** instrumentation code is exercised with generated raster fixtures
**Then** tests verify metrics are collected without requiring PySide widgets or production imagery.

**Given** render diagnostics are enabled or disabled
**When** the same render spec is used
**Then** diagnostics do not alter map-frame geometry, labels, pane gaps, or final/preview visual layout.

### Story 11.2: Add COG and Overview Readiness Tooling

As a Developer,
I want tooling and metadata support for COG/overview readiness,
So that large imagery can be prepared before deeper tile rendering changes are made.

**Requirement References:** RPR-FR2, RPR-FR3, RPR-FR4, RPR-AR1, RPR-AR3, RPR-AR4

**Acceptance Criteria:**

**Given** a GeoTIFF path is checked
**When** overview readiness runs
**Then** it reports raster size, CRS, available overview decimation levels, block/tile hints when available, and whether the raster is likely expensive to zoom out.

**Given** a raster lacks usable overviews
**When** the readiness report is produced
**Then** it includes actionable remediation for creating COG output or external overviews without silently mutating the source file.

**Given** overview metadata has already been cached for an unchanged raster
**When** readiness or render code asks for overview levels again
**Then** it can reuse cached metadata keyed by source path, size, and mtime.

**Given** tests run in CI or a developer machine
**When** the readiness service is tested
**Then** it uses generated lightweight raster fixtures and skips only external GDAL CLI conversion steps that are unavailable.

### Story 11.3: Introduce Fixed Tile Index and Tile Cache Contracts

As a Developer,
I want a deterministic tile index and byte-budgeted tile cache contract,
So that decoded map-space data can survive pan/zoom changes and be reused across frames.

**Requirement References:** RPR-FR5, RPR-FR6, RPR-AR1, RPR-AR2, RPR-AR3, RPR-AR4

**Acceptance Criteria:**

**Given** a viewport, map scale, tile size, and map-space extent
**When** `TileIndex` resolves visible tiles
**Then** it returns deterministic tile keys independent from the current widget frame and stable across small pan movements.

**Given** two nearby pan positions overlap
**When** visible tile keys are compared
**Then** shared map-space tiles keep identical keys and only newly exposed tiles are new.

**Given** a tile cache is configured with a byte budget
**When** tiles are inserted beyond the budget
**Then** least-recently-used entries are evicted deterministically without evicting unrelated current entries prematurely.

**Given** a raster file changes size or mtime
**When** tile keys are built
**Then** the file signature changes and stale tile entries are not reused.

**Given** tile keys and cache entries are introduced
**When** the renderer derives the map-space tile coverage
**Then** it uses the existing render spec/map-frame geometry as input and does not redefine frame size, label placement, pane gap, or map-surround layout.

### Story 11.4: Decode Tiles with Scheduler and Cooperative Cancellation

As a Developer,
I want missing visible tiles decoded asynchronously with cancellation and prioritization,
So that pan/zoom remains responsive while expensive raster work happens off the UI thread.

**Requirement References:** RPR-FR6, RPR-FR7, RPR-AR1, RPR-AR3, RPR-AR4, RPR-UX1

**Acceptance Criteria:**

**Given** a viewport requests tiles and some are missing from cache
**When** the tile scheduler runs
**Then** missing tiles are queued by priority, with tiles nearer the viewport center scheduled before edge tiles.

**Given** the viewport changes before queued tile work completes
**When** obsolete tile jobs finish
**Then** their results are rejected and do not overwrite the current view.

**Given** a tile decode job reads raster data
**When** an appropriate overview/LOD level is available
**Then** the job reads the smallest practical raster window/decimation for that tile instead of full-frame raster data.

**Given** cancellation is requested
**When** the decode worker reaches cancellation checkpoints
**Then** it exits cleanly and leaves cache/state consistent.

### Story 11.5: Compose GIS Canvas from Cached Tiles and Support Partial Repaint

As an Operator,
I want the GIS canvas to reuse already-decoded tiles while panning,
So that the map follows interaction quickly instead of waiting for a full viewport rerender.

**Requirement References:** RPR-FR8, RPR-FR9, RPR-AR1, RPR-AR2, RPR-AR4, RPR-UX1

**Acceptance Criteria:**

**Given** visible tiles are already cached
**When** the Operator pans a small distance
**Then** the canvas repositions cached tiles immediately and queues only newly exposed tiles.

**Given** a previous composed frame exists
**When** pan delta is below the configured threshold
**Then** partial repaint reuses the previous frame buffer and repaints only exposed bands where practical.

**Given** zoom changes or pan delta is too large
**When** the canvas updates
**Then** the compositor falls back to a full recomposite without corrupting tile cache state.

**Given** cached tiles or partial repaint are used
**When** the map is displayed in normal or temporal-compare mode
**Then** the compositor preserves the existing frame shape, dimensions, labels, ticks, pane gaps, pane boundaries, and spacing exactly.

**Given** final export runs
**When** preview tile rendering has been used in Review/Edit
**Then** final render output remains governed by the existing final render contract unless this story explicitly verifies a shared tile path.

### Story 11.6: Add Progressive LOD and Reassess GPU Path

As an Operator,
I want fast pan/zoom to show useful lower-resolution imagery first and refine automatically,
So that Review/Edit remains usable even when high-resolution tiles are still decoding.

**Requirement References:** RPR-FR10, RPR-FR11, RPR-AR1, RPR-AR2, RPR-AR4, RPR-UX1

**Acceptance Criteria:**

**Given** high-resolution visible tiles are missing but lower-resolution cached tiles cover the same area
**When** the canvas repaints during fast pan/zoom
**Then** it displays the lower-resolution tiles as temporary imagery and replaces them when correct-resolution tiles arrive.

**Given** progressive LOD is active
**When** lower-quality imagery is shown
**Then** the UI exposes a clear render-quality/loading status without blocking review actions or relying on color alone.

**Given** progressive LOD or a future GPU path is evaluated
**When** imagery is temporarily lower quality or rendered through another compositor
**Then** only raster imagery quality/timing may vary; map-frame geometry, labels, gaps, pane boundaries, and surrounding layout remain unchanged.

**Given** tile cache, scheduler, compositor, and partial repaint are stable
**When** diagnostics are rerun
**Then** the team can compare baseline versus optimized metrics for CPU, read count, cache hit rate, and perceived latency.

**Given** diagnostics show the remaining bottleneck is not raster decode/resampling
**When** GPU/OpenGL is considered
**Then** the decision record states whether to keep QPainter/QImage or create a later GPU-specific epic/story, with evidence from the measured metrics.
