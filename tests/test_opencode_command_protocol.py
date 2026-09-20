import re
import shutil
from pathlib import Path

from neural_engine.domain.opencode_compatibility import OpencodeCommandProtocolState
from neural_engine.infrastructure.local_opencode_command_protocol_probe import (
    LocalOpencodeCommandProtocolProbe,
)

COMMANDS = {
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


def _repository_root() -> Path:
    return Path(__file__).parents[1]


def test_adapter_preserves_canonical_semantics_and_unknown_commands() -> None:
    root = _repository_root()
    skill = (root / "integrations/opencode/command-protocol/SKILL.md").read_text(encoding="utf-8")
    bootstrap = (root / "integrations/opencode/command-protocol/bootstrap.md").read_text(
        encoding="utf-8"
    )

    assert "read-only by default" in skill and "TRIAGE" in skill
    assert "diagnosis, root cause, minimal safe change, and verification" in skill
    assert "CHECKPOINT` binds evidence to the exact state" in skill
    assert re.search(r"RECHECK.*only.*PROCEED.*REVISE.*STOP", skill, re.DOTALL)
    assert "never automatic execution" in skill
    assert "review → CHECKPOINT → RECHECK → explicit launch" in skill
    assert "`DESTROY` is a workflow phase" in skill
    assert "native `/agent` command" in skill
    assert "PROCEED" in bootstrap and "starts the next phase automatically" in bootstrap
    assert "commands/agent.md" not in {
        path.name for path in (root / "integrations/opencode/command-protocol/commands").iterdir()
    }
    assert not (root / "integrations/opencode/command-protocol/commands/agent.md").exists()


def test_all_native_adapters_preserve_arguments_without_routing() -> None:
    commands_root = _repository_root() / "integrations/opencode/command-protocol/commands"
    routing = re.compile(r"(?i)\b(?:model|provider|agent|subagent)\s*[:=]")
    arguments = "inspect --scope src --ticket CP-42"

    for name, target in COMMANDS.items():
        text = (commands_root / f"{name}.md").read_text(encoding="utf-8")
        assert target in text
        assert arguments in text.replace("$ARGUMENTS", arguments)
        assert not routing.search(text)


def test_probe_reports_healthy_repository_adapter_and_phase2a_warning() -> None:
    report = LocalOpencodeCommandProtocolProbe(repository_root=_repository_root()).inspect()
    states = {check.name: check.state for check in report.checks}

    assert states["Command Protocol bootstrap"] is OpencodeCommandProtocolState.PASS
    assert states["Command Protocol skill"] is OpencodeCommandProtocolState.PASS
    assert states["Command Protocol aliases"] is OpencodeCommandProtocolState.PASS
    assert states["Canonical/installed hash"] is OpencodeCommandProtocolState.WARN
    assert report.protocol_version == "1.2"
    assert report.workflow_version == "1.1"


def test_probe_detects_canonical_drift(tmp_path: Path) -> None:
    root = _repository_root()
    copy = tmp_path / "repository"
    (copy / "docs").mkdir(parents=True)
    (copy / "integrations" / "opencode").mkdir(parents=True)
    shutil.copytree(root / "docs" / "command-protocol", copy / "docs" / "command-protocol")
    shutil.copytree(
        root / "integrations" / "opencode" / "command-protocol",
        copy / "integrations" / "opencode" / "command-protocol",
    )
    canonical = copy / "docs" / "command-protocol" / "COMMAND_CORE_v1.2.md"
    canonical.write_text(canonical.read_text(encoding="utf-8") + "\nDRIFT\n", encoding="utf-8")

    report = LocalOpencodeCommandProtocolProbe(repository_root=copy).inspect()

    canonical_check = next(
        check for check in report.checks if check.name == "Canonical/installed hash"
    )
    assert canonical_check.state is OpencodeCommandProtocolState.FAIL
