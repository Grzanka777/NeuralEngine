import subprocess
from pathlib import Path

import pytest

from neural_engine.infrastructure.local_development_evidence_source import (
    InsufficientDevelopmentEvidenceError,
    InvalidDevelopmentEvidenceError,
    LocalDevelopmentEvidenceSource,
    MissingDevelopmentEvidenceError,
    UnsupportedDevelopmentEvidenceTopologyError,
)

REAL_COMMIT = "49db077c00e67c1d3b5f25ec92b46c83518a30bb"
REAL_PARENT = "f5b1313921a286df698072ef86666b543afa32ab"
REAL_SUBJECT = "fix: enforce playbook revision create-once persistence"


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.rstrip("\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _bundle(root: Path) -> tuple[str, str, str, str]:
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _write(root / "tracked.txt", "before\n")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-qm", "initial")
    parent = _git(root, "rev-parse", "HEAD")
    _write(root / "tracked.txt", "after\n")
    _write(root / "added.txt", "added\n")
    _git(root, "add", "tracked.txt", "added.txt")
    _git(root, "commit", "-qm", "implement fixture")
    commit = _git(root, "rev-parse", "HEAD")
    prompt_path = ".agent-work/prompts/task.md"
    review_path = ".agent-work/reviews/review.md"
    _write(
        root / prompt_path,
        f"""# Task

## Required checkpoints

### NeuralEngine

```text
checkpoint: {parent}
```
""",
    )
    _write_review(root, review_path, parent, commit)
    return prompt_path, review_path, parent, commit


def _write_review(
    root: Path,
    review_path: str,
    parent: str,
    commit: str,
    *,
    exit_line: str = "exit: 0",
    inventory: tuple[str, ...] | None = None,
    patch: str | None = None,
) -> None:
    paths = inventory or tuple(
        _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines()
    )
    diff = patch if patch is not None else _git(root, "diff", parent, commit, "--") + "\n"
    _write(
        root / review_path,
        f"""# Review

## 1. Outcome

`completed`

## 3. Exact starting checkpoints

### NeuralEngine

```text
HEAD: {parent}
```

## 10. Changed-file inventory

```text
{chr(10).join(paths)}
```

## 11. Validation

```text
$ uv run pytest
1 passed in 0.01s
{exit_line}
```

## 17. Risks, deviations, and blockers

Blockers: none.

## 18. Complete relevant diff

```diff
{diff}```
""",
    )


def test_reads_consistent_local_bundle(tmp_path: Path) -> None:
    root = tmp_path / "NeuralEngine"
    prompt, review, parent, commit = _bundle(root)

    snapshot = LocalDevelopmentEvidenceSource().read(
        repository_root=str(root),
        prompt_path=prompt,
        review_path=review,
        commit_sha=commit,
    )

    assert snapshot.commit_parent_sha == parent
    assert snapshot.patch_matches is True
    assert set(snapshot.review_changed_paths) == set(snapshot.commit_changed_paths)
    assert snapshot.validation_claims[0].exit_code == 0
    assert snapshot.validation_claims[0].test_count == 1


def test_real_playbook_revision_commit_as_source_backed_fixture(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    root = tmp_path / "NeuralEngine"
    _git(source_root, "clone", "--quiet", "--no-hardlinks", str(source_root), str(root))
    prompt = ".agent-work/prompts/fixture.md"
    review = ".agent-work/reviews/fixture.md"
    _write(
        root / prompt,
        f"""# Real fixture

## Required checkpoints

checkpoint: {REAL_PARENT}
""",
    )
    _write_review(root, review, REAL_PARENT, REAL_COMMIT)

    snapshot = LocalDevelopmentEvidenceSource().read(
        repository_root=str(root),
        prompt_path=prompt,
        review_path=review,
        commit_sha=REAL_COMMIT,
    )

    assert snapshot.commit_parent_sha == REAL_PARENT
    assert snapshot.commit_subject == REAL_SUBJECT
    assert snapshot.patch_matches is True
    assert len(snapshot.commit_changed_paths) == 9


@pytest.mark.parametrize(
    ("prompt", "review", "message"),
    [
        ("../prompt.md", ".agent-work/reviews/review.md", "escapes"),
        (".agent-work/prompts/task.md", "../review.md", "escapes"),
        ("/tmp/prompt.md", ".agent-work/reviews/review.md", "repo-relative"),
    ],
)
def test_rejects_path_escape_or_absolute_path(
    tmp_path: Path, prompt: str, review: str, message: str
) -> None:
    root = tmp_path / "NeuralEngine"
    _, _, _, commit = _bundle(root)

    with pytest.raises(InvalidDevelopmentEvidenceError, match=message):
        LocalDevelopmentEvidenceSource().read(
            repository_root=str(root),
            prompt_path=prompt,
            review_path=review,
            commit_sha=commit,
        )


def test_rejects_wrong_repository(tmp_path: Path) -> None:
    root = tmp_path / "NeuralEngine-Handbook"
    root.mkdir()

    with pytest.raises(UnsupportedDevelopmentEvidenceTopologyError, match="only"):
        LocalDevelopmentEvidenceSource().read(
            repository_root=str(root),
            prompt_path="prompt.md",
            review_path="review.md",
            commit_sha="a" * 40,
        )


@pytest.mark.parametrize(("missing", "message"), [("prompt", "prompt"), ("review", "review")])
def test_missing_named_file_is_explicit(tmp_path: Path, missing: str, message: str) -> None:
    root = tmp_path / "NeuralEngine"
    prompt, review, _, commit = _bundle(root)
    (root / (prompt if missing == "prompt" else review)).unlink()

    with pytest.raises(MissingDevelopmentEvidenceError, match=message):
        LocalDevelopmentEvidenceSource().read(
            repository_root=str(root),
            prompt_path=prompt,
            review_path=review,
            commit_sha=commit,
        )


def test_missing_commit_is_explicit(tmp_path: Path) -> None:
    root = tmp_path / "NeuralEngine"
    prompt, review, _, _ = _bundle(root)

    with pytest.raises(InvalidDevelopmentEvidenceError, match="could not resolve"):
        LocalDevelopmentEvidenceSource().read(
            repository_root=str(root),
            prompt_path=prompt,
            review_path=review,
            commit_sha="a" * 40,
        )


def test_short_commit_is_invalid(tmp_path: Path) -> None:
    root = tmp_path / "NeuralEngine"
    prompt, review, _, commit = _bundle(root)

    with pytest.raises(InvalidDevelopmentEvidenceError, match="40-character"):
        LocalDevelopmentEvidenceSource().read(
            repository_root=str(root),
            prompt_path=prompt,
            review_path=review,
            commit_sha=commit[:12],
        )


def test_same_prompt_and_review_is_unsupported(tmp_path: Path) -> None:
    root = tmp_path / "NeuralEngine"
    prompt, _, _, commit = _bundle(root)

    with pytest.raises(UnsupportedDevelopmentEvidenceTopologyError, match="distinct"):
        LocalDevelopmentEvidenceSource().read(
            repository_root=str(root),
            prompt_path=prompt,
            review_path=prompt,
            commit_sha=commit,
        )


def test_missing_exit_code_remains_unknown(tmp_path: Path) -> None:
    root = tmp_path / "NeuralEngine"
    prompt, review, parent, commit = _bundle(root)
    _write_review(root, review, parent, commit, exit_line="recorded without an exit code")

    snapshot = LocalDevelopmentEvidenceSource().read(
        repository_root=str(root),
        prompt_path=prompt,
        review_path=review,
        commit_sha=commit,
    )

    assert snapshot.validation_claims[0].exit_code is None


def test_missing_required_review_section_is_insufficient(tmp_path: Path) -> None:
    root = tmp_path / "NeuralEngine"
    prompt, review, _, commit = _bundle(root)
    _write(root / review, "# Review without required sections\n")

    with pytest.raises(InsufficientDevelopmentEvidenceError, match="section"):
        LocalDevelopmentEvidenceSource().read(
            repository_root=str(root),
            prompt_path=prompt,
            review_path=review,
            commit_sha=commit,
        )


def test_merge_commit_is_unsupported(tmp_path: Path) -> None:
    root = tmp_path / "NeuralEngine"
    prompt, review, _, _ = _bundle(root)
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-qb", "feature")
    _write(root / "feature.txt", "feature\n")
    _git(root, "add", "feature.txt")
    _git(root, "commit", "-qm", "feature")
    _git(root, "checkout", "-q", "-")
    _write(root / "main.txt", "main\n")
    _git(root, "add", "main.txt")
    _git(root, "commit", "-qm", "main")
    _git(root, "merge", "--no-ff", "-qm", "merge", "feature")
    merge = _git(root, "rev-parse", "HEAD")
    assert base != merge

    with pytest.raises(UnsupportedDevelopmentEvidenceTopologyError, match="non-merge"):
        LocalDevelopmentEvidenceSource().read(
            repository_root=str(root),
            prompt_path=prompt,
            review_path=review,
            commit_sha=merge,
        )
