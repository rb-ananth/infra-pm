import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
import io

from app.api.deps import get_db, require_roles
from app.models.user import User
from app.models.document import DocumentType
from app.schemas.document import DocumentResponse
from app.services.document_ingestion_service import register_document, ingest_document
from app.models.document import Document

router = APIRouter()

@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    project_id: uuid.UUID = Form(None),
    contract_id: uuid.UUID = Form(None),
    document_type: DocumentType = Form(...),
    document_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager"))
) -> Any:
    # Read file completely into memory
    file_bytes = file.file.read()
    file_stream = io.BytesIO(file_bytes)

    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ""

    # Register (PENDING)
    doc = register_document(
        db=db,
        user_id=current_user.id,
        project_id=project_id,
        contract_id=contract_id,
        document_type=document_type,
        document_name=document_name,
        source_filename=file.filename,
        file_extension=file_extension,
        mime_type=file.content_type,
        file_size_bytes=len(file_bytes),
        file_stream=file_stream
    )

    db.commit()
    db.refresh(doc)
    return doc

@router.post("/{document_id}/ingest", response_model=DocumentResponse)
def ingest_document_endpoint(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager"))
) -> Any:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_bytes = file.file.read()
    file_stream = io.BytesIO(file_bytes)

    ingest_document(db=db, user_id=current_user.id, document_id=doc.id, file_stream=file_stream)
    db.refresh(doc)
    return doc

@router.get("/", response_model=list[DocumentResponse])
def get_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer", "Billing Engineer", "Viewer"))
) -> Any:
    return db.query(Document).all()

@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer", "Billing Engineer", "Viewer"))
) -> Any:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
