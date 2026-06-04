"""Config manager mode."""

from __future__ import annotations

import copy
import json
from enum import IntEnum
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from thucthengay.config import ConfigEditorError, ConfigEditorService
from thucthengay.models import Issue, IssueSeverity

_INVALID_INDEX = QModelIndex()
_PLACEHOLDER_VISIBLE_ROWS = 5


class TargetTableColumn(IntEnum):
    """Columns shown in the target config table."""

    ENABLED = 0
    ORDER = 1
    TARGET_ID = 2
    NAME = 3
    ALIAS = 4
    SCALE = 5
    GRID = 6
    STATUS = 7


class TargetTableRole(IntEnum):
    """Custom roles for target selection."""

    TARGET_ID = int(Qt.ItemDataRole.UserRole) + 200


class TargetTableModel(QAbstractTableModel):
    """Read-only target projection used by the Config tab."""

    HEADERS = {
        TargetTableColumn.ENABLED: "Bật",
        TargetTableColumn.ORDER: "Order",
        TargetTableColumn.TARGET_ID: "ID",
        TargetTableColumn.NAME: "Tên hiển thị",
        TargetTableColumn.ALIAS: "Alias",
        TargetTableColumn.SCALE: "Scale",
        TargetTableColumn.GRID: "Grid",
        TargetTableColumn.STATUS: "Status",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._issues_by_target: dict[str, list[Issue]] = {}

    def set_rows(self, rows: list[dict[str, Any]], issues: list[Issue]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        grouped: dict[str, list[Issue]] = {}
        for issue in issues:
            if issue.target_id:
                grouped.setdefault(issue.target_id, []).append(issue)
        self._issues_by_target = grouped
        self.endResetModel()

    def row_at(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def row_for_target_id(self, target_id: str) -> int:
        for row, target in enumerate(self._rows):
            if target.get("id") == target_id:
                return row
        return -1

    def rowCount(self, parent: QModelIndex = _INVALID_INDEX) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = _INVALID_INDEX) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(TargetTableColumn)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if orientation != Qt.Orientation.Horizontal or role != int(Qt.ItemDataRole.DisplayRole):
            return None
        return self.HEADERS.get(TargetTableColumn(section), "")

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> object:
        if not index.isValid():
            return None
        target = self.row_at(index.row())
        if target is None:
            return None

        target_id = str(target.get("id", ""))
        issues = self._issues_by_target.get(target_id, [])
        if role == TargetTableRole.TARGET_ID:
            return target_id
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return _target_tooltip(target, issues)
        if role == int(Qt.ItemDataRole.BackgroundRole) and issues:
            if any(issue.severity == IssueSeverity.ERROR for issue in issues):
                return QColor("#FFF1F2")
            return QColor("#FFFBEB")
        if (
            role == int(Qt.ItemDataRole.CheckStateRole)
            and index.column() == TargetTableColumn.ENABLED
        ):
            return Qt.CheckState.Checked if target.get("enabled", True) else Qt.CheckState.Unchecked
        if role != int(Qt.ItemDataRole.DisplayRole):
            return None

        column = TargetTableColumn(index.column())
        if column == TargetTableColumn.ENABLED:
            return ""
        if column == TargetTableColumn.ORDER:
            return str(target.get("sort_order", ""))
        if column == TargetTableColumn.TARGET_ID:
            return target_id
        if column == TargetTableColumn.NAME:
            return str(target.get("name", ""))
        if column == TargetTableColumn.ALIAS:
            return str(target.get("alias", "") or "")
        if column == TargetTableColumn.SCALE:
            scale = target.get("scale")
            return f"1:{scale:,}" if isinstance(scale, int) else str(scale or "")
        if column == TargetTableColumn.GRID:
            return _grid_label(target)
        if column == TargetTableColumn.STATUS:
            if not issues:
                return "OK"
            error_count = sum(1 for issue in issues if issue.severity == IssueSeverity.ERROR)
            if error_count:
                return f"{error_count} lỗi"
            return f"{len(issues)} cảnh báo"
        return None


class IssueTableColumn(IntEnum):
    """Columns shown in the validation issue table."""

    SEVERITY = 0
    ISSUE_ID = 1
    MESSAGE = 2
    CONTEXT = 3


class IssueTableRole(IntEnum):
    """Custom roles for issue navigation."""

    TARGET_ID = int(Qt.ItemDataRole.UserRole) + 220


class IssueTableModel(QAbstractTableModel):
    """Read-only issue projection for config validation."""

    HEADERS = {
        IssueTableColumn.SEVERITY: "Severity",
        IssueTableColumn.ISSUE_ID: "Issue",
        IssueTableColumn.MESSAGE: "Message",
        IssueTableColumn.CONTEXT: "Context / remediation",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._issues: list[Issue] = []

    def set_issues(self, issues: list[Issue]) -> None:
        self.beginResetModel()
        self._issues = list(issues)
        self.endResetModel()

    def issue_at(self, row: int) -> Issue | None:
        if row < 0 or row >= len(self._issues):
            return None
        return self._issues[row]

    def rowCount(self, parent: QModelIndex = _INVALID_INDEX) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._issues)

    def columnCount(self, parent: QModelIndex = _INVALID_INDEX) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(IssueTableColumn)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if orientation != Qt.Orientation.Horizontal or role != int(Qt.ItemDataRole.DisplayRole):
            return None
        return self.HEADERS.get(IssueTableColumn(section), "")

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> object:
        if not index.isValid():
            return None
        issue = self.issue_at(index.row())
        if issue is None:
            return None
        if role == IssueTableRole.TARGET_ID:
            return issue.target_id or ""
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return f"{issue.message}\n{issue.remediation or ''}".strip()
        if role == int(Qt.ItemDataRole.BackgroundRole):
            if issue.severity == IssueSeverity.ERROR:
                return QColor("#FFF1F2")
            if issue.severity == IssueSeverity.WARNING:
                return QColor("#FFFBEB")
        if role != int(Qt.ItemDataRole.DisplayRole):
            return None

        column = IssueTableColumn(index.column())
        if column == IssueTableColumn.SEVERITY:
            return issue.severity.value.upper()
        if column == IssueTableColumn.ISSUE_ID:
            return issue.issue_id
        if column == IssueTableColumn.MESSAGE:
            return issue.message
        if column == IssueTableColumn.CONTEXT:
            parts = []
            if issue.target_id:
                parts.append(f"target={issue.target_id}")
            if issue.remediation:
                parts.append(issue.remediation)
            return " | ".join(parts)
        return None


class ConfigMode(QWidget):
    """Config management screen."""

    configSaved = Signal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        service: ConfigEditorService | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("configMode")
        self.setMinimumSize(1100, 620)
        self._service = service or ConfigEditorService()
        self._selected_group_key: str | None = None
        self._selected_target_id: str | None = None
        self._loading_form = False

        self.new_button = QPushButton("Tạo mới")
        self.open_button = QPushButton("Mở config")
        self.reload_button = QPushButton("Tải lại")
        self.backup_button = QPushButton("Backup")
        self.save_button = QPushButton("Lưu")
        self.save_as_button = QPushButton("Lưu thành")
        self.validate_button = QPushButton("Validate")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm target, group, template, geometry")
        self.path_label = QLabel("Chưa có file config.")
        self.path_label.setObjectName("configPathLabel")
        self.path_label.setWordWrap(True)
        self.dirty_label = QLabel("")
        self.valid_label = QLabel("")
        self.downstream_label = QLabel("")
        self.downstream_label.setWordWrap(True)

        self.stat_labels = {
            "targets": QLabel("0"),
            "enabled": QLabel("0"),
            "groups": QLabel("0"),
            "templates": QLabel("0"),
            "geometry": QLabel("0"),
            "issues": QLabel("0"),
        }

        self.group_filter = QComboBox()
        self.group_filter.addItems(["Tất cả target", "Enabled only", "Có cảnh báo"])
        self.group_list = QListWidget()
        self.group_list.setObjectName("configGroupList")
        self.add_group_button = QPushButton("+")
        self.add_group_button.setToolTip("Thêm group mới")

        self.work_tabs = QTabWidget()
        self.target_model = TargetTableModel(self)
        self.target_table = QTableView()
        self.target_table.setObjectName("configTargetTable")
        self.target_table.setModel(self.target_model)
        self.target_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.target_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.target_table.setAlternatingRowColors(True)
        self.target_table.verticalHeader().setVisible(False)
        self.add_target_button = QPushButton("Thêm target")

        self.defaults_fields: dict[str, QLineEdit] = {}
        self.default_label_font_browse_button = QPushButton("Browse")
        self.default_label_font_browse_button.setToolTip("Chọn font label và copy vào fonts")
        self.pattern_table = QTableWidget(0, 3)
        self.pattern_table.setHorizontalHeaderLabels(["Tên", "Pattern", "Separator"])
        self.add_pattern_button = QPushButton("Thêm pattern")
        self.apply_patterns_button = QPushButton("Apply patterns")
        self.pattern_test_input = QLineEdit("20260526_203927_sample_12.tif")
        self.pattern_test_button = QPushButton("Kiểm tra pattern")
        self.pattern_result_label = QLabel("UTC filename + 7 giờ")
        self.pattern_result_label.setWordWrap(True)
        self.raw_json = QTextEdit()
        self.raw_json.setReadOnly(True)

        self.inspector_title = QLabel("Chưa chọn target")
        self.inspector_title.setObjectName("configInspectorTitle")
        self.delete_target_button = QPushButton("Xóa target")
        self.delete_target_button.setObjectName("configDeleteTarget")
        self.reset_button = QPushButton("Reset")
        self.apply_button = QPushButton("Apply")
        self.enabled_check = QCheckBox("Enabled")
        self.target_fields: dict[str, QLineEdit] = {}
        self.template_browse_button = QPushButton("Browse")
        self.template_browse_button.setToolTip("Chọn template PPTX và copy vào data/templates")
        self.placeholder_table = QTableWidget(0, 2)
        self.placeholder_table.setHorizontalHeaderLabels(["field", "value"])
        self.placeholder_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.placeholder_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.add_placeholder_button = QPushButton("Thêm field")
        self.delete_placeholder_button = QPushButton("Xóa field")
        self.import_geojson_button = QPushButton("Import GeoJSON")
        self.export_geojson_button = QPushButton("Export GeoJSON")
        self.geometry_text = QTextEdit()
        self.geometry_text.setObjectName("configGeometryText")
        self.geometry_text.setReadOnly(True)
        self.geometry_text.setMinimumHeight(150)
        self.geometry_text.setPlaceholderText("Target chưa có metadata.geojson_geometry.")

        self.issue_model = IssueTableModel(self)
        self.issue_table = QTableView()
        self.issue_table.setObjectName("configIssueTable")
        self.issue_table.setModel(self.issue_model)
        self.issue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.issue_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.issue_table.verticalHeader().setVisible(False)

        self._build_layout()
        self._connect_signals()
        self._refresh_all()

    def load_config(self, path: str | Path) -> None:
        """Load a config file into the Config tab."""
        try:
            self._service.load(path)
        except ConfigEditorError as error:
            self._show_error("Không mở được config", str(error))
            return
        self._selected_group_key = None
        self._selected_target_id = None
        self._refresh_all()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(self._toolbar_layout())
        layout.addWidget(self.path_label)
        layout.addLayout(self._stats_layout())

        body_splitter = QSplitter(Qt.Orientation.Horizontal)
        body_splitter.addWidget(self._build_group_sidebar())
        body_splitter.addWidget(self._build_workarea())
        body_splitter.addWidget(self._build_inspector())
        body_splitter.setStretchFactor(0, 0)
        body_splitter.setStretchFactor(1, 1)
        body_splitter.setStretchFactor(2, 0)
        body_splitter.setSizes([240, 660, 360])
        layout.addWidget(body_splitter, 1)
        layout.addWidget(self._build_issues_panel())
        layout.addWidget(self.downstream_label)

    def _toolbar_layout(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        for button in (
            self.new_button,
            self.open_button,
            self.reload_button,
            self.backup_button,
            self.save_button,
            self.save_as_button,
        ):
            toolbar.addWidget(button)
        toolbar.addWidget(self.search_input, 1)
        toolbar.addWidget(self.dirty_label)
        toolbar.addWidget(self.valid_label)
        toolbar.addWidget(self.validate_button)
        return toolbar

    def _stats_layout(self) -> QGridLayout:
        stats = QGridLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        labels = [
            ("Targets", "targets"),
            ("Enabled", "enabled"),
            ("Groups", "groups"),
            ("Template PPTX", "templates"),
            ("Geometry", "geometry"),
            ("Issues", "issues"),
        ]
        for column, (title, key) in enumerate(labels):
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(10, 6, 10, 6)
            label = QLabel(title)
            label.setObjectName(f"configStat{key.title()}Title")
            value = self.stat_labels[key]
            value.setObjectName(f"configStat{key.title()}Value")
            frame_layout.addWidget(label)
            frame_layout.addWidget(value)
            stats.addWidget(frame, 0, column)
        return stats

    def _build_group_sidebar(self) -> QWidget:
        sidebar = QWidget()
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        title = QLabel("Groups")
        title.setStyleSheet("font-weight: 700;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.add_group_button)
        layout.addLayout(header)
        layout.addWidget(self.group_filter)
        layout.addWidget(self.group_list, 1)
        return sidebar

    def _build_workarea(self) -> QWidget:
        workarea = QWidget()
        layout = QVBoxLayout(workarea)
        layout.setContentsMargins(0, 0, 0, 0)
        self.work_tabs.addTab(self._build_targets_tab(), "Targets")
        self.work_tabs.addTab(self._build_defaults_tab(), "Defaults")
        self.work_tabs.addTab(self._build_patterns_tab(), "Filename Patterns")
        self.work_tabs.addTab(self._build_raw_json_tab(), "Raw JSON")
        layout.addWidget(self.work_tabs)
        return workarea

    def _build_targets_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        actions = QHBoxLayout()
        actions.addWidget(self.add_target_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(self.target_table, 1)
        return tab

    def _build_defaults_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 8, 4, 8)
        policy_label = QLabel(
            "Defaults là cấu hình dùng chung. Mỗi target vẫn giữ grid.interval riêng; "
            "target grid.style chỉ override các field style khác default."
        )
        policy_label.setObjectName("configDefaultsPolicy")
        policy_label.setWordWrap(True)
        layout.addWidget(policy_label)
        field_specs = [
            ("Default Grid", "grid.label_format", "label_format"),
            ("Default Grid", "grid.style.supported_label_formats", "supported_formats"),
            ("Default Grid", "grid.style.default_label_font", "default_label_font"),
            ("Default Grid", "grid.style.frame_color", "frame_color"),
            ("Default Grid", "grid.style.label_color", "label_color"),
            ("Default Grid", "grid.style.label_font_size", "label_font_size"),
            ("Default Grid", "grid.style.tick_length_px", "tick_length_px"),
            ("Default Grid", "grid.style.reference_label_font_size", "reference_label_font_size"),
            ("Frame Reference", "grid.style.reference_width", "reference_width"),
            ("Frame Reference", "grid.style.reference_height", "reference_height"),
            ("Frame Reference", "grid.style.reference_outer_frame", "reference_outer_frame"),
            ("Frame Reference", "grid.style.reference_frame_gap", "reference_frame_gap"),
            ("Advanced Grid Style", "grid.style.max_frame_ticks_per_axis", "max_ticks_per_axis"),
            ("Advanced Grid Style", "grid.style.epsilon", "epsilon"),
            ("Advanced Grid Style", "grid.style.surround_tick_length", "surround_tick_length"),
            (
                "Advanced Grid Style",
                "grid.style.surround_outer_stroke_width",
                "surround_outer_stroke_width",
            ),
            (
                "Advanced Grid Style",
                "grid.style.surround_inner_stroke_width",
                "surround_inner_stroke_width",
            ),
            (
                "Advanced Grid Style",
                "grid.style.surround_tick_stroke_width",
                "surround_tick_stroke_width",
            ),
            ("Export Defaults", "export.date_format", "date_format"),
            ("Export Defaults", "export.time_format", "time_format"),
            ("Export Defaults", "export.map_background_color", "map_background_color"),
        ]
        grouped: dict[str, list[tuple[str, str]]] = {}
        for group, key, label in field_specs:
            grouped.setdefault(group, []).append((key, label))
        for group, fields in grouped.items():
            box = QGroupBox(group)
            form = QFormLayout(box)
            for key, label in fields:
                field = QLineEdit()
                field.setObjectName(f"configDefault_{key.replace('.', '_')}")
                self.defaults_fields[key] = field
                if key == "grid.style.default_label_font":
                    field.setReadOnly(True)
                    picker = QWidget()
                    picker_layout = QHBoxLayout(picker)
                    picker_layout.setContentsMargins(0, 0, 0, 0)
                    picker_layout.addWidget(field, 1)
                    picker_layout.addWidget(self.default_label_font_browse_button)
                    form.addRow(label, picker)
                else:
                    form.addRow(label, field)
            layout.addWidget(box)
        apply_button = QPushButton("Apply defaults")
        apply_button.clicked.connect(self._apply_defaults)
        layout.addWidget(apply_button)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _build_patterns_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        actions = QHBoxLayout()
        actions.addWidget(self.add_pattern_button)
        actions.addWidget(self.apply_patterns_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(self.pattern_table, 1)
        test_row = QHBoxLayout()
        test_row.addWidget(QLabel("Test Filename"))
        test_row.addWidget(self.pattern_test_input, 1)
        test_row.addWidget(self.pattern_test_button)
        layout.addLayout(test_row)
        layout.addWidget(self.pattern_result_label)
        return tab

    def _build_raw_json_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(self.raw_json)
        return tab

    def _build_inspector(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.addWidget(self.inspector_title)
        actions = QHBoxLayout()
        actions.addWidget(self.delete_target_button)
        actions.addStretch(1)
        actions.addWidget(self.reset_button)
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)
        layout.addWidget(self._build_info_section())
        layout.addWidget(self._build_grid_section())
        layout.addWidget(self._build_export_section())
        layout.addWidget(self._build_placeholder_section())
        layout.addWidget(self._build_geometry_section())
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _build_info_section(self) -> QGroupBox:
        box = QGroupBox("Thông tin")
        form = QFormLayout(box)
        specs = [
            ("id", "id"),
            ("group.key", "group.key"),
            ("group.title", "group.title"),
            ("sort_order", "sort_order"),
            ("name", "name"),
            ("alias", "alias"),
            ("lon", "coordinate.0"),
            ("lat", "coordinate.1"),
            ("scale", "scale"),
        ]
        form.addRow(self.enabled_check)
        for label, key in specs:
            field = QLineEdit()
            field.setObjectName(f"configTarget_{key.replace('.', '_')}")
            self.target_fields[key] = field
            form.addRow(label, field)
        return box

    def _build_grid_section(self) -> QGroupBox:
        box = QGroupBox("Grid")
        form = QFormLayout(box)
        for label, key in (
            ("degrees", "grid.interval.degrees"),
            ("minutes", "grid.interval.minutes"),
            ("seconds", "grid.interval.seconds"),
        ):
            field = QLineEdit()
            self.target_fields[key] = field
            form.addRow(label, field)
        return box

    def _build_export_section(self) -> QGroupBox:
        box = QGroupBox("Export")
        form = QFormLayout(box)
        template_field = QLineEdit()
        template_field.setObjectName("configTarget_export_template_pptx_file")
        template_field.setReadOnly(True)
        template_field.setToolTip("Đường dẫn template được quản lý bằng nút Browse.")
        self.target_fields["export.template_pptx_file"] = template_field
        template_row = QWidget()
        template_layout = QHBoxLayout(template_row)
        template_layout.setContentsMargins(0, 0, 0, 0)
        template_layout.setSpacing(6)
        template_layout.addWidget(template_field, 1)
        template_layout.addWidget(self.template_browse_button)
        form.addRow("template", template_row)
        for label, key in (
            ("TXT", "export.template_txt_value"),
        ):
            field = QLineEdit()
            self.target_fields[key] = field
            form.addRow(label, field)
        return box

    def _build_placeholder_section(self) -> QGroupBox:
        box = QGroupBox("Placeholders")
        layout = QVBoxLayout(box)
        actions = QHBoxLayout()
        actions.addWidget(self.add_placeholder_button)
        actions.addWidget(self.delete_placeholder_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.placeholder_table.verticalHeader().setVisible(False)
        self.placeholder_table.setMinimumHeight(
            _table_height_for_visible_rows(self.placeholder_table, _PLACEHOLDER_VISIBLE_ROWS)
        )
        layout.addWidget(self.placeholder_table)
        return box

    def _build_geometry_section(self) -> QGroupBox:
        box = QGroupBox("Geometry")
        layout = QVBoxLayout(box)
        actions = QHBoxLayout()
        actions.addWidget(self.import_geojson_button)
        actions.addWidget(self.export_geojson_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(QLabel("GeoJSON hiện tại"))
        layout.addWidget(self.geometry_text)
        return box

    def _build_issues_panel(self) -> QGroupBox:
        box = QGroupBox("Validation Issues")
        layout = QVBoxLayout(box)
        layout.addWidget(self.issue_table)
        box.setMaximumHeight(190)
        return box

    def _connect_signals(self) -> None:
        self.new_button.clicked.connect(self._new_config)
        self.open_button.clicked.connect(self._open_config)
        self.reload_button.clicked.connect(self._reload_config)
        self.backup_button.clicked.connect(self._backup_config)
        self.save_button.clicked.connect(self._save_config)
        self.save_as_button.clicked.connect(self._save_config_as)
        self.validate_button.clicked.connect(self._validate_config)
        self.search_input.textChanged.connect(self._refresh_targets)
        self.group_filter.currentIndexChanged.connect(self._refresh_targets)
        self.group_list.currentItemChanged.connect(self._group_changed)
        self.add_group_button.clicked.connect(self._add_group)
        self.add_target_button.clicked.connect(self._add_target)
        self.target_table.selectionModel().selectionChanged.connect(self._target_selection_changed)
        self.delete_target_button.clicked.connect(self._delete_target)
        self.reset_button.clicked.connect(self._populate_inspector)
        self.apply_button.clicked.connect(self._apply_target)
        self.template_browse_button.clicked.connect(self._browse_template_pptx)
        self.default_label_font_browse_button.clicked.connect(self._browse_default_label_font)
        self.add_placeholder_button.clicked.connect(self._add_placeholder_field)
        self.delete_placeholder_button.clicked.connect(self._delete_placeholder_field)
        self.import_geojson_button.clicked.connect(self._import_geojson)
        self.export_geojson_button.clicked.connect(self._export_geojson)
        self.add_pattern_button.clicked.connect(self._add_pattern_row)
        self.apply_patterns_button.clicked.connect(self._apply_patterns)
        self.pattern_test_button.clicked.connect(self._test_pattern)
        self.issue_table.doubleClicked.connect(self._jump_from_issue)

    def _refresh_all(self) -> None:
        self._service.validate()
        self._refresh_status()
        self._refresh_stats()
        self._refresh_groups()
        self._refresh_targets()
        self._populate_inspector()
        self._refresh_defaults()
        self._refresh_patterns()
        self._refresh_raw_json()
        self._refresh_issues()

    def _refresh_status(self) -> None:
        state = self._service.state
        self.path_label.setText(
            f"Config: {state.source_path}" if state.source_path else "Chưa có file config."
        )
        self.dirty_label.setText("Có thay đổi chưa lưu" if state.dirty else "Đã lưu")
        if state.summary.error_count:
            self.valid_label.setText(f"Config lỗi ({state.summary.error_count})")
        elif state.summary.warning_count:
            self.valid_label.setText(f"Có cảnh báo ({state.summary.warning_count})")
        else:
            self.valid_label.setText("Config hợp lệ")
        has_source = state.source_path is not None
        self.reload_button.setEnabled(has_source)
        self.backup_button.setEnabled(has_source or bool(state.draft))
        self.save_button.setEnabled(has_source and state.dirty)
        self.save_as_button.setEnabled(True)

    def _refresh_stats(self) -> None:
        summary = self._service.state.summary
        self.stat_labels["targets"].setText(str(summary.target_count))
        self.stat_labels["enabled"].setText(str(summary.enabled_count))
        self.stat_labels["groups"].setText(str(summary.group_count))
        self.stat_labels["templates"].setText(str(summary.template_count))
        self.stat_labels["geometry"].setText(str(summary.geometry_count))
        self.stat_labels["issues"].setText(str(summary.warning_count + summary.error_count))

    def _refresh_groups(self) -> None:
        self.group_list.blockSignals(True)
        self.group_list.clear()
        all_item = QListWidgetItem("Tất cả target")
        all_item.setData(Qt.ItemDataRole.UserRole, "")
        self.group_list.addItem(all_item)
        selected_row = 0
        for row, group in enumerate(self._service.groups(), start=1):
            item = QListWidgetItem(f"{group.title}\nkey {group.key} · {group.target_count} target")
            item.setData(Qt.ItemDataRole.UserRole, group.key)
            item.setToolTip(f"{group.title} ({group.key})")
            self.group_list.addItem(item)
            if group.key == self._selected_group_key:
                selected_row = row
        self.group_list.setCurrentRow(selected_row)
        self.group_list.blockSignals(False)

    def _refresh_targets(self) -> None:
        rows = self._filtered_targets()
        self.target_model.set_rows(rows, self._service.state.issues)
        self.target_table.resizeColumnsToContents()
        if self._selected_target_id:
            row = self.target_model.row_for_target_id(self._selected_target_id)
            if row >= 0:
                self.target_table.selectRow(row)
                return
        if rows:
            self._selected_target_id = str(rows[0].get("id", ""))
            self.target_table.selectRow(0)
        else:
            self._selected_target_id = None

    def _filtered_targets(self) -> list[dict[str, Any]]:
        rows = self._service.targets_for_group(self._selected_group_key)
        search = self.search_input.text().strip().lower()
        filter_index = self.group_filter.currentIndex()
        issues_by_target = {
            issue.target_id
            for issue in self._service.state.issues
            if issue.target_id and issue.severity in {IssueSeverity.ERROR, IssueSeverity.WARNING}
        }
        filtered: list[dict[str, Any]] = []
        for target in rows:
            if filter_index == 1 and not target.get("enabled", True):
                continue
            if filter_index == 2 and target.get("id") not in issues_by_target:
                continue
            if search and search not in _target_search_text(target):
                continue
            filtered.append(target)
        return filtered

    def _populate_inspector(self) -> None:
        target = self._current_target()
        self._loading_form = True
        try:
            has_target = target is not None
            for widget in (
                self.delete_target_button,
                self.reset_button,
                self.apply_button,
                self.template_browse_button,
                self.add_placeholder_button,
                self.delete_placeholder_button,
                self.import_geojson_button,
                self.export_geojson_button,
                self.geometry_text,
            ):
                widget.setEnabled(has_target)
            self.enabled_check.setEnabled(has_target)
            for field in self.target_fields.values():
                field.setEnabled(has_target)
            self.placeholder_table.setEnabled(has_target)
            if target is None:
                self.inspector_title.setText("Chưa chọn target")
                self.enabled_check.setChecked(False)
                for field in self.target_fields.values():
                    field.setText("")
                self.placeholder_table.setRowCount(0)
                self.geometry_text.setPlainText("")
                return
            target_id = str(target.get("id", ""))
            self.inspector_title.setText(f"{target.get('name', target_id)} · {target_id}")
            self.enabled_check.setChecked(bool(target.get("enabled", True)))
            self._ensure_template_local_for_inspector(target_id)
            target = self._current_target() or target
            values = _target_form_values(target)
            for key, field in self.target_fields.items():
                field.setText(values.get(key, ""))
            self._populate_placeholders(target)
            self._populate_geometry(target)
        finally:
            self._loading_form = False

    def _populate_placeholders(self, target: dict[str, Any]) -> None:
        export = target.get("export")
        placeholders = export.get("placeholders", []) if isinstance(export, dict) else []
        if not isinstance(placeholders, list):
            placeholders = []
        self.placeholder_table.setRowCount(len(placeholders))
        for row, placeholder in enumerate(placeholders):
            if not isinstance(placeholder, dict):
                placeholder = {}
            field_item = QTableWidgetItem(str(placeholder.get("field", "")))
            self.placeholder_table.setItem(row, 0, field_item)
            self.placeholder_table.setItem(
                row,
                1,
                QTableWidgetItem(str(placeholder.get("value", ""))),
            )
        self.placeholder_table.resizeColumnsToContents()

    def _populate_geometry(self, target: dict[str, Any]) -> None:
        self.geometry_text.setPlainText(_geojson_text_for_target(target))

    def _add_placeholder_field(self) -> None:
        if self._selected_target_id is None:
            return
        row = self.placeholder_table.rowCount()
        self.placeholder_table.insertRow(row)
        self.placeholder_table.setItem(
            row,
            0,
            QTableWidgetItem(_next_placeholder_field_name(self.placeholder_table)),
        )
        self.placeholder_table.setItem(row, 1, QTableWidgetItem(""))
        self.placeholder_table.selectRow(row)
        self.placeholder_table.setCurrentCell(row, 0)
        self.placeholder_table.editItem(self.placeholder_table.item(row, 0))

    def _delete_placeholder_field(self) -> None:
        if self._selected_target_id is None or self.placeholder_table.rowCount() == 0:
            return
        selected_rows = self.placeholder_table.selectionModel().selectedRows()
        row = selected_rows[0].row() if selected_rows else self.placeholder_table.currentRow()
        if row < 0:
            return
        self.placeholder_table.removeRow(row)

    def _refresh_defaults(self) -> None:
        defaults = self._service.state.draft.get("defaults")
        if not isinstance(defaults, dict):
            defaults = {}
        for key, field in self.defaults_fields.items():
            value = _get_dotted(defaults, key)
            field.setText(_format_default_value(value))

    def _refresh_patterns(self) -> None:
        patterns = self._service.state.draft.get("filename_patterns", [])
        if not isinstance(patterns, list):
            patterns = []
        self.pattern_table.setRowCount(len(patterns))
        for row, pattern in enumerate(patterns):
            if not isinstance(pattern, dict):
                pattern = {}
            self.pattern_table.setItem(row, 0, QTableWidgetItem(str(pattern.get("name", ""))))
            self.pattern_table.setItem(row, 1, QTableWidgetItem(str(pattern.get("pattern", ""))))
            self.pattern_table.setItem(row, 2, QTableWidgetItem(str(pattern.get("separator", "_"))))
        self.pattern_table.resizeColumnsToContents()

    def _refresh_raw_json(self) -> None:
        self.raw_json.setPlainText(self._service.raw_json())

    def _refresh_issues(self) -> None:
        self.issue_model.set_issues(self._service.state.issues)
        self.issue_table.resizeColumnsToContents()

    def _new_config(self) -> None:
        if not self._confirm_discard_dirty():
            return
        self._service.create_new()
        self._selected_group_key = None
        self._selected_target_id = None
        self.downstream_label.setText("")
        self._refresh_all()

    def _open_config(self) -> None:
        if not self._confirm_discard_dirty():
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Mở config",
            str(Path.cwd()),
            "JSON files (*.json);;All files (*)",
        )
        if path:
            self.load_config(path)

    def _reload_config(self) -> None:
        if not self._confirm_discard_dirty():
            return
        try:
            self._service.reload()
        except ConfigEditorError as error:
            self._show_error("Không tải lại được config", str(error))
            return
        self._refresh_all()

    def _backup_config(self) -> None:
        try:
            path = self._service.backup()
        except ConfigEditorError as error:
            self._show_error("Không tạo được backup", str(error))
            return
        self.downstream_label.setText(f"Đã tạo backup: {path}")

    def _save_config(self) -> None:
        try:
            state = self._service.save()
        except (ConfigEditorError, OSError) as error:
            self._show_error("Không lưu được config", str(error))
            return
        self.configSaved.emit(state.source_path)
        self.downstream_label.setText(_downstream_refresh_message())
        self._refresh_all()

    def _save_config_as(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Lưu config thành",
            str(self._service.state.source_path or Path.cwd() / "config.json"),
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            state = self._service.save(path)
        except (ConfigEditorError, OSError) as error:
            self._show_error("Không lưu được config", str(error))
            return
        self.configSaved.emit(state.source_path)
        self.downstream_label.setText(_downstream_refresh_message())
        self._refresh_all()

    def _validate_config(self) -> None:
        self._service.validate()
        self._refresh_all()

    def _group_changed(self, current: QListWidgetItem | None) -> None:
        if current is None:
            self._selected_group_key = None
        else:
            value = current.data(Qt.ItemDataRole.UserRole)
            self._selected_group_key = str(value) if value else None
        self._refresh_targets()
        self._populate_inspector()

    def _add_group(self) -> None:
        key = f"group_{len(self._service.groups()) + 1}"
        title = "Group mới"
        item = QListWidgetItem(f"{title}\nkey {key} · 0 target")
        item.setData(Qt.ItemDataRole.UserRole, key)
        self.group_list.addItem(item)
        self.group_list.setCurrentItem(item)

    def _add_target(self) -> None:
        group_key = self._selected_group_key or "0"
        group_title = _group_title_for_key(self._service, group_key)
        target_id = self._service.add_target(group_key=group_key, group_title=group_title)
        self._selected_target_id = target_id
        self._refresh_all()

    def _target_selection_changed(self) -> None:
        selected = self.target_table.selectionModel().selectedRows()
        if not selected:
            self._selected_target_id = None
        else:
            target_id = selected[0].data(TargetTableRole.TARGET_ID)
            self._selected_target_id = str(target_id) if target_id else None
        self._populate_inspector()

    def _delete_target(self) -> None:
        target = self._current_target()
        if target is None:
            return
        target_id = str(target.get("id", ""))
        answer = QMessageBox.question(
            self,
            "Xóa target",
            (
                f"Xóa target `{target_id}` khỏi draft config?\n\n"
                "Nếu workspace đang có composition của target này, Review/Edit và Export "
                "cần reload "
                "hoặc xử lý lại sau khi lưu config."
            ),
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_target(target_id)
        except ConfigEditorError as error:
            self._show_error("Không xóa được target", str(error))
            return
        self._selected_target_id = None
        self._refresh_all()

    def _apply_target(self) -> None:
        self._persist_target_form(refresh=True)

    def _persist_target_form(self, *, refresh: bool) -> bool:
        if self._loading_form or self._selected_target_id is None:
            return False
        target = self._current_target()
        if target is None:
            return False
        updates = _collect_target_updates(
            self.enabled_check,
            self.target_fields,
            self.placeholder_table,
            target,
        )
        try:
            self._selected_target_id = self._service.update_target(
                self._selected_target_id,
                updates,
            )
        except (ConfigEditorError, ValueError) as error:
            self._show_error("Không cập nhật được target", str(error))
            return False
        if refresh:
            self._sync_group_to_selected_target()
            self._refresh_all()
        return True

    def _sync_group_to_selected_target(self) -> None:
        if self._selected_target_id is None:
            return
        target = self._service.target(self._selected_target_id)
        if target is None:
            return
        group_key, _group_title = _target_group(target)
        self._selected_group_key = None if group_key in {"", "0"} else group_key

    def _browse_template_pptx(self) -> None:
        if self._selected_target_id is None:
            return
        current_text = self.target_fields["export.template_pptx_file"].text().strip()
        start_dir = str(Path(current_text).expanduser().parent) if current_text else str(Path.cwd())
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Chọn template PPTX",
            start_dir,
            "PowerPoint files (*.pptx);;All files (*)",
        )
        if path:
            try:
                relative_path = self._service.import_template_pptx(
                    self._selected_target_id,
                    path,
                )
            except ConfigEditorError as error:
                self._show_error("Không copy được template", str(error))
                return
            self.target_fields["export.template_pptx_file"].setText(relative_path)
            self.downstream_label.setText(
                f"Đã copy template vào data/templates và cập nhật target: {relative_path}"
            )
            self._refresh_status()
            self._refresh_stats()
            self._refresh_targets()
            self._refresh_raw_json()
            self._refresh_issues()

    def _browse_default_label_font(self) -> None:
        current_text = self.defaults_fields["grid.style.default_label_font"].text().strip()
        start_dir = str(Path(current_text).expanduser().parent) if current_text else str(Path.cwd())
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Chọn font label",
            start_dir,
            "Font files (*.ttf *.otf *.ttc);;All files (*)",
        )
        if not path:
            return
        try:
            relative_path = self._service.import_default_label_font(path)
        except ConfigEditorError as error:
            self._show_error("Không copy được font label", str(error))
            return
        self.defaults_fields["grid.style.default_label_font"].setText(relative_path)
        self.downstream_label.setText(
            f"Đã copy font label vào fonts và cập nhật defaults: {relative_path}"
        )
        self._refresh_status()
        self._refresh_stats()
        self._refresh_raw_json()
        self._refresh_issues()

    def _ensure_template_local_for_inspector(self, target_id: str) -> None:
        try:
            updated_path = self._service.ensure_target_template_local(target_id)
        except ConfigEditorError as error:
            message = f"{error} Hãy chọn lại file bằng Browse."
            self.downstream_label.setText(message)
            self.template_browse_button.setToolTip(message)
            return
        if updated_path:
            self.template_browse_button.setToolTip(
                "Chọn template PPTX và copy vào data/templates"
            )
            self._service.validate()
            self._refresh_status()
            self._refresh_stats()
            self._refresh_raw_json()
            self._refresh_issues()

    def _apply_defaults(self) -> None:
        updates: dict[str, Any] = {}
        for key, field in self.defaults_fields.items():
            value = field.text().strip()
            updates[key] = _parse_scalar(value)
        self._service.update_defaults(updates)
        self.downstream_label.setText(
            "Đã cập nhật defaults trong draft. Target grid.interval và target overrides "
            "không bị ghi đè."
        )
        self._refresh_all()

    def _apply_patterns(self) -> None:
        patterns: list[dict[str, Any]] = []
        for row in range(self.pattern_table.rowCount()):
            patterns.append(
                {
                    "name": _table_text(self.pattern_table, row, 0),
                    "pattern": _table_text(self.pattern_table, row, 1),
                    "separator": _table_text(self.pattern_table, row, 2) or "_",
                }
            )
        self._service.update_filename_patterns(patterns)
        self._refresh_all()

    def _add_pattern_row(self) -> None:
        row = self.pattern_table.rowCount()
        self.pattern_table.insertRow(row)
        self.pattern_table.setItem(row, 0, QTableWidgetItem("Pattern mới"))
        self.pattern_table.setItem(row, 1, QTableWidgetItem("yyyyMMdd_HHmmss_*"))
        self.pattern_table.setItem(row, 2, QTableWidgetItem("_"))

    def _test_pattern(self) -> None:
        result = self._service.test_filename(self.pattern_test_input.text().strip())
        self.pattern_result_label.setText(
            "UTC filename + 7 giờ | "
            f"date={result.capture_date or '-'} · "
            f"time={result.capture_time or '-'} · "
            f"cloud={result.cloud_percent or '-'}"
        )

    def _import_geojson(self) -> None:
        if self._selected_target_id is None:
            return
        target = self._current_target()
        if target is None:
            return
        if _target_has_geometry(target):
            answer = QMessageBox.question(
                self,
                "Thay thế geometry",
                "Target đã có geometry. Thay thế bằng GeoJSON mới?",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Ok:
                return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Import GeoJSON",
            str(Path.cwd()),
            "GeoJSON files (*.geojson *.json);;All files (*)",
        )
        if not path:
            return
        if not self._persist_target_form(refresh=False):
            return
        try:
            self._service.import_geojson(self._selected_target_id, path)
        except ConfigEditorError as error:
            self._show_error("Không import được GeoJSON", str(error))
            return
        self._sync_group_to_selected_target()
        self._refresh_all()

    def _export_geojson(self) -> None:
        if self._selected_target_id is None:
            return
        suggested = f"{self._selected_target_id}.geojson"
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Export GeoJSON",
            str(Path.cwd() / suggested),
            "GeoJSON files (*.geojson);;JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            self._service.export_geojson(self._selected_target_id, path)
        except ConfigEditorError as error:
            self._show_error("Không export được GeoJSON", str(error))
            return

    def _jump_from_issue(self, index: QModelIndex) -> None:
        target_id = index.data(IssueTableRole.TARGET_ID)
        if not target_id:
            return
        self._select_target(str(target_id))

    def _select_target(self, target_id: str) -> None:
        target = self._service.target(target_id)
        if target is None:
            return
        group_key, _title = _target_group(target)
        self._selected_group_key = None if group_key in {"", "0"} else group_key
        self._refresh_groups()
        self._refresh_targets()
        row = self.target_model.row_for_target_id(target_id)
        if row >= 0:
            self.target_table.selectRow(row)

    def _current_target(self) -> dict[str, Any] | None:
        if self._selected_target_id is None:
            return None
        return self._service.target(self._selected_target_id)

    def _confirm_discard_dirty(self) -> bool:
        if not self._service.state.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Bỏ thay đổi chưa lưu?",
            "Draft config có thay đổi chưa lưu. Tiếp tục và bỏ thay đổi?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Discard,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)


def _target_tooltip(target: dict[str, Any], issues: list[Issue]) -> str:
    target_id = str(target.get("id", ""))
    if not issues:
        return f"{target_id} hợp lệ trong draft hiện tại."
    lines = [target_id]
    for issue in issues:
        lines.append(f"[{issue.severity.value.upper()}] {issue.message}")
        if issue.remediation:
            lines.append(issue.remediation)
    return "\n".join(lines)


def _grid_label(target: dict[str, Any]) -> str:
    interval = _get_dotted(target, "grid.interval")
    if not isinstance(interval, dict):
        return ""
    parts = []
    if interval.get("degrees"):
        parts.append(f"{interval['degrees']} độ")
    if interval.get("minutes"):
        parts.append(f"{interval['minutes']} phút")
    if interval.get("seconds"):
        parts.append(f"{interval['seconds']} giây")
    return " ".join(parts)


def _target_search_text(target: dict[str, Any]) -> str:
    group = target.get("group")
    values = [
        target.get("id", ""),
        target.get("name", ""),
        target.get("alias", ""),
        target.get("export", {}).get("template_pptx_file", "")
        if isinstance(target.get("export"), dict)
        else "",
    ]
    if isinstance(group, dict):
        values.extend([group.get("key", ""), group.get("title", "")])
    return " ".join(str(value).lower() for value in values)


def _target_form_values(target: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in (
        "id",
        "group.key",
        "group.title",
        "sort_order",
        "name",
        "alias",
        "scale",
        "grid.interval.degrees",
        "grid.interval.minutes",
        "grid.interval.seconds",
        "export.template_pptx_file",
        "export.template_txt_value",
    ):
        value = _get_dotted(target, key)
        values[key] = "" if value is None else str(value)
    coordinate = target.get("coordinate")
    if isinstance(coordinate, list) and len(coordinate) == 2:
        values["coordinate.0"] = str(coordinate[0])
        values["coordinate.1"] = str(coordinate[1])
    else:
        values["coordinate.0"] = ""
        values["coordinate.1"] = ""
    return values


def _collect_target_updates(
    enabled_check: QCheckBox,
    fields: dict[str, QLineEdit],
    placeholder_table: QTableWidget,
    current_target: dict[str, Any],
) -> dict[str, Any]:
    updates: dict[str, Any] = {"enabled": enabled_check.isChecked()}
    coordinate: list[float] = [0.0, 0.0]
    for key, field in fields.items():
        text = field.text().strip()
        if key == "coordinate.0":
            coordinate[0] = float(text or 0)
        elif key == "coordinate.1":
            coordinate[1] = float(text or 0)
        elif key in {"sort_order", "scale"}:
            updates[key] = int(text or 0)
        elif key.startswith("grid.interval."):
            updates[key] = float(text) if "." in text else int(text or 0)
        else:
            updates[key] = text
    updates["coordinate"] = coordinate
    updates["export.placeholders"] = _collect_placeholders(placeholder_table, current_target)
    return updates


def _collect_placeholders(
    table: QTableWidget,
    current_target: dict[str, Any],
) -> list[dict[str, Any]]:
    existing_by_field: dict[str, dict[str, Any]] = {}
    existing_by_row: list[dict[str, Any]] = []
    export = current_target.get("export")
    if isinstance(export, dict) and isinstance(export.get("placeholders"), list):
        for placeholder in export["placeholders"]:
            if isinstance(placeholder, dict):
                existing = copy.deepcopy(placeholder)
                existing_by_row.append(existing)
                existing_by_field[str(placeholder.get("field", ""))] = existing

    placeholders: list[dict[str, Any]] = []
    for row in range(table.rowCount()):
        field = _table_text(table, row, 0)
        if not field:
            continue
        value = _table_text(table, row, 1)
        placeholder = copy.deepcopy(
            existing_by_field.get(
                field,
                existing_by_row[row] if row < len(existing_by_row) else {"field": field},
            )
        )
        placeholder["field"] = field
        placeholder.setdefault("kind", "map_image" if field == "map_image" else "text")
        if value:
            placeholder["value"] = value
        else:
            placeholder.pop("value", None)
        placeholders.append(placeholder)
    return placeholders


def _get_dotted(data: dict[str, Any], dotted_key: str) -> Any:
    current: Any = data
    for part in dotted_key.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _table_text(table: QTableWidget, row: int, column: int) -> str:
    item = table.item(row, column)
    return "" if item is None else item.text().strip()


def _next_placeholder_field_name(table: QTableWidget) -> str:
    used = {_table_text(table, row, 0) for row in range(table.rowCount())}
    index = 1
    while True:
        field_name = f"field_{index}"
        if field_name not in used:
            return field_name
        index += 1


def _table_height_for_visible_rows(table: QTableWidget, visible_rows: int) -> int:
    header_height = table.horizontalHeader().sizeHint().height()
    row_height = table.verticalHeader().defaultSectionSize()
    return header_height + (row_height * visible_rows) + (table.frameWidth() * 2) + 8


def _format_default_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    if "," in value or (value.startswith("[") and value.endswith("]")):
        list_text = value.strip()
        if list_text.startswith("[") and list_text.endswith("]"):
            list_text = list_text[1:-1]
        return [_parse_scalar(item.strip()) for item in list_text.split(",")]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _target_group(target: dict[str, Any]) -> tuple[str, str]:
    group = target.get("group")
    if isinstance(group, dict):
        return str(group.get("key", "0")), str(group.get("title", "Chưa phân nhóm"))
    return "0", "Chưa phân nhóm"


def _target_has_geometry(target: dict[str, Any]) -> bool:
    metadata = target.get("metadata")
    return isinstance(metadata, dict) and isinstance(metadata.get("geojson_geometry"), dict)


def _geojson_text_for_target(target: dict[str, Any]) -> str:
    metadata = target.get("metadata")
    geometry = metadata.get("geojson_geometry") if isinstance(metadata, dict) else None
    if not isinstance(geometry, dict):
        return ""
    feature = {
        "type": "Feature",
        "properties": {
            "target_id": target.get("id", ""),
            "name": target.get("name", ""),
        },
        "geometry": geometry,
    }
    return json.dumps(feature, ensure_ascii=False, indent=2)


def _group_title_for_key(service: ConfigEditorService, group_key: str) -> str:
    for group in service.groups():
        if group.key == group_key:
            return group.title
    return "Chưa phân nhóm" if group_key == "0" else "Group mới"


def _downstream_refresh_message() -> str:
    return (
        "Đã lưu config. Nếu workspace đang mở, hãy reload config hoặc chạy lại ingestion/"
        "validation/preflight khi đã đổi enabled, target, group, geometry, template, defaults "
        "hoặc filename patterns."
    )
