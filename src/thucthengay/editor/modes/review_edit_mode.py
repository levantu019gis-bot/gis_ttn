"""Review/Edit workstation mode."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import QModelIndex, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from thucthengay.config import ConfigUpdateError, update_target_alignment_defaults
from thucthengay.editor.models.composition_tree_model import (
    CompositionTreeModel,
    QueueFilter,
    queue_filter_label,
)
from thucthengay.editor.models.layer_stack_model import LayerStackColumn, LayerStackModel
from thucthengay.editor.preferences import PreferencesService
from thucthengay.editor.render_worker import RenderWorker
from thucthengay.editor.tile_preview_worker import TilePreviewWorker
from thucthengay.editor.widgets import (
    GisCanvasWidget,
    MetadataEditorDialog,
    TargetPreviewRequestToken,
    TargetPreviewViewportOverlay,
    TargetPreviewWidget,
    WarningsPanelWidget,
    confirm_date_change_dialog,
)
from thucthengay.export.final_render import final_render_output_size
from thucthengay.export.template_selection import (
    template_metadata_for_composition,
    template_pptx_file_for_composition,
)
from thucthengay.gis import view_geo_bounds
from thucthengay.history import HistoryRecordError, HistoryService
from thucthengay.ingestion import cache_layer_source, scan_geotiff_file
from thucthengay.jobs import (
    JobState,
    PreviewRenderJobResult,
    PreviewRenderQuality,
    PreviewRenderRequest,
)
from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    ImageLayerSourceKind,
    Issue,
    MetadataSource,
    MetadataStatus,
    RenderPreviewConfig,
    TargetConfig,
    TemplateMetadata,
    TemporalCompareOrientation,
    WorkspaceSessionState,
)
from thucthengay.render.core import MapRenderCache, render_map_with_cache
from thucthengay.render.raster import render_raster_layers
from thucthengay.render.spec import RenderSpecError, build_render_spec
from thucthengay.render.target_preview import build_target_preview_spec
from thucthengay.render.tile import TileCache
from thucthengay.render.tile_preview import (
    TilePreviewSettings,
    TilePreviewState,
    render_tile_preview_map,
)
from thucthengay.render.tile_scheduler import TileScheduler
from thucthengay.validation import (
    ValidationContext,
    ValidationResult,
    validate_composition_readiness,
)
from thucthengay.workspace import WorkspaceError, WorkspaceService


class ReviewEditMode(QWidget):
    """Desktop Review/Edit layout and target-composition navigator."""

    compositionSelected = Signal(object)
    CANVAS_VIEW_PERSIST_DEBOUNCE_MS = 250
    GRID_INPUT_MIN_HEIGHT = 28

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        preferences_service: PreferencesService | None = None,
        history_service: HistoryService | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("reviewEditMode")
        self.setMinimumSize(960, 560)
        self._preferences_service = preferences_service
        self._history_service = history_service or HistoryService.disabled()
        self._workspace_service: WorkspaceService | None = None
        self._targets: list[TargetConfig] | None = None
        self.selected_composition: Composition | None = None
        self._suppress_selection_validation = False
        self._render_threads: dict[str, QThread] = {}
        self._render_workers: dict[str, RenderWorker] = {}
        self._render_tokens: dict[str, object] = {}
        self._canvas_render_epoch = 0
        self._canvas_render_cache = MapRenderCache()
        self._render_preview_config = RenderPreviewConfig()
        self._canvas_tile_cache = TileCache(
            max_bytes=self._render_preview_config.tile_preview.max_cache_bytes
        )
        self._canvas_tile_scheduler = TileScheduler(cache=self._canvas_tile_cache)
        self._canvas_tile_state = TilePreviewState()
        self._pending_canvas_view: tuple[str, str, list[float], int | None] | None = None
        self._pending_canvas_render_composition: Composition | None = None
        self._target_render_thread: QThread | None = None
        self._target_render_worker: RenderWorker | None = None
        self._target_render_token: TargetPreviewRequestToken | None = None
        self._loading_compare_controls = False
        self._compare_enabled_global = False
        self._compare_orientation_global = TemporalCompareOrientation.VERTICAL
        self._compare_global_initialized = False

        self.tree_model = CompositionTreeModel(self)
        self.tree_view = QTreeView()
        self.tree_view.setObjectName("reviewCompositionTree")
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setUniformRowHeights(True)
        self.tree_view.setMinimumWidth(280)
        self.tree_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.filter_button_group = QButtonGroup(self)
        self.filter_button_group.setExclusive(True)
        self.filter_buttons: dict[QueueFilter, QPushButton] = {}
        for queue_filter in QueueFilter:
            button = QPushButton(queue_filter_label(queue_filter))
            button.setObjectName(f"queueFilter_{queue_filter.value}")
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, selected_filter=queue_filter: self._apply_queue_filter(
                    selected_filter
                )
            )
            self.filter_button_group.addButton(button)
            self.filter_buttons[queue_filter] = button
        self.filter_buttons[QueueFilter.ALL].setChecked(True)

        self.empty_state_label = QLabel("Không có composition khớp bộ lọc hiện tại.")
        self.empty_state_label.setObjectName("reviewQueueEmptyState")
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setVisible(False)

        self.composition_title = QLabel("Chưa chọn composition")
        self.composition_title.setObjectName("reviewCompositionTitle")
        self.composition_title.setWordWrap(True)

        self.layer_model = LayerStackModel(self)
        self.layer_table = QTableView()
        self.layer_table.setObjectName("reviewLayerStackTable")
        self.layer_table.setModel(self.layer_model)
        self.layer_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.layer_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.layer_table.setAlternatingRowColors(True)
        self.layer_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.layer_table.verticalHeader().setVisible(False)
        self.layer_table.verticalHeader().setDefaultSectionSize(28)
        self.layer_table.setMinimumHeight(156)
        layer_header = self.layer_table.horizontalHeader()
        layer_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layer_header.setSectionResizeMode(
            int(LayerStackColumn.FILENAME),
            QHeaderView.ResizeMode.Stretch,
        )

        self.move_layer_up_button = QPushButton("Lên")
        self.move_layer_up_button.setObjectName("reviewLayerMoveUp")
        self.move_layer_up_button.clicked.connect(lambda: self._move_selected_layer(-1))
        self.move_layer_down_button = QPushButton("Xuống")
        self.move_layer_down_button.setObjectName("reviewLayerMoveDown")
        self.move_layer_down_button.clicked.connect(lambda: self._move_selected_layer(1))
        self.edit_metadata_button = QPushButton("Sửa metadata")
        self.edit_metadata_button.setObjectName("reviewLayerEditMetadata")
        self.edit_metadata_button.setToolTip("Sửa ngày/giờ/cloud cho layer đang chọn")
        self.edit_metadata_button.clicked.connect(self._open_metadata_editor)
        self.edit_metadata_button.setEnabled(False)

        self.layer_warning_label = QLabel(
            "Không còn layer nào đang bật. Cần bật ít nhất 1 layer."
        )
        self.layer_warning_label.setObjectName("reviewLayerStackWarning")
        self.layer_warning_label.setWordWrap(True)
        self.layer_warning_label.setVisible(False)

        self.grid_degrees_input = QLineEdit("0")
        self.grid_degrees_input.setObjectName("reviewGridDegrees")
        self.grid_degrees_input.setFixedWidth(56)
        self.grid_degrees_input.setToolTip("Độ của khoảng grid")
        self.grid_minutes_input = QLineEdit("0")
        self.grid_minutes_input.setObjectName("reviewGridMinutes")
        self.grid_minutes_input.setFixedWidth(56)
        self.grid_minutes_input.setToolTip("Phút của khoảng grid")
        self.grid_seconds_input = QLineEdit("0")
        self.grid_seconds_input.setObjectName("reviewGridSeconds")
        self.grid_seconds_input.setFixedWidth(64)
        self.grid_seconds_input.setToolTip("Giây của khoảng grid")
        self.grid_scale_input = QLineEdit("50000")
        self.grid_scale_input.setObjectName("reviewGridScale")
        self.grid_scale_input.setFixedWidth(96)
        self.grid_scale_input.setToolTip("Mẫu số tỷ lệ bản đồ")
        for grid_input in (
            self.grid_degrees_input,
            self.grid_minutes_input,
            self.grid_seconds_input,
            self.grid_scale_input,
        ):
            grid_input.setMinimumHeight(self.GRID_INPUT_MIN_HEIGHT)
        self.grid_status_label = QLabel("Chưa chọn composition.")
        self.grid_status_label.setObjectName("reviewGridStatus")
        self.grid_status_label.setWordWrap(True)
        self.grid_validation_label = QLabel("")
        self.grid_validation_label.setObjectName("reviewGridValidation")
        self.grid_validation_label.setWordWrap(True)
        self.save_grid_button = QPushButton("Lưu grid")
        self.save_grid_button.setObjectName("reviewGridSave")
        self.save_grid_button.clicked.connect(self._save_grid_override)

        self.target_preview = TargetPreviewWidget()
        self.preview_summary = self.target_preview.status_label

        self.gis_canvas = GisCanvasWidget()
        self.gis_canvas.set_live_preview_max_fps(
            self._render_preview_config.tile_preview.live_preview_max_fps
        )
        self.gis_canvas.viewEditCompleted.connect(self._persist_canvas_view)
        self.gis_canvas.viewInteractionChanged.connect(self._handle_canvas_view_interaction)
        self.gis_canvas.comparePaneViewEditCompleted.connect(
            self._persist_compare_pane_view
        )
        self.gis_canvas.comparePaneViewInteractionChanged.connect(
            self._handle_canvas_view_interaction
        )
        self._canvas_view_persist_timer = QTimer(self)
        self._canvas_view_persist_timer.setSingleShot(True)
        self._canvas_view_persist_timer.timeout.connect(self._flush_pending_canvas_view)
        self.refresh_canvas_button = QPushButton("Refresh")
        self.refresh_canvas_button.setObjectName("reviewGisRefresh")
        self.refresh_canvas_button.setToolTip(
            "Cancel current preview, clear render cache, and render the selected canvas again"
        )
        self.refresh_canvas_button.clicked.connect(self._refresh_canvas_render)
        self.refresh_canvas_button.setEnabled(False)
        self.export_canvas_button = QPushButton("Xuất ảnh")
        self.export_canvas_button.setObjectName("reviewGisExportImage")
        self.export_canvas_button.setToolTip("Xuất ảnh đang hiển thị trong GIS editor")
        self.export_canvas_button.clicked.connect(self._export_canvas_image)
        self.export_canvas_button.setEnabled(False)
        self.compare_enabled_checkbox = QCheckBox("Compare")
        self.compare_enabled_checkbox.setObjectName("reviewCompareEnabled")
        self.compare_orientation_combo = QComboBox()
        self.compare_orientation_combo.setObjectName("reviewCompareOrientation")
        self.compare_orientation_combo.addItems(
            [
                TemporalCompareOrientation.VERTICAL.value,
                TemporalCompareOrientation.HORIZONTAL.value,
            ]
        )
        self.compare_pane_a_combo = QComboBox()
        self.compare_pane_a_combo.setObjectName("reviewComparePaneA")
        self.compare_pane_b_combo = QComboBox()
        self.compare_pane_b_combo.setObjectName("reviewComparePaneB")
        self.compare_status_label = QLabel("")
        self.compare_status_label.setObjectName("reviewCompareStatus")
        self.compare_status_label.setWordWrap(True)
        self.compare_enabled_checkbox.toggled.connect(self._persist_temporal_compare_controls)
        self.compare_orientation_combo.currentTextChanged.connect(
            self._persist_temporal_compare_controls
        )
        self.compare_pane_a_combo.currentIndexChanged.connect(
            self._persist_temporal_compare_controls
        )
        self.compare_pane_b_combo.currentIndexChanged.connect(
            self._persist_temporal_compare_controls
        )

        self.previous_button = QPushButton("Trước")
        self.previous_button.setObjectName("reviewActionPrevious")
        self.previous_button.setToolTip("Phím trái: quay lại composition trước")
        self.previous_button.clicked.connect(self._go_previous)
        self.skip_button = QPushButton("Skip")
        self.skip_button.setObjectName("reviewActionSkip")
        self.skip_button.setToolTip("Phím lên: đánh dấu đã duyệt nhưng không include")
        self.skip_button.clicked.connect(self._skip_selected)
        self.include_validate_button = QPushButton("Include/Validate")
        self.include_validate_button.setObjectName("reviewActionIncludeValidate")
        self.include_validate_button.setToolTip(
            "Phím phải: validate rồi include nếu không có lỗi blocking"
        )
        self.include_validate_button.clicked.connect(self._include_selected)
        self.include_validate_button.setProperty("primaryAction", True)
        self.revalidate_button = QPushButton("Revalidate")
        self.revalidate_button.setObjectName("reviewActionRevalidate")
        self.revalidate_button.setToolTip(
            "Chạy lại validation gate hiện tại cho composition đang chọn"
        )
        self.revalidate_button.clicked.connect(self._revalidate_selected)
        for button in (self.previous_button, self.skip_button, self.revalidate_button):
            button.setProperty("primaryAction", False)

        self.action_summary = QLabel("Chọn composition để dùng review actions.")
        self.action_summary.setObjectName("reviewActionSummary")
        self.action_summary.setWordWrap(True)

        self.warnings_panel = WarningsPanelWidget()
        self.warnings_panel.setObjectName("reviewWarningsPanel")
        self.warnings_panel.jumpRequested.connect(self._handle_issue_jump)

        left_panel = self._build_left_panel()
        right_panel = self._build_right_panel()

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("reviewMainSplitter")
        self.main_splitter.addWidget(left_panel)
        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        saved_splitter_sizes = (
            self._preferences_service.preferences.ui.review_main_splitter_sizes
            if self._preferences_service is not None
            else None
        )
        self.main_splitter.setSizes(saved_splitter_sizes or [360, 920])
        self.main_splitter.splitterMoved.connect(self._persist_main_splitter_sizes)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self.main_splitter)

        selection_model = self.tree_view.selectionModel()
        if selection_model is not None:
            selection_model.currentChanged.connect(self._select_composition_index)
        self.layer_model.dataChanged.connect(self._persist_layer_visibility)
        layer_selection = self.layer_table.selectionModel()
        if layer_selection is not None:
            layer_selection.currentChanged.connect(self._update_metadata_edit_button)
            layer_selection.currentChanged.connect(self._persist_selected_layer_session)
        self._update_review_action_state()

    def _persist_main_splitter_sizes(self, _position: int, _index: int) -> None:
        if self._preferences_service is None:
            return
        self._preferences_service.update_review_splitter_sizes(self.main_splitter.sizes())

    def set_history_service(self, history_service: HistoryService | None) -> None:
        """Set the SQLite-backed history service used by Include/Validate."""
        self._history_service = history_service or HistoryService.disabled()

    def _load_workspace_session_state(
        self,
        workspace_service: WorkspaceService,
    ) -> WorkspaceSessionState:
        try:
            return workspace_service.load_session_state()
        except WorkspaceError as error:
            self.action_summary.setText(f"Bỏ qua session state không hợp lệ: {error}")
            return WorkspaceSessionState()

    def _persist_review_session_state(
        self,
        *,
        selected_layer_id: str | None = None,
    ) -> None:
        if self._workspace_service is None:
            return
        composition_id = self._current_or_selected_composition_id()
        if selected_layer_id is None:
            selected_layer_id = self.layer_model.layer_id_for_index(
                self.layer_table.currentIndex()
            )
        try:
            self._workspace_service.update_review_session_state(
                selected_composition_id=composition_id,
                selected_layer_id=selected_layer_id,
                active_queue_filter=self.tree_model.active_queue_filter.value,
            )
        except WorkspaceError as error:
            self.action_summary.setText(f"Không lưu được session state: {error}")

    def _persist_selected_layer_session(self, *_args: object) -> None:
        self._persist_review_session_state()

    def set_render_preview_config(self, config: RenderPreviewConfig | None) -> None:
        """Set Review/Edit preview rendering config without reloading the workspace."""
        self._set_render_preview_config(config)

    def load_workspace(
        self,
        workspace_service: WorkspaceService,
        *,
        targets: list[TargetConfig] | None = None,
        render_preview_config: RenderPreviewConfig | None = None,
    ) -> None:
        """Load composition navigation from a workspace service."""
        selected_id = self._current_or_selected_composition_id()
        session_state = self._load_workspace_session_state(workspace_service)
        if selected_id is None:
            selected_id = session_state.review.selected_composition_id
            queue_filter = _queue_filter_from_session(session_state.review.active_queue_filter)
        else:
            queue_filter = self.tree_model.active_queue_filter
        self._workspace_service = workspace_service
        self._targets = list(targets) if targets is not None else None
        if render_preview_config is not None:
            self._set_render_preview_config(render_preview_config)
        self._canvas_render_cache.clear()
        self._reset_tile_preview_state()
        self._compare_enabled_global = False
        self._compare_orientation_global = TemporalCompareOrientation.VERTICAL
        self._compare_global_initialized = False
        compositions = workspace_service.list_compositions()
        self.tree_model.set_compositions(compositions, targets=targets)
        self.tree_model.set_queue_filter(queue_filter)
        self.tree_view.expandAll()
        self._refresh_filter_controls()
        self._restore_selection(selected_id)

    def refresh_config_targets(
        self,
        targets: list[TargetConfig],
        *,
        render_preview_config: RenderPreviewConfig | None = None,
    ) -> None:
        """Refresh target ordering/details after Config tab saves a new config."""
        if self._workspace_service is None:
            return
        selected_id = self._current_or_selected_composition_id()
        self._targets = list(targets)
        if render_preview_config is not None:
            self._set_render_preview_config(render_preview_config)
        self._canvas_render_cache.clear()
        self._reset_tile_preview_state()
        try:
            compositions = self._workspace_service.list_compositions()
        except WorkspaceError as error:
            self.action_summary.setText(f"Không reload được config targets: {error}")
            return
        self.tree_model.set_compositions(compositions, targets=targets)
        self.tree_view.expandAll()
        self._refresh_filter_controls()
        self._restore_selection(selected_id)
        self.action_summary.setText(
            "Đã reload target config mới. Hãy revalidate composition nếu config ảnh hưởng."
        )

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self._flush_pending_canvas_view()
        self._cancel_target_render()
        self._cancel_render(wait=True)
        super().closeEvent(event)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(320)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Composition queue"))
        layout.addLayout(self._filter_bar_layout())
        layout.addWidget(self.tree_view, 3)
        layout.addWidget(self.empty_state_label)
        layout.addWidget(self._build_layer_panel(), 2)
        layout.addWidget(
            self._panel_frame(
                "Target Preview",
                self.target_preview,
                object_name="reviewTargetPreviewFrame",
            ),
            2,
        )
        return panel

    def _filter_bar_layout(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(4)
        for queue_filter in QueueFilter:
            layout.addWidget(self.filter_buttons[queue_filter])
        layout.addStretch(1)
        return layout

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("reviewRightPanel")
        panel.setMinimumWidth(580)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_gis_editor_panel(), 8)
        layout.addLayout(self._review_action_layout())
        layout.addWidget(self._build_review_bottom_panel(), 1)
        return panel

    def _build_gis_editor_panel(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumHeight(104)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.addWidget(QLabel("GIS editor"))
        header.addStretch(1)
        header.addWidget(self.refresh_canvas_button)
        header.addWidget(self.export_canvas_button)

        layout.addLayout(header)
        layout.addWidget(self._build_compare_panel())
        layout.addWidget(self.gis_canvas, 1)
        return frame

    def _build_compare_panel(self) -> QWidget:
        panel = QWidget()
        layout = QGridLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(4)
        layout.addWidget(self.compare_enabled_checkbox, 0, 0)
        layout.addWidget(QLabel("Split"), 0, 1)
        layout.addWidget(self.compare_orientation_combo, 0, 2)
        layout.addWidget(QLabel("Pane A"), 0, 3)
        layout.addWidget(self.compare_pane_a_combo, 0, 4)
        layout.addWidget(QLabel("Pane B"), 0, 5)
        layout.addWidget(self.compare_pane_b_combo, 0, 6)
        layout.addWidget(self.compare_status_label, 1, 0, 1, 7)
        return panel

    def _review_action_layout(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(self.previous_button)
        layout.addWidget(self.skip_button)
        layout.addWidget(self.include_validate_button)
        layout.addWidget(self.revalidate_button)
        layout.addStretch(1)
        layout.addWidget(self.action_summary)
        return layout

    def _build_review_bottom_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("reviewBottomPanel")
        panel.setMaximumHeight(128)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(
            self._panel_frame(
                "Warnings",
                self.warnings_panel,
                object_name="reviewWarningsFrame",
                minimum_height=96,
            ),
            1,
        )
        layout.addWidget(self._build_grid_panel(), 1)
        return panel

    def _panel_frame(
        self,
        title: str,
        content: QWidget,
        *,
        object_name: str = "",
        minimum_height: int = 104,
    ) -> QFrame:
        frame = QFrame()
        if object_name:
            frame.setObjectName(object_name)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumHeight(minimum_height)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addWidget(QLabel(title))
        layout.addWidget(content, 1)
        return frame

    def _build_layer_panel(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumHeight(220)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Layers"))
        toolbar.addStretch(1)
        toolbar.addWidget(self.edit_metadata_button)
        toolbar.addWidget(self.move_layer_up_button)
        toolbar.addWidget(self.move_layer_down_button)

        layout.addLayout(toolbar)
        layout.addWidget(self.layer_table, 1)
        layout.addWidget(self.layer_warning_label)
        return frame

    def _build_grid_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("reviewGridPanel")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumHeight(96)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(QLabel("Grid interval"))
        header.addStretch(1)
        header.addWidget(self.save_grid_button)

        fields = QHBoxLayout()
        fields.setSpacing(6)
        fields.addWidget(QLabel("Độ"))
        fields.addWidget(self.grid_degrees_input)
        fields.addWidget(QLabel("Phút"))
        fields.addWidget(self.grid_minutes_input)
        fields.addWidget(QLabel("Giây"))
        fields.addWidget(self.grid_seconds_input)
        fields.addWidget(QLabel("Scale 1:"))
        fields.addWidget(self.grid_scale_input)
        fields.addStretch(1)

        layout.addLayout(header)
        layout.addLayout(fields)
        layout.addWidget(self.grid_status_label)
        layout.addWidget(self.grid_validation_label)
        return frame

    def _apply_queue_filter(self, queue_filter: QueueFilter) -> None:
        selected_id = self._current_or_selected_composition_id()
        self.tree_model.set_queue_filter(queue_filter)
        self.tree_view.expandAll()
        self._refresh_filter_controls()
        self._restore_selection(selected_id)
        self._persist_review_session_state()

    def _refresh_filter_controls(self) -> None:
        counts = self.tree_model.filter_counts()
        for queue_filter, button in self.filter_buttons.items():
            button.setText(f"{queue_filter_label(queue_filter)} ({counts[queue_filter]})")
            button.setChecked(queue_filter == self.tree_model.active_queue_filter)

        has_visible_rows = self.tree_model.has_visible_compositions()
        active_label = queue_filter_label(self.tree_model.active_queue_filter)
        self.empty_state_label.setText(
            f"Không có composition khớp bộ lọc \"{active_label}\"."
        )
        self.empty_state_label.setVisible(not has_visible_rows)

    def _current_or_selected_composition_id(self) -> str | None:
        composition_id = self.tree_model.composition_id_for_index(self.tree_view.currentIndex())
        if composition_id is not None:
            return composition_id
        if self.selected_composition is None:
            return None
        return self.selected_composition.composition_id

    def _restore_selection(self, composition_id: str | None) -> None:
        self._restore_selection_with_signal_state(composition_id, emit=True)

    def _restore_selection_with_signal_state(
        self,
        composition_id: str | None,
        *,
        emit: bool,
    ) -> None:
        if composition_id is None:
            return

        index = self.tree_model.index_for_composition_id(composition_id)
        if index.isValid():
            selection_model = self.tree_view.selectionModel()
            previous_blocked = False
            if selection_model is not None and not emit:
                previous_blocked = selection_model.blockSignals(True)
            previous_selected_id = (
                self.selected_composition.composition_id
                if self.selected_composition is not None
                else None
            )
            try:
                self.tree_view.setCurrentIndex(index)
            finally:
                if selection_model is not None and not emit:
                    selection_model.blockSignals(previous_blocked)
            if (
                emit
                and previous_selected_id != composition_id
                and (
                    self.selected_composition is None
                    or self.selected_composition.composition_id != composition_id
                )
            ):
                self._select_composition_index(index, QModelIndex())
        else:
            self.tree_view.clearSelection()

    def _select_composition_index(self, current, _previous) -> None:  # noqa: ANN001
        composition_id = self.tree_model.composition_id_for_index(current)
        if composition_id is None or self._workspace_service is None:
            return

        try:
            composition = self._workspace_service.read_composition(composition_id)
            gate = None
            if not self._suppress_selection_validation:
                gate = self._review_gate(composition)
                composition = self._workspace_service.save_validation_summary(
                    composition_id,
                    gate.summary,
                )
        except WorkspaceError as error:
            self.action_summary.setText(f"Không tải được composition: {error}")
            return

        self.selected_composition = composition
        self._update_detail_panels(composition)
        if gate is not None:
            self._show_review_issues(gate.issues, update_action=False)
        self._persist_review_session_state()
        self.compositionSelected.emit(composition)

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._focus_needs_arrow_keys():
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key.Key_Right:
            self._include_selected()
            event.accept()
            return
        if key == Qt.Key.Key_Up:
            self._skip_selected()
            event.accept()
            return
        if key == Qt.Key.Key_Left:
            self._go_previous()
            event.accept()
            return
        super().keyPressEvent(event)

    def _focus_needs_arrow_keys(self) -> bool:
        return isinstance(QApplication.focusWidget(), QLineEdit)

    def _include_selected(self) -> None:
        if self._workspace_service is None or self.selected_composition is None:
            return

        gate = self._review_gate(self.selected_composition)
        composition_id = self.selected_composition.composition_id
        try:
            self.selected_composition = self._workspace_service.save_validation_summary(
                composition_id,
                gate.summary,
            )
        except WorkspaceError as error:
            self.action_summary.setText(f"Không lưu được validation summary: {error}")
            return
        if not gate.passed:
            self.selected_composition = self._workspace_service.read_composition(composition_id)
            self._refresh_workspace_projection(composition_id, validate_selection=False)
            self._show_review_issues(gate.issues)
            return
        try:
            updated = self._workspace_service.apply_include_transition(
                composition_id,
                validation_passed=True,
            )
        except WorkspaceError as error:
            self.action_summary.setText(f"Không include được composition: {error}")
            return

        self.selected_composition = updated
        try:
            self._persist_included_target_alignment(updated)
        except (ConfigUpdateError, WorkspaceError) as error:
            self._update_detail_panels(updated)
            self._refresh_workspace_projection(updated.composition_id, validate_selection=False)
            self.action_summary.setText(
                "Đã include composition vào workspace. Database history sẽ được cập nhật khi "
                f"Export PPTX/TXT. Nhưng không cập nhật được config target: {error}"
            )
            return
        self._advance_after_transition(updated.composition_id)
        self.action_summary.setText(
            "Đã include composition và chuyển sang mục kế tiếp nếu có. Database history sẽ được "
            "cập nhật khi Export PPTX/TXT."
        )

    def _skip_selected(self) -> None:
        if self._workspace_service is None or self.selected_composition is None:
            return

        composition_id = self.selected_composition.composition_id
        try:
            updated = self._workspace_service.apply_skip_transition(composition_id)
        except WorkspaceError as error:
            self.action_summary.setText(f"Không skip được composition: {error}")
            return

        self.selected_composition = updated
        self._advance_after_transition(updated.composition_id)
        self.action_summary.setText(
            "Đã skip composition và chuyển sang mục kế tiếp nếu có. Database history chưa thay "
            "đổi; danh sách export sẽ quyết định nội dung được ghi khi Export PPTX/TXT."
        )

    def _go_previous(self) -> None:
        if self._workspace_service is None or self.selected_composition is None:
            return

        previous_id = self.tree_model.previous_visible_composition_id(
            self.selected_composition.composition_id
        )
        if previous_id is None:
            self.action_summary.setText("Không có composition trước đó trong queue.")
            self._update_review_action_state()
            return

        self._refresh_workspace_projection(previous_id)
        self.action_summary.setText(
            "Đã quay lại composition trước đó. Database history không thay đổi vì đây "
            "chỉ là thao tác điều hướng."
        )

    def _revalidate_selected(self) -> None:
        if self._workspace_service is None or self.selected_composition is None:
            return

        gate = self._review_gate(self.selected_composition)
        try:
            updated = self._workspace_service.save_validation_summary(
                self.selected_composition.composition_id,
                gate.summary,
            )
        except WorkspaceError as error:
            self.action_summary.setText(f"Không revalidate được composition: {error}")
            return

        if not gate.passed:
            self.selected_composition = updated
            self._refresh_workspace_projection(updated.composition_id, validate_selection=False)
            self._show_review_issues(gate.issues)
            return

        self.selected_composition = updated
        self._update_detail_panels(updated)
        self._refresh_workspace_projection(updated.composition_id, validate_selection=False)
        self.action_summary.setText("Validation gate hiện tại đã pass.")

    def _review_gate(self, composition: Composition) -> ValidationResult:
        return validate_composition_readiness(self._validation_context_for(composition))

    def _validation_context_for(self, composition: Composition) -> ValidationContext:
        target = self._target_for_composition(composition)
        template_metadata: TemplateMetadata | None = None
        template_error: str | None = None
        if target is not None:
            try:
                template_metadata = template_metadata_for_composition(target, composition)
            except Exception as error:  # noqa: BLE001
                template_error = str(error)
        if (
            template_metadata is None
            and target is not None
            and isinstance(target.metadata.get("map_frame"), dict)
        ):
            frame = dict(target.metadata["map_frame"])
            frame.setdefault("x", 0)
            frame.setdefault("y", 0)
            try:
                template_metadata = TemplateMetadata.model_validate(
                    {
                        "template_pptx": template_pptx_file_for_composition(
                            target,
                            composition,
                        ),
                        "slide_index": 0,
                        "map_frame": frame,
                    }
                )
            except Exception as error:  # noqa: BLE001
                template_error = str(error)
        return ValidationContext(
            target=target,
            composition=composition,
            template_metadata=template_metadata,
            template_metadata_error=template_error,
        )

    def _target_for_composition(self, composition: Composition) -> TargetConfig | None:
        for target in self._targets or []:
            if target.id == composition.target_id:
                return target
        return None

    def _request_canvas_render(self, composition: Composition) -> None:
        """Build a RenderSpec and submit a background render for the GIS canvas."""
        if self._render_threads:
            self._cancel_render()
        self._pending_canvas_render_composition = None
        visible = [layer for layer in composition.layers if layer.visible]
        if not visible:
            return
        target = self._target_for_composition(composition)
        if target is None:
            return
        if self._workspace_service is None:
            return
        context = self._validation_context_for(composition)
        if context.template_metadata is None:
            return
        render_composition = self._workspace_service.resolve_composition_layer_paths(composition)
        compare_compositions = self._resolved_compare_compositions_for_render(composition)
        raster_sources = compare_compositions if compare_compositions else [render_composition]
        if not all(_has_existing_visible_raster(item) for item in raster_sources):
            self.gis_canvas.set_error("Không tìm thấy file raster visible để render canvas.")
            return
        canvas_width, canvas_height = final_render_output_size(
            context.template_metadata,
            final_dpi=target.export.final_render_dpi,
        )
        try:
            spec = build_render_spec(
                composition=render_composition,
                target=target,
                template=context.template_metadata,
                template_metadata_file=template_pptx_file_for_composition(
                    target,
                    composition,
                ),
                output_width=canvas_width,
                output_height=canvas_height,
                compare_compositions=compare_compositions,
            )
        except (RenderSpecError, ValidationError) as error:
            self.gis_canvas.set_error(_render_spec_error_message(error))
            return
        self._canvas_render_epoch += 1
        request = PreviewRenderRequest(
            job_id=(
                f"canvas:{composition.composition_id}:"
                f"{self.gis_canvas.generation}:{self._canvas_render_epoch}"
            ),
            composition_id=composition.composition_id,
            revision=self.gis_canvas.generation,
            quality=PreviewRenderQuality.SETTLED_HIGH_RES,
            spec=spec,
        )
        token = self.gis_canvas.set_loading("Đang render preview...")
        self._start_canvas_render(request, token)

    def _start_canvas_render(self, request: PreviewRenderRequest, token: object) -> None:
        if self._render_preview_config.tile_preview.enabled:
            self._start_tile_canvas_render(request, token)
            return
        thread = QThread(self)
        worker = RenderWorker(request, render=self._render_canvas_map)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_canvas_render_result)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda job_id=request.job_id: self._clear_canvas_render_worker(job_id)
        )
        self._render_threads[request.job_id] = thread
        self._render_workers[request.job_id] = worker
        self._render_tokens[request.job_id] = token
        thread.start()

    def _start_tile_canvas_render(self, request: PreviewRenderRequest, token: object) -> None:
        tile_config = self._render_preview_config.tile_preview
        thread = QThread(self)
        worker = TilePreviewWorker(
            request,
            tile_cache=self._canvas_tile_cache,
            tile_scheduler=TileScheduler(cache=self._canvas_tile_cache),
            render_cache=self._canvas_render_cache,
            previous_state=self._canvas_tile_state,
            settings=_tile_preview_settings(tile_config),
            fallback_to_full_render=tile_config.fallback_to_full_render,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.frameReady.connect(self._handle_canvas_render_progress)
        worker.finished.connect(self._handle_canvas_render_result)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda job_id=request.job_id: self._clear_canvas_render_worker(job_id)
        )
        self._render_threads[request.job_id] = thread
        self._render_workers[request.job_id] = worker
        self._render_tokens[request.job_id] = token
        thread.start()

    def _render_canvas_map(self, spec, *, is_cancelled=None, diagnostics=None):  # noqa: ANN001
        tile_config = self._render_preview_config.tile_preview
        if tile_config.enabled:
            try:
                result, tile_state = render_tile_preview_map(
                    spec,
                    tile_cache=self._canvas_tile_cache,
                    tile_scheduler=self._canvas_tile_scheduler,
                    render_cache=self._canvas_render_cache,
                    previous_state=self._canvas_tile_state,
                    settings=_tile_preview_settings(tile_config),
                    is_cancelled=is_cancelled,
                    diagnostics=diagnostics,
                )
                self._canvas_tile_state = tile_state
                return result
            except Exception:  # noqa: BLE001 - tile preview must safely fall back.
                self._canvas_tile_state = TilePreviewState()
                if not tile_config.fallback_to_full_render:
                    raise
        return render_map_with_cache(
            spec,
            render_cache=self._canvas_render_cache,
            is_cancelled=is_cancelled,
            diagnostics=diagnostics,
        )

    def _set_render_preview_config(
        self,
        config: RenderPreviewConfig | None,
    ) -> None:
        self._render_preview_config = config or RenderPreviewConfig()
        if hasattr(self, "gis_canvas"):
            self.gis_canvas.set_live_preview_max_fps(
                self._render_preview_config.tile_preview.live_preview_max_fps
            )
        self._canvas_tile_cache = TileCache(
            max_bytes=self._render_preview_config.tile_preview.max_cache_bytes
        )
        self._canvas_tile_scheduler = TileScheduler(cache=self._canvas_tile_cache)
        self._canvas_tile_state = TilePreviewState()

    def _reset_tile_preview_state(self) -> None:
        self._canvas_tile_cache.clear()
        self._canvas_tile_scheduler = TileScheduler(cache=self._canvas_tile_cache)
        self._canvas_tile_state = TilePreviewState()

    def _refresh_canvas_render(self) -> None:
        """Force a clean render of the currently selected GIS canvas."""
        if self.selected_composition is None or self._workspace_service is None:
            return
        self._pending_canvas_render_composition = None
        self._cancel_render()
        self._canvas_render_cache.clear()
        self._reset_tile_preview_state()

        self._flush_pending_canvas_view(request_render=False)
        composition = self.selected_composition
        if composition is None:
            return
        self._request_canvas_render(composition)
        self.action_summary.setText("Da yeu cau render lai GIS canvas.")

    def _resolved_compare_compositions_for_render(
        self,
        composition: Composition,
    ) -> list[Composition]:
        if self._workspace_service is None or not composition.temporal_compare.enabled:
            return []
        state = composition.temporal_compare
        pane_ids = [state.pane_a_composition_id, state.pane_b_composition_id]
        if not all(pane_ids):
            return []
        resolved: list[Composition] = []
        for pane_id in pane_ids:
            try:
                pane = self._workspace_service.read_composition(str(pane_id))
            except WorkspaceError:
                return []
            resolved.append(self._workspace_service.resolve_composition_layer_paths(pane))
        return resolved

    def _request_target_preview(self, composition: Composition) -> None:
        """Build a full-coverage target preview and render it in a background thread."""
        self._cancel_target_render()
        target = self._target_for_composition(composition)
        if target is None or self._workspace_service is None:
            return

        render_composition = self._workspace_service.resolve_composition_layer_paths(composition)
        context = self._validation_context_for(composition)
        try:
            spec = build_target_preview_spec(
                composition=render_composition,
                target=target,
                template=context.template_metadata,
                template_metadata_file=template_pptx_file_for_composition(
                    target,
                    composition,
                ),
                output_width=self.target_preview.render_width(),
                output_height=self.target_preview.render_height(),
            )
            self.target_preview.set_preview_geo_window(
                (
                    spec.geo_window.min_lon,
                    spec.geo_window.min_lat,
                    spec.geo_window.max_lon,
                    spec.geo_window.max_lat,
                )
            )
            self._sync_target_preview_viewport_overlays()
        except (RenderSpecError, ValidationError) as error:
            token = self.target_preview.begin_render_request()
            self.target_preview.set_error(token, str(error))
            return

        request = PreviewRenderRequest(
            job_id=(
                "target-preview:"
                f"{composition.target_id}:{composition.capture_date.isoformat()}"
            ),
            composition_id=composition.composition_id,
            revision=self.target_preview.generation,
            quality=PreviewRenderQuality.SETTLED_HIGH_RES,
            spec=spec,
        )
        self._target_render_token = self.target_preview.set_loading()
        thread = QThread(self)
        worker = RenderWorker(request, render=render_raster_layers)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_target_preview_render_result)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_target_render_worker)
        self._target_render_thread = thread
        self._target_render_worker = worker
        thread.start()

    @Slot(object)
    def _handle_canvas_render_progress(self, result: PreviewRenderJobResult) -> None:
        token = self._render_tokens.get(result.job_id)
        if token is None:
            return
        self._apply_canvas_render(result, token)

    @Slot(object)
    def _handle_canvas_render_result(self, result: PreviewRenderJobResult) -> None:
        token = self._render_tokens.get(result.job_id)
        if token is None:
            return
        self._apply_canvas_render(result, token)

    def _apply_canvas_render(self, result: PreviewRenderJobResult, token: object) -> None:
        if result.state in {JobState.SUCCESS, JobState.WARNING} and result.canvas is not None:
            if isinstance(result.tile_preview_state, TilePreviewState):
                self._canvas_tile_state = result.tile_preview_state
            self.gis_canvas.apply_render_result(token, result.message, canvas=result.canvas)
        elif result.state == JobState.ERROR:
            self.gis_canvas.set_error(result.message)

    def _handle_canvas_view_interaction(self, *_args) -> None:  # noqa: ANN002
        self._sync_target_preview_viewport_overlays()
        if self._render_preview_config.tile_preview.cancel_on_interaction:
            self._cancel_render()

    @Slot(object)
    def _handle_target_preview_render_result(self, result: PreviewRenderJobResult) -> None:
        token = self._target_render_token
        if token is None:
            return
        self._apply_target_preview_render(result, token)

    def _apply_target_preview_render(
        self,
        result: PreviewRenderJobResult,
        token: TargetPreviewRequestToken,
    ) -> None:
        if result.state in {JobState.SUCCESS, JobState.WARNING} and result.canvas is not None:
            self.target_preview.apply_render_result(
                token,
                result.message,
                canvas=result.canvas,
                issue_count=len(result.issues),
            )
        elif result.state == JobState.ERROR:
            self.target_preview.set_error(token, result.message)

    def _cancel_render(self, *, wait: bool = False) -> None:
        self._render_tokens.clear()
        for worker in list(self._render_workers.values()):
            worker.cancel()
        if not wait:
            return
        for job_id, thread in list(self._render_threads.items()):
            if thread.isRunning():
                thread.quit()
                if not thread.wait(2000):
                    continue
            self._clear_canvas_render_worker(job_id)

    def _cancel_target_render(self) -> None:
        if self._target_render_thread is not None and self._target_render_thread.isRunning():
            if self._target_render_worker is not None:
                self._target_render_worker.cancel()
            self._target_render_thread.quit()
            self._target_render_thread.wait(2000)
        self._target_render_thread = None
        self._target_render_worker = None
        self._target_render_token = None

    def _clear_canvas_render_worker(self, job_id: str) -> None:
        self._render_threads.pop(job_id, None)
        self._render_workers.pop(job_id, None)
        self._render_tokens.pop(job_id, None)
        if self._render_threads:
            return
        pending = self._pending_canvas_render_composition
        if pending is None:
            return
        self._pending_canvas_render_composition = None
        QTimer.singleShot(0, lambda composition=pending: self._request_canvas_render(composition))

    def _clear_target_render_worker(self) -> None:
        self._target_render_thread = None
        self._target_render_worker = None
        self._target_render_token = None

    def _show_review_issues(
        self,
        issues: tuple[Issue, ...],
        *,
        update_action: bool = True,
    ) -> None:
        composition = self.selected_composition
        comp_id = composition.composition_id if composition is not None else ""
        target_id = composition.target_id if composition is not None else ""
        self.warnings_panel.set_issues(issues, composition_id=comp_id, target_id=target_id)
        self.layer_model.set_issues(issues)
        if update_action and any(issue.blocking for issue in issues):
            self.action_summary.setText("Không include: cần xử lý lỗi blocking trước.")

    def _handle_issue_jump(self, target_id: str, composition_id: str, layer_id: str) -> None:
        if composition_id:
            index = self.tree_model.index_for_composition_id(composition_id)
            if not index.isValid() and self._workspace_service is not None:
                try:
                    self._workspace_service.read_composition(composition_id)
                except WorkspaceError:
                    pass
                else:
                    self.tree_model.set_queue_filter(QueueFilter.ALL)
                    self.tree_view.expandAll()
                    self._refresh_filter_controls()
                    index = self.tree_model.index_for_composition_id(composition_id)
            if index.isValid():
                self.tree_view.setCurrentIndex(index)
                if layer_id and not self._select_layer_by_id(layer_id):
                    self.action_summary.setText("Tham chiếu không còn tồn tại.")
            else:
                self.action_summary.setText("Tham chiếu không còn tồn tại.")
        elif target_id:
            index = self.tree_model.index_for_target_id(target_id)
            if not index.isValid():
                self.tree_model.set_queue_filter(QueueFilter.ALL)
                self.tree_view.expandAll()
                self._refresh_filter_controls()
                index = self.tree_model.index_for_target_id(target_id)
            if index.isValid():
                self.tree_view.setCurrentIndex(index)
            else:
                self.action_summary.setText("Tham chiếu không còn tồn tại.")

    def _select_layer_by_id(self, layer_id: str) -> bool:
        for row in range(self.layer_model.rowCount()):
            if self.layer_model.layer_id_for_index(self.layer_model.index(row, 0)) == layer_id:
                index = self.layer_model.index(row, 0)
                self.layer_table.setCurrentIndex(index)
                self.layer_table.selectRow(row)
                return True
        return False

    def _update_metadata_edit_button(self, *_args) -> None:  # noqa: ANN002
        layer_id = self.layer_model.layer_id_for_index(self.layer_table.currentIndex())
        self.edit_metadata_button.setEnabled(
            layer_id is not None
            and self._workspace_service is not None
            and self.selected_composition is not None
        )

    def _current_layer(self) -> ImageLayer | None:
        if self.selected_composition is None:
            return None
        layer_id = self.layer_model.layer_id_for_index(self.layer_table.currentIndex())
        if layer_id is None:
            return None
        for layer in self.selected_composition.layers:
            if layer.layer_id == layer_id:
                return layer
        return None

    def _layer_by_id(self, layer_id: str) -> ImageLayer | None:
        if self.selected_composition is None:
            return None
        for layer in self.selected_composition.layers:
            if layer.layer_id == layer_id:
                return layer
        return None

    def _open_metadata_editor(self) -> None:
        layer = self._current_layer()
        if layer is None or self._workspace_service is None or self.selected_composition is None:
            return
        dialog = MetadataEditorDialog(layer, parent=self)
        dialog.metadataSaved.connect(self._apply_layer_metadata)
        dialog.exec()

    def _apply_layer_metadata(self, layer_id: str, payload: dict) -> None:
        if self._workspace_service is None or self.selected_composition is None:
            return
        current_layer = self._current_layer()
        if current_layer is None or current_layer.layer_id != layer_id:
            current_layer = self._layer_by_id(layer_id)
            if current_layer is not None:
                self._select_layer_by_id(layer_id)
        if current_layer is None or current_layer.layer_id != layer_id:
            self.action_summary.setText("Không tìm thấy layer đang chọn để lưu metadata.")
            return
        composition_id = self.selected_composition.composition_id
        target_id = self.selected_composition.target_id
        source_value = payload.get("source_path")
        source_path = str(source_value).strip() if source_value else current_layer.source_path
        source_changed = source_path != current_layer.source_path
        try:
            payload, source_update_message = self._prepare_source_path_payload(
                current_layer,
                payload,
                source_path,
            )
        except (OSError, ValueError) as error:
            self.action_summary.setText(f"Không cập nhật được file nguồn: {error}")
            return
        history_message = None
        new_date = payload.get("capture_date")
        candidate_id = (
            f"{target_id}__{new_date.strftime('%Y%m%d')}" if new_date is not None else None
        )

        if candidate_id is not None and candidate_id != composition_id:
            confirmed = self._confirm_date_change(layer_id, composition_id, candidate_id)
            if not confirmed:
                self.action_summary.setText("Đã hủy đổi ngày; metadata không được lưu.")
                return
            try:
                payload, cache_message = self._activate_source_path_payload(
                    current_layer,
                    payload,
                    source_path,
                )
                if cache_message is not None:
                    source_update_message = cache_message
                history_message = self._repair_historical_source_path(
                    current_layer,
                    source_path,
                    payload,
                )
                updated_source, updated_dest = (
                    self._workspace_service.move_layer_between_compositions(
                        composition_id,
                        layer_id,
                        new_composition_id=candidate_id,
                        new_target_id=target_id,
                        new_capture_date=new_date,
                        capture_time=payload["capture_time"],
                        cloud_percent=payload["cloud_percent"],
                        metadata_source=payload["metadata_source"],
                        metadata_status=payload["metadata_status"],
                        source_path=source_path,
                        cache_path=payload.get("cache_path"),
                    )
                )
            except (
                HistoryRecordError,
                WorkspaceError,
                ValidationError,
                OSError,
                ValueError,
            ) as error:
                self._rollback_historical_source_path(current_layer, source_path)
                self.action_summary.setText(
                    f"Không di chuyển được layer: {error} "
                    "Vui lòng kiểm tra composition JSON/workspace rồi thử lại."
                )
                return

            self.selected_composition = updated_dest
            self._refresh_workspace_projection(
                updated_dest.composition_id, validate_selection=False
            )
            self.action_summary.setText(
                f"Đã chuyển layer sang {updated_dest.composition_id}; "
                f"cả hai composition cần revalidate."
                f"{_summary_suffix(source_update_message)}{_summary_suffix(history_message)}"
            )
            if source_changed:
                self._request_canvas_render(updated_dest)
            return

        try:
            payload, cache_message = self._activate_source_path_payload(
                current_layer,
                payload,
                source_path,
            )
            if cache_message is not None:
                source_update_message = cache_message
            history_message = self._repair_historical_source_path(
                current_layer,
                source_path,
                payload,
            )
            updated = self._workspace_service.update_layer_metadata(
                composition_id,
                layer_id,
                source_path=source_path,
                capture_date=payload["capture_date"],
                capture_time=payload["capture_time"],
                cloud_percent=payload["cloud_percent"],
                metadata_source=payload["metadata_source"],
                metadata_status=payload["metadata_status"],
                cache_path=payload.get("cache_path"),
            )
        except (
            HistoryRecordError,
            WorkspaceError,
            ValidationError,
            OSError,
            ValueError,
        ) as error:
            self._rollback_historical_source_path(current_layer, source_path)
            self.action_summary.setText(f"Không lưu được metadata: {error}")
            return

        self.selected_composition = updated
        self._update_detail_panels(updated)
        self._refresh_workspace_projection(updated.composition_id, validate_selection=False)
        if source_changed:
            self._request_canvas_render(updated)
        self.action_summary.setText(
            f"Đã lưu metadata/source path; composition cần revalidate."
            f"{_summary_suffix(source_update_message)}{_summary_suffix(history_message)}"
        )

    def _prepare_source_path_payload(
        self,
        layer: ImageLayer,
        payload: dict,
        source_path: str,
    ) -> tuple[dict, str | None]:
        if source_path == layer.source_path:
            return dict(payload), None
        if self._workspace_service is None or self.selected_composition is None:
            return dict(payload), None

        scanned = scan_geotiff_file(source_path)
        updates = dict(payload)
        for field_name in ("capture_date", "capture_time", "cloud_percent"):
            parsed_value = getattr(scanned.layer, field_name)
            if parsed_value is not None:
                updates[field_name] = parsed_value
        if scanned.layer.metadata_source is not MetadataSource.UNKNOWN:
            updates["metadata_source"] = scanned.layer.metadata_source
        else:
            updates["metadata_source"] = updates.get("metadata_source", MetadataSource.MANUAL)
        updates["metadata_status"] = (
            MetadataStatus.VALID
            if updates.get("capture_date") is not None and updates.get("capture_time") is not None
            else MetadataStatus.NEEDS_MANUAL_CORRECTION
        )
        cache_candidate = layer.model_copy(
            update={
                "source_path": source_path,
                "capture_date": updates.get("capture_date"),
                "capture_time": updates.get("capture_time"),
                "cloud_percent": updates.get("cloud_percent"),
                "metadata_source": updates["metadata_source"],
                "metadata_status": updates["metadata_status"],
            }
        )
        updates["_cache_candidate"] = cache_candidate
        updates["_scanned_source_path"] = scanned.path
        updates["source_path"] = str(scanned.path)
        return updates, "Đã validate file mới và đọc metadata từ file nguồn."

    def _activate_source_path_payload(
        self,
        layer: ImageLayer,
        payload: dict,
        source_path: str,
    ) -> tuple[dict, str | None]:
        if source_path == layer.source_path:
            return dict(payload), None
        if self._workspace_service is None or self.selected_composition is None:
            return dict(payload), None

        updates = dict(payload)
        cache_candidate = updates.pop("_cache_candidate", None)
        scanned_source_path = updates.pop("_scanned_source_path", None)
        if not isinstance(cache_candidate, ImageLayer) or scanned_source_path is None:
            return updates, None
        cached_layer = cache_layer_source(
            workspace_service=self._workspace_service,
            target_id=self.selected_composition.target_id,
            source_path=scanned_source_path,
            layer=cache_candidate,
            overwrite_existing=True,
        )
        updates["source_path"] = cached_layer.source_path
        updates["cache_path"] = cached_layer.cache_path
        return updates, f"Đã validate file mới và cập nhật cache: {cached_layer.cache_path}."

    def _repair_historical_source_path(
        self,
        layer: ImageLayer,
        source_path: str,
        payload: dict,
    ) -> str | None:
        if source_path == layer.source_path:
            return None
        if layer.source_kind is not ImageLayerSourceKind.HISTORICAL:
            return None
        if layer.image_asset_id is None:
            return "SQLite history chưa cập nhật vì layer historical cũ thiếu image_asset_id."
        if not self._history_service.enabled:
            return "SQLite history chưa cập nhật vì historical registry đang tắt."

        self._history_service.repair_image_path(
            layer.image_asset_id,
            source_path,
            capture_date=payload.get("capture_date"),
            capture_time=payload.get("capture_time"),
            cloud_percent=payload.get("cloud_percent"),
        )
        return f"SQLite history đã cập nhật image_asset_id={layer.image_asset_id}."

    def _rollback_historical_source_path(self, layer: ImageLayer, source_path: str) -> None:
        if (
            source_path == layer.source_path
            or layer.source_kind is not ImageLayerSourceKind.HISTORICAL
            or layer.image_asset_id is None
            or not self._history_service.enabled
        ):
            return
        try:
            self._history_service.repair_image_path(
                layer.image_asset_id,
                layer.source_path,
                capture_date=layer.capture_date,
                capture_time=layer.capture_time,
                cloud_percent=layer.cloud_percent,
            )
        except HistoryRecordError:
            return

    def _confirm_date_change(
        self,
        layer_id: str,
        source_composition_id: str,
        new_composition_id: str,
    ) -> bool:
        """Hook for confirmation dialog; overridable by tests to bypass modal exec."""
        return confirm_date_change_dialog(
            layer_id, source_composition_id, new_composition_id, parent=self
        )

    def _advance_after_transition(self, composition_id: str) -> None:
        next_id = None
        if self._workspace_service is not None:
            next_id = self.tree_model.next_visible_composition_id(composition_id)
        self._refresh_workspace_projection(next_id or composition_id)

    def _update_review_action_state(self) -> None:
        has_selection = (
            self.selected_composition is not None and self._workspace_service is not None
        )
        previous_available = False
        if has_selection and self._workspace_service is not None and self.selected_composition:
            previous_available = (
                self.tree_model.previous_visible_composition_id(
                    self.selected_composition.composition_id
                )
                is not None
            )

        self.previous_button.setEnabled(previous_available)
        self.skip_button.setEnabled(has_selection)
        self.include_validate_button.setEnabled(has_selection)
        self.refresh_canvas_button.setEnabled(has_selection)
        self.export_canvas_button.setEnabled(has_selection)
        self.revalidate_button.setEnabled(
            has_selection
            and self.selected_composition is not None
            and self.selected_composition.needs_revalidation
        )
        if not has_selection:
            self.action_summary.setText("Chọn composition để dùng review actions.")
        elif self.selected_composition is not None and self.selected_composition.needs_revalidation:
            self.action_summary.setText(
                "Composition cần revalidate trước hoặc trong Include/Validate."
            )
        else:
            self.action_summary.setText("Sẵn sàng: Include/Validate là action chính.")

    def _persist_layer_visibility(self, top_left, bottom_right, roles) -> None:  # noqa: ANN001
        if (
            top_left.column() != int(LayerStackColumn.VISIBILITY)
            or bottom_right.column() != int(LayerStackColumn.VISIBILITY)
            or self._workspace_service is None
            or self.layer_model.composition_id is None
        ):
            return

        layer_id = self.layer_model.layer_id_for_index(top_left)
        if layer_id is None:
            return

        try:
            updated = self._workspace_service.set_layer_visibility(
                self.layer_model.composition_id,
                layer_id,
                visible=self.layer_model.visible_for_row(top_left.row()),
            )
        except WorkspaceError as error:
            self.action_summary.setText(f"Không lưu được layer: {error}")
            if self.selected_composition is not None:
                self.layer_model.set_composition(self.selected_composition)
            return

        self.selected_composition = updated
        self._update_detail_panels(updated)
        self._refresh_workspace_projection(updated.composition_id, validate_selection=False)

    def _move_selected_layer(self, offset: int) -> None:
        if self._workspace_service is None or self.layer_model.composition_id is None:
            return

        layer_id = self.layer_model.layer_id_for_index(self.layer_table.currentIndex())
        if layer_id is None:
            return

        ordered_layer_ids = self.layer_model.move_layer(layer_id, offset)
        if ordered_layer_ids is None:
            return

        try:
            updated = self._workspace_service.reorder_layers(
                self.layer_model.composition_id,
                ordered_layer_ids,
            )
        except WorkspaceError as error:
            self.action_summary.setText(f"Không lưu được thứ tự layer: {error}")
            return

        self.selected_composition = updated
        self._update_detail_panels(updated)
        self._refresh_workspace_projection(updated.composition_id, validate_selection=False)
        new_row = max(0, self.layer_table.currentIndex().row() + offset)
        new_index = self.layer_model.index(new_row, 0)
        if new_index.isValid():
            self.layer_table.setCurrentIndex(new_index)

    def _persist_canvas_view(self, center: list[float], scale: int) -> None:
        if self.selected_composition is None:
            return
        self._pending_canvas_view = (
            "composition",
            self.selected_composition.composition_id,
            list(center),
            scale,
        )
        self._sync_target_preview_viewport_overlays()
        self._canvas_view_persist_timer.start(self._canvas_view_debounce_ms())

    def _persist_compare_pane_view(self, pane: str, center: list[float]) -> None:
        if self.selected_composition is None:
            return
        self._pending_canvas_view = ("compare_pane", pane, list(center), None)
        self._sync_target_preview_viewport_overlays()
        self._canvas_view_persist_timer.start(self._canvas_view_debounce_ms())

    def _canvas_view_debounce_ms(self) -> int:
        return max(
            0,
            int(self._render_preview_config.tile_preview.interaction_render_debounce_ms),
        )

    def _flush_pending_canvas_view(self, *, request_render: bool = True) -> None:
        pending = self._pending_canvas_view
        self._pending_canvas_view = None
        self._canvas_view_persist_timer.stop()
        if pending is None:
            return
        if self._workspace_service is None or self.selected_composition is None:
            return

        kind, identifier, center, scale = pending
        selected_id = self.selected_composition.composition_id
        if kind == "compare_pane":
            try:
                updated = self._workspace_service.update_temporal_compare_pane_view(
                    selected_id,
                    pane=identifier,
                    center=center,
                )
            except (WorkspaceError, ValidationError) as error:
                self.action_summary.setText(f"KhÃ´ng lÆ°u Ä‘Æ°á»£c compare pane: {error}")
                self.gis_canvas.set_composition(self.selected_composition)
                self._load_canvas_compare_context(self.selected_composition)
                return

            self.selected_composition = updated
            self._update_detail_panels(updated, preserve_canvas_render=True)
            self._replace_workspace_projection_composition(updated)
            if request_render:
                self._request_canvas_render(updated)
            return

        composition_id = identifier
        if scale is None:
            return
        try:
            updated = self._workspace_service.update_view_state(
                composition_id,
                center=center,
                scale=scale,
            )
        except (WorkspaceError, ValidationError) as error:
            self.action_summary.setText(f"Không lưu được view canvas: {error}")
            self.gis_canvas.set_composition(self.selected_composition)
            return

        if composition_id == selected_id:
            self.selected_composition = updated
            self._update_detail_panels(updated, preserve_canvas_render=True)
            self._replace_workspace_projection_composition(updated)
            if request_render:
                self._request_canvas_render(updated)
            return

        self._replace_workspace_projection_row(updated)
        try:
            selected = self._workspace_service.mark_needs_revalidation(selected_id)
        except WorkspaceError as error:
            self.action_summary.setText(f"KhÃ´ng Ä‘Ã¡nh dáº¥u stale cho compare: {error}")
            return

        self.selected_composition = selected
        self._update_detail_panels(selected, preserve_canvas_render=True)
        self._replace_workspace_projection_composition(selected)
        if request_render:
            self._request_canvas_render(selected)

    def _replace_workspace_projection_row(self, composition: Composition) -> None:
        if not self.tree_model.replace_composition(composition):
            self._refresh_workspace_projection(
                self.selected_composition.composition_id
                if self.selected_composition is not None
                else composition.composition_id,
                validate_selection=False,
            )
            return
        self.tree_view.expandAll()
        self._refresh_filter_controls()

    def _replace_workspace_projection_composition(self, composition: Composition) -> None:
        if not self.tree_model.replace_composition(composition):
            self._refresh_workspace_projection(composition.composition_id, validate_selection=False)
            return
        self.tree_view.expandAll()
        self._refresh_filter_controls()
        self._restore_selection_with_signal_state(composition.composition_id, emit=False)

    def _persist_included_target_alignment(self, composition: Composition) -> None:
        if self._workspace_service is None:
            return
        grid, _source = self._effective_grid_for_composition(composition)
        manifest = self._workspace_service.load_manifest()
        updated_target = update_target_alignment_defaults(
            manifest.config_path,
            target_id=composition.target_id,
            coordinate=composition.view.center,
            interval=grid.interval,
            scale=composition.view.scale,
        )
        self._sync_target_alignment_in_memory(updated_target)

    def _sync_target_alignment_in_memory(self, updated_target: TargetConfig) -> None:
        if self._targets is None:
            return
        self._targets = [
            target.model_copy(
                update={
                    "coordinate": updated_target.coordinate,
                    "scale": updated_target.scale,
                    "grid": updated_target.grid,
                }
            )
            if target.id == updated_target.id
            else target
            for target in self._targets
        ]

    def _save_grid_override(self) -> None:
        if self._workspace_service is None or self.selected_composition is None:
            return

        try:
            grid = self._grid_from_inputs()
            scale = self._scale_from_input()
            updated = self._workspace_service.update_grid_override(
                self.selected_composition.composition_id,
                degrees=grid.interval.degrees,
                minutes=grid.interval.minutes,
                seconds=grid.interval.seconds,
                label_format=grid.label_format,
                style=grid.style,
            )
            if scale != updated.view.scale:
                updated = self._workspace_service.update_view_state(
                    updated.composition_id,
                    center=list(updated.view.center),
                    scale=scale,
                )
        except ValueError as error:
            self.grid_validation_label.setText(str(error))
            return
        except (WorkspaceError, ValidationError) as error:
            self.grid_validation_label.setText(f"Không lưu được grid: {error}")
            return

        self.selected_composition = updated
        try:
            self._persist_included_target_alignment(updated)
        except (ConfigUpdateError, WorkspaceError) as error:
            self._update_detail_panels(updated)
            self._refresh_workspace_projection(updated.composition_id, validate_selection=False)
            self.grid_validation_label.setText(
                f"Đã lưu grid composition, nhưng không cập nhật được config target: {error}"
            )
            return
        self._update_detail_panels(updated)
        self._refresh_workspace_projection(updated.composition_id, validate_selection=False)
        self._request_canvas_render(updated)
        self.action_summary.setText("Đã lưu grid và cập nhật config target.")

    def _export_canvas_image(self) -> None:
        if self._workspace_service is None or self.selected_composition is None:
            self.action_summary.setText("Chọn composition trước khi xuất ảnh GIS editor.")
            return

        output_path = self._select_canvas_export_path(self._default_canvas_export_path())
        if output_path is None:
            self.action_summary.setText("Đã hủy xuất ảnh GIS editor.")
            return

        try:
            saved = self.gis_canvas.export_displayed_image(output_path)
        except OSError as error:
            self.action_summary.setText(f"Không xuất được ảnh GIS editor: {error}")
            return

        if saved:
            self.action_summary.setText(f"Đã xuất ảnh GIS editor: {output_path}")
        else:
            self.action_summary.setText("Không xuất được ảnh GIS editor.")

    def _default_canvas_export_path(self) -> Path:
        if self._workspace_service is None or self.selected_composition is None:
            return Path("gis-editor.jpg")
        return (
            self._workspace_service.paths.renders
            / f"{self.selected_composition.composition_id}.gis-editor.jpg"
        )

    def _select_canvas_export_path(self, default_path: Path) -> Path | None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Xuất ảnh GIS editor",
            str(default_path),
            "JPEG image (*.jpg *.jpeg)",
        )
        if not path:
            return None
        selected = Path(path)
        if selected.suffix.lower() not in {".jpg", ".jpeg"}:
            selected = selected.with_suffix(".jpg")
        return selected

    def _refresh_workspace_projection(
        self,
        selected_id: str | None,
        *,
        validate_selection: bool = True,
    ) -> None:
        if self._workspace_service is None:
            return

        self.tree_model.set_compositions(
            self._workspace_service.list_compositions(),
            targets=self._targets,
        )
        self.tree_view.expandAll()
        self._refresh_filter_controls()
        previous_suppression = self._suppress_selection_validation
        self._suppress_selection_validation = not validate_selection
        try:
            self._restore_selection(selected_id)
        finally:
            self._suppress_selection_validation = previous_suppression

    def _update_detail_panels(
        self,
        composition: Composition,
        *,
        preserve_canvas_render: bool = False,
    ) -> None:
        self.composition_title.setText(
            f"{composition.composition_id} | {composition.capture_date.isoformat()}"
        )
        self.layer_model.set_composition(composition)
        self._restore_layer_selection_from_session(composition)
        self.layer_warning_label.setVisible(self.layer_model.has_no_visible_layers())
        self._update_metadata_edit_button()
        target_preview_needs_render = self.target_preview.set_composition(composition)
        map_frame_size = self._map_frame_size_for_composition(composition)
        if map_frame_size is not None:
            self.gis_canvas.set_map_frame_size(*map_frame_size)
        effective_grid, _source = self._effective_grid_for_composition(composition)
        self.gis_canvas.set_map_surround_style(effective_grid.style)
        previous_compare_state = composition.temporal_compare
        composition = self._load_temporal_compare_controls(composition)
        compare_state_synced = composition.temporal_compare != previous_compare_state
        self.selected_composition = composition
        self.gis_canvas.set_composition(
            composition,
            preserve_render=preserve_canvas_render,
        )
        self._load_canvas_compare_context(composition)
        self._sync_target_preview_viewport_overlays()
        self._load_grid_controls(composition)
        self.warnings_panel.set_issues(
            (),
            composition_id=composition.composition_id,
            target_id=composition.target_id,
        )
        self._update_review_action_state()
        if target_preview_needs_render:
            self._request_target_preview(composition)
        if not composition.needs_revalidation or compare_state_synced:
            self._request_canvas_render(composition)

    def _restore_layer_selection_from_session(self, composition: Composition) -> None:
        if self._workspace_service is None:
            return
        try:
            state = self._workspace_service.load_session_state()
        except WorkspaceError:
            return
        review = state.review
        if review.selected_composition_id != composition.composition_id:
            return
        layer_id = review.selected_layer_id
        if layer_id:
            self._select_layer_by_id(layer_id)

    def _load_canvas_compare_context(self, composition: Composition) -> None:
        if self._workspace_service is None or not composition.temporal_compare.enabled:
            self.gis_canvas.set_compare_context(composition, pane_a=None, pane_b=None)
            return
        state = composition.temporal_compare
        if not state.pane_a_composition_id or not state.pane_b_composition_id:
            self.gis_canvas.set_compare_context(composition, pane_a=None, pane_b=None)
            return
        try:
            pane_a = self._workspace_service.read_composition(state.pane_a_composition_id)
            pane_b = self._workspace_service.read_composition(state.pane_b_composition_id)
        except WorkspaceError:
            self.gis_canvas.set_compare_context(composition, pane_a=None, pane_b=None)
            return
        self.gis_canvas.set_compare_context(composition, pane_a=pane_a, pane_b=pane_b)

    def _sync_target_preview_viewport_overlays(self, *_args: object) -> None:
        composition = self.selected_composition
        if composition is None:
            self.target_preview.set_viewport_overlays(())
            return

        width_points, height_points = self.gis_canvas.map_frame_size_points()
        scale = self.gis_canvas.scale
        try:
            if composition.temporal_compare.enabled:
                pane_centers = self.gis_canvas.compare_pane_centers()
                if set(pane_centers) == {"A", "B"}:
                    overlays = (
                        TargetPreviewViewportOverlay(
                            bbox=view_geo_bounds(
                                center_lon=pane_centers["A"][0],
                                center_lat=pane_centers["A"][1],
                                scale_denom=scale,
                                map_frame_width_points=width_points,
                                map_frame_height_points=height_points,
                            ),
                            color="#ff3b30",
                            label="A",
                        ),
                        TargetPreviewViewportOverlay(
                            bbox=view_geo_bounds(
                                center_lon=pane_centers["B"][0],
                                center_lat=pane_centers["B"][1],
                                scale_denom=scale,
                                map_frame_width_points=width_points,
                                map_frame_height_points=height_points,
                            ),
                            color="#1f8bff",
                            label="B",
                        ),
                    )
                    self.target_preview.set_viewport_overlays(overlays)
                    return

            center = self.gis_canvas.center
            self.target_preview.set_viewport_overlays(
                (
                    TargetPreviewViewportOverlay(
                        bbox=view_geo_bounds(
                            center_lon=center[0],
                            center_lat=center[1],
                            scale_denom=scale,
                            map_frame_width_points=width_points,
                            map_frame_height_points=height_points,
                        ),
                        color="#ff3b30",
                    ),
                )
            )
        except ValueError:
            self.target_preview.set_viewport_overlays(())

    def _map_frame_size_for_composition(
        self,
        composition: Composition,
    ) -> tuple[float, float] | None:
        for target in self._targets or []:
            if target.id != composition.target_id:
                continue
            template_metadata = target.metadata.get("template_metadata")
            if isinstance(template_metadata, dict):
                size = _map_frame_size(template_metadata.get("map_frame"))
                if size is not None:
                    return size
            map_frame = target.metadata.get("map_frame")
            size = _map_frame_size(map_frame)
            if size is not None:
                return size
            explicit_aspect = target.metadata.get("map_frame_aspect")
            if _is_positive_number(explicit_aspect):
                return float(explicit_aspect), 1.0
        return None

    def _load_temporal_compare_controls(self, composition: Composition) -> Composition:
        self._loading_compare_controls = True
        options: list[Composition] = []
        try:
            self.compare_pane_a_combo.clear()
            self.compare_pane_b_combo.clear()
            options = self._usable_compare_compositions(composition)
            for option in options:
                label = _compare_composition_label(option)
                self.compare_pane_a_combo.addItem(label, option.composition_id)
                self.compare_pane_b_combo.addItem(label, option.composition_id)

            state = composition.temporal_compare
            if not self._compare_global_initialized:
                self._compare_enabled_global = state.enabled
                self._compare_orientation_global = state.orientation
                self._compare_global_initialized = True
            orientation_index = self.compare_orientation_combo.findText(
                self._compare_orientation_global.value
            )
            self.compare_orientation_combo.setCurrentIndex(max(0, orientation_index))
            self.compare_enabled_checkbox.setChecked(self._compare_enabled_global)
            pane_a_fallback, pane_b_fallback = _default_compare_pane_indices(
                options,
                composition.composition_id,
            )
            self._select_compare_composition(
                self.compare_pane_a_combo,
                state.pane_a_composition_id,
                pane_a_fallback,
            )
            self._select_compare_composition(
                self.compare_pane_b_combo,
                state.pane_b_composition_id,
                pane_b_fallback,
            )
            enough_options = len(options) >= 2
            effective_checked = self._compare_enabled_global and enough_options
            self.compare_enabled_checkbox.setChecked(effective_checked)
            self.compare_enabled_checkbox.setEnabled(enough_options)
            self.compare_orientation_combo.setEnabled(effective_checked)
            self.compare_pane_a_combo.setEnabled(effective_checked)
            self.compare_pane_b_combo.setEnabled(effective_checked)
            if not enough_options:
                self.compare_status_label.setText(
                    "Comparison disabled: this target requires at least two compositions."
                )
            elif not self._compare_enabled_global:
                self.compare_status_label.setText(
                    "Comparison off: single-map workflow is unchanged."
                )
            else:
                self.compare_status_label.setText(
                    "Comparison panes render the selected compositions/time points."
                )
        finally:
            self._loading_compare_controls = False
        return self._sync_temporal_compare_state_from_controls(composition, len(options) >= 2)

    def _sync_temporal_compare_state_from_controls(
        self,
        composition: Composition,
        enough_options: bool,
    ) -> Composition:
        """Persist the global compare mode into the selected composition when needed."""
        if self._workspace_service is None:
            return composition
        effective_enabled = self._compare_enabled_global and enough_options
        pane_a_composition_id = self.compare_pane_a_combo.currentData()
        pane_b_composition_id = self.compare_pane_b_combo.currentData()
        desired_a = (
            str(pane_a_composition_id) if effective_enabled and pane_a_composition_id else None
        )
        desired_b = (
            str(pane_b_composition_id) if effective_enabled and pane_b_composition_id else None
        )
        state = composition.temporal_compare
        if not effective_enabled and not state.enabled:
            return composition
        if (
            state.enabled == effective_enabled
            and state.orientation == self._compare_orientation_global
            and state.pane_a_composition_id == desired_a
            and state.pane_b_composition_id == desired_b
        ):
            return composition
        try:
            return self._workspace_service.update_temporal_compare_state(
                composition.composition_id,
                enabled=effective_enabled,
                orientation=self._compare_orientation_global,
                pane_a_composition_id=desired_a,
                pane_b_composition_id=desired_b,
            )
        except (WorkspaceError, ValidationError, ValueError) as error:
            self.compare_status_label.setText(f"Could not save comparison state: {error}")
            return composition

    def _usable_compare_compositions(self, composition: Composition) -> list[Composition]:
        if self._workspace_service is None:
            return [composition] if _has_visible_layer(composition) else []
        try:
            compositions = self._workspace_service.list_compositions()
        except WorkspaceError:
            return [composition] if _has_visible_layer(composition) else []
        return sorted(
            (
                item
                for item in compositions
                if item.target_id == composition.target_id and _has_visible_layer(item)
            ),
            key=lambda item: (item.capture_date, item.composition_id),
        )

    def _select_compare_composition(
        self,
        combo: QComboBox,
        composition_id: str | None,
        fallback_index: int,
    ) -> None:
        index = combo.findData(composition_id) if composition_id is not None else -1
        if index < 0 and combo.count() > fallback_index:
            index = fallback_index
        if index >= 0:
            combo.setCurrentIndex(index)

    def _persist_temporal_compare_controls(self, *_args: object) -> None:
        if self._loading_compare_controls:
            return
        if self._workspace_service is None or self.selected_composition is None:
            return

        self._compare_enabled_global = self.compare_enabled_checkbox.isChecked()
        try:
            self._compare_orientation_global = TemporalCompareOrientation(
                self.compare_orientation_combo.currentText()
                or TemporalCompareOrientation.VERTICAL.value
            )
        except ValueError:
            self._compare_orientation_global = TemporalCompareOrientation.VERTICAL

        enough_options = self.compare_pane_a_combo.count() >= 2
        if self._compare_enabled_global and not enough_options:
            self.compare_status_label.setText(
                "Comparison is on globally, but this target requires two usable time points."
            )

        updated = self._sync_temporal_compare_state_from_controls(
            self.selected_composition,
            enough_options,
        )
        self.selected_composition = updated
        self._update_detail_panels(updated)
        self._refresh_workspace_projection(updated.composition_id, validate_selection=False)
        self._request_canvas_render(updated)

    def _load_grid_controls(self, composition: Composition) -> None:
        grid, source = self._effective_grid_for_composition(composition)
        interval = grid.interval
        self.grid_degrees_input.setText(str(interval.degrees))
        self.grid_minutes_input.setText(str(interval.minutes))
        self.grid_seconds_input.setText(_format_number(interval.seconds))
        self.grid_scale_input.setText(str(composition.view.scale))
        self.grid_validation_label.setText("")
        if source == "override":
            self.grid_status_label.setText("Đang dùng grid override của composition.")
        elif source == "target":
            self.grid_status_label.setText("Đang dùng mặc định target.")
        else:
            self.grid_status_label.setText(
                "Chưa có cấu hình grid target; dùng mặc định tạm thời."
            )

    def _effective_grid_for_composition(self, composition: Composition) -> tuple[GridConfig, str]:
        if composition.grid_override is not None:
            return composition.grid_override, "override"

        for target in self._targets or []:
            if target.id == composition.target_id:
                return target.grid, "target"

        return GridConfig(interval=GridInterval(minutes=1), label_format="dms_full"), "fallback"

    def _grid_from_inputs(self) -> GridConfig:
        degrees = _parse_non_negative_int(self.grid_degrees_input.text(), "Độ")
        minutes = _parse_non_negative_int(self.grid_minutes_input.text(), "Phút")
        seconds = _parse_non_negative_float(self.grid_seconds_input.text(), "Giây")
        base_style: dict[str, object] = {}
        label_format = "dms_full"
        if self.selected_composition is not None:
            base_grid, _source = self._effective_grid_for_composition(self.selected_composition)
            base_style = dict(base_grid.style)
            label_format = base_grid.label_format or "dms_full"
        if minutes >= 60:
            raise ValueError("Phút phải nhỏ hơn 60.")
        if seconds >= 60:
            raise ValueError("Giây phải nhỏ hơn 60.")
        try:
            return GridConfig(
                interval=GridInterval(
                    degrees=degrees,
                    minutes=minutes,
                    seconds=seconds,
                ),
                label_format=label_format,
                style=base_style,
            )
        except ValidationError as error:
            if degrees == 0 and minutes == 0 and seconds == 0:
                raise ValueError("Khoảng grid phải lớn hơn 0.") from error
            raise ValueError(f"Grid không hợp lệ: {error}") from error

    def _scale_from_input(self) -> int:
        return _parse_positive_int(self.grid_scale_input.text(), "Scale")


def _is_positive_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def _map_frame_size(map_frame: object) -> tuple[float, float] | None:
    if not isinstance(map_frame, dict):
        return None
    width = map_frame.get("width")
    height = map_frame.get("height")
    if _is_positive_number(width) and _is_positive_number(height):
        return float(width), float(height)
    return None


def _has_existing_visible_raster(composition: Composition) -> bool:
    for layer in composition.layers:
        if not layer.visible:
            continue
        path = layer.cache_path or layer.source_path
        if Path(path).exists():
            return True
    return False


def _has_visible_layer(composition: Composition) -> bool:
    return any(layer.visible for layer in composition.layers)


def _queue_filter_from_session(value: str) -> QueueFilter:
    try:
        return QueueFilter(value)
    except ValueError:
        return QueueFilter.ALL


def _compare_composition_label(composition: Composition) -> str:
    visible_layers = [layer for layer in composition.layers if layer.visible]
    date_text = composition.capture_date.isoformat()
    times = sorted(layer.capture_time for layer in visible_layers if layer.capture_time is not None)
    time_text = times[0].strftime("%H:%M") if times else "unknown-time"
    source_text = _compare_composition_source_label(composition)
    clouds = [layer.cloud_percent for layer in visible_layers if layer.cloud_percent is not None]
    cloud_text = "--" if not clouds else f"{sum(clouds) / len(clouds):.0f}% cloud"
    return (
        f"{date_text} {time_text} | {source_text} | {cloud_text} | "
        f"{len(visible_layers)} layer(s)"
    )


def _compare_composition_source_label(composition: Composition) -> str:
    source_values = {layer.source_kind.value for layer in composition.layers if layer.visible}
    if not source_values:
        return "No visible layers"
    if len(source_values) == 1:
        return "Historical" if "historical" in source_values else "Current"
    return "Mixed"


def _default_compare_pane_indices(
    options: list[Composition],
    composition_id: str,
) -> tuple[int, int]:
    if not options:
        return 0, 0
    current_index = next(
        (
            index
            for index, option in enumerate(options)
            if option.composition_id == composition_id
        ),
        0,
    )
    if len(options) == 1:
        return current_index, current_index
    if current_index + 1 < len(options):
        return current_index, current_index + 1
    return current_index, current_index - 1


def _render_spec_error_message(error: RenderSpecError | ValidationError) -> str:
    if isinstance(error, RenderSpecError) and error.issues:
        return error.issues[0].message
    text = str(error).strip()
    if text:
        return f"Không tạo được render spec cho GIS canvas: {text}"
    return "Không tạo được render spec cho GIS canvas."


def _tile_preview_settings(config) -> TilePreviewSettings:  # noqa: ANN001
    return TilePreviewSettings(
        tile_pixels=config.tile_pixels,
        max_decode_workers=_resolve_decode_workers(config.max_decode_workers),
        tile_width_degrees=config.tile_width_degrees,
        tile_height_degrees=config.tile_height_degrees,
        partial_repaint_threshold_px=config.partial_repaint_threshold_px,
        progress_frame_interval_ms=config.progress_frame_interval_ms,
        progress_tile_batch_size=config.progress_tile_batch_size,
        tile_decode_timeout_ms=config.tile_decode_timeout_ms,
    )


def _resolve_decode_workers(value: int | str) -> int:
    cpu_count = os.cpu_count() or 1
    if isinstance(value, str) and value.lower() == "auto":
        return max(1, min(4, cpu_count))
    return max(1, min(int(value), cpu_count, 16))


def _summary_suffix(message: str | None) -> str:
    if not message:
        return ""
    return f" {message}"


def _parse_non_negative_int(raw: str, label: str) -> int:
    try:
        value = int(raw.strip())
    except ValueError as error:
        raise ValueError(f"{label} phải là số nguyên không âm.") from error
    if value < 0:
        raise ValueError(f"{label} phải là số không âm.")
    return value


def _parse_positive_int(raw: str, label: str) -> int:
    value = _parse_non_negative_int(raw, label)
    if value <= 0:
        raise ValueError(f"{label} phải là số nguyên dương.")
    return value


def _parse_non_negative_float(raw: str, label: str) -> float:
    try:
        value = float(raw.strip())
    except ValueError as error:
        raise ValueError(f"{label} phải là số không âm.") from error
    if value < 0:
        raise ValueError(f"{label} phải là số không âm.")
    return value


def _format_number(value: float | int) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:g}"
