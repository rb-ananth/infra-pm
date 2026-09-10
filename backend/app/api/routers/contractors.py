import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.contractor import Contractor
from app.models.user import User
from app.schemas.contractor import ContractorCreate, ContractorResponse, ContractorUpdate
from app.services import contractor_service

router = APIRouter()


@router.get("/", response_model=list[ContractorResponse])
def list_contractors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Contractor).order_by(Contractor.name).all()


@router.post("/", response_model=ContractorResponse)
def create_contractor(
    data: ContractorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin")),
):
    return contractor_service.create_contractor(db, data, current_user)


@router.put("/{contractor_id}", response_model=ContractorResponse)
def update_contractor(
    contractor_id: uuid.UUID,
    data: ContractorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin")),
):
    return contractor_service.update_contractor(db, contractor_id, data, current_user)
