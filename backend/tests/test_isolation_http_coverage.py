"""
RBAC V2 — HTTP Route Isolation Coverage Tests
Tests that the FastAPI routes themselves correctly enforce project isolation,
ensuring we don't just test service layers bypassing HTTP endpoints.
"""
import uuid
from decimal import Decimal
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.role import Role
from app.models.user import User, UserProjectAssignment
from app.models.project import Project
from app.models.department import Department
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.boq import Boq
from app.models.boq_revision import BoqRevision
from app.models.boq_item import BoqItem
from app.models.ra_bill import RABill
from app.models.document import Document
from app.models.evm import EVMBaseline

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client():
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def mock_auth(client_obj, user: User):
    def _override(): return user
    app.dependency_overrides[get_current_user] = _override

def override_db(session):
    def _get_db(): yield session
    app.dependency_overrides[get_db] = _get_db

def make_role(db, name):
    r = db.query(Role).filter_by(name=name).first()
    if not r:
        r = Role(name=name)
        db.add(r)
        db.flush()
    return r

def make_user(db, role, suffix=None):
    suffix = suffix or str(uuid.uuid4())[:8]
    u = User(email=f"u_{suffix}@test.com", password_hash="x", role_id=role.id)
    db.add(u)
    db.flush()
    return u

def make_project(db, dept_id, pm_id):
    p = Project(
        code=f"PRJ-{str(uuid.uuid4())[:6]}", name="P", dept_id=dept_id, pm_id=pm_id,
        status="Active", total_estimated_cost=Decimal("500"),
        start_date=date(2026,1,1), expected_completion=date(2026,12,31)
    )
    db.add(p)
    db.flush()
    return p

def assign(db, user_id, project_id):
    a = UserProjectAssignment(user_id=user_id, project_id=project_id)
    db.add(a)
    db.flush()

def setup_full_chain(db, user, create_assignment=True):
    # Department
    dept = Department(code=f"D-{str(uuid.uuid4())[:4]}", name="Dept")
    db.add(dept)
    db.flush()
    
    # Project
    proj = make_project(db, dept.id, user.id)
    if create_assignment:
        assign(db, user.id, proj.id)
        
    # Contractor
    cont = Contractor(registration_number=f"R-{str(uuid.uuid4())[:4]}", name="C", status="Active")
    db.add(cont)
    db.flush()
    
    # Contract
    contract = Contract(
        contract_number=f"CON-{str(uuid.uuid4())[:4]}", project_id=proj.id, contractor_id=cont.id,
        award_date=date(2026,1,1), start_date=date(2026,1,1), original_completion_date=date(2026,12,31),
        current_completion_date=date(2026,12,31), contract_value=Decimal("100"), status="Active"
    )
    db.add(contract)
    db.flush()
    
    # BOQ
    boq = Boq(contract_id=contract.id, boq_number=f"BOQ-{str(uuid.uuid4())[:4]}", title="B", status="Draft")
    db.add(boq)
    db.flush()
    
    # BOQ Revision
    rev = BoqRevision(boq_id=boq.id, revision_number=1, status="Draft", remarks="", revision_date=date(2026,1,1))
    db.add(rev)
    db.flush()
    
    # BOQ Item
    item = BoqItem(
        revision_id=rev.id, item_code="IC", item_number="1", description="D",
        unit="m", quantity=Decimal("10"), rate=Decimal("5"), amount=Decimal("50")
    )
    db.add(item)
    db.flush()
    
    return proj, contract, boq, rev, item

# 1. Measurement GET/POST HTTP isolation
def test_measurement_list_endpoint_succeeds_and_does_not_crash(db_session, client):
    pm = make_user(db_session, make_role(db_session, "Project Manager"))
    proj, contract, boq, rev, item = setup_full_chain(db_session, pm)
    
    override_db(db_session)
    mock_auth(client, pm)
    
    resp = client.get("/api/v1/measurements")
    assert resp.status_code == 200, resp.text


def test_measurement_create_cross_project_fails(db_session, client):
    pm_a = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_b = make_user(db_session, make_role(db_session, "Project Manager"))
    
    proj_a, contract_a, boq_a, rev_a, item_a = setup_full_chain(db_session, pm_a)
    proj_b, contract_b, boq_b, rev_b, item_b = setup_full_chain(db_session, pm_b)
    
    override_db(db_session)
    mock_auth(client, pm_a)
    
    payload = {
        "boq_item_id": str(item_b.id),
        "measurement_date": "2026-06-01",
        "quantity": 5.0,
        "reference": "Cross",
        "description": "Cross project measurement"
    }
    resp = client.post("/api/v1/measurements", json=payload)
    assert resp.status_code == 403


# 2. BOQ Revisions / Items HTTP isolation
def test_boq_item_direct_access_cross_project_fails(db_session, client):
    pm_a = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_b = make_user(db_session, make_role(db_session, "Project Manager"))
    
    _, _, _, _, item_b = setup_full_chain(db_session, pm_b)
    
    override_db(db_session)
    mock_auth(client, pm_a)
    
    resp = client.get(f"/api/v1/boq-items/{item_b.id}")
    assert resp.status_code == 403

def test_boq_revision_direct_access_cross_project_fails(db_session, client):
    pm_a = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_b = make_user(db_session, make_role(db_session, "Project Manager"))
    
    _, _, _, rev_b, _ = setup_full_chain(db_session, pm_b)
    
    override_db(db_session)
    mock_auth(client, pm_a)
    
    resp = client.get(f"/api/v1/boq-revisions/{rev_b.id}")
    assert resp.status_code == 403

# 3. Audit Logs isolation
def test_viewer_cannot_access_global_audit_logs(db_session, client):
    viewer = make_user(db_session, make_role(db_session, "Viewer"))
    proj, _, _, _, _ = setup_full_chain(db_session, viewer, create_assignment=True)
    
    override_db(db_session)
    mock_auth(client, viewer)
    
    resp = client.get("/api/v1/audit-logs/")
    assert resp.status_code == 403
    assert "Project-scoped audit log access is not supported" in resp.json()["detail"]

def test_admin_can_access_global_audit_logs(db_session, client):
    admin = make_user(db_session, make_role(db_session, "Admin"))
    
    override_db(db_session)
    mock_auth(client, admin)
    
    resp = client.get("/api/v1/audit-logs/")
    assert resp.status_code == 200

# 4. RA Bills HTTP isolation
def test_ra_bill_direct_access_cross_project_fails(db_session, client):
    pm_a = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_b = make_user(db_session, make_role(db_session, "Project Manager"))
    
    proj_b, contract_b, _, _, _ = setup_full_chain(db_session, pm_b)
    
    bill_b = RABill(
        contract_id=contract_b.id, bill_number="RB-1", bill_date=date.today(),
        period_from=date.today(), period_to=date.today(), status="Draft", created_by=pm_b.id
    )
    db_session.add(bill_b)
    db_session.flush()
    
    override_db(db_session)
    mock_auth(client, pm_a)
    
    resp = client.get(f"/api/v1/ra-bills/{bill_b.id}")
    assert resp.status_code == 403

def test_ra_bill_create_cross_project_fails(db_session, client):
    pm_a = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_b = make_user(db_session, make_role(db_session, "Project Manager"))
    
    setup_full_chain(db_session, pm_a)
    _, contract_b, _, _, _ = setup_full_chain(db_session, pm_b)
    
    override_db(db_session)
    mock_auth(client, pm_a)
    
    payload = {
        "contract_id": str(contract_b.id),
        "bill_number": "RB-2",
        "bill_date": str(date.today()),
        "period_from": str(date.today()),
        "period_to": str(date.today())
    }
    resp = client.post("/api/v1/ra-bills/", json=payload)
    assert resp.status_code == 403

# 5. Documents HTTP isolation
def test_document_direct_access_cross_project_fails(db_session, client):
    pm_a = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_b = make_user(db_session, make_role(db_session, "Project Manager"))
    
    proj_b, _, _, _, _ = setup_full_chain(db_session, pm_b)
    doc_b = Document(
        project_id=proj_b.id, document_type="CONTRACT", document_name="Doc B",
        source_filename="test.pdf", file_extension="pdf", mime_type="application/pdf",
        file_size_bytes=100, sha256_hash="hash1", ingestion_status="COMPLETED"
    )
    db_session.add(doc_b)
    db_session.flush()
    
    override_db(db_session)
    mock_auth(client, pm_a)
    
    resp = client.get(f"/api/v1/documents/{doc_b.id}")
    assert resp.status_code == 403

def test_document_extract_cross_project_fails(db_session, client):
    pm_a = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_b = make_user(db_session, make_role(db_session, "Project Manager"))
    
    proj_b, _, _, _, _ = setup_full_chain(db_session, pm_b)
    doc_b = Document(
        project_id=proj_b.id, document_type="CONTRACT", document_name="Doc B2",
        source_filename="test2.pdf", file_extension="pdf", mime_type="application/pdf",
        file_size_bytes=100, sha256_hash="hash2", ingestion_status="COMPLETED"
    )
    db_session.add(doc_b)
    db_session.flush()
    
    override_db(db_session)
    mock_auth(client, pm_a)
    
    resp = client.post(f"/api/v1/documents/{doc_b.id}/intelligence/extract")
    assert resp.status_code == 403

# 6. EVM HTTP isolation
def test_evm_baseline_direct_access_cross_project_fails(db_session, client):
    pm_a = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_b = make_user(db_session, make_role(db_session, "Project Manager"))
    
    proj_b, _, _, _, _ = setup_full_chain(db_session, pm_b)
    baseline_b = EVMBaseline(
        project_id=proj_b.id, baseline_number="B-1", name="Base",
        status="Draft", effective_date=date(2026,1,1), created_by=pm_b.id
    )
    db_session.add(baseline_b)
    db_session.flush()
    
    override_db(db_session)
    mock_auth(client, pm_a)
    
    resp = client.get(f"/api/v1/evm-baselines/{baseline_b.id}")
    assert resp.status_code == 403
