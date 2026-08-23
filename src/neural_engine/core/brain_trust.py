"""Persisted Brain trust contract models.

This module defines validation-only models. It does not create, read, update,
or delete any Brain or trust-state files.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

BRAIN_TRUST_METADATA_FORMAT = "1.0.0"
BRAIN_TRUST_BINDING_FORMAT = "1.0.0"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class BrainTrustCompatibility(StrEnum):
    """Read-only format classification for future trust inspection."""

    OLD_FORMAT_UNADOPTED = "OLD_FORMAT_UNADOPTED"
    TRUST_METADATA_SUPPORTED = "TRUST_METADATA_SUPPORTED"
    TRUST_METADATA_UNSUPPORTED = "TRUST_METADATA_UNSUPPORTED"
    BINDING_SUPPORTED = "BINDING_SUPPORTED"
    BINDING_UNSUPPORTED = "BINDING_UNSUPPORTED"


class TargetAction(StrEnum):
    """Durable action for one Brain-relative target."""

    CREATE = "create"
    REPLACE = "replace"
    REMOVE = "remove"


class TransitionOperationKind(StrEnum):
    """The minimum operation distinction required by recovery semantics."""

    ORDINARY_MUTATION = "ordinary_mutation"
    ADOPTION = "adoption"
    RESTORE = "restore"
    CLONE = "clone"
    REBIND = "rebind"


class TargetDescriptor(BaseModel):
    """Bounded evidence for one intended Brain-relative file publication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str
    action: TargetAction
    before_sha256: str | None = None
    after_sha256: str | None = None

    @field_validator("relative_path")
    @classmethod
    def _relative_posix_path(cls, value: str) -> str:
        if not value or value in {".", ".."}:
            raise ValueError("Target path must be a non-empty relative locator.")
        if "\x00" in value or "\\" in value:
            raise ValueError("Target path must use POSIX separators.")

        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or PureWindowsPath(value).is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("Target path must be normalized and Brain-relative.")
        if path.as_posix() != value:
            raise ValueError("Target path must use normalized POSIX serialization.")
        return value

    @field_validator("before_sha256", "after_sha256")
    @classmethod
    def _sha256_or_absent(cls, value: str | None) -> str | None:
        if value is not None and _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("Target hash must be a lower-case SHA-256 value.")
        return value

    @model_validator(mode="after")
    def _action_hashes_must_match(self) -> TargetDescriptor:
        if self.action is TargetAction.CREATE:
            if self.before_sha256 is not None or self.after_sha256 is None:
                raise ValueError("Create targets require absent before bytes and after bytes.")
        elif self.action is TargetAction.REPLACE:
            if self.before_sha256 is None or self.after_sha256 is None:
                raise ValueError("Replace targets require both before and after bytes.")
        elif self.action is TargetAction.REMOVE and (
            self.before_sha256 is None or self.after_sha256 is not None
        ):
            raise ValueError("Remove targets require before bytes and absent after bytes.")
        return self


class PendingTransition(BaseModel):
    """The persisted marker for one in-flight Brain transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transition_id: UUID
    brain_id: UUID
    from_generation: StrictInt | None
    to_generation: StrictInt = Field(ge=1)
    operation_kind: TransitionOperationKind
    targets: tuple[TargetDescriptor, ...] = ()

    @field_validator("from_generation")
    @classmethod
    def _from_generation_is_positive_or_adoption_null(
        cls, value: StrictInt | None
    ) -> StrictInt | None:
        if value is not None and value < 1:
            raise ValueError("Transition from_generation must be at least 1 when present.")
        return value

    @field_validator("targets")
    @classmethod
    def _targets_are_finite_and_unique(
        cls, value: tuple[TargetDescriptor, ...]
    ) -> tuple[TargetDescriptor, ...]:
        paths = [target.relative_path for target in value]
        if len(paths) != len(set(paths)):
            raise ValueError("Transition target paths must be unique.")
        return value

    @model_validator(mode="after")
    def _operation_generation_rules(self) -> PendingTransition:
        kind = self.operation_kind
        if kind is TransitionOperationKind.ADOPTION:
            if self.from_generation is not None or self.to_generation != 1:
                raise ValueError("Adoption requires null from_generation and to_generation 1.")
            if self.targets:
                raise ValueError("Adoption must not rewrite existing record targets.")
        elif kind is TransitionOperationKind.ORDINARY_MUTATION:
            if self.from_generation is None or self.to_generation != self.from_generation + 1:
                raise ValueError("Ordinary mutation must advance generation by exactly one.")
            if not self.targets:
                raise ValueError("Ordinary mutation requires at least one target.")
        elif kind is TransitionOperationKind.RESTORE:
            if self.from_generation is None or self.to_generation <= self.from_generation:
                raise ValueError("Restore must target a generation above its prior context.")
            if not self.targets:
                raise ValueError("Restore requires target evidence.")
        elif kind is TransitionOperationKind.CLONE:
            if self.from_generation is None or self.to_generation != 1:
                raise ValueError("Clone requires a source generation and target generation 1.")
            if not self.targets:
                raise ValueError("Clone requires target evidence.")
        elif kind is TransitionOperationKind.REBIND:
            if self.from_generation is None or self.to_generation != self.from_generation:
                raise ValueError("Rebind must preserve the existing generation.")
            if self.targets:
                raise ValueError("Rebind must not publish record targets.")
        return self


class BrainMetadata(BaseModel):
    """Versioned Brain-local identity and generation metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata_format: str
    brain_id: UUID
    generation: StrictInt = Field(ge=1)
    pending_transition: PendingTransition | None = None

    @field_validator("metadata_format")
    @classmethod
    def _supported_metadata_format(cls, value: str) -> str:
        if value != BRAIN_TRUST_METADATA_FORMAT:
            raise ValueError("Unsupported Brain trust metadata format.")
        return value


class ExternalTrustBinding(BaseModel):
    """Versioned external expected-identity and generation binding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_format: str
    expected_brain_id: UUID
    accepted_generation: StrictInt = Field(ge=1)

    @field_validator("binding_format")
    @classmethod
    def _supported_binding_format(cls, value: str) -> str:
        if value != BRAIN_TRUST_BINDING_FORMAT:
            raise ValueError("Unsupported Brain trust binding format.")
        return value


def classify_metadata_format(value: str | None) -> BrainTrustCompatibility:
    """Classify metadata format without reading or mutating persisted state."""

    if value is None:
        return BrainTrustCompatibility.OLD_FORMAT_UNADOPTED
    if value == BRAIN_TRUST_METADATA_FORMAT:
        return BrainTrustCompatibility.TRUST_METADATA_SUPPORTED
    return BrainTrustCompatibility.TRUST_METADATA_UNSUPPORTED


def classify_binding_format(value: str | None) -> BrainTrustCompatibility:
    """Classify binding format without reading or mutating persisted state."""

    if value == BRAIN_TRUST_BINDING_FORMAT:
        return BrainTrustCompatibility.BINDING_SUPPORTED
    return BrainTrustCompatibility.BINDING_UNSUPPORTED
