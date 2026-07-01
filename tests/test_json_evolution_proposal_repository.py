from pathlib import Path
from uuid import UUID

from neural_engine.domain import EvolutionProposal
from neural_engine.infrastructure.json_evolution_proposal_repository import (
    JsonEvolutionProposalRepository,
)


def make_proposal(summary: str = "Persist proposal") -> EvolutionProposal:
    return EvolutionProposal(
        playbook_id=UUID("11111111-1111-1111-1111-111111111111"),
        evaluation_ids=[UUID("22222222-2222-2222-2222-222222222222")],
        summary=summary,
        rationale="Repository test rationale",
        proposed_changes=["Change one step"],
        expected_benefits=["Better manual outcome"],
    )


def test_save_writes_one_json_file_per_evolution_proposal(tmp_path: Path) -> None:
    repository = JsonEvolutionProposalRepository(tmp_path)
    proposal = make_proposal()

    repository.save(proposal)

    path = tmp_path / f"{proposal.id}.json"
    assert path.exists()
    assert EvolutionProposal.model_validate_json(path.read_text(encoding="utf-8")) == proposal


def test_load_all_returns_saved_proposals_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonEvolutionProposalRepository(tmp_path)
    first = make_proposal("First")
    second = make_proposal("Second")

    repository.save(second)
    repository.save(first)

    assert repository.load_all() == sorted([first, second], key=lambda item: str(item.id))


def test_load_all_returns_empty_list_when_directory_does_not_exist(tmp_path: Path) -> None:
    repository = JsonEvolutionProposalRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_get_by_id_returns_saved_proposal(tmp_path: Path) -> None:
    repository = JsonEvolutionProposalRepository(tmp_path)
    proposal = make_proposal("Load me")
    repository.save(proposal)

    assert repository.get_by_id(proposal.id) == proposal


def test_get_by_id_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    repository = JsonEvolutionProposalRepository(tmp_path)
    proposal = make_proposal("Missing")

    assert repository.get_by_id(proposal.id) is None
