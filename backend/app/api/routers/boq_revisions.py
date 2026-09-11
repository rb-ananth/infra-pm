import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.boq import (
    BoqItemResponse,
    BoqResponse,
    BoqRevisionCreate,
    BoqRevisionDetailResponse,
    BoqRevisionResponse,
    BoqRevisionUpdate,
)
from app.services import boq_service

router = APIRouter()


@router.get("/boqs/{boq_id}/revisions", response_model=list[BoqRevisionResponse])
def list_revisions(boq_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return boq_service.list_revisions(db, boq_id)


@router.post("/boqs/{boq_id}/revisions", response_model=BoqRevisionResponse, status_code=201)
def create_revision(
    boq_id: uuid.UUID,
    data: BoqRevisionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    return boq_service.create_revision(db, boq_id, data, current_user)


@router.get("/boq-revisions/{revision_id}", response_model=BoqRevisionDetailResponse)
def get_revision(revision_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    boq, revision, items, total = boq_service.revision_detail(db, revision_id)
    return BoqRevisionDetailResponse(boq=boq, revision=revision, items=items, total=total)


@router.put("/boq-revisions/{revision_id}", response_model=BoqRevisionResponse)
def update_revision(
    revision_id: uuid.UUID,
    data: BoqRevisionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    return boq_service.update_revision(db, revision_id, data, current_user)


@router.get("/boq-revisions/{revision_id}/items", response_model=list[BoqItemResponse])
def list_items(revision_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return boq_service.list_items(db, revision_id)