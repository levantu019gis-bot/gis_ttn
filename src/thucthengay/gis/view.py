"""Map view math shared by editor interactions and render preparation."""

from __future__ import annotations

from math import isfinite

from pyproj import Geod

POINT_TO_INCH = 1 / 72
INCH_TO_METER = 0.0254

_GEOD = Geod(ellps="WGS84")


def map_frame_ground_span_meters(
    *,
    scale_denom: int,
    map_frame_width_points: float,
    map_frame_height_points: float,
) -> tuple[float, float]:
    """Return ground width/height represented by a PPT map frame at a scale."""
    if scale_denom <= 0:
        msg = "scale_denom must be positive"
        raise ValueError(msg)
    if map_frame_width_points <= 0 or map_frame_height_points <= 0:
        msg = "map frame dimensions must be positive"
        raise ValueError(msg)
    paper_width_m = map_frame_width_points * POINT_TO_INCH * INCH_TO_METER
    paper_height_m = map_frame_height_points * POINT_TO_INCH * INCH_TO_METER
    return paper_width_m * scale_denom, paper_height_m * scale_denom


def view_geo_bounds(
    *,
    center_lon: float,
    center_lat: float,
    scale_denom: int,
    map_frame_width_points: float,
    map_frame_height_points: float,
) -> tuple[float, float, float, float]:
    """Return the WGS84 bbox represented by a center/scale/map-frame view."""
    if not all(isfinite(value) for value in (center_lon, center_lat)):
        msg = "center coordinates must be finite"
        raise ValueError(msg)
    ground_width_m, ground_height_m = map_frame_ground_span_meters(
        scale_denom=scale_denom,
        map_frame_width_points=map_frame_width_points,
        map_frame_height_points=map_frame_height_points,
    )
    half_w_m = ground_width_m / 2.0
    half_h_m = ground_height_m / 2.0
    west_lon, _, _ = _GEOD.fwd(center_lon, center_lat, 270.0, half_w_m)
    east_lon, _, _ = _GEOD.fwd(center_lon, center_lat, 90.0, half_w_m)
    _, south_lat, _ = _GEOD.fwd(center_lon, center_lat, 180.0, half_h_m)
    _, north_lat, _ = _GEOD.fwd(center_lon, center_lat, 0.0, half_h_m)

    lon_values = [west_lon, east_lon]
    if max(lon_values) - min(lon_values) > 180:
        msg = "view window crosses the antimeridian, which is not supported yet"
        raise ValueError(msg)

    return min(lon_values), south_lat, max(lon_values), north_lat


def pan_center_by_viewport_pixels(
    *,
    center_lon: float,
    center_lat: float,
    scale_denom: int,
    map_frame_width_points: float,
    map_frame_height_points: float,
    viewport_width_px: float,
    viewport_height_px: float,
    dx_px: float,
    dy_px: float,
) -> tuple[float, float]:
    """Move a lon/lat center by the ground distance represented by a pixel drag."""
    if viewport_width_px <= 0 or viewport_height_px <= 0:
        return center_lon, center_lat
    if not all(
        isfinite(value)
        for value in (
            center_lon,
            center_lat,
            viewport_width_px,
            viewport_height_px,
            dx_px,
            dy_px,
        )
    ):
        return center_lon, center_lat

    ground_width_m, ground_height_m = map_frame_ground_span_meters(
        scale_denom=scale_denom,
        map_frame_width_points=map_frame_width_points,
        map_frame_height_points=map_frame_height_points,
    )
    lon, lat = center_lon, center_lat
    horizontal_m = abs(dx_px) * ground_width_m / viewport_width_px
    vertical_m = abs(dy_px) * ground_height_m / viewport_height_px
    if horizontal_m:
        lon, lat, _ = _GEOD.fwd(lon, lat, 270.0 if dx_px > 0 else 90.0, horizontal_m)
    if vertical_m:
        lon, lat, _ = _GEOD.fwd(lon, lat, 0.0 if dy_px > 0 else 180.0, vertical_m)
    return _clamp(lon, -180.0, 180.0), _clamp(lat, -90.0, 90.0)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
