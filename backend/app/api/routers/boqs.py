import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.boq import BoqCreate, BoqResponse, BoqUpdate
from app.services import boq_service

router = APIRouter()


@router.get("/", response_model=list[BoqResponse])
def list_boqs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return boq_service.list_boqs(db)


@router.get("/{boq_id}", response_model=BoqResponse)
def get_boq(boq_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return boq_service.get_boq(db, boq_id)


@router.post("/", response_model=BoqResponse, status_code=201)
def create_boq(
    data: BoqCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    return boq_service.create_boq(db, data, current_user)


@router.put("/{boq_id}", response_model=BoqResponse)
def update_boq(
    boq_id: uuid.UUID,
    data: BoqUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    return boq_service.update_boq(db, boq_id, data, current_user)