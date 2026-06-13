# Historical Images One Layer Investigation

## Case Info

- Date: 2026-06-13
- Scope: historical image loading from SQLite into workspace compositions and Review/Edit display.
- User observation: historical composition for a target currently displays only one image.

## Evidence

- Confirmed: `config.json` sets `historical_loading.image_selection.mode` to `latest_images` with `limit_per_target` set to `1`.
- Confirmed: `SetupMode._selected_historical_image_selection()` returns `HistoricalSelectionMode.LATEST_IMAGES` with `limit_per_target=1` for the "Latest image" UI option.
- Confirmed: `HistoryService._query_latest_image_records()` applies `LIMIT ?` using `limit_per_target`.
- Confirmed: `HistoryService._query_latest_date_records()` returns all active image records for the latest capture date, not just one.
- Confirmed: `populate_workspace_cache()` appends every historical record it receives into `layers_by_target_date`.
- Confirmed: `create_target_date_compositions()` creates a composition with all layers in the target/date group.

## Conclusion

The display layer is not the first limiting point. With the current config/UI selection, the loader only asks SQLite for one historical image per target, so the resulting historical composition naturally contains one historical layer. To load all images from the latest historical day/composition, use `latest_date` instead of `latest_images limit_per_target=1`, or update the Setup UI wording/default behavior to expose that mode.
