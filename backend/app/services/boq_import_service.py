import csv
import io
import math
import re
import uuid
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from fastapi import HTTPException, UploadFile
from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.boq_item import BoqItem
from app.models.boq_revision import BoqRevision
from app.models.user import User
from app.schemas.boq import BoqItemCreate
from app.schemas.boq_import import (
    BoqImportError,
    BoqImportItemPreview,
    BoqImportPreviewResponse,
    BoqImportResponse,
)
from app.services.audit_service import add_audit_log
from app.services.boq_service import _amount, _ensure_revision_editable, get_revision, revision_detail

SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}
REQUIRED_COLUMNS = {"item_number", "description", "unit", "quantity", "rate"}
HEADER_ALIASES = {
    "itemnumber": "item_number",
    "item_number": "item_number",
    "itemcode": "item_code",
    "item_code": "item_code",
    "description": "description",
    "unit": "unit",
    "quantity": "quantity",
    "rate": "rate",
    "amount": "amount",
}


@dataclass
class ParsedImport:
    rows: list[tuple[int, dict[str, Any]]]
    ignored_columns: list[str]
    warnings: list[str]


def _extension(filename: str | None) -> str:
    extension = PurePath(filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Only .csv and .xlsx files are supported.")
    return extension


async def read_upload(upload: UploadFile) -> bytes:
    _extension(upload.filename)
    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.BOQ_IMPORT_MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="BOQ import file exceeds the configured size limit.")
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=422, detail="Import file is empty.")
    return b"".join(chunks)


def _normalize_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s_-]+", "_", text).strip("_")


def _header_mapping(headers: list[Any]) -> tuple[dict[int, str], list[str], list[BoqImportError]]:
    mapping: dict[int, str] = {}
    ignored: list[str] = []
    errors: list[BoqImportError] = []
    seen: set[str] = set()
    for index, raw_header in enumerate(headers):
        display_header = str(raw_header or "").strip()
        normalized = _normalize_header(raw_header).replace("_", "")
        logical_name = HEADER_ALIASES.get(normalized)
        if not logical_name:
            if display_header:
                ignored.append(display_header)
            continue
        if logical_name in seen:
            errors.append(BoqImportError(field=logical_name, message="Duplicate column header."))
            continue
        seen.add(logical_name)
        mapping[index] = logical_name
    missing = sorted(REQUIRED_COLUMNS - seen)
    for column in missing:
        errors.append(BoqImportError(field=column, message="Required column is missing."))
    if "amount" in seen:
        ignored.append("amount (ignored; server calculates amount)")
    return mapping, ignored, errors


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _decimal_text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        # openpyxl exposes literal Excel numerics as float; str() preserves the
        # user-visible decimal representation without binary artifacts.
        return str(value)
    return str(value).strip()


def _parse_csv(content: bytes) -> list[list[Any]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=422, detail="CSV file must be UTF-8 encoded.") from error
    try:
        return list(csv.reader(io.StringIO(text), strict=True))
    except csv.Error as error:
        raise HTTPException(status_code=422, detail="CSV file could not be parsed.") from error


def _parse_xlsx(content: bytes) -> list[list[Any]]:
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise HTTPException(status_code=422, detail="The uploaded XLSX content is invalid.")
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        worksheet = workbook.active
        rows = [list(row) for row in worksheet.iter_rows(values_only=True)]
        workbook.close()
        return rows
    except (KeyError, OSError, ValueError, zipfile.BadZipFile) as error:
        raise HTTPException(status_code=422, detail="The uploaded XLSX content is invalid.") from error


def parse_import_file(filename: str | None, content: bytes) -> ParsedImport:
    extension = _extension(filename)
    if extension == ".xlsx":
        rows = _parse_xlsx(content)
    else:
        rows = _parse_csv(content)
    if not rows:
        raise HTTPException(status_code=422, detail="Import file has no header row.")

    mapping, ignored_columns, header_errors = _header_mapping(rows[0])
    if header_errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": [error.model_dump() for error in header_errors], "ignored_columns": ignored_columns},
        )

    parsed_rows: list[tuple[int, dict[str, Any]]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        if all(_cell_text(value) == "" for value in row):
            continue
        values = {logical_name: (row[index] if index < len(row) else None) for index, logical_name in mapping.items()}
        parsed_rows.append((row_number, values))
    if not parsed_rows:
        raise HTTPException(status_code=422, detail="Import file contains no data rows.")
    warnings = []
    if "item_code" not in {name for name in mapping.values()}:
        warnings.append("item_code column missing; item_number will be used as item_code.")
    return ParsedImport(parsed_rows, ignored_columns, warnings)


def _row_item(row: dict[str, Any]) -> BoqItemCreate:
    item_number = _cell_text(row.get("item_number"))
    item_code = _cell_text(row.get("item_code")) or item_number
    return BoqItemCreate(
        item_code=item_code,
        item_number=item_number,
        description=_cell_text(row.get("description")),
        unit=_cell_text(row.get("unit")),
        quantity=_decimal_text(row.get("quantity")),
        rate=_decimal_text(row.get("rate")),
    )


def _validation_errors(row_number: int, error: ValidationError) -> list[BoqImportError]:
    errors = []
    for detail in error.errors():
        field = str(detail.get("loc", ["row"])[0])
        errors.append(BoqImportError(row=row_number, field=field, message=detail["msg"]))
    return errors


def validate_parsed_rows(
    parsed: ParsedImport,
    existing_item_numbers: set[str] | None = None,
) -> BoqImportPreviewResponse:
    errors: list[BoqImportError] = []
    items: list[BoqImportItemPreview] = []
    seen: set[str] = set()
    existing = existing_item_numbers or set()
    has_item_code_column = any("item_code" in row for _, row in parsed.rows)
    for row_number, raw_row in parsed.rows:
        try:
            if has_item_code_column and not _cell_text(raw_row.get("item_code")):
                parsed.warnings.append(
                    f"Row {row_number}: item_code is blank; item_number was used as item_code."
                )
            item = _row_item(raw_row)
            if item.item_number in seen:
                errors.append(BoqImportError(row=row_number, field="item_number", message="Duplicate item_number within uploaded file."))
                continue
            if item.item_number in existing:
                errors.append(BoqImportError(row=row_number, field="item_number", message="item_number already exists in this revision."))
                continue
            seen.add(item.item_number)
            items.append(
                BoqImportItemPreview(
                    **item.model_dump(),
                    amount=_amount(item.quantity, item.rate),
                )
            )
        except ValidationError as error:
            errors.extend(_validation_errors(row_number, error))
        except HTTPException as error:
            errors.append(BoqImportError(row=row_number, message=str(error.detail)))
    invalid_rows = len({error.row for error in errors if error.row is not None})
    return BoqImportPreviewResponse(
        valid=not errors,
        total_rows=len(parsed.rows),
        valid_rows=len(parsed.rows) - invalid_rows,
        invalid_rows=invalid_rows,
        warnings=parsed.warnings,
        ignored_columns=parsed.ignored_columns,
        errors=errors,
        items=items,
    )


def preview_import(db: Session, revision_id: uuid.UUID, filename: str | None, content: bytes) -> BoqImportPreviewResponse:
    revision = get_revision(db, revision_id)
    _ensure_revision_editable(revision)
    parsed = parse_import_file(filename, content)
    existing = {
        item_number
        for (item_number,) in db.query(BoqItem.item_number).filter(BoqItem.revision_id == revision_id).all()
    }
    return validate_parsed_rows(parsed, existing)


def import_items(
    db: Session,
    revision_id: uuid.UUID,
    filename: str | None,
    content: bytes,
    current_user: User,
) -> BoqImportResponse:
    revision = get_revision(db, revision_id)
    _ensure_revision_editable(revision)
    parsed = parse_import_file(filename, content)
    existing = {
        item_number
        for (item_number,) in db.query(BoqItem.item_number).filter(BoqItem.revision_id == revision_id).all()
    }
    preview = validate_parsed_rows(parsed, existing)
    if not preview.valid:
        raise HTTPException(status_code=422, detail=preview.model_dump(mode="json"))

    created: list[BoqItem] = []
    try:
        for item_preview in preview.items:
            item = BoqItem(
                revision_id=revision_id,
                item_code=item_preview.item_code,
                item_number=item_preview.item_number,
                description=item_preview.description,
                unit=item_preview.unit,
                quantity=item_preview.quantity,
                rate=item_preview.rate,
                amount=item_preview.amount,
            )
            db.add(item)
            created.append(item)
        db.flush()
        add_audit_log(
            db,
            current_user.id,
            "BOQImport",
            revision_id,
            "IMPORT",
            {"filename": filename or "unnamed", "revision_id": str(revision_id), "imported_rows": len(created)},
        )
        db.commit()
        for item in created:
            db.refresh(item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Import conflicts with existing BOQ items.")

    _, _, _, total = revision_detail(db, revision_id)
    return BoqImportResponse(
        revision_id=revision_id,
        imported_count=len(created),
        created_item_ids=[item.id for item in created],
        total=total,
    )