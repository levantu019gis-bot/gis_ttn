# Story 13.4: Surface Render Diagnostics and Cache Tuning in Review/Edit

Status: done

## Story

As an Operator or Developer,
I want visible render diagnostics and cache status in Review/Edit,
So that slow display can be diagnosed from the app instead of guessed from logs.

## Acceptance Criteria

1. Given render diagnostics are enabled, when Review/Edit renders or progressively loads tiles, then the UI can show tile count, decoded count, cache hit/miss, cache memory usage, decode time, compose time, and total latency.
2. Given tile preview is enabled, when pan/zoom occurs, then diagnostics distinguish cached reuse, missing tile decode, partial repaint, and full recomposition.
3. Given a raster lacks overviews or is not tiled, when diagnostics are shown, then the user sees a warning and recommended preparation action.
4. Given diagnostics are disabled, when normal Review/Edit is used, then the UI remains quiet and rendering behavior is unchanged.
5. Given operators tune config values, when cache/tile settings are changed and config is reloaded, then diagnostics make the effect observable.

## Tasks / Subtasks

- [x] Add a compact diagnostics panel or expandable status area in Review/Edit.
- [x] Expose tile cache bytes/entries and per-render counters.
- [x] Surface overview readiness warnings near the canvas or target preview.
- [x] Add copy/export diagnostics summary action for troubleshooting.
- [x] Add tests for diagnostics visibility, hidden state, and key metrics.

## Dev Notes

- Reuse `RenderDiagnostics` and existing tile-preview counters.
- Avoid adding visible explanatory text clutter during normal operation; make diagnostics opt-in or expandable.
- Keep user-facing labels Vietnamese.

## Verification

- Review/Edit diagnostics widget tests
- Render diagnostics unit tests
- Manual pan/zoom comparison with tile preview enabled
