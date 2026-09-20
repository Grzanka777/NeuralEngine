import hashlib
import json
import os
import re
from pathlib import Path

from neural_engine.domain.opencode_compatibility import (
    OpencodeCommandProtocolCheck,
    OpencodeCommandProtocolReport,
    OpencodeCommandProtocolState,
)

_PROTOCOL_VERSION = "1.2"
_WORKFLOW_VERSION = "1.1"
_CANONICAL_HASHES = {
    "COMMAND_CORE_v1.2.md": "8cb30c38cf0aa3d96848f1cab78cbe5a8ed5d6c7c7b426bb841f5cc9a864119b",
    "COMMAND_PROTOCOL_v1.2.md": "ebe2a2f26adc96b5f671a3174691f26bbd4e3abf3de7fc577010e208b5b81ee4",
    "ENGINEERING_WORKFLOW_v1.1.md": (
        "910c4ad8f990c48da90b2d554ef4c3b139b894fdc930b3d17678c94f81854f0e"
    ),
}
_ALIASES = {
    "seek": "//SEEK $ARGUMENTS",
    "fix": "//FIX $ARGUMENTS",
    "arch": "//ARCH $ARGUMENTS",
    "ship": "//SHIP $ARGUMENTS",
    "research": "//RESEARCH $ARGUMENTS",
    "optimize": "//OPTIMIZE $ARGUMENTS",
    "kill": "//KILL $ARGUMENTS",
    "checkpoint": "CHECKPOINT $ARGUMENTS",
    "recheck": "RECHECK $ARGUMENTS",
    "next": "NEXT $ARGUMENTS",
}
_INSTALL_MAP = {
    "bootstrap.md": "AGENTS.md",
    "SKILL.md": "skills/command-protocol/SKILL.md",
    **{f"commands/{name}.md": f"commands/{name}.md" for name in _ALIASES},
    **{f"docs/{name}": f"skills/command-protocol/references/{name}" for name in _CANONICAL_HASHES},
}


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError, UnicodeError:
        return None


def _check(
    name: str,
    state: OpencodeCommandProtocolState,
    detail: str,
) -> OpencodeCommandProtocolCheck:
    return OpencodeCommandProtocolCheck(name=name, state=state, detail=detail)


class LocalOpencodeCommandProtocolProbe:
    """Inspect repository adapter material without installing or repairing it."""

    def __init__(
        self,
        *,
        repository_root: Path | None = None,
        installed_root: Path | None = None,
    ) -> None:
        self._repository_root = repository_root or Path.cwd()
        configured_target = os.environ.get("NEURALENGINE_OPENCODE_PROTOCOL_TARGET")
        self._installed_root = installed_root or (
            Path(configured_target).expanduser() if configured_target else None
        )

    def inspect(self) -> OpencodeCommandProtocolReport:
        docs = self._repository_root / "docs" / "command-protocol"
        adapter = self._repository_root / "integrations" / "opencode" / "command-protocol"
        canonical = self._canonical_check(docs)
        bootstrap = self._bootstrap_check(adapter / "bootstrap.md")
        skill = self._skill_check(adapter / "SKILL.md")
        aliases = self._alias_check(adapter / "commands")
        return OpencodeCommandProtocolReport(
            checks=(bootstrap, skill, aliases, canonical),
            protocol_version=_PROTOCOL_VERSION,
            workflow_version=_WORKFLOW_VERSION,
        )

    def _canonical_check(self, docs: Path) -> OpencodeCommandProtocolCheck:
        for name, expected in _CANONICAL_HASHES.items():
            actual = _sha256(docs / name)
            if actual != expected:
                return _check(
                    "Canonical/installed hash",
                    OpencodeCommandProtocolState.FAIL,
                    f"{name}: expected {expected}, observed {actual or 'MISSING'}",
                )
        if self._installed_root is None:
            return _check(
                "Canonical/installed hash",
                OpencodeCommandProtocolState.WARN,
                "canonical hashes match; no Phase 2B installed target is configured",
            )
        state, detail = self._installed_status()
        return _check("Canonical/installed hash", state, detail)

    @staticmethod
    def _bootstrap_check(path: Path) -> OpencodeCommandProtocolCheck:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return _check(
                "Command Protocol bootstrap", OpencodeCommandProtocolState.FAIL, str(error)
            )
        required = ("//SEEK", "//FIX", "CHECKPOINT", "RECHECK", "AGENTS.md", "PROCEED")
        forbidden = re.compile(r"(?i)automatic(?:ally)?\s+(?:commit|push|delete|deploy)")
        if not all(token in text for token in required) or forbidden.search(text):
            return _check(
                "Command Protocol bootstrap",
                OpencodeCommandProtocolState.FAIL,
                "bootstrap contract markers are incomplete or unsafe",
            )
        return _check("Command Protocol bootstrap", OpencodeCommandProtocolState.PASS, str(path))

    @staticmethod
    def _skill_check(path: Path) -> OpencodeCommandProtocolCheck:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return _check("Command Protocol skill", OpencodeCommandProtocolState.FAIL, str(error))
        required = (
            "Command Protocol v1.2",
            "Command Core v1.2",
            "Engineering Workflow v1.1",
            "//SEEK",
            "TRIAGE",
            "CHECKPOINT",
            "PROCEED",
            "REVISE",
            "STOP",
            "DESTROY",
            "//AGENT",
            "references/",
        )
        routing = re.compile(r"(?i)\b(?:model|provider|subagent)\s*[:=]")
        if not all(token in text for token in required) or routing.search(text):
            return _check(
                "Command Protocol skill",
                OpencodeCommandProtocolState.FAIL,
                "skill contract markers are incomplete or contain routing fields",
            )
        return _check("Command Protocol skill", OpencodeCommandProtocolState.PASS, str(path))

    @staticmethod
    def _alias_check(commands: Path) -> OpencodeCommandProtocolCheck:
        missing: list[str] = []
        invalid: list[str] = []
        for name, target in _ALIASES.items():
            path = commands / f"{name}.md"
            try:
                text = path.read_text(encoding="utf-8")
            except OSError, UnicodeDecodeError:
                missing.append(name)
                continue
            if target not in text or re.search(
                r"(?i)\b(?:model|provider|agent|subagent)\s*[:=]", text
            ):
                invalid.append(name)
        if (commands / "agent.md").exists():
            invalid.append("agent (must not exist)")
        if missing or invalid:
            detail = f"missing={','.join(missing) or 'none'}; invalid={','.join(invalid) or 'none'}"
            return _check("Command Protocol aliases", OpencodeCommandProtocolState.FAIL, detail)
        return _check(
            "Command Protocol aliases",
            OpencodeCommandProtocolState.PASS,
            "ten argument-preserving native adapters verified",
        )

    def _installed_status(self) -> tuple[OpencodeCommandProtocolState, str]:
        assert self._installed_root is not None
        manifest = self._installed_root / "command-protocol.manifest.json"
        if manifest.is_symlink() or not manifest.is_file():
            return OpencodeCommandProtocolState.WARN, f"manifest is absent: {manifest}"
        try:
            value = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return OpencodeCommandProtocolState.FAIL, f"manifest could not be read: {error}"
        if not isinstance(value, dict):
            return OpencodeCommandProtocolState.FAIL, "manifest root is not an object"
        if value.get("protocol_version") != _PROTOCOL_VERSION:
            return OpencodeCommandProtocolState.FAIL, "installed protocol version mismatches v1.2"
        if value.get("workflow_version") != _WORKFLOW_VERSION:
            return OpencodeCommandProtocolState.FAIL, "installed workflow version mismatches v1.1"
        if value.get("canonical_source_hashes") != dict(sorted(_CANONICAL_HASHES.items())):
            return (
                OpencodeCommandProtocolState.FAIL,
                "installed canonical source identity mismatches",
            )
        hashes = value.get("installed_hashes")
        if not isinstance(hashes, dict):
            return OpencodeCommandProtocolState.FAIL, "installed hash manifest is missing"
        errors: list[str] = []
        expected_paths = set(_INSTALL_MAP.values())
        for relative in sorted(expected_paths):
            path = self._installed_root / relative
            recorded = hashes.get(relative)
            if path.is_symlink() or not path.is_file():
                errors.append(f"missing installed copy {relative}")
            elif not isinstance(recorded, str) or _sha256(path) != recorded:
                errors.append(f"hash mismatch {relative}")
        managed_skill_root = self._installed_root / "skills" / "command-protocol"
        if managed_skill_root.is_dir():
            for path in managed_skill_root.rglob("*"):
                relative = path.relative_to(self._installed_root).as_posix()
                if path.is_file() and relative not in expected_paths:
                    errors.append(f"unexpected installed copy {relative}")
        if (self._installed_root / "commands" / "agent.md").exists():
            errors.append("unexpected commands/agent.md")
        if errors:
            return OpencodeCommandProtocolState.FAIL, "; ".join(sorted(errors))
        return OpencodeCommandProtocolState.PASS, f"installed manifest verified: {manifest}"
