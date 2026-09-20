"""Tests for exact OpenCode session resolution and ambiguity handling."""

import sqlite3
import time
from pathlib import Path

from neural_engine.domain.opencode_context import (
    SessionAssociationMethod,
)
from neural_engine.infrastructure.local_opencode_session_resolver import (
    LocalOpencodeSessionResolver,
)


def create_test_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE session (
                id TEXT PRIMARY KEY,
                directory TEXT NOT NULL,
                time_created INTEGER NOT NULL,
                time_updated INTEGER NOT NULL,
                time_archived INTEGER
            );
            """
        )


def create_v2_test_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE session_v2 (
                id TEXT PRIMARY KEY,
                directory TEXT NOT NULL,
                time_created INTEGER NOT NULL,
                time_updated INTEGER NOT NULL,
                time_archived INTEGER
            );
            """
        )


def insert_session(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    directory: Path,
    time_created: int = 1000,
    time_updated: int = 1000,
    time_archived: int | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO session (id, directory, time_created, time_updated, time_archived)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, str(directory.resolve()), time_created, time_updated, time_archived),
    )


def insert_v2_session(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    directory: Path,
    time_created: int = 1000,
    time_updated: int = 1000,
    time_archived: int | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO session_v2 (id, directory, time_created, time_updated, time_archived)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, str(directory.resolve()), time_created, time_updated, time_archived),
    )


def test_snapshot_sessions_returns_unarchived_ids_only(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_test_database(db_path)
    target_dir = tmp_path / "my_project"
    target_dir.mkdir()
    other_dir = tmp_path / "other_project"
    other_dir.mkdir()

    with sqlite3.connect(db_path) as connection:
        insert_session(connection, session_id="ses_active_1", directory=target_dir)
        insert_session(connection, session_id="ses_active_2", directory=target_dir)
        insert_session(
            connection, session_id="ses_archived", directory=target_dir, time_archived=2000
        )
        insert_session(connection, session_id="ses_other_dir", directory=other_dir)

    resolver = LocalOpencodeSessionResolver(db_path)
    snapshot = resolver.snapshot_sessions(directory=target_dir)

    assert snapshot == {"ses_active_1", "ses_active_2"}


def test_resolve_direct_explicit_session_when_valid(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with sqlite3.connect(db_path) as connection:
        insert_session(connection, session_id="ses_explicit_1", directory=project_dir)

    resolver = LocalOpencodeSessionResolver(db_path)
    result = resolver.resolve(directory=project_dir, explicit_session_id="ses_explicit_1")

    assert result.session_id == "ses_explicit_1"
    assert result.method is SessionAssociationMethod.DIRECT_ARGUMENT
    assert result.candidates == ("ses_explicit_1",)
    assert result.error is None


def test_resolve_direct_explicit_session_when_not_found(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    resolver = LocalOpencodeSessionResolver(db_path)
    result = resolver.resolve(directory=project_dir, explicit_session_id="ses_does_not_exist")

    assert result.session_id is None
    assert result.method is None
    assert result.candidates == ()
    assert result.error is not None
    assert "does not exist" in result.error


def test_resolve_new_session_delta_single_new_session(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with sqlite3.connect(db_path) as connection:
        insert_session(connection, session_id="ses_old", directory=project_dir)

    resolver = LocalOpencodeSessionResolver(db_path)
    snapshot = resolver.snapshot_sessions(directory=project_dir)
    assert snapshot == {"ses_old"}

    # Simulate OpenCode starting and creating a new session
    with sqlite3.connect(db_path) as connection:
        insert_session(connection, session_id="ses_new_123", directory=project_dir)

    result = resolver.resolve(directory=project_dir, snapshot_ids=snapshot)

    assert result.session_id == "ses_new_123"
    assert result.method is SessionAssociationMethod.NEW_SESSION_DELTA
    assert result.candidates == ("ses_new_123",)
    assert result.error is None


def test_v2_session_table_is_used_for_snapshot_and_new_session_delta(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_v2_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with sqlite3.connect(db_path) as connection:
        insert_v2_session(connection, session_id="ses_v2_old", directory=project_dir)

    resolver = LocalOpencodeSessionResolver(db_path)
    snapshot = resolver.snapshot_sessions(directory=project_dir)
    assert snapshot == {"ses_v2_old"}

    with sqlite3.connect(db_path) as connection:
        insert_v2_session(connection, session_id="ses_v2_new", directory=project_dir)

    result = resolver.resolve(directory=project_dir, snapshot_ids=snapshot)

    assert result.session_id == "ses_v2_new"
    assert result.method is SessionAssociationMethod.NEW_SESSION_DELTA
    assert result.candidates == ("ses_v2_new",)
    assert result.error is None


def test_v2_session_table_supports_direct_session_resolution(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_v2_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with sqlite3.connect(db_path) as connection:
        insert_v2_session(connection, session_id="ses_v2_explicit", directory=project_dir)

    result = LocalOpencodeSessionResolver(db_path).resolve(
        directory=project_dir, explicit_session_id="ses_v2_explicit"
    )

    assert result.session_id == "ses_v2_explicit"
    assert result.method is SessionAssociationMethod.DIRECT_ARGUMENT


def test_resolve_multiple_old_sessions_safely_ignored(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with sqlite3.connect(db_path) as connection:
        for i in range(25):
            insert_session(connection, session_id=f"ses_old_{i:02d}", directory=project_dir)

    resolver = LocalOpencodeSessionResolver(db_path)
    snapshot = resolver.snapshot_sessions(directory=project_dir)
    assert len(snapshot) == 25

    # Simulate OpenCode starting and creating exactly one new session
    with sqlite3.connect(db_path) as connection:
        insert_session(connection, session_id="ses_brand_new", directory=project_dir)

    result = resolver.resolve(directory=project_dir, snapshot_ids=snapshot)

    assert result.session_id == "ses_brand_new"
    assert result.method is SessionAssociationMethod.NEW_SESSION_DELTA
    assert result.candidates == ("ses_brand_new",)
    assert result.error is None


def test_resolve_ambiguous_new_sessions_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with sqlite3.connect(db_path) as connection:
        insert_session(connection, session_id="ses_initial", directory=project_dir)

    resolver = LocalOpencodeSessionResolver(db_path)
    snapshot = resolver.snapshot_sessions(directory=project_dir)

    # Simulate two new sessions appearing concurrently
    with sqlite3.connect(db_path) as connection:
        insert_session(connection, session_id="ses_candidate_A", directory=project_dir)
        insert_session(connection, session_id="ses_candidate_B", directory=project_dir)

    result = resolver.resolve(directory=project_dir, snapshot_ids=snapshot)

    assert result.session_id is None
    assert result.method is None
    assert result.candidates == ("ses_candidate_A", "ses_candidate_B")
    assert result.error is not None
    assert "ambiguity" in result.error.lower()


def test_resolve_resumed_session_by_timestamp_correlation(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    now_ms = int(time.time() * 1000)
    with sqlite3.connect(db_path) as connection:
        insert_session(
            connection,
            session_id="ses_idle",
            directory=project_dir,
            time_created=now_ms - 100_000,
            time_updated=now_ms - 100_000,
        )
        insert_session(
            connection,
            session_id="ses_resumed",
            directory=project_dir,
            time_created=now_ms - 50_000,
            time_updated=now_ms + 1000,  # updated after launch
        )

    resolver = LocalOpencodeSessionResolver(db_path)
    # Delta returns 0 new sessions because both existed in snapshot
    snapshot = {"ses_idle", "ses_resumed"}

    result = resolver.resolve(
        directory=project_dir, snapshot_ids=snapshot, start_timestamp_ms=now_ms
    )

    assert result.session_id == "ses_resumed"
    assert result.method is SessionAssociationMethod.TIMESTAMP_CORRELATION
    assert result.candidates == ("ses_resumed",)
    assert result.error is None


def test_resolve_ambiguous_resumed_sessions_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    now_ms = int(time.time() * 1000)
    with sqlite3.connect(db_path) as connection:
        insert_session(
            connection,
            session_id="ses_resumed_1",
            directory=project_dir,
            time_created=now_ms - 50_000,
            time_updated=now_ms + 1000,
        )
        insert_session(
            connection,
            session_id="ses_resumed_2",
            directory=project_dir,
            time_created=now_ms - 50_000,
            time_updated=now_ms + 2000,
        )

    resolver = LocalOpencodeSessionResolver(db_path)
    snapshot = {"ses_resumed_1", "ses_resumed_2"}

    result = resolver.resolve(
        directory=project_dir, snapshot_ids=snapshot, start_timestamp_ms=now_ms
    )

    assert result.session_id is None
    assert result.method is None
    assert len(result.candidates) == 2
    assert result.error is not None
    assert "ambiguity" in result.error.lower()


def test_resolve_no_candidates_returns_error(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    create_test_database(db_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with sqlite3.connect(db_path) as connection:
        insert_session(
            connection,
            session_id="ses_dormant",
            directory=project_dir,
            time_created=1000,
            time_updated=1000,
        )

    resolver = LocalOpencodeSessionResolver(db_path)
    snapshot = {"ses_dormant"}

    result = resolver.resolve(
        directory=project_dir, snapshot_ids=snapshot, start_timestamp_ms=50_000
    )

    assert result.session_id is None
    assert result.method is None
    assert result.candidates == ()
    assert result.error is not None
    assert "No new or updated" in result.error
