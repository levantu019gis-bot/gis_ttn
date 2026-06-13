"""Confirmation UI for existing workspace operations."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtWidgets import QMessageBox, QWidget

from thucthengay.workspace.service import WorkspaceClearPlan


class ExistingWorkspaceAction(StrEnum):
    """Operator choice when a new ingestion targets an existing workspace."""

    CANCEL = "cancel"
    CLEAR = "clear"
    OVERRIDE = "override"


def choose_existing_workspace_action(
    parent: QWidget | None,
    plan: WorkspaceClearPlan,
) -> ExistingWorkspaceAction:
    """Ask the Operator how to handle app-owned data already in the workspace."""
    message = QMessageBox(parent)
    message.setIcon(QMessageBox.Icon.Warning)
    message.setWindowTitle("Workspace đã có dữ liệu")
    message.setText("Workspace đã có dữ liệu do ứng dụng tạo.")
    message.setInformativeText(
        "Chọn Override để giữ dữ liệu cũ, bổ sung dữ liệu mới và ghi đè file trùng; "
        "chọn Xóa sạch để tạo lại các thư mục: " + ", ".join(plan.labels)
    )
    message.setStandardButtons(QMessageBox.StandardButton.Cancel)

    cancel_button = message.button(QMessageBox.StandardButton.Cancel)
    if cancel_button is not None:
        cancel_button.setText("Hủy")
        message.setDefaultButton(cancel_button)

    override_button = message.addButton(
        "Override / bổ sung vào workspace cũ",
        QMessageBox.ButtonRole.AcceptRole,
    )
    clear_button = message.addButton(
        "Xóa sạch và ingest lại",
        QMessageBox.ButtonRole.DestructiveRole,
    )
    message.exec()
    clicked = message.clickedButton()
    if clicked is override_button:
        return ExistingWorkspaceAction.OVERRIDE
    if clicked is clear_button:
        return ExistingWorkspaceAction.CLEAR
    return ExistingWorkspaceAction.CANCEL


def confirm_workspace_clear(parent: QWidget | None, plan: WorkspaceClearPlan) -> bool:
    """Ask the Operator before clearing app-owned workspace data."""
    return choose_existing_workspace_action(parent, plan) is ExistingWorkspaceAction.CLEAR
