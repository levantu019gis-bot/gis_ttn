"""Raster compositing core for the rendering pipeline.

Story 5.2: read each visible raster layer through a windowed/decimated path,
reproject on-the-fly with ``WarpedVRT`` when needed, and composite into a
single uint8 RGB canvas sized ``(spec.output_height, spec.output_width, 3)``.

Performance:
- ``rasterio.windows.from_bounds`` + ``out_shape=`` ensures GDAL reads the
  smallest possible window at the target decimation; no full-raster loads.
- ``WarpedVRT`` performs CRS reprojection during the read call without writing
  intermediate files. We instantiate it only when CRS differs from WGS84.
- One preallocated canvas, in-place paste, ``uint8`` dtype throughout.
- ``dataset_opener`` injection lets tests pass synthetic ``MemoryFile`` datasets
  without touching disk and keeps the module Qt-free.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np
import rasterio
from pyproj.exceptions import CRSError as PyprojCRSError
from pyproj.exceptions import ProjError
from rasterio.enums import ColorInterp, Resampling
from rasterio.errors import CRSError as RasterioCRSError
from rasterio.errors import RasterioError
from rasterio.io import DatasetReader
from rasterio.vrt import WarpedVRT

from thucthengay.gis.crs import (
    GEOGRAPHIC_CRS,
    geographic_window_to_raster_window,
    normalize_crs_key,
)
from thucthengay.models.issue import Issue, IssueScope, IssueSeverity
from thucthengay.render.spec import MAX_RENDER_PIXELS, RenderLayerRef, RenderSpec

DatasetOpener = Callable[[str], "rasterio.DatasetReader"]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True)
class RasterRenderResult:
    """Canvas plus non-fatal render issues surfaced to preview/export callers."""

    canvas: np.ndarray
    issues: tuple[Issue, ...] = ()
    painted_layer_ids: tuple[str, ...] = ()


class RenderError(Exception):
    """Raised when rendering cannot produce any output; carries structured issues."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


def _parse_hex_color(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) != 6:
        msg = f"Background color must be #RRGGBB, got {value!r}"
        raise ValueError(msg)
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _render_issue(
    issue_id: str,
    message: str,
    remediation: str,
    *,
    composition_id: str | None,
    target_id: str | None,
) -> Issue:
    return _issue(
        issue_id,
        message,
        remediation,
        layer_id=None,
        composition_id=composition_id,
        target_id=target_id,
    )


def _issue(
    issue_id: str,
    message: str,
    remediation: str,
    *,
    layer_id: str | None,
    composition_id: str | None,
    target_id: str | None,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.ERROR,
        scope=IssueScope.RENDER,
        target_id=target_id,
        composition_id=composition_id,
        layer_id=layer_id,
        message=message,
        remediation=remediation,
    )


@contextmanager
def _open_layer(
    layer: RenderLayerRef, opener: DatasetOpener
) -> Iterator[DatasetReader]:
    path = layer.cache_path or layer.source_path
    ds = opener(path)
    try:
        yield ds
    finally:
        ds.close()


def _geo_to_pixel(
    canvas_w: int,
    canvas_h: int,
    geo_bbox: tuple[float, float, float, float],
    target_bbox: tuple[float, float, float, float],
) -> tuple[int, int, int, int]:
    """Map ``target_bbox`` (WGS84) into integer pixel coords on the canvas."""
    min_lon, min_lat, max_lon, max_lat = geo_bbox
    tlon0, tlat0, tlon1, tlat1 = target_bbox
    w_lon = max_lon - min_lon
    h_lat = max_lat - min_lat
    col0 = int(np.floor((tlon0 - min_lon) / w_lon * canvas_w))
    col1 = int(np.ceil((tlon1 - min_lon) / w_lon * canvas_w))
    row0 = int(np.floor((max_lat - tlat1) / h_lat * canvas_h))
    row1 = int(np.ceil((max_lat - tlat0) / h_lat * canvas_h))
    col0 = max(0, min(canvas_w, col0))
    col1 = max(0, min(canvas_w, col1))
    row0 = max(0, min(canvas_h, row0))
    row1 = max(0, min(canvas_h, row1))
    return row0, row1, col0, col1


def _resolve_band_indexes(src: DatasetReader) -> tuple[tuple[int, ...], int | None]:
    colorinterp = tuple(src.colorinterp or ())
    alpha_index = None
    for index, interp in enumerate(colorinterp, start=1):
        if interp == ColorInterp.alpha:
            alpha_index = index
            break

    rgb_indexes = []
    for desired in (ColorInterp.red, ColorInterp.green, ColorInterp.blue):
        if desired in colorinterp:
            rgb_indexes.append(colorinterp.index(desired) + 1)
    if len(rgb_indexes) == 3:
        return tuple(rgb_indexes), alpha_index

    if ColorInterp.gray in colorinterp:
        return (colorinterp.index(ColorInterp.gray) + 1,), alpha_index

    if src.count >= 3:
        return (1, 2, 3), alpha_index
    return (1,), alpha_index


def _scale_to_uint8(data: np.ma.MaskedArray | np.ndarray) -> np.ndarray:
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


def _read_alpha_mask(
    src: DatasetReader,
    *,
    alpha_index: int | None,
    window,
    out_h: int,
    out_w: int,
) -> np.ndarray | None:
    if alpha_index is None:
        return None
    alpha = src.read(
        alpha_index,
        window=window,
        out_shape=(out_h, out_w),
        resampling=Resampling.nearest,
        masked=True,
    )
    alpha_values = np.ma.asarray(alpha).filled(0)
    return alpha_values <= 0


def _read_layer_into(
    *,
    dataset: DatasetReader,
    geo_bbox: tuple[float, float, float, float],
    canvas: np.ndarray,
) -> bool:
    """Read ``dataset`` into the ``canvas`` region corresponding to its overlap.

    Returns ``True`` if pixels were written, ``False`` if no overlap.
    """
    raster_crs = normalize_crs_key(dataset.crs)
    use_vrt = raster_crs != GEOGRAPHIC_CRS

    src: DatasetReader
    if use_vrt:
        src = WarpedVRT(
            dataset,
            crs=GEOGRAPHIC_CRS,
            resampling=Resampling.bilinear,
            warp_mem_limit=64,
        )
    else:
        src = dataset

    try:
        resolution = geographic_window_to_raster_window(geo_bbox, src)
        if resolution is None:
            return False

        canvas_h, canvas_w = canvas.shape[:2]
        row0, row1, col0, col1 = _geo_to_pixel(
            canvas_w, canvas_h, geo_bbox, resolution.covered_bbox
        )
        out_h = row1 - row0
        out_w = col1 - col0
        if out_h <= 0 or out_w <= 0:
            return False

        read_bands, alpha_index = _resolve_band_indexes(src)
        data = src.read(
            indexes=read_bands,
            window=resolution.window,
            out_shape=(len(read_bands), out_h, out_w),
            resampling=Resampling.bilinear,
            masked=True,
        )
        masked_data = np.ma.asarray(data)
        mask = np.ma.getmaskarray(masked_data).any(axis=0)
        alpha_mask = _read_alpha_mask(
            src,
            alpha_index=alpha_index,
            window=resolution.window,
            out_h=out_h,
            out_w=out_w,
        )
        if alpha_mask is not None:
            mask = np.logical_or(mask, alpha_mask)

        if len(read_bands) == 1:
            rgb = np.repeat(_scale_to_uint8(masked_data), 3, axis=0)
        else:
            rgb = _scale_to_uint8(masked_data)

        valid = ~mask
        if not valid.any():
            return False
        target = canvas[row0:row1, col0:col1, :]
        target[valid, :] = np.transpose(rgb, (1, 2, 0))[valid, :]
        return True
    finally:
        if use_vrt:
            src.close()


def render_raster_layers(
    spec: RenderSpec,
    *,
    dataset_opener: DatasetOpener = rasterio.open,
    is_cancelled: CancelCallback | None = None,
) -> RasterRenderResult:
    """Composite visible raster layers into a structured render result.

    Layers are drawn in ``spec.visible_layers`` order (lower ``order`` first);
    later layers overwrite earlier pixels where they cover. Non-fatal layer
    failures are returned in ``RasterRenderResult.issues`` so callers can warn in
    preview or block export. If no output can be produced, ``RenderError`` is
    raised with structured issues.
    """
    return render_raster_layers_result(
        spec, dataset_opener=dataset_opener, is_cancelled=is_cancelled
    )


def render_raster_layers_to_size(
    spec: RenderSpec,
    *,
    output_width: int,
    output_height: int,
    dataset_opener: DatasetOpener = rasterio.open,
    is_cancelled: CancelCallback | None = None,
) -> RasterRenderResult:
    """Composite raster layers into an alternate output size using the same geo window."""
    if output_width <= 0 or output_height <= 0:
        issue = _render_issue(
            "render.output.size_invalid",
            "Kích thước raster render không hợp lệ.",
            "Cung cấp output_width và output_height lớn hơn 0.",
            composition_id=spec.composition_id,
            target_id=spec.target_id,
        )
        raise RenderError([issue])
    sized_spec = spec.model_copy(
        update={
            "output_width": output_width,
            "output_height": output_height,
        }
    )
    return render_raster_layers_result(
        sized_spec,
        dataset_opener=dataset_opener,
        is_cancelled=is_cancelled,
    )


def render_raster_layers_result(
    spec: RenderSpec,
    *,
    dataset_opener: DatasetOpener = rasterio.open,
    is_cancelled: CancelCallback | None = None,
) -> RasterRenderResult:
    """Composite visible raster layers into a single uint8 RGB canvas.

    Layers are drawn in ``spec.visible_layers`` order (lower ``order`` first);
    later layers overwrite earlier pixels where they cover.
    Per-layer IO/CRS failures are collected as ``Issue``s; rendering proceeds
    on remaining layers. If *no* layer is successfully drawn AND at least one
    issue was recorded, ``RenderError`` is raised.
    """
    geo_bbox = (
        spec.geo_window.min_lon,
        spec.geo_window.min_lat,
        spec.geo_window.max_lon,
        spec.geo_window.max_lat,
    )

    issues: list[Issue] = []
    try:
        bg = _parse_hex_color(spec.background.color)
    except ValueError as exc:
        issue = _render_issue(
            "render.background.invalid",
            "Màu nền render không hợp lệ.",
            "Sửa màu nền về định dạng #RRGGBB trước khi render.",
            composition_id=spec.composition_id,
            target_id=spec.target_id,
        )
        raise RenderError([issue]) from exc

    if spec.output_width * spec.output_height > MAX_RENDER_PIXELS:
        issue = _render_issue(
            "render.output.too_large",
            "Kích thước render vượt giới hạn an toàn bộ nhớ.",
            (
                f"Giảm kích thước output để tổng pixel không vượt {MAX_RENDER_PIXELS:,}; "
                "với bản final lớn cần dùng luồng render chia tile."
            ),
            composition_id=spec.composition_id,
            target_id=spec.target_id,
        )
        raise RenderError([issue])

    try:
        canvas = np.empty((spec.output_height, spec.output_width, 3), dtype=np.uint8)
    except MemoryError as exc:
        issue = _render_issue(
            "render.output.memory_error",
            "Không đủ bộ nhớ để tạo canvas render.",
            "Giảm kích thước output hoặc đóng bớt ứng dụng trước khi render lại.",
            composition_id=spec.composition_id,
            target_id=spec.target_id,
        )
        raise RenderError([issue]) from exc
    canvas[..., 0] = bg[0]
    canvas[..., 1] = bg[1]
    canvas[..., 2] = bg[2]

    painted_layer_ids: list[str] = []
    skipped_no_overlap = 0

    for layer in spec.visible_layers:
        if is_cancelled is not None and is_cancelled():
            issues.append(
                _issue(
                    "render.cancelled",
                    "Render đã bị hủy.",
                    "Thực hiện lại render khi không còn thao tác mới hơn đang chờ.",
                    layer_id=layer.layer_id,
                    composition_id=spec.composition_id,
                    target_id=spec.target_id,
                )
            )
            break
        try:
            with _open_layer(layer, dataset_opener) as dataset:
                if dataset.crs is None:
                    issues.append(
                        _issue(
                            "render.raster.crs_missing",
                            f"Layer '{layer.layer_id}' không có CRS.",
                            "Kiểm tra GeoTIFF có gắn CRS hợp lệ (ví dụ EPSG:4326).",
                            layer_id=layer.layer_id,
                            composition_id=spec.composition_id,
                            target_id=spec.target_id,
                        )
                    )
                    continue
                if _read_layer_into(dataset=dataset, geo_bbox=geo_bbox, canvas=canvas):
                    painted_layer_ids.append(layer.layer_id)
                else:
                    skipped_no_overlap += 1
        except (RasterioCRSError, PyprojCRSError, ProjError) as exc:
            issues.append(
                _issue(
                    "render.raster.crs_invalid",
                    f"CRS của layer '{layer.layer_id}' không hợp lệ: {exc}",
                    "Kiểm tra lại GeoTIFF và chuyển về CRS hợp lệ trước khi render.",
                    layer_id=layer.layer_id,
                    composition_id=spec.composition_id,
                    target_id=spec.target_id,
                )
            )
        except MemoryError:
            issues.append(
                _issue(
                    "render.raster.memory_error",
                    f"Không đủ bộ nhớ để đọc layer '{layer.layer_id}'.",
                    "Giảm kích thước output hoặc tắt bớt layer trước khi render lại.",
                    layer_id=layer.layer_id,
                    composition_id=spec.composition_id,
                    target_id=spec.target_id,
                )
            )
        except (RasterioError, OSError, ValueError) as exc:
            issues.append(
                _issue(
                    "render.raster.unreadable",
                    f"Không đọc được layer '{layer.layer_id}': {exc}",
                    "Kiểm tra đường dẫn file và quyền đọc; thử mở lại bằng QGIS để xác minh.",
                    layer_id=layer.layer_id,
                    composition_id=spec.composition_id,
                    target_id=spec.target_id,
                )
            )

    if spec.visible_layers and not painted_layer_ids and not issues and skipped_no_overlap:
        issues.append(
            _render_issue(
                "render.raster.no_overlap",
                "Không có layer visible nào phủ vùng bản đồ cần render.",
                "Kiểm tra lại tâm bản đồ, scale hoặc dữ liệu raster của composition.",
                composition_id=spec.composition_id,
                target_id=spec.target_id,
            )
        )

    if not painted_layer_ids and issues:
        raise RenderError(issues)

    return RasterRenderResult(
        canvas=canvas,
        issues=tuple(issues),
        painted_layer_ids=tuple(painted_layer_ids),
    )
