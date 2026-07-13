"""SQLite service boundary for historical image registry state."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import rasterio
from rasterio.errors import RasterioIOError

from thucthengay.history.loading import (
    HistoricalImageRecord,
    HistoricalLoadingPlan,
    HistoricalLoadingResult,
)
from thucthengay.models import (
    Composition,
    HistoricalLookbackAnchor,
    HistoricalSelectionMode,
    ImageLayer,
    Issue,
    IssueScope,
    IssueSeverity,
    TargetConfig,
)

SCHEMA_VERSION = 2
DEFAULT_BUSY_TIMEOUT_MS = 5_000
_UNCHANGED = object()


class HistoryConfigurationError(RuntimeError):
    """Raised when historical registry settings cannot open a database safely."""


class HistoryRecordError(RuntimeError):
    """Raised when an enabled registry cannot persist included history."""


@dataclass(frozen=True)
class HistoryInitializationResult:
    """Outcome returned after initializing the optional registry."""

    enabled: bool
    database_path: Path | None
    schema_version: int | None


@dataclass(frozen=True)
class HistoryRecordResult:
    """Outcome returned after recording one included composition."""

    enabled: bool
    composition_id: str
    recorded_layers: int
    include_events: int


@dataclass(frozen=True)
class HistoryExportRecordResult:
    """Outcome returned after recording one export-visible composition."""

    enabled: bool
    composition_id: str
    recorded_layers: int
    include_events: int
    existing_layers: int


@dataclass(frozen=True)
class HistorySkipResult:
    """Outcome returned after marking a previously included composition as skipped."""

    enabled: bool
    composition_id: str
    skipped_layers: int


@dataclass(frozen=True)
class HistoricalPathPrefixReplacementRow:
    """One registry path affected by a bulk prefix replacement."""

    image_asset_id: int
    old_path: Path
    new_path: Path


@dataclass(frozen=True)
class HistoricalPathPrefixReplacementPreview:
    """Preview returned before applying a bulk historical path update."""

    old_prefix: Path
    new_prefix: Path
    rows: tuple[HistoricalPathPrefixReplacementRow, ...]

    @property
    def affected_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class HistoricalPathRepairResult:
    """Outcome returned after a validated historical path repair."""

    image_asset_id: int
    old_path: Path
    new_path: Path
    issue: Issue | None = None


@dataclass(frozen=True)
class HistoricalPathPrefixReplacementResult:
    """Outcome returned after applying a confirmed bulk prefix replacement."""

    old_prefix: Path
    new_prefix: Path
    updated_count: int


@dataclass(frozen=True)
class HistoricalImageManagementRow:
    """Flattened row for history management screens and diagnostics."""

    image_asset_id: int
    target_id: str
    source_path: Path
    cache_path: Path | None
    capture_date: date | None
    capture_time: time | None
    cloud_percent: float | None
    active: bool
    latest_status: str
    latest_workspace_path: str | None
    latest_composition_id: str | None


@dataclass(frozen=True)
class HistoryService:
    """Owns all direct SQLite access for the historical image registry."""

    database_path: Path | None
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS
    enabled: bool = True

    @classmethod
    def disabled(cls) -> HistoryService:
        """Return a no-op service that never creates a SQLite file."""
        return cls(database_path=None, enabled=False)

    def initialize(self) -> HistoryInitializationResult:
        """Create or migrate the registry schema if the service is enabled."""
        if not self.enabled:
            return HistoryInitializationResult(
                enabled=False,
                database_path=None,
                schema_version=None,
            )

        database_path = self._required_database_path()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                _create_schema(connection)
                _set_schema_version(connection, SCHEMA_VERSION)

        return HistoryInitializationResult(
            enabled=True,
            database_path=database_path,
            schema_version=SCHEMA_VERSION,
        )

    def list_image_management_rows(
        self,
        *,
        target_id: str | None = None,
        active_only: bool = True,
    ) -> tuple[HistoricalImageManagementRow, ...]:
        """List history image rows for management and path repair tools."""

        if not self.enabled:
            return ()
        database_path = self._required_database_path()
        if not database_path.exists():
            return ()
        clauses: list[str] = []
        params: list[object] = []
        if target_id:
            clauses.append("target_history.target_id = ?")
            params.append(target_id)
        if active_only:
            clauses.append("target_image_history.active = 1")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    image_asset.image_asset_id,
                    target_history.target_id,
                    image_asset.source_path,
                    image_asset.cache_path,
                    image_asset.capture_date,
                    image_asset.capture_time,
                    image_asset.cloud_percent,
                    target_image_history.active,
                    target_image_history.latest_status,
                    target_image_history.latest_workspace_path,
                    target_image_history.latest_composition_id
                FROM target_history
                JOIN target_image_history USING (target_history_id)
                JOIN image_asset USING (image_asset_id)
                {where_sql}
                ORDER BY target_history.target_id,
                         image_asset.capture_date DESC,
                         image_asset.capture_time DESC,
                         image_asset.source_path
                """,
                tuple(params),
            ).fetchall()
        return tuple(_management_row_from_sql(row) for row in rows)

    def record_included_composition(
        self,
        composition: Composition,
        *,
        target: TargetConfig,
        workspace_path: str | Path,
    ) -> HistoryRecordResult:
        """Record the visible layers from one successfully included composition."""
        if not self.enabled:
            return HistoryRecordResult(
                enabled=False,
                composition_id=composition.composition_id,
                recorded_layers=0,
                include_events=0,
            )
        if not composition.include or not composition.ready:
            msg = (
                "included history can only be recorded after a composition is ready "
                "and included"
            )
            raise HistoryRecordError(msg)

        database_path = self._required_database_path()
        if not database_path.exists():
            self.initialize()

        visible_layers = [layer for layer in composition.layers if layer.visible]
        workspace_text = str(Path(workspace_path).expanduser().resolve())
        included_at = _utc_iso()
        with closing(self._connect()) as connection:
            _ensure_target_image_history_review_columns(connection)
            try:
                with connection:
                    target_history_id = _upsert_target_history(
                        connection,
                        target=target,
                        timestamp=included_at,
                    )
                    event_count = 0
                    for layer in visible_layers:
                        image_asset_id = _upsert_image_asset(
                            connection,
                            composition=composition,
                            layer=layer,
                            timestamp=included_at,
                        )
                        target_image_history_id = _upsert_target_image_history(
                            connection,
                            target_history_id=target_history_id,
                            image_asset_id=image_asset_id,
                            workspace_path=workspace_text,
                            composition_id=composition.composition_id,
                            included_at=included_at,
                        )
                        _append_include_event(
                            connection,
                            target_image_history_id=target_image_history_id,
                            workspace_path=workspace_text,
                            composition_id=composition.composition_id,
                            included_at=included_at,
                        )
                        event_count += 1
            except sqlite3.Error as error:
                msg = f"could not record included history for {composition.composition_id}: {error}"
                raise HistoryRecordError(msg) from error

        return HistoryRecordResult(
            enabled=True,
            composition_id=composition.composition_id,
            recorded_layers=len(visible_layers),
            include_events=event_count,
        )

    def record_exported_composition(
        self,
        composition: Composition,
        *,
        target: TargetConfig,
        workspace_path: str | Path,
    ) -> HistoryExportRecordResult:
        """Record visible layers for a composition that was actually used by export.

        Unlike the Review/Edit include path, export sync must be idempotent. Re-running
        the same export should not append duplicate events when the target-image row is
        already active for the same workspace and composition.
        """
        if not self.enabled:
            return HistoryExportRecordResult(
                enabled=False,
                composition_id=composition.composition_id,
                recorded_layers=0,
                include_events=0,
                existing_layers=0,
            )

        database_path = self._required_database_path()
        if not database_path.exists():
            self.initialize()

        visible_layers = [layer for layer in composition.layers if layer.visible]
        workspace_text = str(Path(workspace_path).expanduser().resolve())
        exported_at = _utc_iso()
        recorded_layers = 0
        event_count = 0
        existing_layers = 0
        with closing(self._connect()) as connection:
            _ensure_target_image_history_review_columns(connection)
            try:
                with connection:
                    target_history_id = _upsert_target_history(
                        connection,
                        target=target,
                        timestamp=exported_at,
                    )
                    for layer in visible_layers:
                        image_asset_id = _upsert_image_asset(
                            connection,
                            composition=composition,
                            layer=layer,
                            timestamp=exported_at,
                        )
                        if _target_image_history_is_current(
                            connection,
                            target_history_id=target_history_id,
                            image_asset_id=image_asset_id,
                            workspace_path=workspace_text,
                            composition_id=composition.composition_id,
                        ):
                            existing_layers += 1
                            continue
                        target_image_history_id = _upsert_target_image_history(
                            connection,
                            target_history_id=target_history_id,
                            image_asset_id=image_asset_id,
                            workspace_path=workspace_text,
                            composition_id=composition.composition_id,
                            included_at=exported_at,
                        )
                        _append_include_event(
                            connection,
                            target_image_history_id=target_image_history_id,
                            workspace_path=workspace_text,
                            composition_id=composition.composition_id,
                            included_at=exported_at,
                        )
                        recorded_layers += 1
                        event_count += 1
            except sqlite3.Error as error:
                msg = f"could not record export history for {composition.composition_id}: {error}"
                raise HistoryRecordError(msg) from error

        return HistoryExportRecordResult(
            enabled=True,
            composition_id=composition.composition_id,
            recorded_layers=recorded_layers,
            include_events=event_count,
            existing_layers=existing_layers,
        )

    def record_skipped_composition(
        self,
        composition: Composition,
        *,
        target: TargetConfig,
        workspace_path: str | Path,
    ) -> HistorySkipResult:
        """Mark visible layers from a previously included composition as no longer active."""
        if not self.enabled:
            return HistorySkipResult(
                enabled=False,
                composition_id=composition.composition_id,
                skipped_layers=0,
            )

        database_path = self._required_database_path()
        if not database_path.exists():
            return HistorySkipResult(
                enabled=True,
                composition_id=composition.composition_id,
                skipped_layers=0,
            )

        visible_layers = [layer for layer in composition.layers if layer.visible]
        workspace_text = str(Path(workspace_path).expanduser().resolve())
        skipped_at = _utc_iso()
        skipped_layers = 0
        with closing(self._connect()) as connection:
            _ensure_target_image_history_review_columns(connection)
            try:
                with connection:
                    for layer in visible_layers:
                        skipped_layers += _mark_target_image_history_skipped(
                            connection,
                            target=target,
                            composition=composition,
                            layer=layer,
                            workspace_path=workspace_text,
                            skipped_at=skipped_at,
                        )
            except sqlite3.Error as error:
                msg = f"could not mark skipped history for {composition.composition_id}: {error}"
                raise HistoryRecordError(msg) from error

        return HistorySkipResult(
            enabled=True,
            composition_id=composition.composition_id,
            skipped_layers=skipped_layers,
        )

    def load_historical_images(
        self,
        plan: HistoricalLoadingPlan,
    ) -> HistoricalLoadingResult:
        """Load registry rows selected by the resolved ingestion historical plan."""
        if not self.enabled or not plan.enabled:
            return HistoricalLoadingResult()

        database_path = self._required_database_path()
        if not database_path.exists():
            self.initialize()

        records: list[HistoricalImageRecord] = []
        with closing(self._connect()) as connection:
            _ensure_target_image_history_review_columns(connection)
            for target_id in plan.target_ids:
                records.extend(_query_historical_records(connection, plan, target_id))

        valid_records, issues = _validate_historical_records(records)
        return HistoricalLoadingResult(
            loaded_image_count=len(valid_records),
            skipped_image_count=len(records) - len(valid_records),
            records=valid_records,
            issues=issues,
        )

    def repair_image_path(
        self,
        image_asset_id: int,
        replacement_path: str | Path,
        *,
        capture_date: object | None = _UNCHANGED,
        capture_time: object | None = _UNCHANGED,
        cloud_percent: float | None | object = _UNCHANGED,
    ) -> HistoricalPathRepairResult:
        """Validate and update one image asset source path transactionally."""
        if not self.enabled:
            msg = "historical registry is disabled"
            raise HistoryRecordError(msg)

        resolved_replacement = Path(replacement_path).expanduser().resolve()
        validation_issue = _validate_historical_path(
            image_asset_id=image_asset_id,
            target_id=None,
            source_path=resolved_replacement,
        )
        if validation_issue is not None:
            msg = validation_issue.message
            raise HistoryRecordError(msg)

        database_path = self._required_database_path()
        if not database_path.exists():
            self.initialize()

        updated_at = _utc_iso()
        with closing(self._connect()) as connection:
            try:
                with connection:
                    row = connection.execute(
                        """
                        SELECT source_path, capture_date, capture_time, cloud_percent
                        FROM image_asset
                        WHERE image_asset_id = ?
                        """,
                        (image_asset_id,),
                    ).fetchone()
                    if row is None:
                        msg = f"image_asset_id does not exist: {image_asset_id}"
                        raise HistoryRecordError(msg)
                    old_path = Path(str(row[0])).expanduser()
                    next_capture_date = (
                        row[1] if capture_date is _UNCHANGED else _date_text_or_none(capture_date)
                    )
                    next_capture_time = (
                        row[2] if capture_time is _UNCHANGED else _time_text_or_none(capture_time)
                    )
                    next_cloud_percent = row[3] if cloud_percent is _UNCHANGED else cloud_percent
                    connection.execute(
                        """
                        UPDATE image_asset
                        SET source_path = ?,
                            capture_date = ?,
                            capture_time = ?,
                            cloud_percent = ?,
                            updated_at = ?
                        WHERE image_asset_id = ?
                        """,
                        (
                            str(resolved_replacement),
                            next_capture_date,
                            next_capture_time,
                            next_cloud_percent,
                            updated_at,
                            image_asset_id,
                        ),
                    )
            except sqlite3.Error as error:
                msg = f"could not repair historical image path {image_asset_id}: {error}"
                raise HistoryRecordError(msg) from error

        return HistoricalPathRepairResult(
            image_asset_id=image_asset_id,
            old_path=old_path,
            new_path=resolved_replacement,
        )

    def preview_path_prefix_replacement(
        self,
        old_prefix: str | Path,
        new_prefix: str | Path,
    ) -> HistoricalPathPrefixReplacementPreview:
        """Preview registry rows affected by a bulk path-prefix replacement."""
        normalized_old = Path(old_prefix).expanduser().resolve()
        normalized_new = Path(new_prefix).expanduser().resolve()
        database_path = self._required_database_path()
        if not database_path.exists():
            self.initialize()

        rows: list[HistoricalPathPrefixReplacementRow] = []
        with closing(self._connect()) as connection:
            for image_asset_id, source_path_text in connection.execute(
                "SELECT image_asset_id, source_path FROM image_asset ORDER BY image_asset_id"
            ).fetchall():
                source_path = Path(str(source_path_text)).expanduser().resolve()
                replacement = _replace_path_prefix(
                    source_path,
                    old_prefix=normalized_old,
                    new_prefix=normalized_new,
                )
                if replacement is None:
                    continue
                rows.append(
                    HistoricalPathPrefixReplacementRow(
                        image_asset_id=int(image_asset_id),
                        old_path=source_path,
                        new_path=replacement,
                    )
                )

        return HistoricalPathPrefixReplacementPreview(
            old_prefix=normalized_old,
            new_prefix=normalized_new,
            rows=tuple(rows),
        )

    def apply_path_prefix_replacement(
        self,
        old_prefix: str | Path,
        new_prefix: str | Path,
        *,
        confirmed: bool = False,
    ) -> HistoricalPathPrefixReplacementResult:
        """Apply a confirmed bulk path-prefix update inside one transaction."""
        if not confirmed:
            msg = "bulk historical path prefix replacement requires explicit confirmation"
            raise HistoryRecordError(msg)

        preview = self.preview_path_prefix_replacement(old_prefix, new_prefix)
        updated_at = _utc_iso()
        with closing(self._connect()) as connection:
            try:
                with connection:
                    for row in preview.rows:
                        connection.execute(
                            """
                            UPDATE image_asset
                            SET source_path = ?,
                                updated_at = ?
                            WHERE image_asset_id = ?
                            """,
                            (str(row.new_path), updated_at, row.image_asset_id),
                        )
            except sqlite3.Error as error:
                msg = f"could not apply historical path prefix replacement: {error}"
                raise HistoryRecordError(msg) from error

        return HistoricalPathPrefixReplacementResult(
            old_prefix=preview.old_prefix,
            new_prefix=preview.new_prefix,
            updated_count=preview.affected_count,
        )

    def _connect(self) -> sqlite3.Connection:
        """Open a registry connection with required pragmas for short operations."""
        database_path = self._required_database_path()
        connection = sqlite3.connect(database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {max(0, int(self.busy_timeout_ms))}")
        return connection

    def _required_database_path(self) -> Path:
        if self.database_path is None:
            msg = "historical registry database path is required when enabled"
            raise HistoryConfigurationError(msg)
        return Path(self.database_path).expanduser().resolve()


def _query_historical_records(
    connection: sqlite3.Connection,
    plan: HistoricalLoadingPlan,
    target_id: str,
) -> list[HistoricalImageRecord]:
    selection = plan.image_selection
    capture_date_cap = plan.current_session_latest_capture_date
    if selection.mode == HistoricalSelectionMode.LATEST_DATE:
        return _query_latest_date_records(
            connection,
            target_id,
            capture_date_cap=capture_date_cap,
        )
    if selection.mode == HistoricalSelectionMode.LATEST_IMAGES:
        return _query_latest_image_records(
            connection,
            target_id,
            limit=selection.limit_per_target or 0,
            capture_date_cap=capture_date_cap,
        )
    if selection.mode == HistoricalSelectionMode.DATE_RANGE:
        return _query_date_range_records(
            connection,
            target_id,
            start_date=selection.start_date,
            end_date=_cap_end_date(selection.end_date, capture_date_cap),
        )
    if selection.mode == HistoricalSelectionMode.LOOKBACK_DAYS:
        return _query_lookback_records(connection, plan, target_id)
    return []


def _query_latest_date_records(
    connection: sqlite3.Connection,
    target_id: str,
    *,
    capture_date_cap: date | None,
) -> list[HistoricalImageRecord]:
    cap_condition = _capture_date_cap_condition(capture_date_cap)
    latest_date_row = connection.execute(
        f"""
        SELECT MAX(image_asset.capture_date)
        FROM target_history
        JOIN target_image_history USING (target_history_id)
        JOIN image_asset USING (image_asset_id)
        WHERE target_history.target_id = ?
          AND target_image_history.active = 1
          AND image_asset.capture_date IS NOT NULL
          {cap_condition.sql}
        """,
        (target_id, *cap_condition.parameters),
    ).fetchone()
    latest_date = latest_date_row[0] if latest_date_row else None
    if latest_date is None:
        return []
    rows = connection.execute(
        f"{_HISTORICAL_RECORDS_SELECT} AND image_asset.capture_date = ? "
        f"{_HISTORICAL_RECORDS_ORDER}",
        (target_id, latest_date),
    ).fetchall()
    return _records_from_rows(rows)


def _query_latest_image_records(
    connection: sqlite3.Connection,
    target_id: str,
    *,
    limit: int,
    capture_date_cap: date | None,
) -> list[HistoricalImageRecord]:
    if limit <= 0:
        return []
    cap_condition = _capture_date_cap_condition(capture_date_cap)
    rows = connection.execute(
        f"{_HISTORICAL_RECORDS_SELECT} {cap_condition.sql} "
        f"{_HISTORICAL_RECORDS_ORDER} LIMIT ?",
        (target_id, *cap_condition.parameters, limit),
    ).fetchall()
    return _records_from_rows(rows)


def _query_date_range_records(
    connection: sqlite3.Connection,
    target_id: str,
    *,
    start_date: date | None,
    end_date: date | None,
) -> list[HistoricalImageRecord]:
    if start_date is None or end_date is None:
        return []
    if start_date > end_date:
        return []
    rows = connection.execute(
        f"{_HISTORICAL_RECORDS_SELECT} "
        "AND image_asset.capture_date BETWEEN ? AND ? "
        f"{_HISTORICAL_RECORDS_ORDER}",
        (target_id, start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    return _records_from_rows(rows)


def _query_lookback_records(
    connection: sqlite3.Connection,
    plan: HistoricalLoadingPlan,
    target_id: str,
) -> list[HistoricalImageRecord]:
    selection = plan.image_selection
    if selection.lookback_days is None:
        return []
    if selection.lookback_anchor == HistoricalLookbackAnchor.TODAY:
        end_date = date.today()
    else:
        end_date = plan.current_session_latest_capture_date
    end_date = _cap_end_date(end_date, plan.current_session_latest_capture_date)
    if end_date is None:
        return []
    start_date = end_date - timedelta(days=selection.lookback_days - 1)
    return _query_date_range_records(
        connection,
        target_id,
        start_date=start_date,
        end_date=end_date,
    )


@dataclass(frozen=True)
class _SqlCondition:
    sql: str
    parameters: tuple[str, ...] = ()


def _capture_date_cap_condition(capture_date_cap: date | None) -> _SqlCondition:
    if capture_date_cap is None:
        return _SqlCondition(sql="")
    return _SqlCondition(
        sql="AND image_asset.capture_date <= ?",
        parameters=(capture_date_cap.isoformat(),),
    )


def _cap_end_date(end_date: date | None, capture_date_cap: date | None) -> date | None:
    if end_date is None:
        return capture_date_cap
    if capture_date_cap is None:
        return end_date
    return min(end_date, capture_date_cap)


_HISTORICAL_RECORDS_SELECT = """
    SELECT
        image_asset.image_asset_id,
        target_history.target_id,
        image_asset.source_path,
        image_asset.cache_path,
        image_asset.capture_date,
        image_asset.capture_time,
        image_asset.cloud_percent
    FROM target_history
    JOIN target_image_history USING (target_history_id)
    JOIN image_asset USING (image_asset_id)
    WHERE target_history.target_id = ?
      AND target_image_history.active = 1
"""

_HISTORICAL_RECORDS_ORDER = """
    ORDER BY
        image_asset.capture_date DESC,
        image_asset.capture_time IS NULL ASC,
        image_asset.capture_time DESC,
        target_image_history.updated_at DESC,
        image_asset.source_path DESC
"""


def _records_from_rows(rows: list[tuple[object, ...]]) -> list[HistoricalImageRecord]:
    return [
        HistoricalImageRecord(
            image_asset_id=int(row[0]),
            target_id=str(row[1]),
            source_path=Path(str(row[2])).expanduser(),
            cache_path=str(row[3]) if row[3] is not None else None,
            capture_date=_parse_date(row[4]),
            capture_time=_parse_time(row[5]),
            cloud_percent=float(row[6]) if row[6] is not None else None,
        )
        for row in rows
    ]


def _management_row_from_sql(row: tuple[object, ...]) -> HistoricalImageManagementRow:
    return HistoricalImageManagementRow(
        image_asset_id=int(row[0]),
        target_id=str(row[1]),
        source_path=Path(str(row[2])).expanduser(),
        cache_path=Path(str(row[3])).expanduser() if row[3] else None,
        capture_date=_parse_date(row[4]),
        capture_time=_parse_time(row[5]),
        cloud_percent=float(row[6]) if row[6] is not None else None,
        active=bool(row[7]),
        latest_status=str(row[8]),
        latest_workspace_path=str(row[9]) if row[9] else None,
        latest_composition_id=str(row[10]) if row[10] else None,
    )


def _validate_historical_records(
    records: list[HistoricalImageRecord],
) -> tuple[list[HistoricalImageRecord], list[Issue]]:
    valid_records: list[HistoricalImageRecord] = []
    issues: list[Issue] = []
    for record in records:
        issue = _validate_historical_path(
            image_asset_id=record.image_asset_id,
            target_id=record.target_id,
            source_path=record.source_path,
        )
        if issue is not None:
            issues.append(issue)
            continue
        valid_records.append(record)
    return valid_records, issues


def _validate_historical_path(
    *,
    image_asset_id: int,
    target_id: str | None,
    source_path: Path,
) -> Issue | None:
    resolved_path = source_path.expanduser().resolve()
    if not resolved_path.is_file():
        return _historical_path_issue(
            issue_id="historical.path_missing",
            image_asset_id=image_asset_id,
            target_id=target_id,
            source_path=resolved_path,
            message=f"Không tìm thấy ảnh lịch sử `{resolved_path}`.",
            remediation=(
                "Chọn file thay thế cho ảnh lịch sử này hoặc dùng sửa prefix hàng loạt "
                "nếu nhiều ảnh đã được chuyển sang thư mục mới."
            ),
        )

    try:
        with rasterio.open(resolved_path) as dataset:
            usable = (
                dataset.width > 0
                and dataset.height > 0
                and dataset.count > 0
                and bool(dataset.crs)
            )
    except (RasterioIOError, OSError, ValueError) as error:
        return _historical_path_issue(
            issue_id="historical.geotiff_unreadable",
            image_asset_id=image_asset_id,
            target_id=target_id,
            source_path=resolved_path,
            message=f"Không thể mở ảnh lịch sử `{resolved_path}` như GeoTIFF: {error}",
            remediation=(
                "Kiểm tra định dạng file, quyền truy cập hoặc chọn file GeoTIFF thay thế "
                "trước khi tải lại ảnh lịch sử."
            ),
        )

    if not usable:
        return _historical_path_issue(
            issue_id="historical.geotiff_unusable",
            image_asset_id=image_asset_id,
            target_id=target_id,
            source_path=resolved_path,
            message=f"Ảnh lịch sử `{resolved_path}` không có dữ liệu GeoTIFF/CRS sử dụng được.",
            remediation="Chọn một file GeoTIFF hợp lệ khác cho ảnh lịch sử này.",
        )
    return None


def _historical_path_issue(
    *,
    issue_id: str,
    image_asset_id: int,
    target_id: str | None,
    source_path: Path,
    message: str,
    remediation: str,
) -> Issue:
    return Issue(
        issue_id=issue_id,
        severity=IssueSeverity.WARNING,
        scope=IssueScope.LAYER,
        target_id=target_id,
        layer_id=str(image_asset_id),
        message=message,
        remediation=remediation,
    )


def _replace_path_prefix(
    source_path: Path,
    *,
    old_prefix: Path,
    new_prefix: Path,
) -> Path | None:
    try:
        relative_path = source_path.relative_to(old_prefix)
    except ValueError:
        return None
    return new_prefix / relative_path


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(str(value))


def _parse_time(value: object) -> time | None:
    if value is None:
        return None
    return time.fromisoformat(str(value))


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL CHECK (version >= 1),
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS target_history (
            target_history_id INTEGER PRIMARY KEY,
            target_id TEXT NOT NULL UNIQUE,
            target_name TEXT NOT NULL,
            target_alias TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS image_asset (
            image_asset_id INTEGER PRIMARY KEY,
            source_path TEXT NOT NULL,
            cache_path TEXT,
            capture_date TEXT,
            capture_time TEXT,
            cloud_percent REAL CHECK (
                cloud_percent IS NULL OR (cloud_percent >= 0 AND cloud_percent <= 100)
            ),
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (source_path, capture_date, capture_time)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS target_image_history (
            target_image_history_id INTEGER PRIMARY KEY,
            target_history_id INTEGER NOT NULL,
            image_asset_id INTEGER NOT NULL,
            latest_workspace_path TEXT,
            latest_composition_id TEXT,
            latest_included_at TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            latest_status TEXT NOT NULL DEFAULT 'included',
            latest_skipped_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (target_history_id, image_asset_id),
            FOREIGN KEY (target_history_id)
                REFERENCES target_history (target_history_id)
                ON DELETE CASCADE,
            FOREIGN KEY (image_asset_id)
                REFERENCES image_asset (image_asset_id)
                ON DELETE CASCADE
        )
        """
    )
    _ensure_target_image_history_review_columns(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS include_event (
            include_event_id INTEGER PRIMARY KEY,
            target_image_history_id INTEGER NOT NULL,
            workspace_path TEXT NOT NULL,
            composition_id TEXT NOT NULL,
            included_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (target_image_history_id)
                REFERENCES target_image_history (target_image_history_id)
                ON DELETE CASCADE
        )
        """
    )


def _ensure_target_image_history_review_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(target_image_history)").fetchall()
    }
    if "active" not in existing_columns:
        connection.execute(
            "ALTER TABLE target_image_history ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
        )
    if "latest_status" not in existing_columns:
        connection.execute(
            "ALTER TABLE target_image_history "
            "ADD COLUMN latest_status TEXT NOT NULL DEFAULT 'included'"
        )
    if "latest_skipped_at" not in existing_columns:
        connection.execute("ALTER TABLE target_image_history ADD COLUMN latest_skipped_at TEXT")


def _set_schema_version(connection: sqlite3.Connection, version: int) -> None:
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat()
    connection.execute(
        """
        INSERT INTO schema_version (id, version, applied_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            version = excluded.version,
            applied_at = excluded.applied_at
        """,
        (version, timestamp),
    )


def _upsert_target_history(
    connection: sqlite3.Connection,
    *,
    target: TargetConfig,
    timestamp: str,
) -> int:
    connection.execute(
        """
        INSERT INTO target_history (
            target_id,
            target_name,
            target_alias,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(target_id) DO UPDATE SET
            target_name = excluded.target_name,
            target_alias = excluded.target_alias,
            updated_at = excluded.updated_at
        """,
        (target.id, target.name, target.alias, timestamp, timestamp),
    )
    return _required_row_id(
        connection,
        "SELECT target_history_id FROM target_history WHERE target_id = ?",
        (target.id,),
    )


def _upsert_image_asset(
    connection: sqlite3.Connection,
    *,
    composition: Composition,
    layer: ImageLayer,
    timestamp: str,
) -> int:
    capture_date = (layer.capture_date or composition.capture_date).isoformat()
    capture_time = layer.capture_time.isoformat() if layer.capture_time is not None else None
    existing_id = _optional_row_id(
        connection,
        """
        SELECT image_asset_id
        FROM image_asset
        WHERE source_path = ?
          AND capture_date IS ?
          AND capture_time IS ?
        """,
        (layer.source_path, capture_date, capture_time),
    )
    if existing_id is not None:
        connection.execute(
            """
            UPDATE image_asset
            SET cache_path = ?,
                cloud_percent = ?,
                updated_at = ?
            WHERE image_asset_id = ?
            """,
            (layer.cache_path, layer.cloud_percent, timestamp, existing_id),
        )
        return existing_id

    cursor = connection.execute(
        """
        INSERT INTO image_asset (
            source_path,
            cache_path,
            capture_date,
            capture_time,
            cloud_percent,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, '{}', ?, ?)
        """,
        (
            layer.source_path,
            layer.cache_path,
            capture_date,
            capture_time,
            layer.cloud_percent,
            timestamp,
            timestamp,
        ),
    )
    return int(cursor.lastrowid)


def _upsert_target_image_history(
    connection: sqlite3.Connection,
    *,
    target_history_id: int,
    image_asset_id: int,
    workspace_path: str,
    composition_id: str,
    included_at: str,
) -> int:
    existing_id = _optional_row_id(
        connection,
        """
        SELECT target_image_history_id
        FROM target_image_history
        WHERE target_history_id = ?
          AND image_asset_id = ?
        """,
        (target_history_id, image_asset_id),
    )
    if existing_id is not None:
        connection.execute(
            """
            UPDATE target_image_history
            SET latest_workspace_path = ?,
                latest_composition_id = ?,
                latest_included_at = ?,
                active = 1,
                latest_status = 'included',
                latest_skipped_at = NULL,
                updated_at = ?
            WHERE target_image_history_id = ?
            """,
            (workspace_path, composition_id, included_at, included_at, existing_id),
        )
        return existing_id

    cursor = connection.execute(
        """
        INSERT INTO target_image_history (
            target_history_id,
            image_asset_id,
            latest_workspace_path,
            latest_composition_id,
            latest_included_at,
            active,
            latest_status,
            latest_skipped_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 1, 'included', NULL, ?, ?)
        """,
        (
            target_history_id,
            image_asset_id,
            workspace_path,
            composition_id,
            included_at,
            included_at,
            included_at,
        ),
    )
    return int(cursor.lastrowid)


def _target_image_history_is_current(
    connection: sqlite3.Connection,
    *,
    target_history_id: int,
    image_asset_id: int,
    workspace_path: str,
    composition_id: str,
) -> bool:
    row = connection.execute(
        """
        SELECT active, latest_workspace_path, latest_composition_id
        FROM target_image_history
        WHERE target_history_id = ?
          AND image_asset_id = ?
        """,
        (target_history_id, image_asset_id),
    ).fetchone()
    if row is None:
        return False
    active, latest_workspace_path, latest_composition_id = row
    return (
        int(active) == 1
        and latest_workspace_path == workspace_path
        and latest_composition_id == composition_id
    )


def _mark_target_image_history_skipped(
    connection: sqlite3.Connection,
    *,
    target: TargetConfig,
    composition: Composition,
    layer: ImageLayer,
    workspace_path: str,
    skipped_at: str,
) -> int:
    capture_date = (layer.capture_date or composition.capture_date).isoformat()
    capture_time = layer.capture_time.isoformat() if layer.capture_time is not None else None
    cursor = connection.execute(
        """
        UPDATE target_image_history
        SET active = 0,
            latest_status = 'skipped',
            latest_skipped_at = ?,
            updated_at = ?
        WHERE target_image_history_id IN (
            SELECT target_image_history.target_image_history_id
            FROM target_image_history
            JOIN target_history USING (target_history_id)
            JOIN image_asset USING (image_asset_id)
            WHERE target_history.target_id = ?
              AND image_asset.source_path = ?
              AND image_asset.capture_date IS ?
              AND image_asset.capture_time IS ?
              AND target_image_history.latest_workspace_path = ?
              AND target_image_history.latest_composition_id = ?
              AND target_image_history.active = 1
        )
        """,
        (
            skipped_at,
            skipped_at,
            target.id,
            layer.source_path,
            capture_date,
            capture_time,
            workspace_path,
            composition.composition_id,
        ),
    )
    return int(cursor.rowcount or 0)


def _append_include_event(
    connection: sqlite3.Connection,
    *,
    target_image_history_id: int,
    workspace_path: str,
    composition_id: str,
    included_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO include_event (
            target_image_history_id,
            workspace_path,
            composition_id,
            included_at,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            target_image_history_id,
            workspace_path,
            composition_id,
            included_at,
            included_at,
        ),
    )


def _optional_row_id(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...],
) -> int | None:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        return None
    return int(row[0])


def _required_row_id(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...],
) -> int:
    row_id = _optional_row_id(connection, query, parameters)
    if row_id is None:
        msg = "expected registry row was not created"
        raise HistoryRecordError(msg)
    return row_id


def _utc_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _date_text_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _time_text_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)
