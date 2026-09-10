import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure the backend directory is importable during pytest collection.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Tests expect PostgreSQL to be running and the schema to have been migrated.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://infra_user:infra_password@localhost:5432/infra_pm_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
