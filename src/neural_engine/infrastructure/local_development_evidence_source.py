from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from neural_engine.ports.development_evidence_source import (
    DevelopmentEvidenceSnapshot,
    ValidationClaim,
)

_FULL_SHA = re.compile(r"[0-9a-f]{40}")
_DIFF_PATH = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE)
_HEADING = re.compile(r"^## (.+)$", re.MULTILINE)
_TEST_COUNT = re.compile(r"(?m)(\d+) passed(?: in|\s*$)")


class LocalDevelopmentEvidenceSourceError(Exception):
    """Base failure while reading local development evidence."""


class InvalidDevelopmentEvidenceError(LocalDevelopmentEvidenceSourceError):
    """The caller supplied an invalid repository path, file path, or SHA."""


class MissingDevelopmentEvidenceError(LocalDevelopmentEvidenceSourceError):
    """An explicitly named source artifact does not exist."""


class UnsupportedDevelopmentEvidenceTopologyError(LocalDevelopmentEvidenceSourceError):
    """The source bundle is outside the deliberately narrow v1 topology."""


class InsufficientDevelopmentEvidenceError(LocalDevelopmentEvidenceSourceError):
    """A required conservative Markdown fact could not be established."""


class LocalDevelopmentEvidenceSource:
    """Read bounded facts from one local NeuralEngine Git repository."""

    repository_identity = "NeuralEngine"

    def read(
        self,
        *,
        repository_root: str,
        prompt_path: str,
        review_path: str,
        commit_sha: str,
    ) -> DevelopmentEvidenceSnapshot:
        root = self._repository_root(repository_root)
        prompt_relative, prompt_bytes = self._read_relative_file(root, prompt_path, "prompt")
        review_relative, review_bytes = self._read_relative_file(root, review_path, "review")
        self._require_distinct_files(prompt_relative, review_relative)
        self._require_full_sha(commit_sha)

        prompt_text = self._decode(prompt_bytes, "prompt")
        review_text = self._decode(review_bytes, "review")
        prompt_checkpoint = self._prompt_checkpoint(prompt_text)
        review_checkpoint = self._review_checkpoint(review_text)
        review_patch = self._fenced_block(review_text, "diff")
        review_paths = self._inventory_paths(review_text)
        validation_claims = self._validation_claims(review_text)

        resolved_commit = self._git(root, "rev-parse", "--verify", f"{commit_sha}^{{commit}}")
        if resolved_commit != commit_sha:
            raise InvalidDevelopmentEvidenceError(
                "Commit must be one exact lowercase full SHA, not an abbreviation or alias."
            )
        parents = self._git(root, "show", "-s", "--format=%P", commit_sha).split()
        if len(parents) != 1:
            raise UnsupportedDevelopmentEvidenceTopologyError(
                "Development evidence v1 requires exactly one non-merge commit."
            )
        parent = parents[0]
        subject = self._git(root, "show", "-s", "--format=%s", commit_sha)
        tree = self._git(root, "show", "-s", "--format=%T", commit_sha)
        commit_paths = tuple(
            self._git(
                root,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                commit_sha,
            ).splitlines()
        )
        commit_patch = self._git_bytes(root, "diff", parent, commit_sha, "--")

        return DevelopmentEvidenceSnapshot(
            repository_identity=self.repository_identity,
            repository_root=str(root),
            prompt_path=prompt_relative,
            prompt_sha256=self._sha256(prompt_bytes),
            prompt_starting_checkpoint=prompt_checkpoint,
            review_path=review_relative,
            review_sha256=self._sha256(review_bytes),
            review_starting_checkpoint=review_checkpoint,
            review_outcome=self._review_outcome(review_text),
            review_changed_paths=review_paths,
            review_patch_sha256=self._sha256(review_patch),
            validation_claims=validation_claims,
            validation_tree_attested=self._validation_tree_attestation(review_text),
            risks_deviations_blockers=self._risks(review_text),
            commit_sha=commit_sha,
            commit_parent_sha=parent,
            commit_subject=subject,
            commit_tree_sha=tree,
            commit_changed_paths=commit_paths,
            commit_patch_sha256=self._sha256(commit_patch),
            patch_matches=review_patch == commit_patch,
        )

    def _repository_root(self, value: str) -> Path:
        root = Path(value).expanduser().resolve()
        if not root.is_dir():
            raise MissingDevelopmentEvidenceError(f"Repository root does not exist: {root}")
        if root.name != self.repository_identity:
            raise UnsupportedDevelopmentEvidenceTopologyError(
                "Development evidence v1 supports only the NeuralEngine repository."
            )
        try:
            git_root = Path(self._git(root, "rev-parse", "--show-toplevel")).resolve()
        except InvalidDevelopmentEvidenceError as error:
            raise InvalidDevelopmentEvidenceError(
                f"Local Git repository is unavailable: {root}"
            ) from error
        if git_root != root:
            raise InvalidDevelopmentEvidenceError(
                "Selected repository root must be the NeuralEngine Git worktree root."
            )
        return root

    @staticmethod
    def _read_relative_file(root: Path, value: str, label: str) -> tuple[str, bytes]:
        supplied = Path(value)
        if supplied.is_absolute():
            raise InvalidDevelopmentEvidenceError(f"{label.title()} path must be repo-relative.")
        resolved = (root / supplied).resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as error:
            raise InvalidDevelopmentEvidenceError(
                f"{label.title()} path escapes the selected repository."
            ) from error
        if not resolved.is_file():
            raise MissingDevelopmentEvidenceError(
                f"Development evidence {label} does not exist: {relative.as_posix()}"
            )
        return relative.as_posix(), resolved.read_bytes()

    @staticmethod
    def _require_distinct_files(prompt_path: str, review_path: str) -> None:
        if prompt_path == review_path:
            raise UnsupportedDevelopmentEvidenceTopologyError(
                "Development evidence v1 requires one distinct prompt and one distinct review."
            )

    @staticmethod
    def _require_full_sha(value: str) -> None:
        if _FULL_SHA.fullmatch(value) is None:
            raise InvalidDevelopmentEvidenceError(
                "Commit must be one exact lowercase 40-character SHA."
            )

    @staticmethod
    def _decode(value: bytes, label: str) -> str:
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InvalidDevelopmentEvidenceError(
                f"Development evidence {label} must be UTF-8 Markdown."
            ) from error

    @staticmethod
    def _prompt_checkpoint(text: str) -> str:
        required = LocalDevelopmentEvidenceSource._section(text, "Required checkpoints")
        match = re.search(r"(?m)^checkpoint:\s*([0-9a-f]{40})\s*$", required)
        if match is None:
            raise InsufficientDevelopmentEvidenceError(
                "Prompt does not record one NeuralEngine starting checkpoint."
            )
        return match.group(1)

    @staticmethod
    def _review_checkpoint(text: str) -> str:
        starting = LocalDevelopmentEvidenceSource._section(text, "Exact starting checkpoints")
        match = re.search(r"(?m)^HEAD:\s*([0-9a-f]{40})\s*$", starting)
        if match is None:
            raise InsufficientDevelopmentEvidenceError(
                "Review does not record one NeuralEngine starting checkpoint."
            )
        return match.group(1)

    @staticmethod
    def _review_outcome(text: str) -> str | None:
        outcome = LocalDevelopmentEvidenceSource._section(text, "Outcome")
        match = re.search(r"`([^`\n]+)`", outcome)
        return match.group(1).strip() if match is not None else None

    @staticmethod
    def _inventory_paths(text: str) -> tuple[str, ...]:
        inventory = LocalDevelopmentEvidenceSource._section(text, "Changed-file inventory")
        block = LocalDevelopmentEvidenceSource._fenced_block(inventory, "text").decode()
        paths = tuple(
            line
            for line in block.splitlines()
            if line and not line[0].isspace() and not line.startswith(("$", "No "))
        )
        if not paths:
            raise InsufficientDevelopmentEvidenceError(
                "Review changed-file inventory contains no paths."
            )
        return paths

    @staticmethod
    def _validation_claims(text: str) -> tuple[ValidationClaim, ...]:
        claims: list[ValidationClaim] = []
        for match in re.finditer(r"(?ms)^\$ (.+?)\n(.*?)(?=^\$ |\Z)", text):
            command = match.group(1).strip()
            body = match.group(2)
            if not LocalDevelopmentEvidenceSource._is_validation_command(command):
                continue
            exit_matches = re.findall(r"(?m)^exit:\s*(-?\d+)\s*$", body)
            count_match = _TEST_COUNT.search(body)
            claims.append(
                ValidationClaim(
                    command=command,
                    exit_code=int(exit_matches[-1]) if exit_matches else None,
                    test_count=int(count_match.group(1)) if count_match is not None else None,
                )
            )
        return tuple(claims)

    @staticmethod
    def _is_validation_command(command: str) -> bool:
        return command.startswith(
            ("uv run ruff ", "uv run mypy ", "uv run pytest", "./scripts/validate.sh")
        )

    @staticmethod
    def _validation_tree_attestation(text: str) -> str | None:
        patterns = (
            r"validation(?:s| commands)? (?:ran|was run) (?:on|against) (?:the )?commit(?:ted)? "
            r"tree\s+([0-9a-f]{40})",
            r"validated commit(?:ted)? tree:\s*([0-9a-f]{40})",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match is not None:
                return match.group(1)
        return None

    @staticmethod
    def _risks(text: str) -> tuple[str, ...]:
        headings = [heading for heading in _HEADING.findall(text) if "risk" in heading.lower()]
        if not headings:
            return ()
        section = LocalDevelopmentEvidenceSource._section(text, headings[-1])
        lines = [
            line.strip()
            for line in section.splitlines()
            if line.strip() and not line.startswith(("```", "#")) and len(line.strip()) <= 1000
        ]
        return tuple(lines[:20])

    @staticmethod
    def _section(text: str, heading_name: str) -> str:
        pattern = re.compile(
            rf"(?ms)^## (?:\d+\.\s*)?{re.escape(heading_name)}\s*$\n(.*?)(?=^## |\Z)"
        )
        match = pattern.search(text)
        if match is None:
            raise InsufficientDevelopmentEvidenceError(
                f"Required review/prompt section is missing: {heading_name}"
            )
        return match.group(1)

    @staticmethod
    def _fenced_block(text: str, language: str) -> bytes:
        match = re.search(
            rf"(?ms)^```{re.escape(language)}\s*$\n(.*?)^```\s*$",
            text,
        )
        if match is None:
            raise InsufficientDevelopmentEvidenceError(
                f"Required fenced {language} block is missing."
            )
        return match.group(1).encode()

    @staticmethod
    def _sha256(value: bytes) -> str:
        return f"sha256:{hashlib.sha256(value).hexdigest()}"

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        return LocalDevelopmentEvidenceSource._git_bytes(root, *arguments).decode().rstrip("\n")

    @staticmethod
    def _git_bytes(root: Path, *arguments: str) -> bytes:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *arguments],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise InvalidDevelopmentEvidenceError(
                f"Local Git could not resolve requested evidence: {' '.join(arguments)}"
            ) from error
        return result.stdout
