import uuid
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.models.document import Document
from app.models.boq import Boq
from app.models.boq_revision import BoqRevision
from app.models.boq_item import BoqItem
from app.models.document import DocumentChunk, DocumentFact, ValidationStatus, DocumentType, IngestionStatus
from app.models.ra_bill import RABill, RABillItem, RABillMeasurement
from app.models.measurement import Measurement
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

        if dec.as_tuple().exponent < -2:
            raise ValueError(f"More than 2 decimal places not allowed: {v}")

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

def extract_boq_facts(db: Session, document_id: uuid.UUID, current_user: User) -> dict:
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError("Document not found")
        if doc.document_type != DocumentType.BOQ:
            raise DocumentStateError(f"Extraction requires BOQ document, got {doc.document_type}")
        if doc.ingestion_status != IngestionStatus.COMPLETED:
            raise DocumentStateError(f"Extraction requires COMPLETED ingestion, got {doc.ingestion_status}")

        existing_facts = db.query(DocumentFact).filter(
            DocumentFact.document_id == document_id,
            DocumentFact.fact_type == "BOQ"
        ).all()

        unmatched_existing = {f.id: f for f in existing_facts}
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()

        rows_processed = 0
        valid_items = 0
        facts_extracted = 0
        validation_errors = 0
        source_discrepancies = 0

        parsed_rows = []
        code_counts = {}
        num_counts = {}

        # Pass 1: Parse and identify duplicates globally
        for chunk in chunks:
            if chunk.sheet_name and "BOQ" not in chunk.sheet_name.upper():
                continue

            parts = [p.strip() for p in chunk.content.split(" | ")]
            if len(parts) == 0:
                continue

            while len(parts) < 7:
                parts.append("")

            item_code = parts[0]
            if item_code.upper() == "ITEM CODE":
                continue

            item_number = parts[1]

            if item_code:
                code_counts[item_code] = code_counts.get(item_code, 0) + 1
            if item_number:
                num_counts[item_number] = num_counts.get(item_number, 0) + 1

            parsed_rows.append((chunk, parts))

        new_facts_added = []

        # Pass 2: Extract and Validate
        for chunk, parts in parsed_rows:
            item_code = parts[0]
            item_number = parts[1]
            description = parts[2]
            unit = parts[3]
            quantity_str = parts[4]
            rate_str = parts[5]
            amount_str = parts[6]

            rows_processed += 1
            row_errors = []

            if not item_code: row_errors.append("Missing item_code")
            if not item_number: row_errors.append("Missing item_number")
            if not description: row_errors.append("Missing description")
            if not unit: row_errors.append("Missing unit")
            if not quantity_str: row_errors.append("Missing quantity")
            if not rate_str: row_errors.append("Missing rate")
            if not amount_str: row_errors.append("Missing source_amount")

            if item_code and code_counts[item_code] > 1:
                row_errors.append("Duplicate item_code")
            if item_number and num_counts[item_number] > 1:
                row_errors.append("Duplicate item_number")

            qty_dec = None
            rate_dec = None
            amt_dec = None

            if quantity_str:
                try:
                    qty_dec = Decimal(quantity_str.replace(',', ''))
                    if qty_dec < 0:
                        row_errors.append("Quantity cannot be negative")
                    elif abs(qty_dec.as_tuple().exponent) > 3:
                        row_errors.append("Quantity has more than 3 decimal places")
                except InvalidOperation:
                    row_errors.append("Invalid quantity format")

            if rate_str:
                try:
                    rate_dec = Decimal(rate_str.replace(',', ''))
                    if rate_dec < 0:
                        row_errors.append("Rate cannot be negative")
                    elif abs(rate_dec.as_tuple().exponent) > 2:
                        row_errors.append("Rate has more than 2 decimal places")
                except InvalidOperation:
                    row_errors.append("Invalid rate format")

            if amount_str:
                try:
                    amt_dec = Decimal(amount_str.replace(',', ''))
                    if amt_dec < 0:
                        row_errors.append("Amount cannot be negative")
                    elif abs(amt_dec.as_tuple().exponent) > 2:
                        row_errors.append("Amount has more than 2 decimal places")
                except InvalidOperation:
                    row_errors.append("Invalid amount format")

            is_valid = len(row_errors) == 0
            has_discrepancy = False
            calculated_amount = None

            if is_valid:
                valid_items += 1
                calculated_amount = (qty_dec * rate_dec).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if calculated_amount != amt_dec:
                    has_discrepancy = True
                    source_discrepancies += 1
            else:
                validation_errors += 1

            field_map = {
                "item_code": item_code,
                "item_number": item_number,
                "description": description,
                "unit": unit,
                "quantity": quantity_str,
                "rate": rate_str,
                "source_amount": amount_str
            }

            source_ref = f"Sheet {chunk.sheet_name} Row {chunk.row_start}"

            for fname, fval in field_map.items():
                metadata = {}
                if item_code:
                    metadata["boq_item_code"] = item_code

                final_status = ValidationStatus.UNVALIDATED
                normalized_val = None

                if not is_valid:
                    final_status = ValidationStatus.INVALID
                    metadata["errors"] = row_errors
                else:
                    # Valid structure
                    if fname == "source_amount" and has_discrepancy:
                        final_status = ValidationStatus.CONFLICT
                        metadata["discrepancy"] = {
                            "source_amount": str(amt_dec),
                            "calculated_amount": str(calculated_amount),
                            "difference": str(amt_dec - calculated_amount)
                        }
                    else:
                        final_status = ValidationStatus.VALID

                    # Calculate normalized value
                    if fname == "quantity":
                        normalized_val = f"{qty_dec:.3f}"
                    elif fname == "rate":
                        normalized_val = f"{rate_dec:.2f}"
                    elif fname == "source_amount":
                        normalized_val = f"{amt_dec:.2f}"
                    else:
                        normalized_val = fval.strip()

                matched_id = None
                for fid, ef in unmatched_existing.items():
                    if ef.field_name == fname and ef.value == fval and ef.document_chunk_id == chunk.id:
                        matched_id = fid
                        break

                if matched_id:
                    ef = unmatched_existing[matched_id]
                    # Update metadata, status, normalized_value
                    needs_update = False
                    if ef.validation_status != final_status:
                        ef.validation_status = final_status
                        needs_update = True
                    if ef.metadata_json != metadata:
                        ef.metadata_json = metadata
                        flag_modified(ef, "metadata_json")
                        needs_update = True
                    if ef.normalized_value != normalized_val:
                        ef.normalized_value = normalized_val
                        needs_update = True

                    del unmatched_existing[matched_id]
                    facts_extracted += 1
                else:
                    fact = DocumentFact(
                        document_id=doc.id,
                        document_chunk_id=chunk.id,
                        fact_type="BOQ",
                        field_name=fname,
                        value=fval,
                        normalized_value=normalized_val,
                        source_reference=source_ref,
                        validation_status=final_status,
                        metadata_json=metadata
                    )
                    db.add(fact)
                    new_facts_added.append(fact)
                    facts_extracted += 1

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
                action="BOQ_FACTS_EXTRACTED",
                changes={
                    "rows_processed": rows_processed,
                    "valid_items": valid_items,
                    "validation_errors": validation_errors,
                    "source_discrepancies": source_discrepancies,
                    "extracted_count": len(new_facts_added),
                    "deleted_count": deleted_count
                }
            )

        db.commit()
        return {
            "rows_processed": rows_processed,
            "valid_items": valid_items,
            "facts_extracted": facts_extracted,
            "validation_errors": validation_errors,
            "source_discrepancies": source_discrepancies
        }
    except Exception as e:
        db.rollback()
        raise e

def extract_measurement_facts(db: Session, document_id: uuid.UUID, current_user: User) -> dict:
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError("Document not found")
        if doc.document_type != DocumentType.MEASUREMENT_BOOK:
            raise DocumentStateError(f"Extraction requires MEASUREMENT_BOOK document, got {doc.document_type}")
        if doc.ingestion_status != IngestionStatus.COMPLETED:
            raise DocumentStateError(f"Extraction requires COMPLETED ingestion, got {doc.ingestion_status}")

        if not doc.contract_id:
            raise ContractNotLinkedError("Measurement extraction requires a linked contract")

        approved_revision = db.query(BoqRevision).join(
            Boq, BoqRevision.boq_id == Boq.id
        ).filter(
            Boq.contract_id == doc.contract_id,
            BoqRevision.status == "Approved"
        ).first()

        if not approved_revision:
            raise DocumentStateError("Contract does not have an approved BOQ revision")

        boq_items = db.query(BoqItem.item_code).filter(BoqItem.revision_id == approved_revision.id).all()
        valid_boq_codes = {row[0] for row in boq_items}

        existing_facts = db.query(DocumentFact).filter(
            DocumentFact.document_id == document_id,
            DocumentFact.fact_type == "MEASUREMENT"
        ).all()

        unmatched_existing = {f.id: f for f in existing_facts}
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()

        rows_processed = 0
        valid_measurements = 0
        facts_extracted = 0
        validation_errors = 0
        duplicate_references = 0
        unknown_boq_links = 0

        parsed_rows = []
        ref_counts = {}

        for chunk in chunks:
            if chunk.sheet_name and "MEASUREMENT" not in chunk.sheet_name.upper():
                continue

            parts = [p.strip() for p in chunk.content.split(" | ")]
            if len(parts) == 0:
                continue

            while len(parts) < 6:
                parts.append("")

            reference = parts[0]
            if reference.upper() == "REFERENCE":
                continue

            if reference:
                ref_counts[reference] = ref_counts.get(reference, 0) + 1

            parsed_rows.append((chunk, parts))

        new_facts_added = []

        for chunk, parts in parsed_rows:
            reference = parts[0]
            date_str = parts[1]
            boq_item_code = parts[2]
            quantity_str = parts[3]
            location = parts[4]
            remarks = parts[5]

            rows_processed += 1
            row_errors = []

            if not reference: row_errors.append("Missing reference")
            if not date_str: row_errors.append("Missing date")
            if not boq_item_code: row_errors.append("Missing boq_item_code")
            if not quantity_str: row_errors.append("Missing quantity")

            is_duplicate = False
            if reference and ref_counts[reference] > 1:
                row_errors.append("Duplicate measurement reference")
                is_duplicate = True

            is_unknown_boq = False
            if boq_item_code and boq_item_code not in valid_boq_codes:
                row_errors.append(f"Unknown BOQ item code: {boq_item_code}")
                is_unknown_boq = True

            qty_dec = None
            if quantity_str:
                try:
                    qty_dec = Decimal(quantity_str.replace(',', ''))
                    if qty_dec < 0:
                        row_errors.append("Quantity cannot be negative")
                    elif abs(qty_dec.as_tuple().exponent) > 3:
                        row_errors.append("Quantity has more than 3 decimal places")
                except InvalidOperation:
                    row_errors.append("Invalid quantity format")

            date_val = None
            if date_str:
                parsed_date = None
                date_clean = date_str.split(" ")[0].strip() # Handle "2026-04-25 00:00:00"

                formats = [
                    "%Y-%m-%d",
                    "%d-%b-%Y",
                    "%d-%b-%y",
                    "%d/%m/%Y",
                    "%d/%m/%y"
                ]
                from datetime import datetime
                for fmt in formats:
                    try:
                        parsed_date = datetime.strptime(date_clean, fmt)
                        break
                    except ValueError:
                        pass

                if parsed_date:
                    date_val = parsed_date.strftime("%Y-%m-%d")
                else:
                    row_errors.append("Invalid date format")

            is_valid = len(row_errors) == 0

            if is_valid:
                valid_measurements += 1
            else:
                validation_errors += 1
                if is_duplicate:
                    duplicate_references += 1
                if is_unknown_boq:
                    unknown_boq_links += 1

            field_map = {
                "measurement_reference": reference,
                "measurement_date": date_str,
                "boq_item_code": boq_item_code,
                "quantity": quantity_str
            }
            if location: field_map["location"] = location
            if remarks: field_map["remarks"] = remarks

            source_ref = f"Sheet {chunk.sheet_name} Row {chunk.row_start}"

            for fname, fval in field_map.items():
                metadata = {}
                if reference:
                    metadata["measurement_reference"] = reference

                final_status = ValidationStatus.UNVALIDATED
                normalized_val = None

                if not is_valid:
                    final_status = ValidationStatus.INVALID
                    metadata["errors"] = row_errors
                else:
                    final_status = ValidationStatus.VALID
                    if fname == "quantity":
                        normalized_val = f"{qty_dec:.3f}"
                    elif fname == "measurement_date":
                        normalized_val = date_val
                    else:
                        normalized_val = fval.strip()

                matched_id = None
                for fid, ef in unmatched_existing.items():
                    if ef.field_name == fname and ef.value == fval and ef.document_chunk_id == chunk.id:
                        matched_id = fid
                        break

                if matched_id:
                    ef = unmatched_existing[matched_id]
                    needs_update = False
                    if ef.validation_status != final_status:
                        ef.validation_status = final_status
                        needs_update = True
                    if ef.metadata_json != metadata:
                        ef.metadata_json = metadata
                        flag_modified(ef, "metadata_json")
                        needs_update = True
                    if ef.normalized_value != normalized_val:
                        ef.normalized_value = normalized_val
                        needs_update = True

                    del unmatched_existing[matched_id]
                    facts_extracted += 1
                else:
                    fact = DocumentFact(
                        document_id=doc.id,
                        document_chunk_id=chunk.id,
                        fact_type="MEASUREMENT",
                        field_name=fname,
                        value=fval,
                        normalized_value=normalized_val,
                        source_reference=source_ref,
                        validation_status=final_status,
                        metadata_json=metadata
                    )
                    db.add(fact)
                    new_facts_added.append(fact)
                    facts_extracted += 1

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
                action="MEASUREMENT_FACTS_EXTRACTED",
                changes={
                    "rows_processed": rows_processed,
                    "valid_measurements": valid_measurements,
                    "validation_errors": validation_errors,
                    "duplicate_references": duplicate_references,
                    "unknown_boq_links": unknown_boq_links,
                    "extracted_count": len(new_facts_added),
                    "deleted_count": deleted_count
                }
            )

        db.commit()
        return {
            "rows_processed": rows_processed,
            "valid_measurements": valid_measurements,
            "facts_extracted": facts_extracted,
            "validation_errors": validation_errors,
            "duplicate_references": duplicate_references,
            "unknown_boq_links": unknown_boq_links
        }
    except Exception as e:
        db.rollback()
        raise e



def extract_ra_bill_facts(db: Session, document_id: uuid.UUID, current_user: User) -> dict:
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError("Document not found")
        if doc.document_type != DocumentType.RA_BILL:
            raise DocumentStateError(f"Extraction requires RA_BILL document, got {doc.document_type}")
        if doc.ingestion_status != IngestionStatus.COMPLETED:
            raise DocumentStateError(f"Extraction requires COMPLETED ingestion, got {doc.ingestion_status}")

        if not doc.contract_id:
            raise ContractNotLinkedError("RA Bill extraction requires a linked contract")

        approved_revision = db.query(BoqRevision).join(
            Boq, BoqRevision.boq_id == Boq.id
        ).filter(
            Boq.contract_id == doc.contract_id,
            BoqRevision.status == "Approved"
        ).first()

        if not approved_revision:
            raise DocumentStateError("Contract does not have an approved BOQ revision")

        existing_facts = db.query(DocumentFact).filter(
            DocumentFact.document_id == document_id,
            DocumentFact.fact_type.in_(["RA_BILL_COVER", "RA_BILL_ITEM"])
        ).all()
        
        unmatched_existing = {f.id: f for f in existing_facts}

        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index).all()
        
        summary = {
            "rows_processed": 0,
            "valid_facts": 0,
            "facts_extracted": 0,
            "validation_errors": 0,
            "duplicate_references": 0,
            "unknown_links": 0,
            "reconciliation_matches": 0,
            "reconciliation_mismatches": 0
        }
        
        calc_chunks = []
        cover_chunks = []
        link_chunks = []
        
        for chunk in chunks:
            if chunk.sheet_name == "Cover":
                cover_chunks.append(chunk)
            elif chunk.sheet_name == "Calculations":
                calc_chunks.append(chunk)
            elif chunk.sheet_name == "Measurement Links":
                link_chunks.append(chunk)
                
        # Parse Measurement Links
        linked_refs_from_sheet = set()
        link_headers = {}
        for chunk in link_chunks:
            parts = [p.strip() for p in chunk.content.split(" | ")]
            if not any(p for p in parts): continue
            
            if not link_headers:
                link_headers = {name.lower(): i for i, name in enumerate(parts) if name}
                continue
            
            ref = parts[link_headers.get("reference", 0)] if "reference" in link_headers and len(parts) > link_headers["reference"] else None
            if ref and "total" not in ref.lower():
                linked_refs_from_sheet.add(ref)

        cover_headers = {}
        canonical_bill = None
        has_changes = False
        
        for chunk in cover_chunks:
            parts = [p.strip() for p in chunk.content.split(" | ")]
            if not any(p for p in parts): continue
            
            if not cover_headers:
                cover_headers = {name.lower(): i for i, name in enumerate(parts) if name}
                continue
                
            summary["rows_processed"] += 1
            
            bill_number = parts[cover_headers.get("bill number", 0)] if "bill number" in cover_headers and len(parts) > cover_headers["bill number"] else None
            gross_amount_str = parts[cover_headers.get("gross amount", 1)] if "gross amount" in cover_headers and len(parts) > cover_headers["gross amount"] else None
            linked_meas_str = parts[cover_headers.get("linked measurements", 2)] if "linked measurements" in cover_headers and len(parts) > cover_headers["linked measurements"] else None
            
            validation_errors = []
            if not bill_number: validation_errors.append("Missing required field: Bill Number")
            if not gross_amount_str: validation_errors.append("Missing required field: Gross Amount")
            if not linked_meas_str: validation_errors.append("Missing required field: Linked Measurements")
                
            gross_dec = None
            if gross_amount_str:
                try:
                    gross_dec = Decimal(gross_amount_str)
                    if gross_dec < 0: validation_errors.append("Negative gross amount")
                except: validation_errors.append("Invalid gross amount format")
                    
            linked_meas = None
            if linked_meas_str:
                try:
                    linked_meas = int(linked_meas_str)
                except: validation_errors.append("Invalid linked measurements format")
            
            recon_status = None
            recon_details = []
            
            if not bill_number:
                recon_status = "MISMATCH"
                recon_details.append("No unambiguous canonical bill context (missing bill number)")
            else:
                canonical_bill = db.query(RABill).filter(
                    RABill.contract_id == doc.contract_id,
                    RABill.bill_number == bill_number
                ).first()
                
                if not canonical_bill:
                    recon_status = "MISMATCH"
                    recon_details.append("No canonical RA Bill found")
                else:
                    recon_status = "MATCH"
                    if gross_dec is not None and canonical_bill.gross_amount != gross_dec:
                        recon_status = "MISMATCH"
                        recon_details.append(f"Gross amount mismatch: expected {canonical_bill.gross_amount}, got {gross_dec}")
                    
                    if linked_meas is not None:
                        db_links = db.query(RABillMeasurement).join(RABillItem).filter(RABillItem.ra_bill_id == canonical_bill.id).count()
                        if db_links != linked_meas:
                            recon_status = "MISMATCH"
                            recon_details.append(f"Linked measurements mismatch: expected {db_links}, got {linked_meas}")
                        
            val_status = ValidationStatus.INVALID if validation_errors else ValidationStatus.VALID
            val_bill = bill_number or "UNKNOWN"
            
            matched_id = None
            for fid, ef in unmatched_existing.items():
                if ef.fact_type == "RA_BILL_COVER" and ef.value == val_bill:
                    matched_id = fid
                    break
            
            metadata = {
                "gross_amount": gross_amount_str,
                "linked_measurements": linked_meas_str,
                "errors": validation_errors,
                "reconciliation_status": recon_status,
                "reconciliation_errors": recon_details,
                "sheet_name": "Cover",
                "row_number": chunk.row_start
            }
            
            if matched_id:
                ef = unmatched_existing.pop(matched_id)
                if ef.validation_status != val_status or ef.metadata_json != metadata:
                    ef.validation_status = val_status
                    ef.metadata_json = metadata
                    has_changes = True
            else:
                fact = DocumentFact(
                    document_id=document_id,
                    document_chunk_id=chunk.id,
                    fact_type="RA_BILL_COVER",
                    field_name="bill_number",
                    value=val_bill,
                    validation_status=val_status,
                    source_reference=f"{chunk.sheet_name}:{chunk.row_start}",
                    metadata_json=metadata
                )
                db.add(fact)
                has_changes = True
                
            summary["facts_extracted"] += 1
            if val_status == ValidationStatus.VALID:
                summary["valid_facts"] += 1
            else:
                summary["validation_errors"] += 1
                
            if recon_status == "MATCH":
                summary["reconciliation_matches"] += 1
            elif recon_status == "MISMATCH":
                summary["reconciliation_mismatches"] += 1

        calc_headers = {}
        ref_counts = {}
        calc_refs = set()
        
        for chunk in calc_chunks:
            parts = [p.strip() for p in chunk.content.split(" | ")]
            if not any(p for p in parts): continue
            if not calc_headers:
                calc_headers = {name.lower(): i for i, name in enumerate(parts) if name}
                continue
                
            ref = parts[calc_headers.get("reference", 0)] if "reference" in calc_headers and len(parts) > calc_headers["reference"] else None
            item_code = parts[calc_headers.get("item code", 1)] if "item code" in calc_headers and len(parts) > calc_headers["item code"] else None
            
            if not ref or not item_code or "total" in ref.lower() or "total" in item_code.lower() or (len(parts) > calc_headers.get("rate", 3) and "total" in parts[calc_headers.get("rate", 3)].lower()):
                continue
                
            ref_counts[ref] = ref_counts.get(ref, 0) + 1
            calc_refs.add(ref)
            
        calc_headers = {}
        for chunk in calc_chunks:
            parts = [p.strip() for p in chunk.content.split(" | ")]
            if not any(p for p in parts): continue
            
            if not calc_headers:
                calc_headers = {name.lower(): i for i, name in enumerate(parts) if name}
                continue
                
            ref = parts[calc_headers.get("reference", 0)] if "reference" in calc_headers and len(parts) > calc_headers["reference"] else None
            item_code = parts[calc_headers.get("item code", 1)] if "item code" in calc_headers and len(parts) > calc_headers["item code"] else None
            qty_str = parts[calc_headers.get("quantity", 2)] if "quantity" in calc_headers and len(parts) > calc_headers["quantity"] else None
            rate_str = parts[calc_headers.get("rate", 3)] if "rate" in calc_headers and len(parts) > calc_headers["rate"] else None
            amount_str = parts[calc_headers.get("amount", 4)] if "amount" in calc_headers and len(parts) > calc_headers["amount"] else None
            
            if not ref or not item_code or "total" in ref.lower() or "total" in item_code.lower() or (rate_str and "total" in rate_str.lower()):
                continue
                
            summary["rows_processed"] += 1
            val_errors = []
            
            qty_dec = None
            rate_dec = None
            amount_dec = None
            
            if ref_counts.get(ref, 0) > 1:
                val_errors.append("Duplicate measurement reference")
                summary["duplicate_references"] += 1
                
            if linked_refs_from_sheet and ref not in linked_refs_from_sheet:
                val_errors.append("Measurement reference not found in Measurement Links sheet")
                
            try:
                qty_dec = Decimal(qty_str)
                if qty_dec < 0: val_errors.append("Negative quantity")
            except: val_errors.append("Invalid quantity format")
            
            try:
                rate_dec = Decimal(rate_str)
                if rate_dec < 0: val_errors.append("Negative rate")
            except: val_errors.append("Invalid rate format")
            
            try:
                if amount_str:
                    amount_dec = Decimal(amount_str)
                    if amount_dec < 0: val_errors.append("Negative amount")
            except: val_errors.append("Invalid amount format")
            
            if qty_dec is not None and rate_dec is not None and amount_dec is not None:
                calc_amt = round(qty_dec * rate_dec, 2)
                if calc_amt != amount_dec:
                    val_errors.append(f"Source amount {amount_dec} does not match qty * rate ({calc_amt})")
            
            recon_status = None
            recon_details = []
            
            if canonical_bill:
                canonical_meas = db.query(Measurement).filter(
                    Measurement.reference == ref,
                    Measurement.boq_item.has(revision_id=approved_revision.id)
                ).first()
                
                if not canonical_meas:
                    recon_status = "MISMATCH"
                    recon_details.append("Measurement reference not found in DB")
                    summary["unknown_links"] += 1
                else:
                    ra_meas = db.query(RABillMeasurement).join(RABillItem).filter(
                        RABillItem.ra_bill_id == canonical_bill.id,
                        RABillMeasurement.measurement_id == canonical_meas.id
                    ).first()
                    
                    if not ra_meas:
                        recon_status = "MISMATCH"
                        recon_details.append("Measurement not linked to this RA Bill")
                    else:
                        ra_item = ra_meas.ra_bill_item
                        recon_status = "MATCH"
                        
                        if ra_item.boq_item.item_code != item_code:
                            recon_status = "MISMATCH"
                            recon_details.append(f"BOQ Item code mismatch: expected {ra_item.boq_item.item_code}, got {item_code}")
                            
                        if qty_dec is not None and canonical_meas.quantity != qty_dec:
                            recon_status = "MISMATCH"
                            recon_details.append(f"Quantity mismatch: expected {canonical_meas.quantity}, got {qty_dec}")
                            
                        if rate_dec is not None and ra_item.rate != rate_dec:
                            recon_status = "MISMATCH"
                            recon_details.append(f"Rate mismatch: expected {ra_item.rate}, got {rate_dec}")
                            
                        expected_amt = round(canonical_meas.quantity * ra_item.rate, 2)
                        if amount_dec is not None and amount_dec != expected_amt:
                            recon_status = "MISMATCH"
                            recon_details.append(f"Amount mismatch: expected {expected_amt}, got {amount_dec}")
            else:
                recon_status = "MISMATCH"
                recon_details.append("No canonical RA Bill context")
                
            val_status = ValidationStatus.INVALID if val_errors else ValidationStatus.VALID
            
            matched_id = None
            for fid, ef in unmatched_existing.items():
                if ef.fact_type == "RA_BILL_ITEM" and ef.value == ref:
                    matched_id = fid
                    break
            
            metadata = {
                "boq_item_code": item_code,
                "quantity": qty_str,
                "rate": rate_str,
                "amount": amount_str,
                "errors": val_errors,
                "reconciliation_status": recon_status,
                "reconciliation_errors": recon_details,
                "sheet_name": "Calculations",
                "row_number": chunk.row_start
            }
            
            if matched_id:
                ef = unmatched_existing.pop(matched_id)
                if ef.validation_status != val_status or ef.metadata_json != metadata:
                    ef.validation_status = val_status
                    ef.metadata_json = metadata
                    has_changes = True
            else:
                fact = DocumentFact(
                    document_id=document_id,
                    document_chunk_id=chunk.id,
                    fact_type="RA_BILL_ITEM",
                    field_name="measurement_reference",
                    value=ref,
                    validation_status=val_status,
                    source_reference=f"{chunk.sheet_name}:{chunk.row_start}",
                    metadata_json=metadata
                )
                db.add(fact)
                has_changes = True
                
            summary["facts_extracted"] += 1
            if val_status == ValidationStatus.VALID:
                summary["valid_facts"] += 1
            else:
                summary["validation_errors"] += 1
                
            if recon_status == "MATCH":
                summary["reconciliation_matches"] += 1
            elif recon_status == "MISMATCH":
                summary["reconciliation_mismatches"] += 1
                
        for fid, ef in unmatched_existing.items():
            db.delete(ef)
            has_changes = True
            
        print('HAS CHANGES:', has_changes)
        if has_changes:
            from app.services.audit_service import add_audit_log
            add_audit_log(db, current_user.id, "Document", document_id, "RA_BILL_FACTS_EXTRACTED", summary)
            db.commit()
        else:
            db.rollback()
            
        return summary
    except Exception:
        db.rollback()
        raise
