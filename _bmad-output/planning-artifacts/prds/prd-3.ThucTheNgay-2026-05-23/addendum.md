# PRD Addendum

## Source Inputs

- Product brief: `_bmad-output/planning-artifacts/briefs/brief-3.ThucTheNgay-2026-05-23/brief.md`
- Brief addendum: `_bmad-output/planning-artifacts/briefs/brief-3.ThucTheNgay-2026-05-23/addendum.md`
- Brainstorming session: `_bmad-output/brainstorming/brainstorming-session-2026-05-23-163752.md`

## Technical Decisions Carried Forward

- App type: desktop app.
- UI: PySide6/PyQt6.
- GIS editor/viewer MVP: QGraphicsView self-rendered; no PyQGIS.
- GIS/raster processing: rasterio, GDAL, shapely, pyproj, numpy, Pillow.
- PowerPoint export: python-pptx plus controlled XML/media handling if needed.
- Config/state: JSON.
- Architecture: layered modules `config`, `ingestion`, `workspace`, `gis`, `editor`, `render`, `export`, `validation`.
- `workspace/` is source of truth for manifest, composition JSON, status, validation summary and output paths.

## Data Model Direction

### Target Config

Each target declares all needed fields explicitly. No hidden file-level defaults for target settings.

Key fields:

- `id`, `enabled`, `sort_order`
- `name`, `alias`, `title`
- `geojson_file`
- `coordinate` `[lon, lat]`
- `scale` as map scale denominator, e.g. `50000` means 1:50,000
- `grid.interval`
- `grid` label/style settings
- `export.template_pptx_file`
- `image_rules`
- `map_frame.background_rgb`
- `metadata`

### Composition

`composition = target + date` and maps to one exported slide when included.

Key state:

- `schema_version`
- `composition_id`
- `target_id`
- `date`
- `status.reviewed`, `status.ready`, `status.include`, `status.review_order`, `status.notes`
- `view.center` `[lon, lat]`
- `view.scale`
- `view.rotation = 0`
- `grid` override
- `layers[]`
- `validation_summary`

### Layer

Layer persists workflow metadata:

- `layer_id`
- `workspace_path`
- `visible`
- `order`
- `capture_date`
- `capture_time`
- `timestamp_source`
- `cloud_percent`
- `metadata_status`
- `metadata_notes`

Raster technical metadata is read from GeoTIFF at validate/render time.

### Issue

Issue schema:

- `issue_id`
- `severity`
- `scope`
- `target_id`
- `composition_id`
- `layer_id` optional
- `message`
- `remediation`
- `blocking`

`issue_id` is English; UI/log text is Vietnamese.

### Validation Contract

- Validation services return detailed `Issue` objects plus a compact summary/gate result.
- Composition JSON persists only the validation summary; detailed issues are derived from current config/workspace/composition/layer/template state.
- Enabled target config validation must require `coordinate`, positive `scale` denominator, valid `grid.interval`, `geojson_file`, and `export.template_pptx_file`.
- Full composition readiness rules are implemented in the validation layer after workspace/config contracts exist.

## Rendering Direction

- View source-of-truth is `center` `[lon, lat]` + `scale`; initial composition view is copied from target `coordinate` + `scale`. `scale` is persisted as the map scale denominator, e.g. `50000` means 1:50,000. Render math derives ground width/height from template map-frame physical size multiplied by `scale`, then centers that window on `view.center`.
- Core render math is shared by preview and final render.
- Preview uses cache/downsample/overview.
- GIS editor uses two-stage render: interactive rough render while moving, sharper settle render when idle.
- Final render reads raster at quality appropriate to template map frame output size.

## Template and Export Direction

- Each target points directly to its own one-slide PPTX template.
- Target export config stores the PowerPoint element-id replacement mapping for map image and text/image placeholders.
- Shape replacement uses the resolved PPTX element id as the authoritative lookup key. Configured ids remain supported, and stable selectors/shape names such as `ttn:<field>` may be used during template load to repair volatile PowerPoint ids before export.
- Output remains one combined PPTX sorted by composition review order.
- MVP constraint: all target templates are created from the same compatible base/theme/master.

## Suggested Epic Direction

1. Config, sample fixtures and workspace foundation.
2. Data ingestion and composition creation.
3. Raster render core and final PNG export.
4. Target-specific PPTX/TXT export vertical slice.
5. Review/Edit UI shell and composition state editing.
6. Validation, warnings and metadata correction.
7. Setup/Export modes, progress, preflight and logs.
8. Preview performance and two-stage render hardening.
