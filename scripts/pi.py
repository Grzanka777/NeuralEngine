#!/usr/bin/env python3
"""Launch Pi with NeuralEngine resources from any directory in this checkout."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT_ENV = "NEURALENGINE_PI_PROJECT_ROOT"
UPSTREAM_PI = ".local/bin/pi.upstream"
PI_SUBCOMMANDS = frozenset({"auth", "config", "install", "list", "remove", "uninstall", "update"})
PROJECT_DEFAULTS = (
    ("defaultProvider", "--provider"),
    ("defaultModel", "--model"),
    ("defaultThinkingLevel", "--thinking"),
)


def resolve_project_root(script_file: str | Path = __file__) -> Path:
    return Path(script_file).resolve(strict=True).parent.parent.resolve(strict=True)


def is_inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _has_option(arguments: Sequence[str], option: str) -> bool:
    for argument in arguments:
        if argument == "--":
            return False
        if argument == option or argument.startswith(f"{option}="):
            return True
        if argument == "-e" and option == "--extension":
            return True
    return False


def _has_extension_path(arguments: Sequence[str], extension: Path, cwd: Path) -> bool:
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            break
        value: str | None = None
        if argument in ("--extension", "-e") and index + 1 < len(arguments):
            index += 1
            value = arguments[index]
        elif argument.startswith("--extension="):
            value = argument.partition("=")[2]
        if value:
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = cwd / candidate
            try:
                resolved = candidate.resolve(strict=True)
                if resolved == extension or (resolved.is_dir() and is_inside(resolved, extension)):
                    return True
            except OSError:
                pass
        index += 1
    return False


def _is_pi_subcommand(arguments: Sequence[str]) -> bool:
    return bool(arguments and arguments[0] in PI_SUBCOMMANDS)


def project_arguments(project_root: Path, cwd: Path, arguments: Sequence[str]) -> list[str]:
    """Add canonical project resources only when Pi cannot discover them itself."""
    root = project_root.resolve(strict=True)
    current = cwd.resolve(strict=True)
    if not is_inside(root, current) or current == root or _is_pi_subcommand(arguments):
        return list(arguments)

    project_dir = root / ".pi"
    settings_path = project_dir / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot load canonical Pi project settings: {error}") from error
    if not isinstance(settings, dict):
        raise RuntimeError("canonical Pi project settings must be a JSON object")
    supported_keys = {key for key, _ in PROJECT_DEFAULTS}
    unsupported = sorted(set(settings) - supported_keys)
    if unsupported:
        raise RuntimeError(
            "Pi's CLI has no project-settings override for: " + ", ".join(unsupported)
        )

    extension = (project_dir / "extensions" / "neuralengine-guard.ts").resolve(strict=True)
    skills = project_dir / "skills"
    prompts = project_dir / "prompts"
    if not skills.is_dir() or not prompts.is_dir():
        raise RuntimeError("canonical Pi skills or prompt directory is missing")

    explicit: list[str] = []
    if not _has_extension_path(arguments, extension, current):
        explicit.extend(("--extension", str(extension)))
    explicit.extend(("--skill", str(skills.resolve(strict=True))))
    explicit.extend(("--prompt-template", str(prompts.resolve(strict=True))))

    for key, option in PROJECT_DEFAULTS:
        value = settings.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise RuntimeError(f"canonical Pi setting {key} must be a non-empty string")
        if value is not None and not _has_option(arguments, option):
            explicit.extend((option, value))

    return [*explicit, *arguments]


def main(arguments: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    root = resolve_project_root()
    cwd = Path.cwd().resolve(strict=True)
    env = os.environ.copy()

    if is_inside(root, cwd):
        env[PROJECT_ROOT_ENV] = str(root)
        try:
            arguments = project_arguments(root, cwd, arguments)
        except RuntimeError as error:
            print(f"pi: {error}", file=sys.stderr)
            return 2
    else:
        env.pop(PROJECT_ROOT_ENV, None)

    executable = (Path.home() / UPSTREAM_PI).resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        print(f"pi: upstream Pi executable is unavailable: {executable}", file=sys.stderr)
        return 127
    os.execve(executable, [str(executable), *arguments], env)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
