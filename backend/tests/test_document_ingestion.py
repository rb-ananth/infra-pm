import uuid
import os
import io
import json
import pytest
from decimal import Decimal, InvalidOperation
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.main import app
from app.models.project import Project
from app.models.document import Document, DocumentChunk
from app.models.boq_item import BoqItem
from app.models.measurement import Measurement
from app.services.document_parser import DocumentParser

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
        from app.models.document import DocumentFact, DocumentChunk, Document
        from app.models.audit_log import AuditLog
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
    assert response.status_code == 200
    return response.json()["access_token"]

client = TestClient(app)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SYNTHETIC_EVIDENCE_DIR = os.path.join(FIXTURES_DIR, "synthetic_project_evidence")
GOLDEN_TRUTH_PATH = os.path.join(FIXTURES_DIR, "golden_project", "v1_ground_truth.json")

def test_document_parser_sha256():
    data = b"Hello, world!"
    stream = io.BytesIO(data)
    hash_val = DocumentParser.calculate_sha256(stream)
    assert hash_val == "315f5bdb76d078c43b8ac0064e4a0164612b1fce77c869345bfc94c75894edd3"
    assert stream.tell() == 0

def test_document_lifecycle(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    pdf_path = os.path.join(SYNTHETIC_EVIDENCE_DIR, "contract_agreement.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # 1. Register
    response = client.post(
        "/api/v1/documents/",
        data={
            "project_id": str(db_session.query(Project).first().id), "document_type": "CONTRACT",
            "document_name": "Contract Agreement",
        },
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201, response.text
    doc_id = response.json()["id"]
    managed_docs.append(doc_id)

    doc = db_session.query(Document).filter_by(id=doc_id).first()
    assert doc.ingestion_status == "PENDING"
    assert len(doc.chunks) == 0

    # 2. Ingest
    response2 = client.post(
        f"/api/v1/documents/{doc_id}/ingest",
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response2.status_code == 200, response2.text

    db_session.refresh(doc)
    assert doc.ingestion_status == "COMPLETED"
    assert len(doc.chunks) > 0
    assert doc.chunks[0].page_number == 1
    assert "CONTRACT AGREEMENT" in doc.chunks[0].content.upper()

def test_duplicate_document_registration(db_session, client, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    pdf_path = os.path.join(SYNTHETIC_EVIDENCE_DIR, "contract_agreement.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    response1 = client.post(
        "/api/v1/documents/",
        data={"project_id": str(db_session.query(Project).first().id), "document_type": "CONTRACT", "document_name": "Doc 1"},
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response1.status_code == 201
    managed_docs.append(response1.json()["id"])

    # Duplicate registration should safely return existing
    response2 = client.post(
        "/api/v1/documents/",
        data={"project_id": str(db_session.query(Project).first().id), "document_type": "CONTRACT", "document_name": "Doc 2"},
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]

def test_golden_dataset_validation(db_session, client, managed_docs):
    """
    Parses actual evidence documents and directly verifies values against v1_ground_truth.json
    """
    token = get_token(client, "pm@infrapm.gov", "PM@123")

    with open(GOLDEN_TRUTH_PATH, "r") as f:
        truth = json.load(f)

    # --- 1. BOQ Validation ---
    xlsx_path = os.path.join(SYNTHETIC_EVIDENCE_DIR, "approved_boq.xlsx")
    with open(xlsx_path, "rb") as f:
        response = client.post(
            "/api/v1/documents/",
            data={"project_id": str(db_session.query(Project).first().id), "document_type": "BOQ", "document_name": "Approved BOQ"},
            files={"file": ("approved_boq.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"}
        )
    doc_id = response.json()["id"]
    managed_docs.append(doc_id)

    with open(xlsx_path, "rb") as f:
        client.post(f"/api/v1/documents/{doc_id}/ingest", files={"file": ("approved_boq.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers={"Authorization": f"Bearer {token}"})

    doc = db_session.query(Document).filter_by(id=doc_id).first()
    boq_contents = [c.content for c in doc.chunks if c.sheet_name == "BOQ Items"]

    # Actual file validation against all 10 BOQ items
    for item in truth["boq"]["items"]:
        # Find row matching item_code exactly in the chunk content string split by " | "
        matching_rows = []
        for content in boq_contents:
            cells = [cell.strip() for cell in content.split(" | ")]
            if str(item["item_code"]) in cells:
                matching_rows.append(cells)

        assert len(matching_rows) == 1, f"Missing or duplicate BOQ item {item['item_code']}"
        cells = matching_rows[0]

        # Verify textual fields
        assert str(item["item_number"]) in cells, f"BOQ Item Number mismatch for {item['item_code']}"
        assert str(item["description"]).strip() in cells, f"BOQ Description mismatch for {item['item_code']}"
        assert str(item["unit"]) in cells, f"BOQ Unit mismatch for {item['item_code']}"

        # Verify deterministic numeric fields
        extracted_qty = cells[4]
        extracted_rate = cells[5]
        extracted_amount = cells[6]

        assert Decimal(extracted_qty) == Decimal(item["quantity"]), f"BOQ Quantity mismatch for {item['item_code']}"
        assert Decimal(extracted_rate) == Decimal(item["rate"]), f"BOQ Rate mismatch for {item['item_code']}"
        assert Decimal(extracted_amount) == Decimal(item["amount"]), f"BOQ Amount mismatch for {item['item_code']}"

    # --- 2. Measurement Book Validation ---
    mb_path = os.path.join(SYNTHETIC_EVIDENCE_DIR, "measurement_book.xlsx")
    with open(mb_path, "rb") as f:
        mb_bytes = f.read()
    response = client.post("/api/v1/documents/", data={"project_id": str(db_session.query(Project).first().id), "document_type": "MEASUREMENT_BOOK", "document_name": "MB"}, files={"file": ("mb.xlsx", mb_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers={"Authorization": f"Bearer {token}"})
    mb_id = response.json()["id"]
    managed_docs.append(mb_id)
    client.post(f"/api/v1/documents/{mb_id}/ingest", files={"file": ("mb.xlsx", mb_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers={"Authorization": f"Bearer {token}"})

    mb_doc = db_session.query(Document).filter_by(id=mb_id).first()
    mb_contents = [c.content for c in mb_doc.chunks if c.sheet_name == "Measurements"]

    seen_references = set()
    for meas in truth["measurements"]:
        m_ref = meas["reference"]
        matching_rows = []
        for content in mb_contents:
            cells = [cell.strip() for cell in content.split(" | ")]
            if str(m_ref) in cells:
                matching_rows.append(cells)

        assert len(matching_rows) == 1, f"Missing or duplicate MB reference {m_ref}"
        cells = matching_rows[0]

        seen_references.add(m_ref)

        # Validation
        assert str(meas["measurement_date"]) in cells, f"Measurement Date mismatch for {m_ref}"
        assert str(meas["boq_item_code"]) in cells, f"Measurement BOQ Code mismatch for {m_ref}"

        found_qty = False
        for cell in cells:
            try:
                if Decimal(cell) == Decimal(meas["quantity"]):
                    found_qty = True
                    break
            except InvalidOperation:
                pass
        assert found_qty, f"Measurement Quantity mismatch for {m_ref}"

    assert len(seen_references) == 12, "Measurement Book must contain exactly 12 unique references"


def test_canonical_db_immutability(db_session, client, managed_docs):
    """
    Ensures that ingestion operations do absolutely zero mutations
    to the canonical BOQ and Measurements tables.
    """
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    def get_boq_snapshot():
        items = db_session.query(BoqItem).order_by(BoqItem.id).all()
        return [{"id": i.id, "quantity": i.quantity, "rate": i.rate, "amount": i.amount, "code": i.item_code} for i in items]

    def get_meas_snapshot():
        items = db_session.query(Measurement).order_by(Measurement.id).all()
        return [{"id": i.id, "ref": i.reference, "qty": i.quantity, "date": i.measurement_date, "boq_item_id": i.boq_item_id, "desc": i.description, "status": i.status} for i in items]

    before_boq = get_boq_snapshot()
    before_measurements = get_meas_snapshot()

    # Run document registration & ingestion
    pdf_path = os.path.join(SYNTHETIC_EVIDENCE_DIR, "contract_agreement.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    response = client.post(
        "/api/v1/documents/",
        data={"project_id": str(db_session.query(Project).first().id), "document_type": "CONTRACT", "document_name": "Contract Agreement"},
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    doc_id = response.json()["id"]
    managed_docs.append(doc_id)
    client.post(
        f"/api/v1/documents/{doc_id}/ingest",
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )

    # Take post-snapshots and rigorously compare
    after_boq = get_boq_snapshot()
    after_measurements = get_meas_snapshot()

    assert before_boq == after_boq, "Canonical BOQ records were mutated during document ingestion!"
    assert before_measurements == after_measurements, "Canonical Measurement records were mutated during document ingestion!"
