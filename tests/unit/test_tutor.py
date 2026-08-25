from uuid import UUID

import pytest
from pydantic import ValidationError

from app.llm.gateway import _extractive_answer
from app.rag.types import RetrievedEvidence
from app.schemas.tutor import TutorScope
from app.services.tutor_service import _evidence_status, _remove_unknown_citations


def _evidence(score: float = 0.8) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id="doc:0",
        document_id=str(UUID("00000000-0000-0000-0000-000000000003")),
        filename="lecture.md",
        page_number=1,
        section_title="Regularization",
        text="L1 regularization encourages sparse coefficients.",
        score=score,
    )


def test_scope_rejects_inverted_page_range() -> None:
    with pytest.raises(ValidationError):
        TutorScope(page_from=5, page_to=2)


def test_unknown_citations_are_removed() -> None:
    answer = _remove_unknown_citations("Supported [c1], invented [c9].", 2)

    assert answer == "Supported [c1], invented ."


def test_evidence_status_uses_retrieval_strength() -> None:
    assert _evidence_status([]) == "insufficient"
    assert _evidence_status([_evidence(0.1)]) == "partial"
    assert _evidence_status([_evidence(0.7)]) == "sufficient"


def test_extractive_fallback_keeps_real_citation() -> None:
    result = _extractive_answer([_evidence()])

    assert result.model_name == "retrieval-fallback"
    assert "[c1]" in result.answer
