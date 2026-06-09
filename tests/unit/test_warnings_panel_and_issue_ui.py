"""Tests for story 4.4: issue surfacing in tree, layer, and warnings panel."""

from __future__ import annotations

import os
from datetime import date, time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from thucthengay.editor.models.composition_tree_model import (
    CompositionTreeModel,
    CompositionTreeRole,
)
from thucthengay.editor.models.layer_stack_model import LayerStackColumn, LayerStackModel
from thucthengay.editor.widgets.warnings_panel import WarningsPanelWidget
from thucthengay.models import (
    Composition,
    ImageLayer,
    ImageLayerSourceKind,
    Issue,
    IssueScope,
    IssueSeverity,
    MetadataSource,
    MetadataStatus,
    ValidationSummary,
    ViewState,
)


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_composition(
    composition_id: str,
    target_id: str,
    *,
    errors: int = 0,
    warnings: int = 0,
    info: int = 0,
    layers: list[ImageLayer] | None = None,
) -> Composition:
    return Composition(
        composition_id=composition_id,
        target_id=target_id,
        capture_date=date(2026, 5, 25),
        view=ViewState(center=[106.7, 10.8], scale=50000),
        needs_revalidation=False,
        validation_summary=ValidationSummary(
            error_count=errors,
            warning_count=warnings,
            info_count=info,
        ),
        layers=layers or [
            ImageLayer(
                layer_id=f"{composition_id}-L1",
                source_path=f"{composition_id}.tif",
                order=0,
                capture_date=date(2026, 5, 25),
                capture_time=time(8, 0),
                metadata_status=MetadataStatus.VALID,
                metadata_source=MetadataSource.FILENAME,
            )
        ],
    )


def _make_issue(
    issue_id: str,
    severity: IssueSeverity,
    *,
    message: str = "Test message",
    remediation: str | None = "Fix it",
    scope: IssueScope = IssueScope.COMPOSITION,
    layer_id: str | None = None,
    composition_id: str | None = None,
    target_id: str | None = None,
    blocking: bool = False,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=severity,
        scope=scope,
        message=message,
        remediation=remediation,
        layer_id=layer_id,
        composition_id=composition_id,
        target_id=target_id,
        blocking=blocking,
    )


# --- Tree model tests (AC 1) ---

class TestCompositionTreeIssueIndicators:
    def test_composition_with_errors_returns_decoration_icon(self) -> None:
        qapp()
        model = CompositionTreeModel()
        comp = _make_composition("tgt__20260525", "tgt", errors=2)
        model.set_compositions([comp])

        # Find the composition index under the target
        target_index = model.index(0, 0)
        comp_index = model.index(0, 0, target_index)

        icon = model.data(comp_index, int(Qt.ItemDataRole.DecorationRole))
        assert icon is not None
        assert not icon.isNull()

    def test_composition_issue_count_role_matches_summary(self) -> None:
        qapp()
        model = CompositionTreeModel()
        comp = _make_composition("tgt__20260525", "tgt", errors=1, warnings=2)
        model.set_compositions([comp])

        target_index = model.index(0, 0)
        comp_index = model.index(0, 0, target_index)

        issue_count = model.data(comp_index, CompositionTreeRole.ISSUE_COUNT)
        assert issue_count == 3  # 1 error + 2 warnings

    def test_target_severity_text_reflects_worst_child(self) -> None:
        qapp()
        model = CompositionTreeModel()
        comp_ok = _make_composition("tgt__20260524", "tgt")
        comp_err = _make_composition("tgt__20260525", "tgt", errors=1)
        model.set_compositions([comp_ok, comp_err])

        target_index = model.index(0, 0)
        severity = model.data(target_index, CompositionTreeRole.SEVERITY_TEXT)
        assert severity == "ERROR"

    def test_composition_tooltip_contains_issue_counts(self) -> None:
        qapp()
        model = CompositionTreeModel()
        comp = _make_composition("tgt__20260525", "tgt", warnings=1)
        model.set_compositions([comp])

        target_index = model.index(0, 0)
        comp_index = model.index(0, 0, target_index)

        tooltip = model.data(comp_index, int(Qt.ItemDataRole.ToolTipRole))
        assert tooltip is not None
        assert "Warnings: 1" in tooltip

    def test_clean_composition_has_ok_severity(self) -> None:
        qapp()
        model = CompositionTreeModel()
        comp = _make_composition("tgt__20260525", "tgt")
        model.set_compositions([comp])

        target_index = model.index(0, 0)
        comp_index = model.index(0, 0, target_index)

        severity = model.data(comp_index, CompositionTreeRole.SEVERITY_TEXT)
        assert severity == "OK"


# --- Layer stack issue indicator tests (AC 2) ---

class TestLayerStackIssueColumn:
    def _make_layer(self, layer_id: str) -> ImageLayer:
        return ImageLayer(
            layer_id=layer_id,
            source_path=f"{layer_id}.tif",
            order=0,
            capture_date=date(2026, 5, 25),
            capture_time=time(8, 0),
            metadata_status=MetadataStatus.VALID,
            metadata_source=MetadataSource.FILENAME,
        )

    def test_layer_with_error_issue_shows_error_text(self) -> None:
        qapp()
        model = LayerStackModel()
        comp = _make_composition("tgt__20260525", "tgt")
        model.set_composition(comp)

        issue = _make_issue(
            "err-1",
            IssueSeverity.ERROR,
            layer_id=comp.layers[0].layer_id,
        )
        model.set_issues([issue])

        idx = model.index(0, int(LayerStackColumn.ISSUE))
        text = model.data(idx, int(Qt.ItemDataRole.DisplayRole))
        assert text == "✗ ERROR"

    def test_layer_with_warning_shows_warn_text(self) -> None:
        qapp()
        model = LayerStackModel()
        comp = _make_composition("tgt__20260525", "tgt")
        model.set_composition(comp)

        issue = _make_issue(
            "warn-1",
            IssueSeverity.WARNING,
            layer_id=comp.layers[0].layer_id,
        )
        model.set_issues([issue])

        idx = model.index(0, int(LayerStackColumn.ISSUE))
        text = model.data(idx, int(Qt.ItemDataRole.DisplayRole))
        assert text == "⚠ WARN"

    def test_layer_without_issue_shows_empty_text(self) -> None:
        qapp()
        model = LayerStackModel()
        comp = _make_composition("tgt__20260525", "tgt")
        model.set_composition(comp)
        model.set_issues([])

        idx = model.index(0, int(LayerStackColumn.ISSUE))
        text = model.data(idx, int(Qt.ItemDataRole.DisplayRole))
        assert text == ""

    def test_issue_tooltip_contains_message_and_remediation(self) -> None:
        qapp()
        model = LayerStackModel()
        comp = _make_composition("tgt__20260525", "tgt")
        model.set_composition(comp)

        issue = _make_issue(
            "err-1",
            IssueSeverity.ERROR,
            message="Không có layer bật",
            remediation="Bật ít nhất 1 layer",
            layer_id=comp.layers[0].layer_id,
        )
        model.set_issues([issue])

        idx = model.index(0, int(LayerStackColumn.ISSUE))
        tooltip = model.data(idx, int(Qt.ItemDataRole.ToolTipRole))
        assert tooltip is not None
        assert "Không có layer bật" in tooltip
        assert "Bật ít nhất 1 layer" in tooltip

    def test_set_composition_clears_issues(self) -> None:
        qapp()
        model = LayerStackModel()
        comp = _make_composition("tgt__20260525", "tgt")
        model.set_composition(comp)

        issue = _make_issue("err-1", IssueSeverity.ERROR, layer_id=comp.layers[0].layer_id)
        model.set_issues([issue])

        # Re-setting composition should clear issues
        model.set_composition(comp)
        idx = model.index(0, int(LayerStackColumn.ISSUE))
        text = model.data(idx, int(Qt.ItemDataRole.DisplayRole))
        assert text == ""

    def test_error_overrides_warning_for_same_layer(self) -> None:
        qapp()
        model = LayerStackModel()
        comp = _make_composition("tgt__20260525", "tgt")
        model.set_composition(comp)

        layer_id = comp.layers[0].layer_id
        issues = [
            _make_issue("warn-1", IssueSeverity.WARNING, layer_id=layer_id),
            _make_issue("err-1", IssueSeverity.ERROR, layer_id=layer_id),
        ]
        model.set_issues(issues)

        idx = model.index(0, int(LayerStackColumn.ISSUE))
        text = model.data(idx, int(Qt.ItemDataRole.DisplayRole))
        assert text == "✗ ERROR"

    def test_issue_column_header_is_loi(self) -> None:
        qapp()
        model = LayerStackModel()
        header = model.headerData(
            int(LayerStackColumn.ISSUE),
            Qt.Orientation.Horizontal,
            int(Qt.ItemDataRole.DisplayRole),
        )
        assert header == "Lỗi"

    def test_non_layer_issue_does_not_appear_in_layer_column(self) -> None:
        qapp()
        model = LayerStackModel()
        comp = _make_composition("tgt__20260525", "tgt")
        model.set_composition(comp)

        # Issue with no layer_id — should not affect any layer row
        issue = _make_issue("comp-err", IssueSeverity.ERROR, layer_id=None)
        model.set_issues([issue])

        idx = model.index(0, int(LayerStackColumn.ISSUE))
        text = model.data(idx, int(Qt.ItemDataRole.DisplayRole))
        assert text == ""

    def test_layer_stack_filename_shows_current_or_historical_source_text(self) -> None:
        qapp()
        model = LayerStackModel()
        current = self._make_layer("current")
        historical = self._make_layer("historical").model_copy(
            update={"source_kind": ImageLayerSourceKind.HISTORICAL, "order": 1}
        )
        comp = _make_composition("tgt__20260525", "tgt", layers=[current, historical])
        model.set_composition(comp)

        current_text = model.data(
            model.index(0, int(LayerStackColumn.FILENAME)),
            int(Qt.ItemDataRole.DisplayRole),
        )
        historical_text = model.data(
            model.index(1, int(LayerStackColumn.FILENAME)),
            int(Qt.ItemDataRole.DisplayRole),
        )

        assert "Current" in current_text
        assert "Historical" in historical_text


# --- WarningsPanelWidget tests (AC 3) ---

class TestWarningsPanelWidget:
    def test_set_issues_populates_list(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        issues = [
            _make_issue("i1", IssueSeverity.ERROR, message="Lỗi A"),
            _make_issue("i2", IssueSeverity.WARNING, message="Warning B"),
        ]
        panel.set_issues(issues, composition_id="tgt__20260525", target_id="tgt")
        assert panel._list.count() == 2

    def test_item_text_contains_severity_and_message(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        issue = _make_issue("i1", IssueSeverity.ERROR, message="Không có layer bật")
        panel.set_issues([issue], composition_id="c1", target_id="tgt")
        item_text = panel._list.item(0).text()
        assert "ERROR" in item_text
        assert "Không có layer bật" in item_text

    def test_item_text_contains_remediation(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        issue = _make_issue(
            "i1",
            IssueSeverity.WARNING,
            message="Warning A",
            remediation="Cách sửa: làm X",
        )
        panel.set_issues([issue], composition_id="c1", target_id="tgt")
        item_text = panel._list.item(0).text()
        assert "Cách sửa: làm X" in item_text
        assert "điều hướng" in item_text

    def test_empty_issues_shows_placeholder_row(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        panel.set_issues([], composition_id="c1", target_id="tgt")
        assert panel._list.count() == 1
        assert "Không có vấn đề" in panel._list.item(0).text()

    def test_jump_signal_emitted_on_double_click(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        issue = _make_issue(
            "i1",
            IssueSeverity.ERROR,
            composition_id="tgt__20260525",
            target_id="tgt",
            layer_id="L1",
        )
        panel.set_issues([issue], composition_id="tgt__20260525", target_id="tgt")

        received: list[tuple[str, str, str]] = []
        panel.jumpRequested.connect(lambda t, c, lid: received.append((t, c, lid)))

        panel._on_item_double_clicked(panel._list.item(0))
        assert len(received) == 1
        assert received[0] == ("tgt", "tgt__20260525", "L1")

    def test_item_icon_set_for_error(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        issue = _make_issue("i1", IssueSeverity.ERROR, message="Err")
        panel.set_issues([issue], composition_id="c1", target_id="tgt")
        icon = panel._list.item(0).icon()
        assert icon is not None

    def test_set_issues_clears_previous_items(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        panel.set_issues(
            [_make_issue("i1", IssueSeverity.ERROR)],
            composition_id="c1",
            target_id="tgt",
        )
        panel.set_issues([], composition_id="c1", target_id="tgt")
        assert panel._list.count() == 1  # just the placeholder
        assert "Không có vấn đề" in panel._list.item(0).text()

    def test_jump_data_uses_issue_ids_when_present(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        issue = _make_issue(
            "i1",
            IssueSeverity.WARNING,
            composition_id="specific__comp",
            target_id="specific_tgt",
        )
        panel.set_issues([issue], composition_id="fallback_comp", target_id="fallback_tgt")
        data = panel._list.item(0).data(1000)
        target_id, comp_id, _ = data
        assert target_id == "specific_tgt"
        assert comp_id == "specific__comp"

    def test_jump_data_falls_back_to_caller_ids_when_issue_has_none(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        issue = _make_issue("i1", IssueSeverity.WARNING, composition_id=None, target_id=None)
        panel.set_issues([issue], composition_id="fallback_comp", target_id="fallback_tgt")
        data = panel._list.item(0).data(1000)
        target_id, comp_id, _ = data
        assert target_id == "fallback_tgt"
        assert comp_id == "fallback_comp"

    def test_historical_path_issue_mentions_repair_availability(self) -> None:
        qapp()
        panel = WarningsPanelWidget()
        issue = _make_issue(
            "historical.path_missing",
            IssueSeverity.WARNING,
            scope=IssueScope.LAYER,
            target_id="target_001",
            composition_id="target_001__20260525",
            layer_id="42",
            message="Khong tim thay anh lich su",
        )

        panel.set_issues([issue])

        item_text = panel._list.item(0).text()
        data = panel._list.item(0).data(1000)
        assert "target:target_001" in item_text
        assert "comp:target_001__20260525" in item_text
        assert "layer:42" in item_text
        assert "sua duong dan" in item_text.lower()
        assert data == ("target_001", "target_001__20260525", "42")
