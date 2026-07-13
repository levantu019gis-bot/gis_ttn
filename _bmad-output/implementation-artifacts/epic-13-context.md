# Epic 13 Context: Stabilize Runtime, Large-Raster Workflow, and Operational UX

## Goal

Epic 13 turns the current broad feature set into a more stable operator workflow for real Windows deployments and large satellite imagery. The epic focuses on hardening runtime state, preparing large rasters for fast display, surfacing diagnostics to users, improving data/history management, and making export failures recoverable per slide.

This epic is created from the post-review roadmap after Epic 11 and Epic 12. It should consolidate reliability work before adding another major rendering architecture.

## Source Findings

Recent review identified these priority risks:

- Windows GIS runtime can pick up the wrong `proj.db`, especially from PostgreSQL/PostGIS installations, causing many raster/CRS tests and workflows to fail.
- Ruff currently reports an import-order issue in `src/thucthengay/ingestion/__init__.py`.
- Review/Edit render state has good token guarding for successful canvas frames, but stale error results can still affect the current canvas because error application is not token-gated.
- Tile preview is improving responsiveness, but large 0.5-1 GB rasters still need a first-class COG/tiled GeoTIFF + overview preparation workflow.
- Operators need visible render diagnostics, cache status, and stronger recovery actions rather than only a basic Refresh button.
- History, filename metadata, band/symbology, and unmatched imagery workflows now exist but need a management surface for repair, testing, and batch edits.
- Export should continue on valid slides where possible and provide clearer template/preflight diagnostics.

## Strategic Direction

Epic 13 should prioritize:

1. Runtime reliability and repeatable quality gates.
2. Render state safety and recovery from stale/cancelled workers.
3. Prepared imagery workflow for large rasters.
4. Operator-visible render diagnostics and cache tuning.
5. Data/history management improvements.
6. Export preflight resilience and partial-success reporting.

## Mandatory Guardrails

- Preserve the current map-frame visual/layout contract exactly.
- Do not change frame shape, dimensions, aspect, outer frame, inner raster panel geometry, DMS labels, tick placement, label text/format, temporal-compare pane gap, pane boundaries, or map-surround spacing.
- Do not degrade final export output quality.
- Keep final export and Review/Edit preview behavior consistent unless a story explicitly changes and verifies that contract.
- Keep user-facing status text Vietnamese where surfaced in the UI.
- Do not depend on production LAN paths or real imagery in tests.
- Use generated raster fixtures and controlled environment variables for GIS/runtime tests.
- Avoid mutating original source imagery unless the user explicitly chooses an in-place preparation action.

## Story Sequencing

Story 13.1 should be implemented first because runtime GIS path stability affects tests and production.

Story 13.2 should follow because it reduces render-state races observed during pan/zoom, target switching, cancellation, and Refresh recovery.

Story 13.3 should add large-raster preparation and prepared-source selection before further tile tuning.

Story 13.4 should expose diagnostics so operators and developers can see tile counts, cache usage, and render bottlenecks.

Story 13.5 should consolidate history/metadata management after the ingestion and rendering paths are stable.

Story 13.6 should improve export preflight and partial success once template/data state can be diagnosed clearly.

## Non-Goals

- No GPU/OpenGL implementation in Epic 13 unless a later decision record and separate epic justify it.
- No redesign of the Review/Edit layout or Setup workflow beyond the controls needed for the stories.
- No automatic destructive rewrite of original source rasters.
- No broad refactor of all export/template code unless required for preflight resilience.
