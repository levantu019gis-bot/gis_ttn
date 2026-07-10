# Story 11.1: Instrument Render Pipeline and Establish Baseline Metrics

Status: review

## Story

As a Developer,
I want render performance instrumentation around the current preview pipeline,
So that optimization work is driven by measured bottlenecks instead of guesses.

## Acceptance Criteria

1. Given render diagnostics are enabled for Review/Edit preview, when a composition is rendered, panned, and zoomed, then the diagnostic output records timing for raster window reads, resampling/scaling, QImage conversion, QPixmap conversion, paint/composite work, cache hits/misses, output dimensions, and total render latency.
2. Given diagnostics are disabled, when normal Review/Edit rendering runs, then the render behavior and UI remain unchanged except for negligible instrumentation overhead.
3. Given a diagnostic run includes large GeoTIFF inputs, when the diagnostic summary is written, then it reports whether each raster has usable overview levels and records enough file signature data to compare later runs.
4. Given a developer runs focused tests, when instrumentation code is exercised with generated raster fixtures, then tests verify metrics are collected without requiring PySide widgets or production imagery.
5. Given render diagnostics are enabled or disabled, when the same render spec is used, then diagnostics do not alter map-frame geometry, labels, pane gaps, or final/preview visual layout.

## Tasks / Subtasks

- [x] Add Qt-free render diagnostic data structures and collector (AC: 1, 2, 3, 4)
  - [x] Capture timing buckets, counters, cache hit/miss counts, output dimensions, and raster source metadata.
  - [x] Keep diagnostics optional so existing render calls retain current behavior when no collector is supplied.
- [x] Instrument raster and map render services without changing layout contracts (AC: 1, 2, 5)
  - [x] Measure raster read/scaling, total render latency, cache activity, frame/composite work, and output dimensions.
  - [x] Preserve map-frame shape, size, labels, ticks, pane gaps, pane boundaries, and map-surround spacing.
- [x] Add Review/Edit canvas conversion hooks (AC: 1, 2, 5)
  - [x] Measure QImage conversion, QPixmap conversion, and paint/composite work only when diagnostics are attached.
- [x] Add focused unit tests with generated raster fixtures (AC: 3, 4, 5)
  - [x] Verify metrics and raster overview metadata are collected.
  - [x] Verify diagnostics do not alter rendered canvas shape/pixels for the same render spec.
- [x] Run focused quality gates
  - [x] `pytest tests/unit/test_render_diagnostics.py tests/unit/test_render_core.py tests/unit/test_render_raster.py`

## Dev Notes

- Epic 11 is a performance/refactor epic only. This story must not alter the map-frame visual/layout contract: frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or map-surround spacing.
- Prefer instrumentation at service boundaries over widget behavior changes. `render/` must remain Qt-free.
- Reuse current caches and render spec math. Diagnostics must observe the pipeline, not choose different render paths.
- Raster overview detection should be read-only and must not mutate source imagery.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 11.1]
- [Source: _bmad-output/implementation-artifacts/epic-11-context.md]
- [Source: SOLUTION.md]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; conda run -n ttn-env pytest tests/unit/test_render_diagnostics.py tests/unit/test_render_core.py tests/unit/test_render_raster.py` - passed (`36 passed`).
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; conda run -n ttn-env pytest tests/unit/test_render_diagnostics.py tests/unit/test_render_core.py tests/unit/test_render_raster.py tests/unit/test_render_job.py tests/unit/test_review_edit_mode.py -k "render_diagnostics or render_map or raster or preview or canvas"` - passed (`60 passed, 50 deselected`).
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest tests/unit/test_move_layer_date_change.py` - passed (`17 passed`).
- `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONIOENCODING='utf-8'; conda run -n ttn-env pytest` - passed (`563 passed`).
- `$env:PYTHONPATH='src'; conda run -n ttn-env ruff check src/thucthengay/render/diagnostics.py src/thucthengay/render/raster.py src/thucthengay/render/core.py src/thucthengay/render/__init__.py src/thucthengay/jobs/render_job.py src/thucthengay/editor/widgets/gis_canvas.py src/thucthengay/editor/modes/review_edit_mode.py tests/unit/test_render_diagnostics.py` - passed.

### Completion Notes List

- Added opt-in `RenderDiagnostics` collector with immutable summaries, timing buckets, counters, cache hit/miss counts, and raster source overview/signature metadata.
- Instrumented raster read/scaling, total raster timing, full map timing, cache activity, frame overlay/composite, QImage conversion, QPixmap conversion, and canvas paint/scene render hooks.
- Kept diagnostics passive and optional; tests verify rendered pixels and canvas shape are unchanged for the same render spec.
- Fixed Review/Edit metadata save fallback so direct `layer_id` metadata updates do not require an already selected layer row, and missing `source_path` preserves the existing layer source path.

### File List

- `_bmad-output/implementation-artifacts/11-1-instrument-render-pipeline-and-establish-baseline-metrics.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `src/thucthengay/render/diagnostics.py`
- `src/thucthengay/render/raster.py`
- `src/thucthengay/render/core.py`
- `src/thucthengay/render/__init__.py`
- `src/thucthengay/jobs/render_job.py`
- `src/thucthengay/editor/widgets/gis_canvas.py`
- `src/thucthengay/editor/modes/review_edit_mode.py`
- `tests/unit/test_render_diagnostics.py`

## Change Log

- 2026-07-09: Created Story 11.1 artifact and moved story into active implementation.
- 2026-07-09: Implemented render diagnostics instrumentation, added generated-raster tests, ran full regression and moved story to review.
