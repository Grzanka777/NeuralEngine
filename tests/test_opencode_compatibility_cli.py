import pytest
from typer.testing import CliRunner

import neural_engine.cli as cli
from neural_engine.domain.opencode_compatibility import (
    OpencodeCompatibilityCheck,
    OpencodeCompatibilityReport,
    OpencodeCompatibilityState,
)


class FakeCompatibilityService:
    def __init__(self, report: OpencodeCompatibilityReport) -> None:
        self.report = report
        self.calls: list[tuple[bool, str]] = []

    def inspect(self, *, live_smoke: bool, lane: str) -> OpencodeCompatibilityReport:
        self.calls.append((live_smoke, lane))
        return self.report


class FakeContainer:
    def __init__(self, service: FakeCompatibilityService) -> None:
        self.service = service

    def opencode_compatibility_service(self) -> FakeCompatibilityService:
        return self.service


def test_opencode_doctor_reports_pass_without_version_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeCompatibilityService(
        OpencodeCompatibilityReport(
            version="opencode v99.9.9",
            checks=(
                OpencodeCompatibilityCheck("executable", OpencodeCompatibilityState.PASS, "found"),
            ),
            compatibility=OpencodeCompatibilityState.PASS,
        )
    )
    monkeypatch.setattr(cli, "container", FakeContainer(service))

    result = CliRunner().invoke(cli.app, ["opencode", "doctor"])

    assert result.exit_code == 0
    assert "OpenCode: opencode v99.9.9" in result.output
    assert "Compatibility: PASS" in result.output
    assert service.calls == [(False, "code")]


def test_opencode_doctor_returns_zero_for_degraded_optional_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeCompatibilityService(
        OpencodeCompatibilityReport(
            version="opencode v2.0.8",
            checks=(
                OpencodeCompatibilityCheck(
                    "VISION routing", OpencodeCompatibilityState.DEGRADED, "missing"
                ),
            ),
            compatibility=OpencodeCompatibilityState.DEGRADED,
        )
    )
    monkeypatch.setattr(cli, "container", FakeContainer(service))

    result = CliRunner().invoke(cli.app, ["opencode", "doctor"])

    assert result.exit_code == 0
    assert "Compatibility: DEGRADED" in result.output


def test_opencode_doctor_rejects_invalid_lane_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeCompatibilityService(
        OpencodeCompatibilityReport(
            version="opencode v2.0.8",
            checks=(),
            compatibility=OpencodeCompatibilityState.PASS,
        )
    )
    monkeypatch.setattr(cli, "container", FakeContainer(service))

    result = CliRunner().invoke(cli.app, ["opencode", "doctor", "--lane", "vision"])

    assert result.exit_code == 2
    assert service.calls == []
