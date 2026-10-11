"""
RBAC V2 — Project Isolation Security Tests

Verifies that all project-level authorization boundaries are enforced correctly.
Tests are independent of each other and clean up after themselves via rollback.
"""
import uuid
from decimal import Decimal
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.role import Role  # Role lives in app.models.role
from app.models.user import User, UserProjectAssignment
from app.models.project import Project
from app.models.department import Department
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.boq import Boq
from app.models.boq_revision import BoqRevision
from app.models.boq_item import BoqItem
from app.models.audit_log import AuditLog

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection, join_transaction_mode="create_savepoint")
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
    """Override get_current_user to return the given user object."""
    def _override():
        return user
    app.dependency_overrides[get_current_user] = _override


def override_db(session):
    """Override the DB dependency to use the test transaction session."""
    def _get_db():
        yield session
    app.dependency_overrides[get_db] = _get_db


# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------

def make_role(db, name):
    r = db.query(Role).filter_by(name=name).first()
    if not r:
        r = Role(name=name)
        db.add(r)
        db.flush()
    return r


def make_user(db, role, suffix=None):
    suffix = suffix or str(uuid.uuid4())[:8]
    u = User(
        email=f"user_{suffix}@isolation.test",
        password_hash="x",
        role_id=role.id,
    )
    db.add(u)
    db.flush()
    return u


def make_department(db, suffix=None):
    suffix = suffix or str(uuid.uuid4())[:8]
    d = Department(code=f"D-{suffix}", name=f"Dept {suffix}")
    db.add(d)
    db.flush()
    return d


def make_project(db, dept, pm_user, suffix=None):
    suffix = suffix or str(uuid.uuid4())[:8]
    p = Project(
        code=f"PRJ-{suffix}",
        name=f"Project {suffix}",
        dept_id=dept.id,
        pm_id=pm_user.id,
        status="Active",
        total_estimated_cost=Decimal("500000.00"),
        start_date=date(2026, 1, 1),
        expected_completion=date(2026, 12, 31),
    )
    db.add(p)
    db.flush()
    return p


def assign(db, user, project):
    a = UserProjectAssignment(user_id=user.id, project_id=project.id)
    db.add(a)
    db.flush()
    return a


def make_contractor(db, suffix=None):
    suffix = suffix or str(uuid.uuid4())[:8]
    c = Contractor(
        registration_number=f"REG-{suffix}",
        name=f"Contractor {suffix}",
        status="Active",
    )
    db.add(c)
    db.flush()
    return c


def make_contract(db, project, contractor, suffix=None):
    suffix = suffix or str(uuid.uuid4())[:8]
    c = Contract(
        contract_number=f"CON-{suffix}",
        project_id=project.id,
        contractor_id=contractor.id,
        award_date=date(2026, 1, 1),
        start_date=date(2026, 1, 1),
        original_completion_date=date(2026, 12, 31),
        current_completion_date=date(2026, 12, 31),
        contract_value=Decimal("100000.00"),
        status="Active",
    )
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------
# 1. Unassigned operational user has no project access
# ---------------------------------------------------------------------------

def test_unassigned_user_gets_empty_project_list(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm_user = make_user(db_session, role_pm, "unassigned")
    dept = make_department(db_session)
    make_project(db_session, dept, pm_user)  # Project exists; user has no assignment

    # Remove any auto-assignment (user was PM used to create via model, not service)
    db_session.query(UserProjectAssignment).filter_by(user_id=pm_user.id).delete()
    db_session.flush()

    override_db(db_session)
    mock_auth(client, pm_user)

    resp = client.get("/api/v1/projects/")
    assert resp.status_code == 200
    assert resp.json() == [], f"Expected empty list, got {resp.json()}"


def test_unassigned_user_cannot_access_known_project_by_id(db_session, client):
    role_admin = make_role(db_session, "Admin")
    role_pm = make_role(db_session, "Project Manager")
    admin = make_user(db_session, role_admin, "admin_known")
    pm_no_access = make_user(db_session, role_pm, "pm_no_access")
    dept = make_department(db_session)
    project = make_project(db_session, dept, admin if admin else pm_no_access)

    override_db(db_session)
    mock_auth(client, pm_no_access)

    resp = client.get(f"/api/v1/projects/{project.id}")
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


def test_guessed_uuid_returns_403_for_unassigned_user(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm_user = make_user(db_session, role_pm, "guess")

    override_db(db_session)
    mock_auth(client, pm_user)

    resp = client.get(f"/api/v1/projects/{uuid.uuid4()}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 2. Admin retains global access
# ---------------------------------------------------------------------------

def test_admin_sees_all_projects(db_session, client):
    role_admin = make_role(db_session, "Admin")
    role_pm = make_role(db_session, "Project Manager")
    admin = make_user(db_session, role_admin, "globaladmin")
    pm = make_user(db_session, role_pm, "pmglobal")
    dept = make_department(db_session)
    p1 = make_project(db_session, dept, pm, "gp1")
    p2 = make_project(db_session, dept, pm, "gp2")

    override_db(db_session)
    mock_auth(client, admin)

    resp = client.get("/api/v1/projects/")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert str(p1.id) in ids
    assert str(p2.id) in ids


def test_admin_can_access_any_project_by_id(db_session, client):
    role_admin = make_role(db_session, "Admin")
    role_pm = make_role(db_session, "Project Manager")
    admin = make_user(db_session, role_admin, "admin_direct")
    pm = make_user(db_session, role_pm, "pm_direct")
    dept = make_department(db_session)
    project = make_project(db_session, dept, pm, "admin_p")

    override_db(db_session)
    mock_auth(client, admin)

    resp = client.get(f"/api/v1/projects/{project.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(project.id)


# ---------------------------------------------------------------------------
# 3. Cross-project access fails for all resource types
# ---------------------------------------------------------------------------

def test_pm_cannot_see_unassigned_project(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm_a = make_user(db_session, role_pm, "pma")
    pm_b = make_user(db_session, role_pm, "pmb")
    dept = make_department(db_session)
    proj_a = make_project(db_session, dept, pm_a, "pa")
    proj_b = make_project(db_session, dept, pm_b, "pb")
    assign(db_session, pm_a, proj_a)
    assign(db_session, pm_b, proj_b)

    override_db(db_session)
    mock_auth(client, pm_a)

    # pm_a cannot see proj_b's ID
    resp = client.get(f"/api/v1/projects/{proj_b.id}")
    assert resp.status_code == 403

    # pm_a list shows only proj_a
    resp = client.get("/api/v1/projects/")
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()]
    assert str(proj_a.id) in ids
    assert str(proj_b.id) not in ids


def test_cross_project_contract_access(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm_a = make_user(db_session, role_pm, "cpma")
    pm_b = make_user(db_session, role_pm, "cpmb")
    dept = make_department(db_session)
    proj_a = make_project(db_session, dept, pm_a, "cpa")
    proj_b = make_project(db_session, dept, pm_b, "cpb")
    assign(db_session, pm_a, proj_a)
    assign(db_session, pm_b, proj_b)
    contractor = make_contractor(db_session, "cc")
    contract_b = make_contract(db_session, proj_b, contractor, "cb")

    override_db(db_session)
    mock_auth(client, pm_a)

    # pm_a cannot read contract_b
    resp = client.get(f"/api/v1/contracts/{contract_b.id}")
    assert resp.status_code == 403

    # pm_a cannot create a contract in proj_b
    resp = client.post("/api/v1/contracts/", json={
        "project_id": str(proj_b.id),
        "contractor_id": str(contractor.id),
        "contract_number": f"CROSS-{uuid.uuid4()}",
        "award_date": str(date.today()),
        "start_date": str(date.today()),
        "original_completion_date": str(date.today()),
        "current_completion_date": str(date.today()),
        "contract_value": 1000,
    })
    assert resp.status_code == 403


def test_cross_project_boq_access(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm_a = make_user(db_session, role_pm, "boqa")
    pm_b = make_user(db_session, role_pm, "boqb")
    dept = make_department(db_session)
    proj_a = make_project(db_session, dept, pm_a, "boqpa")
    proj_b = make_project(db_session, dept, pm_b, "boqpb")
    assign(db_session, pm_a, proj_a)
    contractor = make_contractor(db_session, "boqc")
    contract_b = make_contract(db_session, proj_b, contractor, "boqcb")
    boq_b = Boq(
        contract_id=contract_b.id,
        boq_number=f"BOQ-{uuid.uuid4()}",
        title="BOQ B",
        status="Draft",
    )
    db_session.add(boq_b)
    db_session.flush()

    override_db(db_session)
    mock_auth(client, pm_a)

    # pm_a cannot read BOQ from proj_b
    resp = client.get(f"/api/v1/boqs/{boq_b.id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. Mismatched project/contract/resource IDs are rejected
# ---------------------------------------------------------------------------

def test_mismatched_project_id_on_contract_create(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm = make_user(db_session, role_pm, "mismatch")
    dept = make_department(db_session)
    proj_a = make_project(db_session, dept, pm, "mpa")
    proj_b = make_project(db_session, dept, pm, "mpb")
    assign(db_session, pm, proj_a)
    contractor = make_contractor(db_session, "mc")

    override_db(db_session)
    mock_auth(client, pm)

    # PM is assigned to proj_a only, trying to create contract for proj_b
    resp = client.post("/api/v1/contracts/", json={
        "project_id": str(proj_b.id),
        "contractor_id": str(contractor.id),
        "contract_number": f"MIS-{uuid.uuid4()}",
        "award_date": str(date.today()),
        "start_date": str(date.today()),
        "original_completion_date": str(date.today()),
        "current_completion_date": str(date.today()),
        "contract_value": 1000,
    })
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 5. Assignment creation/revocation policy
# ---------------------------------------------------------------------------

def test_admin_can_create_and_revoke_assignment(db_session, client):
    role_admin = make_role(db_session, "Admin")
    role_pm = make_role(db_session, "Project Manager")
    admin = make_user(db_session, role_admin, "asgnadmin")
    pm = make_user(db_session, role_pm, "asgnpm")
    dept = make_department(db_session)
    project = make_project(db_session, dept, pm, "asgnp")

    override_db(db_session)
    mock_auth(client, admin)

    # Create assignment
    resp = client.post("/api/v1/assignments/", json={
        "user_id": str(pm.id),
        "project_id": str(project.id),
    })
    assert resp.status_code == 201
    assignment_id = resp.json()["id"]

    # Audit log entry should exist for ASSIGN
    audit_entries = db_session.query(AuditLog).filter_by(
        entity_name="UserProjectAssignment",
        action="ASSIGN",
    ).all()
    assert any(str(assignment_id) in str(e.entity_id) for e in audit_entries)

    # Revoke
    resp = client.delete(f"/api/v1/assignments/{assignment_id}")
    assert resp.status_code == 204

    # Audit log entry for REVOKE
    audit_entries = db_session.query(AuditLog).filter_by(
        entity_name="UserProjectAssignment",
        action="REVOKE",
    ).all()
    assert len(audit_entries) > 0


def test_pm_cannot_self_assign(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm = make_user(db_session, role_pm, "selfpm")
    dept = make_department(db_session)
    project = make_project(db_session, dept, pm, "selfp")
    assign(db_session, pm, project)  # pm already has access to this project

    override_db(db_session)
    mock_auth(client, pm)

    # PM tries to assign themselves to the same project
    resp = client.post("/api/v1/assignments/", json={
        "user_id": str(pm.id),
        "project_id": str(project.id),
    })
    assert resp.status_code == 403


def test_pm_cannot_assign_to_unmanaged_project(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm_a = make_user(db_session, role_pm, "pmassign_a")
    pm_b = make_user(db_session, role_pm, "pmassign_b")
    dept = make_department(db_session)
    proj_a = make_project(db_session, dept, pm_a, "asgnpa")
    proj_b = make_project(db_session, dept, pm_b, "asgnpb")
    assign(db_session, pm_a, proj_a)
    # pm_a does NOT have access to proj_b

    override_db(db_session)
    mock_auth(client, pm_a)

    # pm_a cannot grant pm_b access to proj_b (which pm_a doesn't manage)
    resp = client.post("/api/v1/assignments/", json={
        "user_id": str(pm_b.id),
        "project_id": str(proj_b.id),
    })
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6. Revocation takes effect on the next request
# ---------------------------------------------------------------------------

def test_revocation_takes_effect_immediately(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    role_admin = make_role(db_session, "Admin")
    admin = make_user(db_session, role_admin, "revadmin")
    pm = make_user(db_session, role_pm, "revpm")
    dept = make_department(db_session)
    project = make_project(db_session, dept, pm, "revp")
    assignment = assign(db_session, pm, project)

    override_db(db_session)

    # PM can access the project
    mock_auth(client, pm)
    resp = client.get(f"/api/v1/projects/{project.id}")
    assert resp.status_code == 200

    # Admin revokes
    mock_auth(client, admin)
    resp = client.delete(f"/api/v1/assignments/{assignment.id}")
    assert resp.status_code == 204

    # PM can no longer access the project on the next request
    mock_auth(client, pm)
    resp = client.get(f"/api/v1/projects/{project.id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 7. Duplicate assignment is rejected without partial write
# ---------------------------------------------------------------------------

def test_duplicate_assignment_rejected(db_session, client):
    role_admin = make_role(db_session, "Admin")
    role_pm = make_role(db_session, "Project Manager")
    admin = make_user(db_session, role_admin, "dupadmin")
    pm = make_user(db_session, role_pm, "duppm")
    dept = make_department(db_session)
    project = make_project(db_session, dept, pm, "dupp")

    override_db(db_session)
    mock_auth(client, admin)

    # First assignment
    resp = client.post("/api/v1/assignments/", json={
        "user_id": str(pm.id),
        "project_id": str(project.id),
    })
    assert resp.status_code == 201

    # Duplicate
    resp = client.post("/api/v1/assignments/", json={
        "user_id": str(pm.id),
        "project_id": str(project.id),
    })
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"].lower()

    # Exactly one assignment record should exist
    count = db_session.query(UserProjectAssignment).filter(
        UserProjectAssignment.user_id == pm.id,
        UserProjectAssignment.project_id == project.id,
    ).count()
    assert count == 1


# ---------------------------------------------------------------------------
# 8. PM cannot revoke their own access
# ---------------------------------------------------------------------------

def test_pm_cannot_revoke_own_access(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm = make_user(db_session, role_pm, "selfrevoke")
    dept = make_department(db_session)
    project = make_project(db_session, dept, pm, "selfrp")
    assignment = assign(db_session, pm, project)

    override_db(db_session)
    mock_auth(client, pm)

    resp = client.delete(f"/api/v1/assignments/{assignment.id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 9. Assignment GET list scoping
# ---------------------------------------------------------------------------

def test_admin_can_list_all_assignments(db_session, client):
    role_admin = make_role(db_session, "Admin")
    role_pm = make_role(db_session, "Project Manager")
    admin = make_user(db_session, role_admin, "listadmin")
    pm1 = make_user(db_session, role_pm, "listpm1")
    pm2 = make_user(db_session, role_pm, "listpm2")
    dept = make_department(db_session)
    p1 = make_project(db_session, dept, pm1, "lp1")
    p2 = make_project(db_session, dept, pm2, "lp2")
    a1 = assign(db_session, pm1, p1)
    a2 = assign(db_session, pm2, p2)

    override_db(db_session)
    mock_auth(client, admin)

    resp = client.get("/api/v1/assignments/")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert str(a1.id) in ids
    assert str(a2.id) in ids


def test_pm_sees_only_own_project_assignments(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm_a = make_user(db_session, role_pm, "listpma")
    pm_b = make_user(db_session, role_pm, "listpmb")
    dept = make_department(db_session)
    proj_a = make_project(db_session, dept, pm_a, "llpa")
    proj_b = make_project(db_session, dept, pm_b, "llpb")
    a1 = assign(db_session, pm_a, proj_a)
    a2 = assign(db_session, pm_b, proj_b)

    override_db(db_session)
    mock_auth(client, pm_a)

    resp = client.get("/api/v1/assignments/")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert str(a1.id) in ids
    assert str(a2.id) not in ids


# ---------------------------------------------------------------------------
# 10. EVM endpoint project isolation
# ---------------------------------------------------------------------------

def test_evm_endpoint_cross_project_denied(db_session, client):
    role_pm = make_role(db_session, "Project Manager")
    pm_a = make_user(db_session, role_pm, "evma")
    pm_b = make_user(db_session, role_pm, "evmb")
    dept = make_department(db_session)
    proj_a = make_project(db_session, dept, pm_a, "evmpa")
    proj_b = make_project(db_session, dept, pm_b, "evmpb")
    assign(db_session, pm_a, proj_a)

    override_db(db_session)
    mock_auth(client, pm_a)

    resp = client.get(f"/api/v1/projects/{proj_b.id}/evm", params={"as_of_date": "2026-06-30"})
    assert resp.status_code == 403

    resp = client.get(f"/api/v1/projects/{proj_b.id}/evm/trend")
    assert resp.status_code == 403
