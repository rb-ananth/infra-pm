# InfraPM Intelligence

A production-ready infrastructure project controls and contract-management platform foundation.

**Purpose**: To provide a traceable, auditable, and immutable source of truth for construction projects, contract administration, billing, and Earned Value Management (EVM), serving as a clean deterministic foundation for future AI and RAG capabilities.

**Target Users**: Project Managers, Billing Engineers, Site Engineers, and Administrators in large-scale infrastructure and construction sectors.

## Current Technology Stack
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL, Alembic (Migrations), Pytest.
- **Frontend**: React, TypeScript, Vite.
- **Security**: JWT Authentication, Role-Based Access Control (RBAC).

## Implemented Modules (V1 Complete)
- **Auth & RBAC**: JWT login, global roles (Admin, Project Manager, Engineer, Billing Engineer, Viewer).
- **Core Registries**: Projects, Departments, Contractors.
- **Contracts & BOQ**: Contract definitions, Bill of Quantities (BOQ), and revision tracking.
- **Measurements**: Physical execution tracking via Measurement Books.
- **RA Billing**: Cumulative and snapshot billing, automated derivation from measurements.
- **EVM**: Automated Planned Value (PV), Earned Value (EV), and Actual Cost (AC) period metrics.
- **Document Ingestion**: Storage and parsing of PDFs and XLSX files.
- **Document Intelligence V1**: Deterministic extraction, structural validation, and canonical reconciliation of Contracts, BOQs, Measurement Books, RA Bills, and EVM reports.
- **Audit**: Immutable, append-only logs attached directly to business transactions.

## High-Level Architecture & Data Flow
`React/Vite Frontend` -> `FastAPI REST API` -> `Service Layer` -> `SQLAlchemy ORM` -> `PostgreSQL`

**Transaction Safety**: The service layer explicitly manages transaction boundaries. Business logic, document fact persistence, and audit logging all execute within the same ACID transaction. If an error occurs, the entire operation is rolled back, preventing orphaned or corrupt records.

## Local Setup & Run

### Prerequisites
- macOS Apple Silicon / Linux / Windows WSL
- Python 3.11+
- Node.js 18+
- Docker Desktop or OrbStack

### 1. Database (PostgreSQL)
```bash
docker compose up -d
docker compose ps
```

### 2. Backend API
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
**API Docs available at**: `http://localhost:8000/docs`

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```
**App available at**: `http://localhost:5173`

## Development Login
These credentials are for local development only:
- admin@infrapm.gov / Admin@123
- pm@infrapm.gov / PM@123
- eng@infrapm.gov / Eng@123
- billing@infrapm.gov / Bill@123
- viewer@infrapm.gov / View@123

## Test Suite Results
*Executed on: 2026-10-09*
```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```
**Results**: 133 tests passed, 0 failures.

## Current Limitations & Planned Features
### Completed Functionality (V1)
- Deterministic extraction and canonical reconciliation.
- Complete core project controls, billing, and EVM mechanics.

### Known Limitations
- Global RBAC (no row-level / project-level security).
- Extraction is strictly pattern-based (Regex/Pandas) and runs synchronously.
- Synthetic evidence only supports predefined deterministic templates.

### Planned Features
- **Predictive AI**: Cost and schedule overrun forecasting.
- **Generative AI & RAG**: Semantic querying over vector-embedded `DocumentChunk` data.
