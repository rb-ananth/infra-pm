import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles, get_allowed_project_ids, verify_project_access, ADMIN_BYPASS, resolve_measurement_project, resolve_boq_item_project
from app.core.database import get_db
from app.models.user import User
from app.models.measurement import Measurement
from app.models.boq_item import BoqItem
from app.models.boq import Boq
from app.models.contract import Contract
from app.schemas.measurement import MeasurementCreate, MeasurementUpdate, MeasurementDetail, MeasurementOut
from app.services import measurement_service

router = APIRouter(prefix="/measurements", tags=["Measurements"])

@router.get("", response_model=list[MeasurementOut])
def list_measurements(
    boq_item_id: uuid.UUID | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer", "Billing Engineer", "Viewer", "PM")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    query = db.query(Measurement)
    if allowed_projects is not ADMIN_BYPASS:
        from app.models.boq_revision import BoqRevision
        query = (
            query.join(BoqItem, Measurement.boq_item_id == BoqItem.id)
            .join(BoqRevision, BoqItem.revision_id == BoqRevision.id)
            .join(Boq, BoqRevision.boq_id == Boq.id)
            .join(Contract, Boq.contract_id == Contract.id)
            .filter(Contract.project_id.in_(allowed_projects))
        )
    if boq_item_id:
        query = query.filter(Measurement.boq_item_id == boq_item_id)
    if status:
        query = query.filter(Measurement.status == status)
    if date_from:
        query = query.filter(Measurement.measurement_date >= date_from)
    if date_to:
        query = query.filter(Measurement.measurement_date <= date_to)
        
    return query.order_by(Measurement.measurement_date.desc(), Measurement.created_at.desc()).all()


@router.get("/{measurement_id}", response_model=MeasurementDetail)
def get_measurement(
    measurement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer", "Billing Engineer", "Viewer", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_measurement_project(db, measurement_id)
    verify_project_access(project_id, allowed_projects)
    return measurement_service.get_measurement_detail(db, measurement_id)


@router.post("", response_model=MeasurementDetail)
def create_measurement(
    data: MeasurementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_boq_item_project(db, data.boq_item_id)
    verify_project_access(project_id, allowed_projects)
    return measurement_service.create_measurement(db, data, current_user)


@router.put("/{measurement_id}", response_model=MeasurementDetail)
def update_measurement(
    measurement_id: uuid.UUID,
    data: MeasurementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_measurement_project(db, measurement_id)
    verify_project_access(project_id, allowed_projects)
    return measurement_service.update_measurement(db, measurement_id, data, current_user)


@router.post("/{measurement_id}/submit", response_model=MeasurementDetail)
def submit_measurement(
    measurement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_measurement_project(db, measurement_id)
    verify_project_access(project_id, allowed_projects)
    return measurement_service.submit_measurement(db, measurement_id, current_user)


@router.post("/{measurement_id}/approve", response_model=MeasurementDetail)
def approve_measurement(
    measurement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_measurement_project(db, measurement_id)
    verify_project_access(project_id, allowed_projects)
    return measurement_service.approve_measurement(db, measurement_id, current_user)


@router.post("/{measurement_id}/reject", response_model=MeasurementDetail)
def reject_measurement(
    measurement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
):
    project_id = resolve_measurement_project(db, measurement_id)
    verify_project_access(project_id, allowed_projects)
    return measurement_service.reject_measurement(db, measurement_id, current_user)
