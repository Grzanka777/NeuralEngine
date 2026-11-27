"""Read-only, project-scoped Brain context assembly for bounded agent handoffs."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from neural_engine.domain import Decision, Knowledge
from neural_engine.ports.decision_acceptance_repository import DecisionAcceptanceRepository
from neural_engine.ports.decision_repository import DecisionRepository
from neural_engine.ports.knowledge_repository import KnowledgeRepository

MIN_CONTEXT_MAX_BYTES = 512
MAX_CONTEXT_MAX_BYTES = 16_384
DEFAULT_CONTEXT_MAX_BYTES = 4_096

# Best-effort pattern filter only; not a confidentiality or DLP guarantee.
_SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:api_key|token|password|secret)\b\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_REDACTED_TEXT = "[content withheld by best-effort secret filter]"
_SECRET_WARNING = "potential credential pattern withheld by best-effort secret filter"
_TRUNCATED_WARNING = (
    "Context truncated: omitted records exceeded byte budget; authority or evidence is incomplete."
)

BrainDecisionStatus = Literal["accepted", "rejected", "proposed"]


class BrainContextFormat(StrEnum):
    """Supported deterministic output formats for scoped Brain context."""

    JSON = "json"
    MARKDOWN = "markdown"


class BrainContextError(Exception):
    """Base error for read-only scoped Brain context assembly."""


class BrainContextProjectKeyRequiredError(BrainContextError):
    """Raised when the project scope key is blank."""

    def __init__(self) -> None:
        super().__init__("Project key must not be blank.")


class BrainContextTopicError(BrainContextError):
    """Raised when an explicit topic filter is blank."""

    def __init__(self) -> None:
        super().__init__("Topic filter must not be blank when supplied.")


class BrainContextBudgetError(BrainContextError):
    """Raised when max_bytes is outside the supported bounds."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(
            f"Context byte budget {max_bytes} must be between "
            f"{MIN_CONTEXT_MAX_BYTES} and {MAX_CONTEXT_MAX_BYTES}."
        )


class BrainContextIntegrityError(BrainContextError):
    """Raised when persisted Decision relations or acceptances fail integrity checks."""


class BrainDecisionItem(BaseModel):
    """Compact, non-persisted Decision representation for agent task prompts."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    action: str
    record: str
    status: BrainDecisionStatus
    supersedes: str | None = None
    superseded_by: tuple[str, ...] = ()


class BrainKnowledgeItem(BaseModel):
    """Compact, non-persisted Knowledge representation for agent task prompts."""

    model_config = ConfigDict(frozen=True)

    id: str
    record: str
    confidence: str


class ScopedBrainContext(BaseModel):
    """Non-persisted, project-scoped Brain context bundle."""

    model_config = ConfigDict(frozen=True)

    project: str
    topic: str | None = None
    planner_enrichment: bool = False
    decisions: tuple[BrainDecisionItem, ...] = ()
    knowledge: tuple[BrainKnowledgeItem, ...] = ()
    truncated: bool = False
    omitted_decisions: int = 0
    omitted_knowledge: int = 0
    warnings: tuple[str, ...] = ()


class BrainContextService:
    """Assemble compact, bounded, project-scoped Brain context without mutating state."""

    def __init__(
        self,
        decision_repository: DecisionRepository,
        acceptance_repository: DecisionAcceptanceRepository,
        knowledge_repository: KnowledgeRepository,
    ) -> None:
        self._decision_repository = decision_repository
        self._acceptance_repository = acceptance_repository
        self._knowledge_repository = knowledge_repository

    def assemble(
        self,
        project_key: str,
        *,
        topic: str | None = None,
        max_bytes: int = DEFAULT_CONTEXT_MAX_BYTES,
        output_format: BrainContextFormat = BrainContextFormat.JSON,
    ) -> ScopedBrainContext:
        """Return the bounded scoped context for one project."""

        context, _ = self.assemble_rendered(
            project_key,
            topic=topic,
            max_bytes=max_bytes,
            output_format=output_format,
        )
        return context

    def assemble_rendered(
        self,
        project_key: str,
        *,
        topic: str | None = None,
        max_bytes: int = DEFAULT_CONTEXT_MAX_BYTES,
        output_format: BrainContextFormat = BrainContextFormat.JSON,
    ) -> tuple[ScopedBrainContext, str]:
        """Assemble and render a bounded scoped Brain context bundle."""

        normalized_project = project_key.strip()
        if not normalized_project:
            raise BrainContextProjectKeyRequiredError()

        normalized_topic: str | None = None
        if topic is not None:
            normalized_topic = topic.strip()
            if not normalized_topic:
                raise BrainContextTopicError()

        if max_bytes < MIN_CONTEXT_MAX_BYTES or max_bytes > MAX_CONTEXT_MAX_BYTES:
            raise BrainContextBudgetError(max_bytes)

        all_decisions = self._decision_repository.load_all()
        decisions_by_id = {decision.id: decision for decision in all_decisions}
        project_decisions = [
            decision for decision in all_decisions if decision.project_key == normalized_project
        ]
        superseded_by = self._validated_supersession_map(
            normalized_project,
            project_decisions,
            decisions_by_id,
        )
        accepted_ids = self._accepted_ids_for_project(project_decisions)
        selected_decisions = self._filter_and_order_decisions(
            project_decisions,
            superseded_by,
            normalized_topic,
        )
        selected_knowledge = self._filter_and_order_knowledge(
            self._knowledge_repository.load_all(),
            normalized_project,
            normalized_topic,
        )

        warnings: set[str] = set()
        decision_items = [
            self._to_decision_item(decision, accepted_ids, superseded_by, warnings)
            for decision in selected_decisions
        ]
        knowledge_items = [
            self._to_knowledge_item(knowledge, warnings) for knowledge in selected_knowledge
        ]
        return self._pack_to_budget(
            project=normalized_project,
            topic=normalized_topic,
            decisions=decision_items,
            knowledge=knowledge_items,
            warnings=tuple(sorted(warnings)),
            max_bytes=max_bytes,
            output_format=output_format,
        )

    @staticmethod
    def render(
        context: ScopedBrainContext,
        *,
        output_format: BrainContextFormat = BrainContextFormat.JSON,
    ) -> str:
        """Render a ScopedBrainContext deterministically in JSON or Markdown."""

        if output_format is BrainContextFormat.JSON:
            payload: dict[str, object] = {
                "project": context.project,
                "topic": context.topic,
                "planner_enrichment": context.planner_enrichment,
                "decisions": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "action": item.action,
                        "record": item.record,
                        "status": item.status,
                        "supersedes": item.supersedes,
                        "superseded_by": list(item.superseded_by),
                    }
                    for item in context.decisions
                ],
                "knowledge": [
                    {
                        "id": item.id,
                        "record": item.record,
                        "confidence": item.confidence,
                    }
                    for item in context.knowledge
                ],
                "truncated": context.truncated,
                "omitted_decisions": context.omitted_decisions,
                "omitted_knowledge": context.omitted_knowledge,
            }
            if context.warnings:
                payload["warnings"] = list(context.warnings)
            return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

        lines = [
            "# Scoped Brain Context",
            f"- Project: {context.project}",
            f"- Topic: {context.topic or 'all'}",
            f"- Planner enrichment: {'enabled' if context.planner_enrichment else 'disabled'}",
            "",
            "## Decisions",
        ]
        if not context.decisions:
            lines.append("- None")
        else:
            for item in context.decisions:
                relations: list[str] = []
                if item.supersedes is not None:
                    relations.append(f"supersedes={item.supersedes}")
                if item.superseded_by:
                    relations.append(f"superseded_by={','.join(item.superseded_by)}")
                relation_suffix = f" | {' '.join(relations)}" if relations else ""
                lines.append(
                    f"- [{item.status}] {item.id} | {item.title} | "
                    f"action={item.action} | record={item.record}{relation_suffix}"
                )

        lines.extend(["", "## Knowledge"])
        if not context.knowledge:
            lines.append("- None")
        else:
            for knowledge in context.knowledge:
                lines.append(f"- {knowledge.id} ({knowledge.confidence}) | {knowledge.record}")

        if context.truncated:
            lines.extend(
                [
                    "",
                    "## Truncation",
                    f"- omitted_decisions={context.omitted_decisions}",
                    f"- omitted_knowledge={context.omitted_knowledge}",
                ]
            )
        if context.warnings:
            lines.extend(["", "## Warnings", *(f"- {warning}" for warning in context.warnings)])

        return "\n".join(lines)

    @staticmethod
    def _validated_supersession_map(
        project_key: str,
        project_decisions: list[Decision],
        decisions_by_id: dict[UUID, Decision],
    ) -> dict[UUID, list[UUID]]:
        superseded_by: dict[UUID, list[UUID]] = defaultdict(list)
        predecessor_map: dict[UUID, UUID] = {}
        for decision in project_decisions:
            target_id = decision.supersedes_decision_id
            if target_id is None:
                continue
            target = decisions_by_id.get(target_id)
            if target is None:
                raise BrainContextIntegrityError(
                    f"Decision {decision.id} supersedes missing Decision {target_id}."
                )
            if target.project_key != project_key:
                raise BrainContextIntegrityError(
                    f"Decision {decision.id} supersedes cross-project Decision {target_id}."
                )
            superseded_by[target_id].append(decision.id)
            predecessor_map[decision.id] = target_id

        visited: set[UUID] = set()
        visiting: set[UUID] = set()
        for decision in project_decisions:
            if decision.id in visited:
                continue
            current: UUID | None = decision.id
            path: list[UUID] = []
            while current is not None:
                if current in visiting:
                    raise BrainContextIntegrityError("Decision supersession cycle detected.")
                if current in visited:
                    break
                visiting.add(current)
                path.append(current)
                current = predecessor_map.get(current)
            visited.update(path)
            visiting.difference_update(path)

        return superseded_by

    def _accepted_ids_for_project(self, project_decisions: list[Decision]) -> set[UUID]:
        project_ids = {decision.id for decision in project_decisions}
        counts: dict[UUID, int] = defaultdict(int)
        for acceptance in self._acceptance_repository.load_all():
            if acceptance.decision_id in project_ids:
                counts[acceptance.decision_id] += 1
        duplicates = sorted(str(decision_id) for decision_id, count in counts.items() if count > 1)
        if duplicates:
            raise BrainContextIntegrityError(
                f"Decision has multiple acceptance records: {duplicates[0]}"
            )
        return set(counts)

    @staticmethod
    def _filter_and_order_decisions(
        project_decisions: list[Decision],
        superseded_by: dict[UUID, list[UUID]],
        topic: str | None,
    ) -> list[Decision]:
        if topic is None:
            selected = list(project_decisions)
        else:
            needle = topic.casefold()
            decisions_by_id = {decision.id: decision for decision in project_decisions}
            matched_ids: set[UUID] = {
                decision.id
                for decision in project_decisions
                if BrainContextService._decision_matches_topic(decision, needle)
            }
            frontier = list(matched_ids)
            while frontier:
                current_id = frontier.pop()
                current = decisions_by_id[current_id]
                neighbors = list(superseded_by.get(current_id, ()))
                if current.supersedes_decision_id is not None:
                    neighbors.append(current.supersedes_decision_id)
                for neighbor_id in neighbors:
                    if neighbor_id not in matched_ids:
                        matched_ids.add(neighbor_id)
                        frontier.append(neighbor_id)
            selected = [decision for decision in project_decisions if decision.id in matched_ids]

        return sorted(
            selected,
            key=lambda d: (bool(superseded_by.get(d.id)), -d.created_at.timestamp(), str(d.id)),
        )

    @staticmethod
    def _decision_matches_topic(decision: Decision, needle: str) -> bool:
        haystacks = (
            decision.title,
            decision.objective,
            decision.context_summary,
            decision.proposed_option,
            decision.rationale,
            *decision.tags,
        )
        return any(needle in value.casefold() for value in haystacks)

    @staticmethod
    def _filter_and_order_knowledge(
        all_knowledge: list[Knowledge],
        project_key: str,
        topic: str | None,
    ) -> list[Knowledge]:
        project_items = [item for item in all_knowledge if project_key in item.tags]
        if topic is not None:
            needle = topic.casefold()
            project_items = [
                item
                for item in project_items
                if any(
                    needle in value.casefold()
                    for value in (item.statement, item.rationale, *item.tags)
                )
            ]
        return sorted(
            project_items,
            key=lambda item: (-item.timestamp.timestamp(), str(item.id)),
        )

    @staticmethod
    def _sanitize(value: str, warnings: set[str]) -> str:
        if _SECRET_PATTERN.search(value):
            warnings.add(_SECRET_WARNING)
            return _REDACTED_TEXT
        return " ".join(value.split())

    def _to_decision_item(
        self,
        decision: Decision,
        accepted_ids: set[UUID],
        superseded_by: dict[UUID, list[UUID]],
        warnings: set[str],
    ) -> BrainDecisionItem:
        if decision.id in accepted_ids:
            status: BrainDecisionStatus = "accepted"
        elif "rejected" in {tag.casefold() for tag in decision.tags}:
            status = "rejected"
        else:
            status = "proposed"

        superseding = tuple(sorted(str(item) for item in superseded_by.get(decision.id, ())))
        return BrainDecisionItem(
            id=str(decision.id),
            title=self._sanitize(decision.title, warnings),
            action=self._sanitize(decision.proposed_option, warnings),
            record=self._sanitize(decision.rationale, warnings),
            status=status,
            supersedes=(
                str(decision.supersedes_decision_id)
                if decision.supersedes_decision_id is not None
                else None
            ),
            superseded_by=superseding,
        )

    def _to_knowledge_item(
        self,
        knowledge: Knowledge,
        warnings: set[str],
    ) -> BrainKnowledgeItem:
        return BrainKnowledgeItem(
            id=str(knowledge.id),
            record=self._sanitize(knowledge.statement, warnings),
            confidence=knowledge.confidence.value,
        )

    @staticmethod
    def _decision_groups(decisions: list[BrainDecisionItem]) -> list[list[BrainDecisionItem]]:
        """Group decisions connected by supersession or same normalized title."""
        by_id = {item.id: item for item in decisions}
        by_title: dict[str, list[str]] = defaultdict(list)
        for item in decisions:
            by_title[item.title.casefold()].append(item.id)

        visited: set[str] = set()
        groups: list[list[BrainDecisionItem]] = []
        order_index = {item.id: idx for idx, item in enumerate(decisions)}

        for item in decisions:
            if item.id in visited:
                continue
            component_ids: set[str] = set()
            stack = [item.id]
            while stack:
                current_id = stack.pop()
                if current_id in component_ids or current_id not in by_id:
                    continue
                component_ids.add(current_id)
                current = by_id[current_id]
                neighbors = [
                    *current.superseded_by,
                    *by_title[current.title.casefold()],
                ]
                if current.supersedes is not None:
                    neighbors.append(current.supersedes)
                for neighbor_id in neighbors:
                    if neighbor_id not in component_ids and neighbor_id in by_id:
                        stack.append(neighbor_id)
            visited.update(component_ids)
            groups.append(
                sorted((by_id[cid] for cid in component_ids), key=lambda d: order_index[d.id])
            )

        return groups

    def _pack_to_budget(
        self,
        *,
        project: str,
        topic: str | None,
        decisions: list[BrainDecisionItem],
        knowledge: list[BrainKnowledgeItem],
        warnings: tuple[str, ...],
        max_bytes: int,
        output_format: BrainContextFormat,
    ) -> tuple[ScopedBrainContext, str]:
        included_decisions: list[BrainDecisionItem] = []
        included_knowledge: list[BrainKnowledgeItem] = []
        total_decisions = len(decisions)
        total_knowledge = len(knowledge)

        def build(
            cand_decisions: list[BrainDecisionItem],
            cand_knowledge: list[BrainKnowledgeItem],
        ) -> tuple[ScopedBrainContext, str]:
            omitted_d = total_decisions - len(cand_decisions)
            omitted_k = total_knowledge - len(cand_knowledge)
            truncated = omitted_d > 0 or omitted_k > 0
            combined_warnings = (
                tuple(sorted({*warnings, _TRUNCATED_WARNING})) if truncated else warnings
            )
            ctx = ScopedBrainContext(
                project=project,
                topic=topic,
                planner_enrichment=False,
                decisions=tuple(cand_decisions),
                knowledge=tuple(cand_knowledge),
                truncated=truncated,
                omitted_decisions=omitted_d,
                omitted_knowledge=omitted_k,
                warnings=combined_warnings,
            )
            return ctx, self.render(ctx, output_format=output_format)

        # Pack supersession/title-linked decision groups atomically and without clipping records,
        # so an accepted decision is never emitted without its superseding or rejecting peers.
        for group in self._decision_groups(decisions):
            trial_decisions = [*included_decisions, *group]
            _, rendered = build(trial_decisions, included_knowledge)
            if len(rendered.encode("utf-8")) <= max_bytes:
                included_decisions = trial_decisions
            else:
                break

        if len(included_decisions) == total_decisions:
            for knowledge_item in knowledge:
                trial_knowledge = [*included_knowledge, knowledge_item]
                _, rendered = build(included_decisions, trial_knowledge)
                if len(rendered.encode("utf-8")) <= max_bytes:
                    included_knowledge = trial_knowledge
                else:
                    break

        final_context, final_rendered = build(included_decisions, included_knowledge)
        if len(final_rendered.encode("utf-8")) > max_bytes:
            raise BrainContextBudgetError(max_bytes)
        return final_context, final_rendered
