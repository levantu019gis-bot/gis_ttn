"""Workspace service facade for manifest and composition state."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    LayerRenderBands,
    LayerSymbology,
    MetadataSource,
    MetadataStatus,
    TemporalCompareOrientation,
    TemporalCompareState,
    ValidationSummary,
    ViewState,
    WorkspaceManifest,
    WorkspaceSessionState,
)
from thucthengay.workspace.atomic_write import atomic_write_json
from thucthengay.workspace.paths import WorkspacePaths


class WorkspaceError(RuntimeError):
    """Base error for expected workspace failures."""


class WorkspaceClearNotConfirmedError(WorkspaceError):
    """Raised when destructive clearing is requested without explicit confirmation."""


@dataclass(frozen=True)
class WorkspaceClearPlan:
    """App-owned workspace paths that would be cleared."""

    cache: Path
    compositions: Path
    renders: Path
    exports: Path

    @property
    def labels(self) -> tuple[str, ...]:
        return ("cache/", "compositions/", "renders/", "exports/")

    @property
    def paths(self) -> tuple[Path, ...]:
        return (self.cache, self.compositions, self.renders, self.exports)


_UNCHANGED = object()


class WorkspaceService:
    """Owns all workspace manifest and composition file access."""

    def __init__(self, workspace_root: str | Path) -> None:
        self.paths = WorkspacePaths(Path(workspace_root).expanduser().resolve())

    def initialize(
        self,
        *,
        config_path: str | Path,
        imagery_input_path: str | Path | None = None,
    ) -> WorkspaceManifest:
        """Create or verify the workspace layout and manifest."""
        self._ensure_layout()
        if self.paths.manifest.exists():
            manifest = self.load_manifest()
            changed = False
            if str(config_path) != manifest.config_path:
                manifest.config_path = str(config_path)
                changed = True
            if (
                imagery_input_path is not None
                and str(imagery_input_path) != manifest.imagery_input_path
            ):
                manifest.imagery_input_path = str(imagery_input_path)
                changed = True
            if changed:
                self.write_manifest(manifest)
            return manifest

        now = _utc_now()
        manifest = WorkspaceManifest(
            config_path=str(config_path),
            imagery_input_path=str(imagery_input_path) if imagery_input_path is not None else None,
            composition_ids=[],
            created_at=now,
            updated_at=now,
        )
        self.write_manifest(manifest)
        return manifest

    def load_manifest(self) -> WorkspaceManifest:
        """Load the manifest and recreate recoverable missing folders."""
        self._ensure_layout()
        try:
            raw = json.loads(self.paths.manifest.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            msg = f"Workspace manifest not found: {self.paths.manifest}"
            raise WorkspaceError(msg) from error
        except JSONDecodeError as error:
            msg = f"Workspace manifest is not valid JSON: {self.paths.manifest}"
            raise WorkspaceError(msg) from error

        try:
            return WorkspaceManifest.model_validate(raw)
        except ValidationError as error:
            msg = f"Workspace manifest schema is invalid: {self.paths.manifest}"
            raise WorkspaceError(msg) from error

    def write_manifest(self, manifest: WorkspaceManifest) -> None:
        """Atomically persist the workspace manifest."""
        manifest.updated_at = _utc_now()
        if manifest.created_at is None:
            manifest.created_at = manifest.updated_at
        atomic_write_json(self.paths.manifest, manifest.model_dump(mode="json"))

    def load_session_state(self) -> WorkspaceSessionState:
        """Load persisted UI session state, or return defaults for old workspaces."""
        self._ensure_layout()
        if not self.paths.session_state.exists():
            return WorkspaceSessionState()
        try:
            raw = json.loads(self.paths.session_state.read_text(encoding="utf-8"))
        except JSONDecodeError as error:
            msg = f"Workspace session state is not valid JSON: {self.paths.session_state}"
            raise WorkspaceError(msg) from error

        try:
            return WorkspaceSessionState.model_validate(raw)
        except ValidationError as error:
            msg = f"Workspace session state schema is invalid: {self.paths.session_state}"
            raise WorkspaceError(msg) from error

    def write_session_state(self, state: WorkspaceSessionState) -> Path:
        """Atomically persist workspace-local UI session state."""
        self._ensure_layout()
        state.updated_at = _utc_now()
        atomic_write_json(self.paths.session_state, state.model_dump(mode="json"))
        return self.paths.session_state

    def update_review_session_state(
        self,
        *,
        selected_composition_id: str | None | object = _UNCHANGED,
        selected_layer_id: str | None | object = _UNCHANGED,
        active_queue_filter: str | object = _UNCHANGED,
    ) -> WorkspaceSessionState:
        """Persist the latest Review/Edit cursor without touching compositions."""
        state = self.load_session_state()
        review_updates: dict[str, object | None] = {}
        if selected_composition_id is not _UNCHANGED:
            review_updates["selected_composition_id"] = selected_composition_id
        if selected_layer_id is not _UNCHANGED:
            review_updates["selected_layer_id"] = selected_layer_id
        if active_queue_filter is not _UNCHANGED:
            review_updates["active_queue_filter"] = active_queue_filter
        if not review_updates:
            return state
        updated = state.model_copy(
            update={"review": state.review.model_copy(update=review_updates)}
        )
        self.write_session_state(updated)
        return updated

    def write_composition(self, composition: Composition) -> Path:
        """Atomically persist one composition and register it in the manifest."""
        self._ensure_layout()
        composition_path = self.paths.composition_file(composition.composition_id)
        atomic_write_json(composition_path, composition.model_dump(mode="json"))

        manifest = self.load_manifest()
        if composition.composition_id not in manifest.composition_ids:
            manifest.composition_ids.append(composition.composition_id)
            manifest.composition_ids.sort()
            self.write_manifest(manifest)

        return composition_path

    def read_composition(self, composition_id: str) -> Composition:
        """Load one composition by id."""
        composition_path = self.paths.composition_file(composition_id)
        try:
            raw = json.loads(composition_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            msg = f"Composition not found: {composition_id}"
            raise WorkspaceError(msg) from error
        except JSONDecodeError as error:
            msg = f"Composition JSON is invalid: {composition_path}"
            raise WorkspaceError(msg) from error

        try:
            return Composition.model_validate(raw)
        except ValidationError as error:
            msg = f"Composition schema is invalid: {composition_path}"
            raise WorkspaceError(msg) from error

    def list_compositions(self) -> list[Composition]:
        """Load compositions in manifest queue order."""
        manifest = self.load_manifest()
        return [
            self.read_composition(composition_id)
            for composition_id in manifest.composition_ids
        ]

    def resolve_composition_layer_paths(self, composition: Composition) -> Composition:
        """Return a transient composition whose relative layer paths are workspace-rooted."""
        resolved_layers = [
            layer.model_copy(
                update={
                    "source_path": self._resolve_layer_path(layer.source_path),
                    "cache_path": (
                        self._resolve_layer_path(layer.cache_path)
                        if layer.cache_path is not None
                        else None
                    ),
                    "prepared_path": (
                        self._resolve_layer_path(layer.prepared_path)
                        if layer.prepared_path is not None
                        else None
                    ),
                }
            )
            for layer in composition.layers
        ]
        return composition.model_copy(update={"layers": resolved_layers})

    def update_review_state(
        self,
        composition_id: str,
        *,
        reviewed: bool | None = None,
        ready: bool | None = None,
        include: bool | None = None,
        review_order: int | None = None,
        notes: str | None = None,
    ) -> Composition:
        """Persist review/status fields for one composition."""
        composition = self.read_composition(composition_id)
        updates: dict[str, object | None] = {}
        if reviewed is not None:
            updates["reviewed"] = reviewed
        if ready is not None:
            updates["ready"] = ready
        if include is not None:
            updates["include"] = include
        if review_order is not None:
            updates["review_order"] = review_order
        if notes is not None:
            updates["notes"] = notes

        updated = _validated_composition_update(composition, updates)
        self.write_composition(updated)
        return updated

    def save_validation_summary(
        self,
        composition_id: str,
        summary: ValidationSummary,
    ) -> Composition:
        """Persist compact validation summary and mark it current."""
        composition = self.read_composition(composition_id)
        updated = _validated_composition_update(
            composition,
            {
                "validation_summary": summary,
                "needs_revalidation": False,
            },
        )
        self.write_composition(updated)
        return updated

    def record_final_render_artifacts(
        self,
        composition_id: str,
        *,
        final_render_path: str,
        render_log_path: str,
    ) -> Composition:
        """Persist workspace-relative final image and render-log references."""
        final_render_path = _validate_render_artifact_path(final_render_path)
        render_log_path = _validate_render_artifact_path(render_log_path)
        composition = self.read_composition(composition_id)
        artifacts = composition.artifacts.model_copy(
            update={
                "final_render_path": final_render_path,
                "render_log_path": render_log_path,
            }
        )
        updated = _validated_composition_update(composition, {"artifacts": artifacts})
        self.write_composition(updated)
        return updated

    def mark_needs_revalidation(self, composition_id: str) -> Composition:
        """Mark a composition stale after layer/view/grid/metadata edits."""
        composition = self.read_composition(composition_id)
        updated = _mark_composition_edit_stale(composition)
        self.write_composition(updated)
        return updated

    def set_layer_visibility(
        self,
        composition_id: str,
        layer_id: str,
        *,
        visible: bool,
    ) -> Composition:
        """Persist one layer visibility change and mark the composition stale."""
        composition = self.read_composition(composition_id)
        found = False
        updated_layers: list[ImageLayer] = []
        for layer in composition.layers:
            if layer.layer_id == layer_id:
                found = True
                updated_layers.append(layer.model_copy(update={"visible": visible}))
            else:
                updated_layers.append(layer)

        if not found:
            msg = f"Layer not found in composition {composition_id}: {layer_id}"
            raise WorkspaceError(msg)

        updated = _mark_composition_edit_stale(
            _validated_composition_update(composition, {"layers": updated_layers})
        )
        self.write_composition(updated)
        return updated

    def update_layer_metadata(
        self,
        composition_id: str,
        layer_id: str,
        *,
        source_path: str | None = None,
        cache_path: str | None = None,
        capture_date: Any,
        capture_time: Any,
        cloud_percent: float | None,
        metadata_source: MetadataSource,
        metadata_status: MetadataStatus,
        render_bands: LayerRenderBands | None | object = _UNCHANGED,
        symbology: LayerSymbology | None | object = _UNCHANGED,
    ) -> Composition:
        """Persist manual layer metadata correction and mark composition stale."""
        if capture_date is None and capture_time is not None:
            msg = "Cần nhập ngày chụp khi đã có giờ chụp."
            raise WorkspaceError(msg)

        if source_path is not None and not source_path.strip():
            msg = "File nguồn không được để trống."
            raise WorkspaceError(msg)

        metadata_updates = {
            "capture_date": capture_date,
            "capture_time": capture_time,
            "cloud_percent": cloud_percent,
            "metadata_source": metadata_source,
            "metadata_status": metadata_status,
        }
        if render_bands is not _UNCHANGED:
            metadata_updates["render_bands"] = render_bands
        if symbology is not _UNCHANGED:
            metadata_updates["symbology"] = symbology
        if source_path is not None:
            metadata_updates["source_path"] = source_path.strip()
        if cache_path is not None:
            metadata_updates["cache_path"] = cache_path.strip() or None
        composition = self.read_composition(composition_id)
        found = False
        updated_layers: list[ImageLayer] = []
        for layer in composition.layers:
            if layer.layer_id == layer_id:
                found = True
                layer_data = layer.model_dump(mode="python")
                layer_data.update(metadata_updates)
                updated_layers.append(ImageLayer.model_validate(layer_data))
            else:
                updated_layers.append(layer)

        if not found:
            msg = f"Layer not found in composition {composition_id}: {layer_id}"
            raise WorkspaceError(msg)

        updated = _mark_composition_edit_stale(
            _validated_composition_update(composition, {"layers": updated_layers})
        )
        self.write_composition(updated)
        return updated

    def move_layer_between_compositions(
        self,
        source_composition_id: str,
        layer_id: str,
        *,
        new_composition_id: str,
        new_target_id: str,
        new_capture_date: Any,
        capture_time: Any,
        cloud_percent: float | None,
        metadata_source: MetadataSource,
        metadata_status: MetadataStatus,
        source_path: str | None = None,
        cache_path: str | None = None,
        render_bands: LayerRenderBands | None | object = _UNCHANGED,
        symbology: LayerSymbology | None | object = _UNCHANGED,
    ) -> tuple[Composition, Composition]:
        """Move a layer from one composition to another (creating dest if needed)."""
        if new_capture_date is None:
            msg = "Cần có capture_date để xác định composition đích."
            raise WorkspaceError(msg)

        if source_path is not None and not source_path.strip():
            msg = "File nguồn không được để trống."
            raise WorkspaceError(msg)

        source = self.read_composition(source_composition_id)
        moved_layer: ImageLayer | None = None
        remaining_layers: list[ImageLayer] = []
        for layer in source.layers:
            if layer.layer_id == layer_id:
                moved_layer = layer
            else:
                remaining_layers.append(layer)

        if moved_layer is None:
            msg = f"Layer not found in composition {source_composition_id}: {layer_id}"
            raise WorkspaceError(msg)

        destination_path = self.paths.composition_file(new_composition_id)
        destination_existed = destination_path.exists()
        if destination_existed:
            destination = self.read_composition(new_composition_id)
            if (
                destination.target_id != new_target_id
                or destination.capture_date != new_capture_date
            ):
                msg = (
                    f"Composition đích {new_composition_id} không khớp target/ngày "
                    "đang lưu. Vui lòng kiểm tra workspace trước khi đổi ngày."
                )
                raise WorkspaceError(msg)
        else:
            destination = Composition(
                composition_id=new_composition_id,
                target_id=new_target_id,
                capture_date=new_capture_date,
                view=source.view,
                layers=[],
            )

        dest_layers = list(destination.layers)
        if any(layer.layer_id == layer_id for layer in dest_layers):
            msg = (
                f"Composition đích {new_composition_id} đã có layer {layer_id}. "
                "Vui lòng kiểm tra workspace trước khi đổi ngày."
            )
            raise WorkspaceError(msg)

        layer_data = moved_layer.model_dump(mode="python")
        layer_data.update(
            {
                "capture_date": new_capture_date,
                "capture_time": capture_time,
                "cloud_percent": cloud_percent,
                "metadata_source": metadata_source,
                "metadata_status": metadata_status,
                "order": len(dest_layers),
            }
        )
        if render_bands is not _UNCHANGED:
            layer_data["render_bands"] = render_bands
        if symbology is not _UNCHANGED:
            layer_data["symbology"] = symbology
        if source_path is not None:
            layer_data["source_path"] = source_path.strip()
        if cache_path is not None:
            layer_data["cache_path"] = cache_path.strip() or None
        try:
            updated_layer = ImageLayer.model_validate(layer_data)
        except ValidationError as error:
            msg = f"Metadata layer không hợp lệ: {error}"
            raise WorkspaceError(msg) from error
        dest_layers.append(updated_layer)
        normalized_dest_layers = [
            layer.model_copy(update={"order": order})
            for order, layer in enumerate(dest_layers)
        ]
        normalized_source_layers = [
            layer.model_copy(update={"order": order})
            for order, layer in enumerate(remaining_layers)
        ]
        updated_destination = _mark_composition_edit_stale(
            _validated_composition_update(destination, {"layers": normalized_dest_layers})
        )
        updated_source = _mark_composition_edit_stale(
            _validated_composition_update(source, {"layers": normalized_source_layers})
        )

        try:
            self.write_composition(updated_destination)
        except (WorkspaceError, OSError, ValueError) as error:
            msg = (
                f"Không ghi được composition đích {new_composition_id}: {error}. "
                "Vui lòng kiểm tra workspace và thử lại."
            )
            raise WorkspaceError(msg) from error

        try:
            self.write_composition(updated_source)
        except (WorkspaceError, OSError, ValueError) as error:
            rollback_error = self._rollback_destination_after_failed_move(
                new_composition_id,
                destination if destination_existed else None,
            )
            rollback_note = (
                " Đã khôi phục composition đích."
                if rollback_error is None
                else f" Không thể tự khôi phục composition đích: {rollback_error}."
            )
            msg = (
                f"Đã ghi composition đích nhưng không cập nhật được nguồn "
                f"{source_composition_id}: {error}.{rollback_note} "
                "Vui lòng kiểm tra workspace rồi thử lại."
            )
            raise WorkspaceError(msg) from error

        return updated_source, updated_destination

    def _rollback_destination_after_failed_move(
        self,
        composition_id: str,
        original_destination: Composition | None,
    ) -> str | None:
        try:
            if original_destination is not None:
                self.write_composition(original_destination)
            else:
                self.paths.composition_file(composition_id).unlink(missing_ok=True)
                manifest = self.load_manifest()
                if composition_id in manifest.composition_ids:
                    manifest.composition_ids.remove(composition_id)
                    self.write_manifest(manifest)
        except (WorkspaceError, OSError, ValueError) as error:
            return str(error)
        return None

    def reorder_layers(
        self,
        composition_id: str,
        ordered_layer_ids: list[str],
    ) -> Composition:
        """Persist a complete layer order using normalized zero-based order values."""
        composition = self.read_composition(composition_id)
        current_ids = {layer.layer_id for layer in composition.layers}
        requested_ids = set(ordered_layer_ids)
        if len(ordered_layer_ids) != len(requested_ids) or requested_ids != current_ids:
            msg = f"Layer order must include each layer in {composition_id} exactly once."
            raise WorkspaceError(msg)

        layer_lookup = {layer.layer_id: layer for layer in composition.layers}
        updated_layers = [
            layer_lookup[layer_id].model_copy(update={"order": order})
            for order, layer_id in enumerate(ordered_layer_ids)
        ]
        updated = _mark_composition_edit_stale(
            _validated_composition_update(composition, {"layers": updated_layers})
        )
        self.write_composition(updated)
        return updated

    def update_view_state(
        self,
        composition_id: str,
        *,
        center: list[float],
        scale: int,
    ) -> Composition:
        """Persist map view center/scale and mark the composition stale."""
        composition = self.read_composition(composition_id)
        view = ViewState(center=center, scale=scale, rotation=0)
        updated = _mark_composition_edit_stale(
            _validated_composition_update(composition, {"view": view})
        )
        self.write_composition(updated)
        return updated

    def update_layer_prepared_path(
        self,
        composition_id: str,
        layer_id: str,
        *,
        prepared_path: str | None,
    ) -> Composition:
        """Persist a prepared raster path while keeping the original source path."""

        composition = self.read_composition(composition_id)
        found = False
        updated_layers: list[ImageLayer] = []
        for layer in composition.layers:
            if layer.layer_id == layer_id:
                found = True
                updated_layers.append(
                    layer.model_copy(
                        update={
                            "prepared_path": prepared_path.strip()
                            if prepared_path
                            else None
                        }
                    )
                )
            else:
                updated_layers.append(layer)
        if not found:
            msg = f"Layer not found in composition {composition_id}: {layer_id}"
            raise WorkspaceError(msg)
        updated = _mark_composition_edit_stale(
            _validated_composition_update(composition, {"layers": updated_layers})
        )
        self.write_composition(updated)
        return updated

    def update_temporal_compare_state(
        self,
        composition_id: str,
        *,
        enabled: bool,
        orientation: TemporalCompareOrientation | str,
        pane_a_composition_id: str | None = None,
        pane_b_composition_id: str | None = None,
        pane_a_layer_id: str | None = None,
        pane_b_layer_id: str | None = None,
    ) -> Composition:
        """Persist temporal comparison selections and mark render/export stale."""
        composition = self.read_composition(composition_id)
        use_compositions = bool(pane_a_composition_id or pane_b_composition_id)
        if enabled and use_compositions:
            if not pane_a_composition_id or not pane_b_composition_id:
                msg = "Comparison panes must reference two compositions."
                raise WorkspaceError(msg)
            pane_a = self.read_composition(pane_a_composition_id)
            pane_b = self.read_composition(pane_b_composition_id)
            if (
                pane_a.target_id != composition.target_id
                or pane_b.target_id != composition.target_id
            ):
                msg = "Comparison panes must belong to the selected composition target."
                raise WorkspaceError(msg)
            if not _has_visible_layer(pane_a) or not _has_visible_layer(pane_b):
                msg = "Comparison pane compositions must have at least one visible layer."
                raise WorkspaceError(msg)
        elif enabled:
            layer_ids = {layer.layer_id for layer in composition.layers}
            missing = [
                layer_id
                for layer_id in (pane_a_layer_id, pane_b_layer_id)
                if layer_id is None or layer_id not in layer_ids
            ]
            if missing:
                msg = "Comparison panes must reference existing composition layers."
                raise WorkspaceError(msg)
            if pane_a_layer_id == pane_b_layer_id:
                msg = "Comparison panes must use two different layers."
                raise WorkspaceError(msg)

        state = TemporalCompareState(
            enabled=enabled,
            orientation=orientation,
            pane_a_composition_id=pane_a_composition_id if enabled and use_compositions else None,
            pane_b_composition_id=pane_b_composition_id if enabled and use_compositions else None,
            pane_a_layer_id=pane_a_layer_id if enabled and not use_compositions else None,
            pane_b_layer_id=pane_b_layer_id if enabled and not use_compositions else None,
            pane_a_center=(
                _preserved_or_composition_center(
                    composition.temporal_compare,
                    "A",
                    pane_a_composition_id,
                    pane_a,
                )
                if enabled and use_compositions
                else None
            ),
            pane_b_center=(
                _preserved_or_composition_center(
                    composition.temporal_compare,
                    "B",
                    pane_b_composition_id,
                    pane_b,
                )
                if enabled and use_compositions
                else None
            ),
        )
        updated = _mark_composition_edit_stale(
            _validated_composition_update(composition, {"temporal_compare": state})
        )
        self.write_composition(updated)
        return updated

    def update_temporal_compare_pane_view(
        self,
        composition_id: str,
        *,
        pane: str,
        center: list[float],
    ) -> Composition:
        """Persist a per-pane comparison center and mark render/export stale."""
        composition = self.read_composition(composition_id)
        state = composition.temporal_compare
        pane_key = pane.upper()
        if not state.enabled or not state.pane_a_composition_id or not state.pane_b_composition_id:
            msg = "Comparison pane view can only be updated for enabled composition compare."
            raise WorkspaceError(msg)
        if pane_key not in {"A", "B"}:
            msg = f"Comparison pane must be 'A' or 'B', got {pane!r}."
            raise WorkspaceError(msg)
        state_data = state.model_dump(mode="python")
        state_data["pane_a_center" if pane_key == "A" else "pane_b_center"] = list(center)
        next_state = TemporalCompareState.model_validate(state_data)
        updated = _mark_composition_edit_stale(
            _validated_composition_update(composition, {"temporal_compare": next_state})
        )
        self.write_composition(updated)
        return updated

    def update_grid_override(
        self,
        composition_id: str,
        *,
        degrees: int,
        minutes: int,
        seconds: float,
        label_format: str = "dms_full",
        style: dict[str, Any] | None = None,
    ) -> Composition:
        """Persist per-composition grid override and mark the composition stale."""
        composition = self.read_composition(composition_id)
        grid_override = GridConfig(
            interval=GridInterval(
                degrees=degrees,
                minutes=minutes,
                seconds=seconds,
            ),
            label_format=label_format.strip() or "dms_full",
            style=dict(style or {}),
        )
        updated = _mark_composition_edit_stale(
            _validated_composition_update(composition, {"grid_override": grid_override})
        )
        self.write_composition(updated)
        return updated

    def apply_include_transition(
        self,
        composition_id: str,
        *,
        validation_passed: bool,
    ) -> Composition:
        """Persist the right-arrow include transition after a caller-supplied pass gate."""
        if not validation_passed:
            msg = "Include transition requires a passing validation gate from the caller."
            raise WorkspaceError(msg)

        composition = self.read_composition(composition_id)
        review_order = composition.review_order or self._next_review_order()
        updated = _validated_composition_update(
            composition,
            {
                "reviewed": True,
                "ready": True,
                "include": True,
                "review_order": review_order,
            },
        )
        self.write_composition(updated)
        return updated

    def apply_skip_transition(self, composition_id: str) -> Composition:
        """Persist the up-arrow skip transition."""
        composition = self.read_composition(composition_id)
        updated = _validated_composition_update(
            composition,
            {
                "reviewed": True,
                "ready": False,
                "include": False,
                "review_order": None,
            },
        )
        self.write_composition(updated)
        return updated

    def next_composition_id(self, composition_id: str) -> str | None:
        """Return the next composition id in review queue order."""
        return self._neighbor_composition_id(composition_id, offset=1)

    def previous_composition_id(self, composition_id: str) -> str | None:
        """Return the previous composition id without mutating composition state."""
        return self._neighbor_composition_id(composition_id, offset=-1)

    def included_export_candidates(self) -> list[Composition]:
        """Return included compositions whose persisted state is not stale or errored.

        Epic 4 export preflight must still recompute detailed validation. This helper only
        prevents obviously stale persisted summaries from being treated as export-ready.
        """
        return [
            composition
            for composition in self.list_compositions()
            if composition.include
            and composition.ready
            and not composition.needs_revalidation
            and composition.validation_summary.error_count == 0
        ]

    def clear_plan(self) -> WorkspaceClearPlan:
        """Return the app-owned folders that destructive clearing would remove."""
        return WorkspaceClearPlan(
            cache=self.paths.cache,
            compositions=self.paths.compositions,
            renders=self.paths.renders,
            exports=self.paths.exports,
        )

    def has_app_owned_data(self) -> bool:
        """Return true when app-owned workspace folders contain any data."""
        return any(path.exists() and any(path.iterdir()) for path in self.paths.app_owned_dirs)

    def clear_app_owned_data(self, *, confirmed: bool = False) -> None:
        """Clear app-owned generated folders only after explicit confirmation."""
        if not confirmed:
            labels = ", ".join(self.clear_plan().labels)
            msg = f"Refusing to clear workspace data without confirmation: {labels}"
            raise WorkspaceClearNotConfirmedError(msg)

        for path in self.clear_plan().paths:
            if path.exists():
                shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)
        if self.paths.session_state.exists():
            self.paths.session_state.unlink()

        manifest = self.load_manifest()
        manifest.composition_ids = []
        self.write_manifest(manifest)

    def _ensure_layout(self) -> None:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        for directory in self.paths.app_owned_dirs:
            directory.mkdir(parents=True, exist_ok=True)

    def _resolve_layer_path(self, value: str) -> str:
        path = Path(value).expanduser()
        if path.is_absolute():
            return str(path)
        return str((self.paths.root / path).resolve())

    def _next_review_order(self) -> int:
        existing_orders = [
            composition.review_order
            for composition in self.list_compositions()
            if composition.include and composition.review_order is not None
        ]
        return max(existing_orders, default=0) + 1

    def _neighbor_composition_id(self, composition_id: str, *, offset: int) -> str | None:
        composition_ids = self.load_manifest().composition_ids
        try:
            index = composition_ids.index(composition_id)
        except ValueError:
            return None

        neighbor_index = index + offset
        if neighbor_index < 0 or neighbor_index >= len(composition_ids):
            return None
        return composition_ids[neighbor_index]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _validated_composition_update(
    composition: Composition,
    updates: dict[str, object | None],
) -> Composition:
    data = composition.model_dump(mode="python")
    data.update(updates)
    return Composition.model_validate(data)


def _mark_composition_edit_stale(composition: Composition) -> Composition:
    artifacts = composition.artifacts.model_copy(
        update={
            "final_render_path": None,
            "render_log_path": None,
        }
    )
    return _validated_composition_update(
        composition,
        {
            "artifacts": artifacts,
            "needs_revalidation": True,
            "ready": False,
            "include": False,
            "review_order": None,
        },
    )


def _has_visible_layer(composition: Composition) -> bool:
    return any(layer.visible for layer in composition.layers)


def _preserved_or_composition_center(
    state: TemporalCompareState,
    pane: str,
    composition_id: str | None,
    composition: Composition,
) -> list[float]:
    if pane == "A":
        if state.pane_a_composition_id == composition_id and state.pane_a_center is not None:
            return list(state.pane_a_center)
        return list(composition.view.center)
    if state.pane_b_composition_id == composition_id and state.pane_b_center is not None:
        return list(state.pane_b_center)
    return list(composition.view.center)


def _validate_render_artifact_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        msg = f"Render artifact path must stay workspace-relative: {value!r}"
        raise WorkspaceError(msg)
    normalized = path.as_posix()
    if not normalized.startswith("renders/"):
        msg = f"Render artifact path must be under renders/: {value!r}"
        raise WorkspaceError(msg)
    return normalized
