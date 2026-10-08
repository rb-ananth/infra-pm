import uuid
import re
from decimal import Decimal, InvalidOperation
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.models.document import Document, DocumentChunk, DocumentFact, ValidationStatus, DocumentType, IngestionStatus
from app.models.contract import Contract
from app.models.user import User
from app.services.audit_service import add_audit_log

class DocumentNotFoundError(Exception): pass
class DocumentStateError(Exception): pass
class ContractNotLinkedError(Exception): pass

def normalize_contract_value(v: str) -> str:
    v = v.strip()
    match = re.match(r'^(?:INR|₹)?\s*(?P<amount>(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?)$', v, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid monetary format: {v}")
    clean_str = match.group('amount').replace(',', '')
    try:
        dec = Decimal(clean_str)
        if dec < 0:
            raise ValueError("Negative value not allowed")
        return f"{dec:.2f}"
    except InvalidOperation:
        raise ValueError(f"Invalid decimal value: {v}")

def normalize_contract_number(v: str) -> str:
    return re.sub(r'\s*-\s*', '-', v.strip())

FACT_SPECIFICATIONS = {
    "CONTRACT": {
        "contract_number": {
            "pattern": r"Contract Number:\s*(.*)",
            "normalizer": normalize_contract_number
        },
        "contract_value": {
            "pattern": r"Contract Value:\s*(.*)",
            "normalizer": normalize_contract_value
        }
    }
}

def extract_contract_facts(db: Session, document_id: uuid.UUID, current_user: User) -> list[DocumentFact]:
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError("Document not found")
        if doc.document_type != DocumentType.CONTRACT:
            raise DocumentStateError(f"Extraction requires CONTRACT document, got {doc.document_type}")
        if doc.ingestion_status != IngestionStatus.COMPLETED:
            raise DocumentStateError(f"Extraction requires COMPLETED ingestion, got {doc.ingestion_status}")
            
        existing_facts = db.query(DocumentFact).filter(
            DocumentFact.document_id == document_id,
            DocumentFact.fact_type == "CONTRACT"
        ).all()
        
        unmatched_existing = {f.id: f for f in existing_facts}
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        
        spec = FACT_SPECIFICATIONS["CONTRACT"]
        new_facts_added = []
        
        for chunk in chunks:
            content = chunk.content
            for field_name, rules in spec.items():
                matches = re.findall(rules["pattern"], content, re.IGNORECASE)
                for raw_value in matches:
                    raw_value = raw_value.strip()
                    source_ref = f"Page {chunk.page_number}" if chunk.page_number else f"Chunk {chunk.chunk_index}"
                    
                    matched_id = None
                    for fid, ef in unmatched_existing.items():
                        if ef.field_name == field_name and ef.value == raw_value and ef.document_chunk_id == chunk.id:
                            matched_id = fid
                            break
                            
                    if matched_id:
                        del unmatched_existing[matched_id]
                    else:
                        fact = DocumentFact(
                            document_id=doc.id,
                            document_chunk_id=chunk.id,
                            fact_type="CONTRACT",
                            field_name=field_name,
                            value=raw_value,
                            confidence=1.0,
                            source_reference=source_ref,
                            validation_status=ValidationStatus.UNVALIDATED,
                            metadata_json={}
                        )
                        db.add(fact)
                        new_facts_added.append(fact)
                        
        deleted_count = 0
        for fid, ef in unmatched_existing.items():
            db.delete(ef)
            deleted_count += 1
            
        db.flush()
        
        if new_facts_added or deleted_count > 0:
            add_audit_log(
                db=db,
                user_id=current_user.id,
                entity_name="Document",
                entity_id=doc.id,
                action="FACTS_EXTRACTED",
                changes={"extracted_count": len(new_facts_added), "deleted_count": deleted_count, "fact_type": "CONTRACT"}
            )
            
        db.commit()
        return db.query(DocumentFact).filter(DocumentFact.document_id == document_id, DocumentFact.fact_type == "CONTRACT").all()
    except Exception as e:
        db.rollback()
        raise e

def reconcile_contract_facts(db: Session, document_id: uuid.UUID, current_user: User) -> list[DocumentFact]:
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError("Document not found")
            
        if doc.document_type != DocumentType.CONTRACT:
            raise DocumentStateError(f"Reconciliation requires CONTRACT document, got {doc.document_type}")
        if doc.ingestion_status != IngestionStatus.COMPLETED:
            raise DocumentStateError(f"Reconciliation requires COMPLETED ingestion, got {doc.ingestion_status}")
            
        contract = db.query(Contract).filter(Contract.id == doc.contract_id).first()
        if not contract:
            raise ContractNotLinkedError("Document is not linked to a Contract")
            
        facts = db.query(DocumentFact).filter(
            DocumentFact.document_id == document_id,
            DocumentFact.fact_type == "CONTRACT"
        ).all()
        
        spec = FACT_SPECIFICATIONS["CONTRACT"]
        reconciled_count = 0
        
        field_values = {}
        for fact in facts:
            if fact.field_name not in spec:
                continue
            try:
                norm_val = spec[fact.field_name]["normalizer"](fact.value)
                fact.normalized_value = norm_val
                field_values.setdefault(fact.field_name, set()).add(norm_val)
            except Exception:
                fact.normalized_value = None
        
        ambiguous_fields = {f for f, v in field_values.items() if len(v) > 1}
        
        for fact in facts:
            if fact.field_name not in spec:
                continue
                
            canonical_value = None
            if fact.field_name == "contract_number":
                canonical_value = contract.contract_number
            elif fact.field_name == "contract_value":
                canonical_value = f"{Decimal(contract.contract_value):.2f}"
                
            if fact.normalized_value is None:
                outcome = "INVALID_FORMAT"
                fact.validation_status = ValidationStatus.INVALID
            elif fact.field_name in ambiguous_fields:
                outcome = "AMBIGUOUS"
                fact.validation_status = ValidationStatus.CONFLICT
            else:
                if fact.normalized_value == canonical_value:
                    outcome = "MATCH"
                    fact.validation_status = ValidationStatus.VALID
                else:
                    outcome = "MISMATCH"
                    fact.validation_status = ValidationStatus.CONFLICT
                    
            meta = fact.metadata_json or {}
            meta["reconciliation"] = {
                "outcome": outcome,
                "canonical_value": canonical_value,
                "comparison_representation": fact.normalized_value
            }
            fact.metadata_json = meta
            flag_modified(fact, "metadata_json")
            
            reconciled_count += 1
            
        db.flush()
        
        if reconciled_count > 0:
            add_audit_log(
                db=db,
                user_id=current_user.id,
                entity_name="Document",
                entity_id=doc.id,
                action="FACTS_RECONCILED",
                changes={"reconciled_count": reconciled_count, "fact_type": "CONTRACT", "ambiguous_fields": list(ambiguous_fields)}
            )
            
        db.commit()
        return facts
    except Exception as e:
        db.rollback()
        raise e
