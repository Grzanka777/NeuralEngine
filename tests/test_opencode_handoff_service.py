from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

import neural_engine.cli as cli
from neural_engine.application.opencode_handoff_service import (
    HandoffSessionObservation,
    OpencodeHandoffError,
    OpencodeHandoffRequest,
    OpencodeHandoffService,
)
from neural_engine.domain.opencode_context import ContextSourceQuality
from neural_engine.ports.opencode_handoff_repository import HandoffRepositoryCheckpoint


class FakeRepository:
    def __init__(self) -> None:
        self.checkpoint = HandoffRepositoryCheckpoint(
            root=Path("/work/NeuralEngine"),
            branch="main",
            head="a" * 40,
            worktree_entries=2,
        )
        self.available_files = {"src/neural_engine/cli.py", "tests/test_cli.py"}
        self.inspected_roots: list[Path] = []
        self.resolved_values: list[str] = []

    def inspect(self, requested_root: Path) -> HandoffRepositoryCheckpoint:
        self.inspected_roots.append(requested_root)
        return self.checkpoint

    def resolve_file(self, checkpoint: HandoffRepositoryCheckpoint, value: str) -> str:
        self.resolved_values.append(value)
        if value not in self.available_files:
            raise AssertionError(f"Unexpected fixture file: {value}")
        return value


def make_service(repository: FakeRepository | None = None) -> OpencodeHandoffService:
    return OpencodeHandoffService(
        repository or FakeRepository(),
        clock=lambda: datetime(2026, 9, 14, 14, 30, tzinfo=UTC),
    )


def make_request(**changes: object) -> OpencodeHandoffRequest:
    values: dict[str, object] = {
        "repository_root": Path("/work/NeuralEngine"),
        "task_goal": "Create a manual verified handoff.",
        "next_action": "Review this checkpoint before starting a fresh session.",
        "verified_decisions": ("Use a manual handoff, not native compaction.",),
        "files": ("src/neural_engine/cli.py",),
        "modules": ("neural_engine.cli",),
        "validated_evidence": ("V2 public compact returns HTTP 503 in OpenCode 1.18.29.",),
        "uncertainty": ("Automatic compaction remains unsafe for unattended use.",),
        "do_not_do": ("Do not change OpenCode provider configuration.",),
    }
    values.update(changes)
    return OpencodeHandoffRequest(**values)  # type: ignore[arg-type]


def test_handoff_renders_sections_in_deterministic_order() -> None:
    output = make_service().render(make_request())

    headings = (
        "## TASK GOAL",
        "## VERIFIED DECISIONS",
        "## CURRENT WORKING SET",
        "## VALIDATED EVIDENCE",
        "## OPEN BLOCKERS / UNCERTAINTY",
        "## NEXT ACTION",
        "## DO NOT DO",
        "## CHECKPOINT",
    )
    assert [output.index(heading) for heading in headings] == sorted(
        output.index(heading) for heading in headings
    )
    assert "- branch: main" in output
    assert "- worktree: dirty (2 entry(s); details omitted)" in output
    assert "- generated_at: 2026-09-14T14:30:00+00:00" in output


def test_handoff_omits_empty_optional_working_set_lists() -> None:
    output = make_service().render(
        make_request(
            verified_decisions=(),
            files=(),
            modules=(),
            validated_evidence=(),
            uncertainty=(),
        )
    )

    assert "- relevant files:" not in output
    assert "- relevant modules:" not in output
    assert "No verified decisions were supplied." in output
    assert "No validated evidence was supplied." in output
    assert "No uncertainty was supplied; do not assume missing facts are settled." in output


def test_handoff_places_only_explicit_uncertainty_in_uncertainty_section() -> None:
    output = make_service().render(
        make_request(
            verified_decisions=(),
            validated_evidence=(),
            uncertainty=("Confirm the next OpenCode release behavior.",),
        )
    )

    uncertainty_section = output.split("## OPEN BLOCKERS / UNCERTAINTY", 1)[1].split(
        "## NEXT ACTION", 1
    )[0]
    decisions_section = output.split("## VERIFIED DECISIONS", 1)[1].split(
        "## CURRENT WORKING SET", 1
    )[0]
    assert "Confirm the next OpenCode release behavior." in uncertainty_section
    assert "Confirm the next OpenCode release behavior." not in decisions_section


def test_handoff_deduplicates_repeated_facts_and_files() -> None:
    output = make_service().render(
        make_request(
            verified_decisions=("Manual handoff is required.", "manual handoff is required."),
            files=("src/neural_engine/cli.py", "src/neural_engine/cli.py"),
            validated_evidence=("Ruff passed.", "ruff passed."),
        )
    )

    assert output.count("Manual handoff is required.") == 1
    assert output.count("src/neural_engine/cli.py") == 1
    assert output.casefold().count("ruff passed.") == 1


def test_handoff_rejects_oversized_raw_log_without_echoing_it() -> None:
    raw_log = "x" * 501

    with pytest.raises(OpencodeHandoffError) as error:
        make_service().render(make_request(validated_evidence=(raw_log,)))

    assert "raw logs" in str(error.value)
    assert raw_log not in str(error.value)


def test_handoff_representative_fixture_stays_within_compact_budget() -> None:
    output = make_service().render(make_request())

    assert len(output) < 7_000
    assert output.endswith("\n")


def test_handoff_renders_only_supplied_session_observation() -> None:
    output = make_service().render(
        make_request(
            session_observation=HandoffSessionObservation(
                session_id="ses_fixture",
                current_tokens=25_240,
                context_limit=32_768,
                source_quality=ContextSourceQuality.ESTIMATED,
                source_description="OpenCode SQLite latest completed response tokens.total",
            )
        )
    )

    assert "## OPENCODE SESSION OBSERVATION" in output
    assert "- session: ses_fixture" in output
    assert "- context: ~25240 / 32768" in output


class RenderingService:
    def __init__(self) -> None:
        self.request: OpencodeHandoffRequest | None = None

    def render(self, request: OpencodeHandoffRequest) -> str:
        self.request = request
        return (
            "# OPENCODE FRESH-SESSION HANDOFF\n\n## TASK GOAL\n- fixture\n"
            "- source_scope: "
            "explicit CLI task/session input; live Git metadata; caller-selected files\n"
        )


class HandoffContainer:
    def __init__(self, service: RenderingService) -> None:
        self.service = service

    def opencode_handoff_service(self) -> RenderingService:
        return self.service


def test_handoff_cli_writes_checkpoint_to_stdout_without_brain_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RenderingService()
    unavailable_home = tmp_path / "unavailable-neural-home"
    monkeypatch.setenv("NEURAL_HOME", str(unavailable_home))
    monkeypatch.setattr(cli, "container", HandoffContainer(service))

    result = CliRunner().invoke(
        cli.app,
        [
            "handoff",
            "opencode",
            "--task-goal",
            "fixture task",
            "--next-action",
            "review fixture",
            "--repository-root",
            str(tmp_path),
            "--verified-decision",
            "manual only",
            "--uncertainty",
            "verify output",
        ],
    )

    assert result.exit_code == 0
    assert result.output == (
        "# OPENCODE FRESH-SESSION HANDOFF\n\n## TASK GOAL\n- fixture\n"
        "- source_scope: explicit CLI task/session input; live Git metadata; "
        "caller-selected files\n"
    )
    assert service.request is not None
    assert service.request.task_goal == "fixture task"
    assert service.request.verified_decisions == ("manual only",)
    assert service.request.uncertainty == ("verify output",)
    assert not unavailable_home.exists()
