"""Export mode dashboard and preflight plan UI."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from thucthengay.editor.export_worker import ExportRunner, ExportWorker
from thucthengay.editor.models.export_plan_model import ExportPlanModel
from thucthengay.editor.preferences import PreferencesService
from thucthengay.editor.widgets.export_summary import ExportSummaryWidget
from thucthengay.export import (
    FullExportResult,
    build_export_preflight_plan,
    preflight_allows_auto_export,
    run_full_export,
)
from thucthengay.history import HistoryService
from thucthengay.models import ExportPreflightPlan, Issue, IssueSeverity, TargetConfig
from thucthengay.workspace import WorkspaceError, WorkspaceService


class ExportMode(QWidget):
    """Desktop Export mode focused on preflight and export plan review."""

    jumpRequested = Signal(str, str, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        preferences_service: PreferencesService | None = None,
        export_runner: ExportRunner = run_full_export,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("exportMode")
        self.setMinimumSize(960, 560)
        self._preferences_service = preferences_service
        self._workspace_service: WorkspaceService | None = None
        self._targets: list[TargetConfig] = []
        self._template_issues: list[Issue] = []
        self._history_service: HistoryService | None = None
        self._last_plan: ExportPreflightPlan | None = None
        self._export_runner = export_runner
        self._export_thread: QThread | None = None
        self._export_worker: ExportWorker | None = None

        self.summary = ExportSummaryWidget()
        self.preflight_button = QPushButton("Preflight")
        self.preflight_button.setObjectName("exportPreflight")
        self.preflight_button.clicked.connect(self.run_preflight)
        output_stem = (
            self._preferences_service.preferences.export.output_stem
            if self._preferences_service is not None
            else "report"
        )
        self.output_stem_input = QLineEdit(output_stem)
        self.output_stem_input.setObjectName("exportOutputStem")
        self.output_stem_input.setMinimumWidth(180)
        self.output_stem_input.setToolTip("Tên file export trong workspace/exports")
        self.output_stem_input.editingFinished.connect(self._persist_output_stem)
        self.export_button = QPushButton("Export PPTX/TXT")
        self.export_button.setObjectName("exportFinal")
        self.export_button.setProperty("primaryAction", True)
        self.export_button.setEnabled(False)
        self.export_button.setToolTip("Chay Preflight va xu ly loi blocking truoc khi export.")
        self.export_button.clicked.connect(self.run_export)

        self.status_label = QLabel("Chua chay preflight.")
        self.status_label.setObjectName("exportStatus")
        self.status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("exportProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumWidth(220)

        self.plan_model = ExportPlanModel(self)
        self.plan_table = QTableView()
        self.plan_table.setObjectName("exportPlanTable")
        self.plan_table.setModel(self.plan_model)
        self.plan_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.plan_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.plan_table.setAlternatingRowColors(True)
        self.plan_table.verticalHeader().setDefaultSectionSize(30)
        self.plan_table.verticalHeader().setVisible(False)
        self.plan_table.doubleClicked.connect(self._jump_from_index)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.preflight_button)
        toolbar.addWidget(QLabel("Tên file"))
        toolbar.addWidget(self.output_stem_input)
        toolbar.addWidget(self.export_button)
        toolbar.addWidget(self.progress_bar)
        toolbar.addStretch(1)
        toolbar.addWidget(self.status_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self.summary)
        layout.addLayout(toolbar)
        layout.addWidget(self._panel_frame("Export Plan", self.plan_table), 1)

    def load_workspace(
        self,
        workspace_service: WorkspaceService,
        *,
        targets: list[TargetConfig] | None = None,
        template_issues: list[Issue] | None = None,
        history_service: HistoryService | None = None,
    ) -> None:
        self._workspace_service = workspace_service
        self._targets = list(targets or [])
        self._template_issues = list(template_issues or [])
        self._history_service = history_service
        self.status_label.setText("San sang chay preflight.")
        self.progress_bar.setValue(0)
        self.export_button.setEnabled(False)
        self._last_plan = None

    def set_history_service(self, history_service: HistoryService | None) -> None:
        """Refresh the configured historical registry used by export."""
        self._history_service = history_service

    def refresh_config_targets(
        self,
        targets: list[TargetConfig],
        *,
        template_issues: list[Issue] | None = None,
    ) -> None:
        """Refresh target config after the Config tab saves and require preflight again."""
        if self._workspace_service is None:
            return
        self._targets = list(targets)
        self._template_issues = list(template_issues or [])
        self._last_plan = None
        self.plan_model.set_rows([])
        self.export_button.setEnabled(False)
        self.export_button.setToolTip("Config da doi; hay chay lai Preflight truoc khi export.")
        self.status_label.setText("Da reload config moi. Hay chay lai Preflight.")

    def run_preflight(self) -> None:
        if self._workspace_service is None:
            self.status_label.setText("Chua co workspace de chay preflight.")
            self.export_button.setEnabled(False)
            return
        try:
            plan = build_export_preflight_plan(
                self._workspace_service,
                self._targets,
                template_issues=self._template_issues,
            )
        except WorkspaceError as error:
            self.status_label.setText(f"Khong doc duoc workspace: {error}")
            self.export_button.setEnabled(False)
            return

        self._last_plan = plan
        self.summary.set_summary(plan.summary)
        self.plan_model.set_rows(plan.rows)
        self.plan_table.resizeColumnsToContents()
        can_export = preflight_allows_auto_export(plan)
        self.export_button.setEnabled(can_export)
        if plan.summary.error_count and not can_export:
            self.export_button.setToolTip("Export bi chan vi preflight con loi blocking.")
            self.status_label.setText(
                "Preflight bi chan. Double click row co issue de quay lai sua."
            )
        elif plan.summary.error_count:
            self.export_button.setToolTip("Export se tao anh final con thieu truoc khi xuat.")
            self.status_label.setText(
                "Preflight chi thieu anh final; bam Export de render va xuat PPTX/TXT."
            )
        else:
            self.export_button.setToolTip("Xuat PPTX/TXT va ghi export log.")
            self.status_label.setText("Preflight khong co loi blocking; san sang export.")

    def run_export(self) -> None:
        if self._workspace_service is None:
            self.status_label.setText("Chua co workspace de export.")
            return
        if self._export_thread is not None:
            return
        if self._last_plan is None:
            self.run_preflight()
        if self._last_plan is None or not preflight_allows_auto_export(self._last_plan):
            self.status_label.setText("Export bi chan vi preflight con loi blocking.")
            return

        self.preflight_button.setEnabled(False)
        self.export_button.setEnabled(False)
        output_stem = self._current_output_stem()
        self._persist_output_stem()
        self.progress_bar.setValue(0)
        self.status_label.setText("Dang tao anh final va export PPTX/TXT...")
        thread = QThread(self)
        worker = ExportWorker(
            self._workspace_service,
            list(self._targets),
            output_stem=output_stem,
            template_issues=self._template_issues,
            history_service=self._history_service,
            runner=self._export_runner,
        )
        worker.moveToThread(thread)
        self._export_thread = thread
        self._export_worker = worker
        thread.started.connect(worker.run)
        worker.progress.connect(self._update_export_progress)
        worker.finished.connect(self._finish_export)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_export_worker)
        thread.start()

    @Slot(object)
    def _finish_export(self, result: FullExportResult) -> None:
        self.progress_bar.setValue(100)
        self._last_plan = result.preflight_plan
        self.summary.set_summary(result.preflight_plan.summary)
        self.plan_model.set_rows(result.preflight_plan.rows)
        self.plan_table.resizeColumnsToContents()
        self.preflight_button.setEnabled(True)
        self.export_button.setEnabled(preflight_allows_auto_export(result.preflight_plan))
        if result.ok and result.log_result is not None:
            summary = result.log_result.summary
            if summary.skipped_count or summary.error_count:
                self.status_label.setText(
                    "Export xong mot phan: "
                    f"{summary.slide_count} slide, {summary.txt_line_count} dong TXT, "
                    f"bo qua {summary.skipped_count} composition. "
                    f"{_issue_details(result.log_result.issues)} "
                    f"Log: {summary.log_path}."
                )
            else:
                self.status_label.setText(
                    "Export xong: "
                    f"{summary.slide_count} slide, {summary.txt_line_count} dong TXT. "
                    f"Log: {summary.log_path}."
                )
            self.export_button.setToolTip("Co the export lai neu workspace thay doi.")
            return

        log_path = (
            result.log_result.summary.log_path
            if result.log_result is not None and result.log_result.summary.log_path
            else None
        )
        issues = result.log_result.issues if result.log_result is not None else result.issues
        issue_count = len(issues)
        log_text = f" Log: {log_path}." if log_path else ""
        self.status_label.setText(
            f"Export loi: {issue_count} issue. {_issue_details(issues)}{log_text}"
        )
        self.export_button.setToolTip("Kiem tra issue trong bang Preflight roi thu lai.")

    @Slot(object)
    def _update_export_progress(self, progress) -> None:  # noqa: ANN001
        percent = getattr(progress, "percent", None)
        if percent is None:
            total = getattr(progress, "total", 100) or 100
            completed = getattr(progress, "completed", 0) or 0
            percent = max(0, min(100, round(completed / total * 100)))
        self.progress_bar.setValue(percent)
        message = getattr(progress, "message", "")
        if message:
            self.status_label.setText(message)

    def _clear_export_worker(self) -> None:
        self._export_thread = None
        self._export_worker = None

    def _current_output_stem(self) -> str:
        output_stem = self.output_stem_input.text().strip() or "report"
        if output_stem != self.output_stem_input.text():
            self.output_stem_input.setText(output_stem)
        return output_stem

    def _persist_output_stem(self) -> None:
        if self._preferences_service is None:
            return
        self._preferences_service.update_export_output_stem(self._current_output_stem())

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._export_worker is not None:
            self._export_worker.cancel()
        if self._export_thread is not None and self._export_thread.isRunning():
            self._export_thread.quit()
            self._export_thread.wait(2000)
        super().closeEvent(event)

    def _jump_from_index(self, index) -> None:  # noqa: ANN001
        row = self.plan_model.row_at(index.row())
        if row is None:
            return
        self.jumpRequested.emit(row.target_id, row.composition_id, "")

    def _panel_frame(self, title: str, content: QWidget) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        layout.addWidget(QLabel(title))
        layout.addWidget(content, 1)
        return frame


def _issue_details(issues: list[Issue], *, limit: int = 3) -> str:
    selected: list[Issue] = []
    for issue in sorted(issues, key=_issue_detail_priority):
        if issue.severity == IssueSeverity.ERROR and issue not in selected:
            selected.append(issue)
        if len(selected) >= limit:
            break
    if not selected:
        for issue in issues:
            if issue not in selected:
                selected.append(issue)
            if len(selected) >= limit:
                break
    if not selected:
        return "Khong co chi tiet issue."
    details: list[str] = []
    for issue in selected:
        subject = issue.composition_id or issue.target_id or issue.scope.value
        text = f"{subject}: Nguyen nhan: {issue.message}"
        if issue.remediation:
            text = f"{text} Cach xu ly: {issue.remediation}"
        details.append(text)
    remaining = len(issues) - len(selected)
    suffix = f" (+{remaining} issue khac)" if remaining > 0 else ""
    return "Chi tiet loi: " + " | ".join(details) + suffix


def _issue_detail_priority(issue: Issue) -> tuple[int, str]:
    if issue.scope.value == "render" and issue.issue_id != "export.final_render_missing":
        return (0, issue.issue_id)
    if issue.issue_id not in {"export.final_render_missing", "export.output_row_missing"}:
        return (1, issue.issue_id)
    return (2, issue.issue_id)
