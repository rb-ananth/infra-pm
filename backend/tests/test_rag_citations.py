
import pytest
from app.services.rag_service import validate_answer_citations
from unittest.mock import Mock


@pytest.fixture
def db_session():
    """Provide a lightweight session substitute for the autouse fixture."""
    return Mock()

@pytest.mark.parametrize(
    ("answer", "source_count", "expected"),
    [
        ("The work is pending. [1]", 2, True),
        ("The contract states this. [1] Further details are in [2].", 2, True),
        ("The work is pending. [3]", 2, False),
        ("The work is pending.", 2, False),
        ("No conclusion can be drawn from the available evidence.", 2, False),
        ("The work is pending. [0]", 2, False),
        ("The work is pending. [1]", 0, False),
    ],
)
def test_validate_answer_citations(answer, source_count, expected):
    assert validate_answer_citations(answer, source_count) is expected


import uuid
from unittest.mock import Mock

from app.services.rag_service import answer_project_question


def make_retrieved_match():
    return {
        "chunk_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
        "document_name": "Progress Report",
        "source_filename": "progress.pdf",
        "content": "The foundation work remains pending.",
        "page_number": 2,
        "sheet_name": None,
        "row_start": None,
        "row_end": None,
        "section": "Progress",
        "clause_reference": None,
        "cosine_distance": 0.1,
    }


def mock_llm_response(monkeypatch, answer):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": answer}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "app.services.rag_service.httpx.Client",
        FakeClient,
    )


def test_rag_service_rejects_unknown_citation(monkeypatch):
    project_id = uuid.uuid4()
    match = make_retrieved_match()

    monkeypatch.setattr(
        "app.services.rag_service.search_document_chunks",
        lambda **kwargs: [match],
    )
    mock_llm_response(
        monkeypatch,
        "The foundation work remains pending. [7]",
    )

    result = answer_project_question(
        db=Mock(),
        project_id=project_id,
        question="What work is pending?",
    )

    assert result["insufficient_evidence"] is True
    assert "reliably cited answer" in result["answer"]
    assert len(result["sources"]) == 1

def test_rag_service_accepts_valid_citation(monkeypatch):
    project_id = uuid.uuid4()
    match = make_retrieved_match()

    monkeypatch.setattr(
        "app.services.rag_service.search_document_chunks",
        lambda **kwargs: [match],
    )
    mock_llm_response(
        monkeypatch,
        "The foundation work remains pending. [1]",
    )

    result = answer_project_question(
        db=Mock(),
        project_id=project_id,
        question="What work is pending?",
    )

    assert result["insufficient_evidence"] is False
    assert result["answer"] == (
        "The foundation work remains pending. [1]"
    )
    assert len(result["sources"]) == 1
def test_rag_service_rejects_weak_retrieval_evidence(monkeypatch):
    project_id = uuid.uuid4()
    match = make_retrieved_match()
    match["cosine_distance"] = 0.9

    monkeypatch.setattr(
        "app.services.rag_service.search_document_chunks",
        lambda **kwargs: [match],
    )

    def unexpected_llm_call(*args, **kwargs):
        raise AssertionError(
            "LLM must not be called when all evidence is too weak."
        )

    monkeypatch.setattr(
        "app.services.rag_service.httpx.Client",
        unexpected_llm_call,
    )

    monkeypatch.setattr(
        "app.services.rag_service.settings.RAG_MAX_COSINE_DISTANCE",
        0.35,
        raising=False,
    )

    result = answer_project_question(
        db=Mock(),
        project_id=project_id,
        question="What is the contractual completion date?",
    )

    assert result["insufficient_evidence"] is True
    assert result["sources"] == []
    assert "sufficiently relevant evidence" in result["answer"]


def test_rag_service_rejects_unrelated_schedule_evidence(monkeypatch):
    project_id = uuid.uuid4()
    match = make_retrieved_match()
    match["content"] = (
        "Worksheet: S-Curve Data\n"
        "Columns: Date | Planned Percentage\n"
        "Excel row 4: Date: 2026-06-30 | "
        "Planned Percentage: 22"
    )
    match["document_name"] = "Baseline Schedule"
    match["source_filename"] = "baseline_schedule.xlsx"
    match["cosine_distance"] = 0.50

    monkeypatch.setattr(
        "app.services.rag_service.search_document_chunks",
        lambda **kwargs: [match],
    )

    def unexpected_llm_call(*args, **kwargs):
        raise AssertionError(
            "LLM must not be called when evidence is unrelated."
        )

    monkeypatch.setattr(
        "app.services.rag_service.httpx.Client",
        unexpected_llm_call,
    )
    monkeypatch.setattr(
        "app.services.rag_service.settings.RAG_MAX_COSINE_DISTANCE",
        0.55,
        raising=False,
    )

    result = answer_project_question(
        db=Mock(),
        project_id=project_id,
        question="What is the contractor's tax registration number?",
    )

    assert result["insufficient_evidence"] is True
    assert result["sources"] == []

def test_tax_identifier_evidence_matches_question_intent():
    from app.services.rag_service import (
        evidence_matches_question_intent,
    )

    assert evidence_matches_question_intent(
        "What is the contractor's tax registration number?",
        "Contractor GSTIN: 30ABCDE1234F1Z5",
    )

    assert not evidence_matches_question_intent(
        "What is the contractor's tax registration number?",
        "Worksheet: S-Curve Data. Date: 2026-06-30. "
        "Planned Percentage: 22.",
    )