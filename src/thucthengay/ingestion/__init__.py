"""Imagery ingestion package."""

from thucthengay.ingestion.cache_builder import (
    CacheImageInput,
    CachePopulationResult,
    cache_layer_source,
    populate_workspace_cache,
)
from thucthengay.ingestion.composition_builder import (
    CompositionCreationResult,
    create_target_date_compositions,
)
from thucthengay.ingestion.intersection import (
    ImageryTargetMatch,
    TargetBoundary,
    TargetMatchingResult,
    load_target_boundary,
    match_imagery_to_targets,
)
from thucthengay.ingestion.metadata_parser import ParsedBusinessMetadata, parse_business_metadata
from thucthengay.ingestion.scanner import (
    ImageryScanResult,
    RasterBounds,
    RasterMetadata,
    ScannedGeoTiff,
    discover_geotiffs,
    scan_geotiff_file,
    scan_imagery_folder,
)

__all__ = [
    "CachePopulationResult",
    "CacheImageInput",
    "cache_layer_source",
    "CompositionCreationResult",
    "ImageryScanResult",
    "ImageryTargetMatch",
    "ParsedBusinessMetadata",
    "RasterBounds",
    "RasterMetadata",
    "ScannedGeoTiff",
    "TargetBoundary",
    "TargetMatchingResult",
    "discover_geotiffs",
    "load_target_boundary",
    "match_imagery_to_targets",
    "parse_business_metadata",
    "populate_workspace_cache",
    "create_target_date_compositions",
    "scan_geotiff_file",
    "scan_imagery_folder",
]
