
import io
import uuid
import hashlib
import pytest
from app.core.config import settings
from app.models.document import Document, DocumentChunk, IngestionStatus
from app.services.document_ingestion_service import ingest_document
from app.services.retrieval_service import search_document_chunks
from app.models.audit_log import AuditLog

def test_ingestion_embeddings_and_project_scoped_retrieval(
    db_session, isolated_project_and_contract
):
    project = isolated_project_and_contract["project"]
    contract = isolated_project_and_contract["contract"]

    # Unique content prevents collisions with existing document hashes.
    content = (
        "Infrastructure project test evidence. "
        "Pending work includes foundation excavation and reinforcement. "
        f"Test reference: {uuid.uuid4()}"
    )

    # Use a PDF so the real parser and embedding service are exercised.
    from pathlib import Path
    import hashlib

    pdf_path = (
        Path(__file__).parent
        / "fixtures"
        / "synthetic_project_evidence"
        / "contract_agreement.pdf"
    )

    # Append a unique PDF comment without changing the existing page content.
    pdf_bytes = (
        pdf_path.read_bytes()
        + f"\n% RAG test {uuid.uuid4()}\n".encode("utf-8")
    )
    doc = Document(
        project_id=project.id,
        contract_id=contract.id,
        document_type="PROGRESS_REPORT",
        document_name="RAG Integration Test",
        source_filename=f"rag-test-{uuid.uuid4()}.pdf",
        file_extension="pdf",
        mime_type="application/pdf",
        file_size_bytes=len(pdf_bytes),
        sha256_hash=hashlib.sha256(pdf_bytes).hexdigest(),
        ingestion_status=IngestionStatus.PENDING,
        source_system="TEST",
    )
    db_session.add(doc)
    db_session.commit()

    try:
        ingest_document(
            db=db_session,
            user_id=None,
            document_id=doc.id,
            file_stream=io.BytesIO(pdf_bytes),
        )

        db_session.expire_all()
        stored_chunks = (
            db_session.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc.id)
            .all()
        )

        assert stored_chunks, "Ingestion should create chunks"
        assert all(chunk.embedding is not None for chunk in stored_chunks)
        assert all(len(chunk.embedding) == 1024 for chunk in stored_chunks)

        results = search_document_chunks(
            db=db_session,
            query_text="What work is pending on the project?",
            project_id=project.id,
            limit=5,
        )

        assert results, "Retrieval should return relevant project chunks"
        assert any(result["document_id"] == str(doc.id) for result in results)

        for result in results:
            assert result["document_id"]
            assert result["content"]
            assert "cosine_distance" in result
            assert result["document_name"]


    finally:
        from app.models.document import DocumentFact

        doc_id = doc.id
        db_session.rollback()

        db_session.query(AuditLog).filter(
            AuditLog.entity_name == "Document",
            AuditLog.entity_id == doc_id,
        ).delete(synchronize_session=False)

        db_session.query(DocumentFact).filter(
            DocumentFact.document_id == doc_id
        ).delete(synchronize_session=False)

        db_session.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc_id
        ).update(
            {DocumentChunk.parent_chunk_id: None},
            synchronize_session=False,
        )

        db_session.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc_id
        ).delete(synchronize_session=False)

        db_session.query(Document).filter(
            Document.id == doc_id
        ).delete(synchronize_session=False)

        db_session.commit()

def test_retrieval_excludes_documents_from_other_projects(
    db_session, isolated_project_and_contract, monkeypatch
):
    import hashlib
    from datetime import date
    from decimal import Decimal

    from app.models.project import Project
    from app.models.user import User
    from app.models.department import Department

    target_project = isolated_project_and_contract["project"]
    target_contract = isolated_project_and_contract["contract"]

    # Reuse valid foreign keys from the isolated fixture.
    manager = db_session.query(User).filter(
        User.id == target_project.pm_id
    ).one()
    department = db_session.query(Department).filter(
        Department.id == target_project.dept_id
    ).one()

    unrelated_project = Project(
        code=f"RAG-ISOLATION-{uuid.uuid4().hex[:12]}",
        name="Unrelated RAG Isolation Project",
        dept_id=department.id,
        pm_id=manager.id,
        status="Proposed",
        total_estimated_cost=Decimal("100000.00"),
        start_date=date(2026, 1, 1),
        expected_completion=date(2027, 1, 1),
    )
    db_session.add(unrelated_project)
    db_session.flush()

    target_doc = Document(
        project_id=target_project.id,
        contract_id=target_contract.id,
        document_type="PROGRESS_REPORT",
        document_name="Target Project Evidence",
        source_filename=f"target-{uuid.uuid4().hex}.txt",
        file_extension="txt",
        mime_type="text/plain",
        file_size_bytes=10,
        sha256_hash=hashlib.sha256(
            f"target-{uuid.uuid4()}".encode()
        ).hexdigest(),
        ingestion_status=IngestionStatus.COMPLETED,
        source_system="TEST",
    )
    unrelated_doc = Document(
        project_id=unrelated_project.id,
        contract_id=None,
        document_type="PROGRESS_REPORT",
        document_name="Unrelated Project Evidence",
        source_filename=f"unrelated-{uuid.uuid4().hex}.txt",
        file_extension="txt",
        mime_type="text/plain",
        file_size_bytes=10,
        sha256_hash=hashlib.sha256(
            f"unrelated-{uuid.uuid4()}".encode()
        ).hexdigest(),
        ingestion_status=IngestionStatus.COMPLETED,
        source_system="TEST",
    )

    db_session.add_all([target_doc, unrelated_doc])
    db_session.flush()

    # Use valid-sized vectors so this test does not call Ollama.
    vector = [0.01] * 1024

    target_chunk = DocumentChunk(
        document_id=target_doc.id,
        chunk_index=0,
        content="Target project foundation progress evidence.",
        content_hash=hashlib.sha256(b"target chunk").hexdigest(),
        embedding=vector,
    )
    unrelated_chunk = DocumentChunk(
        document_id=unrelated_doc.id,
        chunk_index=0,
        content="Confidential unrelated project evidence.",
        content_hash=hashlib.sha256(b"unrelated chunk").hexdigest(),
        embedding=vector,
    )

    db_session.add_all([target_chunk, unrelated_chunk])
    db_session.commit()

    # Replace only the embedding call; exercise the real retrieval SQL.
    monkeypatch.setattr(
        "app.services.retrieval_service.generate_embedding",
        lambda query: vector,
    )

    try:
        results = search_document_chunks(
            db=db_session,
            query_text="Find project progress evidence",
            project_id=target_project.id,
            limit=20,
        )

        returned_document_ids = {
            result["document_id"] for result in results
        }

        assert str(target_doc.id) in returned_document_ids
        assert str(unrelated_doc.id) not in returned_document_ids

    finally:
        # Remove only records created by this test.
        from app.models.document import DocumentFact

        db_session.rollback()

        document_ids = [target_doc.id, unrelated_doc.id]
        chunk_ids = [target_chunk.id, unrelated_chunk.id]

        db_session.query(DocumentFact).filter(
            DocumentFact.document_id.in_(document_ids)
        ).delete(synchronize_session=False)

        db_session.query(DocumentChunk).filter(
            DocumentChunk.parent_chunk_id.in_(chunk_ids)
        ).update(
            {DocumentChunk.parent_chunk_id: None},
            synchronize_session=False,
        )

        db_session.query(DocumentChunk).filter(
            DocumentChunk.id.in_(chunk_ids)
        ).delete(synchronize_session=False)

        db_session.query(Document).filter(
            Document.id.in_(document_ids)
        ).delete(synchronize_session=False)

        db_session.query(Project).filter(
            Project.id == unrelated_project.id
        ).delete(synchronize_session=False)

        db_session.commit()

def test_retrieval_orders_chunks_by_cosine_distance(
    db_session, isolated_project_and_contract, monkeypatch
):
    import hashlib

    project = isolated_project_and_contract["project"]
    contract = isolated_project_and_contract["contract"]

    query_vector = [0.0] * 1024
    query_vector[0] = 1.0

    close_vector = query_vector.copy()

    distant_vector = [0.0] * 1024
    distant_vector[1] = 1.0

    created_document_ids = []
    created_chunk_ids = []

    try:
        for name, content, vector in [
            (
                "Relevant contract evidence",
                "Contract completion clause",
                close_vector,
            ),
            (
                "Less relevant RA evidence",
                "RA bill payment details",
                distant_vector,
            ),
        ]:
            document = Document(
                project_id=project.id,
                contract_id=contract.id,
                document_type="CONTRACT",
                document_name=name,
                source_filename=f"{uuid.uuid4()}.txt",
                file_extension="txt",
                mime_type="text/plain",
                file_size_bytes=len(content),
                sha256_hash=hashlib.sha256(
                    str(uuid.uuid4()).encode()
                ).hexdigest(),
                ingestion_status=IngestionStatus.COMPLETED,
                source_system="TEST",
            )
            db_session.add(document)
            db_session.flush()
            created_document_ids.append(document.id)

            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content=content,
                content_hash=hashlib.sha256(
                    content.encode()
                ).hexdigest(),
                embedding=vector,
            )
            db_session.add(chunk)
            db_session.flush()
            created_chunk_ids.append(chunk.id)

        db_session.commit()

        monkeypatch.setattr(
            "app.services.retrieval_service.generate_embedding",
            lambda query: query_vector,
        )

        results = search_document_chunks(
            db=db_session,
            query_text="What is the contract completion clause?",
            project_id=project.id,
            limit=20,
        )

        returned_test_results = [
            result
            for result in results
            if result["document_id"] in {
                str(document_id)
                for document_id in created_document_ids
            }
        ]

        assert len(returned_test_results) == 2
        assert (
            returned_test_results[0]["document_name"]
            == "Relevant contract evidence"
        )
        assert (
            returned_test_results[0]["cosine_distance"]
            < returned_test_results[1]["cosine_distance"]
        )

    finally:
        from app.models.document import DocumentFact

        db_session.rollback()

        db_session.query(DocumentFact).filter(
            DocumentFact.document_id.in_(created_document_ids)
        ).delete(synchronize_session=False)

        db_session.query(DocumentChunk).filter(
            DocumentChunk.parent_chunk_id.in_(created_chunk_ids)
        ).update(
            {DocumentChunk.parent_chunk_id: None},
            synchronize_session=False,
        )

        db_session.query(DocumentChunk).filter(
            DocumentChunk.id.in_(created_chunk_ids)
        ).delete(synchronize_session=False)

        db_session.query(Document).filter(
            Document.id.in_(created_document_ids)
        ).delete(synchronize_session=False)

        db_session.commit()
def test_ingestion_stores_context_rich_schedule_chunks(
    db_session, isolated_project_and_contract
):
    from pathlib import Path

    project = isolated_project_and_contract["project"]
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "synthetic_project_evidence"
        / "baseline_schedule.xlsx"
    )

    file_bytes = fixture_path.read_bytes()
    document = Document(
        project_id=project.id,
        contract_id=None,
        document_type="BASELINE_SCHEDULE",
        document_name="Schedule Parser Regression Test",
        source_filename=f"schedule-{uuid.uuid4().hex}.xlsx",
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
    document_id = document.id

    try:
        ingest_document(
            db=db_session,
            user_id=None,
            document_id=document_id,
            file_stream=io.BytesIO(file_bytes),
        )

        chunks = (
            db_session.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        assert len(chunks) == 2
        assert all(chunk.embedding is not None for chunk in chunks)
        assert all(len(chunk.embedding) == 1024 for chunk in chunks)

        combined_content = "\n".join(chunk.content for chunk in chunks)

        assert "Columns: Date | Planned Percentage" in combined_content
        assert "Date: 2026-06-30" in combined_content
        assert "Planned Percentage: 22" in combined_content
        assert "Date: 2026-11-30" in combined_content
        assert "Planned Percentage: 100" in combined_content

        assert chunks[0].row_start == 2
        assert chunks[0].row_end == 6
        assert chunks[1].row_start == 7
        assert chunks[1].row_end == 9

    finally:
        from app.models.document import DocumentFact

        db_session.rollback()

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
