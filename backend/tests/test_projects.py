
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.core.config import settings
from app.main import app
from app.models.department import Department


@pytest.fixture
def client():
    engine = create_engine(settings.DATABASE_URL)
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    from fastapi.testclient import TestClient

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        transaction.rollback()
        connection.close()
        engine.dispose()


def get_token(client, email, password):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_viewer_cannot_create_project(client):
    token = get_token(client, "viewer@infrapm.gov", "View@123")

    # Create the required department within this test's transaction.
    connection = create_engine(settings.DATABASE_URL)
    try:
        with connection.begin() as db_connection:
            TestSession = sessionmaker(bind=db_connection)
            with TestSession() as db:
                department = Department(
                    code=f"VIEW-{uuid.uuid4().hex[:12]}",
                    name="Viewer Permission Test Department",
                )
                db.add(department)
                db.flush()
                department_id = str(department.id)
                db.flush()
    finally:
        connection.dispose()

    pm_token = get_token(client, "pm@infrapm.gov", "PM@123")
    projects = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert projects.status_code == 200

    payload = {
        "code": f"TEST-VIEWER-{uuid.uuid4().hex[:8]}",
        "name": "Unauthorized Test Project",
        "dept_id": department_id,
        "pm_id": (
            projects.json()[0]["pm_id"]
            if projects.json()
            else "00000000-0000-0000-0000-000000000000"
        ),
        "total_estimated_cost": "10.00",
        "start_date": "2026-09-01",
        "expected_completion": "2027-09-01",
    }

    response = client.post(
        "/api/v1/projects",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_projects_are_readable_by_authenticated_user(client):
    token = get_token(client, "viewer@infrapm.gov", "View@123")
    response = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
