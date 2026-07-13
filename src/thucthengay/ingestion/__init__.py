"""Imagery ingestion package."""

from thucthengay.ingestion.cache_builder import (
    CacheImageInput,
    CachePopulationResult,
    cache_layer_source,
    populate_workspace_cache,
)
from thucthengay.ingestion.composition_builder import (
    UNMATCHED_TARGET_ID_PREFIX,
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
    "CacheImageInput",
    "CachePopulationResult",
    "CompositionCreationResult",
    "cache_layer_source",
    "create_target_date_compositions",
    "ImageryScanResult",
    "ImageryTargetMatch",
    "ParsedBusinessMetadata",
    "RasterBounds",
    "RasterMetadata",
    "ScannedGeoTiff",
    "TargetBoundary",
    "TargetMatchingResult",
    "UNMATCHED_TARGET_ID_PREFIX",
    "discover_geotiffs",
    "load_target_boundary",
    "match_imagery_to_targets",
    "parse_business_metadata",
    "scan_geotiff_file",
    "scan_imagery_folder",
    "populate_workspace_cache",
]
