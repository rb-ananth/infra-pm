from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import audit_logs, auth, contractors, contracts, departments, projects, users
from app.core.config import settings

app = FastAPI(
    title="InfraPM Intelligence API",
    description="Sprint 1 - Core project registry, authentication, RBAC and audit foundation.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(departments.router, prefix="/api/v1/departments", tags=["Departments"])
app.include_router(contractors.router, prefix="/api/v1/contractors", tags=["Contractors"])
app.include_router(contracts.router, prefix="/api/v1/contracts", tags=["Contracts"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["Projects"])
app.include_router(audit_logs.router, prefix="/api/v1/audit-logs", tags=["Audit Logs"])


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok"}
