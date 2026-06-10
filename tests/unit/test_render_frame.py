"""Tests for Story 5.3 coordinate frame rendering."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import thucthengay.render.frame as frame
from thucthengay.models.config import GridConfig, GridInterval
from thucthengay.models.template import MapFrame
from thucthengay.render import (
    GeoWindow,
    MapSurroundLayout,
    PixelRect,
    RenderBackground,
    RenderError,
    RenderSpec,
    build_map_surround_layout,
    draw_coordinate_frame,
    draw_map_surround_frame,
    draw_map_surround_pane_frame,
    fit_rect_to_aspect,
)


def _spec(
    *,
    width: int = 120,
    height: int = 80,
    interval: GridInterval | None = None,
    label_format: str = "dms_full",
    grid_style: dict[str, object] | None = None,
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
            style=grid_style or {},
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

    def test_supported_label_formats_can_be_configured_from_grid_style(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        spec = _spec(
            label_format="dms_full",
            grid_style={"supported_label_formats": ["dms_short"]},
        )

        with pytest.raises(RenderError) as exc:
            draw_coordinate_frame(canvas, spec)

        assert exc.value.issues[0].issue_id == "render.frame.label_format_invalid"
        assert "'dms_short'" in exc.value.issues[0].remediation

    def test_too_dense_interval_raises_structured_issue(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)
        interval = GridInterval.model_construct(degrees=0, minutes=0, seconds=0.001)

        with pytest.raises(RenderError) as exc:
            draw_coordinate_frame(canvas, _spec(interval=interval))

        assert exc.value.issues[0].issue_id == "render.frame.interval_too_dense"

    def test_max_tick_limit_can_be_configured_from_grid_style(self) -> None:
        canvas = np.zeros((80, 120, 3), dtype=np.uint8)

        with pytest.raises(RenderError) as exc:
            draw_coordinate_frame(
                canvas,
                _spec(
                    interval=GridInterval(minutes=30),
                    grid_style={"max_frame_ticks_per_axis": 1},
                ),
            )

        assert exc.value.issues[0].issue_id == "render.frame.interval_too_dense"
        assert "1." in exc.value.issues[0].remediation

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

        assert layout.outer_frame == PixelRect(left=244, top=144, right=3272, bottom=2286)
        assert layout.inner_map == PixelRect(left=292, top=192, right=3224, bottom=2238)
        assert layout.inner_map.left - (layout.outer_frame.left + 6) == 42
        assert layout.inner_map.top - (layout.outer_frame.top + 6) == 42
        assert layout.outer_frame.right - 6 - layout.inner_map.right == 42
        assert layout.outer_frame.bottom - 6 - layout.inner_map.bottom == 42

    def test_layout_uses_configured_reference_style_values(self) -> None:
        layout = build_map_surround_layout(
            100,
            100,
            {
                "reference_width": 100,
                "reference_height": 100,
                "reference_outer_frame": [10, 20, 90, 80],
                "reference_frame_gap": 5,
                "surround_outer_stroke_width": 2,
            },
        )

        assert layout.outer_frame == PixelRect(left=10, top=20, right=90, bottom=80)
        assert layout.inner_map == PixelRect(left=17, top=27, right=83, bottom=73)

    def test_layout_keeps_frame_gap_absolute_at_preview_size(self) -> None:
        layout = build_map_surround_layout(640, 453)

        assert layout.inner_map.left - (layout.outer_frame.left + 6) == 42
        assert layout.inner_map.top - (layout.outer_frame.top + 6) == 42
        assert layout.outer_frame.right - 6 - layout.inner_map.right == 42
        assert layout.outer_frame.bottom - 6 - layout.inner_map.bottom == 42

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
            layout.inner_map.top + 4 : layout.inner_map.bottom - 4,
            layout.inner_map.left + 4 : layout.inner_map.right - 4,
            :,
        ]
        assert np.array_equal(
            inner_interior,
            np.full_like(inner_interior, np.array([17, 34, 51], dtype=np.uint8)),
        )

    def test_map_surround_ticks_anchor_to_inner_frame_and_extend_outward(self) -> None:
        spec = _spec(
            width=240,
            height=200,
            interval=GridInterval(minutes=30),
        )
        layout = MapSurroundLayout(
            outer_frame=PixelRect(left=10, top=10, right=230, bottom=190),
            inner_map=PixelRect(left=70, top=70, right=170, bottom=130),
        )
        canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 255, 255)
        canvas[
            layout.inner_map.top : layout.inner_map.bottom,
            layout.inner_map.left : layout.inner_map.right,
            :,
        ] = (17, 34, 51)

        draw_map_surround_frame(canvas, spec, layout)

        lon_tick_x = layout.inner_map.center_x
        lat_tick_y = layout.inner_map.center_y
        assert tuple(canvas[layout.inner_map.top - 14, lon_tick_x].tolist()) == (0, 0, 0)
        assert tuple(canvas[layout.inner_map.top - 15, lon_tick_x].tolist()) == (255, 255, 255)
        assert tuple(canvas[layout.inner_map.bottom + 13, lon_tick_x].tolist()) == (0, 0, 0)
        assert tuple(canvas[layout.inner_map.bottom + 14, lon_tick_x].tolist()) == (255, 255, 255)
        assert tuple(canvas[lat_tick_y, layout.inner_map.left - 14].tolist()) == (0, 0, 0)
        assert tuple(canvas[lat_tick_y, layout.inner_map.left - 15].tolist()) == (255, 255, 255)
        assert tuple(canvas[lat_tick_y, layout.inner_map.right + 13].tolist()) == (0, 0, 0)
        assert tuple(canvas[lat_tick_y, layout.inner_map.right + 14].tolist()) == (255, 255, 255)

    def test_horizontal_compare_pane_internal_lon_ticks_extend_into_gap(self) -> None:
        spec = _spec(
            width=120,
            height=100,
            interval=GridInterval(minutes=30),
            grid_style={
                "surround_tick_stroke_width": 1,
                "surround_inner_stroke_width": 1,
            },
        )
        layout = MapSurroundLayout(
            outer_frame=PixelRect(left=0, top=0, right=120, bottom=100),
            inner_map=PixelRect(left=10, top=10, right=110, bottom=90),
        )
        top_pane = PixelRect(left=10, top=10, right=110, bottom=46)
        bottom_pane = PixelRect(left=10, top=54, right=110, bottom=90)
        tick_x = top_pane.center_x

        canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 255, 255)

        draw_map_surround_pane_frame(canvas, spec, layout, top_pane, internal_gap_px=8)
        draw_map_surround_pane_frame(canvas, spec, layout, bottom_pane, internal_gap_px=8)

        assert tuple(canvas[top_pane.bottom + 7, tick_x].tolist()) == (0, 0, 0)
        assert tuple(canvas[top_pane.bottom - 9, tick_x].tolist()) == (255, 255, 255)
        assert tuple(canvas[bottom_pane.top - 8, tick_x].tolist()) == (0, 0, 0)
        assert tuple(canvas[bottom_pane.top + 8, tick_x].tolist()) == (255, 255, 255)

    def test_map_surround_tick_length_can_be_configured_from_grid_style(self) -> None:
        spec = _spec(
            width=240,
            height=200,
            interval=GridInterval(minutes=30),
            grid_style={
                "surround_tick_length": 6,
                "surround_tick_stroke_width": 2,
            },
        )
        layout = MapSurroundLayout(
            outer_frame=PixelRect(left=10, top=10, right=230, bottom=190),
            inner_map=PixelRect(left=70, top=70, right=170, bottom=130),
        )
        canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 255, 255)
        canvas[
            layout.inner_map.top : layout.inner_map.bottom,
            layout.inner_map.left : layout.inner_map.right,
            :,
        ] = (17, 34, 51)

        draw_map_surround_frame(canvas, spec, layout)

        lon_tick_x = layout.inner_map.center_x
        assert tuple(canvas[layout.inner_map.top - 6, lon_tick_x].tolist()) == (0, 0, 0)
        assert tuple(canvas[layout.inner_map.top - 7, lon_tick_x].tolist()) == (255, 255, 255)

    def test_draws_horizontal_degree_labels_when_frame_band_can_fit_text(self) -> None:
        spec = _spec(
            width=640,
            height=453,
            interval=GridInterval(minutes=30),
            grid_style={
                "label_color": "#FF0000",
                "label_font_size": 10,
            },
        )
        layout = build_map_surround_layout(spec.output_width, spec.output_height)
        canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 255, 255)
        canvas[
            layout.inner_map.top : layout.inner_map.bottom,
            layout.inner_map.left : layout.inner_map.right,
            :,
        ] = (17, 34, 51)

        draw_map_surround_frame(canvas, spec, layout)

        top_gap = canvas[layout.outer_frame.top + 1 : layout.inner_map.top, :, :]
        assert (
            (top_gap[:, :, 0] > 180)
            & (top_gap[:, :, 1] < 100)
            & (top_gap[:, :, 2] < 100)
        ).any()

        inner_interior = canvas[
            layout.inner_map.top + 4 : layout.inner_map.bottom - 4,
            layout.inner_map.left + 4 : layout.inner_map.right - 4,
            :,
        ]
        assert np.array_equal(
            inner_interior,
            np.full_like(inner_interior, np.array([17, 34, 51], dtype=np.uint8)),
        )

    def test_draws_rotated_degree_labels_when_side_band_can_fit_text(self) -> None:
        spec = _spec(
            width=640,
            height=453,
            interval=GridInterval(minutes=30),
            grid_style={
                "label_color": "#FF0000",
                "label_font_size": 10,
            },
        )
        layout = build_map_surround_layout(spec.output_width, spec.output_height)
        canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 255, 255)
        canvas[
            layout.inner_map.top : layout.inner_map.bottom,
            layout.inner_map.left : layout.inner_map.right,
            :,
        ] = (17, 34, 51)

        draw_map_surround_frame(canvas, spec, layout)

        left_gap = canvas[:, layout.outer_frame.left + 1 : layout.inner_map.left, :]
        assert (
            (left_gap[:, :, 0] > 180)
            & (left_gap[:, :, 1] < 100)
            & (left_gap[:, :, 2] < 100)
        ).any()

    def test_rotated_label_layer_keeps_font_bbox_offsets_inside_padding(self, monkeypatch) -> None:
        captured_alpha: dict[str, np.ndarray] = {}
        original_rotate = Image.Image.rotate

        def capture_rotate(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            captured_alpha["value"] = np.asarray(self.getchannel("A")).copy()
            return original_rotate(self, *args, **kwargs)

        monkeypatch.setattr(Image.Image, "rotate", capture_rotate)
        font = frame._label_font(
            72,
            {"default_label_font": "fonts/arial-bold/Arial Bold/Arial Bold.ttf"},
        )

        frame._draw_rotated_text_with_halo(
            Image.new("RGB", (500, 500), (255, 255, 255)),
            (250, 250),
            "16°40'00\"N",
            font=font,
            fill=(0, 0, 0),
            halo=(255, 255, 255),
            angle=90,
        )

        alpha = captured_alpha["value"]
        rows_with_ink = np.flatnonzero(alpha.max(axis=1) > 0)
        cols_with_ink = np.flatnonzero(alpha.max(axis=0) > 0)
        assert rows_with_ink[0] > 0
        assert rows_with_ink[-1] < alpha.shape[0] - 1
        assert cols_with_ink[0] > 0
        assert cols_with_ink[-1] < alpha.shape[1] - 1

    def test_reference_frame_widths_match_template_sample(self) -> None:
        spec = _spec(width=3306, height=2340, interval=GridInterval(degrees=1))
        layout = build_map_surround_layout(spec.output_width, spec.output_height)
        canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 255, 255)
        canvas[
            layout.inner_map.top : layout.inner_map.bottom,
            layout.inner_map.left : layout.inner_map.right,
            :,
        ] = (17, 34, 51)

        draw_map_surround_frame(canvas, spec, layout)

        assert np.array_equal(
            canvas[144:150, 500:1000],
            np.full((6, 500, 3), np.array([0, 0, 0], dtype=np.uint8)),
        )
        assert np.array_equal(
            canvas[192:196, 500:1000],
            np.full((4, 500, 3), np.array([0, 0, 0], dtype=np.uint8)),
        )
        assert tuple(canvas[196, 296].tolist()) == (17, 34, 51)

    def test_reference_label_height_matches_template_sample(self) -> None:
        spec = _spec(width=3306, height=2340, interval=GridInterval(minutes=30))
        layout = build_map_surround_layout(spec.output_width, spec.output_height)
        canvas = np.zeros((spec.output_height, spec.output_width, 3), dtype=np.uint8)
        canvas[:, :] = (255, 255, 255)
        canvas[
            layout.inner_map.top : layout.inner_map.bottom,
            layout.inner_map.left : layout.inner_map.right,
            :,
        ] = (17, 34, 51)

        draw_map_surround_frame(canvas, spec, layout)

        top_center_label = canvas[
            layout.outer_frame.top + 6 : layout.inner_map.top,
            layout.inner_map.center_x - 150 : layout.inner_map.center_x + 150,
            :,
        ]
        black_pixels_by_row = (top_center_label.max(axis=2) <= 10).sum(axis=1)
        text_row_indexes = np.flatnonzero(black_pixels_by_row >= 20)

        assert text_row_indexes[-1] - text_row_indexes[0] + 1 >= 16
        label_center_y = (
            layout.outer_frame.top
            + 6
            + int(text_row_indexes[0] + text_row_indexes[-1]) // 2
        )
        band_center_y = (layout.outer_frame.top + layout.inner_map.top) // 2
        assert abs(label_center_y - band_center_y) <= 1
