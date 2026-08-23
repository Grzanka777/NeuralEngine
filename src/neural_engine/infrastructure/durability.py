"""Small POSIX-local filesystem durability primitives.

These helpers deliberately operate on exact bytes only. Serialization,
validation, identity checks, and repository-level idempotency remain outside
this module.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import BinaryIO


def fsync_directory(path: Path) -> None:
    """Flush directory-entry metadata for one existing directory."""

    directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_replace_bytes(path: Path, data: bytes) -> None:
    """Publish exact bytes by replacing ``path`` atomically.

    The temporary file is created beside the target, fully written and
    fsynced before ``os.replace``. The containing directory is then fsynced.
    An error after replacement is propagated without attempting a rollback.
    """

    _require_bytes(data)
    temporary_path, temporary_fd = _create_temporary_file(path)
    operation_error: BaseException | None = None

    try:
        _write_and_fsync(temporary_fd, data)
        os.replace(temporary_path, path)
        fsync_directory(path.parent)
    except BaseException as error:
        operation_error = error
        raise
    finally:
        _cleanup_temporary_file(temporary_path, operation_error)


def create_once_bytes(path: Path, data: bytes) -> None:
    """Publish exact bytes only when ``path`` does not already exist.

    ``os.link`` atomically claims the absent target without replacing an
    existing file. A successful claim is followed by a containing-directory
    fsync. ``FileExistsError`` is intentionally left visible to the caller;
    semantic idempotency belongs to the repository layer.
    """

    _require_bytes(data)
    temporary_path, temporary_fd = _create_temporary_file(path)
    operation_error: BaseException | None = None
    cleanup_attempted = False

    try:
        _write_and_fsync(temporary_fd, data)
        os.link(temporary_path, path)
        fsync_directory(path.parent)
        cleanup_attempted = True
        _cleanup_temporary_file(temporary_path, None)
        fsync_directory(path.parent)
    except BaseException as error:
        operation_error = error
        raise
    finally:
        if not cleanup_attempted:
            _cleanup_temporary_file(temporary_path, operation_error)


def _require_bytes(data: bytes) -> None:
    if not isinstance(data, bytes):
        raise TypeError("Durability primitives accept bytes only.")


def _create_temporary_file(path: Path) -> tuple[Path, int]:
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    return Path(temporary_name), file_descriptor


def _write_and_fsync(file_descriptor: int, data: bytes) -> None:
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            file_descriptor = -1
            _write_complete(temporary_file, data)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
    finally:
        if file_descriptor != -1:
            os.close(file_descriptor)


def _write_complete(temporary_file: BinaryIO, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = temporary_file.write(data[offset:])
        if written <= 0:
            raise OSError("Temporary file write made no progress.")
        offset += written


def _cleanup_temporary_file(
    temporary_path: Path,
    operation_error: BaseException | None,
) -> None:
    try:
        os.unlink(temporary_path)
    except FileNotFoundError:
        return
    except BaseException as cleanup_error:
        if operation_error is None:
            raise
        operation_error.add_note(f"Temporary file cleanup failed: {cleanup_error!r}")
