import os
import uuid
import pytest
from decimal import Decimal
from app.models.document import Document, DocumentFact, DocumentChunk, ValidationStatus
from app.models.contract import Contract
from app.models.audit_log import AuditLog

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.main import app

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
    assert response.status_code == 200
    return response.json()["access_token"]

def test_document_intelligence_pipeline(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    contract = db_session.query(Contract).filter(Contract.contract_number == "CNT-PWD-2026-001").first()

    pdf_path = os.path.join(os.path.dirname(__file__), "fixtures", "synthetic_project_evidence", "contract_agreement.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    bad_pdf_bytes = b"fake pdf content"
    non_contract_res = client.post(
        "/api/v1/documents/",
        data={
            "document_type": "BOQ",
            "document_name": "Test Contract Intelligence - Bad Type",
            "project_id": str(contract.project_id)
        },
        files={"file": ("bad_agreement.pdf", bad_pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    bad_doc_id = non_contract_res.json()["id"]
    managed_docs.append(bad_doc_id)

    # We do NOT ingest, just attempt extraction to see it fail
    extract_bad = client.post(f"/api/v1/documents/{bad_doc_id}/intelligence/extract", headers={"Authorization": f"Bearer {token}"})
    assert extract_bad.status_code == 400
    assert "requires CONTRACT" in extract_bad.json()["detail"]

    # Also test reconciliation rejected for non-CONTRACT
    recon_bad = client.post(f"/api/v1/documents/{bad_doc_id}/intelligence/reconcile", headers={"Authorization": f"Bearer {token}"})
    assert recon_bad.status_code == 400
    assert "requires CONTRACT" in recon_bad.json()["detail"]

    # Upload CONTRACT Document
    response = client.post(
        "/api/v1/documents/",
        data={
            "document_type": "CONTRACT",
            "document_name": "Test Contract Intelligence",
            "project_id": str(contract.project_id),
            "contract_id": str(contract.id)
        },
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    doc_id = response.json()["id"]
    managed_docs.append(doc_id)

    # Test extraction rejected before ingestion
    extract_early = client.post(f"/api/v1/documents/{doc_id}/intelligence/extract", headers={"Authorization": f"Bearer {token}"})
    assert extract_early.status_code == 400
    assert "requires COMPLETED ingestion" in extract_early.json()["detail"]

    # Test reconciliation rejected before ingestion
    recon_early = client.post(f"/api/v1/documents/{doc_id}/intelligence/reconcile", headers={"Authorization": f"Bearer {token}"})
    assert recon_early.status_code == 400
    assert "requires COMPLETED ingestion" in recon_early.json()["detail"]

    # Ingest Document
    client.post(f"/api/v1/documents/{doc_id}/ingest", files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")}, headers={"Authorization": f"Bearer {token}"})

    # Extraction
    extract_res = client.post(f"/api/v1/documents/{doc_id}/intelligence/extract", headers={"Authorization": f"Bearer {token}"})
    assert extract_res.status_code == 200
    facts = extract_res.json()
    assert len(facts) == 2

    fact_map = {f["field_name"]: f for f in facts}
    assert fact_map["contract_number"]["value"] == "CNT -PWD-2026-001"
    assert fact_map["contract_value"]["value"] == "485000000.00"
    original_cv_fact_id = fact_map["contract_value"]["id"]

    # Repeated extraction preserving IDs
    extract_res2 = client.post(f"/api/v1/documents/{doc_id}/intelligence/extract", headers={"Authorization": f"Bearer {token}"})
    assert extract_res2.status_code == 200
    facts2 = extract_res2.json()
    assert len(facts2) == 2
    assert [f for f in facts2 if f["field_name"] == "contract_value"][0]["id"] == original_cv_fact_id

    # Normalization & Reconciliation
    recon_res = client.post(f"/api/v1/documents/{doc_id}/intelligence/reconcile", headers={"Authorization": f"Bearer {token}"})
    assert recon_res.status_code == 200
    recon_facts = recon_res.json()
    recon_map = {f["field_name"]: f for f in recon_facts}

    assert recon_map["contract_number"]["normalized_value"] == "CNT-PWD-2026-001"
    assert recon_map["contract_number"]["validation_status"] == "VALID"
    assert recon_map["contract_value"]["normalized_value"] == "485000000.00"

    # 404 tests
    fake_id = str(uuid.uuid4())
    assert client.post(f"/api/v1/documents/{fake_id}/intelligence/extract", headers={"Authorization": f"Bearer {token}"}).status_code == 404

def test_document_intelligence_edge_cases(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    contract = db_session.query(Contract).filter(Contract.contract_number == "CNT-PWD-2026-001").first()

    doc = Document(
        document_type="CONTRACT",
        document_name="Test Contract Intelligence - Edge Cases",
        project_id=contract.project_id,
        contract_id=contract.id,
        sha256_hash="fakehash",
        ingestion_status="COMPLETED",
        source_filename="fake.pdf",
        file_extension="pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        source_system="MANUAL_UPLOAD"
    )
    db_session.add(doc)
    db_session.commit()
    managed_docs.append(str(doc.id))

    chunk = DocumentChunk(document_id=doc.id, chunk_index=0, content="Fake content", content_hash="fake")
    db_session.add(chunk)
    db_session.commit()

    # Equivalent monetary formats testing
    f1 = DocumentFact(document_id=doc.id, document_chunk_id=chunk.id, fact_type="CONTRACT", field_name="contract_value", value="INR 485,000,000.00", source_reference="Page 1", validation_status=ValidationStatus.UNVALIDATED)
    f2 = DocumentFact(document_id=doc.id, document_chunk_id=chunk.id, fact_type="CONTRACT", field_name="contract_value", value="₹ 485000000", source_reference="Page 2", validation_status=ValidationStatus.UNVALIDATED)

    # Bad values for monetary testing
    f3_bad = DocumentFact(document_id=doc.id, document_chunk_id=chunk.id, fact_type="CONTRACT", field_name="contract_value", value="-500.00", source_reference="Page 3", validation_status=ValidationStatus.UNVALIDATED)
    f_bad_excess = DocumentFact(document_id=doc.id, document_chunk_id=chunk.id, fact_type="CONTRACT", field_name="contract_value", value="485000000.001", source_reference="Page 4", validation_status=ValidationStatus.UNVALIDATED)
    f_bad_text = DocumentFact(document_id=doc.id, document_chunk_id=chunk.id, fact_type="CONTRACT", field_name="contract_value", value="xyz", source_reference="Page 5", validation_status=ValidationStatus.UNVALIDATED)
    f_bad_empty = DocumentFact(document_id=doc.id, document_chunk_id=chunk.id, fact_type="CONTRACT", field_name="contract_value", value="", source_reference="Page 6", validation_status=ValidationStatus.UNVALIDATED)
    f_bad_comma = DocumentFact(document_id=doc.id, document_chunk_id=chunk.id, fact_type="CONTRACT", field_name="contract_value", value="48,500,00", source_reference="Page 7", validation_status=ValidationStatus.UNVALIDATED)

    f4_dup = DocumentFact(document_id=doc.id, document_chunk_id=chunk.id, fact_type="CONTRACT", field_name="contract_number", value="CNT-PWD-2026-001", source_reference="Page 1", validation_status=ValidationStatus.UNVALIDATED)
    f5_dup = DocumentFact(document_id=doc.id, document_chunk_id=chunk.id, fact_type="CONTRACT", field_name="contract_number", value="CNT-PWD-9999", source_reference="Page 2", validation_status=ValidationStatus.UNVALIDATED)

    db_session.add_all([f1, f2, f3_bad, f_bad_excess, f_bad_text, f_bad_empty, f_bad_comma, f4_dup, f5_dup])
    db_session.commit()

    recon_res = client.post(f"/api/v1/documents/{doc.id}/intelligence/reconcile", headers={"Authorization": f"Bearer {token}"})
    assert recon_res.status_code == 200

    db_facts = db_session.query(DocumentFact).filter(DocumentFact.document_id == doc.id).all()
    cv_facts = {f.id: f for f in db_facts if f.field_name == "contract_value"}

    f1_db = cv_facts[f1.id]
    assert f1_db.normalized_value == "485000000.00"
    assert f1_db.validation_status == ValidationStatus.VALID

    f2_db = cv_facts[f2.id]
    # The normalizer yields strictly formatted to .2f, so it equals canonical and f1_db, NOT ambiguous
    assert f2_db.normalized_value == "485000000.00"
    assert f2_db.validation_status == ValidationStatus.VALID
    assert f2_db.metadata_json["reconciliation"]["outcome"] == "MATCH"

    # Assert bad values are rejected with INVALID_FORMAT (and implicitly not a MATCH nor AMBIGUOUS)
    for bad_f in [f3_bad, f_bad_excess, f_bad_text, f_bad_empty, f_bad_comma]:
        bad_db = cv_facts[bad_f.id]
        assert bad_db.normalized_value is None, f"Expected None for {bad_f.value}"
        assert bad_db.validation_status == ValidationStatus.INVALID, f"Expected INVALID for {bad_f.value}"
        assert bad_db.metadata_json["reconciliation"]["outcome"] == "INVALID_FORMAT"

    cn_facts = [f for f in db_facts if f.field_name == "contract_number"]
    assert len(cn_facts) == 2
    for cn in cn_facts:
        assert cn.validation_status == ValidationStatus.CONFLICT
        assert cn.metadata_json["reconciliation"]["outcome"] == "AMBIGUOUS"

    c_after = db_session.query(Contract).filter(Contract.id == contract.id).first()
    assert c_after.contract_value == Decimal("485000000.00")
