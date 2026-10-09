import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles, get_allowed_project_ids, verify_project_access, ADMIN_BYPASS
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
    allowed_projects = Depends(get_allowed_project_ids)
):
    query = db.query(Contract)
    if allowed_projects is not ADMIN_BYPASS:
        query = query.filter(Contract.project_id.in_(allowed_projects))
    return query.order_by(Contract.contract_number).all()


@router.get("/{contract_id}", response_model=ContractResponse)
def get_contract(
    contract_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    allowed_projects = Depends(get_allowed_project_ids)
):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found.")
        
    verify_project_access(contract.project_id, allowed_projects)
    return contract


@router.post("/", response_model=ContractResponse, status_code=201)
def create_contract(
    data: ContractCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "Project Manager")
    ),
    allowed_projects = Depends(get_allowed_project_ids)
):
    verify_project_access(data.project_id, allowed_projects)
    return contract_service.create_contract(db, data, current_user)


@router.put("/{contract_id}", response_model=ContractResponse)
def update_contract(
    contract_id: uuid.UUID,
    data: ContractUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "Project Manager")
    ),
    allowed_projects = Depends(get_allowed_project_ids)
):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found.")
        
    verify_project_access(contract.project_id, allowed_projects)
    # If they are trying to move the contract to a new project (if even allowed), verify access to the new project too
    if data.project_id and data.project_id != contract.project_id:
        verify_project_access(data.project_id, allowed_projects)
        
    return contract_service.update_contract(db, contract_id, data, current_user)
