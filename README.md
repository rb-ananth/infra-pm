# InfraPM Intelligence

A production-ready infrastructure project controls and contract-management platform foundation.

**Purpose**: To provide a traceable, auditable, and immutable source of truth for construction projects, contract administration, billing, Extension of Time (EOT) applications, and Earned Value Management (EVM), serving as a clean deterministic foundation for future AI and RAG capabilities.

**Target Users**: Project Managers, Billing Engineers, Site Engineers, and Administrators in large-scale infrastructure and construction sectors.

## Key Capabilities
- **Auth & RBAC**: JWT login, global roles (Admin, Project Manager, Engineer, Billing Engineer, Viewer).
- **Core Registries**: Projects, Departments, Contractors.
- **Contracts & BOQ**: Contract definitions, Bill of Quantities (BOQ), and revision tracking.
- **Measurements**: Physical execution tracking via Measurement Books.
- **RA Billing**: Cumulative and snapshot billing, automated derivation from measurements.
- **EOT (Extension of Time)**: Full workflow for managing, submitting, reviewing, and approving timeline extensions natively updating contract timelines.
- **EVM (Earned Value Management)**: Automated Planned Value (PV), Earned Value (EV), and Actual Cost (AC) period metrics.
- **Document Intelligence V1**: Extraction, structural validation, and canonical reconciliation of Contracts, BOQs, Measurement Books, RA Bills, and EVM reports. **Note**: Currently uses deterministic pattern-based extraction with foundational hooks; full LLM/RAG semantic embeddings are planned for V2.

## High-Level Architecture
`React/TypeScript Frontend` -> `FastAPI REST API` -> `Service Layer` -> `SQLAlchemy ORM` -> `PostgreSQL`

**Transaction Safety**: The service layer explicitly manages transaction boundaries. Business logic, document fact persistence, and audit logging all execute within the same ACID transaction. If an error occurs, the entire operation is rolled back, preventing orphaned or corrupt records.

See [docs/architecture.md](docs/architecture.md) for detailed architecture and data flows.

## Quick Start (Docker Compose)

The fastest way to run the entire stack (Database, Backend API, and Frontend) locally is using Docker Compose.

### Prerequisites
- Docker Desktop or OrbStack
- Git

### Launch the Application
```bash
# 1. Start the stack (this will build the DB, apply migrations, and start the app)
docker compose up -d

# 2. Seed the isolated demo database (run once)
docker compose exec backend python scripts/seed.py

# 3. View logs if necessary
docker compose logs -f
```

- **Frontend Application**: `http://localhost:5173`
- **Backend API & Swagger Docs**: `http://localhost:8000/docs`

## Manual Local Setup

If you prefer to run the services natively without Docker Compose for the application containers:

### 1. Database (PostgreSQL)
Ensure you have a PostgreSQL instance running, or start just the DB via Docker:
```bash
docker compose up -d db
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
fastapi run app/main.py --host 0.0.0.0 --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

## Demo Data & Synthetic Credentials

The repository includes a robust demonstration seed (`backend/scripts/seed.py`).
**DO NOT run the seed script against an existing populated database** as it provisions fixed canonical IDs.

The synthetic demonstration dataset includes:
- **₹48.50 Crore Project Value**
- **12 Approved Measurements**
- **3 Approved RA Bills**
- **1 Approved EVM Baseline**

### Verified Local Login Credentials
These credentials are for local development and demonstration only:
- **Admin**: `admin@infrapm.gov` / `Admin@123`
- **Project Manager**: `pm@infrapm.gov` / `PM@123`
- **Engineer**: `eng@infrapm.gov` / `Eng@123`
- **Billing Engineer**: `billing@infrapm.gov` / `Bill@123`
- **Viewer**: `viewer@infrapm.gov` / `View@123`

## Screenshots

*(Placeholder: EOT Application Workflow)*
`![EOT Application Workflow](docs/assets/eot_workflow.png)`

*(Placeholder: EVM Dashboard)*
`![EVM Dashboard](docs/assets/evm_dashboard.png)`

## Current Limitations & Planned Features

### Known Limitations
- Global RBAC (no strict row-level / project-level security).
- Data extraction is currently pattern-based (Regex/Pandas) and runs synchronously.

### Future Roadmap
- **Predictive AI**: Cost and schedule overrun forecasting natively integrated into EVM.
- **Generative AI & RAG**: Semantic querying over vector-embedded `DocumentChunk` data.
