import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.project import Project
from app.models.user import User
from app.schemas.contract import ContractCreate, ContractUpdate
from app.services.audit_service import add_audit_log


def _validate_references(
    db: Session,
    project_id: uuid.UUID,
    contractor_id: uuid.UUID,
) -> None:
    project = (
        db.query(Project)
        .filter(Project.id == project_id)
        .first()
    )

    if not project:
        raise HTTPException(
            status_code=400,
            detail="Project not found.",
        )

    contractor = (
        db.query(Contractor)
        .filter(Contractor.id == contractor_id)
        .first()
    )

    if not contractor:
        raise HTTPException(
            status_code=400,
            detail="Contractor not found.",
        )

    if contractor.status != "Active":
        raise HTTPException(
            status_code=400,
            detail="Contractor must be Active to be assigned to a contract.",
        )


def create_contract(
    db: Session,
    data: ContractCreate,
    current_user: User,
) -> Contract:
    _validate_references(
        db,
        data.project_id,
        data.contractor_id,
    )

    contract = Contract(**data.model_dump())
    db.add(contract)

    try:
        db.flush()

        add_audit_log(
            db,
            current_user.id,
            "Contract",
            contract.id,
            "CREATE",
            data.model_dump(mode="json"),
        )

        db.commit()
        db.refresh(contract)

        return contract

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Contract number already exists or violates a database constraint.",
        )


def update_contract(
    db: Session,
    contract_id: uuid.UUID,
    data: ContractUpdate,
    current_user: User,
) -> Contract:
    contract = (
        db.query(Contract)
        .filter(Contract.id == contract_id)
        .first()
    )

    if not contract:
        raise HTTPException(
            status_code=404,
            detail="Contract not found.",
        )

    update_data = data.model_dump(exclude_unset=True)

    if "contractor_id" in update_data:
        _validate_references(
            db,
            contract.project_id,
            update_data["contractor_id"],
        )

    old_values = {}
    new_values = {}

    for field, value in update_data.items():
        old_value = getattr(contract, field)

        if old_value != value:
            old_values[field] = str(old_value)
            new_values[field] = str(value)
            setattr(contract, field, value)

    if new_values:
        add_audit_log(
            db,
            current_user.id,
            "Contract",
            contract.id,
            "UPDATE",
            {
                "old": old_values,
                "new": new_values,
            },
        )

        try:
            db.commit()
            db.refresh(contract)

        except IntegrityError:
            db.rollback()

            raise HTTPException(
                status_code=400,
                detail="Database integrity error.",
            )

    return contract
