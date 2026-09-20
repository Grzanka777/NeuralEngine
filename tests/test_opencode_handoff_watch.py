import json
import sqlite3
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

import neural_engine.cli as cli
from neural_engine.application.opencode_context_pressure import (
    CRITICAL_THRESHOLD,
    HANDOFF_THRESHOLD,
    NOTICE_THRESHOLD,
    assess_context_pressure,
)
from neural_engine.application.opencode_handoff_watch_service import (
    OpencodeHandoffWatchReport,
    OpencodeHandoffWatchService,
)
from neural_engine.domain.opencode_context import (
    ContextPressureLevel,
    ContextSourceQuality,
    OpencodeContextObservation,
)
from neural_engine.infrastructure.local_opencode_session_observer import (
    LocalOpencodeSessionObserver,
)


def observation(
    *,
    tokens: int | None,
    quality: ContextSourceQuality = ContextSourceQuality.EXACT,
    session_id: str | None = "ses_fixture",
    uncertainty: str | None = None,
) -> OpencodeContextObservation:
    return OpencodeContextObservation(
        session_id=session_id,
        current_tokens=tokens,
        context_limit=32_768,
        source_quality=quality,
        source_description="synthetic OpenCode fixture",
        uncertainty=uncertainty,
    )


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (NOTICE_THRESHOLD - 1, ContextPressureLevel.HEALTHY),
        (NOTICE_THRESHOLD, ContextPressureLevel.NOTICE),
        (HANDOFF_THRESHOLD, ContextPressureLevel.HANDOFF),
        (CRITICAL_THRESHOLD, ContextPressureLevel.CRITICAL),
    ],
)
def test_pressure_model_respects_threshold_boundaries(
    tokens: int, expected: ContextPressureLevel
) -> None:
    result = assess_context_pressure(tokens, source_quality=ContextSourceQuality.EXACT)

    assert result.level is expected


def test_pressure_model_calculates_exact_remaining_tokens() -> None:
    result = assess_context_pressure(25_240, source_quality=ContextSourceQuality.EXACT)

    assert result.remaining_tokens == 7_528
    assert result.ratio == pytest.approx(25_240 / 32_768)


def test_pressure_model_returns_unknown_for_unavailable_tokens() -> None:
    result = assess_context_pressure(None)

    assert result.level is ContextPressureLevel.UNKNOWN
    assert result.remaining_tokens is None


def test_estimated_high_value_does_not_claim_critical_pressure() -> None:
    result = assess_context_pressure(
        CRITICAL_THRESHOLD, source_quality=ContextSourceQuality.ESTIMATED
    )

    assert result.level is ContextPressureLevel.HANDOFF
    assert "cannot confirm critical" in result.recommendation


class FixedObserver:
    def __init__(self, value: OpencodeContextObservation) -> None:
        self.value = value
        self.calls: list[tuple[str | None, Path]] = []

    def observe(self, *, session_id: str | None, directory: Path) -> OpencodeContextObservation:
        self.calls.append((session_id, directory))
        return self.value


def test_watch_service_preserves_an_exact_observation() -> None:
    observer = FixedObserver(observation(tokens=25_240))

    report = OpencodeHandoffWatchService(observer).inspect(
        session_id="ses_fixture", directory=Path("/work")
    )

    assert report.observation.source_quality is ContextSourceQuality.EXACT
    assert report.pressure.level is ContextPressureLevel.HANDOFF
    assert observer.calls == [("ses_fixture", Path("/work"))]


def create_opencode_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE session (
                id TEXT PRIMARY KEY,
                directory TEXT NOT NULL,
                time_archived INTEGER
            );
            CREATE TABLE part (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                time_updated INTEGER NOT NULL,
                data TEXT NOT NULL
            );
            """
        )


def create_v2_opencode_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE session_v2 (
                id TEXT PRIMARY KEY,
                directory TEXT NOT NULL,
                time_archived INTEGER
            );
            CREATE TABLE session_message (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                time_updated INTEGER NOT NULL,
                data TEXT NOT NULL
            );
            """
        )


def add_session(connection: sqlite3.Connection, session_id: str, directory: Path) -> None:
    connection.execute(
        "INSERT INTO session (id, directory, time_archived) VALUES (?, ?, NULL)",
        (session_id, str(directory.resolve())),
    )


def add_token_part(connection: sqlite3.Connection, session_id: str, total: int) -> None:
    connection.execute(
        "INSERT INTO part (id, session_id, time_updated, data) VALUES (?, ?, ?, ?)",
        (f"part_{session_id}", session_id, 1, json.dumps({"tokens": {"total": total}})),
    )


def add_v2_session(connection: sqlite3.Connection, session_id: str, directory: Path) -> None:
    connection.execute(
        "INSERT INTO session_v2 (id, directory, time_archived) VALUES (?, ?, NULL)",
        (session_id, str(directory.resolve())),
    )


def add_v2_token_message(connection: sqlite3.Connection, session_id: str, total: int) -> None:
    connection.execute(
        """
        INSERT INTO session_message (id, session_id, type, time_updated, data)
        VALUES (?, ?, 'assistant', 2, ?)
        """,
        (
            f"message_{session_id}",
            session_id,
            json.dumps(
                {
                    "time": {"completed": 2},
                    "tokens": {"input": total, "output": 0, "reasoning": 0},
                }
            ),
        ),
    )


def test_local_observer_reads_latest_completed_response_as_estimate(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    directory = tmp_path / "project"
    directory.mkdir()
    create_opencode_database(database)
    with sqlite3.connect(database) as connection:
        add_session(connection, "ses_one", directory)
        add_token_part(connection, "ses_one", 25_580)
    database_before = database.read_bytes()

    result = LocalOpencodeSessionObserver(database, process_is_running=lambda: True).observe(
        session_id=None, directory=directory
    )

    assert result.session_id == "ses_one"
    assert result.current_tokens == 25_580
    assert result.source_quality is ContextSourceQuality.ESTIMATED
    assert result.uncertainty is not None
    assert "latest completed-response" in result.uncertainty
    assert database.read_bytes() == database_before


def test_local_observer_reads_v2_session_message_tokens(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    directory = tmp_path / "project"
    directory.mkdir()
    create_v2_opencode_database(database)
    with sqlite3.connect(database) as connection:
        add_v2_session(connection, "ses_v2", directory)
        add_v2_token_message(connection, "ses_v2", 25_580)

    result = LocalOpencodeSessionObserver(database, process_is_running=lambda: True).observe(
        session_id="ses_v2", directory=directory
    )

    assert result.session_id == "ses_v2"
    assert result.current_tokens == 25_580
    assert result.source_quality is ContextSourceQuality.ESTIMATED
    assert result.uncertainty is not None


def test_local_observer_reports_unavailable_source_without_database(tmp_path: Path) -> None:
    result = LocalOpencodeSessionObserver(
        tmp_path / "missing.db", process_is_running=lambda: True
    ).observe(session_id=None, directory=tmp_path)

    assert result.session_id is None
    assert result.current_tokens is None
    assert result.source_quality is ContextSourceQuality.UNKNOWN


def test_local_observer_fails_closed_when_current_directory_has_multiple_sessions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "opencode.db"
    directory = tmp_path / "project"
    directory.mkdir()
    create_opencode_database(database)
    with sqlite3.connect(database) as connection:
        add_session(connection, "ses_one", directory)
        add_session(connection, "ses_two", directory)

    result = LocalOpencodeSessionObserver(database, process_is_running=lambda: True).observe(
        session_id=None, directory=directory
    )

    assert result.session_id is None
    assert result.current_tokens is None
    assert result.source_quality is ContextSourceQuality.UNKNOWN
    assert result.uncertainty is not None
    assert "Multiple OpenCode sessions" in result.uncertainty


def test_local_observer_fails_closed_when_opencode_is_not_running(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    create_opencode_database(database)

    result = LocalOpencodeSessionObserver(database, process_is_running=lambda: False).observe(
        session_id="ses_one", directory=tmp_path
    )

    assert result.session_id is None
    assert result.current_tokens is None
    assert result.source_quality is ContextSourceQuality.UNKNOWN
    assert result.uncertainty == "No live OpenCode process is available for session observation."


class SequenceWatcher:
    def __init__(self, reports: list[OpencodeHandoffWatchReport]) -> None:
        self.reports = reports
        self.calls: list[tuple[str | None, Path]] = []

    def inspect(self, *, session_id: str | None, directory: Path) -> OpencodeHandoffWatchReport:
        self.calls.append((session_id, directory))
        return self.reports.pop(0) if len(self.reports) > 1 else self.reports[0]


class RecordingHandoffService:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def render(self, request: object) -> str:
        self.requests.append(request)
        return "# OPENCODE FRESH-SESSION HANDOFF\n"


class WatchContainer:
    def __init__(self, watcher: SequenceWatcher, handoff: RecordingHandoffService) -> None:
        self.watcher = watcher
        self.handoff = handoff

    def opencode_handoff_watch_service(self) -> SequenceWatcher:
        return self.watcher

    def opencode_handoff_service(self) -> RecordingHandoffService:
        return self.handoff


def report_for(
    tokens: int | None, quality: ContextSourceQuality = ContextSourceQuality.EXACT
) -> OpencodeHandoffWatchReport:
    value = observation(
        tokens=tokens,
        quality=quality,
        session_id="ses_fixture" if tokens is not None else None,
        uncertainty="synthetic uncertainty" if tokens is None else None,
    )
    return OpencodeHandoffWatchReport(
        observation=value,
        pressure=assess_context_pressure(
            value.current_tokens, value.context_limit, value.source_quality
        ),
    )


@pytest.mark.parametrize(
    ("tokens", "expected_exit"),
    [(18_420, 0), (25_580, 10), (30_100, 20), (None, 30)],
)
def test_watch_check_uses_documented_exit_codes(
    tokens: int | None,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watcher = SequenceWatcher([report_for(tokens)])
    handoff = RecordingHandoffService()
    monkeypatch.setattr(cli, "container", WatchContainer(watcher, handoff))

    result = CliRunner().invoke(cli.app, ["handoff", "watch", "--check"])

    assert result.exit_code == expected_exit
    assert "OPENCODE CONTEXT WATCH" in result.output
    assert not handoff.requests


def test_interactive_watch_defaults_to_no_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    watcher = SequenceWatcher([report_for(25_580)])
    handoff = RecordingHandoffService()
    monkeypatch.setattr(cli, "container", WatchContainer(watcher, handoff))

    result = CliRunner().invoke(cli.app, ["handoff", "watch"], input="\n")

    assert result.exit_code == 0
    assert "Generate handoff now? [y/N]" in result.output
    assert not handoff.requests


def test_interactive_yes_reuses_handoff_service(monkeypatch: pytest.MonkeyPatch) -> None:
    watcher = SequenceWatcher([report_for(25_580)])
    handoff = RecordingHandoffService()
    monkeypatch.setattr(cli, "container", WatchContainer(watcher, handoff))

    result = CliRunner().invoke(
        cli.app,
        ["handoff", "watch"],
        input="y\nImplement watcher\nReview the candidate checkpoint\n",
    )

    assert result.exit_code == 0
    assert len(handoff.requests) == 1
    assert "# OPENCODE FRESH-SESSION HANDOFF" in result.output


def test_interactive_watch_does_not_generate_below_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    watcher = SequenceWatcher([report_for(23_110)])
    handoff = RecordingHandoffService()
    monkeypatch.setattr(cli, "container", WatchContainer(watcher, handoff))

    result = CliRunner().invoke(cli.app, ["handoff", "watch"])

    assert result.exit_code == 0
    assert "Generate handoff now?" not in result.output
    assert not handoff.requests


def test_watch_check_does_not_initialize_or_write_brain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watcher = SequenceWatcher([report_for(18_420)])
    handoff = RecordingHandoffService()
    unavailable_home = tmp_path / "unavailable-neural-home"
    monkeypatch.setenv("NEURAL_HOME", str(unavailable_home))
    monkeypatch.setattr(cli, "container", WatchContainer(watcher, handoff))

    result = CliRunner().invoke(cli.app, ["handoff", "watch", "--check"])

    assert result.exit_code == 0
    assert not unavailable_home.exists()
    assert not handoff.requests


def test_follow_prints_only_pressure_transitions_and_stops_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watcher = SequenceWatcher([report_for(18_420), report_for(18_600), report_for(25_580)])
    handoff = RecordingHandoffService()
    monkeypatch.setattr(cli, "container", WatchContainer(watcher, handoff))
    sleep_calls = 0

    def stop_after_transition(_: int) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", stop_after_transition)

    result = CliRunner().invoke(cli.app, ["handoff", "watch", "--follow"])

    assert result.exit_code == 0
    assert result.output.count("OPENCODE CONTEXT WATCH") == 2
    assert not handoff.requests


def test_follow_rejects_an_interval_below_thirty_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    watcher = SequenceWatcher([report_for(18_420)])
    handoff = RecordingHandoffService()
    monkeypatch.setattr(cli, "container", WatchContainer(watcher, handoff))

    result = CliRunner().invoke(cli.app, ["handoff", "watch", "--follow", "--interval", "29"])

    assert result.exit_code == 2
    assert "at least 30 seconds" in result.output
    assert not watcher.calls
    assert not handoff.requests
