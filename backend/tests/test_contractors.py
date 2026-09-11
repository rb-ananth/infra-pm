import uuid

from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.contractor import Contractor


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

    db = SessionLocal()
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
