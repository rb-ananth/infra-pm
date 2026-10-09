import pytest
import uuid
import json
from decimal import Decimal
from datetime import date
from sqlalchemy.orm import Session
from app.models.document import Document, DocumentChunk, DocumentFact, DocumentType, IngestionStatus
from app.models.project import Project
from app.models.evm import EVMBaseline


def get_token(client, email, password):
    response = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    return response.json()["access_token"]


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.config import settings
from app.models.audit_log import AuditLog
from fastapi.testclient import TestClient

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def managed_docs(db_session):
    doc_ids = []
    yield doc_ids
    if doc_ids:
        db_session.query(AuditLog).filter(
            AuditLog.entity_name == "Document",
            AuditLog.entity_id.in_(doc_ids)
        ).delete(synchronize_session=False)
        db_session.query(DocumentFact).filter(DocumentFact.document_id.in_(doc_ids)).delete(synchronize_session=False)
        db_session.query(DocumentChunk).filter(DocumentChunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
        db_session.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)
        db_session.commit()

def test_evm_extraction_golden_dataset(db_session: Session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")

    project = db_session.query(Project).filter(Project.code == "PWD-2026-001").first()
    assert project

    with open("tests/fixtures/golden_project/v1_ground_truth.json", "r") as f:
        ground_truth = json.load(f)

    for checkpoint in ground_truth["evm"]["checkpoints"]:
        cp_date = checkpoint["date"]

        doc = Document(
            document_type="PROGRESS_REPORT",
            document_name=f"Progress-Report-{cp_date}",
            sha256_hash=f"fakehash{cp_date}",
            ingestion_status="COMPLETED",
            source_filename=f"progress_report_{cp_date}.pdf",
            file_extension="pdf",
            mime_type="application/pdf",
            file_size_bytes=100,
            source_system="MANUAL_UPLOAD",
            project_id=project.id
        )
        db_session.add(doc)
        db_session.commit()
        managed_docs.append(str(doc.id))

        # We need the real text from the PDF file to test the regexes properly,
        # or we can mock the text since we've already seen it.
        # Let's use the actual text pattern from the PDF!
        text = f"MONTHL Y PROGRESS REPORT: {cp_date}\nExecutive Summary\nEVM Snapshot\nPlanned Value (PV): {checkpoint['pv']}\nEarned Value (EV): {checkpoint['ev']}\nActual Cost (AC): {checkpoint['ac']}"

        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            content=text,
            content_hash=f"hash{cp_date}",
            page_number=1,
            row_start=0,
            row_end=0
        )
        db_session.add(chunk)
        db_session.commit()

        res = client.post(f"/api/v1/documents/{doc.id}/intelligence/evm/extract", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        summary = res.json()

        assert summary["facts_extracted"] == 1
        assert summary["valid_facts"] == 1
        assert summary["validation_errors"] == 0
        assert summary["reconciliation_matches"] == 1

        # Test idempotency
        res = client.post(f"/api/v1/documents/{doc.id}/intelligence/evm/extract", headers={"Authorization": f"Bearer {token}"})
        summary2 = res.json()
        assert summary2 == summary

def test_evm_extraction_edge_cases(db_session: Session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    project = db_session.query(Project).filter(Project.code == "PWD-2026-001").first()

    doc = Document(
        document_type="PROGRESS_REPORT",
        document_name="Test Edge",
        sha256_hash="fakehashedge",
        ingestion_status="COMPLETED",
        source_filename="fake.pdf",
        file_extension="pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        source_system="MANUAL_UPLOAD",
        project_id=project.id
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    text = "MONTHL Y PROGRESS REPORT: 2026-04-30\nPlanned Value (PV): 24250000.001\nEarned Value (EV): -100\nActual Cost (AC): \n"

    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content=text,
        content_hash="hashedge",
        page_number=1,
        row_start=0,
        row_end=0
    )
    db_session.add(chunk)
    db_session.commit()

    res = client.post(f"/api/v1/documents/{doc.id}/intelligence/evm/extract", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    summary = res.json()

    assert summary["validation_errors"] == 1
    assert summary["valid_facts"] == 0
    assert summary["reconciliation_mismatches"] == 1

    fact = db_session.query(DocumentFact).filter(DocumentFact.document_id == doc.id).first()
    errs = fact.metadata_json["errors"]
    assert any("PV precision exceeds" in e for e in errs)
    print("ERRORS:", errs); assert any("Negative EV" in e for e in errs)
    assert any("Missing Actual Cost" in e for e in errs)

def test_evm_transaction_rollback_on_failure(db_session: Session, client, managed_docs, monkeypatch):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    project = db_session.query(Project).filter(Project.code == "PWD-2026-001").first()

    doc = Document(
        document_type="PROGRESS_REPORT",
        document_name="Test Fail",
        sha256_hash="fakehashfail",
        ingestion_status="COMPLETED",
        source_filename="fail.pdf",
        file_extension="pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        source_system="MANUAL_UPLOAD",
        project_id=project.id
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    text = "MONTHL Y PROGRESS REPORT: 2026-04-30\nPlanned Value (PV): 24250000.00\nEarned Value (EV): 9675000.00\nActual Cost (AC): 9675000.00"
    chunk = DocumentChunk(
        document_id=doc.id, chunk_index=0, content=text,
        content_hash="hashfail", page_number=1, row_start=0, row_end=0
    )
    db_session.add(chunk)
    db_session.commit()

    import app.services.audit_service
    def mock_add_audit_log(*args, **kwargs):
        raise ValueError("Simulated audit log failure")
    monkeypatch.setattr(app.services.audit_service, "add_audit_log", mock_add_audit_log)

    with pytest.raises(ValueError, match="Simulated audit log failure"):
        client.post(f"/api/v1/documents/{doc.id}/intelligence/evm/extract", headers={"Authorization": f"Bearer {token}"})

    assert db_session.query(DocumentFact).filter(DocumentFact.document_id == doc.id).count() == 0

