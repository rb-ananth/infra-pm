
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_current_user, get_db
from app.models.role import Role
from app.models.user import User, UserProjectAssignment
from app.models.project import Project
from app.models.department import Department


@pytest.fixture
def db_session():
    """Use the configured test database and roll back test changes."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings

    engine = create_engine(settings.DATABASE_URL)
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=connection,
        join_transaction_mode="create_savepoint",
    )
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_user(db, role_name):
    role = db.query(Role).filter_by(name=role_name).first()
    if role is None:
        role = Role(name=role_name)
        db.add(role)
        db.flush()

    user = User(
        email=f"rag-{uuid.uuid4().hex}@test.com",
        password_hash="test-only",
        role_id=role.id,
    )
    db.add(user)
    db.flush()
    return user


def make_project(db, user):
    department = Department(
        code=f"RAG-{uuid.uuid4().hex[:10]}",
        name="RAG Endpoint Test Department",
    )
    db.add(department)
    db.flush()

    project = Project(
        code=f"RAG-{uuid.uuid4().hex[:10]}",
        name="RAG Endpoint Test Project",
        dept_id=department.id,
        pm_id=user.id,
        status="Active",
        total_estimated_cost=100000,
        start_date="2026-01-01",
        expected_completion="2027-01-01",
    )
    db.add(project)
    db.flush()
    return project


def configure_request(client, db, user):
    def override_db():
        yield db

    def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user


def test_ask_returns_answer_and_source_metadata(db_session, client):
    user = make_user(db_session, "Project Manager")
    project = make_project(db_session, user)

    db_session.add(
        UserProjectAssignment(user_id=user.id, project_id=project.id)
    )
    db_session.flush()
    configure_request(client, db_session, user)

    chunk_id = uuid.uuid4()
    document_id = uuid.uuid4()

    mocked_result = {
        "question": "What is the project status?",
        "project_id": project.id,
        "answer": "The evidence identifies pending work. [1]",
        "sources": [
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "document_name": "Progress Report",
                "source_filename": "progress.pdf",
                "page_number": 2,
                "sheet_name": None,
                "row_start": None,
                "row_end": None,
                "section": "Progress",
                "clause_reference": None,
            }
        ],
        "insufficient_evidence": False,
    }

    with patch(
        "app.api.routers.documents.answer_project_question",
        return_value=mocked_result,
    ) as mocked_rag:
        response = client.post(
            "/api/v1/documents/ask",
            json={
                "project_id": str(project.id),
                "question": "What is the project status?",
                "limit": 5,
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"] == mocked_result["answer"]
    assert body["insufficient_evidence"] is False
    assert len(body["sources"]) == 1
    assert body["sources"][0]["document_name"] == "Progress Report"
    mocked_rag.assert_called_once()


def test_ask_returns_insufficient_evidence(db_session, client):
    user = make_user(db_session, "Project Manager")
    project = make_project(db_session, user)

    db_session.add(
        UserProjectAssignment(user_id=user.id, project_id=project.id)
    )
    db_session.flush()
    configure_request(client, db_session, user)

    with patch(
        "app.api.routers.documents.answer_project_question",
        return_value={
            "question": "What is the project status?",
            "project_id": project.id,
            "answer": "No relevant evidence was found.",
            "sources": [],
            "insufficient_evidence": True,
        },
    ):
        response = client.post(
            "/api/v1/documents/ask",
            json={
                "project_id": str(project.id),
                "question": "What is the project status?",
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["insufficient_evidence"] is True
    assert response.json()["sources"] == []


def test_ask_rejects_cross_project_access(db_session, client):
    user = make_user(db_session, "Project Manager")
    project = make_project(db_session, user)

    # Deliberately do not assign this user to the project.
    db_session.flush()
    configure_request(client, db_session, user)

    with patch(
        "app.api.routers.documents.answer_project_question"
    ) as mocked_rag:
        response = client.post(
            "/api/v1/documents/ask",
            json={
                "project_id": str(project.id),
                "question": "What is the project status?",
            },
        )

    assert response.status_code == 403, response.text
    mocked_rag.assert_not_called()


def test_ask_rejects_invalid_question(db_session, client):
    user = make_user(db_session, "Project Manager")
    project = make_project(db_session, user)

    db_session.add(
        UserProjectAssignment(user_id=user.id, project_id=project.id)
    )
    db_session.flush()
    configure_request(client, db_session, user)

    response = client.post(
        "/api/v1/documents/ask",
        json={
            "project_id": str(project.id),
            "question": "",
        },
    )

    assert response.status_code == 422


def test_ask_handles_llm_failure(db_session, client):
    user = make_user(db_session, "Project Manager")
    project = make_project(db_session, user)

    db_session.add(
        UserProjectAssignment(user_id=user.id, project_id=project.id)
    )
    db_session.flush()
    configure_request(client, db_session, user)

    from app.services.rag_service import RAGServiceError

    with patch(
        "app.api.routers.documents.answer_project_question",
        side_effect=RAGServiceError("Internal test error"),
    ):
        response = client.post(
            "/api/v1/documents/ask",
            json={
                "project_id": str(project.id),
                "question": "What is the project status?",
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "The project question service is temporarily unavailable."
    )
