import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles, get_allowed_project_ids, ADMIN_BYPASS, resolve_eot_application_project, resolve_contract_project, verify_project_access
from app.core.database import get_db
from app.models.eot import EOTApplication
from app.models.contract import Contract
from app.models.user import User
from app.schemas.eot import EOTApplicationOut, EOTApplicationCreate, EOTApplicationUpdate, EOTApplicationDecision
from app.services.eot_service import EOTService

router = APIRouter()

@router.get("/", response_model=List[EOTApplicationOut])
def list_eot_applications(
    contract_id: uuid.UUID = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer", "Viewer")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    query = db.query(EOTApplication)
    if allowed_projects is not ADMIN_BYPASS:
        query = query.join(Contract, EOTApplication.contract_id == Contract.id).filter(Contract.project_id.in_(allowed_projects))

    if contract_id:
        query = query.filter(EOTApplication.contract_id == contract_id)

    return query.order_by(EOTApplication.created_at.desc()).all()


@router.post("/", response_model=EOTApplicationOut, status_code=201)
def create_eot_application(
    payload: EOTApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_contract_project(db, payload.contract_id)
    verify_project_access(project_id, allowed_projects)
    return EOTService.create_application(db, payload, current_user.id)


@router.get("/{eot_id}", response_model=EOTApplicationOut)
def get_eot_application(
    eot_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer", "Viewer")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_eot_application_project(db, eot_id)
    verify_project_access(project_id, allowed_projects)
    return EOTService.get_application(db, eot_id)


@router.put("/{eot_id}", response_model=EOTApplicationOut)
def update_eot_application(
    eot_id: uuid.UUID,
    payload: EOTApplicationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_eot_application_project(db, eot_id)
    verify_project_access(project_id, allowed_projects)
    return EOTService.update_application(db, eot_id, payload, current_user.id)


@router.post("/{eot_id}/submit", response_model=EOTApplicationOut)
def submit_eot_application(
    eot_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_eot_application_project(db, eot_id)
    verify_project_access(project_id, allowed_projects)
    return EOTService.submit_application(db, eot_id, current_user.id)


@router.post("/{eot_id}/review", response_model=EOTApplicationOut)
def review_eot_application(
    eot_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_eot_application_project(db, eot_id)
    verify_project_access(project_id, allowed_projects)
    return EOTService.review_application(db, eot_id, current_user.id)


@router.post("/{eot_id}/approve", response_model=EOTApplicationOut)
def approve_eot_application(
    eot_id: uuid.UUID,
    payload: EOTApplicationDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_eot_application_project(db, eot_id)
    verify_project_access(project_id, allowed_projects)
    return EOTService.approve_application(db, eot_id, payload, current_user.id)


@router.post("/{eot_id}/reject", response_model=EOTApplicationOut)
def reject_eot_application(
    eot_id: uuid.UUID,
    payload: EOTApplicationDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_eot_application_project(db, eot_id)
    verify_project_access(project_id, allowed_projects)
    return EOTService.reject_application(db, eot_id, payload, current_user.id)
