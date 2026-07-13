# Story 13.2: Make Render State, Cancellation, and Refresh Recovery Robust

Status: done

## Story

As an Operator,
I want pan/zoom, target switching, cancellation, and Refresh to recover reliably,
So that old worker results cannot blank the canvas, show stale errors, or prevent later imagery from rendering.

## Acceptance Criteria

1. Given a render worker from an old viewport, target, or composition finishes late with success, warning, cancellation, or error, when the canvas has moved to a newer generation, then the old result is ignored.
2. Given the current render is cancelled during pan/zoom or target switching, when new imagery is requested, then queued decode work is cancelled cooperatively and does not block later render requests.
3. Given Refresh is clicked after a stuck, cancelled, or failed tile preview, when a composition is selected, then the app cancels old work, clears relevant caches/state, starts a new render generation, and surfaces a clear status.
4. Given progressive tile frames arrive after a newer request has superseded them, when they are handled by Review/Edit, then they cannot overwrite the current canvas or tile state.
5. Given errors are shown on the canvas, when they originate from stale workers, then they are not applied to the current canvas.

## Tasks / Subtasks

- [x] Token-gate error application in `GisCanvas` and Review/Edit render handlers.
- [x] Add a hard-refresh path that invalidates render epochs, cancels active workers, clears render/tile caches, and requeues the selected composition.
- [x] Audit tile worker shutdown and `ThreadPoolExecutor` cancellation for pending futures.
- [x] Add tests for stale success, stale error, Refresh after cancellation, and target switch during tile decode.
- [x] Add concise Vietnamese status messages for hard refresh and stale/cancelled recovery.

## Dev Notes

- `GisCanvas.apply_render_result()` already compares `RenderRequestToken`; align error handling with the same rule.
- Keep cooperative cancellation. Do not use unsafe thread termination.
- This story directly addresses observed symptoms: black canvas flash, frame reverting after pan, and Refresh not recovering after target switch during tile decode.

## Verification

- Focused Review/Edit render-state tests
- Tile preview worker cancellation tests
- Manual pan/zoom + target switch smoke with tile preview enabled
