import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.boq_item import BoqItem
from app.models.measurement import Measurement
from app.models.user import User
from app.schemas.measurement import MeasurementCreate, MeasurementUpdate, MeasurementDetail, MeasurementOut
from app.schemas.boq import BoqItemResponse
from app.services.audit_service import add_audit_log

QUANTITY_QUANTUM = Decimal("0.001")
PERCENT_QUANTUM = Decimal("0.01")


def _get_cumulative_approved(db: Session, boq_item_id: uuid.UUID) -> Decimal:
    result = db.query(func.sum(Measurement.quantity)).filter(
        Measurement.boq_item_id == boq_item_id,
        Measurement.status == "Approved"
    ).scalar()
    if result is None:
        return Decimal("0.000")
    return Decimal(result).quantize(QUANTITY_QUANTUM)


def _build_detail(db: Session, measurement: Measurement, boq_item: BoqItem = None) -> MeasurementDetail:
    if boq_item is None:
        boq_item = measurement.boq_item
    
    cumulative = _get_cumulative_approved(db, boq_item.id)
    
    boq_quantity = boq_item.quantity
    balance = boq_quantity - cumulative
    if boq_quantity > 0:
        percentage = (cumulative / boq_quantity * 100).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
    else:
        percentage = Decimal("0.00")
        
    is_overrun = cumulative > boq_quantity
    overrun_qty = cumulative - boq_quantity if is_overrun else None
    
    return MeasurementDetail(
        measurement=MeasurementOut.model_validate(measurement),
        boq_item=BoqItemResponse.model_validate(boq_item),
        cumulative_approved_quantity=cumulative,
        balance_quantity=balance,
        percentage_executed=percentage,
        is_overrun=is_overrun,
        overrun_quantity=overrun_qty
    )


def list_measurements(
    db: Session, 
    boq_item_id: uuid.UUID | None = None, 
    status: str | None = None, 
    date_from: date | None = None, 
    date_to: date | None = None
) -> list[Measurement]:
    query = db.query(Measurement)
    if boq_item_id:
        query = query.filter(Measurement.boq_item_id == boq_item_id)
    if status:
        query = query.filter(Measurement.status == status)
    if date_from:
        query = query.filter(Measurement.measurement_date >= date_from)
    if date_to:
        query = query.filter(Measurement.measurement_date <= date_to)
        
    return query.order_by(Measurement.measurement_date.desc(), Measurement.created_at.desc()).all()


def get_measurement_detail(db: Session, measurement_id: uuid.UUID) -> MeasurementDetail:
    measurement = db.query(Measurement).filter(Measurement.id == measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found.")
    return _build_detail(db, measurement)


def create_measurement(db: Session, data: MeasurementCreate, current_user: User) -> MeasurementDetail:
    boq_item = db.query(BoqItem).filter(BoqItem.id == data.boq_item_id).first()
    if not boq_item:
        raise HTTPException(status_code=400, detail="BOQ item not found.")
        
    if boq_item.revision.status != "Approved":
        raise HTTPException(status_code=400, detail="Measurements can only be created against an Approved BOQ revision.")
        
    measurement = Measurement(
        **data.model_dump(),
        status="Draft",
        created_by=current_user.id
    )
    db.add(measurement)
    db.flush()
    
    add_audit_log(db, current_user.id, "Measurement", measurement.id, "CREATE", data.model_dump(mode="json"))
    db.commit()
    db.refresh(measurement)
    
    return _build_detail(db, measurement, boq_item)


def update_measurement(db: Session, measurement_id: uuid.UUID, data: MeasurementUpdate, current_user: User) -> MeasurementDetail:
    measurement = db.query(Measurement).filter(Measurement.id == measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found.")
        
    if measurement.status not in ["Draft", "Rejected"]:
        raise HTTPException(status_code=409, detail="Only Draft or Rejected measurements can be modified.")
        
    update_data = data.model_dump(exclude_unset=True)
    old_values = {}
    new_values = {}
    
    for field, value in update_data.items():
        old_value = getattr(measurement, field)
        if old_value != value:
            old_values[field] = str(old_value)
            new_values[field] = str(value)
            setattr(measurement, field, value)
            
    if measurement.status == "Rejected":
        old_values["status"] = "Rejected"
        new_values["status"] = "Draft"
        measurement.status = "Draft"
            
    if new_values:
        add_audit_log(db, current_user.id, "Measurement", measurement.id, "UPDATE", {"old": old_values, "new": new_values})
        db.commit()
        db.refresh(measurement)
        
    return _build_detail(db, measurement)


def submit_measurement(db: Session, measurement_id: uuid.UUID, current_user: User) -> MeasurementDetail:
    measurement = db.query(Measurement).filter(Measurement.id == measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found.")
        
    if measurement.status != "Draft":
        raise HTTPException(status_code=409, detail="Only Draft measurements can be submitted.")
        
    measurement.status = "Submitted"
    add_audit_log(db, current_user.id, "Measurement", measurement.id, "SUBMIT", {})
    db.commit()
    db.refresh(measurement)
    
    return _build_detail(db, measurement)


def approve_measurement(db: Session, measurement_id: uuid.UUID, current_user: User) -> MeasurementDetail:
    measurement = db.query(Measurement).filter(Measurement.id == measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found.")
        
    if measurement.status != "Submitted":
        raise HTTPException(status_code=409, detail="Only Submitted measurements can be approved.")
        
    # Lock the BOQ item row to prevent concurrent approvals from causing race conditions
    boq_item = db.query(BoqItem).filter(BoqItem.id == measurement.boq_item_id).with_for_update().first()
    
    measurement.status = "Approved"
    
    # We log the approval
    add_audit_log(db, current_user.id, "Measurement", measurement.id, "APPROVE", {})
    db.commit()
    db.refresh(measurement)
    
    return _build_detail(db, measurement)


def reject_measurement(db: Session, measurement_id: uuid.UUID, current_user: User) -> MeasurementDetail:
    measurement = db.query(Measurement).filter(Measurement.id == measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found.")
        
    if measurement.status != "Submitted":
        raise HTTPException(status_code=409, detail="Only Submitted measurements can be rejected.")
        
    measurement.status = "Rejected"
    
    add_audit_log(db, current_user.id, "Measurement", measurement.id, "REJECT", {})
    db.commit()
    db.refresh(measurement)
    
    return _build_detail(db, measurement)
