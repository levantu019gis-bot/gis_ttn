"""Raster display symbology utilities shared by full renders and tile preview."""

from __future__ import annotations

import numpy as np

from thucthengay.models import LayerSymbology


def scale_to_uint8(
    data: np.ma.MaskedArray | np.ndarray,
    symbology: LayerSymbology | None = None,
) -> np.ndarray:
    """Convert raster band data into uint8 display pixels."""

    if symbology is None:
        return _legacy_scale_to_uint8(data)

    source = np.ma.asarray(data)
    if not symbology.enabled:
        return _legacy_scale_to_uint8(source)
    if symbology.stretch_mode == "none":
        return np.ma.clip(source, 0, 255).filled(0).astype(np.uint8)

    ranges = _resolve_ranges(source, symbology)
    scaled = _apply_ranges(source, ranges)
    scaled = _apply_gamma(scaled, symbology.gamma)
    display = scaled * 255.0
    if symbology.contrast != 1.0:
        display = (display - 127.5) * symbology.contrast + 127.5
    if symbology.brightness:
        display = display + symbology.brightness
    return np.ma.clip(display, 0, 255).filled(0).astype(np.uint8)


def _legacy_scale_to_uint8(data: np.ma.MaskedArray | np.ndarray) -> np.ndarray:
    source = np.ma.asarray(data)
    if source.dtype == np.uint8:
        return source.filled(0).astype(np.uint8, copy=False)

    valid = source.compressed()
    if valid.size == 0:
        return np.zeros(source.shape, dtype=np.uint8)

    if np.issubdtype(source.dtype, np.integer):
        dtype_info = np.iinfo(source.dtype)
        scaled = source.astype(np.float32) / float(dtype_info.max) * 255.0
    else:
        finite = valid[np.isfinite(valid)]
        if finite.size == 0:
            return np.zeros(source.shape, dtype=np.uint8)
        min_value = float(finite.min())
        max_value = float(finite.max())
        if min_value >= 0.0 and max_value <= 1.0:
            scaled = source.astype(np.float32) * 255.0
        elif max_value > min_value:
            scaled = (source.astype(np.float32) - min_value) / (max_value - min_value) * 255.0
        else:
            scaled = np.ma.zeros(source.shape, dtype=np.float32)

    return np.ma.clip(scaled, 0, 255).filled(0).astype(np.uint8)


def _resolve_ranges(
    data: np.ma.MaskedArray,
    symbology: LayerSymbology,
) -> list[tuple[float, float]]:
    channel_count = data.shape[0] if data.ndim >= 3 else 1
    if symbology.stretch_mode == "manual":
        lows = _expand_values(symbology.manual_min or [0.0], channel_count)
        highs = _expand_values(symbology.manual_max or [255.0], channel_count)
        return [_safe_range(low, high) for low, high in zip(lows, highs, strict=True)]

    if not symbology.per_channel:
        low, high = _range_for_channel(data, symbology)
        return [_safe_range(low, high)] * channel_count

    if data.ndim < 3:
        low, high = _range_for_channel(data, symbology)
        return [_safe_range(low, high)]
    ranges: list[tuple[float, float]] = []
    for channel in range(channel_count):
        low, high = _range_for_channel(data[channel], symbology)
        ranges.append(_safe_range(low, high))
    return ranges


def _range_for_channel(
    data: np.ma.MaskedArray,
    symbology: LayerSymbology,
) -> tuple[float, float]:
    source = np.ma.asarray(data)
    finite = source.compressed()
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 0.0, 1.0

    if symbology.stretch_mode == "dtype" and np.issubdtype(source.dtype, np.integer):
        dtype_info = np.iinfo(source.dtype)
        return float(dtype_info.min), float(dtype_info.max)
    if symbology.stretch_mode == "dtype" and np.issubdtype(source.dtype, np.floating):
        return 0.0, 1.0
    if symbology.stretch_mode == "percent_clip":
        low, high = np.percentile(
            finite,
            [symbology.lower_percentile, symbology.upper_percentile],
        )
        return float(low), float(high)
    if symbology.stretch_mode == "stddev":
        mean = float(finite.mean())
        std = float(finite.std())
        delta = std * symbology.stddev_factor
        return mean - delta, mean + delta
    return float(finite.min()), float(finite.max())


def _apply_ranges(
    data: np.ma.MaskedArray,
    ranges: list[tuple[float, float]],
) -> np.ma.MaskedArray:
    source = data.astype(np.float32)
    if source.ndim < 3:
        low, high = ranges[0]
        return (source - low) / (high - low)
    scaled = np.ma.empty(source.shape, dtype=np.float32)
    for channel in range(source.shape[0]):
        low, high = ranges[min(channel, len(ranges) - 1)]
        scaled[channel] = (source[channel] - low) / (high - low)
    return np.ma.clip(scaled, 0.0, 1.0)


def _apply_gamma(data: np.ma.MaskedArray, gamma: float) -> np.ma.MaskedArray:
    clipped = np.ma.clip(data, 0.0, 1.0)
    if gamma == 1.0:
        return clipped
    return np.ma.power(clipped, 1.0 / gamma)


def _safe_range(low: float, high: float) -> tuple[float, float]:
    if not np.isfinite(low):
        low = 0.0
    if not np.isfinite(high):
        high = low + 1.0
    if high <= low:
        high = low + 1.0
    return low, high


def _expand_values(values: list[float], count: int) -> list[float]:
    if len(values) == 1:
        return [values[0]] * count
    if len(values) >= count:
        return values[:count]
    return [*values, *([values[-1]] * (count - len(values)))]
