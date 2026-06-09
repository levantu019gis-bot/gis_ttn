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
    HistoryInitializationResult,
    HistoryRecordError,
    HistoryRecordResult,
    HistoryService,
)

__all__ = [
    "HistoryConfigurationError",
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
]
