---
title: 'Group-scoped target order'
type: 'feature'
created: '2026-06-03'
status: 'done'
baseline_commit: 'a252c25f85206dad86a5625b61eda14ccb51eda7'
context:
  - '{project-root}/_bmad-output/project-context.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** `sort_order` is currently global, so it cannot be reset from `1` inside each target group without changing app ordering behavior. Review/Edit also displays targets without real group nodes and advances through workspace manifest order, which can diverge from the visible tree.

**Approach:** Treat `group.key` as the primary target ordering key and `sort_order` as the per-group ordering key. Show Review/Edit as `group -> target -> composition`, and make previous/next review navigation follow the visible tree order.

## Boundaries & Constraints

**Always:** Preserve the current target/composition selection roles; group `0` remains "Chưa phân nhóm" and sorts after official groups; composition children keep their existing per-target sort by review state/date.

**Ask First:** Reclassifying group `0` targets into official groups, changing export `review_order`, or migrating existing workspace manifests.

**Never:** Use manifest string order as the Review/Edit action queue, remove queue filters, or rewrite unrelated example/workspace files.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Grouped config | Targets share `sort_order` values across different `group.key` values | Config loader returns targets ordered by group first, then per-group `sort_order` | Missing group sorts after official groups |
| Review tree | Compositions from targets in multiple groups | Tree root nodes are groups; each group contains sorted targets; each target contains sorted compositions | Unknown target is placed in "Chưa phân nhóm" |
| Review navigation | Manifest order differs from visible tree order | Include/Skip/Previous walks visible composition order from top to bottom | If no neighbor exists, remain on current composition |

</frozen-after-approval>

## Code Map

- `src/thucthengay/models/config.py` -- target group schema and shared target ordering helper.
- `src/thucthengay/config/service.py` -- enabled target sorting during config load.
- `src/thucthengay/editor/models/composition_tree_model.py` -- Review/Edit tree projection and visible navigation order.
- `src/thucthengay/editor/modes/review_edit_mode.py` -- review action navigation.
- `config.json` -- production target order data.
- `tests/unit/test_config_service.py`, `tests/unit/test_review_edit_mode.py`, `tests/unit/test_warnings_panel_and_issue_ui.py` -- behavior coverage.

## Tasks & Acceptance

**Execution:**
- [x] `src/thucthengay/models/config.py` -- add target group/order helpers -- keep ordering consistent across loader and UI.
- [x] `src/thucthengay/config/service.py` -- sort enabled targets by group then local order -- support duplicated `sort_order` across groups.
- [x] `src/thucthengay/editor/models/composition_tree_model.py` -- add group nodes and visible neighbor helpers -- make tree order explicit.
- [x] `src/thucthengay/editor/modes/review_edit_mode.py` -- use visible tree neighbors for previous/next actions -- prevent manifest-order jumps.
- [x] `config.json` -- reorder targets by group and reset `sort_order` within each group -- align data with new semantics.
- [x] tests -- update and add focused coverage -- verify grouped tree, loader sort, and navigation behavior.

**Acceptance Criteria:**
- Given targets in multiple groups with duplicate `sort_order`, when config loads, then targets are ordered by `group.key`, then per-group `sort_order`, then id.
- Given Review/Edit loads multiple target groups, when the tree is built, then root rows are group nodes and target rows do not interleave across groups.
- Given manifest order differs from tree order, when Include/Skip advances, then the next selected composition is the next visible composition in the tree.
- Given a queue filter is active, when navigating, then previous/next only considers compositions visible under that filter.

## Spec Change Log

## Design Notes

The ordering helper should be shared rather than duplicated. Numeric dotted keys such as `2.2.1` sort by numeric segments, while `0` and missing group are treated as an unassigned bucket after official groups.

## Verification

**Commands:**
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync pytest tests/unit/test_models.py tests/unit/test_config_service.py tests/unit/test_review_edit_mode.py tests/unit/test_warnings_panel_and_issue_ui.py -q` -- passed: `106 passed`.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync pytest tests/unit/test_ingestion_intersection.py tests/unit/test_ingestion_job.py tests/unit/test_ingestion_composition_builder.py -q` -- passed: `16 passed`.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync ruff check src/thucthengay/models/config.py src/thucthengay/models/__init__.py src/thucthengay/config/service.py src/thucthengay/editor/models/composition_tree_model.py src/thucthengay/editor/modes/review_edit_mode.py tests/unit/test_config_service.py tests/unit/test_review_edit_mode.py tests/unit/test_warnings_panel_and_issue_ui.py` -- passed.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync python -c "from thucthengay.config import load_project_config; r=load_project_config('config.json'); print('ok', r.ok, 'targets', len(r.enabled_targets), 'issues', len(r.issues))"` -- passed: `ok True targets 70 issues 0`.
- `/home/ongtu/miniconda3/bin/conda run -n ttn-env env UV_PROJECT_ENVIRONMENT=/home/ongtu/miniconda3/envs/ttn-env uv run --no-sync python -m thucthengay --smoke` -- passed: `3.ThucTheNgay app ready.`
- Full `pytest -q` currently aborts in native Qt/PySide after the export-mode tests begin. The isolated test shown by verbose output passes when run alone, so this is recorded as a full-suite native stability issue outside this change's acceptance scope.
