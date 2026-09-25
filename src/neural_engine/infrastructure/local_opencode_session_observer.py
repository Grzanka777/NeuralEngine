"""Read-only OpenCode SQLite observation adapter.

OpenCode 1.x persists the latest completed response in ``part`` as
``tokens.total``. OpenCode 2.x uses ``session_message`` and stores the same
components under ``tokens``. Both values are useful evidence of recent context
pressure, but neither is a live prompt counter: tool output or new input can
arrive after that response. The adapter therefore always marks the value as an
estimate.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from neural_engine.application.opencode_context_pressure import PRODUCTION_CONTEXT_LIMIT
from neural_engine.domain.opencode_context import ContextSourceQuality, OpencodeContextObservation

_DEFAULT_DATABASE_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
_SESSION_TABLES = ("session_v2", "session")
_SOURCE_DESCRIPTION = "OpenCode SQLite latest completed response token total"


class LocalOpencodeSessionObserver:
    """Select only an explicit or single local session and read scalar metadata."""

    def __init__(
        self,
        database_path: Path = _DEFAULT_DATABASE_PATH,
        *,
        context_limit: int = PRODUCTION_CONTEXT_LIMIT,
        process_is_running: Callable[[], bool] | None = None,
    ) -> None:
        self._database_path = database_path
        self._context_limit = context_limit
        self._process_is_running = process_is_running or self._has_live_opencode_process

    def observe(self, *, session_id: str | None, directory: Path) -> OpencodeContextObservation:
        if not self._process_is_running():
            return self._unavailable(
                "No live OpenCode process is available for session observation."
            )
        if not self._database_path.is_file():
            return self._unavailable("OpenCode local session database is unavailable.")

        try:
            with self._connect() as connection:
                selected_session_id, uncertainty = self._select_session(
                    connection, session_id=session_id, directory=directory.resolve()
                )
                if selected_session_id is None:
                    return self._unavailable(uncertainty)
                current_tokens = self._latest_total_tokens(connection, selected_session_id)
        except sqlite3.Error:
            return self._unavailable("OpenCode local session metadata could not be read safely.")

        if current_tokens is None:
            return OpencodeContextObservation(
                session_id=selected_session_id,
                current_tokens=None,
                context_limit=self._context_limit,
                source_quality=ContextSourceQuality.UNKNOWN,
                source_description=_SOURCE_DESCRIPTION,
                uncertainty="The selected session has no usable completed-response token total.",
            )
        return OpencodeContextObservation(
            session_id=selected_session_id,
            current_tokens=current_tokens,
            context_limit=self._context_limit,
            source_quality=ContextSourceQuality.ESTIMATED,
            source_description=_SOURCE_DESCRIPTION,
            uncertainty=(
                "This is the latest completed-response total, not a live active-prompt count."
            ),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True, timeout=1)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _available_tables(
        connection: sqlite3.Connection, table_names: tuple[str, ...]
    ) -> tuple[str, ...]:
        placeholders = ", ".join("?" for _ in table_names)
        rows = connection.execute(
            f"""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name IN ({placeholders})
            """,
            table_names,
        ).fetchall()
        available = {str(row["name"]) for row in rows}
        return tuple(table for table in table_names if table in available)

    def _select_session(
        self, connection: sqlite3.Connection, *, session_id: str | None, directory: Path
    ) -> tuple[str | None, str]:
        if session_id is not None:
            for table in self._available_tables(connection, _SESSION_TABLES):
                row = connection.execute(
                    f"SELECT id FROM {table} WHERE id = ? LIMIT 1", (session_id,)
                ).fetchone()
                if row is not None:
                    return str(row["id"]), ""
            return None, "The requested OpenCode session does not exist."

        session_ids: set[str] = set()
        for table in self._available_tables(connection, _SESSION_TABLES):
            rows = connection.execute(
                f"""
                SELECT id
                FROM {table}
                WHERE directory = ? AND time_archived IS NULL
                """,
                (str(directory),),
            ).fetchall()
            session_ids.update(str(row["id"]) for row in rows)
        if not session_ids:
            return None, "No unarchived OpenCode session matches the current directory."
        if len(session_ids) != 1:
            return None, (
                "Multiple OpenCode sessions match the current directory; "
                "use --session to select one."
            )
        return next(iter(session_ids)), ""

    @classmethod
    def _latest_total_tokens(cls, connection: sqlite3.Connection, session_id: str) -> int | None:
        token_candidates: list[tuple[int, int]] = []

        if "session_message" in cls._available_tables(connection, ("session_message",)):
            row = connection.execute(
                """
                SELECT
                    COALESCE(json_extract(data, '$.tokens.input'), 0)
                    + COALESCE(json_extract(data, '$.tokens.output'), 0)
                    + COALESCE(json_extract(data, '$.tokens.reasoning'), 0)
                    + COALESCE(json_extract(data, '$.tokens.cache.read'), 0)
                    + COALESCE(json_extract(data, '$.tokens.cache.write'), 0)
                    AS total_tokens,
                    time_updated
                FROM session_message
                WHERE session_id = ?
                  AND type = 'assistant'
                  AND json_type(data, '$.time.completed') IN ('integer', 'real')
                  AND json_type(data, '$.tokens.input') IN ('integer', 'real')
                ORDER BY time_updated DESC, id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is not None:
                value = row["total_tokens"]
                if isinstance(value, (int, float)) and value >= 0:
                    token_candidates.append((int(row["time_updated"]), int(value)))

        if "part" in cls._available_tables(connection, ("part",)):
            row = connection.execute(
                """
                SELECT json_extract(data, '$.tokens.total') AS total_tokens, time_updated
                FROM part
                WHERE session_id = ?
                  AND json_type(data, '$.tokens.total') = 'integer'
                ORDER BY time_updated DESC, id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is not None:
                value = row["total_tokens"]
                if isinstance(value, int) and value >= 0:
                    token_candidates.append((int(row["time_updated"]), value))

        if not token_candidates:
            return None
        _, total_tokens = max(token_candidates)
        return total_tokens

    def _unavailable(self, uncertainty: str) -> OpencodeContextObservation:
        return OpencodeContextObservation(
            session_id=None,
            current_tokens=None,
            context_limit=self._context_limit,
            source_quality=ContextSourceQuality.UNKNOWN,
            source_description=_SOURCE_DESCRIPTION,
            uncertainty=uncertainty,
        )

    @staticmethod
    def _has_live_opencode_process() -> bool:
        """Inspect Linux process names without controlling any process."""

        try:
            entries = tuple(Path("/proc").iterdir())
        except OSError:
            return False
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            try:
                if (entry / "comm").read_text(encoding="utf-8").strip() == "opencode":
                    return True
            except OSError:
                continue
        return False
