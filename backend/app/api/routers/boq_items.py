import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.boq import BoqItemCreate, BoqItemResponse, BoqItemUpdate
from app.services import boq_service

router = APIRouter()


@router.post("/boq-revisions/{revision_id}/items", response_model=BoqItemResponse, status_code=201)
def create_item(
    revision_id: uuid.UUID,
    data: BoqItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    return boq_service.create_item(db, revision_id, data, current_user)


@router.get("/boq-items/{item_id}", response_model=BoqItemResponse)
def get_item(item_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return boq_service.get_item(db, item_id)


@router.put("/boq-items/{item_id}", response_model=BoqItemResponse)
def update_item(
    item_id: uuid.UUID,
    data: BoqItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    return boq_service.update_item(db, item_id, data, current_user)