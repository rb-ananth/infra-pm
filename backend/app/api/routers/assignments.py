import uuid
from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    get_current_user,
    require_roles,
    get_allowed_project_ids,
    verify_project_access,
    ADMIN_BYPASS,
)
from app.models.user import User, UserProjectAssignment
from app.services.audit_service import add_audit_log


class AssignmentCreate(BaseModel):
    user_id: uuid.UUID
    project_id: uuid.UUID


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    assigned_by_id: uuid.UUID | None
    assigned_at: datetime


router = APIRouter(prefix="/assignments", tags=["Assignments"])


@router.get("/", response_model=List[AssignmentOut])
def list_assignments(
    project_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects=Depends(get_allowed_project_ids),
):
    """List project assignments.

    - Admin: sees all assignments, optionally filtered by project_id.
    - Project Manager: sees only assignments for projects they are authorized to manage.
    """
    query = db.query(UserProjectAssignment)

    if allowed_projects is not ADMIN_BYPASS:
        query = query.filter(UserProjectAssignment.project_id.in_(allowed_projects))

    if project_id is not None:
        verify_project_access(project_id, allowed_projects)
        query = query.filter(UserProjectAssignment.project_id == project_id)

    return query.order_by(UserProjectAssignment.assigned_at.desc()).all()


@router.post("/", response_model=AssignmentOut, status_code=201)
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects=Depends(get_allowed_project_ids),
):
    """Create a project assignment.

    Admin: can assign any user to any project.
    Project Manager: can assign other users only to projects they already manage.
    PMs cannot assign themselves.
    """
    verify_project_access(payload.project_id, allowed_projects)

    if current_user.role.name != "Admin" and payload.user_id == current_user.id:
        raise HTTPException(status_code=403, detail="Cannot assign yourself to a project.")

    target_user = db.query(User).filter(User.id == payload.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")

    exists = db.query(UserProjectAssignment).filter(
        UserProjectAssignment.user_id == payload.user_id,
        UserProjectAssignment.project_id == payload.project_id,
    ).first()

    if exists:
        raise HTTPException(status_code=400, detail="Assignment already exists.")

    assignment = UserProjectAssignment(
        user_id=payload.user_id,
        project_id=payload.project_id,
        assigned_by_id=current_user.id,
    )
    db.add(assignment)
    db.flush()

    add_audit_log(
        db,
        current_user.id,
        "UserProjectAssignment",
        assignment.id,
        "ASSIGN",
        {
            "actor_id": str(current_user.id),
            "target_user_id": str(payload.user_id),
            "project_id": str(payload.project_id),
        },
    )

    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{assignment_id}", status_code=204)
def remove_assignment(
    assignment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects=Depends(get_allowed_project_ids),
):
    """Revoke a project assignment.

    Admin: can revoke any assignment.
    Project Manager: can revoke for projects they manage; cannot revoke own access.
    Revocation takes effect immediately on the next request.
    """
    assignment = db.query(UserProjectAssignment).filter(
        UserProjectAssignment.id == assignment_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    verify_project_access(assignment.project_id, allowed_projects)

    if current_user.role.name != "Admin" and assignment.user_id == current_user.id:
        raise HTTPException(status_code=403, detail="Cannot revoke your own access.")

    add_audit_log(
        db,
        current_user.id,
        "UserProjectAssignment",
        assignment.id,
        "REVOKE",
        {
            "actor_id": str(current_user.id),
            "target_user_id": str(assignment.user_id),
            "project_id": str(assignment.project_id),
        },
    )

    db.delete(assignment)
    db.commit()
