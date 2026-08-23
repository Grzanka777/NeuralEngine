from __future__ import annotations

import os
from pathlib import Path

import pytest

import neural_engine.infrastructure.durability as durability
from neural_engine.infrastructure.durability import (
    atomic_replace_bytes,
    create_once_bytes,
    fsync_directory,
)


def _temporary_files(directory: Path, target: Path) -> list[Path]:
    return sorted(directory.glob(f".{target.name}.*.tmp"))


def test_atomic_replace_publishes_exact_bytes_and_cleans_temp(tmp_path: Path) -> None:
    target = tmp_path / "record.bin"
    target.write_bytes(b"old\x00bytes")

    atomic_replace_bytes(target, b"new\xff\x00bytes")

    assert target.read_bytes() == b"new\xff\x00bytes"
    assert _temporary_files(tmp_path, target) == []


def test_create_once_publishes_exact_bytes_and_cleans_temp(tmp_path: Path) -> None:
    target = tmp_path / "record.bin"

    create_once_bytes(target, b"exact\x00\xffbytes")

    assert target.read_bytes() == b"exact\x00\xffbytes"
    assert _temporary_files(tmp_path, target) == []


def test_create_once_fsyncs_parent_before_and_after_temp_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.bin"
    original_fsync_directory = durability.fsync_directory
    observations: list[tuple[bool, int]] = []

    def recording_fsync_directory(directory: Path) -> None:
        observations.append((target.exists(), len(_temporary_files(tmp_path, target))))
        original_fsync_directory(directory)

    monkeypatch.setattr(durability, "fsync_directory", recording_fsync_directory)

    create_once_bytes(target, b"durable cleanup")

    assert observations == [(True, 1), (True, 0)]
    assert target.read_bytes() == b"durable cleanup"
    assert _temporary_files(tmp_path, target) == []


def test_create_once_second_directory_fsync_failure_keeps_published_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.bin"
    original_fsync_directory = durability.fsync_directory
    calls = 0

    def fail_second_fsync(directory: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("second directory fsync failed")
        original_fsync_directory(directory)

    monkeypatch.setattr(durability, "fsync_directory", fail_second_fsync)

    with pytest.raises(OSError, match="second directory fsync failed"):
        create_once_bytes(target, b"published before cleanup fsync")

    assert calls == 2
    assert target.read_bytes() == b"published before cleanup fsync"
    assert _temporary_files(tmp_path, target) == []


def test_fsync_directory_closes_descriptor_when_fsync_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = os.open
    original_close = os.close
    opened: list[int] = []
    closed: list[int] = []

    def recording_open(path: Path, flags: int) -> int:
        file_descriptor = original_open(path, flags)
        opened.append(file_descriptor)
        return file_descriptor

    def recording_close(file_descriptor: int) -> None:
        closed.append(file_descriptor)
        original_close(file_descriptor)

    def failing_fsync(file_descriptor: int) -> None:
        raise OSError("directory fsync failed")

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(os, "close", recording_close)
    monkeypatch.setattr(os, "fsync", failing_fsync)

    with pytest.raises(OSError, match="directory fsync failed"):
        fsync_directory(tmp_path)

    assert opened
    assert closed == opened


def test_atomic_replace_write_failure_preserves_target_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.bin"
    original_bytes = b"original"
    target.write_bytes(original_bytes)

    def failing_write(_temporary_file: object, _data: bytes) -> None:
        raise OSError("write failed")

    monkeypatch.setattr(durability, "_write_complete", failing_write)

    with pytest.raises(OSError, match="write failed"):
        atomic_replace_bytes(target, b"replacement")

    assert target.read_bytes() == original_bytes
    assert _temporary_files(tmp_path, target) == []


def test_atomic_replace_file_fsync_failure_preserves_target_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.bin"
    original_bytes = b"original"
    target.write_bytes(original_bytes)

    def failing_fsync(_file_descriptor: int) -> None:
        raise OSError("file fsync failed")

    monkeypatch.setattr(os, "fsync", failing_fsync)

    with pytest.raises(OSError, match="file fsync failed"):
        atomic_replace_bytes(target, b"replacement")

    assert target.read_bytes() == original_bytes
    assert _temporary_files(tmp_path, target) == []


def test_atomic_replace_failure_preserves_old_target_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.bin"
    original_bytes = b"original"
    target.write_bytes(original_bytes)

    def failing_replace(_temporary_path: Path, _target: Path) -> None:
        raise OSError("atomic replace failed")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError, match="atomic replace failed"):
        atomic_replace_bytes(target, b"replacement")

    assert target.read_bytes() == original_bytes
    assert _temporary_files(tmp_path, target) == []


def test_atomic_replace_directory_fsync_failure_propagates_after_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.bin"
    target.write_bytes(b"original")
    original_fsync = os.fsync
    calls = 0

    def fail_directory_fsync(file_descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("directory fsync failed")
        original_fsync(file_descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)

    with pytest.raises(OSError, match="directory fsync failed"):
        atomic_replace_bytes(target, b"replacement")

    assert target.read_bytes() == b"replacement"
    assert _temporary_files(tmp_path, target) == []


def test_create_once_existing_target_surfaces_conflict_and_preserves_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "record.bin"
    original_bytes = b"original"
    target.write_bytes(original_bytes)

    with pytest.raises(FileExistsError):
        create_once_bytes(target, b"replacement")

    assert target.read_bytes() == original_bytes
    assert _temporary_files(tmp_path, target) == []


def test_create_once_directory_fsync_failure_keeps_published_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.bin"
    original_fsync = os.fsync
    calls = 0

    def fail_directory_fsync(file_descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("directory fsync failed")
        original_fsync(file_descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)

    with pytest.raises(OSError, match="directory fsync failed"):
        create_once_bytes(target, b"published")

    assert target.read_bytes() == b"published"
    assert _temporary_files(tmp_path, target) == []


def test_temp_cleanup_failure_is_propagated_without_removing_published_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.bin"
    original_unlink = os.unlink

    def failing_unlink(path: Path) -> None:
        if Path(path).parent == tmp_path:
            raise OSError("temporary cleanup failed")
        original_unlink(path)

    monkeypatch.setattr(os, "unlink", failing_unlink)

    with pytest.raises(OSError, match="temporary cleanup failed"):
        create_once_bytes(target, b"published")

    assert target.read_bytes() == b"published"
    assert len(_temporary_files(tmp_path, target)) == 1


def test_durability_primitives_reject_non_bytes(tmp_path: Path) -> None:
    target = tmp_path / "record.bin"

    with pytest.raises(TypeError, match="bytes only"):
        atomic_replace_bytes(target, bytearray(b"not bytes"))  # type: ignore[arg-type]

    assert not target.exists()
    assert _temporary_files(tmp_path, target) == []
