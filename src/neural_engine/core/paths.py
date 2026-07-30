import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

NEURAL_HOME_ENV = "NEURAL_HOME"
RECORD_STORE_NAMES: tuple[str, ...] = (
    "observations",
    "experiences",
    "knowledge",
    "playbooks",
    "playbook-runs",
    "playbook-evaluations",
    "evolution-proposals",
    "playbook-revisions",
    "playbook-revision-activations",
    "playbook-revision-applications",
    "decisions",
    "decision-acceptances",
    "decision-actions",
    "decision-outcomes",
    "decision-reviews",
)

NeuralHomeSource = Literal["default", "override"]
NeuralHomeReason = Literal[
    "invalid_configuration",
    "home_unavailable",
    "home_not_directory",
    "home_inaccessible",
    "brain_uninitialized",
    "brain_unavailable",
]
AccessChecker = Callable[[Path, int], bool]


class NeuralHomeError(Exception):
    """A controlled Neural home resolution or availability failure."""

    def __init__(
        self,
        reason: NeuralHomeReason,
        *,
        source: NeuralHomeSource,
        configured_value: str | None,
        resolved_path: Path | None = None,
        detail: str | None = None,
        operation: str | None = None,
    ) -> None:
        self.reason = reason
        self.source = source
        self.configured_value = configured_value
        self.resolved_path = resolved_path
        self.detail = detail
        self.operation = operation
        super().__init__(self._message())

    def _message(self) -> str:
        if self.reason == "invalid_configuration":
            detail = self.detail or "the value is invalid"
            return f"Invalid {NEURAL_HOME_ENV}: {detail}. No fallback was used."

        configured = self.configured_value or "-"
        if self.reason == "home_unavailable":
            return f"Configured Neural home is unavailable: {configured}. No fallback was used."
        selected = configured if self.source == "override" else str(self.resolved_path or "-")
        label = "Configured" if self.source == "override" else "Default"
        if self.reason == "home_not_directory":
            return f"{label} Neural home is not a directory: {selected}."
        if self.reason == "home_inaccessible":
            operation = self.operation or "operation"
            return f"{label} Neural home is inaccessible for {operation}: {selected}."

        resolved = self.resolved_path or Path(configured)
        if self.reason == "brain_uninitialized":
            return f"Neural Brain is not initialized at {resolved / 'brain'}. Run 'neural init'."
        return f"Neural Brain became unavailable at {resolved / 'brain'}. No fallback was used."


@dataclass(frozen=True, slots=True)
class NeuralPaths:
    """One immutable, internally consistent set of Neural Engine paths."""

    source: NeuralHomeSource
    configured_value: str | None
    HOME: Path
    _access_checker: AccessChecker = field(repr=False, compare=False)

    BRAIN: Path = field(init=False)
    EXPERIENCES: Path = field(init=False)
    OBSERVATIONS: Path = field(init=False)
    KNOWLEDGE: Path = field(init=False)
    PLAYBOOKS: Path = field(init=False)
    PLAYBOOK_RUNS: Path = field(init=False)
    PLAYBOOK_EVALUATIONS: Path = field(init=False)
    EVOLUTION_PROPOSALS: Path = field(init=False)
    PLAYBOOK_REVISIONS: Path = field(init=False)
    PLAYBOOK_REVISION_ACTIVATIONS: Path = field(init=False)
    PLAYBOOK_REVISION_APPLICATIONS: Path = field(init=False)
    DECISIONS: Path = field(init=False)
    DECISION_ACCEPTANCES: Path = field(init=False)
    DECISION_ACTIONS: Path = field(init=False)
    DECISION_OUTCOMES: Path = field(init=False)
    DECISION_REVIEWS: Path = field(init=False)
    PROJECTS: Path = field(init=False)
    LOGS: Path = field(init=False)
    CONFIG: Path = field(init=False)
    VERSION: Path = field(init=False)

    def __post_init__(self) -> None:
        brain = self.HOME / "brain"
        object.__setattr__(self, "BRAIN", brain)
        object.__setattr__(self, "EXPERIENCES", brain / "experiences")
        object.__setattr__(self, "OBSERVATIONS", brain / "observations")
        object.__setattr__(self, "KNOWLEDGE", brain / "knowledge")
        object.__setattr__(self, "PLAYBOOKS", brain / "playbooks")
        object.__setattr__(self, "PLAYBOOK_RUNS", brain / "playbook-runs")
        object.__setattr__(self, "PLAYBOOK_EVALUATIONS", brain / "playbook-evaluations")
        object.__setattr__(self, "EVOLUTION_PROPOSALS", brain / "evolution-proposals")
        object.__setattr__(self, "PLAYBOOK_REVISIONS", brain / "playbook-revisions")
        object.__setattr__(
            self,
            "PLAYBOOK_REVISION_ACTIVATIONS",
            brain / "playbook-revision-activations",
        )
        object.__setattr__(
            self,
            "PLAYBOOK_REVISION_APPLICATIONS",
            brain / "playbook-revision-applications",
        )
        object.__setattr__(self, "DECISIONS", brain / "decisions")
        object.__setattr__(self, "DECISION_ACCEPTANCES", brain / "decision-acceptances")
        object.__setattr__(self, "DECISION_ACTIONS", brain / "decision-actions")
        object.__setattr__(self, "DECISION_OUTCOMES", brain / "decision-outcomes")
        object.__setattr__(self, "DECISION_REVIEWS", brain / "decision-reviews")
        object.__setattr__(self, "PROJECTS", self.HOME / "projects")
        object.__setattr__(self, "LOGS", self.HOME / "logs")
        object.__setattr__(self, "CONFIG", self.HOME / "config.toml")
        object.__setattr__(self, "VERSION", self.HOME / "VERSION")

    @property
    def is_override(self) -> bool:
        return self.source == "override"

    @property
    def record_stores(self) -> tuple[tuple[str, Path], ...]:
        """Return the canonical ordered JSON record-store topology."""

        paths = (
            self.OBSERVATIONS,
            self.EXPERIENCES,
            self.KNOWLEDGE,
            self.PLAYBOOKS,
            self.PLAYBOOK_RUNS,
            self.PLAYBOOK_EVALUATIONS,
            self.EVOLUTION_PROPOSALS,
            self.PLAYBOOK_REVISIONS,
            self.PLAYBOOK_REVISION_ACTIVATIONS,
            self.PLAYBOOK_REVISION_APPLICATIONS,
            self.DECISIONS,
            self.DECISION_ACCEPTANCES,
            self.DECISION_ACTIONS,
            self.DECISION_OUTCOMES,
            self.DECISION_REVIEWS,
        )
        return tuple(zip(RECORD_STORE_NAMES, paths, strict=True))

    def require_available(
        self,
        *,
        operation: str,
        writable: bool = False,
        require_brain: bool = False,
    ) -> None:
        """Revalidate a configured root immediately before an operation."""

        if not self.is_override:
            if not self.HOME.exists():
                return
            if not self.HOME.is_dir():
                raise NeuralHomeError(
                    "home_not_directory",
                    source=self.source,
                    configured_value=None,
                    resolved_path=self.HOME,
                )
            mode = os.R_OK | os.X_OK
            if writable:
                mode |= os.W_OK
            if not self._access_checker(self.HOME, mode):
                raise NeuralHomeError(
                    "home_inaccessible",
                    source=self.source,
                    configured_value=None,
                    resolved_path=self.HOME,
                    operation=operation,
                )
            return

        try:
            resolved = Path(self.configured_value or "").resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise NeuralHomeError(
                "home_unavailable",
                source=self.source,
                configured_value=self.configured_value,
            ) from error

        if resolved != self.HOME:
            raise NeuralHomeError(
                "home_unavailable",
                source=self.source,
                configured_value=self.configured_value,
            )
        if not resolved.is_dir():
            raise NeuralHomeError(
                "home_not_directory",
                source=self.source,
                configured_value=self.configured_value,
                resolved_path=resolved,
            )

        mode = os.R_OK | os.X_OK
        if writable:
            mode |= os.W_OK
        if not self._access_checker(resolved, mode):
            raise NeuralHomeError(
                "home_inaccessible",
                source=self.source,
                configured_value=self.configured_value,
                resolved_path=resolved,
                operation=operation,
            )

        if require_brain:
            if not self.BRAIN.exists():
                if self.BRAIN.is_symlink():
                    raise NeuralHomeError(
                        "brain_unavailable",
                        source=self.source,
                        configured_value=self.configured_value,
                        resolved_path=resolved,
                        operation=operation,
                    )
                raise NeuralHomeError(
                    "brain_uninitialized",
                    source=self.source,
                    configured_value=self.configured_value,
                    resolved_path=resolved,
                )
            if not self.BRAIN.is_dir() or not self._access_checker(self.BRAIN, mode):
                raise NeuralHomeError(
                    "brain_unavailable",
                    source=self.source,
                    configured_value=self.configured_value,
                    resolved_path=resolved,
                    operation=operation,
                )


def resolve_neural_paths(
    *,
    environ: Mapping[str, str] | None = None,
    default_home: Path | None = None,
    access_checker: AccessChecker = os.access,
) -> NeuralPaths:
    """Resolve one Neural home without caching environment-derived state."""

    environment = os.environ if environ is None else environ
    fallback = (default_home if default_home is not None else Path.home()) / ".neural"

    if NEURAL_HOME_ENV not in environment:
        return NeuralPaths(
            source="default",
            configured_value=None,
            HOME=fallback,
            _access_checker=access_checker,
        )

    value = environment[NEURAL_HOME_ENV]
    if not value:
        raise _invalid_override(value, "the value must not be blank")
    if value != value.strip():
        raise _invalid_override(value, "leading or trailing whitespace is not allowed")
    if "\x00" in value:
        raise _invalid_override(value, "NUL characters are not allowed")
    if "~" in value:
        raise _invalid_override(value, "'~' is not expanded or allowed")

    configured = Path(value)
    if not configured.is_absolute():
        raise _invalid_override(value, "the path must be absolute")

    try:
        resolved = configured.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise NeuralHomeError(
            "home_unavailable",
            source="override",
            configured_value=value,
        ) from error

    if not resolved.is_dir():
        raise NeuralHomeError(
            "home_not_directory",
            source="override",
            configured_value=value,
            resolved_path=resolved,
        )
    if not access_checker(resolved, os.R_OK | os.X_OK):
        raise NeuralHomeError(
            "home_inaccessible",
            source="override",
            configured_value=value,
            resolved_path=resolved,
            operation="read",
        )

    return NeuralPaths(
        source="override",
        configured_value=value,
        HOME=resolved,
        _access_checker=access_checker,
    )


def _invalid_override(value: str, detail: str) -> NeuralHomeError:
    return NeuralHomeError(
        "invalid_configuration",
        source="override",
        configured_value=value,
        detail=detail,
    )
