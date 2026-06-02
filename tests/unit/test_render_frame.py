"""Tests for Story 5.3 coordinate frame rendering."""

from __future__ import annotations

import numpy as np
import pytest

from thucthengay.models.config import GridConfig, GridInterval
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    GeoWindow,
    PixelRect,
    RenderBackground,
    RenderError,
    RenderSpec,
    build_map_surround_layout,
    draw_coordinate_frame,
    draw_map_surround_frame,
    fit_rect_to_aspect,
)


def _spec(
    *,
    width: int = 120,
    height: int = 80,
    interval: GridInterval | None = None,
    label_format: str = "dms_full",
) -> RenderSpec:
    return RenderSpec(
        composition_id="tgt__20260525",
        target_id="tgt",
        output_width=width,
        output_height=height,
        view_center=[106.5, 10.5],
        view_scale=50000,
        map_frame=MapFrame(x=0, y=0, width=640, height=360),
        map_frame_aspect=640 / 360,
        geo_window=GeoWindow(min_lon=106.0, min_lat=10.0, max_lon=107.0, max_lat=11.0),
        visible_layers=[],
        grid=GridConfig(
            interval=interval or GridInterval(minutes=30),
            label_format=label_format,
        ),
        background=RenderBackground(color="#010203"),
        template_metadata_file="t.json",
        template_pptx="t.pptx",
        slide_index=0,
    )


class TestCoordinateFrame:
    def test_draws_outer_frame_ticks_and_labels(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        canvas[:, :] = (1, 2, 3)

        result = draw_coordinate_frame(canvas, _spec())

        assert result is canvas
        assert tuple(canvas[0, 0].tolist()) != (1, 2, 3)
        assert tuple(canvas[0, 60].tolist()) != (1, 2, 3)
        assert tuple(canvas[79, 60].tolist()) != (1, 2, 3)
        assert tuple(canvas[40, 0].tolist()) != (1, 2, 3)
        assert tuple(canvas[40, 119].tolist()) != (1, 2, 3)
        assert (canvas != np.array([1, 2, 3], dtype=np.uint8)).any()

    def test_does_not_draw_internal_grid_mesh(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        canvas[:, :] = (1, 2, 3)

        draw_coordinate_frame(canvas, _spec())

        assert tuple(canvas[40, 60].tolist()) == (1, 2, 3)
        assert tuple(canvas[20, 60].tolist()) == (1, 2, 3)
        assert tuple(canvas[40, 30].tolist()) == (1, 2, 3)

    def test_tick_positions_align_to_geo_window_edges(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        canvas[:, :] = (1, 2, 3)

        draw_coordinate_frame(canvas, _spec(interval=GridInterval(minutes=30)))

        assert tuple(canvas[0, 0].tolist()) != (1, 2, 3)
        assert tuple(canvas[0, 60].tolist()) != (1, 2, 3)
        assert tuple(canvas[0, 119].tolist()) != (1, 2, 3)
        assert tuple(canvas[79, 0].tolist()) != (1, 2, 3)
        assert tuple(canvas[40, 0].tolist()) != (1, 2, 3)
        assert tuple(canvas[18, 30].tolist()) == (1, 2, 3)

    def test_invalid_label_format_raises_structured_issue(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        spec = _spec(label_format="unsupported")

        with pytest.raises(RenderError) as exc:
            draw_coordinate_frame(canvas, spec)

        issue = exc.value.issues[0]
        assert issue.issue_id == "render.frame.label_format_invalid"
        assert issue.composition_id == "tgt__20260525"
        assert "dms_full" in issue.remediation

    def test_empty_label_format_raises_structured_issue(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        spec = _spec(label_format=" ")

        with pytest.raises(RenderError) as exc:
            draw_coordinate_frame(canvas, spec)

        assert exc.value.issues[0].issue_id == "render.frame.label_format_invalid"

    def test_too_dense_interval_raises_structured_issue(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        interval = GridInterval.model_construct(degrees=0, minutes=0, seconds=0.001)

        with pytest.raises(RenderError) as exc:
            draw_coordinate_frame(canvas, _spec(interval=interval))

        assert exc.value.issues[0].issue_id == "render.frame.interval_too_dense"

    def test_edge_only_ticks_still_draw_labels_inside_canvas(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        canvas[:, :] = (1, 2, 3)

        draw_coordinate_frame(canvas, _spec(interval=GridInterval(degrees=1)))

        top_label_band = canvas[1:14, :, :]
        bottom_label_band = canvas[65:79, :, :]
        assert (top_label_band == np.array([255, 255, 255], dtype=np.uint8)).any()
        assert (bottom_label_band == np.array([255, 255, 255], dtype=np.uint8)).any()


class TestCoordinateFormatting:
    def test_short_format_can_be_rendered(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        canvas[:, :] = (1, 2, 3)

        draw_coordinate_frame(canvas, _spec(label_format="dms_short"))

        assert tuple(canvas[0, 60].tolist()) != (1, 2, 3)


class TestMapSurroundFrame:
    def test_reference_layout_matches_template_sample_geometry(self) -> None:
        layout = build_map_surround_layout(3306, 2340)

        assert layout.outer_frame == PixelRect(left=244, top=165, right=3272, bottom=2307)
        assert layout.inner_map == PixelRect(left=292, top=213, right=3224, bottom=2259)

    def test_fit_rect_to_aspect_preserves_geographic_view_shape(self) -> None:
        layout = build_map_surround_layout(330, 234)
        fitted = fit_rect_to_aspect(layout.inner_map, 16 / 9)

        assert fitted.left >= layout.inner_map.left
        assert fitted.right <= layout.inner_map.right
        assert fitted.top >= layout.inner_map.top
        assert fitted.bottom <= layout.inner_map.bottom
        assert abs((fitted.width / fitted.height) - (16 / 9)) < 0.05

    def test_draws_outer_inner_frames_and_keeps_raster_panel_clean(self) -> None:
        spec = _spec(width=330, height=234, interval=GridInterval(degrees=10))
        layout = build_map_surround_layout(spec.output_width, spec.output_height)
        canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 255, 255)
        canvas[
            layout.inner_map.top : layout.inner_map.bottom,
            layout.inner_map.left : layout.inner_map.right,
            :,
        ] = (17, 34, 51)

        draw_map_surround_frame(canvas, spec, layout)

        assert tuple(canvas[0, 0].tolist()) == (255, 255, 255)
        assert tuple(canvas[layout.outer_frame.top, layout.outer_frame.left].tolist()) == (0, 0, 0)
        assert tuple(canvas[layout.inner_map.top, layout.inner_map.left].tolist()) == (0, 0, 0)
        assert tuple(canvas[layout.inner_map.center_y, layout.inner_map.center_x].tolist()) == (
            17,
            34,
            51,
        )

    def test_draws_ticks_and_labels_outside_inner_map(self) -> None:
        spec = _spec(width=330, height=234, interval=GridInterval(minutes=30))
        layout = build_map_surround_layout(spec.output_width, spec.output_height)
        canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 255, 255)
        canvas[
            layout.inner_map.top : layout.inner_map.bottom,
            layout.inner_map.left : layout.inner_map.right,
            :,
        ] = (17, 34, 51)

        draw_map_surround_frame(canvas, spec, layout)

        assert tuple(canvas[layout.inner_map.center_y, layout.inner_map.center_x].tolist()) == (
            17,
            34,
            51,
        )
        top_band = canvas[layout.outer_frame.top : layout.inner_map.top, :, :]
        assert (top_band != np.array([255, 255, 255], dtype=np.uint8)).any()
        inner_interior = canvas[
            layout.inner_map.top + 1 : layout.inner_map.bottom - 1,
            layout.inner_map.left + 1 : layout.inner_map.right - 1,
            :,
        ]
        assert np.array_equal(
            inner_interior,
            np.full_like(inner_interior, np.array([17, 34, 51], dtype=np.uint8)),
        )
