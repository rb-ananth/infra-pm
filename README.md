# InfraPM Intelligence

An AI-assisted infrastructure project management and contract administration platform, combining deterministic project controls with document intelligence and retrieval-augmented generation (RAG).

## Purpose

Provide a traceable foundation for construction project data, contract administration, billing, Extension of Time (EOT) applications and Earned Value Management (EVM), with document-based question answering grounded in retrieved evidence.

## Target Users

Project Managers, Billing Engineers, Site Engineers and Administrators in infrastructure and construction organizations.

## Key Capabilities

- **Authentication and RBAC:** JWT authentication and role-based access control.
- **Core Registries:** Projects, departments and contractors.
- **Contracts and BOQ:** Contract definitions, Bills of Quantities and revision tracking.
- **Measurements and RA Billing:** Physical execution tracking and billing workflows.
- **EOT Management:** Application, submission, review, approval and rejection workflows.
- **Earned Value Management:** Planned Value (PV), Earned Value (EV) and Actual Cost (AC) metrics.
- **Document Intelligence:** Document parsing, structured extraction, validation and reconciliation.
- **Document Q&A with RAG:** Embeddings, similarity-based retrieval, project-scoped retrieval logic, source metadata and citation validation, with insufficient-evidence handling.

## Technology Stack

- **Backend:** Python, FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL with pgvector
- **Frontend:** React, TypeScript, Vite
- **AI and Retrieval:** Ollama-based embeddings and LLM generation, vector similarity search
- **Testing:** Pytest and frontend production build

## Architecture

React/TypeScript frontend → FastAPI REST API → Service layer → SQLAlchemy → PostgreSQL/pgvector

The document Q&A workflow ingests and parses documents, generates embeddings, retrieves relevant chunks and passes the retrieved evidence to an LLM to generate a contextual response.

See [docs/architecture.md](docs/architecture.md) for the detailed architecture.

## Quick Start

### Prerequisites

- Docker Desktop or OrbStack
- Git

### Start the application

```bash
docker compose up -d
```

The application exposes the following local services:

- Frontend: http://localhost:5173
- Backend API documentation: http://localhost:8000/docs

Follow the repository's environment and database setup instructions before running migrations or seeding data. **Do not run the seed script against an existing populated database**; it provisions fixed canonical IDs.

## Testing

The project includes automated backend tests covering project and contract workflows, EOT management, document processing, retrieval and RAG behavior.

The latest recorded verification in the development environment included:

- Backend regression suite: 175 passed, 1 skipped
- Golden-dataset suite: 20 passed
- Focused EOT and RAG suite: 29 passed
- Frontend production build: passed

These are recorded development results, not a claim of production deployment or independent validation.

## Known Limitations

- Project-level authorization and isolation require further security review before production use.
- RAG citation validation checks citation references; it does not independently prove that every claim is entailed by its cited source.
- Retrieval relevance and answer quality require broader evaluation on representative project documents.
- Document extraction behavior depends on document structure and the implemented parsing rules.
- Production deployment, monitoring, backup/restore and operational recovery have not been fully validated.

## Roadmap

- Evaluate retrieval quality and grounded answer accuracy on a representative document set.
- Expand project-level authorization and security testing.
- Develop and validate predictive cost and schedule risk models.
- Improve operational observability and deployment readiness.
