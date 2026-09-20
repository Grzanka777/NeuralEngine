"""Local SQLite implementation of OpenCode session resolver.

Implements preferred association order:
1. Direct OpenCode-provided session ID
2. Process-correlated session ID
3. New-session delta (snapshot before/after)
4. Timestamp/activity correlation

OpenCode 2.x stores sessions in ``session_v2``.  Older installations use
``session`` and some upgraded databases retain both tables, so reads union
the two known schemas by session ID.  Never silently picks an arbitrary
session; fails closed on ambiguity.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from neural_engine.domain.opencode_context import (
    SessionAssociationMethod,
    SessionResolutionResult,
)
from neural_engine.ports.opencode_session_resolver import OpencodeSessionResolver

_DEFAULT_OPENCODE_DATABASE = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
_SESSION_TABLES = ("session_v2", "session")


class LocalOpencodeSessionResolver(OpencodeSessionResolver):
    """Resolves exact local OpenCode session ID using preferred association methods."""

    def __init__(self, database_path: Path | None = None) -> None:
        self._database_path = (database_path or _DEFAULT_OPENCODE_DATABASE).expanduser().resolve()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True, timeout=1)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _available_session_tables(connection: sqlite3.Connection) -> tuple[str, ...]:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('session_v2', 'session')
            """
        ).fetchall()
        available = {str(row["name"]) for row in rows}
        return tuple(table for table in _SESSION_TABLES if table in available)

    @classmethod
    def _session_ids(cls, connection: sqlite3.Connection, directory: str) -> set[str]:
        session_ids: set[str] = set()
        for table in cls._available_session_tables(connection):
            rows = connection.execute(
                f"""
                SELECT id
                FROM {table}
                WHERE directory = ? AND time_archived IS NULL
                """,
                (directory,),
            ).fetchall()
            session_ids.update(str(row["id"]) for row in rows)
        return session_ids

    @classmethod
    def _session_exists(cls, connection: sqlite3.Connection, session_id: str) -> bool:
        for table in cls._available_session_tables(connection):
            row = connection.execute(
                f"SELECT id FROM {table} WHERE id = ? LIMIT 1", (session_id,)
            ).fetchone()
            if row is not None:
                return True
        return False

    def snapshot_sessions(self, *, directory: Path) -> set[str]:
        """Read all currently unarchived v2 or legacy sessions for a directory."""
        if not self._database_path.is_file():
            return set()
        try:
            with self._connect() as connection:
                return self._session_ids(connection, str(directory.resolve()))
        except sqlite3.Error:
            return set()

    def resolve(
        self,
        *,
        directory: Path,
        explicit_session_id: str | None = None,
        snapshot_ids: set[str] | None = None,
        start_timestamp_ms: int | None = None,
    ) -> SessionResolutionResult:
        """Resolve the exact OpenCode session ID in preferred order:

        1. Direct OpenCode-provided session ID (CLI arg)
        2. Process-correlated session ID (if available)
        3. New-session delta (snapshot before/after)
        4. Timestamp/activity correlation

        Fails closed on ambiguity or when no candidate is uniquely proven.
        """
        canonical_dir = str(directory.resolve())

        # Method 1: Direct OpenCode-provided session ID
        if explicit_session_id is not None and explicit_session_id.strip():
            session_id = explicit_session_id.strip()
            if self._database_path.is_file():
                try:
                    with self._connect() as connection:
                        if not self._session_exists(connection, session_id):
                            return SessionResolutionResult(
                                session_id=None,
                                method=None,
                                candidates=(),
                                error=(
                                    f"The requested OpenCode session '{session_id}' does not exist."
                                ),
                            )
                        return SessionResolutionResult(
                            session_id=session_id,
                            method=SessionAssociationMethod.DIRECT_ARGUMENT,
                            candidates=(session_id,),
                        )
                except sqlite3.Error as error:
                    return SessionResolutionResult(
                        session_id=None,
                        method=None,
                        candidates=(),
                        error=f"Database error checking session '{session_id}': {error}",
                    )
            return SessionResolutionResult(
                session_id=session_id,
                method=SessionAssociationMethod.DIRECT_ARGUMENT,
                candidates=(session_id,),
            )

        if not self._database_path.is_file():
            return SessionResolutionResult(
                session_id=None,
                method=None,
                candidates=(),
                error=f"OpenCode database not found at {self._database_path}.",
            )

        try:
            with self._connect() as connection:
                # Method 3: New-session delta
                if snapshot_ids is not None:
                    current_ids = self._session_ids(connection, canonical_dir)
                    delta_ids = current_ids - snapshot_ids
                    if len(delta_ids) == 1:
                        resolved_id = next(iter(delta_ids))
                        return SessionResolutionResult(
                            session_id=resolved_id,
                            method=SessionAssociationMethod.NEW_SESSION_DELTA,
                            candidates=(resolved_id,),
                        )
                    if len(delta_ids) > 1:
                        candidates = tuple(sorted(delta_ids))
                        return SessionResolutionResult(
                            session_id=None,
                            method=None,
                            candidates=candidates,
                            error=(
                                f"Multiple new OpenCode sessions detected for {canonical_dir} "
                                f"({len(candidates)} candidates); "
                                "ambiguity prevents safe association."
                            ),
                        )

                # Method 4: Timestamp/activity correlation
                if start_timestamp_ms is not None:
                    cutoff = max(0, start_timestamp_ms - 2000)
                    candidates_by_id: dict[str, int] = {}
                    for table in self._available_session_tables(connection):
                        try:
                            rows = connection.execute(
                                f"""
                                SELECT id, time_updated
                                FROM {table}
                                WHERE directory = ?
                                  AND time_archived IS NULL
                                  AND time_updated >= ?
                                """,
                                (canonical_dir, cutoff),
                            ).fetchall()
                        except sqlite3.Error:
                            continue
                        for row in rows:
                            session_id = str(row["id"])
                            updated = int(row["time_updated"])
                            candidates_by_id[session_id] = max(
                                updated, candidates_by_id.get(session_id, 0)
                            )
                    candidates = tuple(
                        session_id
                        for session_id, _ in sorted(
                            candidates_by_id.items(), key=lambda item: (-item[1], item[0])
                        )
                    )
                    if len(candidates) == 1:
                        return SessionResolutionResult(
                            session_id=candidates[0],
                            method=SessionAssociationMethod.TIMESTAMP_CORRELATION,
                            candidates=candidates,
                        )
                    if len(candidates) > 1:
                        return SessionResolutionResult(
                            session_id=None,
                            method=None,
                            candidates=candidates,
                            error=(
                                f"Multiple active OpenCode sessions updated for {canonical_dir} "
                                f"({len(candidates)} candidates); "
                                "ambiguity prevents safe association."
                            ),
                        )

                return SessionResolutionResult(
                    session_id=None,
                    method=None,
                    candidates=(),
                    error=f"No new or updated OpenCode session found for {canonical_dir}.",
                )
        except sqlite3.Error as error:
            return SessionResolutionResult(
                session_id=None,
                method=None,
                candidates=(),
                error=f"OpenCode database query error: {error}",
            )
