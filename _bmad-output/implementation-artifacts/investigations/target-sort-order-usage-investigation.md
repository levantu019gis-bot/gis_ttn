# Target `sort_order` Usage Investigation

## Case Info

- Date: 2026-06-03
- Input: `/home/ongtu/Working/3.ThucTheNgay/config.json`
- Question: `sort_order` of each target is used for what in the app?
- Status: Concluded

## Confirmed Evidence

- `config.json` contains 70 enabled targets, with unique `sort_order` values from 1 to 70.
- `src/thucthengay/models/config.py` declares `TargetConfig.sort_order: int = 0`.
- `src/thucthengay/config/service.py:122` sorts enabled targets by `target.sort_order` immediately after config validation.
- `src/thucthengay/editor/app_shell.py:138` and `src/thucthengay/editor/app_shell.py:142` pass that sorted `enabled_targets` list into Review/Edit and Export modes.
- `src/thucthengay/editor/models/composition_tree_model.py:168` sorts target groups by `TargetConfig.sort_order`, with unknown targets falling back to `10_000` and then target id.
- `src/thucthengay/ingestion/intersection.py:62` and `src/thucthengay/ingestion/intersection.py:68` iterate `config_result.enabled_targets`, so matching/progress order follows the sorted target list.
- `src/thucthengay/export/pptx_exporter.py:369` sorts export output by composition `review_order`, not target `sort_order`.

## Conclusion

`sort_order` is the configured default ordering of targets. It affects enabled target ordering after config load, target matching/progress traversal during ingestion, and target group ordering in the Review/Edit composition tree.

It does not control PowerPoint/TXT slide order; export slide order is driven by composition `review_order`. It also does not control render layer order or map-frame drawing order.

## Notes For Current Config

- First targets by `sort_order`: `DaBac` (1), `DaConCatTay` (2), `DaCay` (3).
- Last target by `sort_order`: `DaGacMa` (70).
- No duplicate `sort_order` values were found in the current config.
