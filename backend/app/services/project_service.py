import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.project import Project
from app.models.role import Role
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.audit_service import add_audit_log


def _validate_project_references(db: Session, project_data) -> None:
    department = db.query(Department).filter(Department.id == project_data.dept_id).first()
    if not department or not department.is_active:
        raise HTTPException(status_code=400, detail="Active department not found.")

    manager = db.query(User).filter(User.id == project_data.pm_id).first()
    if not manager or not manager.is_active:
        raise HTTPException(status_code=400, detail="Active project manager not found.")

    role = db.query(Role).filter(Role.id == manager.role_id).first()
    if not role or role.name != "Project Manager":
        raise HTTPException(status_code=400, detail="Assigned user must have Project Manager role.")


def create_project(db: Session, data: ProjectCreate, current_user: User) -> Project:
    _validate_project_references(db, data)
    project = Project(**data.model_dump())
    db.add(project)
    try:
        db.flush()
        add_audit_log(db, current_user.id, "Project", project.id, "CREATE", data.model_dump(mode="json"))
        db.commit()
        db.refresh(project)
        return project
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project code already exists or violates a database constraint.")


def update_project(
    db: Session, project_id: uuid.UUID, data: ProjectUpdate, current_user: User
) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    update_data = data.model_dump(exclude_unset=True)

    final_start = update_data.get("start_date", project.start_date)
    final_completion = update_data.get("expected_completion", project.expected_completion)
    if final_completion < final_start:
        raise HTTPException(status_code=422, detail="Expected completion date cannot be before start date.")

    if "dept_id" in update_data:
        department = db.query(Department).filter(Department.id == update_data["dept_id"]).first()
        if not department or not department.is_active:
            raise HTTPException(status_code=400, detail="Active department not found.")

    if "pm_id" in update_data:
        manager = db.query(User).filter(User.id == update_data["pm_id"]).first()
        if not manager or not manager.is_active:
            raise HTTPException(status_code=400, detail="Active project manager not found.")
        role = db.query(Role).filter(Role.id == manager.role_id).first()
        if not role or role.name != "Project Manager":
            raise HTTPException(status_code=400, detail="Assigned user must have Project Manager role.")

    old_values = {}
    new_values = {}
    for field, value in update_data.items():
        old_value = getattr(project, field)
        if old_value != value:
            old_values[field] = str(old_value)
            new_values[field] = str(value)
            setattr(project, field, value)

    if new_values:
        add_audit_log(
            db,
            current_user.id,
            "Project",
            project.id,
            "UPDATE",
            {"old": old_values, "new": new_values},
        )
        try:
            db.commit()
            db.refresh(project)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Database integrity error.")

    return project
