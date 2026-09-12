import csv
import io
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.models.audit_log import AuditLog
from app.models.boq import Boq
from app.models.boq_item import BoqItem
from app.models.boq_revision import BoqRevision
from app.models.contract import Contract
from app.models.user import User
from app.core.database import SessionLocal
from app.services import boq_import_service


class Query:
    def __init__(self, values):
        self.values = values

    def filter(self, *args):
        return self

    def all(self):
        return self.values

    def first(self):
        return self.values[0] if self.values else None


class ImportSession:
    def __init__(self, revision, existing_items=None):
        self.revision = revision
        self.existing_items = existing_items or []
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        if model is BoqRevision:
            return Query([self.revision])
        if model is BoqItem:
            return Query([(item.item_number,) for item in self.existing_items] + [
                (item.item_number,) for item in self.added if isinstance(item, BoqItem)
            ])
        return Query([])

    def add(self, value):
        self.added.append(value)
        if isinstance(value, BoqItem) and value.id is None:
            value.id = uuid4()

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, value):
        return None


def csv_bytes(rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def xlsx_bytes(rows):
    workbook = Workbook()
    worksheet = workbook.active
    for row in rows:
        worksheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def valid_rows():
    return [
        ["Item Number", "Description", "Unit", "Quantity", "Rate", "Amount", "Imported Note"],
        ["1", "Earthwork", "Cum", "12.345", "250.50", "999999", "ignored"],
        ["2", "Tiling", "Sqm", "85.5", "1250.75", "ignored"],
    ]


def draft_revision():
    return SimpleNamespace(id=uuid4(), status="Draft")


def test_valid_csv_preview_and_amounts():
    parsed = boq_import_service.parse_import_file("boq.csv", csv_bytes(valid_rows()))
    preview = boq_import_service.validate_parsed_rows(parsed)

    assert preview.valid is True
    assert preview.total_rows == 2
    assert preview.valid_rows == 2
    assert preview.invalid_rows == 0
    assert preview.items[0].item_code == "1"
    assert preview.items[0].amount == Decimal("3092.42")
    assert "amount (ignored; server calculates amount)" in preview.ignored_columns
    assert "Imported Note" in preview.ignored_columns


def test_valid_xlsx_preview():
    parsed = boq_import_service.parse_import_file("boq.xlsx", xlsx_bytes(valid_rows()))
    preview = boq_import_service.validate_parsed_rows(parsed)

    assert preview.valid is True
    assert preview.items[1].quantity == Decimal("85.5")
    assert preview.items[1].amount == Decimal("106939.13")


def test_missing_required_column_rejected():
    with pytest.raises(HTTPException) as error:
        boq_import_service.parse_import_file("boq.csv", csv_bytes([["item_number", "description"]]))

    assert error.value.status_code == 422
    assert any(item["field"] == "unit" for item in error.value.detail["errors"])


def test_unknown_extra_column_and_amount_are_reported():
    parsed = boq_import_service.parse_import_file("boq.csv", csv_bytes(valid_rows()))

    assert "Imported Note" in parsed.ignored_columns
    assert "amount (ignored; server calculates amount)" in parsed.ignored_columns


def test_blank_item_code_warns_with_spreadsheet_row():
    rows = [
        ["item_number", "item_code", "description", "unit", "quantity", "rate"],
        ["1", "", "Earthwork", "Cum", "1.000", "10.00"],
    ]
    parsed = boq_import_service.parse_import_file("boq.csv", csv_bytes(rows))
    preview = boq_import_service.validate_parsed_rows(parsed)

    assert preview.valid is True
    assert preview.items[0].item_code == "1"
    assert "Row 2: item_code is blank; item_number was used as item_code." in preview.warnings


def test_malformed_csv_quoting_is_rejected():
    malformed = b'item_number,description,unit,quantity,rate\n1,"Unclosed,Cum,1.000,10.00\n'

    with pytest.raises(HTTPException) as error:
        boq_import_service.parse_import_file("boq.csv", malformed)

    assert error.value.status_code == 422
    assert "CSV file could not be parsed" in error.value.detail


def test_negative_and_excess_precision_values_are_rejected():
    rows = [
        ["item_number", "description", "unit", "quantity", "rate"],
        ["1", "Negative quantity", "Cum", "-1", "10.00"],
        ["2", "Negative rate", "Cum", "1.000", "-10.00"],
        ["3", "Quantity precision", "Cum", "1.0001", "10.00"],
        ["4", "Rate precision", "Cum", "1.000", "10.001"],
    ]
    preview = boq_import_service.validate_parsed_rows(
        boq_import_service.parse_import_file("boq.csv", csv_bytes(rows))
    )

    assert preview.valid is False
    assert preview.invalid_rows == 4
    assert {error.field for error in preview.errors} == {"quantity", "rate"}


def test_malformed_partial_and_blank_rows_are_reported():
    rows = [
        ["item_number", "description", "unit", "quantity", "rate"],
        ["1", "Malformed quantity", "Cum", "not-a-number", "10.00"],
        ["2", "Partial", "", "1.000", "10.00"],
        ["3", "Malformed rate", "Cum", "1.000", "not-a-rate"],
        ["", "", "", "", ""],
    ]
    parsed = boq_import_service.parse_import_file("boq.csv", csv_bytes(rows))
    preview = boq_import_service.validate_parsed_rows(parsed)

    assert preview.total_rows == 3
    assert preview.invalid_rows == 3
    assert {error.row for error in preview.errors} == {2, 3, 4}


def test_duplicates_within_file_and_existing_revision_are_rejected():
    rows = [
        ["item_number", "description", "unit", "quantity", "rate"],
        ["1", "First", "Cum", "1.000", "10.00"],
        ["1", "Duplicate", "Cum", "2.000", "10.00"],
        ["2", "Existing", "Cum", "2.000", "10.00"],
    ]
    parsed = boq_import_service.parse_import_file("boq.csv", csv_bytes(rows))
    preview = boq_import_service.validate_parsed_rows(parsed, {"2"})

    assert preview.valid is False
    assert any("within uploaded file" in error.message for error in preview.errors)
    assert any("already exists" in error.message for error in preview.errors)


def test_unsupported_and_empty_files_rejected():
    with pytest.raises(HTTPException) as unsupported:
        boq_import_service.parse_import_file("boq.xls", b"data")
    assert unsupported.value.status_code == 422

    with pytest.raises(HTTPException) as empty:
        boq_import_service.parse_import_file("boq.csv", b"")
    assert empty.value.status_code == 422


def test_import_is_atomic_on_invalid_row(monkeypatch):
    revision = draft_revision()
    db = ImportSession(revision)
    monkeypatch.setattr(boq_import_service, "revision_detail", lambda *_: (None, revision, [], Decimal("0.00")))
    content = csv_bytes([
        ["item_number", "description", "unit", "quantity", "rate"],
        ["1", "Valid", "Cum", "1.000", "10.00"],
        ["2", "Invalid", "Cum", "1.0001", "10.00"],
    ])

    with pytest.raises(HTTPException) as error:
        boq_import_service.import_items(db, revision.id, "atomic.csv", content, SimpleNamespace(id=uuid4()))

    assert error.value.status_code == 422
    assert db.commits == 0
    assert not [value for value in db.added if isinstance(value, BoqItem)]


def test_successful_import_calculates_amounts_and_audits(monkeypatch):
    revision = draft_revision()
    db = ImportSession(revision)
    monkeypatch.setattr(
        boq_import_service,
        "revision_detail",
        lambda *_: (None, revision, [], Decimal("3092.42")),
    )
    content = csv_bytes([
        ["item_number", "description", "unit", "quantity", "rate"],
        ["1", "Rounding", "Cum", "1.005", "1.00"],
    ])

    result = boq_import_service.import_items(db, revision.id, "success.csv", content, SimpleNamespace(id=uuid4()))

    items = [value for value in db.added if isinstance(value, BoqItem)]
    audits = [value for value in db.added if isinstance(value, AuditLog)]
    assert db.commits == 1
    assert result.imported_count == 1
    assert items[0].amount == Decimal("1.01")
    assert audits[0].entity_name == "BOQImport"
    assert audits[0].action == "IMPORT"


@pytest.mark.parametrize("status", ["Submitted", "Approved", "Superseded"])
def test_locked_revision_is_rejected(status):
    revision = SimpleNamespace(id=uuid4(), status=status)
    db = ImportSession(revision)

    with pytest.raises(HTTPException) as error:
        boq_import_service.preview_import(db, revision.id, "boq.csv", csv_bytes(valid_rows()))

    assert error.value.status_code == 409


def test_upload_size_limit_is_enforced(monkeypatch):
    class Upload:
        filename = "boq.csv"
        def __init__(self):
            self.calls = 0
        async def read(self, _size):
            self.calls += 1
            return b"x" * (11 * 1024 * 1024) if self.calls == 1 else b""

    monkeypatch.setattr(boq_import_service.settings, "BOQ_IMPORT_MAX_FILE_SIZE_BYTES", 10 * 1024 * 1024)

    import asyncio
    with pytest.raises(HTTPException) as error:
        asyncio.run(boq_import_service.read_upload(Upload()))

    assert error.value.status_code == 413


def test_viewer_is_denied_import_endpoint(client):
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "viewer@infrapm.gov", "password": "View@123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    response = client.post(
        "/api/v1/boq-revisions/00000000-0000-0000-0000-000000000001/import/preview",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("boq.csv", b"item_number,description,unit,quantity,rate\n1,Item,Cum,1,10.00\n", "text/csv")},
    )

    assert response.status_code == 403


def _create_integration_revision():
    db = SessionLocal()
    contract = db.query(Contract).first()
    admin = db.query(User).filter(User.email == "admin@infrapm.gov").first()
    assert contract is not None
    assert admin is not None
    boq = Boq(
        contract_id=contract.id,
        boq_number=f"IMPORT-TEST-{uuid4().hex[:12]}",
        title="Import Integration Test",
    )
    db.add(boq)
    db.flush()
    revision = BoqRevision(
        boq_id=boq.id,
        revision_number=1,
        revision_date=date(2026, 9, 12),
        status="Draft",
    )
    db.add(revision)
    db.commit()
    return db, boq, revision, admin


def _cleanup_integration_revision(db, boq_id, revision_id):
    items = db.query(BoqItem).filter(BoqItem.revision_id == revision_id).all()
    entity_ids = [boq_id, revision_id, *(item.id for item in items)]
    db.query(AuditLog).filter(AuditLog.entity_id.in_(entity_ids)).delete(synchronize_session=False)
    db.query(BoqItem).filter(BoqItem.revision_id == revision_id).delete(synchronize_session=False)
    db.query(BoqRevision).filter(BoqRevision.id == revision_id).delete(synchronize_session=False)
    db.query(Boq).filter(Boq.id == boq_id).delete(synchronize_session=False)
    db.commit()


def test_postgresql_import_persists_items_amounts_total_and_audit():
    db, boq, revision, admin = _create_integration_revision()
    try:
        content = csv_bytes([
            ["item_number", "item_code", "description", "unit", "quantity", "rate"],
            ["1", "", "Rounding item", "Cum", "1.005", "1.00"],
            ["2", "CIV-002", "Second item", "Nos", "2.000", "10.00"],
        ])
        result = boq_import_service.import_items(
            db, revision.id, "integration.csv", content, admin
        )

        items = db.query(BoqItem).filter(BoqItem.revision_id == revision.id).order_by(BoqItem.item_number).all()
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.entity_name == "BOQImport", AuditLog.entity_id == revision.id)
            .first()
        )
        _, _, _, total = boq_import_service.revision_detail(db, revision.id)

        assert result.imported_count == 2
        assert [item.amount for item in items] == [Decimal("1.01"), Decimal("20.00")]
        assert items[0].item_code == "1"
        assert audit is not None
        assert audit.changes["imported_rows"] == 2
        assert total == Decimal("21.01")
    finally:
        _cleanup_integration_revision(db, boq.id, revision.id)
        db.close()


def test_postgresql_import_invalid_row_is_atomic():
    db, boq, revision, admin = _create_integration_revision()
    try:
        content = csv_bytes([
            ["item_number", "description", "unit", "quantity", "rate"],
            ["1", "Valid item", "Cum", "1.000", "10.00"],
            ["2", "Invalid item", "Cum", "1.0001", "10.00"],
        ])

        with pytest.raises(HTTPException) as error:
            boq_import_service.import_items(
                db, revision.id, "atomic-integration.csv", content, admin
            )

        assert error.value.status_code == 422
        assert db.query(BoqItem).filter(BoqItem.revision_id == revision.id).count() == 0
        assert (
            db.query(AuditLog)
            .filter(AuditLog.entity_name == "BOQImport", AuditLog.entity_id == revision.id)
            .count()
            == 0
        )
    finally:
        _cleanup_integration_revision(db, boq.id, revision.id)
        db.close()
