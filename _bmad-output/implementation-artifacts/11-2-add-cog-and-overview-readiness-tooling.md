# Story 11.2: Add COG and Overview Readiness Tooling

Status: review

## Story

As a Developer,
I want tooling and metadata support for COG/overview readiness,
So that large imagery can be prepared before deeper tile rendering changes are made.

## Acceptance Criteria

1. Given a GeoTIFF path is checked, when overview readiness runs, then it reports raster size, CRS, available overview decimation levels, block/tile hints when available, and whether the raster is likely expensive to zoom out.
2. Given a raster lacks usable overviews, when the readiness report is produced, then it includes actionable remediation for creating COG output or external overviews without silently mutating the source file.
3. Given overview metadata has already been cached for an unchanged raster, when readiness or render code asks for overview levels again, then it can reuse cached metadata keyed by source path, size, and mtime.
4. Given tests run in CI or a developer machine, when the readiness service is tested, then it uses generated lightweight raster fixtures and skips only external GDAL CLI conversion steps that are unavailable.

## Tasks / Subtasks

- [x] Add Qt-free raster overview readiness data structures and classifier (AC: 1, 2)
  - [x] Report size, CRS, driver, block/tile hints, overview ladders, file signature, and zoom-out cost hint.
  - [x] Classify ready, needs overviews, needs COG conversion, or unreadable with actionable notes.
- [x] Add cache keyed by source path, file size, and mtime (AC: 3)
  - [x] Reuse cached metadata for unchanged rasters.
  - [x] Invalidate naturally when size or mtime changes.
- [x] Add non-mutating preparation support (AC: 2, 4)
  - [x] Generate remediation/preparation plans that default to writing a separate output.
  - [x] Provide explicit output preparation without silently mutating source imagery.
- [x] Add focused tests with generated raster fixtures (AC: 1, 2, 3, 4)
  - [x] Verify overviews and missing-overview classifications.
  - [x] Verify unreadable classification and cache reuse.
  - [x] Verify preparation defaults do not mutate source files.
- [x] Run focused quality gates
  - [x] `pytest tests/unit/test_render_overview_readiness.py`

## Dev Notes

- Epic 11 is a performance/refactor epic only. This story must not alter the map-frame visual/layout contract: frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or map-surround spacing.
- Keep readiness tooling below the render/UI layout layer. It may inspect raster sources and create separate prepared outputs, but it must not change render spec geometry or frame drawing behavior.
- Prefer rasterio metadata APIs over shelling out to GDAL CLI in unit-tested paths.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.2]
- [Source: _bmad-output/implementation-artifacts/epic-11-context.md#COG / Overview Readiness]
- [Source: SOLUTION.md]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_overview_readiness.py` - passed (`8 passed`).
- `$env:PYTHONPATH='src'; conda run -n ttn-env ruff check src/thucthengay/render/overview.py src/thucthengay/render/__init__.py tests/unit/test_render_overview_readiness.py` - passed.
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_render_diagnostics.py tests/unit/test_render_overview_readiness.py tests/unit/test_render_core.py tests/unit/test_render_raster.py` - passed (`44 passed`).
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest` - passed (`571 passed`).

### Completion Notes List

- Added Qt-free raster readiness metadata and classification for ready, needs-overviews, needs-COG, and unreadable sources.
- Added overview metadata cache keyed by path, file size, and mtime so unchanged raster checks can reuse prior results.
- Added render-spec readiness inspection that covers normal visible layers and temporal compare panes while deduplicating source paths.
- Added explicit preparation planning and output creation. By default, no source file is mutated; prepared copies are written only to an explicit `output_path`, `output_dir`, or explicit `mutate_source=True` plan.
- Preserved Epic 11 map-frame invariance by keeping all changes in metadata/preparation helpers and tests, with no edits to frame geometry, label, tick, pane-gap, or render-layout code.

### File List

- `_bmad-output/implementation-artifacts/11-2-add-cog-and-overview-readiness-tooling.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `src/thucthengay/render/overview.py`
- `src/thucthengay/render/__init__.py`
- `tests/unit/test_render_overview_readiness.py`
