from __future__ import annotations

import ast
import sqlite3
from datetime import date, time
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from thucthengay.history import (
    HistoricalLoadingPlan,
    HistoryInitializationResult,
    HistoryRecordError,
    HistoryService,
)
from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    HistoricalImageSelectionConfig,
    ImageLayer,
    MetadataSource,
    MetadataStatus,
    TargetConfig,
    TargetExportConfig,
    ViewState,
)


def test_disabled_history_service_is_noop_and_creates_no_database(tmp_path: Path) -> None:
    service = HistoryService.disabled()

    result = service.initialize()

    assert result == HistoryInitializationResult(
        enabled=False,
        database_path=None,
        schema_version=None,
    )
    assert list(tmp_path.iterdir()) == []


def test_history_service_initializes_schema_idempotently(tmp_path: Path) -> None:
    database_path = tmp_path / "history" / "registry.sqlite"
    service = HistoryService(database_path)

    first = service.initialize()
    second = service.initialize()

    assert first.enabled is True
    assert first.database_path == database_path.resolve()
    assert second.schema_version == first.schema_version
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        schema_rows = connection.execute("SELECT id, version FROM schema_version").fetchall()

    assert {
        "schema_version",
        "target_history",
        "image_asset",
        "target_image_history",
        "include_event",
    }.issubset(tables)
    assert schema_rows == [(1, 1)]


def test_history_service_enables_foreign_keys_for_service_connections(
    tmp_path: Path,
) -> None:
    service = HistoryService(tmp_path / "registry.sqlite")
    service.initialize()

    with service._connect() as connection, pytest.raises(sqlite3.IntegrityError):
        with connection:
            connection.execute(
                """
                INSERT INTO target_image_history (
                    target_history_id,
                    image_asset_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (999, 999, "2026-06-09T00:00:00Z", "2026-06-09T00:00:00Z"),
            )


def test_history_service_rolls_back_failed_transactions(tmp_path: Path) -> None:
    service = HistoryService(tmp_path / "registry.sqlite")
    service.initialize()

    with service._connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO target_history (
                        target_id,
                        target_name,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        "target_a",
                        "Target A",
                        "2026-06-09T00:00:00Z",
                        "2026-06-09T00:00:00Z",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO target_image_history (
                        target_history_id,
                        image_asset_id,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        cursor.lastrowid,
                        999,
                        "2026-06-09T00:00:00Z",
                        "2026-06-09T00:00:00Z",
                    ),
                )

    with sqlite3.connect(service.database_path) as connection:
        rows = connection.execute("SELECT target_id FROM target_history").fetchall()

    assert rows == []


def test_history_service_does_not_force_wal_journal_mode(tmp_path: Path) -> None:
    database_path = tmp_path / "registry.sqlite"

    HistoryService(database_path).initialize()

    with sqlite3.connect(database_path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert journal_mode.lower() != "wal"


def test_record_included_composition_writes_target_image_link_and_event(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "registry.sqlite"
    service = HistoryService(database_path)
    service.initialize()
    composition = _included_composition()

    result = service.record_included_composition(
        composition,
        target=_target_config(),
        workspace_path=tmp_path / "workspace",
    )

    with sqlite3.connect(database_path) as connection:
        target_rows = connection.execute(
            "SELECT target_id, target_name, target_alias FROM target_history"
        ).fetchall()
        image_rows = connection.execute(
            """
            SELECT source_path, cache_path, capture_date, capture_time, cloud_percent
            FROM image_asset
            ORDER BY source_path
            """
        ).fetchall()
        link_rows = connection.execute(
            """
            SELECT latest_workspace_path, latest_composition_id
            FROM target_image_history
            """
        ).fetchall()
        event_rows = connection.execute(
            "SELECT workspace_path, composition_id FROM include_event"
        ).fetchall()

    assert result.recorded_layers == 1
    assert result.include_events == 1
    assert target_rows == [("alpha", "Alpha Target", "A")]
    assert image_rows == [
        (
            "imagery/alpha-visible.tif",
            "cache/alpha/20260525/alpha-visible.tif",
            "2026-05-25",
            "08:30:00",
            12.5,
        )
    ]
    assert link_rows == [(str((tmp_path / "workspace").resolve()), "alpha__20260525")]
    assert event_rows == [(str((tmp_path / "workspace").resolve()), "alpha__20260525")]


def test_record_included_composition_updates_link_and_appends_events(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "registry.sqlite"
    service = HistoryService(database_path)
    service.initialize()
    target = _target_config()
    composition = _included_composition()

    service.record_included_composition(
        composition,
        target=target,
        workspace_path=tmp_path / "workspace-a",
    )
    service.record_included_composition(
        composition.model_copy(update={"composition_id": "alpha__20260525_repeat"}),
        target=target,
        workspace_path=tmp_path / "workspace-b",
    )

    with sqlite3.connect(database_path) as connection:
        link_rows = connection.execute(
            """
            SELECT latest_workspace_path, latest_composition_id
            FROM target_image_history
            """
        ).fetchall()
        event_count = connection.execute("SELECT COUNT(*) FROM include_event").fetchone()[0]

    assert link_rows == [
        (str((tmp_path / "workspace-b").resolve()), "alpha__20260525_repeat")
    ]
    assert event_count == 2


def test_record_included_composition_disabled_service_is_noop(tmp_path: Path) -> None:
    service = HistoryService.disabled()

    result = service.record_included_composition(
        _included_composition(),
        target=_target_config(),
        workspace_path=tmp_path / "workspace",
    )

    assert result.recorded_layers == 0
    assert result.include_events == 0
    assert list(tmp_path.iterdir()) == []


def test_load_historical_images_latest_date_returns_all_images_from_latest_day(
    tmp_path: Path,
) -> None:
    service = HistoryService(tmp_path / "registry.sqlite")
    service.initialize()
    _record_history_image(service, "old.tif", date(2026, 5, 20), time(7, 0))
    _record_history_image(service, "new-a.tif", date(2026, 5, 25), time(8, 0))
    _record_history_image(service, "new-b.tif", date(2026, 5, 25), time(9, 0))

    result = service.load_historical_images(
        HistoricalLoadingPlan(
            enabled=True,
            database_path=tmp_path / "registry.sqlite",
            target_ids=("alpha",),
            image_selection=HistoricalImageSelectionConfig(mode="latest_date"),
        )
    )

    assert [record.source_path.name for record in result.records] == [
        "new-b.tif",
        "new-a.tif",
    ]


def test_load_historical_images_selection_modes_filter_per_target(
    tmp_path: Path,
) -> None:
    service = HistoryService(tmp_path / "registry.sqlite")
    service.initialize()
    _record_history_image(service, "may-01.tif", date(2026, 5, 1), time(7, 0))
    _record_history_image(service, "may-20.tif", date(2026, 5, 20), time(8, 0))
    _record_history_image(service, "jun-05.tif", date(2026, 6, 5), time(9, 0))
    _record_history_image(service, "beta.tif", date(2026, 6, 6), time(9, 0), target_id="beta")

    latest_images = service.load_historical_images(
        HistoricalLoadingPlan(
            enabled=True,
            database_path=tmp_path / "registry.sqlite",
            target_ids=("alpha",),
            image_selection=HistoricalImageSelectionConfig(
                mode="latest_images",
                limit_per_target=2,
            ),
        )
    )
    date_range = service.load_historical_images(
        HistoricalLoadingPlan(
            enabled=True,
            database_path=tmp_path / "registry.sqlite",
            target_ids=("alpha",),
            image_selection=HistoricalImageSelectionConfig(
                mode="date_range",
                start_date=date(2026, 5, 15),
                end_date=date(2026, 5, 31),
            ),
        )
    )
    lookback = service.load_historical_images(
        HistoricalLoadingPlan(
            enabled=True,
            database_path=tmp_path / "registry.sqlite",
            target_ids=("alpha",),
            image_selection=HistoricalImageSelectionConfig(
                mode="lookback_days",
                lookback_days=10,
            ),
            current_session_latest_capture_date=date(2026, 6, 9),
        )
    )

    assert [record.source_path.name for record in latest_images.records] == [
        "jun-05.tif",
        "may-20.tif",
    ]
    assert [record.source_path.name for record in date_range.records] == ["may-20.tif"]
    assert [record.source_path.name for record in lookback.records] == ["jun-05.tif"]


def test_load_historical_images_caps_latest_selection_to_current_session_date(
    tmp_path: Path,
) -> None:
    service = HistoryService(tmp_path / "registry.sqlite")
    service.initialize()
    _record_history_image(service, "jun-09.tif", date(2026, 6, 9), time(7, 0))
    _record_history_image(service, "jun-10-a.tif", date(2026, 6, 10), time(8, 0))
    _record_history_image(service, "jun-10-b.tif", date(2026, 6, 10), time(9, 0))
    _record_history_image(service, "jun-11.tif", date(2026, 6, 11), time(10, 0))

    latest_images = service.load_historical_images(
        HistoricalLoadingPlan(
            enabled=True,
            database_path=tmp_path / "registry.sqlite",
            target_ids=("alpha",),
            image_selection=HistoricalImageSelectionConfig(
                mode="latest_images",
                limit_per_target=2,
            ),
            current_session_latest_capture_date=date(2026, 6, 10),
        )
    )
    latest_date = service.load_historical_images(
        HistoricalLoadingPlan(
            enabled=True,
            database_path=tmp_path / "registry.sqlite",
            target_ids=("alpha",),
            image_selection=HistoricalImageSelectionConfig(mode="latest_date"),
            current_session_latest_capture_date=date(2026, 6, 10),
        )
    )

    assert [record.source_path.name for record in latest_images.records] == [
        "jun-10-b.tif",
        "jun-10-a.tif",
    ]
    assert [record.source_path.name for record in latest_date.records] == [
        "jun-10-b.tif",
        "jun-10-a.tif",
    ]


def test_load_historical_images_caps_date_windows_to_current_session_date(
    tmp_path: Path,
) -> None:
    service = HistoryService(tmp_path / "registry.sqlite")
    service.initialize()
    _record_history_image(service, "jun-05.tif", date(2026, 6, 5), time(7, 0))
    _record_history_image(service, "jun-10.tif", date(2026, 6, 10), time(8, 0))
    _record_history_image(service, "jun-11.tif", date(2026, 6, 11), time(9, 0))

    date_range = service.load_historical_images(
        HistoricalLoadingPlan(
            enabled=True,
            database_path=tmp_path / "registry.sqlite",
            target_ids=("alpha",),
            image_selection=HistoricalImageSelectionConfig(
                mode="date_range",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
            ),
            current_session_latest_capture_date=date(2026, 6, 10),
        )
    )
    assert [record.source_path.name for record in date_range.records] == [
        "jun-10.tif",
        "jun-05.tif",
    ]


def test_load_historical_images_warns_and_skips_missing_paths(
    tmp_path: Path,
) -> None:
    service = HistoryService(tmp_path / "registry.sqlite")
    service.initialize()
    missing_path = tmp_path / "moved" / "missing.tif"
    _record_history_image(
        service,
        missing_path,
        date(2026, 5, 25),
        time(8, 0),
        create_file=False,
    )

    result = service.load_historical_images(
        HistoricalLoadingPlan(
            enabled=True,
            database_path=tmp_path / "registry.sqlite",
            target_ids=("alpha",),
            image_selection=HistoricalImageSelectionConfig(mode="latest_date"),
        )
    )

    assert result.records == []
    assert result.loaded_image_count == 0
    assert result.skipped_image_count == 1
    assert [issue.issue_id for issue in result.issues] == ["historical.path_missing"]
    issue = result.issues[0]
    assert issue.target_id == "alpha"
    assert issue.layer_id is not None
    assert str(missing_path) in issue.message
    assert issue.remediation is not None


def test_load_historical_images_warns_and_skips_unreadable_geotiffs(
    tmp_path: Path,
) -> None:
    service = HistoryService(tmp_path / "registry.sqlite")
    service.initialize()
    unreadable_path = tmp_path / "bad.tif"
    unreadable_path.write_text("not a geotiff", encoding="utf-8")
    _record_history_image(
        service,
        unreadable_path,
        date(2026, 5, 25),
        time(8, 0),
        create_file=False,
    )

    result = service.load_historical_images(
        HistoricalLoadingPlan(
            enabled=True,
            database_path=tmp_path / "registry.sqlite",
            target_ids=("alpha",),
            image_selection=HistoricalImageSelectionConfig(mode="latest_date"),
        )
    )

    assert result.records == []
    assert result.loaded_image_count == 0
    assert result.skipped_image_count == 1
    assert [issue.issue_id for issue in result.issues] == ["historical.geotiff_unreadable"]
    assert result.issues[0].blocking is False


def test_repair_image_path_validates_and_updates_registry_transactionally(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "registry.sqlite"
    service = HistoryService(database_path)
    service.initialize()
    missing_path = tmp_path / "old" / "missing.tif"
    bad_replacement = tmp_path / "bad-replacement.tif"
    valid_replacement = tmp_path / "new" / "valid.tif"
    bad_replacement.write_text("not a geotiff", encoding="utf-8")
    write_geotiff(valid_replacement)
    _record_history_image(
        service,
        missing_path,
        date(2026, 5, 25),
        time(8, 0),
        create_file=False,
    )
    image_asset_id = _single_image_asset_id(database_path)

    with pytest.raises(HistoryRecordError):
        service.repair_image_path(image_asset_id, bad_replacement)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT source_path FROM image_asset").fetchone()[0] == str(
            missing_path
        )

    result = service.repair_image_path(image_asset_id, valid_replacement)

    assert result.image_asset_id == image_asset_id
    assert result.old_path == missing_path
    assert result.new_path == valid_replacement.resolve()
    assert result.issue is None
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT source_path FROM image_asset").fetchone()[0] == str(
            valid_replacement.resolve()
        )


def test_bulk_prefix_replacement_previews_and_requires_confirmation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "registry.sqlite"
    service = HistoryService(database_path)
    service.initialize()
    old_root = tmp_path / "old-root"
    new_root = tmp_path / "new-root"
    _record_history_image(
        service,
        old_root / "a.tif",
        date(2026, 5, 25),
        time(8, 0),
        create_file=False,
    )
    _record_history_image(
        service,
        old_root / "nested" / "b.tif",
        date(2026, 5, 26),
        time(8, 0),
        create_file=False,
    )

    preview = service.preview_path_prefix_replacement(old_root, new_root)

    assert preview.old_prefix == old_root.resolve()
    assert preview.new_prefix == new_root.resolve()
    assert preview.affected_count == 2
    assert {row.old_path.name for row in preview.rows} == {"a.tif", "b.tif"}
    with pytest.raises(HistoryRecordError):
        service.apply_path_prefix_replacement(old_root, new_root, confirmed=False)

    result = service.apply_path_prefix_replacement(old_root, new_root, confirmed=True)

    assert result.updated_count == 2
    with sqlite3.connect(database_path) as connection:
        paths = [
            Path(row[0])
            for row in connection.execute(
                "SELECT source_path FROM image_asset ORDER BY source_path"
            ).fetchall()
        ]
    assert paths == [new_root.resolve() / "a.tif", new_root.resolve() / "nested" / "b.tif"]


def test_history_module_has_no_ui_dependencies() -> None:
    imports = _imported_modules(Path("src/thucthengay/history"))

    assert "PySide6" not in imports
    assert "thucthengay.editor" not in imports


def test_editor_does_not_import_sqlite3_directly() -> None:
    imports = _imported_modules(Path("src/thucthengay/editor"))

    assert "sqlite3" not in imports


def _imported_modules(root: Path) -> set[str]:
    modules: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
    return modules


def _target_config() -> TargetConfig:
    return TargetConfig(
        id="alpha",
        name="Alpha Target",
        alias="A",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export=TargetExportConfig(template_pptx_file="alpha.pptx"),
    )


def _included_composition() -> Composition:
    visible = ImageLayer(
        layer_id="visible",
        source_path="imagery/alpha-visible.tif",
        cache_path="cache/alpha/20260525/alpha-visible.tif",
        order=0,
        capture_date=date(2026, 5, 25),
        capture_time=time(8, 30),
        cloud_percent=12.5,
        metadata_status=MetadataStatus.VALID,
        metadata_source=MetadataSource.FILENAME,
    )
    hidden = visible.model_copy(
        update={
            "layer_id": "hidden",
            "source_path": "imagery/alpha-hidden.tif",
            "visible": False,
            "order": 1,
        }
    )
    return Composition(
        composition_id="alpha__20260525",
        target_id="alpha",
        capture_date=date(2026, 5, 25),
        layers=[visible, hidden],
        view=ViewState(center=[106.7, 10.8], scale=50000),
        reviewed=True,
        ready=True,
        include=True,
        needs_revalidation=False,
        review_order=1,
    )


def _record_history_image(
    service: HistoryService,
    source_name: str | Path,
    capture_date: date,
    capture_time: time,
    *,
    target_id: str = "alpha",
    create_file: bool = True,
) -> None:
    source_path = Path(source_name)
    if not source_path.is_absolute() and service.database_path is not None:
        source_path = Path(service.database_path).parent / source_path
    if create_file:
        write_geotiff(source_path)
    source_text = str(source_path)
    composition = _included_composition().model_copy(
        update={
            "composition_id": f"{target_id}__{capture_date:%Y%m%d}_{source_path.name}",
            "target_id": target_id,
            "capture_date": capture_date,
            "layers": [
                _included_composition().layers[0].model_copy(
                    update={
                        "layer_id": source_path.name,
                        "source_path": source_text,
                        "cache_path": (
                            f"cache/{target_id}/{capture_date:%Y%m%d}/{source_path.name}"
                        ),
                        "capture_date": capture_date,
                        "capture_time": capture_time,
                    }
                )
            ],
        }
    )
    service.record_included_composition(
        composition,
        target=_target_config().model_copy(update={"id": target_id}),
        workspace_path=Path("workspace"),
    )


def _single_image_asset_id(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        return int(connection.execute("SELECT image_asset_id FROM image_asset").fetchone()[0])


def write_geotiff(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(106.0, 11.0, 0.1, 0.1),
    ) as dataset:
        dataset.write(np.ones((1, 2, 2), dtype="uint8"))
