from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ValidationClaim:
    """One validation command and only the result explicitly recorded beside it."""

    command: str
    exit_code: int | None
    test_count: int | None


@dataclass(frozen=True, slots=True)
class DevelopmentEvidenceSnapshot:
    """Replaceable source facts for one bounded local development bundle."""

    repository_identity: str
    repository_root: str
    prompt_path: str
    prompt_sha256: str
    prompt_starting_checkpoint: str
    review_path: str
    review_sha256: str
    review_starting_checkpoint: str
    review_outcome: str | None
    review_changed_paths: tuple[str, ...]
    review_patch_sha256: str
    validation_claims: tuple[ValidationClaim, ...]
    validation_tree_attested: str | None
    risks_deviations_blockers: tuple[str, ...]
    commit_sha: str
    commit_parent_sha: str
    commit_subject: str
    commit_tree_sha: str
    commit_changed_paths: tuple[str, ...]
    commit_patch_sha256: str
    patch_matches: bool


class DevelopmentEvidenceSource(Protocol):
    """Read one explicitly named repository-local prompt/review/commit bundle."""

    def read(
        self,
        *,
        repository_root: str,
        prompt_path: str,
        review_path: str,
        commit_sha: str,
    ) -> DevelopmentEvidenceSnapshot: ...
