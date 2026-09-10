# InfraPM Intelligence

Sprint 1 foundation for an infrastructure project controls and contract-management platform.

## Sprint 1 scope

- JWT authentication
- Role-based access control
- Departments
- Contractors
- Project Registry
- Append-only audit logging
- PostgreSQL + SQLAlchemy
- Alembic migrations
- React/Vite frontend shell
- Pytest API tests

Not included yet: Contracts, BOQ, Measurements, RA Billing, EVM, ML, RAG.

## Architecture

React/Vite frontend -> FastAPI REST API -> service layer -> SQLAlchemy -> PostgreSQL

The service layer owns transaction boundaries. Audit records are added to the same transaction as the business change.

## Prerequisites

- macOS Apple Silicon
- Python 3.11+
- Node.js 18+
- Docker Desktop or OrbStack

## Setup

### 1. Start PostgreSQL

```bash
cd infra-pm
docker compose up -d
docker compose ps
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
cp ../.env.example .env
pip install -r requirements.txt
alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --reload --port 8000
```

API docs:
http://localhost:8000/docs

### 3. Frontend

Open another terminal:

```bash
cd infra-pm/frontend
npm install
npm run dev
```

Frontend:
http://localhost:5173

## Development login

These credentials are synthetic and for local development only:

- admin@infrapm.gov / Admin@123
- pm@infrapm.gov / PM@123
- eng@infrapm.gov / Eng@123
- billing@infrapm.gov / Bill@123
- viewer@infrapm.gov / View@123

Do not use these credentials outside local development.

## Tests

With PostgreSQL running:

```bash
cd backend
source .venv/bin/activate
pytest -v
```

## Useful commands

```bash
docker compose up -d
docker compose ps
docker compose logs db
docker compose down
alembic upgrade head
alembic current
pytest -v
```

## Sprint roadmap

V1: Core data, execution tracking, billing and EVM
V2: Contract administration and documents
V3: Predictive intelligence
V4: Generative intelligence / RAG
