# Story 10.2: Match Source GeoTIFFs Against Explicit GeoJSON Files

Status: review

## Story

As an Operator,
I want selected GeoJSON files to be matched directly against selected source image folders,
so that I can download imagery for exactly the AOI files I chose.

## Acceptance Criteria

1. Given the Operator selects one or more GeoJSON files, when the download run starts, then the engine loads only those explicit files, and it does not require or scan a GeoJSON folder input in the primary workflow.
2. Given a GeoJSON file contains a FeatureCollection, Feature, or geometry object, when the engine loads AOIs, then valid non-empty geometries are merged per GeoJSON file for matching, and invalid or unreadable GeoJSON produces a Vietnamese configuration error that identifies the file.
3. Given source image folders contain GeoTIFF files recursively, when the scan runs, then the engine reads raster CRS/bounds with rasterio, transforms each GeoJSON geometry to the raster CRS when needed, and tests intersection using the include-boundary-touch option.
4. Given a source image intersects multiple selected GeoJSON files, when matching completes, then the result records every matched GeoJSON for that image, and the image is eligible for output under each matched GeoJSON branch.
5. Given a raster cannot be opened or has no usable CRS, when the engine scans it, then the run records a failed-image row with the error, and scanning continues for the remaining images.

## Tasks / Subtasks

- [x] Add GeoJSON AOI loading for explicit files (AC: 1, 2)
  - [x] Load only `ResolvedSatelliteDownloadRequest.geojson_files`.
  - [x] Support FeatureCollection, Feature, and raw geometry objects.
  - [x] Merge valid non-empty geometries per GeoJSON file and retain safe GeoJSON branch name.
  - [x] Raise/return Vietnamese config errors for unreadable, invalid, empty, or mixed-CRS GeoJSON inputs.
- [x] Add source GeoTIFF discovery and raster metadata scan (AC: 3, 5)
  - [x] Recursively discover configured extensions under every resolved source image folder.
  - [x] Read CRS and bounds with rasterio.
  - [x] Record failed candidates instead of aborting the run for unreadable rasters or rasters with missing CRS.
- [x] Add AOI/raster intersection matching (AC: 3, 4)
  - [x] Transform each AOI geometry to each raster CRS when needed.
  - [x] Honor `include_boundary_touch`.
  - [x] Return match records containing source folder, source path, and all matched GeoJSON names/paths.
- [x] Add focused tests (AC: 1, 2, 3, 4, 5)
  - [x] Test explicit GeoJSON file loading for FeatureCollection, Feature, and raw geometry.
  - [x] Test recursive GeoTIFF discovery and CRS transform matching with generated fixtures.
  - [x] Test one image matching multiple GeoJSON files.
  - [x] Test unreadable raster is recorded as failed and does not stop later matches.

## Dev Notes

### Scope

Story 10.2 adds matching only. Do not implement filename/cloud filters, copy/output tree, manifest writing, job worker, or UI. Those remain in Stories 10.3 through 10.7.

### Technical Requirements

- Build on `src/thucthengay/download/` contracts from Story 10.1.
- Use `rasterio`, `shapely`, and `pyproj`, already project dependencies.
- Keep module headless; no PySide6/editor imports.
- Reuse script behavior where practical: explicit GeoJSON files, source folder safe names, extension filtering, CRS transform, `include_boundary_touch`.
- Failed raster rows should be represented in a typed match/scan result so later manifest work can report them.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 10, Story 10.2.
- `_bmad-output/implementation-artifacts/10-1-extract-reusable-satellite-download-engine.md` - download request/result contracts.
- `D:/0.TU_KHONG_XOA/1.NCPT/1.TTN/0.Download_Img/download_satellite_images_by_geojson.py` - source script functions `load_geojson_areas`, `discover_rasters`, `get_raster_metadata`, `transform_geometry`, `intersects_geometry`.
- `src/thucthengay/ingestion/intersection.py` - existing CRS transform/intersection pattern.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `conda run -n ttn-env pytest tests/unit/test_download_matching.py -q --basetemp=.pytest_tmp_codex_download_10_2_red`
- `conda run -n ttn-env pytest tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_core_import_boundaries.py -q --basetemp=.pytest_tmp_codex_download_10_2`
- `conda run -n ttn-env ruff check src/thucthengay/download tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_core_import_boundaries.py`
- `conda run -n ttn-env pytest tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_core_import_boundaries.py tests/unit/test_ingestion_scanner.py tests/unit/test_ingestion_intersection.py -q --basetemp=.pytest_tmp_codex_download_10_2_related`
- `conda run -n ttn-env ruff check .`
- `conda run -n ttn-env pytest -q --basetemp=.pytest_tmp_codex_download_10_2_full`
- `PYTHONPATH=src conda run -n ttn-env python -m thucthengay --smoke`

### Completion Notes List

- Added `match_source_images()` for explicit GeoJSON-to-source-GeoTIFF matching without output copy side effects.
- Added typed AOI, raster candidate, raster metadata, image match, failed image, and match result contracts.
- Implemented explicit GeoJSON loading for FeatureCollection, Feature, and geometry objects with per-file safe names and Vietnamese config errors.
- Implemented recursive source GeoTIFF discovery, raster CRS/bounds reads, CRS transform, include-boundary-touch behavior, and failed-raster recording.
- Added generated GeoTIFF/GeoJSON tests covering explicit files, CRS transform, multiple GeoJSON matches, failed raster continuation, and invalid GeoJSON errors.
- Full regression run reached 506 passed and 5 failures in pre-existing UI/metadata tests unrelated to the download module.

### File List

- `src/thucthengay/download/__init__.py`
- `src/thucthengay/download/matching.py`
- `src/thucthengay/download/models.py`
- `tests/unit/test_download_matching.py`
- `_bmad-output/implementation-artifacts/10-2-match-source-geotiffs-against-explicit-geojson-files.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-06-14: Created Story 10.2 context and moved status to in-progress.
- 2026-06-14: Implemented Story 10.2 explicit GeoJSON/source GeoTIFF matching; status moved to review.
