import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.contract import Contract
from app.models.user import User
from app.schemas.contract import (
    ContractCreate,
    ContractResponse,
    ContractUpdate,
)
from app.services import contract_service

router = APIRouter()


@router.get("/", response_model=list[ContractResponse])
def list_contracts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Contract)
        .order_by(Contract.contract_number)
        .all()
    )


@router.get("/{contract_id}", response_model=ContractResponse)
def get_contract(
    contract_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = (
        db.query(Contract)
        .filter(Contract.id == contract_id)
        .first()
    )

    if not contract:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail="Contract not found.",
        )

    return contract


@router.post("/", response_model=ContractResponse, status_code=201)
def create_contract(
    data: ContractCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "Project Manager")
    ),
):
    return contract_service.create_contract(
        db,
        data,
        current_user,
    )


@router.put("/{contract_id}", response_model=ContractResponse)
def update_contract(
    contract_id: uuid.UUID,
    data: ContractUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "Project Manager")
    ),
):
    return contract_service.update_contract(
        db,
        contract_id,
        data,
        current_user,
    )
