import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
import io

from app.api.deps import get_db, require_roles, get_allowed_project_ids, verify_project_access, ADMIN_BYPASS
from app.models.user import User
from app.models.contract import Contract
from app.models.document import DocumentType
from app.schemas.document import DocumentResponse, DocumentFactResponse, BoqExtractionSummaryResponse, MeasurementExtractionSummaryResponse, RABillExtractionSummaryResponse, EVMExtractionSummaryResponse
from app.services.document_ingestion_service import register_document, ingest_document
from app.services.document_intelligence_service import extract_contract_facts, reconcile_contract_facts, extract_boq_facts, extract_measurement_facts, extract_ra_bill_facts, extract_evm_facts, DocumentNotFoundError, DocumentStateError, ContractNotLinkedError
from app.models.document import Document

router = APIRouter()

def _verify_doc_project_access(document_id: uuid.UUID, db: Session, allowed_projects):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.project_id:
        verify_project_access(doc.project_id, allowed_projects)
    return doc

@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    project_id: uuid.UUID = Form(None),
    contract_id: uuid.UUID = Form(None),
    document_type: DocumentType = Form(...),
    document_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    if project_id:
        verify_project_access(project_id, allowed_projects)
        
    if contract_id:
        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            raise HTTPException(status_code=400, detail="Invalid contract_id")
        verify_project_access(contract.project_id, allowed_projects)
        if project_id and project_id != contract.project_id:
            raise HTTPException(status_code=400, detail="Project mismatch")
        project_id = contract.project_id # Force inherit

    if not project_id:
        # If no project is tied, the document is essentially global (maybe dangerous). 
        # For now, require project_id for standard operational users.
        if allowed_projects is not ADMIN_BYPASS:
            raise HTTPException(status_code=400, detail="project_id or contract_id is required")

    file_bytes = file.file.read()
    file_stream = io.BytesIO(file_bytes)
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ""

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
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    doc = _verify_doc_project_access(document_id, db, allowed_projects)
    file_bytes = file.file.read()
    file_stream = io.BytesIO(file_bytes)

    ingest_document(db=db, user_id=current_user.id, document_id=doc.id, file_stream=file_stream)
    db.refresh(doc)
    return doc

@router.get("/", response_model=list[DocumentResponse])
def get_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer", "Billing Engineer", "Viewer")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    query = db.query(Document)
    if allowed_projects is not ADMIN_BYPASS:
        # User can only see documents tied to their projects, or docs with NO project (global policies, etc).
        query = query.filter(Document.project_id.in_(allowed_projects))
    return query.all()

@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer", "Billing Engineer", "Viewer")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    return _verify_doc_project_access(document_id, db, allowed_projects)

@router.post("/{document_id}/intelligence/extract", response_model=list[DocumentFactResponse])
def extract_facts_endpoint(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    _verify_doc_project_access(document_id, db, allowed_projects)
    try:
        facts = extract_contract_facts(db=db, document_id=document_id, current_user=current_user)
        return facts
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DocumentStateError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{document_id}/intelligence/reconcile", response_model=list[DocumentFactResponse])
def reconcile_facts_endpoint(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    _verify_doc_project_access(document_id, db, allowed_projects)
    try:
        facts = reconcile_contract_facts(db=db, document_id=document_id, current_user=current_user)
        return facts
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DocumentStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractNotLinkedError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{document_id}/intelligence/boq/extract", response_model=BoqExtractionSummaryResponse)
def extract_boq_facts_endpoint(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    _verify_doc_project_access(document_id, db, allowed_projects)
    try:
        summary = extract_boq_facts(db=db, document_id=document_id, current_user=current_user)
        return summary
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DocumentStateError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{document_id}/intelligence/measurement/extract", response_model=MeasurementExtractionSummaryResponse)
def extract_measurement_facts_endpoint(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    _verify_doc_project_access(document_id, db, allowed_projects)
    try:
        summary = extract_measurement_facts(db=db, document_id=document_id, current_user=current_user)
        return summary
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DocumentStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractNotLinkedError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{document_id}/intelligence/ra-bill/extract", response_model=RABillExtractionSummaryResponse)
def extract_ra_bill_facts_endpoint(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    _verify_doc_project_access(document_id, db, allowed_projects)
    try:
        summary = extract_ra_bill_facts(db=db, document_id=document_id, current_user=current_user)
        return summary
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DocumentStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractNotLinkedError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{document_id}/intelligence/evm/extract", response_model=EVMExtractionSummaryResponse)
def extract_evm_facts_endpoint(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
    allowed_projects = Depends(get_allowed_project_ids)
) -> Any:
    _verify_doc_project_access(document_id, db, allowed_projects)
    try:
        summary = extract_evm_facts(db=db, document_id=document_id, current_user=current_user)
        return summary
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (DocumentStateError, ContractNotLinkedError) as e:
        raise HTTPException(status_code=400, detail=str(e))
