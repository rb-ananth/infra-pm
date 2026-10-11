import uuid

from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.contractor import Contractor

import pytest
from app.main import app
from app.api.deps import get_db
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from app.core.config import settings

from app.models.user import User
from app.models.role import Role
from app.core.security import get_password_hash

@pytest.fixture
def client():
    engine = create_engine(settings.DATABASE_URL)
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")

    def override_get_db():
        session = TestingSessionLocal()
        yield session
        session.close()

    app.dependency_overrides[get_db] = override_get_db
        # Create test accounts within the test's rollbackable transaction.
    db = TestingSessionLocal()
    try:
        test_users = [
            ("admin@infrapm.gov", "Admin@123", "Admin"),
            ("pm@infrapm.gov", "PM@123", "Project Manager"),
            ("viewer@infrapm.gov", "View@123", "Viewer"),
            ("eng@infrapm.gov", "Eng@123", "Engineer"),
        ]

        for email, password, role_name in test_users:
            role = db.query(Role).filter_by(name=role_name).first()
            if role is None:
                role = Role(name=role_name)
                db.add(role)
                db.flush()

            user = db.query(User).filter_by(email=email).first()
            if user is None:
                user = User(
                    email=email,
                    password_hash=get_password_hash(password),
                    role_id=role.id,
                    is_active=True,
                )
                db.add(user)
            else:
                user.password_hash = get_password_hash(password)
                user.role_id = role.id
                user.is_active = True

        db.flush()
    finally:
        db.close()
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    transaction.rollback()
    connection.close()



def login(client, email, password):
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": email,
            "password": password,
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_create_contractor(client):
    token = login(client, "admin@infrapm.gov", "Admin@123")

    response = client.post(
        "/api/v1/contractors/",
        headers=auth_headers(token),
        json={
            "registration_number": f"TEST-{uuid.uuid4().hex[:8]}",
            "name": "Test Infrastructure Contractor",
            "status": "Active",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["name"] == "Test Infrastructure Contractor"
    assert data["status"] == "Active"
    assert data["registration_number"].startswith("TEST-")


def test_duplicate_registration_number_returns_409(client):
    registration_number = f"DUP-{uuid.uuid4().hex[:8]}"

    token = login(client, "admin@infrapm.gov", "Admin@123")

    first_response = client.post(
        "/api/v1/contractors/",
        headers=auth_headers(token),
        json={
            "registration_number": registration_number,
            "name": "Existing Contractor",
            "status": "Active",
        },
    )

    assert first_response.status_code == 200

    second_response = client.post(
        "/api/v1/contractors/",
        headers=auth_headers(token),
        json={
            "registration_number": registration_number,
            "name": "Duplicate Contractor",
            "status": "Active",
        },
    )

    assert second_response.status_code == 409


def test_authenticated_user_can_list_contractors(client):
    token = login(client, "viewer@infrapm.gov", "View@123")

    response = client.get(
        "/api/v1/contractors/",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_non_admin_cannot_create_contractor(client):
    token = login(client, "pm@infrapm.gov", "PM@123")

    response = client.post(
        "/api/v1/contractors/",
        headers=auth_headers(token),
        json={
            "registration_number": f"PM-{uuid.uuid4().hex[:8]}",
            "name": "Unauthorized Contractor",
            "status": "Active",
        },
    )

    assert response.status_code == 403


def test_admin_can_update_contractor(client):
    registration_number = f"UPD-{uuid.uuid4().hex[:8]}"

    token = login(client, "admin@infrapm.gov", "Admin@123")

    create_response = client.post(
        "/api/v1/contractors/",
        headers=auth_headers(token),
        json={
            "registration_number": registration_number,
            "name": "Update Test Contractor",
            "status": "Active",
        },
    )

    assert create_response.status_code == 200
    contractor_id = create_response.json()["id"]

    response = client.put(
        f"/api/v1/contractors/{contractor_id}",
        headers=auth_headers(token),
        json={
            "status": "Suspended",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "Suspended"


def test_non_admin_cannot_update_contractor(client):
    admin_token = login(client, "admin@infrapm.gov", "Admin@123")

    create_response = client.post(
        "/api/v1/contractors/",
        headers=auth_headers(admin_token),
        json={
            "registration_number": f"DENY-{uuid.uuid4().hex[:8]}",
            "name": "Permission Test Contractor",
            "status": "Active",
        },
    )

    assert create_response.status_code == 200
    contractor_id = create_response.json()["id"]

    engineer_token = login(client, "eng@infrapm.gov", "Eng@123")

    response = client.put(
        f"/api/v1/contractors/{contractor_id}",
        headers=auth_headers(engineer_token),
        json={
            "status": "Inactive",
        },
    )

    assert response.status_code == 403


def test_contractor_changes_are_audited(client):
    token = login(client, "admin@infrapm.gov", "Admin@123")

    registration_number = f"AUD-{uuid.uuid4().hex[:8]}"

    response = client.post(
        "/api/v1/contractors/",
        headers=auth_headers(token),
        json={
            "registration_number": registration_number,
            "name": "Audited Contractor",
            "status": "Active",
        },
    )

    assert response.status_code == 200
    contractor_id = uuid.UUID(response.json()["id"])

    db = next(app.dependency_overrides[get_db]())
    try:
        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_name == "Contractor",
                AuditLog.entity_id == contractor_id,
                AuditLog.action == "CREATE",
            )
            .first()
        )

        assert audit is not None
        assert audit.changes["name"] == "Audited Contractor"
        assert audit.changes["registration_number"] == registration_number
    finally:
        db.close()
