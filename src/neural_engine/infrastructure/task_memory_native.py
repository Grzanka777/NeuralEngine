"""Run one native CLI task and translate process settlement into task memory."""

import json
import os
import shutil
import signal
import subprocess
from contextlib import suppress
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryFile
from types import FrameType
from uuid import UUID

from neural_engine.application.task_memory_service import NativeClientTrust, TaskMemoryError
from neural_engine.infrastructure.task_memory_runtime import Completion, NativeEngine

_MAX_OUTPUT = 4 * 1024 * 1024


def verify_trusted_native(engine: NativeEngine, trust: NativeClientTrust) -> None:
    name = "codex" if engine.engine == "codex" else "agy"
    selected = shutil.which(name)
    path = Path(trust.executable)
    if (
        trust.engine != engine.engine
        or trust.model != engine.requested_model
        or selected is None
        or not path.is_absolute()
        or Path(selected).resolve(strict=True) != path
        or not path.is_file()
    ):
        raise TaskMemoryError("NATIVE_CLIENT_IDENTITY_MISMATCH")
    with path.open("rb") as program:
        if file_digest(program, "sha256").hexdigest() != trust.sha256:
            raise TaskMemoryError("NATIVE_CLIENT_IDENTITY_MISMATCH")
    overrides = (
        ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL")
        if engine.engine == "codex"
        else ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_BASE_URL", "AGY_ADC_AUTH")
    )
    if any(os.environ.get(name) for name in overrides):
        raise TaskMemoryError("NATIVE_ROUTE_OVERRIDE")
    if engine.engine == "antigravity":
        gemini = Path.home() / ".gemini"
        settings = gemini / "antigravity-cli/settings.json"
        configuration = gemini / "config/config.json"
        if (
            settings.exists()
            and json.loads(settings.read_bytes()).get("modelProvider") not in {None, ""}
        ) or (
            configuration.exists()
            and json.loads(configuration.read_bytes()).get("userSettings", {}).get("enableAdc")
        ):
            raise TaskMemoryError("NATIVE_ROUTE_OVERRIDE")


def _command(engine: NativeEngine, workspace: Path, trust: NativeClientTrust | None) -> list[str]:
    model = f"--model={engine.requested_model}"
    if engine.engine == "codex":
        return [
            trust.executable if trust else "codex",
            "--ask-for-approval",
            "never",
            "exec",
            *(
                [
                    "--ignore-user-config",
                    "-c",
                    'model_provider="openai"',
                    "-c",
                    'forced_login_method="chatgpt"',
                    "--disable",
                    "hooks",
                ]
                if trust
                else []
            ),
            "--ephemeral",
            "--json",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(workspace),
            model,
            "-",
        ]
    return [
        trust.executable if trust else "agy",
        "--sandbox",
        "--disable-slash-commands",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        model,
    ]


def _settlement(engine: NativeEngine, workspace: Path, raw: bytes) -> tuple[UUID | None, bool, str]:
    if engine.engine == "antigravity":
        conversation = None
        result = None
        for line in raw.splitlines():
            event = json.loads(line)
            match event["event"]:
                case "init":
                    if conversation is not None or Path(event["init"]["cwd"]) != workspace:
                        raise ValueError("Invalid native workspace")
                    conversation = UUID(event["conversation_id"])
                case "result":
                    if conversation is None or result is not None:
                        raise ValueError("Duplicate or misplaced native result")
                    result = event["result"]
        if not result or UUID(result["conversation_id"]) != conversation:
            return conversation, False, ""
        reply = result["response"]
        return conversation, result["status"] == "SUCCESS", reply if isinstance(reply, str) else ""

    session = None
    terminal = None
    reply = ""
    for line in raw.splitlines():
        event = json.loads(line)
        match event["type"]:
            case "thread.started":
                if session is not None or terminal is not None:
                    raise ValueError("Duplicate or misplaced thread.started")
                session = UUID(event["thread_id"])
            case "turn.completed" | "turn.failed":
                if session is None or terminal is not None:
                    raise ValueError("Duplicate or misplaced turn settlement")
                terminal = event["type"]
            case "item.completed":
                item = event["item"]
                if item["type"] == "agent_message" and isinstance(item["text"], str):
                    reply = item["text"]
    return session, terminal == "turn.completed", reply


def run_native(
    engine: NativeEngine,
    workspace: Path,
    task: str,
    brain_home: str,
    receipts: Path,
    trust: NativeClientTrust | None = None,
) -> tuple[Completion, UUID | None, str]:
    # Hide the selected Brain and operator receipts from subprocesses, including tool calls.
    # Keep the normal client configuration/authentication paths for the native CLI.
    selected = Path(brain_home)
    if (
        not selected.is_absolute()
        or selected.resolve(strict=True) != selected
        or not selected.is_dir()
    ):
        raise TaskMemoryError("NATIVE_BRAIN_HOME_INVALID")
    protected = {selected, receipts, Path.home() / ".neural"}
    if inherited := os.environ.get("NEURAL_HOME"):
        protected.add(Path(inherited))
    masks: list[str] = []
    for path in sorted({path.resolve() for path in protected}):
        if path.is_relative_to(workspace) or workspace.is_relative_to(path):
            raise TaskMemoryError("NATIVE_PROTECTED_PATH_OVERLAP")
        if path.is_dir():
            masks.extend(("--tmpfs", str(path)))

    command = [
        "bwrap",
        "--die-with-parent",
        "--unshare-pid",
        "--bind",
        "/",
        "/",
        # Bind / exposes the host device nodes, but a capability-free child cannot open
        # them, so stdio-null (os.devnull, Stdio::null) fails with EACCES. A private
        # devtmpfs restores /dev/null without exposing host devices.
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        *masks,
        "--chdir",
        str(workspace),
        "--",
        *_command(engine, workspace, trust),
    ]
    environment = os.environ.copy()
    environment.pop("NEURAL_HOME", None)
    environment.pop("NEURAL_TASK_MEMORY_POLICY", None)
    native_input = task.encode()
    if engine.engine == "antigravity":
        native_input = (json.dumps({"event": "user", "message": {"content": task}}) + "\n").encode()
    with TemporaryFile() as output:
        try:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=output,
                start_new_session=True,
            )
        except OSError:
            return "failed", None, ""
        interrupted = False

        def interrupt(signum: int, frame: FrameType | None) -> None:
            nonlocal interrupted
            interrupted = True
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            signal.alarm(5)

        def force_stop(signum: int, frame: FrameType | None) -> None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)

        signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        handlers = {kind: signal.signal(kind, interrupt) for kind in signals}
        handlers[signal.SIGALRM] = signal.signal(signal.SIGALRM, force_stop)
        try:
            process.communicate(native_input)
        finally:
            signal.alarm(0)
            for kind, previous in handlers.items():
                signal.signal(kind, previous)
        output.seek(0)
        raw = output.read(_MAX_OUTPUT + 1)
    session, completed, reply = None, False, ""
    if len(raw) <= _MAX_OUTPUT:
        with suppress(ValueError, KeyError, TypeError, AttributeError):
            session, completed, reply = _settlement(engine, workspace, raw)
    if interrupted or process.returncode in {-signal.SIGTERM, -signal.SIGINT, 130, 143}:
        return "interrupted", session, ""
    if process.returncode != 0 or not completed or session is None:
        return "failed", session, ""
    return "completed", session, reply
