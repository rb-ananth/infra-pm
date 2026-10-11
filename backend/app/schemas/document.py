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

class BoqExtractionSummaryResponse(BaseModel):
    rows_processed: int
    valid_items: int
    facts_extracted: int
    validation_errors: int
    source_discrepancies: int

class MeasurementExtractionSummaryResponse(BaseModel):
    rows_processed: int
    valid_measurements: int
    facts_extracted: int
    validation_errors: int
    duplicate_references: int
    unknown_boq_links: int

class RABillExtractionSummaryResponse(BaseModel):
    rows_processed: int
    valid_facts: int
    facts_extracted: int
    validation_errors: int
    duplicate_references: int
    unknown_links: int
    reconciliation_matches: int
    reconciliation_mismatches: int

class EVMExtractionSummaryResponse(BaseModel):
    facts_extracted: int
    duplicate_metrics: int = 0
    valid_facts: int
    validation_errors: int
    reconciliation_matches: int
    reconciliation_mismatches: int


class DocumentSearchRequest(BaseModel):
    project_id: uuid.UUID
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)


class DocumentSearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    source_filename: str
    content: str
    page_number: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    section: str | None = None
    clause_reference: str | None = None
    cosine_distance: float


class DocumentSearchResponse(BaseModel):
    query: str
    project_id: uuid.UUID
    results: list[DocumentSearchResult]


class RAGQueryRequest(BaseModel):
    project_id: uuid.UUID
    question: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)


class RAGSource(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    source_filename: str
    page_number: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    section: str | None = None
    clause_reference: str | None = None


class RAGQueryResponse(BaseModel):
    question: str
    project_id: uuid.UUID
    answer: str
    sources: list[RAGSource]
    insufficient_evidence: bool = False