# Story 13.3: Add Large-Raster Preparation and Prepared Source Selection

Status: done

## Story

As an Operator,
I want large source rasters prepared into tiled GeoTIFF/COG files with overview pyramids,
So that Review/Edit can display 0.5-1 GB imagery without crashing or decoding full-resolution data unnecessarily.

## Acceptance Criteria

1. Given a large raster lacks tiling or overview levels, when ingestion or Review/Edit detects it, then the app reports a clear readiness warning and offers a non-destructive preparation path.
2. Given the user chooses to prepare imagery, when the job runs, then a separate prepared output is created as COG or tiled GeoTIFF with internal overviews, without mutating the original file by default.
3. Given a prepared raster exists, when Review/Edit builds render specs or tile jobs, then it prefers the prepared path while preserving source-path traceability.
4. Given preparation is interrupted or fails, when the workspace is reopened, then partial files are not treated as valid prepared imagery and actionable errors are shown.
5. Given export records history or managed source paths, when prepared imagery is used for display, then the original source path and prepared/cache path remain distinct and auditable.

## Tasks / Subtasks

- [x] Add config/workspace fields for prepared imagery root and preparation policy.
- [x] Build a preparation job around existing `render.overview` helpers.
- [x] Add readiness/preparation UI entry points from Setup or Review/Edit.
- [x] Store prepared path metadata per layer without losing original source path.
- [x] Prefer prepared path for preview/tile decode when available.
- [x] Add tests for COG/tiled output planning, failed preparation, and prepared-source selection.

## Dev Notes

- Reuse `src/thucthengay/render/overview.py`.
- Default behavior must be non-mutating.
- Prepared imagery should help large raster preview; final export quality must remain explicit and tested.

## Verification

- Overview/preparation unit tests
- Ingestion/workspace metadata tests
- Review/Edit render spec/path selection tests
