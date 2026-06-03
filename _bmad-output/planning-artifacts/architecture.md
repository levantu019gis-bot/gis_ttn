---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: complete
completedAt: '2026-05-24'
inputDocuments:
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/briefs/brief-3.ThucTheNgay-2026-05-23/brief.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/prds/prd-3.ThucTheNgay-2026-05-23/prd.md
  - /home/ongtu/Working/3.ThucTheNgay/_bmad-output/planning-artifacts/ux-design-specification.md
workflowType: architecture
project_name: 3.ThucTheNgay
user_name: Ongtu
date: 2026-05-23
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Workflow Initialization

Input documents loaded:

- Product Brief: `_bmad-output/planning-artifacts/briefs/brief-3.ThucTheNgay-2026-05-23/brief.md`
- PRD: `_bmad-output/planning-artifacts/prds/prd-3.ThucTheNgay-2026-05-23/prd.md`
- UX Design Specification: `_bmad-output/planning-artifacts/ux-design-specification.md`

Required PRD input is present. UX specification is present and should inform UI architecture, component boundaries, keyboard handling, and render-preview interactions.

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**

PRD có 23 functional requirements, nhóm thành 6 vùng kiến trúc chính:

1. **Config & Setup** — load target config JSON, chọn input/workspace/output paths, validate config và paths.
2. **Data Ingestion** — scan GeoTIFF, parse filename metadata, check intersection với target GeoJSON, copy ảnh vào workspace cache, tạo composition.
3. **Workspace & Composition State** — quản lý manifest, cache, composition JSON, status, review_order, validation_summary.
4. **Review/Edit UI** — PySide6 desktop UI với tree, layers, slide preview, GIS editor, keyboard review loop.
5. **Rendering & Validation** — render preview/final từ composition state, validate layer/metadata/grid/template/render readiness, issue schema.
6. **Export** — target-specific one-slide PPTX template, render PNG final, copy slide template, replace placeholders by PPTX element id, export PPTX/TXT/log.

**Non-Functional Requirements:**

- Performance: GeoTIFF lớn cần cache/downsample/two-stage render để editor không lag.
- Reliability: workspace JSON writes không được corrupt state.
- Recoverability: workspace artifact cần inspect/restore thủ công được.
- Traceability: export log cần map composition -> slide/TXT line/skipped reason.
- Data locality: local/LAN files, không cần network.
- Usability/accessibility: keyboard workflow, visible status, remediation tiếng Việt.

**Scale & Complexity:**

- Primary domain: desktop geospatial/report-generation tool.
- Complexity level: medium-high.
- Lý do: không có multi-user/network/backend, nhưng có nhiều integration risk: GeoTIFF/GIS math, CRS/grid, PySide6 interactive UI, render cache, JSON workspace consistency, PPTX template manipulation.
- Estimated architectural components: 8 core modules plus app shell.

### Technical Constraints & Dependencies

- App type: desktop PySide6/PyQt6.
- GIS editor/viewer: QGraphicsView self-rendered; no PyQGIS for MVP.
- GIS/raster stack: rasterio/GDAL, shapely, pyproj, numpy, Pillow.
- PPTX export: python-pptx plus controlled XML/media handling if needed.
- State/config: JSON files.
- Workspace is source of truth.
- Template analyzer metadata JSON is out of scope for MVP export; app consumes one-slide PPTX templates and element-id mappings declared in target config.
- Target templates may be separate PPTX files, but must share compatible base/theme/master for MVP.
- UX requires desktop-first adaptive splitter layout, keyboard review actions, warning navigation, and dense Qt-native components.

### Cross-Cutting Concerns Identified

- **State consistency:** UI, validation, render and export must all read/write composition state through workspace services.
- **Long-running task orchestration:** ingestion, validation, rendering and export need progress, cancellation/ignore-stale behavior and UI-safe threading.
- **File path robustness:** local/LAN paths, copied cache files, moved metadata-date files, missing files.
- **CRS and spatial correctness:** intersection, center/scale-derived map window, grid labels, raster transform and final render must be consistent.
- **Render parity:** preview and final render must share core math while using different performance paths.
- **Issue propagation:** issue schema must support tree indicators, Warnings panel, validation gates and export logs.
- **Template/export reliability:** PPTX template path, element-id mappings, slide copy, PNG insertion and TXT templating need strict validation.
- **Keyboard and focus handling:** review shortcuts must not conflict with metadata/grid text inputs.

## Starter Template Evaluation

### Primary Technology Domain

Primary technology domain là **Python desktop geospatial/report-generation application**.

Không dùng web/mobile/full-stack starter. App cần:

- PySide6 desktop UI;
- raster/GIS processing;
- local/LAN file access;
- JSON workspace state;
- PPTX/TXT export;
- long-running background jobs.

### Starter Options Considered

#### Option A: Generic PySide6 example/starter

PySide6 official docs/examples hữu ích để học API và patterns, nhưng không cung cấp architecture starter phù hợp cho app nhiều module, workspace state, GIS rendering và export pipeline.

**Decision:** Không dùng làm starter chính; chỉ dùng làm API reference/example source.

#### Option B: Web desktop wrapper starter: Electron/Tauri

Không phù hợp vì PRD đã chốt desktop Python/PySide6, cần truy cập file local/LAN, xử lý GeoTIFF lớn, dùng rasterio/GDAL/shapely/pyproj và QGraphicsView self-rendered.

**Decision:** Reject.

#### Option C: Custom Python package scaffold with `uv`

Dùng `uv init` hoặc scaffold tương đương để tạo Python project chuẩn `pyproject.toml`, sau đó tổ chức source theo layered architecture.

**Decision:** Chọn Option C.

### Selected Starter: Custom Python Package Scaffold

**Rationale for Selection:**

- Phù hợp nhất với PySide6 desktop app.
- Không ép app vào web/app framework không cần thiết.
- Cho phép kiểm soát module boundaries: `config`, `ingestion`, `workspace`, `gis`, `editor`, `render`, `export`, `validation`.
- Dễ test từng core module không cần UI.
- Dễ đóng gói/điều chỉnh dependency GIS/PPTX sau này.

**Initialization Command:**

```bash
uv init --app
```

Sau đó chỉnh `pyproject.toml` để thêm dependencies chính:

```text
PySide6
rasterio
GDAL
shapely
pyproj
numpy
Pillow
python-pptx
pydantic
```

Testing/tooling nên thêm ở dev dependencies:

```text
pytest
ruff
mypy hoặc pyright
```

### Architectural Decisions Provided by Starter

**Language & Runtime:**

- Python application project.
- `pyproject.toml` là source cho project metadata/dependencies.
- Environment quản lý bằng `uv`.

**Build Tooling:**

- Không dùng frontend bundler.
- Không dùng Electron/Tauri.
- Runtime entrypoint là Python desktop app.

**Testing Framework:**

- Chọn `pytest` cho core modules.
- UI testing ở MVP có thể giới hạn smoke/manual; core logic test được độc lập.

**Code Organization:**

Proposed initial source layout:

```text
src/
  thucthengay/
    app.py
    config/
    ingestion/
    workspace/
    gis/
    editor/
    render/
    export/
    validation/
tests/
  fixtures/
  unit/
  integration/
```

**Development Experience:**

- `uv run` để chạy app/tests/tools.
- `ruff` để lint/format.
- Core modules thiết kế để chạy headless test không cần mở GUI.
- UI layer chỉ điều phối view state và gọi services.

**Note:** Project initialization using this scaffold should be the first implementation story.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

- Python desktop app with PySide6 Qt Widgets.
- Layered package architecture.
- Workspace JSON as source of truth.
- Pydantic-based schema validation for config/composition/export template mapping.
- Service-oriented core modules testable without UI.
- Background job model for ingestion/render/export.
- Hybrid renderer with shared core math and separate preview/final paths.
- Target-specific one-slide PPTX template and element-id replacement validation.

**Important Decisions (Shape Architecture):**

- Atomic JSON writes.
- Issue schema as shared contract between validation/UI/export.
- QGraphicsView-based GIS editor.
- Qt model/view for composition tree, layer list, warnings and export plan.
- `uv` + `pyproject.toml` + `pytest` + `ruff`.

**Deferred Decisions:**

- Packaging/distribution strategy: defer until vertical slice works.
- Exact render latency budgets: defer until representative GeoTIFF tests.
- Metadata override reuse across re-ingest: defer to hardening.
- Full automated UI testing: defer; MVP focuses on core module tests and manual/smoke UI tests.

### Data Architecture

**Decision:** File-based workspace with JSON state.

Workspace structure:

```text
workspace/
  manifest.json
  cache/
    target_id/YYYYMMDD/*.tif
  compositions/
    target_id__YYYYMMDD.json
  renders/
  exports/
```

**Rationale:**

- Matches PRD requirement that workspace is inspectable/recoverable.
- Avoids SQLite complexity in MVP.
- Keeps each composition as independent artifact.
- Works well for personal desktop local/LAN workflow.

**Validation Strategy:**

- Config validation must require target `coordinate` `[lon, lat]`, positive scale denominator, valid grid interval, GeoJSON path, and template PPTX path for enabled targets.
- Use Pydantic models for:
  - project/target config;
  - composition JSON;
  - layer metadata;
- target PPTX template and element-id mapping;
  - issue schema;
  - export log.
- Use structured load/save service; UI should not parse/write JSON directly.

**Write Strategy:**

- Atomic writes: write temp file, fsync if feasible, replace target file.
- Keep deterministic formatting for inspectable JSON.
- Save composition through `workspace` service only.

**Caching Strategy:**

- Ingestion copies matched GeoTIFFs into workspace cache.
- Preview cache/downsample files can live under `renders/preview_cache/` or `cache/_preview/`.
- Final renders live under `renders/final/` and are tied to composition/render parameters.

### Authentication & Security

**Decision:** No authentication/authorization for MVP.

**Rationale:**

- Single-user desktop app.
- No backend or network service.
- Data locality is a requirement.

**Security Guardrails:**

- Treat file paths as untrusted input.
- Avoid arbitrary code execution from config/PPTX template mapping.
- Resolve relative paths against config/workspace roots.
- Confirm destructive operations:
  - clear workspace;
  - reset ready composition;
  - move file due to metadata date correction.
- Logs should avoid silently leaking unrelated filesystem data; include paths needed for traceability only.

### API & Communication Patterns

**Decision:** No external API. Internal communication uses Python service interfaces and Qt signals/slots.

**Internal Pattern:**

- UI calls application services:
  - `ConfigService`
  - `WorkspaceService`
  - `IngestionService`
  - `ValidationService`
  - `RenderService`
  - `ExportService`
- Long-running services report progress through typed progress events.
- UI receives progress via Qt signals on main thread.

**Error Handling:**

- Core services raise typed domain exceptions or return structured result objects.
- User-facing validation uses `Issue` objects, not raw exceptions.
- Blocking errors become `severity=error` issues where possible.

### Frontend / UI Architecture

**Decision:** PySide6 Qt Widgets with model/view architecture.

**Rationale:**

- UX spec requires dense desktop UI, splitters, tree/list/table, QGraphicsView canvas and keyboard workflows.
- Qt Widgets is a better fit than QML for MVP because app is utility/tool-like and needs fast implementation with native widgets.

**UI Structure:**

```text
AppShell / QMainWindow
  ModeSwitcher
  SetupMode
  ReviewEditMode
    CompositionTreeModel/View
    LayerListModel/View
    SlidePreviewWidget
    GisEditorView / QGraphicsView
    WarningsModel/View
    ReviewActionBar
  ExportMode
    ExportSummaryWidget
    ExportPlanModel/View
```

**State Rule:**

- UI model state is a projection/cache of workspace state.
- Workspace service remains source of truth.
- UI must mark dirty/needs_revalidation when view/layer/grid/metadata changes.

**Keyboard Rule:**

- Review shortcuts active only when not editing text fields.
- Metadata/grid editors must receive arrow keys normally.

### Rendering Architecture

**Decision:** Hybrid render pipeline.

**Core Render Math:**

- Shared by preview and final.
- Inputs: composition, target config, PPTX map-frame bounds, output size.
- Uses `view.center`, `view.scale`, visible layers, layer order, grid interval, label format, background RGB.

**Preview Path:**

- Uses downsample/overview/cache.
- Supports two-stage rendering:
  - interactive low-res during pan/zoom;
  - settled high-res after idle/debounce.
- Stale render jobs are ignored if render token/state version changes.

**Final Path:**

- Reads raster at appropriate resolution for final output size.
- Produces PNG for PPTX insertion.
- Writes render metadata/log: composition id, center, scale, derived map window, layer ids/order, output size, grid config.

### GIS / Spatial Architecture

**Decision:** Use rasterio/GDAL for raster metadata/read windows, shapely for geometry/intersection, pyproj for CRS transforms.

**Rules:**

- Ingestion intersection uses GeoTIFF bounds transformed into compatible CRS with target GeoJSON.
- Target config stores `coordinate` as geographic `[lon, lat]` plus `scale` as the map scale denominator, e.g. `50000` means 1:50,000; new compositions initialize `view.center` and `view.scale` from those target fields.
- Render layer reads derive the ground map window from `view.center`, `view.scale`, and the template map-frame physical size/aspect. The renderer converts the center to an appropriate projected CRS for meter-based span calculation, derives the geographic window, then converts it into each raster CRS/read window as needed.
- Grid interval comes from the composition override when present, otherwise from target grid config; labels use configured label format, default DMS full.

**Risk Control:**

- Add fixture tests for CRS transform, intersection and grid label generation.
- Do not expose CRS controls in MVP UI unless needed for error remediation.

### Export Architecture

**Decision:** Target-specific one-slide PPTX templates, one combined PPTX output.

**Flow:**

1. Load included compositions sorted by review_order.
2. Full preflight validation.
3. Render final PNG per composition.
4. Load target-specific one-slide PPTX template and element-id mapping from target config.
5. Copy the only slide from target-specific PPTX.
6. Replace map frame image and text placeholders by configured PPTX element ids.
7. Write combined PPTX.
8. Write TXT.
9. Write export log JSON/TXT.

**Template Rule:**

- Export replacement uses the resolved PPTX element id as the authoritative key.
- Configured element ids remain supported, but the loader may repair volatile ids from stable selector metadata before export uses them.
- Preferred stable shape-name convention is `ttn:<field>`, for example `ttn:map_image`, `ttn:title`, `ttn:time`, and `ttn:comment`.
- Required placeholders missing = blocking error.
- Ambiguous selector/name matches = blocking error; the app must not guess.
- MVP requires all target PPTX templates share compatible base/theme/master.

**Implementation Note:**

- Start with one-slide export vertical slice; reject target templates with zero or multiple slides.
- If python-pptx slide copying is insufficient, isolate XML/media copy logic inside `export/pptx_slide_copy.py` so risk is contained.

### Infrastructure & Deployment

**Decision:** Local desktop runtime; no server infrastructure.

**Development:**

- `uv run` for app/tests/tools.
- `pytest` for config/workspace/ingestion/gis/render/export validation.
- `ruff` for formatting/linting.
- Type checking with mypy or pyright once models stabilize.

**Packaging:**

- Windows executable tooling uses PyInstaller from the conda environment.
- One-folder output is the preferred default for PySide6/GDAL/rasterio stability: `dist\ThucTheNgay\ThucTheNgay.exe`.
- One-file output is optional but should be treated as higher risk until tested with representative GIS/template workflows.
- PyInstaller must be run on Windows; Windows `.exe` cross-compilation from Linux is not supported.
- GDAL/rasterio packaging is a known risk; architecture should keep packaging concerns separate from domain modules.

### Decision Impact Analysis

**Implementation Sequence:**

1. Scaffold Python package and dependency baseline.
2. Define Pydantic schemas and fixtures.
3. Implement workspace service and atomic JSON writes.
4. Implement ingestion minimal.
5. Implement GIS utility functions and render final PNG.
6. Implement target PPTX mapping and one-slide PPTX/TXT export.
7. Build PySide6 shell and Review/Edit vertical slice.
8. Add validation/warnings and preview cache.
9. Harden export, progress jobs and logs.

**Cross-Component Dependencies:**

- `validation` depends on config/workspace/gis/target PPTX mapping but should not depend on UI.
- `render` depends on gis/workspace models but should not depend on UI widgets.
- `editor` depends on workspace/render/validation services through application interfaces.
- `export` depends on validation/render/target PPTX mapping and workspace.
- `ingestion` creates workspace artifacts consumed by editor/render/export.

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

Critical conflict points:

- JSON field naming and schema ownership.
- Service boundaries and where business logic lives.
- UI model/view vs workspace service responsibilities.
- Error/issue representation.
- Long-running job progress/cancellation.
- File path resolution and atomic writes.
- Render job stale-state handling.
- Test fixture organization.

### Naming Patterns

**Python code naming**

- Packages/modules/files: `snake_case`.
- Classes: `PascalCase`.
- Functions/methods/variables: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Qt widgets/classes: descriptive `PascalCase`, e.g. `ReviewEditMode`, `GisEditorView`, `CompositionTreeModel`.

**Domain naming**

Use PRD glossary terms exactly in code:

- `Target`
- `Composition`
- `ImageLayer`
- `Workspace`
- `ReviewOrder`
- `TemplateMetadata`
- `ViewExtent`
- `Issue`

Do not introduce synonyms like `Scene`, `SlideItem`, `MapSession`, `AOI` unless explicitly added to glossary.

**JSON field naming**

- Use `snake_case` in all config/workspace/composition/template/export JSON.
- Dates use ISO-like strings:
  - `capture_date`: `YYYY-MM-DD`
  - `capture_time`: `HH:MM:SS`
  - `last_validated_at`: ISO datetime with timezone when available.
- Composition id format: `target_id__YYYYMMDD`.

### Structure Patterns

**Layered source structure**

```text
src/thucthengay/
  app.py
  models/
  config/
  workspace/
  ingestion/
  gis/
  render/
  validation/
  export/
  editor/
  jobs/
  utils/
```

**Ownership rules**

- `models/`: Pydantic schemas and enums shared across modules.
- `workspace/`: only place allowed to read/write composition JSON and manifest.
- `editor/`: PySide6 widgets/models only; no direct JSON parsing/writing.
- `validation/`: returns `Issue` objects; does not mutate workspace.
- `render/`: no Qt widget dependency; produces images/render results.
- `gis/`: CRS, geometry, raster window/grid math.
- `export/`: PPTX/TXT/log generation; no UI dependency.
- `jobs/`: background job adapters/progress events.

**Test structure**

```text
tests/
  fixtures/
    configs/
    geojson/
    geotiff/
    templates/
    workspaces/
  unit/
  integration/
```

- Unit tests cover models, workspace, metadata parsing, validation, GIS math.
- Integration tests cover ingest -> workspace, render final PNG, export one-slide PPTX/TXT.
- UI tests are smoke/manual for MVP unless later automated.

### Format Patterns

**Service result format**

Services should prefer typed result objects for expected domain outcomes:

```python
class IngestionResult(BaseModel):
    scanned_count: int
    matched_count: int
    targets_with_images: int
    warning_count: int
    issues: list[Issue]
```

Unexpected programmer/system errors may raise typed exceptions.

**Issue format**

All user-facing validation and workflow issues use shared `Issue` model:

```python
class Issue(BaseModel):
    issue_id: str
    severity: IssueSeverity
    scope: IssueScope
    target_id: str | None = None
    composition_id: str | None = None
    layer_id: str | None = None
    message: str
    remediation: str | None = None
    blocking: bool = False
```

Rules:

- `issue_id` in English stable code form, e.g. `layer.file_missing`.
- `message` and `remediation` in Vietnamese.
- `severity=error` blocks ready/export.

**Path format**

- Store workspace-relative paths where possible inside workspace JSON.
- Config paths can be relative to config file location.
- Resolve paths via dedicated path resolver, not ad hoc string joins.

### Communication Patterns

**Core service calls**

- UI calls services synchronously only for cheap operations.
- Long-running operations run through job layer:
  - ingestion;
  - full validation if heavy;
  - render final;
  - export;
  - preview render when asynchronous.

**Progress event shape**

```python
class ProgressEvent(BaseModel):
    job_id: str
    stage: str
    current: int | None = None
    total: int | None = None
    message: str
    issues: list[Issue] = []
```

**Qt signal rule**

- Worker emits progress/result/error signals.
- UI updates only on main thread.
- Core services must not import PySide6 except job adapters if needed.

### State Management Patterns

**Workspace is source of truth**

- Composition changes go through `WorkspaceService`.
- UI models mirror workspace state.
- After edits to view/layer/grid/metadata, UI requests save through workspace service and marks composition `needs_revalidation`.

**Review status transitions**

- Right arrow:
  - run full validation;
  - if pass: `reviewed=true`, `ready=true`, `include=true`, set `review_order`;
  - if fail: no state transition.
- Up arrow:
  - `reviewed=true`, `ready=false`, `include=false`.
- Left arrow:
  - if previous `ready=true`, confirm reset before editing.

**Render state**

- Render request gets a monotonically increasing `render_token` or state version.
- Completed preview render is applied only if token still matches current composition/view/layer state.

### Error Handling Patterns

**Expected validation problems**

- Return `Issue` objects.
- Show in tree, layer row, Warnings panel and export logs.

**Unexpected exceptions**

- Log technical details.
- Show short Vietnamese message with remediation if possible.
- Do not convert programmer errors into silent warnings.

**Destructive operation errors**

- Must include attempted path/action in log.
- UI message should explain whether state changed partially or not.

### Loading State Patterns

- Each long-running job has `idle/running/succeeded/failed/cancelled` state.
- Disable conflicting actions while running.
- Progress UI shows current stage and counters when known.
- Cancel is only shown when cancellation is safe.

### Enforcement Guidelines

All AI agents MUST:

- Use shared Pydantic models from `models/`.
- Use `WorkspaceService` for workspace reads/writes.
- Return `Issue` for validation/workflow problems.
- Keep UI code out of core services.
- Keep render/export independent of Qt widgets.
- Use `snake_case` JSON fields.
- Add focused tests for core logic touched by a change.

Pattern enforcement:

- `ruff` for formatting/lint.
- `pytest` for unit/integration.
- PR/code review checks for boundary violations.
- Architecture doc is source for naming/boundary decisions.

### Good Examples

```python
workspace.save_composition(composition)
issues = validation_service.validate_composition(composition_id)
render_result = render_service.render_final(composition_id, output_size)
```

### Anti-Patterns

```python
# Bad: UI writes JSON directly
Path(composition_path).write_text(json.dumps(ui_state))

# Bad: validation mutates workspace state
validation_service.validate_and_set_ready(composition)

# Bad: render imports Qt widget classes
from PySide6.QtWidgets import QLabel
```

## Project Structure & Boundaries

### Complete Project Directory Structure

```text
3.ThucTheNgay/
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── src/
│   └── thucthengay/
│       ├── __init__.py
│       ├── app.py
│       ├── __main__.py
│       ├── models/
│       ├── config/
│       ├── workspace/
│       ├── ingestion/
│       ├── gis/
│       ├── render/
│       ├── validation/
│       ├── export/
│       ├── jobs/
│       ├── editor/
│       │   ├── modes/
│       │   ├── models/
│       │   ├── widgets/
│       │   └── delegates/
│       └── utils/
├── tests/
│   ├── fixtures/
│   │   ├── configs/
│   │   ├── geojson/
│   │   ├── geotiff/
│   │   ├── templates/
│   │   └── workspaces/
│   ├── unit/
│   └── integration/
└── docs/
    ├── architecture.md
    └── sample-config.md
```

Detailed source files:

```text
src/thucthengay/
  models/{config.py,workspace.py,composition.py,layer.py,template.py,issue.py,render.py,export.py}
  config/{service.py,loader.py,path_resolver.py}
  workspace/{service.py,manifest.py,composition_store.py,atomic_write.py,paths.py}
  ingestion/{service.py,scanner.py,metadata_parser.py,intersection.py,cache_builder.py}
  gis/{crs.py,geometry.py,raster.py,view_state.py,grid.py,dms.py}
  render/{service.py,core.py,preview.py,final.py,cache.py,grid_drawer.py}
  validation/{service.py,rules.py,config_rules.py,composition_rules.py,layer_rules.py,render_rules.py,template_rules.py}
  export/{service.py,pptx_exporter.py,pptx_slide_copy.py,txt_exporter.py,template_loader.py,log_writer.py}
  jobs/{progress.py,worker.py,ingestion_job.py,render_job.py,export_job.py}
  editor/{app_shell.py,theme.py,shortcuts.py}
  editor/modes/{setup_mode.py,review_edit_mode.py,export_mode.py}
  editor/models/{composition_tree_model.py,layer_list_model.py,warnings_model.py,export_plan_model.py}
  editor/widgets/{mode_switcher.py,path_picker.py,ingestion_progress.py,gis_editor_view.py,slide_preview.py,review_action_bar.py,warnings_panel.py,metadata_editor.py,export_summary.py}
  editor/delegates/{composition_item_delegate.py,layer_item_delegate.py}
  utils/{logging.py,time_format.py,ids.py}
```

### User Project Data Layout

User project data should live outside the application source tree. The app reads these files through paths selected/configured by the Operator.

Recommended layout:

```text
project_data/
  config.json
  targets/
    target_001.geojson
    target_002.geojson
  templates/
    target_001.pptx
    target_001.template.json
    target_002.pptx
    target_002.template.json
  imagery/
    raw_geotiff_files/
  workspace/
    manifest.json
    cache/
    compositions/
    renders/
    exports/
```

Rules:

- `config.json` is the primary project config selected in Setup.
- `targets/*.geojson` are source target boundaries referenced by `config.json` through `geojson_file`.
- `templates/*.pptx` are target-specific one-slide PowerPoint templates referenced directly by `target.export.template_pptx_file`.
- `imagery/` contains source GeoTIFFs and should be scan/read-only for the app.
- `workspace/` is runtime state owned by the app and may be cleared on `Lấy dữ liệu` after confirmation.
- Paths inside `config.json` resolve relative to the config file location.
- Workspace JSON should store workspace-relative paths where possible.

### Architectural Boundaries

**Core/UI boundary**

- `editor/` may import services and models.
- Core modules must not import `editor/` or Qt widgets.
- `jobs/` may adapt service progress to Qt signal delivery.

**Workspace boundary**

- Only `workspace/` reads/writes `manifest.json` and `compositions/*.json`.
- Other modules request state through `WorkspaceService`.

**GIS/render boundary**

- `gis/` owns CRS, geometry, raster window and grid math.
- `render/` owns converting composition state into image outputs.
- `render/` can use `gis/`; `gis/` must not know about rendering or UI.

**Validation boundary**

- `validation/` exposes a stable service contract early: validate current project/target/composition context and return detailed `Issue` objects plus a compact validation summary/gate result.
- Epic 1 may define the models and persistence contract for validation summary, but full readiness rules are implemented in Epic 4.
- `validation/` reads models/context and returns `Issue` objects; it does not mutate status or write workspace.
- UI/workflow decides whether to apply state transitions after validation.

**Export boundary**

- `export/` orchestrates validation/render/template/PPTX/TXT/log.
- Export should not know about widgets.
- Template slide-copy risk isolated in `pptx_slide_copy.py`.

### Requirements to Structure Mapping

**FR-1 to FR-2 Config/Setup**

- `config/service.py`
- `config/loader.py`
- `config/path_resolver.py`
- `editor/modes/setup_mode.py`
- `editor/widgets/path_picker.py`

**FR-3 to FR-5 Ingestion**

- `ingestion/scanner.py`
- `ingestion/metadata_parser.py`
- `ingestion/intersection.py`
- `ingestion/cache_builder.py`
- `ingestion/service.py`
- `jobs/ingestion_job.py`
- `editor/widgets/ingestion_progress.py`

**FR-6 to FR-8 Workspace**

- `workspace/service.py`
- `workspace/manifest.py`
- `workspace/composition_store.py`
- `workspace/atomic_write.py`
- `models/workspace.py`
- `models/composition.py`

**FR-9 to FR-14 Review/Edit**

- `editor/modes/review_edit_mode.py`
- `editor/models/composition_tree_model.py`
- `editor/models/layer_list_model.py`
- `editor/widgets/gis_editor_view.py`
- `editor/widgets/slide_preview.py`
- `editor/widgets/review_action_bar.py`
- `editor/widgets/metadata_editor.py`

**FR-15 to FR-16 Rendering**

- `render/core.py`
- `render/preview.py`
- `render/final.py`
- `render/cache.py`
- `render/grid_drawer.py`
- `jobs/render_job.py`

**FR-17 to FR-19 Validation/Warnings**

- `validation/service.py`
- `validation/*_rules.py`
- `models/issue.py`
- `editor/models/warnings_model.py`
- `editor/widgets/warnings_panel.py`

**FR-20 to FR-23 Export**

- `export/template_loader.py`
- `export/pptx_exporter.py`
- `export/pptx_slide_copy.py`
- `export/txt_exporter.py`
- `export/log_writer.py`
- `export/service.py`
- `editor/modes/export_mode.py`
- `editor/models/export_plan_model.py`

### Integration Points

**Internal Communication**

- UI calls services.
- Services return models/results/issues.
- Long-running jobs emit progress/result/error.
- Workspace service is central state gateway.

**External Integrations**

- Filesystem local/LAN.
- GeoTIFF via rasterio/GDAL.
- GeoJSON via shapely/json parser.
- PPTX via python-pptx.
- Target one-slide PPTX templates and element-id mappings in config.

**Data Flow**

```text
Config + imagery folder
  -> ingestion
  -> workspace cache + compositions
  -> Review/Edit UI
  -> validation/render preview
  -> ready/include compositions
  -> export preflight
  -> final render PNG
  -> PPTX/TXT/log
```

### File Organization Patterns

**Configuration Files**

- User project config lives outside app, selected in Setup.
- App schema models live in `models/config.py`.
- Path resolution in `config/path_resolver.py`.

**Source Organization**

- One module per architectural responsibility.
- Services are facade entry points.
- Helpers stay local until shared by 2+ modules.

**Test Organization**

- Fixture-driven tests for GIS/render/export.
- No production sample data embedded in source package.
- Integration tests use temp workspaces.

**Asset Organization**

- MVP app icons/theme assets can later live in `editor/assets/`.
- User templates and GeoTIFFs are external data, not repo assets.

### Development Workflow Integration

**Development Runtime**

- Run app through `uv run python -m thucthengay`.
- Run tests through `uv run pytest`.
- Lint through `uv run ruff check .`.

**Build/Deployment**

- Runtime code remains separate from packaging scripts.
- Windows packaging scripts live under `scripts/` and `scripts/pyinstaller/`.
- Packaged executable validation is not complete until `ThucTheNgay.exe --smoke` passes on Windows.

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**

Các quyết định chính tương thích với nhau:

- PySide6 Qt Widgets phù hợp desktop UX spec.
- Custom Python package scaffold phù hợp app local không backend.
- File-based workspace JSON phù hợp yêu cầu inspect/recover.
- Pydantic schemas phù hợp JSON config/workspace/export template mapping.
- Service-oriented core modules giúp test headless và giữ UI không sở hữu business logic.
- Hybrid renderer phù hợp yêu cầu preview nhanh nhưng final chính xác.
- Target-specific one-slide PPTX templates phù hợp PRD đã chốt mỗi target có template riêng.

**Pattern Consistency:**

Implementation patterns hỗ trợ architecture:

- `WorkspaceService` là gateway duy nhất cho state.
- `Issue` là contract chung cho validation/UI/export.
- Long-running tasks đi qua `jobs/`.
- UI dùng model/view và không ghi JSON trực tiếp.
- Render/export không phụ thuộc Qt widgets.

**Structure Alignment:**

Project structure hỗ trợ đầy đủ module boundaries:

- `models/` chứa shared contracts.
- `config/`, `workspace/`, `ingestion/`, `gis/`, `render/`, `validation/`, `export/` tách rõ.
- `editor/` gom PySide6 UI.
- `tests/fixtures` hỗ trợ GIS/render/export integration tests.

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:**

- FR-1 to FR-2 covered by `config/` + `editor/modes/setup_mode.py`.
- FR-3 to FR-5 covered by `ingestion/` + `jobs/ingestion_job.py`.
- FR-6 to FR-8 covered by `workspace/` + `models/composition.py`.
- FR-9 to FR-14 covered by `editor/` models/widgets/modes.
- FR-15 to FR-16 covered by `render/` + `gis/` + `jobs/render_job.py`.
- FR-17 to FR-19 covered by `validation/` + `models/issue.py` + warnings UI.
- FR-20 to FR-23 covered by `export/` + final render + target PPTX template/element-id mapping.

**Non-Functional Requirements Coverage:**

- Performance: addressed by render cache, two-stage preview, stale job tokens.
- Reliability: addressed by atomic JSON writes and workspace service boundary.
- Recoverability: addressed by inspectable workspace JSON.
- Traceability: addressed by export logs and render metadata.
- Data locality: local filesystem architecture, no backend.
- Usability/accessibility: UX spec mapped to Qt model/view, keyboard rules, issue remediation.

### Implementation Readiness Validation ✅

**Decision Completeness:**

Critical decisions are documented and actionable. External exact dependency pins can be chosen during scaffold implementation, but stack choices are clear.

**Structure Completeness:**

Project tree is specific enough for agents to place code consistently. User project data layout is explicitly separate from source tree.

**Pattern Completeness:**

Naming, JSON format, service boundaries, issue handling, job progress, state transitions, render stale handling and tests are documented.

### Gap Analysis Results

**Critical Gaps:** None.

**Important Gaps:**

- Exact dependency version pins should be finalized when `pyproject.toml` is created.
- Exact target export mapping schema for PPTX element ids still needs to be written as implementation artifact.
- Exact render output DPI/pixel rules depend on the map-frame element bounds in sample PPTX templates.

**Nice-to-Have Gaps:**

- Packaging strategy has an initial PyInstaller path, but Windows build verification remains pending.
- Automated UI testing remains deferred.
- Metadata override reuse across re-ingest remains deferred.

### Validation Issues Addressed

No blocking validation issues found. The user project data layout question was addressed by adding `project_data/config.json`, `targets/`, `templates/`, `imagery/`, and `workspace/` structure with path resolution rules.

### Architecture Completeness Checklist

**Requirements Analysis**

- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**

- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**Implementation Patterns**

- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**

- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High for MVP vertical slice, medium for final packaging/export hardening.

**Key Strengths:**

- Clear module boundaries.
- Workspace state ownership is explicit.
- Render preview/final separation is defined.
- Export template risk is isolated.
- UX requirements are mapped to UI architecture.
- Tests can cover core logic without GUI.

**Areas for Future Enhancement:**

- Packaging/distribution hardening after Windows build verification.
- UI automation.
- Advanced render cache tuning.
- Metadata override persistence across re-ingest.

### Implementation Handoff

**AI Agent Guidelines:**

- Follow architecture boundaries exactly.
- Use shared Pydantic models.
- Use `WorkspaceService` for state.
- Do not let UI write JSON directly.
- Do not let validation mutate state.
- Keep render/export independent of Qt widgets.
- Add tests for every core module behavior.

**First Implementation Priority:**

Initialize scaffold and create schemas/fixtures:

```bash
uv init --app
```

Then create:

- `src/thucthengay/models/`
- initial config/composition/template/issue schemas;
- sample `project_data/` fixture;
- workspace read/write tests.
