
import uuid

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.document import Document, DocumentChunk
from app.services.embedding_service import generate_embedding


def search_document_chunks(
    db: Session,
    query_text: str,
    project_id: uuid.UUID,
    limit: int = 5,
) -> list[dict]:
    """
    Retrieve the most relevant document chunks for one project.

    Authorization must be checked by the API route before calling
    this function. Global, unassigned documents are excluded.
    """

    if not query_text or not query_text.strip():
        raise ValueError("Search query cannot be empty.")

    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20.")

    query_embedding = generate_embedding(query_text)

    # Normally project_id is populated on the document.
    # The contract join also supports legacy documents whose project_id
    # is NULL but whose contract belongs to the requested project.
    project_filter = or_(
        Document.project_id == project_id,
        and_(
            Document.project_id.is_(None),
            Document.contract_id.is_not(None),
            Contract.project_id == project_id,
        ),
    )

    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    ).label("distance")

    results = (
        db.query(DocumentChunk, Document, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .outerjoin(Contract, Contract.id == Document.contract_id)
        .filter(
            project_filter,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance.asc())
        .limit(limit)
        .all()
    )

    matches = []

    for chunk, document, cosine_distance in results:
        matches.append(
            {
                "chunk_id": str(chunk.id),
                "document_id": str(document.id),
                "document_name": document.document_name,
                "source_filename": document.source_filename,
                "content": chunk.content,
                "page_number": chunk.page_number,
                "sheet_name": chunk.sheet_name,
                "row_start": chunk.row_start,
                "row_end": chunk.row_end,
                "section": chunk.section,
                "clause_reference": chunk.clause_reference,
                "cosine_distance": float(cosine_distance),
            }
        )

    return matches
