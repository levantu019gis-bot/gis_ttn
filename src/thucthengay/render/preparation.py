"""Non-destructive raster preparation workflow for large imagery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rasterio.enums import Resampling

from thucthengay.render.overview import (
    RasterOverviewReadiness,
    build_raster_preparation_plan,
    inspect_raster_overview_readiness,
    prepare_raster_overview_output,
)


@dataclass(frozen=True)
class PreparedRasterResult:
    """Result of creating a prepared raster copy."""

    source_path: str
    prepared_path: str
    readiness: RasterOverviewReadiness


def prepared_raster_path(source_path: str | Path, prepared_root: str | Path) -> Path:
    """Return the deterministic prepared-raster path for a source image."""

    source = Path(source_path)
    return Path(prepared_root) / f"{source.stem}.prepared.tif"


def prepare_raster_copy(
    source_path: str | Path,
    *,
    prepared_root: str | Path,
    create_cog: bool = False,
    resampling: Resampling = Resampling.nearest,
) -> PreparedRasterResult:
    """Create a prepared raster copy atomically and inspect the final output."""

    source = Path(source_path)
    destination = prepared_raster_path(source, prepared_root)
    tmp_destination = destination.with_suffix(f"{destination.suffix}.tmp")
    if tmp_destination.exists():
        tmp_destination.unlink()

    plan = build_raster_preparation_plan(
        source,
        output_path=tmp_destination,
        create_cog=create_cog,
    )
    prepare_raster_overview_output(plan, resampling=resampling)
    tmp_destination.replace(destination)
    readiness = inspect_raster_overview_readiness(destination)
    return PreparedRasterResult(
        source_path=str(source),
        prepared_path=str(destination),
        readiness=readiness,
    )
