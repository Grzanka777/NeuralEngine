from pathlib import Path

from neural_engine.application.opencode_compatibility_service import (
    OpencodeCompatibilityService,
)
from neural_engine.domain.opencode_compatibility import OpencodeCompatibilityState
from neural_engine.ports.opencode_compatibility import (
    OpencodeCapabilityObservation,
    OpencodeCompatibilityEvidence,
)


def _evidence(
    *observations: OpencodeCapabilityObservation,
    version: str | None = "opencode v99.9.9",
) -> OpencodeCompatibilityEvidence:
    return OpencodeCompatibilityEvidence(
        version=version,
        capabilities=observations,
        wrapper_path=Path("/tmp/opencode-watch"),
        llm_path=Path("/tmp/llm"),
        model_ids=(
            ("llama-general/qwen3.6-general-local", "qwen3.6-general-local"),
            ("llama-code/qwen3-coder-local", "qwen3-coder-local"),
        ),
    )


class FakeProbe:
    def __init__(self, evidence: OpencodeCompatibilityEvidence) -> None:
        self.evidence = evidence

    def inspect(self) -> OpencodeCompatibilityEvidence:
        return self.evidence


class FakeSmokeRunner:
    def __init__(self, result: tuple[bool, str] = (True, "smoke passed")) -> None:
        self.result = result
        self.lanes: list[str] = []

    def run(self, evidence: OpencodeCompatibilityEvidence, *, lane: str) -> tuple[bool, str]:
        self.lanes.append(lane)
        return self.result


def test_different_opencode_version_is_diagnostic_only() -> None:
    evidence = _evidence(
        OpencodeCapabilityObservation("executable", True, "found", True),
        OpencodeCapabilityObservation("config", True, "found", True),
        OpencodeCapabilityObservation("wrapper", True, "found", True),
    )

    report = OpencodeCompatibilityService(FakeProbe(evidence), FakeSmokeRunner()).inspect()

    assert report.version == "opencode v99.9.9"
    assert report.compatibility is OpencodeCompatibilityState.PASS


def test_missing_optional_capability_degrades_without_stopping_work() -> None:
    evidence = _evidence(
        OpencodeCapabilityObservation("executable", True, "found", True),
        OpencodeCapabilityObservation("VISION routing", False, "missing", False),
    )

    report = OpencodeCompatibilityService(FakeProbe(evidence), FakeSmokeRunner()).inspect()

    assert report.compatibility is OpencodeCompatibilityState.DEGRADED
    assert report.checks[1].state is OpencodeCompatibilityState.DEGRADED


def test_missing_critical_capability_blocks() -> None:
    evidence = _evidence(
        OpencodeCapabilityObservation("executable", True, "found", True),
        OpencodeCapabilityObservation("CODE routing", False, "missing", True),
    )

    report = OpencodeCompatibilityService(FakeProbe(evidence), FakeSmokeRunner()).inspect()

    assert report.compatibility is OpencodeCompatibilityState.BLOCKED


def test_unknown_critical_capability_is_not_reported_as_pass() -> None:
    evidence = _evidence(
        OpencodeCapabilityObservation("executable", True, "found", True),
        OpencodeCapabilityObservation("config", None, "unreadable", True),
    )

    report = OpencodeCompatibilityService(FakeProbe(evidence), FakeSmokeRunner()).inspect()

    assert report.compatibility is OpencodeCompatibilityState.UNKNOWN


def test_live_smoke_is_explicit_and_failed_smoke_blocks() -> None:
    evidence = _evidence(
        OpencodeCapabilityObservation("executable", True, "found", True),
    )
    runner = FakeSmokeRunner((False, "cleanup failed"))

    report = OpencodeCompatibilityService(FakeProbe(evidence), runner).inspect(
        live_smoke=True,
        lane="code",
    )

    assert runner.lanes == ["code"]
    assert report.compatibility is OpencodeCompatibilityState.BLOCKED
    assert report.live_smoke is not None
    assert report.live_smoke.state is OpencodeCompatibilityState.BLOCKED
