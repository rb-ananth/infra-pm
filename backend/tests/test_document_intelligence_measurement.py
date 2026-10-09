import os


import json
import uuid
import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentFact, DocumentChunk, ValidationStatus
from app.models.boq_item import BoqItem
from app.models.measurement import Measurement
from app.models.contract import Contract
from app.core.config import settings
from app.services.document_intelligence_service import extract_measurement_facts

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

def get_token(client, username, password):
    response = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    return response.json()["access_token"]

def test_measurement_extraction_golden_dataset(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    contract = db_session.query(Contract).filter(Contract.contract_number == "CNT-PWD-2026-001").first()

    # Take canonical snapshots to ensure no changes
    before_boq = [b.id for b in db_session.query(BoqItem).all()]
    before_meas = [m.id for m in db_session.query(Measurement).all()]

    xlsx_path = os.path.join(os.path.dirname(__file__), "fixtures/synthetic_project_evidence/measurement_book.xlsx")
    with open(xlsx_path, "rb") as f:
        file_bytes = f.read()

    res_reg = client.post(
        "/api/v1/documents/",
        data={"document_type": "MEASUREMENT_BOOK", "document_name": "Test MB Extraction", "contract_id": str(contract.id)},
        files={"file": ("measurement_book.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {token}"}
    )
    doc_id = res_reg.json()["id"]
    managed_docs.append(doc_id)

    res_ingest = client.post(
        f"/api/v1/documents/{doc_id}/ingest",
        files={"file": ("measurement_book.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_ingest.status_code == 200

    res_extract = client.post(
        f"/api/v1/documents/{doc_id}/intelligence/measurement/extract",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_extract.status_code == 200
    summary = res_extract.json()

    print("SUMMARY:", summary)
    print("ERRORS:")

    os.system("python3 get_errors.py")
    print("ERRORS:")
    import subprocess
    subprocess.run(["python3", "get_errors.py"])
    assert summary["valid_measurements"] == 12
    assert summary["validation_errors"] == 0
    assert summary["duplicate_references"] == 0
    assert summary["unknown_boq_links"] == 0

    with open(os.path.join(os.path.dirname(__file__), "fixtures/golden_project/v1_ground_truth.json"), "r") as gf:
        truth = json.load(gf)

    facts = db_session.query(DocumentFact).filter_by(document_id=doc_id, fact_type="MEASUREMENT").all()

    for item in truth["measurements"]:
        ref = item["reference"]
        item_facts = [f for f in facts if f.metadata_json.get("measurement_reference") == ref]
        assert len(item_facts) in (4, 5, 6) # depends on remarks/location

        fmap = {f.field_name: f.normalized_value for f in item_facts}
        assert fmap["measurement_date"] == item["measurement_date"]
        assert fmap["boq_item_code"] == item["boq_item_code"]
        assert Decimal(fmap["quantity"]) == Decimal(item["quantity"])

    # Idempotent extraction test
    res_extract_2 = client.post(
        f"/api/v1/documents/{doc_id}/intelligence/measurement/extract",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_extract_2.status_code == 200
    assert res_extract_2.json()["valid_measurements"] == 12

    facts_2 = db_session.query(DocumentFact).filter_by(document_id=doc_id, fact_type="MEASUREMENT").all()
    original_ids = {f.id for f in facts}
    new_ids = {f.id for f in facts_2}
    assert original_ids == new_ids

    # 12. Canonical project/contract/BOQ/Measurement data remaining unchanged
    after_boq = [b.id for b in db_session.query(BoqItem).all()]
    after_meas = [m.id for m in db_session.query(Measurement).all()]
    assert before_boq == after_boq
    assert before_meas == after_meas

def test_measurement_extraction_edge_cases(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    contract = db_session.query(Contract).filter(Contract.contract_number == "CNT-PWD-2026-001").first()

    doc = Document(
        document_type="MEASUREMENT_BOOK",
        document_name="Test MB Edge Cases",
        sha256_hash="fakehashmb",
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
        "REFERENCE | DATE | ITEM CODE | QTY | LOCATION | REMARKS", # header
        "MB-VALID | 2026-01-01 | EW-01 | 100.000 | Loc | Rem",
        "MB-DUP | 2026-01-01 | EW-01 | 100.000 | Loc | Rem", # duplicate 1
        "MB-DUP | 2026-01-01 | EW-01 | 100.000 | Loc | Rem", # duplicate 2
        "MB-UNKNOWN | 2026-01-01 | UNKNOWN-99 | 100.000 | Loc | Rem", # unknown BOQ
        "MB-PREC | 2026-01-01 | EW-01 | 100.0001 | Loc | Rem", # excess prec
        "MB-NEG | 2026-01-01 | EW-01 | -100.000 | Loc | Rem", # negative
        "MB-DATE | INVALID-DATE | EW-01 | 100.000 | Loc | Rem", # bad date
        "MB-MISSING |  | EW-01 |  | Loc | Rem", # missing required
    ]

    for i, content in enumerate(chunk_content):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=content,
            content_hash=f"hash{i}",
            sheet_name="Measurements",
            row_start=i+1,
            row_end=i+1
        )
        db_session.add(chunk)
    db_session.commit()

    res = client.post(f"/api/v1/documents/{doc.id}/intelligence/measurement/extract", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    summary = res.json()

    assert summary["rows_processed"] == 8
    assert summary["valid_measurements"] == 1 # only MB-VALID
    assert summary["validation_errors"] == 7
    assert summary["duplicate_references"] == 2 # MB-DUP (both rows get flagged)
    assert summary["unknown_boq_links"] == 1 # MB-UNKNOWN

    facts = db_session.query(DocumentFact).filter_by(document_id=doc.id).all()

    # Idempotent normalization update regression
    miss_chunk = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id, DocumentChunk.content.contains("MB-MISSING")).first()
    miss_chunk.content = "MB-MISSING | 2026-01-01 | EW-01 | 100.000 | Loc | Rem"
    db_session.commit()

    res_re = client.post(f"/api/v1/documents/{doc.id}/intelligence/measurement/extract", headers={"Authorization": f"Bearer {token}"})
    assert res_re.status_code == 200

    miss_qty_fact = db_session.query(DocumentFact).filter(
        DocumentFact.document_id == doc.id,
        DocumentFact.document_chunk_id == miss_chunk.id,
        DocumentFact.field_name == "quantity"
    ).first()
    assert miss_qty_fact.normalized_value == "100.000"
    assert miss_qty_fact.validation_status == ValidationStatus.VALID

def test_measurement_extraction_auth_and_state(db_session, client, managed_docs):
    token_pm = get_token(client, "pm@infrapm.gov", "PM@123")
    token_viewer = get_token(client, "viewer@infrapm.gov", "View@123")

    doc = Document(
        document_type="BOQ", # Incompatible
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
    res1 = client.post(f"/api/v1/documents/{doc.id}/intelligence/measurement/extract", headers={"Authorization": f"Bearer {token_viewer}"})
    assert res1.status_code == 403

    # 9. Incompatible document type
    res2 = client.post(f"/api/v1/documents/{doc.id}/intelligence/measurement/extract", headers={"Authorization": f"Bearer {token_pm}"})
    assert res2.status_code == 400

    doc.document_type = "MEASUREMENT_BOOK"
    doc.ingestion_status = "PENDING"
    db_session.commit()

    # 9. Incompatible ingestion state
    res3 = client.post(f"/api/v1/documents/{doc.id}/intelligence/measurement/extract", headers={"Authorization": f"Bearer {token_pm}"})
    assert res3.status_code == 400

def test_transaction_rollback_on_failure(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    contract = db_session.query(Contract).filter(Contract.contract_number == "CNT-PWD-2026-001").first()

    doc = Document(
        document_type="MEASUREMENT_BOOK",
        document_name="Test Rollback",
        sha256_hash="fakehashrollback",
        ingestion_status="COMPLETED",
        source_filename="fake.xlsx",
        file_extension="xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size_bytes=100,
        contract_id=contract.id
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    chunk = DocumentChunk(
        document_id=doc.id, chunk_index=0, content="REF | 2026-01-01 | EW-01 | 100", content_hash="hash", sheet_name="Measurements", row_start=1, row_end=1
    )
    db_session.add(chunk)
    db_session.commit()

    with patch("sqlalchemy.orm.Session.flush", side_effect=Exception("Simulated DB failure")):
        with pytest.raises(Exception) as exc:
            extract_measurement_facts(db=db_session, document_id=doc.id, current_user=None)

        assert "Simulated DB failure" in str(exc.value)

    facts = db_session.query(DocumentFact).filter_by(document_id=doc.id).all()
    assert len(facts) == 0
