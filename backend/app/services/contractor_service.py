import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.contractor import Contractor
from app.models.user import User
from app.schemas.contractor import ContractorCreate, ContractorUpdate
from app.services.audit_service import add_audit_log


def create_contractor(db: Session, data: ContractorCreate, current_user: User) -> Contractor:
    contractor = Contractor(**data.model_dump())
    db.add(contractor)
    try:
        db.flush()
        add_audit_log(db, current_user.id, "Contractor", contractor.id, "CREATE", data.model_dump(mode="json"))
        db.commit()
        db.refresh(contractor)
        return contractor
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Contractor registration number already exists.")


def update_contractor(
    db: Session, contractor_id: uuid.UUID, data: ContractorUpdate, current_user: User
) -> Contractor:
    contractor = db.query(Contractor).filter(Contractor.id == contractor_id).first()
    if not contractor:
        raise HTTPException(status_code=404, detail="Contractor not found.")

    old_values = {}
    new_values = {}
    for field, value in data.model_dump(exclude_unset=True).items():
        old_value = getattr(contractor, field)
        if old_value != value:
            old_values[field] = old_value
            new_values[field] = value
            setattr(contractor, field, value)

    if new_values:
        add_audit_log(
            db,
            current_user.id,
            "Contractor",
            contractor.id,
            "UPDATE",
            {"old": old_values, "new": new_values},
        )
        try:
            db.commit()
            db.refresh(contractor)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Database integrity error.")

    return contractor
