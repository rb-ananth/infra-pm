from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.deps import require_roles
from app.models.boq import Boq
from app.models.boq_item import BoqItem
from app.models.boq_revision import BoqRevision
from app.models.contract import Contract
from app.models.user import User
from app.schemas.boq import (
    BoqCreate,
    BoqItemCreate,
    BoqItemUpdate,
    BoqRevisionCreate,
)
from app.services import boq_service


class FakeQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value

    def all(self):
        if isinstance(self.value, list):
            return self.value
        return [self.value] if self.value else []


class FakeSession:
    def __init__(self, values=None, flush_error=None):
        self.values = values or {}
        self.flush_error = flush_error
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        return FakeQuery(self.values.get(model))

    def add(self, value):
        self.added.append(value)

    def flush(self):
        if self.flush_error:
            raise self.flush_error

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, value):
        return None


def user(role_name="Admin"):
    return User(id=uuid4(), role=SimpleNamespace(name=role_name))


def contract():
    return Contract(id=uuid4())


def revision(status="Draft"):
    return BoqRevision(id=uuid4(), boq_id=uuid4(), revision_number=1, revision_date="2026-09-12", status=status)


def item(revision_value, quantity="2.000", rate="10.00", amount="20.00"):
    return BoqItem(
        id=uuid4(),
        revision_id=revision_value.id,
        item_code="CIV-001",
        item_number="1",
        description="Concrete",
        unit="m3",
        quantity=Decimal(quantity),
        rate=Decimal(rate),
        amount=Decimal(amount),
        revision=revision_value,
    )


def test_create_boq_against_valid_contract():
    current_contract = contract()
    db = FakeSession({Contract: current_contract})

    result = boq_service.create_boq(
        db,
        BoqCreate(contract_id=current_contract.id, boq_number=" BOQ-001 ", title=" Main Works "),
        user(),
    )

    assert result.contract_id == current_contract.id
    assert result.boq_number == "BOQ-001"
    assert db.commits == 1


def test_reject_boq_for_nonexistent_contract():
    db = FakeSession({Contract: None})

    with pytest.raises(HTTPException) as error:
        boq_service.create_boq(
            db,
            BoqCreate(contract_id=uuid4(), boq_number="BOQ-001", title="Main Works"),
            user(),
        )

    assert error.value.status_code == 400


def test_duplicate_boq_number_is_rejected():
    db = FakeSession(
        {Contract: contract()},
        IntegrityError("insert", {}, Exception("duplicate")),
    )

    with pytest.raises(HTTPException) as error:
        boq_service.create_boq(
            db,
            BoqCreate(contract_id=uuid4(), boq_number="BOQ-001", title="Main Works"),
            user(),
        )

    assert error.value.status_code == 409


def test_create_revision():
    boq = Boq(id=uuid4(), contract_id=uuid4(), boq_number="BOQ-001", title="Main Works", status="Draft")
    db = FakeSession({Boq: boq})

    result = boq_service.create_revision(
        db,
        boq.id,
        BoqRevisionCreate(revision_number=1, revision_date="2026-09-12"),
        user(),
    )

    assert result.boq_id == boq.id
    assert result.revision_number == 1


def test_duplicate_revision_number_is_rejected():
    boq = Boq(id=uuid4(), contract_id=uuid4(), boq_number="BOQ-001", title="Main Works", status="Draft")
    db = FakeSession({Boq: boq}, IntegrityError("insert", {}, Exception("duplicate")))

    with pytest.raises(HTTPException) as error:
        boq_service.create_revision(
            db,
            boq.id,
            BoqRevisionCreate(revision_number=1, revision_date="2026-09-12"),
            user(),
        )

    assert error.value.status_code == 409


def test_create_item_calculates_amount_server_side():
    current_revision = revision()
    db = FakeSession({BoqRevision: current_revision})

    result = boq_service.create_item(
        db,
        current_revision.id,
        BoqItemCreate(
            item_code="CIV-001",
            item_number="1",
            description="Concrete",
            unit="m3",
            quantity=Decimal("2.125"),
            rate=Decimal("10.50"),
        ),
        user(),
    )

    assert result.amount == Decimal("22.31")


def test_quantity_with_three_decimal_places_is_accepted():
    data = BoqItemCreate(
        item_code="CIV-001",
        item_number="1",
        description="Concrete",
        unit="m3",
        quantity=Decimal("2.125"),
        rate=Decimal("10.50"),
    )

    assert data.quantity == Decimal("2.125")


def test_quantity_with_four_decimal_places_is_rejected():
    with pytest.raises(ValueError, match="Quantity cannot have more than 3"):
        BoqItemCreate(
            item_code="CIV-001",
            item_number="1",
            description="Concrete",
            unit="m3",
            quantity=Decimal("2.1251"),
            rate=Decimal("10.50"),
        )


def test_rate_with_two_decimal_places_is_accepted():
    data = BoqItemCreate(
        item_code="CIV-001",
        item_number="1",
        description="Concrete",
        unit="m3",
        quantity=Decimal("2.125"),
        rate=Decimal("10.50"),
    )

    assert data.rate == Decimal("10.50")


def test_rate_with_three_decimal_places_is_rejected():
    with pytest.raises(ValueError, match="Rate cannot have more than 2"):
        BoqItemCreate(
            item_code="CIV-001",
            item_number="1",
            description="Concrete",
            unit="m3",
            quantity=Decimal("2.125"),
            rate=Decimal("10.501"),
        )


def test_client_supplied_amount_is_ignored():
    data = BoqItemCreate.model_validate(
        {
            "item_code": "CIV-001",
            "item_number": "1",
            "description": "Concrete",
            "unit": "m3",
            "quantity": "2.000",
            "rate": "10.00",
            "amount": "999999.99",
        }
    )

    assert not hasattr(data, "amount")


def test_negative_client_amount_cannot_be_persisted():
    current_revision = revision()
    db = FakeSession({BoqRevision: current_revision})

    data = BoqItemCreate.model_validate(
        {
            "item_code": "CIV-001",
            "item_number": "1",
            "description": "Concrete",
            "unit": "m3",
            "quantity": "2.000",
            "rate": "10.00",
            "amount": "-999.99",
        }
    )
    result = boq_service.create_item(db, current_revision.id, data, user())

    assert result.amount == Decimal("20.00")
    assert result.amount >= 0


def test_negative_quantity_is_rejected():
    with pytest.raises(ValueError):
        BoqItemCreate(
            item_code="CIV-001",
            item_number="1",
            description="Concrete",
            unit="m3",
            quantity=Decimal("-1"),
            rate=Decimal("10.00"),
        )


def test_negative_rate_is_rejected():
    with pytest.raises(ValueError):
        BoqItemCreate(
            item_code="CIV-001",
            item_number="1",
            description="Concrete",
            unit="m3",
            quantity=Decimal("1"),
            rate=Decimal("-10.00"),
        )


def test_duplicate_item_number_is_rejected():
    current_revision = revision()
    db = FakeSession(
        {BoqRevision: current_revision},
        IntegrityError("insert", {}, Exception("duplicate")),
    )

    with pytest.raises(HTTPException) as error:
        boq_service.create_item(
            db,
            current_revision.id,
            BoqItemCreate(
                item_code="CIV-001",
                item_number="1",
                description="Concrete",
                unit="m3",
                quantity=Decimal("1"),
                rate=Decimal("10"),
            ),
            user(),
        )

    assert error.value.status_code == 409


def test_approved_revision_prevents_item_creation():
    current_revision = revision("Approved")
    db = FakeSession({BoqRevision: current_revision})

    with pytest.raises(HTTPException) as error:
        boq_service.create_item(
            db,
            current_revision.id,
            BoqItemCreate(
                item_code="CIV-001",
                item_number="1",
                description="Concrete",
                unit="m3",
                quantity=Decimal("1"),
                rate=Decimal("10"),
            ),
            user(),
        )

    assert error.value.status_code == 409


def test_approved_revision_prevents_item_update():
    current_revision = revision("Approved")
    current_item = item(current_revision)
    db = FakeSession({BoqItem: current_item})

    with pytest.raises(HTTPException) as error:
        boq_service.update_item(
            db,
            current_item.id,
            BoqItemUpdate(quantity=Decimal("3")),
            user(),
        )

    assert error.value.status_code == 409


def test_revision_total_equals_sum_of_item_amounts():
    current_revision = revision()
    boq = Boq(id=current_revision.boq_id, contract_id=uuid4(), boq_number="BOQ-001", title="Main Works")
    items = [item(current_revision, amount="20.00"), item(current_revision, amount="12.35")]
    db = FakeSession({BoqRevision: current_revision, Boq: boq, BoqItem: items})

    _, _, _, total = boq_service.revision_detail(db, current_revision.id)

    assert total == Decimal("32.35")


def test_engineer_can_read_but_cannot_use_write_role_dependency():
    checker = require_roles("Admin", "Project Manager")

    assert checker(SimpleNamespace(role=SimpleNamespace(name="Admin"))).role.name == "Admin"
    with pytest.raises(HTTPException) as error:
        checker(SimpleNamespace(role=SimpleNamespace(name="Engineer")))

    assert error.value.status_code == 403