"""Offline synthetic tests for read-only, project-scoped Brain context assembly."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

import neural_engine.cli as cli
from neural_engine.application.brain_context_service import (
    BrainContextBudgetError,
    BrainContextFormat,
    BrainContextIntegrityError,
    BrainContextProjectKeyRequiredError,
    BrainContextService,
    BrainContextTopicError,
)
from neural_engine.application.container import Container
from neural_engine.core.brain import Brain
from neural_engine.core.paths import NeuralPaths, resolve_neural_paths
from neural_engine.domain import Decision, DecisionAcceptance, Knowledge, KnowledgeConfidence
from neural_engine.infrastructure.json_decision_acceptance_repository import (
    JsonDecisionAcceptanceRepository,
)
from neural_engine.infrastructure.json_decision_repository import JsonDecisionRepository
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_EXTENSION = REPO_ROOT / ".pi/extensions/neuralengine-guard.ts"
GUARD_PROBE = REPO_ROOT / "tests/pi_guard_probe.mjs"


def _synthetic_paths(tmp_path: Path) -> NeuralPaths:
    home = tmp_path / "neural-home"
    home.mkdir(parents=True)
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(home)})
    Brain(paths).initialize()
    return paths


def _service(paths: NeuralPaths) -> BrainContextService:
    return BrainContextService(
        JsonDecisionRepository(paths=paths),
        JsonDecisionAcceptanceRepository(paths=paths),
        JsonKnowledgeRepository(paths=paths),
    )


def _snapshot_brain(paths: NeuralPaths) -> dict[str, str]:
    return {
        str(path.relative_to(paths.BRAIN)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths.BRAIN.rglob("*"))
        if path.is_file()
    }


def _seed_decision(
    paths: NeuralPaths,
    *,
    project_key: str,
    title: str,
    proposed_option: str,
    rationale: str,
    key: str,
    accepted: bool = False,
    rejected: bool = False,
    supersedes_decision_id: UUID | None = None,
    created_at: datetime | None = None,
) -> Decision:
    tags = ("rejected",) if rejected else ()
    decision = Decision(
        created_at=created_at or datetime(2026, 2, 1, tzinfo=UTC),
        project_key=project_key,
        title=title,
        objective=f"Select {title} policy",
        context_summary="Synthetic adoption validation record",
        alternatives=(proposed_option, "other"),
        proposed_option=proposed_option,
        rationale=rationale,
        proposed_by="synthetic-author",
        supersedes_decision_id=supersedes_decision_id,
        idempotency_key=key,
        tags=tags,
    )
    JsonDecisionRepository(paths=paths).save(decision)
    if accepted:
        JsonDecisionAcceptanceRepository(paths=paths).save(
            DecisionAcceptance(
                accepted_at=decision.created_at + timedelta(minutes=1),
                decision_id=decision.id,
                accepted_by="synthetic-maintainer",
                reason="Approved in synthetic fixture",
                idempotency_key=f"accept-{key}",
            )
        )
    return decision


def _seed_knowledge(
    paths: NeuralPaths,
    *,
    statement: str,
    tags: list[str],
    confidence: KnowledgeConfidence = KnowledgeConfidence.MEDIUM,
    timestamp: datetime | None = None,
) -> Knowledge:
    knowledge = Knowledge(
        timestamp=timestamp or datetime(2026, 2, 1, tzinfo=UTC),
        statement=statement,
        rationale="Synthetic historical note",
        confidence=confidence,
        experience_ids=[uuid4()],
        tags=tags,
    )
    JsonKnowledgeRepository(paths=paths).save(knowledge)
    return knowledge


def test_scoped_context_isolation_and_decision_statuses(tmp_path: Path) -> None:
    paths = _synthetic_paths(tmp_path)
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)

    fir_accepted = _seed_decision(
        paths,
        project_key="fir",
        title="registry",
        proposed_option="regional",
        rationale="Fir uses regional registry only.",
        key="fir-1",
        accepted=True,
        created_at=t0,
    )
    _seed_decision(
        paths,
        project_key="spruce",
        title="registry",
        proposed_option="global",
        rationale="Spruce uses global registry.",
        key="spruce-1",
        accepted=True,
        created_at=t0,
    )
    _seed_decision(
        paths,
        project_key="fir",
        title="cache",
        proposed_option="shared-cache",
        rationale="Rejected shared cache due to payload leaks.",
        key="fir-2",
        rejected=True,
        created_at=t0 + timedelta(minutes=5),
    )
    _seed_decision(
        paths,
        project_key="fir",
        title="purge",
        proposed_option="purge-7d",
        rationale="Proposed seven-day purge without acceptance.",
        key="fir-3",
        accepted=False,
        created_at=t0 + timedelta(minutes=10),
    )
    fir_old = _seed_decision(
        paths,
        project_key="fir",
        title="cutover",
        proposed_option="drain",
        rationale="Old drain cutover.",
        key="fir-4",
        accepted=True,
        created_at=t0 + timedelta(minutes=15),
    )
    fir_new = _seed_decision(
        paths,
        project_key="fir",
        title="cutover",
        proposed_option="pause",
        rationale="Pause workers and verify offset.",
        key="fir-5",
        accepted=True,
        supersedes_decision_id=fir_old.id,
        created_at=t0 + timedelta(minutes=20),
    )
    fir_note = _seed_knowledge(
        paths,
        statement="Verify regional registry scope before release.",
        tags=["fir", "registry"],
        confidence=KnowledgeConfidence.HIGH,
    )
    _seed_knowledge(
        paths,
        statement="Spruce global endpoint note must not leak to Fir.",
        tags=["spruce", "registry"],
    )
    _seed_knowledge(
        paths,
        statement="Untagged note must not leak to Fir.",
        tags=["general"],
    )

    before = _snapshot_brain(paths)
    context, rendered = _service(paths).assemble_rendered("fir")
    after = _snapshot_brain(paths)

    assert before == after
    assert context.project == "fir"
    assert context.planner_enrichment is False
    assert context.truncated is False

    by_id = {item.id: item for item in context.decisions}
    assert len(by_id) == 5
    assert str(fir_accepted.id) in by_id
    assert by_id[str(fir_accepted.id)].status == "accepted"
    assert by_id[str(fir_new.id)].supersedes == str(fir_old.id)
    assert by_id[str(fir_old.id)].superseded_by == (str(fir_new.id),)

    statuses = {item.action: item.status for item in context.decisions}
    assert statuses == {
        "regional": "accepted",
        "shared-cache": "rejected",
        "purge-7d": "proposed",
        "drain": "accepted",
        "pause": "accepted",
    }

    assert [item.id for item in context.knowledge] == [str(fir_note.id)]
    parsed = json.loads(rendered)
    assert parsed["planner_enrichment"] is False
    assert "acceptance_id" not in rendered
    assert "accepted_by" not in rendered
    assert "Spruce" not in rendered
    assert "Untagged" not in rendered


def test_topic_filter_includes_supersession_chain_and_excludes_unrelated(tmp_path: Path) -> None:
    paths = _synthetic_paths(tmp_path)
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)

    old = _seed_decision(
        paths,
        project_key="elm",
        title="cutover",
        proposed_option="drain",
        rationale="Legacy drain method.",
        key="elm-1",
        accepted=True,
        created_at=t0,
    )
    new = _seed_decision(
        paths,
        project_key="elm",
        title="cutover",
        proposed_option="pause",
        rationale="Current pause method with verify-offset.",
        key="elm-2",
        accepted=True,
        supersedes_decision_id=old.id,
        created_at=t0 + timedelta(minutes=5),
    )
    _seed_decision(
        paths,
        project_key="elm",
        title="logging",
        proposed_option="json",
        rationale="Unrelated logging policy.",
        key="elm-3",
        accepted=True,
        created_at=t0 + timedelta(minutes=10),
    )

    context = _service(paths).assemble("elm", topic="drain")
    ids = [item.id for item in context.decisions]
    assert ids == [str(new.id), str(old.id)]
    assert context.decisions[0].superseded_by == ()
    assert context.decisions[1].superseded_by == (str(new.id),)


def test_bounded_context_size_and_single_oversized_record(tmp_path: Path) -> None:
    paths = _synthetic_paths(tmp_path)
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)

    for index in range(6):
        _seed_decision(
            paths,
            project_key="alder",
            title=f"topic-{index}",
            proposed_option=f"opt-{index}",
            rationale="x" * 220,
            key=f"alder-{index}",
            accepted=True,
            created_at=t0 + timedelta(minutes=index),
        )
    _seed_knowledge(
        paths,
        statement="y" * 200,
        tags=["alder"],
    )

    for fmt in (BrainContextFormat.JSON, BrainContextFormat.MARKDOWN):
        ctx, rendered = _service(paths).assemble_rendered("alder", max_bytes=700, output_format=fmt)
        assert len(rendered.encode("utf-8")) <= 700
        assert ctx.truncated is True
        assert ctx.omitted_decisions > 0
        assert ctx.omitted_knowledge == 1

    # Single oversized decision is omitted cleanly rather than clipped mid-record,
    # keeping incomplete authority explicit within the byte budget.
    single_paths = _synthetic_paths(tmp_path / "single")
    _seed_decision(
        single_paths,
        project_key="birch",
        title="oversized",
        proposed_option="pause",
        rationale="long-rationale " * 120,
        key="birch-1",
        accepted=True,
    )
    single_ctx, single_rendered = _service(single_paths).assemble_rendered(
        "birch", max_bytes=512, output_format=BrainContextFormat.JSON
    )
    assert len(single_rendered.encode("utf-8")) <= 512
    assert single_ctx.decisions == ()
    assert single_ctx.truncated is True
    assert single_ctx.omitted_decisions == 1
    assert any("incomplete" in w for w in single_ctx.warnings)


def test_atomic_packing_never_emits_accepted_without_superseding_or_rejected_peer(
    tmp_path: Path,
) -> None:
    paths = _synthetic_paths(tmp_path)
    t0 = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)

    # Group 1 (title="retry"): accepted decision + rejected peer on the same title.
    _seed_decision(
        paths,
        project_key="cedar",
        title="retry",
        proposed_option="pure",
        rationale="Accepted pure retry " + ("a" * 160),
        key="cedar-accepted",
        accepted=True,
        created_at=t0 + timedelta(minutes=10),
    )
    _seed_decision(
        paths,
        project_key="cedar",
        title="retry",
        proposed_option="shared-cache",
        rationale="Rejected shared cache " + ("b" * 160),
        key="cedar-rejected",
        rejected=True,
        created_at=t0,
    )

    # Budget fits one decision alone (~380B) but not the pair together -> omit group atomically.
    ctx, rendered = _service(paths).assemble_rendered("cedar", max_bytes=550)
    assert len(rendered.encode("utf-8")) <= 550
    assert ctx.decisions == ()
    assert ctx.truncated is True
    assert ctx.omitted_decisions == 2

    # Supersession chain across different titles is also atomic.
    sup_paths = _synthetic_paths(tmp_path / "supersession")
    old = _seed_decision(
        sup_paths,
        project_key="elm",
        title="legacy-cutover",
        proposed_option="drain",
        rationale="Historical accepted drain " + ("c" * 160),
        key="elm-old",
        accepted=True,
        created_at=t0,
    )
    _seed_decision(
        sup_paths,
        project_key="elm",
        title="release-5-cutover",
        proposed_option="pause",
        rationale="Proposed superseding pause " + ("d" * 160),
        key="elm-new",
        accepted=False,
        supersedes_decision_id=old.id,
        created_at=t0 + timedelta(minutes=5),
    )
    sup_ctx, sup_rendered = _service(sup_paths).assemble_rendered("elm", max_bytes=550)
    assert len(sup_rendered.encode("utf-8")) <= 550
    assert sup_ctx.decisions == ()
    assert sup_ctx.truncated is True
    assert sup_ctx.omitted_decisions == 2


def test_secret_guard_withholds_credential_like_content(tmp_path: Path) -> None:
    paths = _synthetic_paths(tmp_path)
    _seed_decision(
        paths,
        project_key="cedar",
        title="auth",
        proposed_option="env-var",
        rationale="Do not embed api_key=sk-secret-value-12345 in config.",
        key="cedar-1",
        accepted=False,
    )
    _seed_knowledge(
        paths,
        statement="Found token=ghp_supersecrettoken in old log.",
        tags=["cedar"],
    )

    ctx, rendered = _service(paths).assemble_rendered("cedar")
    assert "sk-secret-value-12345" not in rendered
    assert "ghp_supersecrettoken" not in rendered
    assert any("best-effort" in w for w in ctx.warnings)


def test_validation_errors_and_integrity_failures(tmp_path: Path) -> None:
    paths = _synthetic_paths(tmp_path)
    svc = _service(paths)

    with pytest.raises(BrainContextProjectKeyRequiredError):
        svc.assemble("   ")
    with pytest.raises(BrainContextTopicError):
        svc.assemble("fir", topic="   ")
    with pytest.raises(BrainContextBudgetError):
        svc.assemble("fir", max_bytes=256)
    with pytest.raises(BrainContextBudgetError):
        svc.assemble("fir", max_bytes=32768)

    # Cross-project supersession fails closed.
    other = _seed_decision(
        paths,
        project_key="spruce",
        title="registry",
        proposed_option="global",
        rationale="Spruce rule.",
        key="spruce-1",
        accepted=True,
    )
    _seed_decision(
        paths,
        project_key="fir",
        title="registry",
        proposed_option="regional",
        rationale="Invalid cross-project supersession.",
        key="fir-bad",
        supersedes_decision_id=other.id,
    )
    with pytest.raises(BrainContextIntegrityError):
        svc.assemble("fir")


def test_cli_context_command_and_pi_guard_read_only_compatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _synthetic_paths(tmp_path)
    _seed_decision(
        paths,
        project_key="hemlock",
        title="retention",
        proposed_option="purge",
        rationale="Proposed purge awaiting maintainer acceptance.",
        key="hemlock-1",
        accepted=False,
    )
    before = _snapshot_brain(paths)

    monkeypatch.setenv("NEURAL_HOME", str(paths.HOME))
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    monkeypatch.setattr(cli, "container", Container())

    runner = CliRunner()
    json_result = runner.invoke(cli.app, ["context", "--project", "hemlock"])
    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["project"] == "hemlock"
    assert payload["planner_enrichment"] is False
    assert payload["decisions"][0]["status"] == "proposed"

    md_result = runner.invoke(cli.app, ["context", "--project", "hemlock", "--format", "markdown"])
    assert md_result.exit_code == 0
    assert "# Scoped Brain Context" in md_result.stdout
    assert "[proposed]" in md_result.stdout
    assert before == _snapshot_brain(paths)

    # Verify Pi guard classifies `neural context` as non-mutating
    # while blocking `neural decision add`.
    probe = subprocess.run(
        [
            "node",
            str(GUARD_PROBE),
            str(GUARD_EXTENSION),
            json.dumps(
                [
                    "uv run neural context --project hemlock --topic retention",
                    "uv run neural decision add --project-key hemlock",
                ]
            ),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert probe.returncode == 0, probe.stderr
    classifications = json.loads(probe.stdout)
    assert classifications["uv run neural context --project hemlock --topic retention"] is None
    assert (
        classifications["uv run neural decision add --project-key hemlock"]
        == "NeuralEngine durable-state mutation requires separate explicit authorization"
    )
