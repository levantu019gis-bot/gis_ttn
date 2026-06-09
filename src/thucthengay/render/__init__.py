"""Rendering package."""

from thucthengay.models.render import FinalRenderCurrentness
from thucthengay.render.core import (
    FrameOverlayCache,
    FullMapCache,
    MapRenderCache,
    RasterBaseCache,
    render_map,
    render_map_with_cache,
)
from thucthengay.render.final import (
    is_final_render_current,
    render_final_png,
    render_spec_hash,
)
from thucthengay.render.frame import (
    MapSurroundLayout,
    PixelRect,
    build_map_surround_layout,
    draw_coordinate_frame,
    draw_map_surround_frame,
    fit_rect_to_aspect,
)
from thucthengay.render.raster import (
    RasterRenderResult,
    RenderError,
    render_raster_layers,
    render_raster_layers_result,
    render_raster_layers_to_size,
)
from thucthengay.render.spec import (
    GeoWindow,
    RenderBackground,
    RenderComparisonPane,
    RenderComparisonSpec,
    RenderLayerRef,
    RenderSpec,
    RenderSpecError,
    build_render_spec,
)
from thucthengay.render.target_preview import build_target_preview_spec

__all__ = [
    "GeoWindow",
    "FinalRenderCurrentness",
    "MapSurroundLayout",
    "PixelRect",
    "RenderBackground",
    "RenderComparisonPane",
    "RenderComparisonSpec",
    "RenderError",
    "RenderLayerRef",
    "RenderSpec",
    "RenderSpecError",
    "RasterRenderResult",
    "FrameOverlayCache",
    "FullMapCache",
    "MapRenderCache",
    "RasterBaseCache",
    "build_render_spec",
    "build_target_preview_spec",
    "build_map_surround_layout",
    "draw_coordinate_frame",
    "draw_map_surround_frame",
    "fit_rect_to_aspect",
    "is_final_render_current",
    "render_final_png",
    "render_map",
    "render_map_with_cache",
    "render_raster_layers",
    "render_raster_layers_result",
    "render_raster_layers_to_size",
    "render_spec_hash",
]
