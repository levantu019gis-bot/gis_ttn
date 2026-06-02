---
title: 'Configurable Frame Defaults'
type: 'feature'
created: '2026-06-02'
status: 'done'
route: 'one-shot'
context:
  - '_bmad-output/project-context.md'
  - '_bmad-output/implementation-artifacts/spec-map-surround-layout.md'
---

# Configurable Frame Defaults

## Intent

**Problem:** `render/frame.py` kept the map-surround reference geometry, tick limits,
stroke sizes, label defaults, and font path as private constants, so operators could not
see or tune those defaults from `config.json`.

**Approach:** Store those frame defaults under `defaults.grid.style` in `config.json`,
then have the renderer resolve frame settings from the effective target grid style with
safe fallbacks for tests and minimal configs.

## Suggested Review Order

- `config.json:7` -- confirm every requested frame default is present under
  `defaults.grid.style` and existing visual overrides remain intact.
- `src/thucthengay/render/frame.py:22` -- review fallback/default resolution and
  validation guards for invalid config values.
- `src/thucthengay/render/frame.py:86` -- review layout helpers now accepting optional
  style while preserving the previous public helper contract.
- `src/thucthengay/render/core.py:199` -- verify render output passes `spec.grid.style`
  into map-surround layout creation.
- `tests/unit/test_render_frame.py:114` -- review coverage for configured label formats,
  tick limits, reference geometry, and surround tick length.

## Verification

**Commands:**
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync pytest tests/unit/test_render_frame.py tests/unit/test_render_core.py -q` -- passed: 29 tests.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync ruff check src/thucthengay/render/frame.py src/thucthengay/render/core.py tests/unit/test_render_frame.py` -- passed.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync python -m thucthengay --smoke` -- passed.

**Known unrelated blockers observed during full checks:**
- Full `ruff check .` fails in `tests/unit/test_render_alignment.py:100` for a pre-existing
  `zip()`/line-length lint issue outside this change.
- Full `pytest -q` aborts in native code at
  `tests/unit/test_export_mode.py::test_export_mode_runs_full_export_pipeline`, including
  when run alone with `QT_QPA_PLATFORM=offscreen`.
