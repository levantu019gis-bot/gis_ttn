"""Review/Edit workstation mode."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
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

from thucthengay.editor.models.composition_tree_model import (
    CompositionTreeModel,
    QueueFilter,
    queue_filter_label,
)
from thucthengay.editor.models.layer_stack_model import LayerStackColumn, LayerStackModel
from thucthengay.editor.render_worker import RenderWorker
from thucthengay.editor.widgets import (
    GisCanvasWidget,
    MetadataEditorDialog,
    TargetPreviewRequestToken,
    TargetPreviewWidget,
    WarningsPanelWidget,
    confirm_date_change_dialog,
)
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
    Issue,
    TargetConfig,
    TemplateMetadata,
)
from thucthengay.render.raster import render_raster_layers
from thucthengay.render.spec import RenderSpecError, build_render_spec
from thucthengay.render.target_preview import build_target_preview_spec
from thucthengay.validation import (
    ValidationContext,
    ValidationResult,
    validate_composition_readiness,
)
from thucthengay.workspace import WorkspaceError, WorkspaceService


class ReviewEditMode(QWidget):
    """Desktop Review/Edit layout and target-composition navigator."""

    compositionSelected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("reviewEditMode")
        self.setMinimumSize(960, 560)
        self._workspace_service: WorkspaceService | None = None
        self._targets: list[TargetConfig] | None = None
        self.selected_composition: Composition | None = None
        self._suppress_selection_validation = False
        self._render_thread: QThread | None = None
        self._render_worker: RenderWorker | None = None
        self._render_token: object | None = None
        self._target_render_thread: QThread | None = None
        self._target_render_worker: RenderWorker | None = None
        self._target_render_token: TargetPreviewRequestToken | None = None

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
        self.grid_label_format_input = QLineEdit("dms_full")
        self.grid_label_format_input.setObjectName("reviewGridLabelFormat")
        self.grid_label_format_input.setToolTip("Định dạng nhãn grid")
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
        self.gis_canvas.viewEditCompleted.connect(self._persist_canvas_view)

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
        self.main_splitter.setSizes([360, 920])

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
        self._update_review_action_state()

    def load_workspace(
        self,
        workspace_service: WorkspaceService,
        *,
        targets: list[TargetConfig] | None = None,
    ) -> None:
        """Load composition navigation from a workspace service."""
        selected_id = self._current_or_selected_composition_id()
        self._workspace_service = workspace_service
        self._targets = list(targets) if targets is not None else None
        compositions = workspace_service.list_compositions()
        self.tree_model.set_compositions(compositions, targets=targets)
        self.tree_view.expandAll()
        self._refresh_filter_controls()
        self._restore_selection(selected_id)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self._cancel_target_render()
        self._cancel_render()
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
        layout.addWidget(self._build_grid_panel(), 1)
        layout.addWidget(self._panel_frame("Target Preview", self.target_preview), 1)
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
        panel.setMinimumWidth(580)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.composition_title)
        layout.addWidget(self._panel_frame("GIS editor", self.gis_canvas), 4)
        layout.addLayout(self._review_action_layout())
        layout.addWidget(self._panel_frame("Warnings", self.warnings_panel), 1)
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

    def _panel_frame(self, title: str, content: QWidget) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumHeight(104)
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
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumHeight(152)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(QLabel("Grid interval"))
        header.addStretch(1)
        header.addWidget(self.save_grid_button)

        fields = QGridLayout()
        fields.setHorizontalSpacing(6)
        fields.setVerticalSpacing(4)
        fields.addWidget(QLabel("Độ"), 0, 0)
        fields.addWidget(self.grid_degrees_input, 0, 1)
        fields.addWidget(QLabel("Phút"), 0, 2)
        fields.addWidget(self.grid_minutes_input, 0, 3)
        fields.addWidget(QLabel("Giây"), 0, 4)
        fields.addWidget(self.grid_seconds_input, 0, 5)
        fields.addWidget(QLabel("Label"), 1, 0)
        fields.addWidget(self.grid_label_format_input, 1, 1, 1, 5)

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
        if composition_id is None:
            return

        index = self.tree_model.index_for_composition_id(composition_id)
        if index.isValid():
            self.tree_view.setCurrentIndex(index)
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
        self.action_summary.setText(
            "Đã include composition và chuyển sang mục kế tiếp nếu có."
        )
        self._advance_after_transition(updated.composition_id)

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
        self.action_summary.setText(
            "Đã skip composition và chuyển sang mục kế tiếp nếu có."
        )
        self._advance_after_transition(updated.composition_id)

    def _go_previous(self) -> None:
        if self._workspace_service is None or self.selected_composition is None:
            return

        previous_id = self._workspace_service.previous_composition_id(
            self.selected_composition.composition_id
        )
        if previous_id is None:
            self.action_summary.setText("Không có composition trước đó trong queue.")
            self._update_review_action_state()
            return

        self._refresh_workspace_projection(previous_id)
        self.action_summary.setText("Đã quay lại composition trước đó.")

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
        if target is not None and "template_metadata" in target.metadata:
            try:
                template_metadata = TemplateMetadata.model_validate(
                    target.metadata["template_metadata"]
                )
            except Exception as error:  # noqa: BLE001
                template_error = str(error)
        elif target is not None and isinstance(target.metadata.get("map_frame"), dict):
            frame = dict(target.metadata["map_frame"])
            frame.setdefault("x", 0)
            frame.setdefault("y", 0)
            try:
                template_metadata = TemplateMetadata.model_validate(
                    {
                        "template_pptx": target.export.template_metadata_file,
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
        self._cancel_render()
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
        if not _has_existing_visible_raster(render_composition):
            self.gis_canvas.set_error("Không tìm thấy file raster visible để render canvas.")
            return
        canvas_width, canvas_height = self.gis_canvas.render_output_size()
        try:
            spec = build_render_spec(
                composition=render_composition,
                target=target,
                template=context.template_metadata,
                template_metadata_file=target.export.template_metadata_file,
                output_width=canvas_width,
                output_height=canvas_height,
            )
        except (RenderSpecError, ValidationError):
            return
        request = PreviewRenderRequest(
            job_id=f"canvas:{composition.composition_id}",
            composition_id=composition.composition_id,
            revision=self.gis_canvas.generation,
            quality=PreviewRenderQuality.SETTLED_HIGH_RES,
            spec=spec,
        )
        self._render_token = self.gis_canvas.set_loading("Đang render preview...")
        thread = QThread(self)
        worker = RenderWorker(request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_canvas_render_result)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_render_worker)
        self._render_thread = thread
        self._render_worker = worker
        thread.start()

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
                template_metadata_file=target.export.template_metadata_file,
                output_width=self.target_preview.render_width(),
                output_height=self.target_preview.render_height(),
            )
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
    def _handle_canvas_render_result(self, result: PreviewRenderJobResult) -> None:
        token = self._render_token
        if token is None:
            return
        self._apply_canvas_render(result, token)

    def _apply_canvas_render(self, result: PreviewRenderJobResult, token: object) -> None:
        if result.state in {JobState.SUCCESS, JobState.WARNING} and result.canvas is not None:
            self.gis_canvas.apply_render_result(token, result.message, canvas=result.canvas)
        elif result.state == JobState.ERROR:
            self.gis_canvas.set_error(result.message)

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

    def _cancel_render(self) -> None:
        if self._render_thread is not None and self._render_thread.isRunning():
            self._render_thread.quit()
            self._render_thread.wait(2000)
        self._render_thread = None
        self._render_worker = None
        self._render_token = None

    def _cancel_target_render(self) -> None:
        if self._target_render_thread is not None and self._target_render_thread.isRunning():
            self._target_render_thread.quit()
            self._target_render_thread.wait(2000)
        self._target_render_thread = None
        self._target_render_worker = None
        self._target_render_token = None

    def _clear_render_worker(self) -> None:
        self._render_thread = None
        self._render_worker = None
        self._render_token = None

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

    def _current_layer(self) -> object | None:
        if self.selected_composition is None:
            return None
        layer_id = self.layer_model.layer_id_for_index(self.layer_table.currentIndex())
        if layer_id is None:
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
        composition_id = self.selected_composition.composition_id
        target_id = self.selected_composition.target_id
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
                    )
                )
            except (WorkspaceError, ValidationError, OSError, ValueError) as error:
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
                "cả hai composition cần revalidate."
            )
            return

        try:
            updated = self._workspace_service.update_layer_metadata(
                composition_id,
                layer_id,
                capture_date=payload["capture_date"],
                capture_time=payload["capture_time"],
                cloud_percent=payload["cloud_percent"],
                metadata_source=payload["metadata_source"],
                metadata_status=payload["metadata_status"],
            )
        except (WorkspaceError, ValidationError, OSError, ValueError) as error:
            self.action_summary.setText(f"Không lưu được metadata: {error}")
            return

        self.selected_composition = updated
        self._update_detail_panels(updated)
        self._refresh_workspace_projection(updated.composition_id, validate_selection=False)
        self.action_summary.setText("Đã lưu metadata; composition cần revalidate.")

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
            next_id = self._workspace_service.next_composition_id(composition_id)
        self._refresh_workspace_projection(next_id or composition_id)

    def _update_review_action_state(self) -> None:
        has_selection = (
            self.selected_composition is not None and self._workspace_service is not None
        )
        previous_available = False
        if has_selection and self._workspace_service is not None and self.selected_composition:
            previous_available = (
                self._workspace_service.previous_composition_id(
                    self.selected_composition.composition_id
                )
                is not None
            )

        self.previous_button.setEnabled(previous_available)
        self.skip_button.setEnabled(has_selection)
        self.include_validate_button.setEnabled(has_selection)
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
        if self._workspace_service is None or self.selected_composition is None:
            return

        composition_id = self.selected_composition.composition_id
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

        self.selected_composition = updated
        self._update_detail_panels(updated)
        self._refresh_workspace_projection(updated.composition_id, validate_selection=False)

    def _save_grid_override(self) -> None:
        if self._workspace_service is None or self.selected_composition is None:
            return

        try:
            grid = self._grid_from_inputs()
            updated = self._workspace_service.update_grid_override(
                self.selected_composition.composition_id,
                degrees=grid.interval.degrees,
                minutes=grid.interval.minutes,
                seconds=grid.interval.seconds,
                label_format=grid.label_format,
                style=grid.style,
            )
        except ValueError as error:
            self.grid_validation_label.setText(str(error))
            return
        except (WorkspaceError, ValidationError) as error:
            self.grid_validation_label.setText(f"Không lưu được grid: {error}")
            return

        self.selected_composition = updated
        self._update_detail_panels(updated)
        self._refresh_workspace_projection(updated.composition_id, validate_selection=False)

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

    def _update_detail_panels(self, composition: Composition) -> None:
        self.composition_title.setText(
            f"{composition.composition_id} | {composition.capture_date.isoformat()}"
        )
        self.layer_model.set_composition(composition)
        self.layer_warning_label.setVisible(self.layer_model.has_no_visible_layers())
        self._update_metadata_edit_button()
        target_preview_needs_render = self.target_preview.set_composition(composition)
        frame_aspect = self._frame_aspect_for_composition(composition)
        if frame_aspect is not None:
            self.gis_canvas.set_frame_aspect(frame_aspect)
        self.gis_canvas.set_composition(composition)
        self._load_grid_controls(composition)
        self.warnings_panel.set_issues(
            (),
            composition_id=composition.composition_id,
            target_id=composition.target_id,
        )
        self._update_review_action_state()
        if target_preview_needs_render:
            self._request_target_preview(composition)
        self._request_canvas_render(composition)

    def _frame_aspect_for_composition(self, composition: Composition) -> float | None:
        for target in self._targets or []:
            if target.id != composition.target_id:
                continue
            explicit_aspect = target.metadata.get("map_frame_aspect")
            if _is_positive_number(explicit_aspect):
                return float(explicit_aspect)
            template_metadata = target.metadata.get("template_metadata")
            if isinstance(template_metadata, dict):
                aspect = _map_frame_aspect(template_metadata.get("map_frame"))
                if aspect is not None:
                    return aspect
            map_frame = target.metadata.get("map_frame")
            aspect = _map_frame_aspect(map_frame)
            if aspect is not None:
                return aspect
        return None

    def _load_grid_controls(self, composition: Composition) -> None:
        grid, source = self._effective_grid_for_composition(composition)
        interval = grid.interval
        self.grid_degrees_input.setText(str(interval.degrees))
        self.grid_minutes_input.setText(str(interval.minutes))
        self.grid_seconds_input.setText(_format_number(interval.seconds))
        self.grid_label_format_input.setText(grid.label_format or "dms_full")
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
        if self.selected_composition is not None:
            base_grid, _source = self._effective_grid_for_composition(self.selected_composition)
            base_style = dict(base_grid.style)
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
                label_format=self.grid_label_format_input.text().strip() or "dms_full",
                style=base_style,
            )
        except ValidationError as error:
            if degrees == 0 and minutes == 0 and seconds == 0:
                raise ValueError("Khoảng grid phải lớn hơn 0.") from error
            raise ValueError(f"Grid không hợp lệ: {error}") from error


def _is_positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _map_frame_aspect(map_frame: object) -> float | None:
    if not isinstance(map_frame, dict):
        return None
    width = map_frame.get("width")
    height = map_frame.get("height")
    if _is_positive_number(width) and _is_positive_number(height):
        return float(width) / float(height)
    return None


def _has_existing_visible_raster(composition: Composition) -> bool:
    for layer in composition.layers:
        if not layer.visible:
            continue
        path = layer.cache_path or layer.source_path
        if Path(path).exists():
            return True
    return False


def _parse_non_negative_int(raw: str, label: str) -> int:
    try:
        value = int(raw.strip())
    except ValueError as error:
        raise ValueError(f"{label} phải là số nguyên không âm.") from error
    if value < 0:
        raise ValueError(f"{label} phải là số không âm.")
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
