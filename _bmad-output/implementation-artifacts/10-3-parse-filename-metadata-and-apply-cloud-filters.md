# Story 10.3: Parse Filename Metadata and Apply Cloud Filters

Status: review

## Story

As an Operator,
I want the download run to parse capture time and cloud percent from known filename patterns,
so that high-cloud scenes can be skipped and the manifest contains useful metadata.

## Acceptance Criteria

1. Given filename format rules are configured, when a candidate image filename is evaluated, then the first matching rule extracts capture date/time and cloud percent using the supported tokens `yyyyMMdd`, `hhMMss`, `cloud-percent`, `cloud_percent`, and `*`, and the matched rule name is recorded for manifest output.
2. Given a matched filename rule has `max_cloud_percent`, when the image cloud percent exceeds the threshold, then the image is skipped with status `skipped_cloud`, and the run increments skipped-cloud progress counters.
3. Given no filename rule matches, when the image otherwise intersects a GeoJSON, then the image can still be copied unless a future option explicitly requires metadata parsing, and the manifest records that filename format was not matched.
4. Given multiple filename rules could overlap, when options are validated or the run starts, then the app surfaces a non-blocking warning that an earlier rule may hide a later rule, and the warning includes remediation to reorder the rules.

## Tasks / Subtasks

- [x] Add filename format parser (AC: 1, 3)
  - [x] Compile supported tokens `yyyyMMdd`, `hhMMss`, `HHmmss`, `cloud-percent`, `cloud_percent`, and `*`.
  - [x] Parse capture datetime and cloud percent from the first matching rule.
  - [x] Return unmatched metadata without blocking otherwise matched images.
- [x] Add cloud filtering over matched images (AC: 2, 3)
  - [x] Preserve accepted matches with parsed/unparsed filename metadata.
  - [x] Move over-threshold matches into skipped-cloud rows.
  - [x] Update download stats skipped-cloud counter.
- [x] Add overlap warning detection (AC: 4)
  - [x] Detect when an earlier rule can match the later rule's sample filename.
  - [x] Return non-blocking Vietnamese warning text with reorder remediation.
- [x] Add focused tests (AC: 1, 2, 3, 4)
  - [x] Test first matching rule extracts date/time/cloud and rule name.
  - [x] Test over-threshold cloud skip.
  - [x] Test unmatched filename stays accepted with `matched_format=false`.
  - [x] Test overlapping rules produce warning.

## Dev Notes

### Scope

Story 10.3 works on already matched image rows from Story 10.2. Do not write output files, manifests, progress jobs, or UI. Those remain in later stories.

### Technical Requirements

- Build in `src/thucthengay/download/`.
- Keep contracts typed and headless.
- Follow source script behavior from `compile_filename_format`, `parse_filename_metadata`, `should_skip_for_cloud`, `filename_format_warnings`, and `sample_filename_from_format`.
- Do not require metadata parsing for accepted rows unless a future story adds such an option.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 10, Story 10.3.
- `D:/0.TU_KHONG_XOA/1.NCPT/1.TTN/0.Download_Img/download_satellite_images_by_geojson.py` - filename format parsing/filtering behavior.
- `_bmad-output/implementation-artifacts/10-2-match-source-geotiffs-against-explicit-geojson-files.md` - match result contracts used as input.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-06-14: RED `conda run -n ttn-env pytest tests/unit/test_download_filename_filter.py -q --basetemp=.pytest_tmp_codex_download_10_3_red` failed as expected because `filename_format_warnings` API did not exist.
- 2026-06-14: GREEN focused `conda run -n ttn-env pytest tests/unit/test_download_filename_filter.py -q --basetemp=.pytest_tmp_codex_download_10_3` passed: 4 passed.
- 2026-06-14: Regression scope `conda run -n ttn-env pytest tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_download_filename_filter.py tests/unit/test_core_import_boundaries.py -q --basetemp=.pytest_tmp_codex_download_10_3_group2` passed: 21 passed.
- 2026-06-14: `conda run -n ttn-env ruff check src/thucthengay/download tests/unit/test_download_contract.py tests/unit/test_download_matching.py tests/unit/test_download_filename_filter.py tests/unit/test_core_import_boundaries.py` passed.
- 2026-06-14: `conda run -n ttn-env ruff check .` passed with the existing Windows access warning while scanning temp folders.
- 2026-06-14: Full suite with UTF-8 output `conda run -n ttn-env pytest -q --basetemp=.pytest_tmp_codex_download_10_3_full_utf8` reported 510 passed, 5 failed in pre-existing editor/metadata/isolated Qt tests outside download scope.
- 2026-06-14: Smoke `$env:PYTHONPATH='src'; conda run -n ttn-env python -m thucthengay --smoke` passed: `3.ThucTheNgay app ready.`

### Implementation Plan

- Added headless filename parsing/filtering contracts under `thucthengay.download`.
- Kept cloud filtering after Story 10.2 matching, without output writes, manifest writes, progress jobs, or UI.
- Preserved unmatched filename rows as accepted with `matched_format=false` for later manifest generation.

### Completion Notes List

- Implemented tokenized filename format compilation for `yyyyMMdd`, `hhMMss`, `HHmmss`, `cloud-percent`, `cloud_percent`, and `*`.
- Implemented first-match metadata extraction, capture datetime parsing, cloud-percent parsing, cloud threshold skip rows, and updated skipped-cloud stats.
- Implemented non-blocking overlap warnings using later-rule sample filenames and remediation to reorder rules.
- Added focused tests covering all Story 10.3 acceptance criteria.

### File List

- src/thucthengay/download/__init__.py
- src/thucthengay/download/filename.py
- src/thucthengay/download/models.py
- tests/unit/test_download_filename_filter.py
- _bmad-output/implementation-artifacts/10-3-parse-filename-metadata-and-apply-cloud-filters.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-06-14: Created Story 10.3 context and moved status to in-progress.
- 2026-06-14: Implemented filename metadata parsing, cloud filtering, overlap warnings, focused tests, and moved story to review.
