# InfraPM Intelligence — Development Instructions

## Project

InfraPM Intelligence is an infrastructure project management and project-controls
platform.

The application combines:

- Construction project management
- Contract management
- BOQ / estimation
- Quantity measurement
- RA billing
- Progress monitoring
- Earned Value Management
- Cost analytics
- Predictive analytics
- Future AI/RAG capabilities

The goal is a portfolio-quality production-style application, not a generic CRUD demo.

## Architecture

Backend:

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic
- Pydantic

Frontend:

- React
- TypeScript
- Vite
- Axios
- React Router

## Architectural principles

1. Keep business logic in service modules.
2. Keep API routers thin.
3. Use Pydantic schemas for request/response validation.
4. Use PostgreSQL NUMERIC/DECIMAL for monetary values.
5. Use UUID primary keys.
6. Use timezone-aware timestamps.
7. Use database foreign keys for relationships.
8. Preserve auditability of important business transactions.
9. Avoid hard deletion of important transactional records.
10. Prefer deactivation/status changes where appropriate.
11. Do not introduce unnecessary dependencies.
12. Do not rewrite existing working modules without a clear reason.
13. Preserve existing RBAC behavior.
14. Do not introduce mock data into API-backed production screens.
15. Run relevant tests/builds after meaningful changes.

## Current module dependency

Project
↓
Contract
↓
BOQ
↓
Measurements
↓
RA Billing
↓
Progress / EVM
↓
Cost Analytics
↓
Predictive Analytics
↓
AI / RAG

Do not bypass these dependencies without explicit instruction.

## BOQ principles

BOQ items should preserve:

- item number
- description
- unit
- quantity
- rate
- calculated amount

Amount should be derived from:

quantity × rate

BOQ must eventually support Excel/CSV import with validation and preview.

## Frontend principles

Use the existing InfraPM visual language.

Prefer:

- clean enterprise layout
- tables for registries
- clear status badges
- responsive forms
- loading states
- empty states
- error states

Do not replace existing UI architecture unnecessarily.

## Git

Do not commit secrets.

Never commit:

- .env
- API keys
- passwords
- tokens
- credentials

Before committing:

- run tests
- run frontend build when frontend changes
- inspect git diff
- inspect git status

Use focused commits describing the completed feature.

## Working style

Before making a large architectural change:

- inspect the existing implementation
- explain the proposed change
- make the smallest safe change

Do not blindly regenerate existing files.

When a requirement is ambiguous, inspect the existing architecture before inventing new behavior.
