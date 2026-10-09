import json
import os
import uuid
import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.document import Document, DocumentChunk, DocumentFact, DocumentType, IngestionStatus, ValidationStatus
from app.models.contract import Contract
from app.models.boq_item import BoqItem
from app.models.measurement import Measurement
from app.models.audit_log import AuditLog
from app.models.ra_bill import RABill, RABillItem, RABillMeasurement

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_token(client, email, password):
    res = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    return res.json()["access_token"]

@pytest.fixture
def managed_docs(db_session):
    docs = []
    yield docs
    for doc_id in docs:
        db_session.query(AuditLog).filter(AuditLog.entity_name == "Document", AuditLog.entity_id == doc_id).delete()
        db_session.query(DocumentFact).filter(DocumentFact.document_id == doc_id).delete()
        db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
        db_session.query(Document).filter(Document.id == doc_id).delete()
    db_session.commit()

def test_ra_bill_extraction_golden_dataset(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    contract = db_session.query(Contract).filter(Contract.contract_number == "CNT-PWD-2026-001").first()

    before_boq = [b.id for b in db_session.query(BoqItem).all()]
    before_meas = [m.id for m in db_session.query(Measurement).all()]
    before_rabill = [b.id for b in db_session.query(RABill).all()]

    xlsx_path = os.path.join(os.path.dirname(__file__), "fixtures/synthetic_project_evidence/RA-04.xlsx")
    with open(xlsx_path, "rb") as f:
        file_bytes = f.read()

    res_reg = client.post(
        "/api/v1/documents/",
        data={"document_type": "RA_BILL", "document_name": "Test RA-04 Extraction", "contract_id": str(contract.id)},
        files={"file": ("RA-04.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {token}"}
    )
    doc_id = res_reg.json()["id"]
    managed_docs.append(doc_id)

    res_ingest = client.post(
        f"/api/v1/documents/{doc_id}/ingest",
        files={"file": ("RA-04.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_ingest.status_code == 200

    res_extract = client.post(
        f"/api/v1/documents/{doc_id}/intelligence/ra-bill/extract",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_extract.status_code == 200
    summary = res_extract.json()

    assert summary["rows_processed"] == 2  # Cover row + Calculations row
    assert summary["valid_facts"] == 2
    assert summary["reconciliation_matches"] == 2
    assert summary["reconciliation_mismatches"] == 0

    # Ensure canonical intact
    assert before_boq == [b.id for b in db_session.query(BoqItem).all()]
    assert before_meas == [m.id for m in db_session.query(Measurement).all()]
    assert before_rabill == [b.id for b in db_session.query(RABill).all()]

def test_ra_bill_extraction_edge_cases(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    contract = db_session.query(Contract).filter(Contract.contract_number == "CNT-PWD-2026-001").first()

    doc = Document(
        document_type="RA_BILL",
        document_name="Test RABill Edge Cases",
        sha256_hash="fakehashra",
        ingestion_status="COMPLETED",
        source_filename="fake.xlsx",
        file_extension="xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size_bytes=100,
        source_system="MANUAL_UPLOAD",
        contract_id=contract.id
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    chunk_content = [
        ("Cover", "Bill Number | Gross Amount | Linked Measurements | Cumulative Total"),
        ("Cover", "RA-04 | -9675000 | INVALID | "), # mismatch and neg
        ("Calculations", "Reference | Item Code | Quantity | Rate | Amount"),
        ("Calculations", "MB-2026-04-001 | EW-01 | -21500 | -450 | -9675000"), # neg, but matches reference
        ("Calculations", "MB-UNKNOWN | UNK-01 | 1 | 1 | 1"), # unknown measurement
        ("Calculations", "MB-DUP | EW-01 | 1 | 1 | 1"),
        ("Calculations", "MB-DUP | EW-01 | 1 | 1 | 1"), # duplicate
    ]

    for i, (sheet, content) in enumerate(chunk_content):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=content,
            content_hash=f"hash{i}",
            sheet_name=sheet,
            row_start=i+1,
            row_end=i+1
        )
        db_session.add(chunk)
    db_session.commit()

    res = client.post(f"/api/v1/documents/{doc.id}/intelligence/ra-bill/extract", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    summary = res.json()

    assert summary["duplicate_references"] == 2
    assert summary["unknown_links"] == 3
    assert summary["validation_errors"] > 0
    assert summary["reconciliation_mismatches"] > 0

def test_ra_bill_extraction_auth_and_state(db_session, client, managed_docs):
    token_pm = get_token(client, "pm@infrapm.gov", "PM@123")
    token_viewer = get_token(client, "viewer@infrapm.gov", "View@123")

    doc = Document(
        document_type="BOQ",
        document_name="Test Incompatible",
        sha256_hash="fake-rabill-auth",
        ingestion_status="COMPLETED",
        source_filename="fake.pdf",
        file_extension="pdf",
        mime_type="application/pdf",
        file_size_bytes=100
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    res1 = client.post(f"/api/v1/documents/{doc.id}/intelligence/ra-bill/extract", headers={"Authorization": f"Bearer {token_viewer}"})
    assert res1.status_code == 403

    res2 = client.post(f"/api/v1/documents/{doc.id}/intelligence/ra-bill/extract", headers={"Authorization": f"Bearer {token_pm}"})
    assert res2.status_code == 400

    doc.document_type = "RA_BILL"
    doc.ingestion_status = "PENDING"
    db_session.commit()

    res3 = client.post(f"/api/v1/documents/{doc.id}/intelligence/ra-bill/extract", headers={"Authorization": f"Bearer {token_pm}"})
    assert res3.status_code == 400

    doc.ingestion_status = 'COMPLETED'
    doc.contract_id = None
    db_session.commit()
    res4 = client.post(f"/api/v1/documents/{doc.id}/intelligence/ra-bill/extract", headers={"Authorization": f"Bearer {token_pm}"})
    assert res4.status_code == 400
    assert "linked contract" in res4.json()["detail"]

    # 12. Missing approved BOQ
    from app.models.contract import Contract
    from app.models.boq import Boq
    from app.models.boq_revision import BoqRevision

    contract = db_session.query(Contract).filter(Contract.contract_number == "CNT-PWD-2026-001").first()
    doc.contract_id = contract.id
    db_session.commit()

    boq = db_session.query(Boq).filter(Boq.contract_id == contract.id).first()
    revision = db_session.query(BoqRevision).filter(BoqRevision.boq_id == boq.id).first()
    original_status = revision.status
    revision.status = "Draft"
    db_session.commit()

    res5 = client.post(f"/api/v1/documents/{doc.id}/intelligence/ra-bill/extract", headers={"Authorization": f"Bearer {token_pm}"})
    assert res5.status_code == 400
    assert "does not have an approved BOQ" in res5.json()["detail"]

    revision.status = original_status
    db_session.commit()

def test_transaction_rollback_on_failure(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")

    doc = Document(
        document_type="RA_BILL",
        document_name="Test Rollback",
        sha256_hash="fakehashrabill2",
        ingestion_status="COMPLETED",
        source_filename="fake.xlsx",
        file_extension="xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size_bytes=100,
        source_system="MANUAL_UPLOAD",
        contract_id=db_session.query(Contract).first().id
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    # Use invalid document id UUID
    res = client.post(f"/api/v1/documents/{uuid.uuid4()}/intelligence/ra-bill/extract", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404
