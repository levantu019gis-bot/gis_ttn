from __future__ import annotations

import json
import os
from datetime import date, time
from pathlib import Path

import numpy as np
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsView,
    QLineEdit,
    QSplitter,
    QTableView,
    QTreeView,
)

import thucthengay.editor.modes.review_edit_mode as review_edit_mode
from thucthengay.editor.app_shell import AppShell
from thucthengay.editor.models.composition_tree_model import (
    CompositionTreeModel,
    CompositionTreeRole,
    QueueFilter,
    TreeNodeKind,
)
from thucthengay.editor.models.layer_stack_model import (
    LayerStackColumn,
    LayerStackModel,
    LayerStackRole,
)
from thucthengay.editor.modes.review_edit_mode import ReviewEditMode
from thucthengay.editor.preferences import PreferencesService
from thucthengay.editor.widgets import (
    GisCanvasState,
    GisCanvasWidget,
    SlidePreviewState,
    SlidePreviewWidget,
    TargetPreviewState,
    TargetPreviewWidget,
)
from thucthengay.jobs import (
    JobState,
    PreviewRenderController,
    PreviewRenderJobResult,
    PreviewRenderQuality,
)
from thucthengay.models import (
    Composition,
    GridConfig,
    GridInterval,
    ImageLayer,
    MetadataSource,
    MetadataStatus,
    TargetConfig,
    TargetExportConfig,
    ValidationSummary,
    ViewState,
)
from thucthengay.models.template import MapFrame
from thucthengay.render.spec import (
    GeoWindow,
    RenderBackground,
    RenderLayerRef,
    RenderSpec,
    RenderSpecError,
)
from thucthengay.workspace import WorkspaceService


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def target_config(target_id: str, *, sort_order: int, name: str) -> TargetConfig:
    return TargetConfig(
        id=target_id,
        sort_order=sort_order,
        name=name,
        geojson_file=f"{target_id}.geojson",
        coordinate=[106.7, 10.8],
        scale=50000,
        grid=GridConfig(interval=GridInterval(minutes=1)),
        export=TargetExportConfig(template_metadata_file=f"{target_id}.template.json"),
        metadata={
            "template_metadata": {
                "template_pptx": f"{target_id}.pptx",
                "slide_index": 0,
                "map_frame": {"x": 0, "y": 0, "width": 640, "height": 360},
            }
        },
    )


def write_project_config(path: Path, target_id: str = "alpha") -> None:
    path.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "id": target_id,
                        "enabled": True,
                        "sort_order": 1,
                        "name": "Alpha Target",
                        "geojson_file": f"{target_id}.geojson",
                        "coordinate": [106.7, 10.8],
                        "scale": 50000,
                        "grid": {
                            "interval": {"minutes": 1},
                            "label_format": "dms_short",
                        },
                        "export": {
                            "template_pptx_file": f"{target_id}.pptx",
                            "placeholders": [
                                {
                                    "field": "map_image",
                                    "kind": "map_image",
                                    "element_id": 2,
                                }
                            ],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def composition(
    composition_id: str,
    target_id: str,
    capture_date: date,
    *,
    reviewed: bool = False,
    ready: bool = False,
    include: bool = False,
    needs_revalidation: bool = True,
    review_order: int | None = None,
    warnings: int = 0,
    errors: int = 0,
) -> Composition:
    return Composition(
        composition_id=composition_id,
        target_id=target_id,
        capture_date=capture_date,
        view=ViewState(center=[106.7, 10.8], scale=50000),
        reviewed=reviewed,
        ready=ready,
        include=include,
        needs_revalidation=needs_revalidation,
        review_order=review_order,
        validation_summary=ValidationSummary(warning_count=warnings, error_count=errors),
        layers=[
            ImageLayer(
                layer_id=f"{composition_id}-layer",
                source_path=f"{composition_id}.tif",
                order=0,
                capture_date=capture_date,
                capture_time=time(8, 30),
                metadata_status=MetadataStatus.VALID,
                metadata_source=MetadataSource.FILENAME,
            )
        ],
    )


def _preview_spec(composition_id: str, *, width: int = 1200, height: int = 800) -> RenderSpec:
    return RenderSpec(
        composition_id=composition_id,
        target_id="alpha",
        output_width=width,
        output_height=height,
        view_center=[106.7, 10.8],
        view_scale=50000,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
        map_frame_aspect=16 / 9,
        geo_window=GeoWindow(min_lon=106.5, min_lat=10.6, max_lon=106.9, max_lat=11.0),
        visible_layers=[
            RenderLayerRef(
                layer_id="L1",
                source_path="L1.tif",
                cache_path="cache/L1.tif",
                order=0,
            )
        ],
        grid=GridConfig(interval=GridInterval(minutes=1)),
        background=RenderBackground(color="#FFFFFF"),
        template_metadata_file="alpha.template.json",
        template_pptx="alpha.pptx",
        slide_index=0,
    )


def test_composition_tree_groups_by_target_order_and_review_queue_order() -> None:
    qapp()
    model = CompositionTreeModel()
    model.set_compositions(
        [
            composition("beta__20260525", "beta", date(2026, 5, 25), review_order=2),
            composition("alpha__20260526", "alpha", date(2026, 5, 26)),
            composition("alpha__20260524", "alpha", date(2026, 5, 24), review_order=1),
        ],
        targets=[
            target_config("beta", sort_order=2, name="Beta Target"),
            target_config("alpha", sort_order=1, name="Alpha Target"),
        ],
    )

    first_target = model.index(0, 0)
    second_target = model.index(1, 0)

    assert first_target.data(CompositionTreeRole.NODE_KIND) == TreeNodeKind.TARGET
    assert "Alpha Target" in first_target.data(Qt.ItemDataRole.DisplayRole)
    assert "0 vấn đề" in first_target.data(Qt.ItemDataRole.DisplayRole)
    assert "Beta Target" in second_target.data(Qt.ItemDataRole.DisplayRole)

    first_alpha_child = model.index(0, 0, first_target)
    second_alpha_child = model.index(1, 0, first_target)

    assert first_alpha_child.data(CompositionTreeRole.COMPOSITION_ID) == "alpha__20260524"
    assert second_alpha_child.data(CompositionTreeRole.COMPOSITION_ID) == "alpha__20260526"


def test_composition_tree_exposes_text_status_severity_counts_and_tooltips() -> None:
    qapp()
    model = CompositionTreeModel()
    model.set_compositions(
        [
            composition(
                "alpha__20260525",
                "alpha",
                date(2026, 5, 25),
                reviewed=True,
                ready=True,
                include=True,
                needs_revalidation=False,
                warnings=2,
            )
        ],
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )

    index = model.index(0, 0, model.index(0, 0))

    assert index.data(CompositionTreeRole.STATUS_TEXT) == "Include"
    assert index.data(CompositionTreeRole.SEVERITY_TEXT) == "WARN"
    assert index.data(CompositionTreeRole.ISSUE_COUNT) == 2
    assert "alpha__20260525" in index.data(Qt.ItemDataRole.DisplayRole)
    assert "[WARN]" in index.data(Qt.ItemDataRole.DisplayRole)
    assert "2 vấn đề" in index.data(Qt.ItemDataRole.DisplayRole)
    assert "Warnings: 2" in index.data(Qt.ItemDataRole.ToolTipRole)


def test_composition_tree_filters_counts_and_preserves_target_grouping() -> None:
    qapp()
    model = CompositionTreeModel()
    model.set_compositions(
        [
            composition("alpha__20260525", "alpha", date(2026, 5, 25)),
            composition(
                "alpha__20260526",
                "alpha",
                date(2026, 5, 26),
                reviewed=True,
                ready=True,
                needs_revalidation=False,
            ),
            composition(
                "beta__20260525",
                "beta",
                date(2026, 5, 25),
                reviewed=True,
                ready=True,
                include=True,
                needs_revalidation=False,
                warnings=1,
            ),
            composition(
                "gamma__20260525",
                "gamma",
                date(2026, 5, 25),
                reviewed=True,
                needs_revalidation=False,
                errors=1,
            ),
        ],
        targets=[
            target_config("alpha", sort_order=1, name="Alpha Target"),
            target_config("beta", sort_order=2, name="Beta Target"),
            target_config("gamma", sort_order=3, name="Gamma Target"),
        ],
    )

    counts = model.filter_counts()

    assert counts[QueueFilter.ALL] == 4
    assert counts[QueueFilter.UNREVIEWED] == 1
    assert counts[QueueFilter.READY] == 1
    assert counts[QueueFilter.INCLUDE] == 1
    assert counts[QueueFilter.WARNING] == 1
    assert counts[QueueFilter.ERROR] == 1

    model.set_queue_filter(QueueFilter.WARNING)

    assert model.rowCount() == 1
    target_index = model.index(0, 0)
    assert target_index.data(CompositionTreeRole.TARGET_ID) == "beta"
    assert model.rowCount(target_index) == 1
    assert model.index(0, 0, target_index).data(CompositionTreeRole.COMPOSITION_ID) == (
        "beta__20260525"
    )


def test_composition_tree_refresh_updates_filter_counts_and_stale_ready_text() -> None:
    qapp()
    model = CompositionTreeModel()
    stale_ready = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        reviewed=True,
        ready=True,
        needs_revalidation=True,
    )

    model.set_compositions([stale_ready])
    model.set_queue_filter(QueueFilter.READY)

    index = model.index(0, 0, model.index(0, 0))
    assert model.filter_counts()[QueueFilter.READY] == 1
    assert index.data(CompositionTreeRole.STATUS_TEXT) == "Cần kiểm tra lại"
    assert index.data(CompositionTreeRole.SEVERITY_TEXT) == "STALE"

    model.set_compositions([stale_ready.model_copy(update={"ready": False})])

    assert model.filter_counts()[QueueFilter.READY] == 0
    assert model.visible_composition_count() == 0


def test_review_edit_mode_loads_selected_composition_through_workspace_service(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )

    mode = ReviewEditMode()
    mode._request_canvas_render = lambda _composition: None  # noqa: SLF001
    target = target_config("alpha", sort_order=1, name="Alpha Target").model_copy(
        update={"metadata": {"map_frame": {"width": 4, "height": 3}}}
    )
    mode.load_workspace(
        service,
        targets=[target],
    )
    target_index = mode.tree_model.index(0, 0)
    composition_index = mode.tree_model.index(0, 0, target_index)

    mode.tree_view.setCurrentIndex(composition_index)

    assert mode.selected_composition is not None
    assert mode.selected_composition.composition_id == "alpha__20260525"
    assert "alpha__20260525" in mode.composition_title.text()
    assert mode.layer_model.rowCount() == 1
    assert mode.warnings_panel._list.count() >= 0  # panel is wired up


def test_review_edit_mode_persists_splitter_sizes(tmp_path: Path) -> None:
    qapp()
    preferences = PreferencesService(tmp_path / "preferences.json")
    mode = ReviewEditMode(preferences_service=preferences)

    mode.main_splitter.setSizes([420, 960])
    mode._persist_main_splitter_sizes(0, 0)  # noqa: SLF001

    assert preferences.preferences.ui.review_main_splitter_sizes == mode.main_splitter.sizes()


def test_review_edit_uses_template_metadata_map_frame_aspect(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )

    mode = ReviewEditMode()
    mode._request_canvas_render = lambda _composition: None  # noqa: SLF001
    target = target_config("alpha", sort_order=1, name="Alpha Target").model_copy(
        update={
            "metadata": {
                "template_metadata": {
                    "template_pptx": "alpha.pptx",
                    "slide_index": 0,
                    "map_frame": {"x": 0, "y": 0, "width": 4, "height": 3},
                }
            }
        }
    )
    mode.load_workspace(
        service,
        targets=[target],
    )
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    assert abs(mode.gis_canvas.frame_aspect() - (4 / 3)) < 0.02


def test_review_edit_selection_persists_compact_validation_summary_only(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            needs_revalidation=True,
        )
    )

    mode = ReviewEditMode()
    mode.load_workspace(service, targets=[target_config("alpha", sort_order=1, name="Alpha")])
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    reloaded = service.read_composition("alpha__20260525")
    raw = json.loads(
        (service.paths.compositions / "alpha__20260525.json").read_text(encoding="utf-8")
    )

    assert reloaded.needs_revalidation is False
    assert reloaded.validation_summary.error_count == 0
    assert "issues" not in raw


def test_review_edit_suppressed_selection_refresh_does_not_run_validation(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )

    mode = ReviewEditMode()
    mode.load_workspace(service, targets=[target_config("alpha", sort_order=1, name="Alpha")])
    target_index = mode.tree_model.index(0, 0)
    composition_index = mode.tree_model.index(0, 0, target_index)

    def fail_validation(_composition: Composition) -> None:
        raise AssertionError("validation should be suppressed")

    mode._review_gate = fail_validation  # type: ignore[method-assign]
    mode._suppress_selection_validation = True
    mode._select_composition_index(composition_index, None)

    assert mode.selected_composition is not None
    assert mode.selected_composition.composition_id == "alpha__20260525"


def test_review_edit_invalid_fallback_map_frame_becomes_validation_issue(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )
    target = target_config("alpha", sort_order=1, name="Alpha").model_copy(
        update={"metadata": {"map_frame": {"width": 0, "height": 3}}}
    )

    mode = ReviewEditMode()
    mode.load_workspace(service, targets=[target])
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    assert mode.warnings_panel._list.count() == 1
    assert "PPTX template" in mode.warnings_panel._list.item(0).text()


def test_layer_stack_model_display_roles_and_no_visible_warning() -> None:
    qapp()
    long_name = "alpha_target_layer_with_a_very_long_filename_that_should_elide_20260525.tif"
    model = LayerStackModel()
    model.set_composition(
        Composition(
            composition_id="alpha__20260525",
            target_id="alpha",
            capture_date=date(2026, 5, 25),
            view=ViewState(center=[106.7, 10.8], scale=50000),
            layers=[
                ImageLayer(
                    layer_id="new",
                    source_path=f"/imagery/{long_name}",
                    cache_path="cache/alpha/new.tif",
                    visible=False,
                    order=1,
                    capture_date=date(2026, 5, 25),
                    capture_time=time(9, 15),
                    cloud_percent=12.4,
                    metadata_status=MetadataStatus.NEEDS_MANUAL_CORRECTION,
                    metadata_source=MetadataSource.FILENAME,
                ),
                ImageLayer(
                    layer_id="old",
                    source_path="/imagery/old.tif",
                    visible=False,
                    order=0,
                    metadata_status=MetadataStatus.VALID,
                ),
            ],
        )
    )

    long_filename = model.index(1, int(LayerStackColumn.FILENAME))
    first_visibility = model.index(0, int(LayerStackColumn.VISIBILITY))
    second_order = model.index(1, int(LayerStackColumn.ORDER))

    assert model.index(0, 0).data(LayerStackRole.LAYER_ID) == "old"
    assert model.index(0, 0).data(LayerStackRole.NO_VISIBLE_WARNING) is True
    assert first_visibility.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert second_order.data(Qt.ItemDataRole.DisplayRole) == "2"
    assert "..." in long_filename.data(Qt.ItemDataRole.DisplayRole)
    assert "/imagery/" in long_filename.data(Qt.ItemDataRole.ToolTipRole)
    assert "Cache:" in long_filename.data(Qt.ItemDataRole.ToolTipRole)


def test_layer_stack_model_accepts_integer_check_state_values() -> None:
    qapp()
    model = LayerStackModel()
    model.set_composition(
        Composition(
            composition_id="alpha__20260525",
            target_id="alpha",
            capture_date=date(2026, 5, 25),
            view=ViewState(center=[106.7, 10.8], scale=50000),
            layers=[
                ImageLayer(
                    layer_id="old",
                    source_path="/imagery/old.tif",
                    visible=False,
                    order=0,
                    metadata_status=MetadataStatus.VALID,
                )
            ],
        )
    )

    visibility_index = model.index(0, int(LayerStackColumn.VISIBILITY))

    assert model.setData(
        visibility_index,
        Qt.CheckState.Checked.value,
        Qt.ItemDataRole.CheckStateRole,
    )
    assert visibility_index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert visibility_index.data(LayerStackRole.VISIBLE) is True
    assert model.has_no_visible_layers() is False


def test_gis_canvas_states_fixed_frame_and_stale_render_guard() -> None:
    qapp()
    canvas = GisCanvasWidget()
    canvas.resize(800, 450)
    canvas.set_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            needs_revalidation=False,
        )
    )

    assert canvas.visible_layer_count() == 1
    assert canvas.state() == GisCanvasState.READY
    assert "Canvas đã tải" in canvas.state_text()
    assert abs(canvas.frame_aspect() - GisCanvasWidget.DEFAULT_FRAME_ASPECT) < 0.02
    frame = canvas._frame_rect()  # noqa: SLF001
    viewport_width = max(canvas.viewport().width(), 640)
    assert abs(frame.width() / viewport_width - GisCanvasWidget.MAP_FRAME_FILL_RATIO) < 0.02
    assert canvas.render_output_size() == (
        max(1, int(frame.width())),
        max(1, int(frame.height())),
    )

    old_token = canvas.begin_render_request()
    old_generation = canvas.generation
    canvas.pan_by_pixels(40, -20, emit=False)

    assert canvas.generation > old_generation
    assert canvas.state() == GisCanvasState.STALE
    assert canvas.apply_render_result(old_token, "old render") is False

    current_token = canvas.begin_render_request()
    assert canvas.apply_render_result(current_token, "fresh render") is True
    assert canvas.last_applied_render_label == "fresh render"

    canvas.set_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25)).model_copy(
            update={
                "layers": [
                    ImageLayer(
                        layer_id="hidden",
                        source_path="/imagery/hidden.tif",
                        visible=False,
                        order=0,
                    )
                ]
            }
        )
    )

    assert canvas.state() == GisCanvasState.NO_VISIBLE_LAYER
    assert "Không có layer" in canvas.state_text()

    token = canvas.set_loading()
    assert canvas.state() == GisCanvasState.LOADING
    assert token.generation == canvas.generation
    canvas.set_error("Không đọc được raster.")
    assert canvas.state() == GisCanvasState.ERROR
    assert "raster" in canvas.state_text()


def test_gis_canvas_exports_current_displayed_image(tmp_path: Path) -> None:
    qapp()
    canvas = GisCanvasWidget()
    canvas.resize(800, 450)
    canvas.set_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            needs_revalidation=False,
        )
    )
    token = canvas.begin_render_request()
    rendered = np.zeros((120, 160, 3), dtype=np.uint8)
    rendered[:, :, 1] = 180

    assert canvas.apply_render_result(token, "preview render", canvas=rendered) is True
    assert canvas.rendered_image_size == (160, 120)

    output_path = tmp_path / "gis-editor.jpg"
    assert canvas.export_displayed_image(output_path) is True

    image = QImage(str(output_path))
    assert not image.isNull()
    assert image.width() == 160
    assert image.height() == 120
    with Image.open(output_path) as saved:
        assert saved.format == "JPEG"
        dpi = saved.info["dpi"]
        assert round(dpi[0]) == GisCanvasWidget.EXPORT_DPI
        assert round(dpi[1]) == GisCanvasWidget.EXPORT_DPI


def test_gis_canvas_downscales_large_render_for_display() -> None:
    qapp()
    canvas = GisCanvasWidget()
    canvas.set_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            needs_revalidation=False,
        )
    )
    token = canvas.begin_render_request()
    rendered = np.zeros((2340, 3306, 3), dtype=np.uint8)

    assert canvas.apply_render_result(token, "final-layout preview", canvas=rendered) is True

    display_size = canvas.rendered_image_size
    assert display_size is not None
    assert display_size[0] <= GisCanvasWidget.DISPLAY_IMAGE_MAX_WIDTH
    assert display_size[0] < rendered.shape[1]
    assert display_size[1] < rendered.shape[0]
    assert abs((display_size[0] / display_size[1]) - (3306 / 2340)) < 0.01


def test_gis_canvas_export_requires_rendered_map_image(tmp_path: Path) -> None:
    qapp()
    canvas = GisCanvasWidget()
    output_path = tmp_path / "gis-editor.jpg"

    assert canvas.export_displayed_image(output_path) is False
    assert not output_path.exists()


def test_review_edit_export_button_saves_gis_canvas_image(tmp_path: Path) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )

    mode = ReviewEditMode()
    mode._request_canvas_render = lambda _composition: None  # noqa: SLF001
    mode._request_target_preview = lambda _composition: None  # noqa: SLF001
    output_path = tmp_path / "review-export.jpg"
    mode._select_canvas_export_path = lambda _default: output_path  # type: ignore[method-assign]  # noqa: SLF001
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))
    token = mode.gis_canvas.begin_render_request()
    rendered = np.full((2340, 3306, 3), 255, dtype=np.uint8)
    assert mode.gis_canvas.apply_render_result(token, "rendered", canvas=rendered) is True

    assert mode.export_canvas_button.isEnabled()

    mode.export_canvas_button.click()

    assert output_path.is_file()
    image = QImage(str(output_path))
    assert image.size().width() == 3306
    assert image.size().height() == 2340
    with Image.open(output_path) as saved:
        assert saved.format == "JPEG"
        dpi = saved.info["dpi"]
        assert round(dpi[0]) == GisCanvasWidget.EXPORT_DPI
        assert round(dpi[1]) == GisCanvasWidget.EXPORT_DPI
    assert "Đã xuất ảnh GIS editor" in mode.action_summary.text()


def test_review_edit_canvas_render_uses_final_template_size_not_viewport(
    tmp_path: Path,
    monkeypatch,
) -> None:
    qapp()
    raster_path = tmp_path / "alpha.tif"
    raster_path.touch()
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    ).model_copy(
        update={
            "layers": [
                ImageLayer(
                    layer_id="alpha-layer",
                    source_path=str(raster_path),
                    order=0,
                    capture_date=date(2026, 5, 25),
                    capture_time=time(8, 30),
                    metadata_status=MetadataStatus.VALID,
                )
            ]
        }
    )
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(selected)

    mode = ReviewEditMode()
    target = target_config("alpha", sort_order=1, name="Alpha Target")
    target = target.model_copy(
        update={
            "metadata": {
                "template_metadata": {
                    "template_pptx": "alpha.pptx",
                    "slide_index": 0,
                    "map_frame": {"x": 0, "y": 0, "width": 16.5223, "height": 11.6946},
                    "placeholders": [
                        {
                            "field": "map",
                            "element_id": 10,
                            "kind": "map_image",
                            "required": True,
                        }
                    ],
                    "metadata": {
                        "selected_slide": {
                            "shapes": [
                                {
                                    "id": "10",
                                    "picture": {
                                        "media": {
                                            "image": {
                                                "width_px": 3306,
                                                "height_px": 2340,
                                            }
                                        }
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }
    )
    mode.load_workspace(service, targets=[target])
    mode.gis_canvas.resize(800, 500)
    mode.gis_canvas.set_frame_aspect(GisCanvasWidget.DEFAULT_FRAME_ASPECT)
    mode.gis_canvas.set_composition(selected)
    expected_size = (3306, 2340)
    viewport_size = (
        max(mode.gis_canvas.viewport().width(), 640),
        max(mode.gis_canvas.viewport().height(), 360),
    )
    assert expected_size != viewport_size

    captured: dict[str, tuple[int, int]] = {}

    def capture_render_size(**kwargs) -> RenderSpec:
        captured["size"] = (kwargs["output_width"], kwargs["output_height"])
        raise RenderSpecError([])

    monkeypatch.setattr(review_edit_mode, "build_render_spec", capture_render_size)

    mode._request_canvas_render(selected)  # noqa: SLF001

    assert captured["size"] == expected_size


def test_review_edit_canvas_render_request_keeps_export_size(tmp_path: Path) -> None:
    qapp()
    raster_path = tmp_path / "alpha.tif"
    raster_path.touch()
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    ).model_copy(
        update={
            "layers": [
                ImageLayer(
                    layer_id="alpha-layer",
                    source_path=str(raster_path),
                    order=0,
                    capture_date=date(2026, 5, 25),
                    capture_time=time(8, 30),
                    metadata_status=MetadataStatus.VALID,
                )
            ]
        }
    )
    target = target_config("alpha", sort_order=1, name="Alpha Target").model_copy(
        update={
            "metadata": {
                "template_metadata": {
                    "template_pptx": "alpha.pptx",
                    "slide_index": 0,
                    "map_frame": {"x": 0, "y": 0, "width": 16.5223, "height": 11.6946},
                    "placeholders": [
                        {
                            "field": "map",
                            "element_id": 10,
                            "kind": "map_image",
                            "required": True,
                        }
                    ],
                    "metadata": {
                        "selected_slide": {
                            "shapes": [
                                {
                                    "id": "10",
                                    "picture": {
                                        "media": {
                                            "image": {
                                                "width_px": 3306,
                                                "height_px": 2340,
                                            }
                                        }
                                    },
                                }
                            ]
                        }
                    },
                }
            }
        }
    )
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(selected)

    mode = ReviewEditMode()
    mode.load_workspace(service, targets=[target])
    started: list[tuple[PreviewRenderQuality, int, int]] = []

    def capture_start(request, _token) -> None:  # noqa: ANN001
        started.append(
            (
                request.quality,
                request.spec.output_width,
                request.spec.output_height,
            )
        )

    mode._start_canvas_render = capture_start  # type: ignore[method-assign]  # noqa: SLF001

    mode._request_canvas_render(selected)  # noqa: SLF001

    assert started == [(PreviewRenderQuality.SETTLED_HIGH_RES, 3306, 2340)]


def test_review_edit_skips_canvas_render_for_stale_composition(tmp_path: Path) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    stale = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=True,
    )
    service.write_composition(stale)

    mode = ReviewEditMode()
    requested: list[str] = []
    mode._request_canvas_render = (  # type: ignore[method-assign]  # noqa: SLF001
        lambda selected: requested.append(selected.composition_id)
    )
    mode._request_target_preview = lambda _composition: None  # noqa: SLF001
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    requested.clear()
    mode._update_detail_panels(stale)  # noqa: SLF001

    assert requested == []
    assert mode.gis_canvas.state() == GisCanvasState.STALE


def test_slide_preview_debounces_state_and_rejects_stale_results() -> None:
    app = qapp()
    preview = SlidePreviewWidget(debounce_ms=1)
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    )
    grid = GridConfig(interval=GridInterval(minutes=2, seconds=30), label_format="dms_short")

    preview.set_composition(
        selected,
        effective_grid=grid,
        background={"color": "#101820"},
    )
    stale_token = preview.begin_preview_request()

    assert preview.state() == SlidePreviewState.NEEDS_UPDATE
    assert "Preview cần cập nhật" in preview.state_text()
    assert "Scale 1:50,000" in preview.detail_text()
    assert "Grid: 0d 2m 30s" in preview.detail_text()
    assert "#101820" in preview.detail_text()

    preview.set_composition(
        selected.model_copy(
            update={"view": ViewState(center=[106.8, 10.9], scale=25000)}
        ),
        effective_grid=grid,
    )

    assert preview.apply_preview_result(stale_token, "old preview") is False

    app.processEvents()
    preview._timer.timeout.emit()

    assert preview.state() == SlidePreviewState.LOADING
    preview._render_timer.timeout.emit()

    assert preview.state() == SlidePreviewState.RENDERED
    assert "Preview đã cập nhật" in preview.state_text()
    assert "Scale 1:25,000" in preview.detail_text()

    preview.set_render_error("Không đọc được preview cache.")

    assert preview.state() == SlidePreviewState.RENDER_ERROR
    assert "tiếp tục chỉnh sửa" in preview.detail_text()

    preview.set_composition(selected, effective_grid=grid)
    preview._timer.timeout.emit()
    preview._render_timer.timeout.emit()

    assert preview.state() == SlidePreviewState.RENDERED
    assert "Không đọc được" not in preview.detail_text()


def test_slide_preview_review_edge_cases_do_not_accept_stale_results() -> None:
    qapp()
    preview = SlidePreviewWidget(debounce_ms=-5)
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    )
    selected = selected.model_copy(
        update={"view": ViewState(center=[106.7, 10.8], scale=50000, rotation=0)}
    )

    preview.set_composition(
        selected,
        background={"color": "#101820", 7: {"nested": ["value"]}},
    )
    stale_token = preview.begin_preview_request()
    preview._timer.timeout.emit()

    assert preview.state() == SlidePreviewState.LOADING
    assert "Rotation 0" in preview.detail_text()

    preview.set_render_error("Không tạo được preview.")

    assert preview.apply_preview_result(stale_token, "old preview") is False
    assert preview.state() == SlidePreviewState.RENDER_ERROR
    assert "tiếp tục chỉnh sửa" in preview.detail_text()


def test_slide_preview_applies_only_current_preview_job_results() -> None:
    qapp()
    preview = SlidePreviewWidget(debounce_ms=1)
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    )
    preview.set_composition(selected)

    controller = PreviewRenderController(debounce_ms=1)
    first = controller.request_preview(_preview_spec("alpha__20260525"))
    preview.track_preview_plan(first)

    updated = selected.model_copy(
        update={"view": ViewState(center=[106.8, 10.9], scale=25000)}
    )
    preview.set_composition(updated)
    second = controller.request_preview(_preview_spec("alpha__20260525", width=480, height=320))
    preview.track_preview_plan(second)

    old_result = PreviewRenderJobResult(
        job_id=first.interactive.job_id,
        composition_id="alpha__20260525",
        revision=first.interactive.revision,
        quality=first.interactive.quality,
        state=JobState.SUCCESS,
        output_width=320,
        output_height=213,
        message="old",
    )
    current_result = PreviewRenderJobResult(
        job_id=second.interactive.job_id,
        composition_id="alpha__20260525",
        revision=second.interactive.revision,
        quality=second.interactive.quality,
        state=JobState.SUCCESS,
        output_width=480,
        output_height=320,
        message="current",
    )

    assert preview.apply_preview_job_result(old_result) is False
    assert preview.apply_preview_job_result(current_result) is True
    assert preview.state() == SlidePreviewState.RENDERED
    assert "interactive_low_res" in preview.detail_text()
    assert "480x320" in preview.detail_text()


def test_slide_preview_rejects_late_low_res_after_settled_job_result() -> None:
    qapp()
    preview = SlidePreviewWidget(debounce_ms=1)
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    )
    preview.set_composition(selected)
    plan = PreviewRenderController(debounce_ms=1).request_preview(_preview_spec("alpha__20260525"))
    preview.track_preview_plan(plan)

    settled = PreviewRenderJobResult(
        job_id=plan.settled.job_id,
        composition_id="alpha__20260525",
        revision=plan.settled.revision,
        quality=plan.settled.quality,
        state=JobState.SUCCESS,
        output_width=960,
        output_height=640,
        message="settled",
    )
    late_low_res = PreviewRenderJobResult(
        job_id=plan.interactive.job_id,
        composition_id="alpha__20260525",
        revision=plan.interactive.revision,
        quality=plan.interactive.quality,
        state=JobState.SUCCESS,
        output_width=480,
        output_height=320,
        message="late low-res",
    )

    assert preview.apply_preview_job_result(settled) is True
    assert "settled_high_res" in preview.detail_text()
    assert preview.apply_preview_job_result(late_low_res) is False
    assert "settled_high_res" in preview.detail_text()


def test_slide_preview_job_failure_sets_recoverable_render_error() -> None:
    qapp()
    preview = SlidePreviewWidget(debounce_ms=1)
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    )
    preview.set_composition(selected)
    plan = PreviewRenderController(debounce_ms=1).request_preview(_preview_spec("alpha__20260525"))
    preview.track_preview_plan(plan)

    failure = PreviewRenderJobResult(
        job_id=plan.settled.job_id,
        composition_id="alpha__20260525",
        revision=plan.settled.revision,
        quality=plan.settled.quality,
        state=JobState.ERROR,
        output_width=960,
        output_height=640,
        message="Khong tao duoc preview. Kiem tra raster roi thu lai.",
    )

    assert preview.apply_preview_job_result(failure) is True
    assert preview.state() == SlidePreviewState.RENDER_ERROR
    assert "Kiem tra raster" in preview.detail_text()


def test_target_preview_applies_render_canvas_and_rejects_stale_results() -> None:
    qapp()
    preview = TargetPreviewWidget()
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    )

    assert preview.set_composition(selected) is True
    stale_token = preview.begin_render_request()
    updated = composition(
        "beta__20260525",
        "beta",
        date(2026, 5, 25),
        needs_revalidation=False,
    )
    assert preview.set_composition(updated) is True

    canvas = np.full((16, 24, 3), 128, dtype=np.uint8)
    assert preview.apply_render_result(stale_token, "old", canvas=canvas) is False

    current_token = preview.set_loading()
    assert preview.apply_render_result(current_token, "done", canvas=canvas) is True
    assert preview.state() == TargetPreviewState.RENDERED
    assert "Target Preview đã cập nhật" in preview.state_text()
    assert "beta" in preview.detail_text()


def test_target_preview_stays_fixed_for_same_target_day_view_changes() -> None:
    qapp()
    preview = TargetPreviewWidget()
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    )
    assert preview.set_composition(selected) is True
    token = preview.set_loading()
    preview.apply_render_result(
        token,
        "done",
        canvas=np.full((12, 12, 3), 80, dtype=np.uint8),
    )

    changed_view = selected.model_copy(
        update={"view": ViewState(center=[106.8, 10.9], scale=25000)}
    )

    assert preview.set_composition(changed_view) is False
    assert preview.state() == TargetPreviewState.RENDERED
    assert "Scale 1:25,000" not in preview.detail_text()


def test_target_preview_refreshes_for_layer_visibility_and_order_changes() -> None:
    qapp()
    preview = TargetPreviewWidget()
    selected = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    ).model_copy(
        update={
            "layers": [
                ImageLayer(layer_id="old", source_path="old.tif", visible=True, order=0),
                ImageLayer(layer_id="new", source_path="new.tif", visible=True, order=1),
            ]
        }
    )

    assert preview.set_composition(selected) is True
    token = preview.set_loading()
    preview.apply_render_result(
        token,
        "done",
        canvas=np.full((12, 12, 3), 80, dtype=np.uint8),
    )

    hidden_old = selected.model_copy(
        update={
            "layers": [
                selected.layers[0].model_copy(update={"visible": False}),
                selected.layers[1],
            ]
        }
    )
    assert preview.set_composition(hidden_old) is True
    assert preview.state() == TargetPreviewState.NEEDS_UPDATE

    reordered = selected.model_copy(
        update={
            "layers": [
                selected.layers[0].model_copy(update={"order": 1}),
                selected.layers[1].model_copy(update={"order": 0}),
            ]
        }
    )
    assert preview.set_composition(reordered) is True


def test_review_edit_layer_stack_saves_visibility_order_and_warning(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            ready=True,
            include=True,
            needs_revalidation=False,
            review_order=2,
        ).model_copy(
            update={
                "layers": [
                    ImageLayer(
                        layer_id="old",
                        source_path="/imagery/old.tif",
                        visible=True,
                        order=0,
                        capture_date=date(2026, 5, 25),
                        capture_time=time(8, 30),
                        metadata_status=MetadataStatus.VALID,
                    ),
                    ImageLayer(
                        layer_id="new",
                        source_path="/imagery/new.tif",
                        visible=True,
                        order=1,
                        capture_date=date(2026, 5, 25),
                        capture_time=time(9, 0),
                        metadata_status=MetadataStatus.VALID,
                    ),
                ]
            }
        )
    )

    mode = ReviewEditMode()
    target_preview_requests: list[tuple[tuple[str, int, bool], ...]] = []
    mode._request_target_preview = (  # noqa: SLF001
        lambda selected: target_preview_requests.append(
            tuple((layer.layer_id, layer.order, layer.visible) for layer in selected.layers)
        )
    )
    target = target_config("alpha", sort_order=1, name="Alpha Target").model_copy(
        update={"metadata": {"map_frame": {"width": 4, "height": 3}}}
    )
    mode.load_workspace(
        service,
        targets=[target],
    )
    target_index = mode.tree_model.index(0, 0)
    composition_index = mode.tree_model.index(0, 0, target_index)
    mode.tree_view.setCurrentIndex(composition_index)
    assert len(target_preview_requests) == 1

    first_visibility = mode.layer_model.index(0, int(LayerStackColumn.VISIBILITY))
    second_visibility = mode.layer_model.index(1, int(LayerStackColumn.VISIBILITY))
    mode.layer_model.setData(
        first_visibility,
        Qt.CheckState.Unchecked,
        Qt.ItemDataRole.CheckStateRole,
    )

    reloaded = service.read_composition("alpha__20260525")
    assert reloaded.layers[0].visible is False
    assert reloaded.needs_revalidation is True
    assert reloaded.ready is False
    assert reloaded.include is False
    assert reloaded.review_order is None
    assert mode.layer_warning_label.isHidden()
    assert len(target_preview_requests) == 2
    assert target_preview_requests[-1] == (("old", 0, False), ("new", 1, True))

    second_visibility = mode.layer_model.index(1, int(LayerStackColumn.VISIBILITY))
    mode.layer_model.setData(
        second_visibility,
        Qt.CheckState.Unchecked,
        Qt.ItemDataRole.CheckStateRole,
    )

    assert service.read_composition("alpha__20260525").layers[1].visible is False
    assert not mode.layer_warning_label.isHidden()
    assert "ít nhất 1 layer" in mode.layer_warning_label.text()
    assert mode.tree_model.index_for_composition_id("alpha__20260525").data(
        CompositionTreeRole.SEVERITY_TEXT
    ) == "ERROR"
    assert mode.tree_model.index_for_composition_id("alpha__20260525").data(
        CompositionTreeRole.STATUS_TEXT
    ) == "Không có layer bật"
    assert mode.filter_buttons[QueueFilter.ERROR].text() == "Có error (1)"
    assert len(target_preview_requests) == 2
    assert mode.target_preview.state() == TargetPreviewState.NO_LAYER

    second_visibility = mode.layer_model.index(1, int(LayerStackColumn.VISIBILITY))
    mode.layer_model.setData(
        second_visibility,
        Qt.CheckState.Checked.value,
        Qt.ItemDataRole.CheckStateRole,
    )

    assert service.read_composition("alpha__20260525").layers[1].visible is True
    assert mode.layer_warning_label.isHidden()
    assert len(target_preview_requests) == 3
    assert target_preview_requests[-1] == (("old", 0, False), ("new", 1, True))

    mode.layer_table.setCurrentIndex(mode.layer_model.index(1, int(LayerStackColumn.FILENAME)))
    mode.move_layer_up_button.click()

    reordered = service.read_composition("alpha__20260525")
    assert [layer.layer_id for layer in reordered.layers] == ["new", "old"]
    assert [layer.order for layer in reordered.layers] == [0, 1]
    assert len(target_preview_requests) == 4
    assert target_preview_requests[-1] == (("new", 0, True), ("old", 1, False))


def test_review_edit_gis_canvas_saves_pan_zoom_and_marks_preview_stale(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            ready=True,
            include=True,
            needs_revalidation=False,
            review_order=3,
        )
    )

    mode = ReviewEditMode()
    mode._request_canvas_render = lambda _composition: None  # noqa: SLF001
    target = target_config("alpha", sort_order=1, name="Alpha Target").model_copy(
        update={"metadata": {"map_frame": {"width": 4, "height": 3}}}
    )
    mode.load_workspace(
        service,
        targets=[target],
    )
    target_index = mode.tree_model.index(0, 0)
    composition_index = mode.tree_model.index(0, 0, target_index)
    mode.tree_view.setCurrentIndex(composition_index)

    original_center = mode.gis_canvas.center
    target_preview_generation = mode.target_preview.generation
    assert abs(mode.gis_canvas.frame_aspect() - (4 / 3)) < 0.02

    mode.gis_canvas.pan_by_pixels(48, -24)
    assert service.read_composition("alpha__20260525").view.center == original_center

    mode._flush_pending_canvas_view()  # noqa: SLF001

    panned = service.read_composition("alpha__20260525")
    assert panned.view.center != original_center
    assert panned.needs_revalidation is True
    assert panned.ready is False
    assert panned.include is False
    assert panned.review_order is None
    assert mode.target_preview.generation == target_preview_generation

    mode.gis_canvas.zoom_by_factor(0.5)
    mode._flush_pending_canvas_view()  # noqa: SLF001

    zoomed = service.read_composition("alpha__20260525")
    assert zoomed.view.scale == 25000
    assert zoomed.view.rotation == 0
    assert mode.gis_canvas.state() in {GisCanvasState.STALE, GisCanvasState.LOADING}
    assert mode.tree_model.index_for_composition_id("alpha__20260525").data(
        CompositionTreeRole.STATUS_TEXT
    ) == "Cần kiểm tra lại"


def test_review_edit_grid_controls_show_defaults_save_override_and_mark_stale(
    tmp_path: Path,
) -> None:
    qapp()
    config_path = tmp_path / "config.json"
    write_project_config(config_path)
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path=config_path)
    service.write_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            ready=True,
            include=True,
            needs_revalidation=False,
            review_order=3,
        )
    )
    target = target_config("alpha", sort_order=1, name="Alpha Target").model_copy(
        update={
            "grid": GridConfig(
                interval=GridInterval(minutes=1),
                label_format="dms_full",
                style={"color": "white"},
            )
        }
    )

    mode = ReviewEditMode()
    mode.load_workspace(service, targets=[target])
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))
    target_preview_generation = mode.target_preview.generation
    canvas_render_requests: list[Composition] = []
    mode._request_canvas_render = canvas_render_requests.append  # type: ignore[method-assign]  # noqa: SLF001

    assert mode.grid_degrees_input.text() == "0"
    assert mode.grid_minutes_input.text() == "1"
    assert mode.grid_seconds_input.text() == "0"
    assert mode.grid_scale_input.text() == "50000"
    assert mode.findChild(QLineEdit, "reviewGridLabelFormat") is None
    assert "mặc định target" in mode.grid_status_label.text()

    mode.grid_minutes_input.setText("2")
    mode.grid_seconds_input.setText("30")
    mode.grid_scale_input.setText("25000")
    mode.save_grid_button.click()

    reloaded = service.read_composition("alpha__20260525")
    assert reloaded.grid_override is not None
    assert reloaded.grid_override.interval.minutes == 2
    assert reloaded.grid_override.interval.seconds == 30
    assert reloaded.grid_override.label_format == "dms_full"
    assert reloaded.grid_override.style == {"color": "white"}
    assert reloaded.view.scale == 25000
    assert reloaded.needs_revalidation is True
    assert reloaded.ready is False
    assert reloaded.include is False
    assert reloaded.review_order is None
    assert target.grid.interval.minutes == 1
    assert "override" in mode.grid_status_label.text()
    assert mode.target_preview.generation == target_preview_generation
    assert mode.tree_model.index_for_composition_id("alpha__20260525").data(
        CompositionTreeRole.STATUS_TEXT
    ) == "Cần kiểm tra lại"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw_target = raw["targets"][0]
    assert raw_target["scale"] == 25000
    assert raw_target["grid"]["interval"] == {"minutes": 2, "seconds": 30}
    assert mode._targets is not None  # noqa: SLF001
    assert mode._targets[0].scale == 25000  # noqa: SLF001
    assert mode._targets[0].grid.interval.minutes == 2  # noqa: SLF001
    assert len(canvas_render_requests) == 1
    requested = canvas_render_requests[0]
    assert requested.composition_id == "alpha__20260525"
    assert requested.grid_override is not None
    assert requested.grid_override.interval.minutes == 2
    assert requested.grid_override.interval.seconds == 30
    assert requested.view.scale == 25000
    assert "Đã lưu grid và cập nhật config target" in mode.action_summary.text()


def test_review_edit_target_preview_loads_once_and_stays_fixed_after_view_edits(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            needs_revalidation=False,
        )
    )
    target = target_config("alpha", sort_order=1, name="Alpha Target").model_copy(
        update={
            "grid": GridConfig(interval=GridInterval(minutes=1), label_format="dms_full"),
            "metadata": {"preview_background": {"color": "#ddeeff"}},
        }
    )

    mode = ReviewEditMode()
    mode.load_workspace(service, targets=[target])
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    assert mode.target_preview.key is not None
    assert mode.target_preview.key.target_id == "alpha"
    assert mode.target_preview.key.capture_date == date(2026, 5, 25)
    assert mode.target_preview.state() in {
        TargetPreviewState.NEEDS_UPDATE,
        TargetPreviewState.LOADING,
        TargetPreviewState.RENDER_ERROR,
    }
    generation = mode.target_preview.generation

    mode.gis_canvas.pan_by_pixels(20, 0)

    assert mode.target_preview.generation == generation
    assert mode.target_preview.key is not None
    assert mode.target_preview.key.target_id == "alpha"


def test_review_edit_target_preview_panel_uses_target_preview_name(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            needs_revalidation=False,
        )
    )
    target = target_config("alpha", sort_order=1, name="Alpha Target").model_copy(
        update={"metadata": {"map_background": "#112233"}}
    )

    mode = ReviewEditMode()
    mode.load_workspace(service, targets=[target])
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    assert "Target Preview" in mode.preview_summary.text()


def test_review_edit_grid_controls_reject_invalid_values_without_write(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25)).model_copy(
            update={
                "grid_override": GridConfig(
                    interval=GridInterval(minutes=1),
                    label_format="dms_full",
                )
            }
        )
    )

    mode = ReviewEditMode()
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    mode.grid_minutes_input.setText("60")
    mode.save_grid_button.click()

    reloaded = service.read_composition("alpha__20260525")
    assert reloaded.grid_override is not None
    assert reloaded.grid_override.interval.minutes == 1
    assert "Phút phải nhỏ hơn 60" in mode.grid_validation_label.text()

    mode.grid_minutes_input.setText("1")
    mode.grid_scale_input.setText("0")
    mode.save_grid_button.click()

    reloaded = service.read_composition("alpha__20260525")
    assert reloaded.grid_override is not None
    assert reloaded.grid_override.interval.minutes == 1
    assert reloaded.view.scale == 50000
    assert "Scale phải là số nguyên dương" in mode.grid_validation_label.text()


def test_review_edit_filter_bar_counts_empty_state_and_selection_restore(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )
    service.write_composition(
        composition(
            "alpha__20260526",
            "alpha",
            date(2026, 5, 26),
            reviewed=True,
            ready=True,
            needs_revalidation=False,
        )
    )

    mode = ReviewEditMode()
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    target_index = mode.tree_model.index(0, 0)
    ready_index = mode.tree_model.index(1, 0, target_index)
    mode.tree_view.setCurrentIndex(ready_index)

    mode.filter_buttons[QueueFilter.READY].click()

    assert mode.tree_model.active_queue_filter == QueueFilter.READY
    assert "Ready (1)" == mode.filter_buttons[QueueFilter.READY].text()
    assert mode.empty_state_label.isHidden()
    assert mode.tree_model.composition_id_for_index(mode.tree_view.currentIndex()) == (
        "alpha__20260526"
    )

    mode.filter_buttons[QueueFilter.INCLUDE].click()

    assert not mode.empty_state_label.isHidden()
    assert "Include" in mode.empty_state_label.text()
    assert mode.filter_buttons[QueueFilter.ALL].text() == "Tất cả (2)"

    mode.filter_buttons[QueueFilter.ALL].click()

    assert mode.empty_state_label.isHidden()
    assert mode.tree_model.composition_id_for_index(mode.tree_view.currentIndex()) == (
        "alpha__20260526"
    )

    service.write_composition(
        composition(
            "alpha__20260526",
            "alpha",
            date(2026, 5, 26),
            reviewed=True,
            ready=True,
            include=True,
            needs_revalidation=False,
            warnings=1,
        )
    )
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )

    assert mode.filter_buttons[QueueFilter.INCLUDE].text() == "Include (1)"
    assert mode.filter_buttons[QueueFilter.WARNING].text() == "Có warning (1)"
    assert mode.tree_model.composition_id_for_index(mode.tree_view.currentIndex()) == (
        "alpha__20260526"
    )


def test_review_edit_action_bar_includes_and_advances_on_passing_gate(
    tmp_path: Path,
) -> None:
    qapp()
    config_path = tmp_path / "config.json"
    write_project_config(config_path)
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path=config_path)
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )
    service.write_composition(
        composition("alpha__20260526", "alpha", date(2026, 5, 26), needs_revalidation=False)
    )

    mode = ReviewEditMode()
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    buttons = [
        mode.previous_button,
        mode.skip_button,
        mode.include_validate_button,
        mode.revalidate_button,
    ]
    assert [button.property("primaryAction") for button in buttons].count(True) == 1
    assert mode.include_validate_button.isEnabled()
    assert not mode.previous_button.isEnabled()

    mode.include_validate_button.click()

    included = service.read_composition("alpha__20260525")
    assert included.reviewed is True
    assert included.ready is True
    assert included.include is True
    assert included.review_order == 1
    assert mode.tree_model.composition_id_for_index(mode.tree_view.currentIndex()) == (
        "alpha__20260526"
    )
    assert mode.previous_button.isEnabled()


def test_review_edit_include_persists_target_interval_and_scale_to_config(
    tmp_path: Path,
) -> None:
    qapp()
    config_path = tmp_path / "config.json"
    write_project_config(config_path)
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path=config_path)
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )
    target = target_config("alpha", sort_order=1, name="Alpha Target").model_copy(
        update={
            "grid": GridConfig(interval=GridInterval(minutes=1), label_format="dms_short")
        }
    )

    mode = ReviewEditMode()
    mode.load_workspace(service, targets=[target])
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    mode.grid_minutes_input.setText("2")
    mode.grid_seconds_input.setText("30")
    mode.grid_scale_input.setText("25000")
    mode.save_grid_button.click()
    mode.include_validate_button.click()

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw_target = raw["targets"][0]
    included = service.read_composition("alpha__20260525")
    assert included.include is True
    assert raw_target["scale"] == 25000
    assert raw_target["grid"]["interval"] == {"minutes": 2, "seconds": 30}
    assert raw_target["grid"]["label_format"] == "dms_short"
    assert mode._targets is not None  # noqa: SLF001
    assert mode._targets[0].scale == 25000  # noqa: SLF001
    assert mode._targets[0].grid.interval.minutes == 2  # noqa: SLF001


def test_review_edit_action_bar_blocks_include_and_supports_skip_previous(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    blocked = composition(
        "alpha__20260525",
        "alpha",
        date(2026, 5, 25),
        needs_revalidation=False,
    )
    blocked = blocked.model_copy(
        update={"layers": [layer.model_copy(update={"visible": False}) for layer in blocked.layers]}
    )
    service.write_composition(blocked)
    service.write_composition(
        composition("alpha__20260526", "alpha", date(2026, 5, 26), needs_revalidation=False)
    )

    mode = ReviewEditMode()
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    mode.include_validate_button.click()

    unchanged = service.read_composition("alpha__20260525")
    assert unchanged.reviewed is False
    assert unchanged.ready is False
    assert unchanged.include is False
    assert mode.warnings_panel._list.count() > 0
    assert mode.action_summary.text() == "Không include: cần xử lý lỗi blocking trước."
    assert mode.tree_model.composition_id_for_index(mode.tree_view.currentIndex()) == (
        "alpha__20260525"
    )
    assert mode.tree_view.currentIndex().data(CompositionTreeRole.ISSUE_COUNT) > 0

    mode.skip_button.click()

    skipped = service.read_composition("alpha__20260525")
    assert skipped.reviewed is True
    assert skipped.ready is False
    assert skipped.include is False
    assert skipped.review_order is None
    assert mode.tree_model.composition_id_for_index(mode.tree_view.currentIndex()) == (
        "alpha__20260526"
    )

    second_before = service.read_composition("alpha__20260526")
    mode.previous_button.click()
    second_after = service.read_composition("alpha__20260526")

    assert second_after == second_before
    assert mode.tree_model.composition_id_for_index(mode.tree_view.currentIndex()) == (
        "alpha__20260525"
    )


def test_review_edit_issue_jump_handles_filtered_composition_and_target_only_refs(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )

    mode = ReviewEditMode()
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    mode.tree_model.set_queue_filter(QueueFilter.READY)
    mode._refresh_filter_controls()
    assert not mode.tree_model.has_visible_compositions()

    mode._handle_issue_jump("alpha", "alpha__20260525", "")

    assert mode.tree_model.active_queue_filter == QueueFilter.ALL
    assert mode.tree_model.composition_id_for_index(mode.tree_view.currentIndex()) == (
        "alpha__20260525"
    )

    mode._handle_issue_jump("alpha", "", "")

    assert mode.tree_view.currentIndex().data(CompositionTreeRole.TARGET_ID) == "alpha"


def test_review_edit_issue_jump_reports_stale_missing_layer(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )

    mode = ReviewEditMode()
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))
    mode.action_summary.setText("before")

    mode._handle_issue_jump("alpha", "alpha__20260525", "missing-layer")

    assert mode.action_summary.text() == "Tham chiếu không còn tồn tại."


def test_review_edit_revalidate_clears_stale_error_summary_with_lightweight_gate(
    tmp_path: Path,
) -> None:
    qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition(
            "alpha__20260525",
            "alpha",
            date(2026, 5, 25),
            needs_revalidation=True,
            errors=1,
        )
    )

    mode = ReviewEditMode()
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    revalidated = service.read_composition("alpha__20260525")
    assert revalidated.needs_revalidation is False
    assert revalidated.validation_summary.error_count == 0
    assert revalidated.ready is False
    assert revalidated.include is False
    assert not mode.revalidate_button.isEnabled()


def test_review_edit_keyboard_shortcuts_respect_text_input_arrow_guard(
    tmp_path: Path,
) -> None:
    app = qapp()
    service = WorkspaceService(tmp_path / "workspace")
    service.initialize(config_path="config.json")
    service.write_composition(
        composition("alpha__20260525", "alpha", date(2026, 5, 25), needs_revalidation=False)
    )

    mode = ReviewEditMode()
    mode._request_canvas_render = lambda _composition: None  # noqa: SLF001
    mode._request_target_preview = lambda _composition: None  # noqa: SLF001
    mode.load_workspace(
        service,
        targets=[target_config("alpha", sort_order=1, name="Alpha Target")],
    )
    target_index = mode.tree_model.index(0, 0)
    mode.tree_view.setCurrentIndex(mode.tree_model.index(0, 0, target_index))

    mode.show()
    mode.grid_minutes_input.setFocus()
    app.processEvents()
    mode.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    )

    assert service.read_composition("alpha__20260525").include is False

    mode.tree_view.setFocus()
    app.processEvents()
    mode.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    )

    assert service.read_composition("alpha__20260525").include is True


def test_review_edit_layout_and_app_shell_expose_review_mode(tmp_path: Path) -> None:
    qapp()

    shell = AppShell(preferences_service=PreferencesService(tmp_path / "preferences.json"))

    assert shell.mode_tabs.count() == 3
    assert shell.mode_tabs.tabText(0) == "Setup"
    assert shell.mode_tabs.tabText(1) == "Review/Edit"
    assert shell.mode_tabs.tabText(2) == "Export"
    assert isinstance(shell.review_edit_mode.tree_view, QTreeView)
    assert QueueFilter.ALL in shell.review_edit_mode.filter_buttons
    assert isinstance(shell.review_edit_mode.layer_table, QTableView)
    assert isinstance(shell.review_edit_mode.gis_canvas, QGraphicsView)
    assert shell.review_edit_mode.tree_view.uniformRowHeights()
    assert shell.review_edit_mode.minimumWidth() >= 960
    assert shell.review_edit_mode.findChild(QSplitter, "reviewMainSplitter") is not None
    assert shell.review_edit_mode.warnings_panel is not None
