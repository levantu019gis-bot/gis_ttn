---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/prds/prd-3.ThucTheNgay-2026-05-23/prd.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/architecture.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/ux-design-specification.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/config-manager-tab-design.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/config-manager-ui-mockup.html
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
