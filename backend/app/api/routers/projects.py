import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles, get_allowed_project_ids, verify_project_access, ADMIN_BYPASS
from app.core.database import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services import project_service

router = APIRouter()


@router.get("/", response_model=list[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    allowed_projects = Depends(get_allowed_project_ids)
):
    query = db.query(Project)
    if allowed_projects is not ADMIN_BYPASS:
        query = query.filter(Project.id.in_(allowed_projects))
    return query.order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    allowed_projects = Depends(get_allowed_project_ids)
):
    verify_project_access(project_id, allowed_projects)
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@router.post("/", response_model=ProjectResponse)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    # Atomic: project_service.create_project handles PM auto-assignment in the same transaction
    return project_service.create_project(db, data, current_user)


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    verify_project_access(project_id, allowed_projects)
    return project_service.update_project(db, project_id, data, current_user)
