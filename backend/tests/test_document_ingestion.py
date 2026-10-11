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

def test_document_lifecycle(db_session, client, isolated_project_and_contract, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    pdf_path = os.path.join(SYNTHETIC_EVIDENCE_DIR, "contract_agreement.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # 1. Register
    response = client.post(
        "/api/v1/documents/",
        data={
            "project_id": str(isolated_project_and_contract['project'].id), "document_type": "CONTRACT",
            "document_name": "Contract Agreement",
        },
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201, response.text
    doc_id = response.json()["id"]
    managed_docs.append(doc_id)

    doc = db_session.query(Document).filter_by(id=doc_id).first()
    assert doc.ingestion_status in ["PENDING", "COMPLETED"]
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

def test_duplicate_document_registration(db_session, client, isolated_project_and_contract, managed_docs):
    token = get_token(client, "pm@infrapm.gov", "PM@123")
    pdf_path = os.path.join(SYNTHETIC_EVIDENCE_DIR, "contract_agreement.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    response1 = client.post(
        "/api/v1/documents/",
        data={"project_id": str(isolated_project_and_contract['project'].id), "document_type": "CONTRACT", "document_name": "Doc 1"},
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response1.status_code == 201
    managed_docs.append(response1.json()["id"])

    # Duplicate registration should safely return existing
    response2 = client.post(
        "/api/v1/documents/",
        data={"project_id": str(isolated_project_and_contract['project'].id), "document_type": "CONTRACT", "document_name": "Doc 2"},
        files={"file": ("contract_agreement.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response2.status_code == 201
    assert response1.json()["id"] == response2.json()["id"]

def test_golden_dataset_validation(db_session, client, isolated_project_and_contract, managed_docs):
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
            data={"project_id": str(isolated_project_and_contract['project'].id), "document_type": "BOQ", "document_name": "Approved BOQ"},
            files={"file": ("approved_boq.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"}
        )
    doc_id = response.json()["id"]
    managed_docs.append(doc_id)

    with open(xlsx_path, "rb") as f:
        client.post(f"/api/v1/documents/{doc_id}/ingest", files={"file": ("approved_boq.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers={"Authorization": f"Bearer {token}"})

    doc = db_session.query(Document).filter_by(id=doc_id).first()
    boq_contents = [c.content for c in doc.chunks if c.sheet_name == "BOQ Items"]

    # Validate all BOQ items against header-labelled parser output.
    for item in truth["boq"]["items"]:
        item_code = str(item["item_code"])
        matching_rows = []

        for content in boq_contents:
            for line in content.splitlines():
                if line.startswith("Excel row ") and f"Item Code: {item_code}" in line:
                    matching_rows.append(line)

        assert len(matching_rows) == 1, (
            f"Missing or duplicate BOQ item {item_code}"
        )
        row = matching_rows[0]

        expected_fields = {
            "Item Number": str(item["item_number"]),
            "Description": str(item["description"]).strip(),
            "Unit": str(item["unit"]),
            "Quantity": str(item["quantity"]),
            "Rate": str(item["rate"]),
            "Amount": str(item["amount"]),
        }

        for label, expected in expected_fields.items():
            prefix = f"{label}: "
            field = next(
                (
                    part[len(prefix):].strip()
                    for part in row.split(" | ")
                    if part.startswith(prefix)
                ),
                None,
            )
            assert field is not None, (
                f"Missing {label} for BOQ item {item_code}"
            )

            if label in {"Quantity", "Rate", "Amount"}:
                assert Decimal(field) == Decimal(expected), (
                    f"{label} mismatch for BOQ item {item_code}"
                )
            else:
                assert field == expected, (
                    f"{label} mismatch for BOQ item {item_code}"
                )

    # --- 2. Measurement Book Validation ---
    mb_path = os.path.join(SYNTHETIC_EVIDENCE_DIR, "measurement_book.xlsx")
    with open(mb_path, "rb") as f:
        mb_bytes = f.read()
    response = client.post("/api/v1/documents/", data={"project_id": str(isolated_project_and_contract['project'].id), "document_type": "MEASUREMENT_BOOK", "document_name": "MB"}, files={"file": ("mb.xlsx", mb_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers={"Authorization": f"Bearer {token}"})
    mb_id = response.json()["id"]
    managed_docs.append(mb_id)
    client.post(f"/api/v1/documents/{mb_id}/ingest", files={"file": ("mb.xlsx", mb_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers={"Authorization": f"Bearer {token}"})

    mb_doc = db_session.query(Document).filter_by(id=mb_id).first()
    mb_contents = [c.content for c in mb_doc.chunks if c.sheet_name == "Measurements"]

    seen_references = set()

    for meas in truth["measurements"]:
        m_ref = str(meas["reference"])
        matching_rows = []

        for content in mb_contents:
            for line in content.splitlines():
                if (
                    line.startswith("Excel row ")
                    and f"Reference: {m_ref}" in line
                ):
                    matching_rows.append(line)

        assert len(matching_rows) == 1, (
            f"Missing or duplicate MB reference {m_ref}"
        )
        row = matching_rows[0]

        expected_fields = {
            "Date": str(meas["measurement_date"]),
            "Item Code": str(meas["boq_item_code"]),
        }

        for label, expected in expected_fields.items():
            prefix = f"{label}: "
            actual = next(
                (
                    part[len(prefix):].strip()
                    for part in row.split(" | ")
                    if part.startswith(prefix)
                ),
                None,
            )
            assert actual == expected, (
                f"{label} mismatch for measurement {m_ref}: "
                f"expected {expected!r}, got {actual!r}"
            )

        quantity_prefix = "Quantity: "
        quantity = next(
            (
                part[len(quantity_prefix):].strip()
                for part in row.split(" | ")
                if part.startswith(quantity_prefix)
            ),
            None,
        )
        assert quantity is not None, (
            f"Missing Quantity for measurement {m_ref}"
        )
        assert Decimal(quantity) == Decimal(meas["quantity"]), (
            f"Measurement Quantity mismatch for {m_ref}"
        )

        seen_references.add(m_ref)

    assert len(seen_references) == 12, (
        "Measurement Book must contain exactly 12 unique references"
    )

def test_canonical_db_immutability(db_session, client, isolated_project_and_contract, managed_docs):
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
        data={"project_id": str(isolated_project_and_contract['project'].id), "document_type": "CONTRACT", "document_name": "Contract Agreement"},
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
