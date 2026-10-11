import uuid
from typing import BinaryIO
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.document import Document, DocumentChunk, IngestionStatus
from app.services.document_parser import DocumentParser, PdfParser, ExcelParser
from app.services.audit_service import add_audit_log
from app.services.embedding_service import generate_embedding

def register_document(
    db: Session,
    user_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    contract_id: uuid.UUID | None,
    document_type: str,
    document_name: str,
    source_filename: str,
    file_extension: str,
    mime_type: str,
    file_size_bytes: int,
    file_stream: BinaryIO
) -> Document:
    sha256_hash = DocumentParser.calculate_sha256(file_stream)

    existing = db.query(Document).filter(Document.sha256_hash == sha256_hash).first()
    if existing:
        return existing

    doc = Document(
        project_id=project_id,
        contract_id=contract_id,
        document_type=document_type,
        document_name=document_name,
        source_filename=source_filename,
        file_extension=file_extension,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        sha256_hash=sha256_hash,
        ingestion_status=IngestionStatus.PENDING,
        source_system="MANUAL_UPLOAD"
    )
    db.add(doc)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # Race condition handling
        return db.query(Document).filter(Document.sha256_hash == sha256_hash).first()

    add_audit_log(
        db=db,
        user_id=user_id,
        entity_name="Document",
        entity_id=doc.id,
        action="REGISTER",
        changes={"filename": source_filename, "hash": sha256_hash}
    )

    return doc

def ingest_document(db: Session, user_id: uuid.UUID | None, document_id: uuid.UUID, file_stream: BinaryIO) -> Document:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError("Document not found")

    if doc.ingestion_status == IngestionStatus.COMPLETED:
        return doc

    try:
        doc.ingestion_status = IngestionStatus.PROCESSING
        db.flush()

        add_audit_log(
            db=db,
            user_id=user_id,
            entity_name="Document",
            entity_id=doc.id,
            action="INGEST_START",
            changes={"status": "PROCESSING"}
        )

        file_stream.seek(0)
        chunks_data = []
        if doc.file_extension.lower() == "pdf":
            chunks_data = PdfParser.parse(file_stream)
        elif doc.file_extension.lower() in ["xlsx", "xls"]:
            chunks_data = ExcelParser.parse(file_stream)
        else:
            raise ValueError(f"Unsupported file extension: {doc.file_extension}")


        for chunk_data in chunks_data:
            content = chunk_data["content"]

            # Empty pages or rows can be stored, but cannot be embedded.
            embedding = generate_embedding(content) if content.strip() else None

            chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=chunk_data["chunk_index"],
                content=content,
                content_hash=chunk_data["content_hash"],
                embedding=embedding,
                page_number=chunk_data.get("page_number"),
                sheet_name=chunk_data.get("sheet_name"),
                row_start=chunk_data.get("row_start"),
                row_end=chunk_data.get("row_end")
            )
            db.add(chunk)


        doc.ingestion_status = IngestionStatus.COMPLETED
        add_audit_log(
            db=db,
            user_id=user_id,
            entity_name="Document",
            entity_id=doc.id,
            action="INGEST_COMPLETE",
            changes={"chunks_created": len(chunks_data), "status": "COMPLETED"}
        )
        db.commit()
    except Exception as e:
        db.rollback()
        # Re-fetch document inside new transaction to update status to FAILED
        doc = db.query(Document).filter(Document.id == document_id).first()
        doc.ingestion_status = IngestionStatus.FAILED
        doc.metadata_json = {"error": str(e)}
        add_audit_log(
            db=db,
            user_id=user_id,
            entity_name="Document",
            entity_id=doc.id,
            action="INGEST_FAILED",
            changes={"error": str(e), "status": "FAILED"}
        )
        db.commit()
        raise e

    return doc
