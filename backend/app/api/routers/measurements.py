import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.user import User
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
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer", "Billing Engineer", "Viewer")),
):
    return measurement_service.list_measurements(
        db, boq_item_id=boq_item_id, status=status, date_from=date_from, date_to=date_to
    )


@router.get("/{measurement_id}", response_model=MeasurementDetail)
def get_measurement(
    measurement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer", "Billing Engineer", "Viewer")),
):
    return measurement_service.get_measurement_detail(db, measurement_id)


@router.post("", response_model=MeasurementDetail)
def create_measurement(
    data: MeasurementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer")),
):
    return measurement_service.create_measurement(db, data, current_user)


@router.put("/{measurement_id}", response_model=MeasurementDetail)
def update_measurement(
    measurement_id: uuid.UUID,
    data: MeasurementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer")),
):
    return measurement_service.update_measurement(db, measurement_id, data, current_user)


@router.post("/{measurement_id}/submit", response_model=MeasurementDetail)
def submit_measurement(
    measurement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer")),
):
    return measurement_service.submit_measurement(db, measurement_id, current_user)


@router.post("/{measurement_id}/approve", response_model=MeasurementDetail)
def approve_measurement(
    measurement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM")),
):
    return measurement_service.approve_measurement(db, measurement_id, current_user)


@router.post("/{measurement_id}/reject", response_model=MeasurementDetail)
def reject_measurement(
    measurement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "PM", "Engineer")),
):
    return measurement_service.reject_measurement(db, measurement_id, current_user)
