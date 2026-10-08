import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from app.models.document import DocumentType, IngestionStatus, ValidationStatus


class DocumentBase(BaseModel):
    project_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    document_type: DocumentType
    document_name: str
    source_filename: str
    file_extension: str
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    ingestion_status: IngestionStatus = IngestionStatus.PENDING
    source_system: str | None = None
    document_date: datetime | None = None
    metadata_json: dict[str, Any] | None = None


class DocumentCreate(DocumentBase):
    pass


class DocumentResponse(DocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DocumentChunkBase(BaseModel):
    chunk_index: int
    content: str
    content_hash: str
    page_number: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    section: str | None = None
    clause_reference: str | None = None
    parent_chunk_id: uuid.UUID | None = None
    metadata_json: dict[str, Any] | None = None


class DocumentChunkResponse(DocumentChunkBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    created_at: datetime


class DocumentFactBase(BaseModel):
    fact_type: str
    field_name: str
    value: str
    normalized_value: str | None = None
    unit: str | None = None
    confidence: float | None = None
    source_reference: str
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED
    metadata_json: dict[str, Any] | None = None


class DocumentFactResponse(DocumentFactBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    document_chunk_id: uuid.UUID | None
    created_at: datetime
