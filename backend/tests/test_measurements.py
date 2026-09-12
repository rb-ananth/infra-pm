from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.functions import Function

from app.api.deps import require_roles
from app.models.boq_item import BoqItem
from app.models.boq_revision import BoqRevision
from app.models.measurement import Measurement
from app.models.user import User
from app.schemas.measurement import MeasurementCreate, MeasurementUpdate
from app.services import measurement_service

class FakeQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def with_for_update(self, *args, **kwargs):
        return self

    def first(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value

    def all(self):
        if isinstance(self.value, list):
            return self.value
        return [self.value] if self.value else []
        
    def scalar(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value


class FakeSession:
    def __init__(self, values=None, flush_error=None):
        self.values = values or {}
        self.flush_error = flush_error
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model_or_func):
        if hasattr(model_or_func, "name") and model_or_func.name == "sum":
            return FakeQuery(self.values.get("sum", 0))
        # Fallback if it's some other non-class object
        if not isinstance(model_or_func, type):
            return FakeQuery(self.values.get("sum", 0))
        return FakeQuery(self.values.get(model_or_func))

    def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid4()
        if getattr(value, "created_at", None) is None:
            value.created_at = datetime.utcnow()
        if getattr(value, "updated_at", None) is None:
            value.updated_at = datetime.utcnow()
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


from datetime import datetime

def boq_item(status="Approved", qty="100.000"):
    rev = BoqRevision(
        id=uuid4(), boq_id=uuid4(), revision_number=1, revision_date="2026-09-12", status=status,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow()
    )
    return BoqItem(
        id=uuid4(),
        revision_id=rev.id,
        item_code="CIV-001",
        item_number="1",
        description="Concrete",
        unit="m3",
        quantity=Decimal(qty),
        rate=Decimal("10.00"),
        amount=Decimal("1000.00"),
        revision=rev,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def measurement(status="Draft", boq_item_val=None, qty="10.000"):
    if not boq_item_val:
        boq_item_val = boq_item()
    return Measurement(
        id=uuid4(),
        boq_item_id=boq_item_val.id,
        measurement_date="2026-09-12",
        quantity=Decimal(qty),
        reference="MB-1/Page-1",
        description="Foundations",
        status=status,
        boq_item=boq_item_val,
        created_by=uuid4(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def test_create_measurement_success():
    item_val = boq_item("Approved")
    db = FakeSession({BoqItem: item_val, "sum": Decimal("0.000")})

    result = measurement_service.create_measurement(
        db,
        MeasurementCreate(
            boq_item_id=item_val.id,
            measurement_date="2026-09-12",
            quantity=Decimal("15.500"),
            reference="Ref 1",
            description="Desc 1",
        ),
        user(),
    )

    assert result.measurement.quantity == Decimal("15.500")
    assert result.measurement.status == "Draft"
    assert db.commits == 1


def test_create_measurement_on_unapproved_boq_fails():
    item_val = boq_item("Draft")
    db = FakeSession({BoqItem: item_val, "sum": Decimal("0.000")})

    with pytest.raises(HTTPException) as exc:
        measurement_service.create_measurement(
            db,
            MeasurementCreate(
                boq_item_id=item_val.id,
                measurement_date="2026-09-12",
                quantity=Decimal("15.500"),
                reference="Ref 1",
                description="Desc 1",
            ),
            user(),
        )
    assert exc.value.status_code == 400


def test_update_measurement_success():
    meas = measurement("Draft")
    db = FakeSession({Measurement: meas, "sum": Decimal("0.000")})

    result = measurement_service.update_measurement(
        db,
        meas.id,
        MeasurementUpdate(quantity=Decimal("20.000")),
        user(),
    )
    assert result.measurement.quantity == Decimal("20.000")


def test_update_measurement_not_draft_or_rejected_fails():
    meas = measurement("Submitted")
    db = FakeSession({Measurement: meas, "sum": Decimal("0.000")})

    with pytest.raises(HTTPException) as exc:
        measurement_service.update_measurement(
            db,
            meas.id,
            MeasurementUpdate(quantity=Decimal("20.000")),
            user(),
        )
    assert exc.value.status_code == 409


def test_update_rejected_measurement_sets_draft():
    meas = measurement("Rejected")
    db = FakeSession({Measurement: meas, "sum": Decimal("0.000")})

    result = measurement_service.update_measurement(
        db,
        meas.id,
        MeasurementUpdate(quantity=Decimal("20.000")),
        user(),
    )
    assert result.measurement.status == "Draft"


def test_submit_measurement():
    meas = measurement("Draft")
    db = FakeSession({Measurement: meas, "sum": Decimal("0.000")})

    result = measurement_service.submit_measurement(db, meas.id, user())
    assert result.measurement.status == "Submitted"


def test_approve_measurement():
    meas = measurement("Submitted")
    db = FakeSession({Measurement: meas, BoqItem: meas.boq_item, "sum": Decimal("0.000")})

    result = measurement_service.approve_measurement(db, meas.id, user())
    assert result.measurement.status == "Approved"


def test_reject_measurement():
    meas = measurement("Submitted")
    db = FakeSession({Measurement: meas, "sum": Decimal("0.000")})

    result = measurement_service.reject_measurement(db, meas.id, user())
    assert result.measurement.status == "Rejected"


def test_measurement_detail_calculations():
    item_val = boq_item("Approved", qty="100.000")
    meas = measurement("Approved", boq_item_val=item_val, qty="40.000")
    
    # Simulate existing sum of 40
    db = FakeSession({Measurement: meas, "sum": Decimal("40.000")})
    
    result = measurement_service.get_measurement_detail(db, meas.id)
    assert result.cumulative_approved_quantity == Decimal("40.000")
    assert result.balance_quantity == Decimal("60.000")
    assert result.percentage_executed == Decimal("40.00")
    assert result.is_overrun is False
    assert result.overrun_quantity is None


def test_measurement_detail_overrun():
    item_val = boq_item("Approved", qty="100.000")
    meas = measurement("Approved", boq_item_val=item_val, qty="120.000")
    
    # Simulate existing sum of 120
    db = FakeSession({Measurement: meas, "sum": Decimal("120.000")})
    
    result = measurement_service.get_measurement_detail(db, meas.id)
    assert result.cumulative_approved_quantity == Decimal("120.000")
    assert result.balance_quantity == Decimal("-20.000")
    assert result.percentage_executed == Decimal("120.00")
    assert result.is_overrun is True
    assert result.overrun_quantity == Decimal("20.000")
