import hashlib
import io
import uuid
from pathlib import Path

from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentChunk, DocumentFact, IngestionStatus
from app.services.document_ingestion_service import ingest_document
from app.services.retrieval_service import search_document_chunks


def test_real_embedding_schedule_retrieval(
    db_session, isolated_project_and_contract
):
    project = isolated_project_and_contract["project"]
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "synthetic_project_evidence"
        / "baseline_schedule.xlsx"
    )
    file_bytes = fixture_path.read_bytes()
    document_id = uuid.uuid4()

    document = Document(
        id=document_id,
        project_id=project.id,
        contract_id=None,
        document_type="BASELINE_SCHEDULE",
        document_name="Temporary Schedule Retrieval Evaluation",
        source_filename=f"rag-eval-{document_id.hex}.xlsx",
        file_extension="xlsx",
        mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        file_size_bytes=len(file_bytes),
        sha256_hash=hashlib.sha256(file_bytes).hexdigest(),
        ingestion_status=IngestionStatus.PENDING,
        source_system="TEST",
    )

    db_session.add(document)
    db_session.commit()

    cases = [
    (
        "What was the planned progress at the end of June 2026?",
        "2026-06-30",
        "Planned Percentage: 22",
    ),
    (
        "What was the planned progress at the end of September 2026?",
        "2026-09-30",
        "Planned Percentage: 66",
    ),
    (
        "What was the planned completion date?",
        "2026-11-30",
        "Planned Percentage: 100",
    ),
    (
        "What was the planned percentage on 30 June 2026?",
        "2026-06-30",
        "Planned Percentage: 22",
    ),
    (
        "When was planned progress 22 percent?",
        "2026-06-30",
        "Planned Percentage: 22",
    ),
    (
        "When was the project planned to reach 100%?",
        "2026-11-30",
        "Planned Percentage: 100",
    ),
    ]

    try:
        ingest_document(
            db=db_session,
            user_id=None,
            document_id=document_id,
            file_stream=io.BytesIO(file_bytes),
        )

        print("\nREAL-EMBEDDING SCHEDULE RETRIEVAL")
        for question, expected_date, expected_value in cases:
            results = search_document_chunks(
                db=db_session,
                query_text=question,
                project_id=project.id,
                limit=10,
            )

            expected_rank = None
            print(f"\nQuestion: {question}")

            for rank, result in enumerate(results, start=1):
                content = result["content"]
                expected = (
                    expected_date in content
                    and expected_value in content
                )

                if expected and expected_rank is None:
                    expected_rank = rank

                print(
                    f"rank={rank}, "
                    f"distance={result['cosine_distance']:.4f}, "
                    f"expected={expected}, "
                    f"content={content!r}"
                )

            print(f"Expected evidence rank: {expected_rank or 'NOT FOUND'}")

        # This is a diagnostic test: ranking is measured, not asserted.
        # We will use the actual results to define appropriate quality gates.

    finally:
        db_session.rollback()

        db_session.query(AuditLog).filter(
            AuditLog.entity_name == "Document",
            AuditLog.entity_id == document_id,
        ).delete(synchronize_session=False)

        db_session.query(DocumentFact).filter(
            DocumentFact.document_id == document_id
        ).delete(synchronize_session=False)

        db_session.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).update(
            {DocumentChunk.parent_chunk_id: None},
            synchronize_session=False,
        )

        db_session.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).delete(synchronize_session=False)

        db_session.query(Document).filter(
            Document.id == document_id
        ).delete(synchronize_session=False)

        db_session.commit()
