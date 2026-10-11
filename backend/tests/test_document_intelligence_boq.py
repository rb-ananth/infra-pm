import pytest
pytestmark = pytest.mark.golden

import os
import json
import uuid
import pytest
from decimal import Decimal
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.project import Project
from app.models.document import Document, DocumentFact, DocumentChunk, ValidationStatus
from app.models.boq_item import BoqItem
from app.models.measurement import Measurement
from app.core.config import settings
from app.services.document_intelligence_service import extract_boq_facts

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.models.audit_log import AuditLog

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
def client():
    with TestClient(app) as c:
        yield c

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

def get_token(client, email, password):
    response = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    return response.json()["access_token"]

def test_boq_extraction_golden_dataset(db_session, client, managed_docs, isolated_project_and_contract):
    token = get_token(client, "pm@infrapm.gov", "PM@123")

    # Take canonical snapshots to ensure no changes
    before_boq = [b.id for b in db_session.query(BoqItem).all()]
    before_meas = [m.id for m in db_session.query(Measurement).all()]

    # Register and ingest document
    xlsx_path = os.path.join(os.path.dirname(__file__), "fixtures/synthetic_project_evidence/approved_boq.xlsx")
    with open(xlsx_path, "rb") as f:
        file_bytes = f.read()

    res_reg = client.post(
        "/api/v1/documents/",
        data={"project_id": str(isolated_project_and_contract['project'].id), "document_type": "BOQ", "document_name": "Test BOQ Extraction"},
        files={"file": ("approved_boq.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {token}"}
    )
    doc_id = res_reg.json()["id"]
    managed_docs.append(doc_id)

    res_ingest = client.post(
        f"/api/v1/documents/{doc_id}/ingest",
        files={"file": ("approved_boq.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_ingest.status_code == 200

    # Run BOQ Extraction
    res_extract = client.post(
        f"/api/v1/documents/{doc_id}/intelligence/boq/extract",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_extract.status_code == 200
    summary = res_extract.json()

    print("\nBOQ EXTRACTION SUMMARY:", summary)

    assert summary["valid_items"] == 10
    assert summary["validation_errors"] == 0
    assert summary["source_discrepancies"] == 0
    assert summary["facts_extracted"] == 70  # 10 items * 7 fields

    facts = db_session.query(DocumentFact).filter_by(document_id=doc_id, fact_type="BOQ").all()
    assert len(facts) == 70

    # 1. Extraction of 10 items, 2. Provenance, 3. Decimal Normalization
    pt_amount = None
    for fact in facts:
        assert fact.validation_status == ValidationStatus.VALID
        assert fact.normalized_value is not None
        assert "Sheet BOQ Items Row" in fact.source_reference
        if fact.field_name == "item_code":
            assert fact.metadata_json["boq_item_code"] == fact.value
        if fact.metadata_json["boq_item_code"] == "PT-01" and fact.field_name == "source_amount":
            pt_amount = fact.normalized_value

    assert pt_amount == "4500000.00"

    # 8. Idempotent repeated extraction
    res_extract_2 = client.post(
        f"/api/v1/documents/{doc_id}/intelligence/boq/extract",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_extract_2.status_code == 200
    summary_2 = res_extract_2.json()
    assert summary_2["valid_items"] == 10

    facts_2 = db_session.query(DocumentFact).filter_by(document_id=doc_id, fact_type="BOQ").all()
    assert len(facts_2) == 70

    # Verify IDs are preserved (Idempotent)
    original_ids = {f.id for f in facts}
    new_ids = {f.id for f in facts_2}
    assert original_ids == new_ids

    # 12. Canonical project/contract/BOQ data remaining unchanged
    after_boq = [b.id for b in db_session.query(BoqItem).all()]
    after_meas = [m.id for m in db_session.query(Measurement).all()]
    assert before_boq == after_boq
    assert before_meas == after_meas

def test_boq_extraction_edge_cases(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")

    doc = Document(
        document_type="BOQ",
        document_name="Test BOQ Edge Cases",
        sha256_hash="fakehashboq",
        ingestion_status="COMPLETED",
        source_filename="fake.xlsx",
        file_extension="xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size_bytes=100,
        source_system="MANUAL_UPLOAD"
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    chunk_content = [
        "ITEM CODE | ITEM NUMBER | DESC | UNIT | QTY | RATE | AMOUNT", # header
        "VALID-01 | 1.1 | Valid Item | CUM | 10.000 | 100.00 | 1000.00",
        "DISCREP-01 | 1.2 | Bad Calc | CUM | 10.000 | 100.00 | 1100.00", # source_discrepancies (4)
        "MISSING-01 | 1.3 | Missing Qty | CUM |  | 100.00 | 1000.00", # Missing field (5)
        "PRECISION-01 | 1.4 | Bad Qty Prec | CUM | 10.0001 | 100.00 | 1000.00", # Excess precision (6)
        "PRECISION-02 | 1.5 | Bad Rate Prec | CUM | 10.000 | 100.001 | 1000.00", # Excess precision (6)
        "DUP-01 | 1.6 | Dup Code | CUM | 10.000 | 100.00 | 1000.00",
        "DUP-01 | 1.7 | Dup Code | CUM | 10.000 | 100.00 | 1000.00", # Duplicate item codes (7)
        "DUP-02 | 1.8 | Dup Num | CUM | 10.000 | 100.00 | 1000.00",
        "DUP-03 | 1.8 | Dup Num | CUM | 10.000 | 100.00 | 1000.00", # Duplicate item numbers (7)
        "NEG-01 | 1.9 | Negative Qty | CUM | -10.000 | 100.00 | 1000.00", # Invalid negative
        "MALFORMED-01 | 1.10 | Non Numeric | CUM | xyz | 100.00 | 1000.00", # Invalid numeric
    ]

    for i, content in enumerate(chunk_content):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=content,
            content_hash=f"hash{i}",
            sheet_name="BOQ Items",
            row_start=i+1,
            row_end=i+1
        )
        db_session.add(chunk)
    db_session.commit()

    res = client.post(f"/api/v1/documents/{doc.id}/intelligence/boq/extract", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    summary = res.json()

    assert summary["rows_processed"] == 11 # 12 rows minus 1 header
    assert summary["valid_items"] == 2 # VALID-01 and DISCREP-01 are the only structurally valid items
    assert summary["validation_errors"] == 9 # the rest are invalid
    assert summary["source_discrepancies"] == 1 # DISCREP-01
    assert summary["facts_extracted"] == 11 * 7 # 77 facts

    facts = db_session.query(DocumentFact).filter_by(document_id=doc.id).all()

    # Check Discrepancy (Only source_amount should be CONFLICT)
    discrep_facts = [f for f in facts if f.metadata_json.get("boq_item_code") == "DISCREP-01"]
    for f in discrep_facts:
        if f.field_name == "source_amount":
            assert f.validation_status == ValidationStatus.CONFLICT
            assert f.metadata_json["discrepancy"]["difference"] == "100.00"
        else:
            assert f.validation_status == ValidationStatus.VALID

    # Check Precision rejection
    prec_facts = [f for f in facts if f.metadata_json.get("boq_item_code") == "PRECISION-01"]
    for f in prec_facts:
        assert f.validation_status == ValidationStatus.INVALID
        assert "Quantity has more than 3 decimal places" in f.metadata_json["errors"]

    # Check Missing field
    miss_facts = [f for f in facts if f.metadata_json.get("boq_item_code") == "MISSING-01"]
    for f in miss_facts:
        assert f.validation_status == ValidationStatus.INVALID
        assert "Missing quantity" in f.metadata_json["errors"]

    # Idempotent normalization update regression
    # Transition MISSING-01 to valid by patching chunk and re-running
    miss_chunk = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id, DocumentChunk.content.contains("MISSING-01")).first()
    miss_chunk.content = "MISSING-01 | 1.3 | Missing Qty | CUM | 10.000 | 100.00 | 1000.00"
    db_session.commit()

    res_re = client.post(f"/api/v1/documents/{doc.id}/intelligence/boq/extract", headers={"Authorization": f"Bearer {token}"})
    assert res_re.status_code == 200

    miss_facts_re = db_session.query(DocumentFact).filter(DocumentFact.document_id == doc.id).filter(DocumentFact.value == "MISSING-01").all()
    assert miss_facts_re[0].validation_status == ValidationStatus.VALID

    miss_qty_fact = db_session.query(DocumentFact).filter(DocumentFact.document_id == doc.id, DocumentFact.document_chunk_id == miss_chunk.id, DocumentFact.field_name == "quantity").first()
    assert miss_qty_fact.normalized_value == "10.000"
    assert miss_qty_fact.validation_status == ValidationStatus.VALID


def test_boq_extraction_auth_and_state(db_session, client, managed_docs):
    token_pm = get_token(client, "pm@infrapm.gov", "PM@123")
    token_viewer = get_token(client, "viewer@infrapm.gov", "View@123")

    doc = Document(
        document_type="CONTRACT", # Incompatible (9)
        document_name="Test Incompatible",
        sha256_hash="fake",
        ingestion_status="COMPLETED",
        source_filename="fake.pdf",
        file_extension="pdf",
        mime_type="application/pdf",
        file_size_bytes=100
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    # 10. Unauthorized requests
    res1 = client.post(f"/api/v1/documents/{doc.id}/intelligence/boq/extract", headers={"Authorization": f"Bearer {token_viewer}"})
    assert res1.status_code == 403

    # 9. Incompatible document type
    res2 = client.post(f"/api/v1/documents/{doc.id}/intelligence/boq/extract", headers={"Authorization": f"Bearer {token_pm}"})

    assert res2.status_code == 400
    assert "requires BOQ document" in res2.json()["detail"]

    # Change to BOQ but PENDING
    doc.document_type = "BOQ"
    doc.ingestion_status = "PENDING"
    db_session.commit()

    # 9. Incompatible ingestion state
    res3 = client.post(f"/api/v1/documents/{doc.id}/intelligence/boq/extract", headers={"Authorization": f"Bearer {token_pm}"})
    assert res3.status_code == 400
    assert "requires COMPLETED ingestion" in res3.json()["detail"]

def test_transaction_rollback_on_failure(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")

    doc = Document(
        document_type="BOQ",
        document_name="Test Rollback",
        sha256_hash="fakehashrollback",
        ingestion_status="COMPLETED",
        source_filename="fake.xlsx",
        file_extension="xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size_bytes=100
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    chunk = DocumentChunk(
        document_id=doc.id, chunk_index=0, content="CODE1 | 1.1 | Desc | CUM | 10 | 100 | 1000", content_hash="hash", sheet_name="BOQ Items", row_start=1, row_end=1
    )
    db_session.add(chunk)
    db_session.commit()

    # 11. Transaction rollback on extraction failure
    # Force a failure during flush by mocking
    from unittest.mock import patch
    with patch("sqlalchemy.orm.Session.flush", side_effect=Exception("Simulated DB failure")):

        with pytest.raises(Exception) as exc:
            extract_boq_facts(db=db_session, document_id=doc.id, current_user=None)

        assert "Simulated DB failure" in str(exc.value)

        facts = db_session.query(DocumentFact).filter_by(document_id=doc.id).all()
        assert len(facts) == 0 # Rollback preserved empty state
