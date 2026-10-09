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

        valid_boq_codes = set()
        if doc.contract_id:
            boq_items = db.query(BoqItem.item_code).join(
                BoqRevision, BoqItem.revision_id == BoqRevision.id
            ).join(
                Boq, BoqRevision.boq_id == Boq.id
            ).filter(
                Boq.contract_id == doc.contract_id,
                BoqRevision.status == "Approved"
            ).all()
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
