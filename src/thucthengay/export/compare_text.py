"""Helpers for resolving export text context from temporal compare panes."""

from __future__ import annotations

from thucthengay.models import Composition
from thucthengay.workspace import WorkspaceError, WorkspaceService


def resolve_compare_text_panes(
    workspace_service: WorkspaceService,
    composition: Composition,
) -> tuple[Composition | None, Composition | None]:
    """Return pane A/B compositions used by compare export text placeholders."""
    state = composition.temporal_compare
    if not state.enabled:
        return None, None
    return (
        _read_optional_composition(workspace_service, state.pane_a_composition_id),
        _read_optional_composition(workspace_service, state.pane_b_composition_id),
    )


def _read_optional_composition(
    workspace_service: WorkspaceService,
    composition_id: str | None,
) -> Composition | None:
    if not composition_id:
        return None
    try:
        return workspace_service.read_composition(composition_id)
    except WorkspaceError:
        return None
