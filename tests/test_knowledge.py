from datetime import UTC
from uuid import UUID

from neural_engine.domain import Knowledge, KnowledgeConfidence


def test_knowledge_has_domain_defaults() -> None:
    experience_id = UUID("11111111-1111-1111-1111-111111111111")

    knowledge = Knowledge(
        statement="Focused tests isolate failures quickly",
        rationale="The linked experience found the failing behavior with a narrow test run.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[experience_id],
    )

    assert isinstance(knowledge.id, UUID)
    assert knowledge.timestamp.tzinfo == UTC
    assert knowledge.statement == "Focused tests isolate failures quickly"
    assert (
        knowledge.rationale
        == "The linked experience found the failing behavior with a narrow test run."
    )
    assert knowledge.confidence == KnowledgeConfidence.HIGH
    assert knowledge.experience_ids == [experience_id]
    assert knowledge.tags == []


def test_knowledge_confidence_values() -> None:
    assert KnowledgeConfidence.LOW.value == "low"
    assert KnowledgeConfidence.MEDIUM.value == "medium"
    assert KnowledgeConfidence.HIGH.value == "high"
