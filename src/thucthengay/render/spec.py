"""Shared render specification built from composition state.

Story 5.1: produce a normalized, immutable spec object that both preview and
final rendering paths can consume. The spec is derived (not persisted) and is
free of Qt dependencies.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from thucthengay.gis import view_geo_bounds
from thucthengay.models import TemporalCompareOrientation
from thucthengay.models.composition import Composition
from thucthengay.models.config import GridConfig, TargetConfig
from thucthengay.models.issue import Issue, IssueScope, IssueSeverity
from thucthengay.models.template import MapFrame, TemplateMetadata

POINT_TO_INCH: float = 1.0 / 72.0
INCH_TO_METER: float = 0.0254
METERS_PER_DEGREE_LAT: float = 111_320.0
MAX_RENDER_PIXELS: int = 50_000_000


class RenderSpecError(Exception):
    """Raised when render spec inputs are invalid; carries structured issues."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


class GeoWindow(BaseModel):
    """Geographic bounding window in WGS84 lon/lat degrees."""

    model_config = ConfigDict(extra="forbid")

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @model_validator(mode="after")
    def bounds_must_be_ordered(self) -> GeoWindow:
        values = (self.min_lon, self.min_lat, self.max_lon, self.max_lat)
        if not all(math.isfinite(value) for value in values):
            msg = "GeoWindow bounds must be finite"
            raise ValueError(msg)
        if not -180 <= self.min_lon <= 180 or not -180 <= self.max_lon <= 180:
            msg = "GeoWindow longitude bounds must be between -180 and 180"
            raise ValueError(msg)
        if not -90 <= self.min_lat <= 90 or not -90 <= self.max_lat <= 90:
            msg = "GeoWindow latitude bounds must be between -90 and 90"
            raise ValueError(msg)
        if self.min_lon >= self.max_lon:
            msg = "min_lon must be < max_lon"
            raise ValueError(msg)
        if self.min_lat >= self.max_lat:
            msg = "min_lat must be < max_lat"
            raise ValueError(msg)
        return self


class RenderLayerRef(BaseModel):
    """Lightweight pointer to a visible layer in draw order."""

    model_config = ConfigDict(extra="forbid")

    layer_id: str
    source_path: str
    cache_path: str | None = None
    order: int = Field(ge=0)


class RenderBackground(BaseModel):
    """Background settings drawn beneath raster coverage."""

    model_config = ConfigDict(extra="forbid")

    color: str = "#FFFFFF"

    @field_validator("color")
    @classmethod
    def color_must_be_hex_rgb(cls, value: str) -> str:
        text = value.lstrip("#")
        if len(text) != 6:
            msg = "background color must use #RRGGBB"
            raise ValueError(msg)
        try:
            int(text, 16)
        except ValueError as exc:
            msg = "background color must use #RRGGBB"
            raise ValueError(msg) from exc
        return f"#{text.upper()}"


class RenderComparisonPane(BaseModel):
    """One selected side of a temporal comparison render."""

    model_config = ConfigDict(extra="forbid")

    composition_id: str | None = None
    layer_id: str | None = None
    view_center: list[float] | None = None
    view_scale: int | None = Field(default=None, gt=0)
    geo_window: GeoWindow | None = None
    layers: list[RenderLayerRef] = Field(default_factory=list)

    @field_validator("view_center")
    @classmethod
    def view_center_must_be_lon_lat(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if len(value) != 2:
            msg = "view_center must contain exactly [lon, lat]"
            raise ValueError(msg)
        lon, lat = value
        if not -180 <= lon <= 180:
            msg = "view_center longitude must be between -180 and 180"
            raise ValueError(msg)
        if not -90 <= lat <= 90:
            msg = "view_center latitude must be between -90 and 90"
            raise ValueError(msg)
        return value


class RenderComparisonSpec(BaseModel):
    """Render-time temporal comparison pane selections."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    orientation: TemporalCompareOrientation = TemporalCompareOrientation.VERTICAL
    pane_a: RenderComparisonPane = Field(default_factory=RenderComparisonPane)
    pane_b: RenderComparisonPane = Field(default_factory=RenderComparisonPane)


class RenderSpec(BaseModel):
    """Normalized render specification consumed by preview and final renderers."""

    model_config = ConfigDict(extra="forbid")

    composition_id: str
    target_id: str
    output_width: int = Field(gt=0)
    output_height: int = Field(gt=0)
    view_center: list[float]
    view_scale: int = Field(gt=0)
    map_frame: MapFrame
    map_frame_aspect: float = Field(gt=0)
    geo_window: GeoWindow
    visible_layers: list[RenderLayerRef] = Field(default_factory=list)
    grid: GridConfig
    background: RenderBackground = Field(default_factory=RenderBackground)
    temporal_compare: RenderComparisonSpec = Field(default_factory=RenderComparisonSpec)
    template_metadata_file: str
    template_pptx: str
    slide_index: int = Field(ge=0)

    @field_validator("view_center")
    @classmethod
    def view_center_must_be_lon_lat(cls, value: list[float]) -> list[float]:
        if len(value) != 2:
            msg = "view_center must contain exactly [lon, lat]"
            raise ValueError(msg)
        lon, lat = value
        if not -180 <= lon <= 180:
            msg = "view_center longitude must be between -180 and 180"
            raise ValueError(msg)
        if not -90 <= lat <= 90:
            msg = "view_center latitude must be between -90 and 90"
            raise ValueError(msg)
        return value


def target_render_background(target: TargetConfig) -> RenderBackground:
    """Return the configured background for the target map render area."""
    return RenderBackground(color=target.export.map_background_color)


def _issue(
    issue_id: str,
    message: str,
    remediation: str,
    *,
    scope: IssueScope = IssueScope.RENDER,
    target_id: str | None = None,
    composition_id: str | None = None,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.ERROR,
        scope=scope,
        target_id=target_id,
        composition_id=composition_id,
        message=message,
        remediation=remediation,
    )


def _ground_span_meters(*, scale_denom: int, map_frame: MapFrame) -> tuple[float, float]:
    paper_width_m = map_frame.width * POINT_TO_INCH * INCH_TO_METER
    paper_height_m = map_frame.height * POINT_TO_INCH * INCH_TO_METER
    ground_width_m = paper_width_m * scale_denom
    ground_height_m = paper_height_m * scale_denom
    return ground_width_m, ground_height_m


def _compute_geo_window(
    *, center_lon: float, center_lat: float, scale_denom: int, map_frame: MapFrame
) -> GeoWindow:
    """Derive a WGS84 window from scale + map frame physical size.

    Treats ``map_frame.width``/``height`` as PowerPoint points. The span is
    computed geodesically from the persisted center so preview and final render
    share one stable, CRS-aware source of truth.
    """
    min_lon, min_lat, max_lon, max_lat = view_geo_bounds(
        center_lon=center_lon,
        center_lat=center_lat,
        scale_denom=scale_denom,
        map_frame_width_points=map_frame.width,
        map_frame_height_points=map_frame.height,
    )
    return GeoWindow(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)


def build_render_spec(
    *,
    composition: Composition,
    target: TargetConfig,
    template: TemplateMetadata,
    template_metadata_file: str,
    output_width: int,
    output_height: int,
    compare_compositions: list[Composition] | None = None,
) -> RenderSpec:
    """Build a :class:`RenderSpec` from composition + target + template + output size."""
    issues: list[Issue] = []

    if composition.target_id != target.id:
        issues.append(
            _issue(
                "render.spec.target_mismatch",
                "Composition và target không khớp.",
                (
                    f"Target id '{target.id}' không trùng với composition.target_id "
                    f"'{composition.target_id}'. Hãy chọn đúng target cho composition."
                ),
                target_id=target.id,
                composition_id=composition.composition_id,
            )
        )

    if output_width <= 0 or output_height <= 0:
        issues.append(
            _issue(
                "render.spec.output_size_invalid",
                "Kích thước output phải dương.",
                "Cung cấp output_width và output_height lớn hơn 0.",
                target_id=target.id,
                composition_id=composition.composition_id,
            )
        )
    elif output_width * output_height > MAX_RENDER_PIXELS:
        issues.append(
            _issue(
                "render.spec.output_size_too_large",
                "Kích thước output quá lớn cho một lần render.",
                (
                    f"Giảm output_width/output_height để tổng số pixel không vượt "
                    f"{MAX_RENDER_PIXELS:,}, hoặc dùng luồng render chia tile ở bản final."
                ),
                target_id=target.id,
                composition_id=composition.composition_id,
            )
        )

    if template.map_frame.width <= 0 or template.map_frame.height <= 0:
        issues.append(
            _issue(
                "render.spec.map_frame_invalid",
                "Kích thước map frame của template không hợp lệ.",
                "Kiểm tra template metadata: map_frame width/height phải > 0.",
                scope=IssueScope.TEMPLATE,
                target_id=target.id,
                composition_id=composition.composition_id,
            )
        )

    if issues:
        raise RenderSpecError(issues)

    grid = composition.grid_override if composition.grid_override is not None else target.grid

    center_lon, center_lat = composition.view.center
    try:
        geo_window = _compute_geo_window(
            center_lon=center_lon,
            center_lat=center_lat,
            scale_denom=composition.view.scale,
            map_frame=template.map_frame,
        )
    except (ValueError, ValidationError) as exc:
        issues.append(
            _issue(
                "render.spec.geo_window_invalid",
                "Không tính được vùng bản đồ hợp lệ từ center/scale/template.",
                (
                    "Kiểm tra tọa độ tâm, scale và map frame; vùng render không được vượt "
                    f"miền WGS84 hợp lệ hoặc cắt qua kinh tuyến 180. Chi tiết: {exc}"
                ),
                target_id=target.id,
                composition_id=composition.composition_id,
            )
        )
        raise RenderSpecError(issues) from exc

    map_frame_aspect = template.map_frame.width / template.map_frame.height
    visible_refs = _visible_layer_refs(composition)
    temporal_compare = _build_temporal_compare_spec(
        composition=composition,
        visible_refs=visible_refs,
        compare_compositions=compare_compositions or [],
        target=target,
        template=template,
        base_geo_window=geo_window,
    )
    if temporal_compare.enabled:
        visible_refs = [*temporal_compare.pane_a.layers, *temporal_compare.pane_b.layers]

    return RenderSpec(
        composition_id=composition.composition_id,
        target_id=target.id,
        output_width=output_width,
        output_height=output_height,
        view_center=list(composition.view.center),
        view_scale=composition.view.scale,
        map_frame=template.map_frame,
        map_frame_aspect=map_frame_aspect,
        geo_window=geo_window,
        visible_layers=visible_refs,
        grid=grid,
        background=target_render_background(target),
        temporal_compare=temporal_compare,
        template_metadata_file=template_metadata_file,
        template_pptx=template.template_pptx,
        slide_index=template.slide_index,
    )


def _build_temporal_compare_spec(
    *,
    composition: Composition,
    visible_refs: list[RenderLayerRef],
    compare_compositions: list[Composition],
    target: TargetConfig,
    template: TemplateMetadata,
    base_geo_window: GeoWindow,
) -> RenderComparisonSpec:
    state = composition.temporal_compare
    if not state.enabled:
        return RenderComparisonSpec()

    if state.pane_a_composition_id or state.pane_b_composition_id:
        return _build_composition_temporal_compare_spec(
            composition=composition,
            compare_compositions=compare_compositions,
            target=target,
            template=template,
        )

    refs_by_id = {layer.layer_id: layer for layer in visible_refs}
    pane_a = refs_by_id.get(state.pane_a_layer_id or "")
    pane_b = refs_by_id.get(state.pane_b_layer_id or "")
    if pane_a is None or pane_b is None or pane_a.layer_id == pane_b.layer_id:
        raise RenderSpecError(
            [
                _issue(
                    "render.spec.temporal_compare_invalid",
                    "Temporal comparison pane selections are not valid.",
                    (
                        "Select two different visible layers for Pane A and Pane B before "
                        "render/export."
                    ),
                    target_id=target.id,
                    composition_id=composition.composition_id,
                )
            ]
        )

    return RenderComparisonSpec(
        enabled=True,
        orientation=state.orientation,
        pane_a=RenderComparisonPane(
            layer_id=pane_a.layer_id,
            view_center=list(composition.view.center),
            view_scale=composition.view.scale,
            geo_window=base_geo_window,
            layers=[pane_a],
        ),
        pane_b=RenderComparisonPane(
            layer_id=pane_b.layer_id,
            view_center=list(composition.view.center),
            view_scale=composition.view.scale,
            geo_window=base_geo_window,
            layers=[pane_b],
        ),
    )


def _build_composition_temporal_compare_spec(
    *,
    composition: Composition,
    compare_compositions: list[Composition],
    target: TargetConfig,
    template: TemplateMetadata,
) -> RenderComparisonSpec:
    state = composition.temporal_compare
    compare_by_id = {item.composition_id: item for item in compare_compositions}
    pane_a = compare_by_id.get(state.pane_a_composition_id or "")
    pane_b = compare_by_id.get(state.pane_b_composition_id or "")
    if pane_a is None or pane_b is None:
        raise RenderSpecError(
            [
                _issue(
                    "render.spec.temporal_compare_invalid",
                    "Temporal comparison pane selections are not valid.",
                    (
                        "Select compositions/time points for Pane A and Pane B before "
                        "render/export."
                    ),
                    target_id=target.id,
                    composition_id=composition.composition_id,
                )
            ]
        )
    if pane_a.target_id != composition.target_id or pane_b.target_id != composition.target_id:
        raise RenderSpecError(
            [
                _issue(
                    "render.spec.temporal_compare_target_mismatch",
                    "Temporal comparison panes do not belong to the selected target.",
                    "Select two compositions from the same target before render/export.",
                    target_id=target.id,
                    composition_id=composition.composition_id,
                )
            ]
        )

    pane_a_layers = _visible_layer_refs(pane_a)
    pane_b_layers = _visible_layer_refs(pane_b)
    if not pane_a_layers or not pane_b_layers:
        raise RenderSpecError(
            [
                _issue(
                    "render.spec.temporal_compare_empty_pane",
                    "Temporal comparison pane has no visible layers.",
                    "Enable at least one layer in each selected comparison composition.",
                    target_id=target.id,
                    composition_id=composition.composition_id,
                )
            ]
        )

    return RenderComparisonSpec(
        enabled=True,
        orientation=state.orientation,
        pane_a=RenderComparisonPane(
            composition_id=pane_a.composition_id,
            view_center=list(state.pane_a_center or pane_a.view.center),
            view_scale=composition.view.scale,
            geo_window=_comparison_pane_geo_window(
                pane_a,
                target=target,
                template=template,
                scale_denom=composition.view.scale,
                center=state.pane_a_center,
            ),
            layers=pane_a_layers,
        ),
        pane_b=RenderComparisonPane(
            composition_id=pane_b.composition_id,
            view_center=list(state.pane_b_center or pane_b.view.center),
            view_scale=composition.view.scale,
            geo_window=_comparison_pane_geo_window(
                pane_b,
                target=target,
                template=template,
                scale_denom=composition.view.scale,
                center=state.pane_b_center,
            ),
            layers=pane_b_layers,
        ),
    )


def _comparison_pane_geo_window(
    composition: Composition,
    *,
    target: TargetConfig,
    template: TemplateMetadata,
    scale_denom: int | None = None,
    center: list[float] | None = None,
) -> GeoWindow:
    center_lon, center_lat = center or composition.view.center
    try:
        return _compute_geo_window(
            center_lon=center_lon,
            center_lat=center_lat,
            scale_denom=scale_denom or composition.view.scale,
            map_frame=template.map_frame,
        )
    except (ValueError, ValidationError) as exc:
        raise RenderSpecError(
            [
                _issue(
                    "render.spec.temporal_compare_geo_window_invalid",
                    "Khong tinh duoc vung ban do hop le cho comparison pane.",
                    (
                        "Kiem tra center/scale cua composition duoc chon cho pane "
                        f"'{composition.composition_id}'. Chi tiet: {exc}"
                    ),
                    target_id=target.id,
                    composition_id=composition.composition_id,
                )
            ]
        ) from exc


def _visible_layer_refs(composition: Composition) -> list[RenderLayerRef]:
    visible_layers = sorted(
        (layer for layer in composition.layers if layer.visible),
        key=lambda layer: layer.order,
    )
    return [
        RenderLayerRef(
            layer_id=layer.layer_id,
            source_path=layer.source_path,
            cache_path=layer.cache_path,
            order=layer.order,
        )
        for layer in visible_layers
    ]
