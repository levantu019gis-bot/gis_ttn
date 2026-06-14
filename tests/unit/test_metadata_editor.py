"""Tests for story 4.5: metadata editor and WorkspaceService.update_layer_metadata."""

from __future__ import annotations

import os
from datetime import date, time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QApplication

from thucthengay.editor.widgets.metadata_editor import MetadataEditorDialog
from thucthengay.models import (
    Composition,
    ImageLayer,
    MetadataSource,
    MetadataStatus,
    ViewState,
)
from thucthengay.workspace import WorkspaceError, WorkspaceService


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _layer(
    layer_id: str = "L1",
    *,
    source_path: str | None = None,
    capture_date: date | None = date(2026, 5, 25),
    capture_time: time | None = time(8, 0),
    cloud_percent: float | None = 12.5,
    metadata_status: MetadataStatus = MetadataStatus.VALID,
    metadata_source: MetadataSource = MetadataSource.FILENAME,
) -> ImageLayer:
    return ImageLayer(
        layer_id=layer_id,
        source_path=source_path or f"{layer_id}.tif",
        order=0,
        capture_date=capture_date,
        capture_time=capture_time,
        cloud_percent=cloud_percent,
        metadata_status=metadata_status,
        metadata_source=metadata_source,
    )


def _composition(layers: list[ImageLayer] | None = None) -> Composition:
    return Composition(
        composition_id="tgt__20260525",
        target_id="tgt",
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=50000),
        needs_revalidation=False,
        layers=layers or [_layer()],
    )


# --- WorkspaceService.update_layer_metadata tests ---

class TestUpdateLayerMetadata:
    def _bootstrap_service(self, tmp_path: Path) -> tuple[WorkspaceService, Composition]:
        service = WorkspaceService(tmp_path / "workspace")
        service.initialize(config_path="config.json")
        comp = _composition()
        service.write_composition(comp)
        return service, comp

    def test_persists_all_metadata_fields(self, tmp_path: Path) -> None:
        service, comp = self._bootstrap_service(tmp_path)

        updated = service.update_layer_metadata(
            comp.composition_id,
            "L1",
            capture_date=date(2026, 6, 1),
            capture_time=time(9, 30),
            cloud_percent=42.0,
            metadata_source=MetadataSource.MANUAL,
            metadata_status=MetadataStatus.VALID,
        )

        layer = updated.layers[0]
        assert layer.capture_date == date(2026, 6, 1)
        assert layer.capture_time == time(9, 30)
        assert layer.cloud_percent == 42.0
        assert layer.metadata_source is MetadataSource.MANUAL
        assert layer.metadata_status is MetadataStatus.VALID

    def test_persists_source_path_when_provided(self, tmp_path: Path) -> None:
        service, comp = self._bootstrap_service(tmp_path)

        updated = service.update_layer_metadata(
            comp.composition_id,
            "L1",
            source_path=str(tmp_path / "replacement.tif"),
            cache_path="cache/tgt/20260525/replacement.tif",
            capture_date=date(2026, 5, 25),
            capture_time=time(8, 0),
            cloud_percent=12.5,
            metadata_source=MetadataSource.MANUAL,
            metadata_status=MetadataStatus.VALID,
        )

        assert updated.layers[0].source_path == str(tmp_path / "replacement.tif")
        assert updated.layers[0].cache_path == "cache/tgt/20260525/replacement.tif"

    def test_marks_composition_needs_revalidation(self, tmp_path: Path) -> None:
        service, comp = self._bootstrap_service(tmp_path)
        assert comp.needs_revalidation is False

        updated = service.update_layer_metadata(
            comp.composition_id,
            "L1",
            capture_date=date(2026, 5, 26),
            capture_time=time(10, 0),
            cloud_percent=None,
            metadata_source=MetadataSource.MANUAL,
            metadata_status=MetadataStatus.VALID,
        )

        assert updated.needs_revalidation is True

    def test_unknown_layer_raises_workspace_error(self, tmp_path: Path) -> None:
        service, comp = self._bootstrap_service(tmp_path)

        with pytest.raises(WorkspaceError):
            service.update_layer_metadata(
                comp.composition_id,
                "MISSING-LAYER",
                capture_date=None,
                capture_time=None,
                cloud_percent=None,
                metadata_source=MetadataSource.MANUAL,
                metadata_status=MetadataStatus.NEEDS_MANUAL_CORRECTION,
            )

    def test_time_without_date_raises_workspace_error(self, tmp_path: Path) -> None:
        service, comp = self._bootstrap_service(tmp_path)

        with pytest.raises(WorkspaceError, match="Cần nhập ngày chụp"):
            service.update_layer_metadata(
                comp.composition_id,
                "L1",
                capture_date=None,
                capture_time=time(9, 30),
                cloud_percent=None,
                metadata_source=MetadataSource.MANUAL,
                metadata_status=MetadataStatus.NEEDS_MANUAL_CORRECTION,
            )

    def test_invalid_cloud_percent_is_rejected(self, tmp_path: Path) -> None:
        service, comp = self._bootstrap_service(tmp_path)

        with pytest.raises(ValueError):
            service.update_layer_metadata(
                comp.composition_id,
                "L1",
                capture_date=date(2026, 5, 25),
                capture_time=time(9, 30),
                cloud_percent=101.0,
                metadata_source=MetadataSource.MANUAL,
                metadata_status=MetadataStatus.VALID,
            )

    def test_clears_date_time_and_cloud_when_none(self, tmp_path: Path) -> None:
        service, comp = self._bootstrap_service(tmp_path)
        updated = service.update_layer_metadata(
            comp.composition_id,
            "L1",
            capture_date=None,
            capture_time=None,
            cloud_percent=None,
            metadata_source=MetadataSource.MANUAL,
            metadata_status=MetadataStatus.NEEDS_MANUAL_CORRECTION,
        )

        layer = updated.layers[0]
        assert layer.capture_date is None
        assert layer.capture_time is None
        assert layer.cloud_percent is None
        assert layer.metadata_status is MetadataStatus.NEEDS_MANUAL_CORRECTION


# --- MetadataEditorDialog tests ---

class TestMetadataEditorDialog:
    def test_dialog_populates_from_layer(self) -> None:
        qapp()
        layer = _layer()
        dialog = MetadataEditorDialog(layer)

        assert dialog._capture_date_checkbox.isChecked()
        assert dialog._capture_date_edit.date() == QDate(2026, 5, 25)
        assert dialog._capture_time_checkbox.isChecked()
        assert dialog._capture_time_edit.time() == QTime(8, 0)
        assert dialog._cloud_checkbox.isChecked()
        assert dialog._cloud_spin.value() == 12.5
        assert dialog._source_path_edit.text() == "L1.tif"

    def test_dialog_handles_missing_fields(self) -> None:
        qapp()
        layer = _layer(
            capture_date=None,
            capture_time=None,
            cloud_percent=None,
            metadata_status=MetadataStatus.NEEDS_MANUAL_CORRECTION,
            metadata_source=MetadataSource.UNKNOWN,
        )
        dialog = MetadataEditorDialog(layer)

        assert not dialog._capture_date_checkbox.isChecked()
        assert not dialog._capture_time_checkbox.isChecked()
        assert not dialog._cloud_checkbox.isChecked()
        assert "Cần nhập tay" in dialog._state_label.text()

    def test_save_emits_signal_with_payload(self) -> None:
        qapp()
        layer = _layer()
        dialog = MetadataEditorDialog(layer)

        received: list[tuple[str, dict]] = []
        dialog.metadataSaved.connect(lambda lid, payload: received.append((lid, payload)))

        dialog._on_save()

        assert len(received) == 1
        layer_id, payload = received[0]
        assert layer_id == "L1"
        assert payload["capture_date"] == date(2026, 5, 25)
        assert payload["capture_time"] == time(8, 0)
        assert payload["cloud_percent"] == 12.5
        assert payload["source_path"] == "L1.tif"
        assert payload["metadata_source"] == MetadataSource.MANUAL
        assert payload["metadata_status"] == MetadataStatus.VALID

    def test_save_emits_updated_source_path(self, tmp_path: Path) -> None:
        qapp()
        replacement = tmp_path / "replacement.tif"
        layer = _layer(source_path="missing.tif")
        dialog = MetadataEditorDialog(layer)
        dialog._source_path_edit.setText(str(replacement))

        received: list[tuple[str, dict]] = []
        dialog.metadataSaved.connect(lambda lid, payload: received.append((lid, payload)))

        dialog._on_save()

        assert received[0][1]["source_path"] == str(replacement)

    def test_save_with_time_only_shows_validation_and_does_not_emit(self) -> None:
        qapp()
        layer = _layer(capture_date=None, capture_time=time(8, 0))
        dialog = MetadataEditorDialog(layer)
        # Manually configure: keep date unchecked, time checked
        dialog._capture_date_checkbox.setChecked(False)
        dialog._capture_time_checkbox.setChecked(True)

        received: list[tuple[str, dict]] = []
        dialog.metadataSaved.connect(lambda lid, payload: received.append((lid, payload)))

        dialog._on_save()

        assert received == []
        assert "Cần nhập ngày" in dialog.validation_text

    def test_save_with_only_date_shows_validation_and_does_not_emit(self) -> None:
        qapp()
        layer = _layer(capture_date=date(2026, 5, 25), capture_time=None)
        dialog = MetadataEditorDialog(layer)
        dialog._capture_date_checkbox.setChecked(True)
        dialog._capture_time_checkbox.setChecked(False)

        received: list[tuple[str, dict]] = []
        dialog.metadataSaved.connect(lambda lid, payload: received.append((lid, payload)))

        dialog._on_save()

        assert received == []
        assert "Cần nhập giờ" in dialog.validation_text

    def test_save_with_no_fields_shows_validation_and_does_not_emit(self) -> None:
        qapp()
        layer = _layer(capture_date=None, capture_time=None, cloud_percent=None)
        dialog = MetadataEditorDialog(layer)
        dialog._capture_date_checkbox.setChecked(False)
        dialog._capture_time_checkbox.setChecked(False)
        dialog._cloud_checkbox.setChecked(False)

        received: list[tuple[str, dict]] = []
        dialog.metadataSaved.connect(lambda lid, payload: received.append((lid, payload)))

        dialog._on_save()

        assert received == []
        assert "Cần nhập ngày" in dialog.validation_text

    def test_manual_source_state_pill_shows_manual_label(self) -> None:
        qapp()
        layer = _layer(metadata_source=MetadataSource.MANUAL)
        dialog = MetadataEditorDialog(layer)
        assert "Đã sửa thủ công" in dialog._state_label.text()

    def test_valid_metadata_state_pill_shows_parsed_label(self) -> None:
        qapp()
        layer = _layer(
            metadata_source=MetadataSource.FILENAME,
            metadata_status=MetadataStatus.VALID,
        )
        dialog = MetadataEditorDialog(layer)
        assert "Đã parse" in dialog._state_label.text()
