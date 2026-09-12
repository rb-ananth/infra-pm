import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.boq import BoqItemCreate, BoqItemResponse, BoqItemUpdate
from app.schemas.boq_import import BoqImportPreviewResponse, BoqImportResponse
from app.services import boq_service
from app.services import boq_import_service

router = APIRouter()


@router.post("/boq-revisions/{revision_id}/import/preview", response_model=BoqImportPreviewResponse)
async def preview_import(
    revision_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    content = await boq_import_service.read_upload(file)
    return boq_import_service.preview_import(db, revision_id, file.filename, content)


@router.post("/boq-revisions/{revision_id}/import", response_model=BoqImportResponse, status_code=201)
async def import_items(
    revision_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    content = await boq_import_service.read_upload(file)
    return boq_import_service.import_items(db, revision_id, file.filename, content, current_user)


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