"""SQLite-backed historical imagery registry boundary."""

from thucthengay.history.loading import (
    HistoricalImageRecord,
    HistoricalLoadingPlan,
    HistoricalLoadingResult,
)
from thucthengay.history.service import (
    HistoricalPathPrefixReplacementPreview,
    HistoricalPathPrefixReplacementResult,
    HistoricalPathPrefixReplacementRow,
    HistoricalPathRepairResult,
    HistoryConfigurationError,
    HistoryExportRecordResult,
    HistoryInitializationResult,
    HistoryRecordError,
    HistoryRecordResult,
    HistoryService,
    HistorySkipResult,
)

__all__ = [
    "HistoryConfigurationError",
    "HistoryExportRecordResult",
    "HistoryInitializationResult",
    "HistoricalPathPrefixReplacementPreview",
    "HistoricalPathPrefixReplacementResult",
    "HistoricalPathPrefixReplacementRow",
    "HistoricalPathRepairResult",
    "HistoricalImageRecord",
    "HistoricalLoadingPlan",
    "HistoricalLoadingResult",
    "HistoryRecordError",
    "HistoryRecordResult",
    "HistoryService",
    "HistorySkipResult",
]
