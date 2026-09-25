from neural_engine.domain.opencode_compatibility import (
    OpencodeCompatibilityCheck,
    OpencodeCompatibilityReport,
    OpencodeCompatibilityState,
    OpencodeLiveSmokeResult,
)
from neural_engine.ports.opencode_compatibility import (
    OpencodeCapabilityObservation,
    OpencodeCommandProtocolProbe,
    OpencodeCompatibilityProbe,
    OpencodeLiveSmokeRunner,
)


class OpencodeCompatibilityService:
    """Classify required OpenCode capabilities without version pinning."""

    def __init__(
        self,
        probe: OpencodeCompatibilityProbe,
        live_smoke_runner: OpencodeLiveSmokeRunner,
        command_protocol_probe: OpencodeCommandProtocolProbe | None = None,
    ) -> None:
        self._probe = probe
        self._live_smoke_runner = live_smoke_runner
        self._command_protocol_probe = command_protocol_probe

    def inspect(
        self,
        *,
        live_smoke: bool = False,
        lane: str = "code",
    ) -> OpencodeCompatibilityReport:
        evidence = self._probe.inspect()
        command_protocol = evidence.command_protocol
        if self._command_protocol_probe is not None:
            command_protocol = self._command_protocol_probe.inspect()
        checks = tuple(self._classify(observation) for observation in evidence.capabilities)
        compatibility = self._overall(checks)
        live_result: OpencodeLiveSmokeResult | None = None

        if live_smoke:
            if compatibility in {
                OpencodeCompatibilityState.BLOCKED,
                OpencodeCompatibilityState.UNKNOWN,
            }:
                live_result = OpencodeLiveSmokeResult(
                    lane=lane,
                    state=compatibility,
                    detail="fast preflight did not permit a live smoke",
                )
            else:
                passed, detail = self._live_smoke_runner.run(evidence, lane=lane)
                live_result = OpencodeLiveSmokeResult(
                    lane=lane,
                    state=(
                        OpencodeCompatibilityState.PASS
                        if passed
                        else OpencodeCompatibilityState.BLOCKED
                    ),
                    detail=detail,
                )
                if not passed:
                    compatibility = OpencodeCompatibilityState.BLOCKED

        return OpencodeCompatibilityReport(
            version=evidence.version,
            checks=checks,
            compatibility=compatibility,
            live_smoke=live_result,
            command_protocol=command_protocol,
        )

    @staticmethod
    def _classify(
        observation: OpencodeCapabilityObservation,
    ) -> OpencodeCompatibilityCheck:
        available = observation.available
        critical = observation.critical
        if available is True:
            state = OpencodeCompatibilityState.PASS
        elif available is False:
            state = (
                OpencodeCompatibilityState.BLOCKED
                if critical
                else OpencodeCompatibilityState.DEGRADED
            )
        else:
            state = (
                OpencodeCompatibilityState.UNKNOWN
                if critical
                else OpencodeCompatibilityState.DEGRADED
            )
        return OpencodeCompatibilityCheck(
            name=observation.name,
            state=state,
            detail=observation.detail,
        )

    @staticmethod
    def _overall(
        checks: tuple[OpencodeCompatibilityCheck, ...],
    ) -> OpencodeCompatibilityState:
        states = {check.state for check in checks}
        if OpencodeCompatibilityState.BLOCKED in states:
            return OpencodeCompatibilityState.BLOCKED
        if OpencodeCompatibilityState.UNKNOWN in states:
            return OpencodeCompatibilityState.UNKNOWN
        if OpencodeCompatibilityState.DEGRADED in states:
            return OpencodeCompatibilityState.DEGRADED
        return OpencodeCompatibilityState.PASS
