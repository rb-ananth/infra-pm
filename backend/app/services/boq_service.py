import uuid
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.boq import Boq
from app.models.boq_item import BoqItem
from app.models.boq_revision import BoqRevision
from app.models.contract import Contract
from app.models.user import User
from app.schemas.boq import BoqCreate, BoqItemCreate, BoqItemUpdate, BoqRevisionCreate, BoqRevisionUpdate, BoqUpdate
from app.services.audit_service import add_audit_log

MONEY_QUANTUM = Decimal("0.01")
EDITABLE_REVISION_STATUSES = {"Draft"}
REVISION_STATUS_TRANSITIONS = {
    "Draft": {"Draft", "Submitted", "Approved", "Superseded"},
    "Submitted": {"Submitted", "Approved", "Superseded"},
    "Approved": {"Approved", "Superseded"},
    "Superseded": {"Superseded"},
}


def _amount(quantity: Decimal, rate: Decimal) -> Decimal:
    if quantity < 0 or quantity.as_tuple().exponent < -3:
        raise HTTPException(status_code=422, detail="Quantity must be nonnegative with at most 3 decimal places.")
    if rate < 0 or rate.as_tuple().exponent < -2:
        raise HTTPException(status_code=422, detail="Rate must be nonnegative with at most 2 decimal places.")
    return (quantity * rate).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _ensure_revision_editable(revision: BoqRevision) -> None:
    if revision.status not in EDITABLE_REVISION_STATUSES:
        raise HTTPException(status_code=409, detail="Only Draft revisions can be modified.")


def _commit(db: Session, conflict_detail: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=conflict_detail)


def list_boqs(db: Session) -> list[Boq]:
    return db.query(Boq).order_by(Boq.boq_number).all()


def get_boq(db: Session, boq_id: uuid.UUID) -> Boq:
    boq = db.query(Boq).filter(Boq.id == boq_id).first()
    if not boq:
        raise HTTPException(status_code=404, detail="BOQ not found.")
    return boq


def create_boq(db: Session, data: BoqCreate, current_user: User) -> Boq:
    if not db.query(Contract).filter(Contract.id == data.contract_id).first():
        raise HTTPException(status_code=400, detail="Contract not found.")

    boq = Boq(**data.model_dump())
    db.add(boq)
    try:
        db.flush()
        add_audit_log(db, current_user.id, "BOQ", boq.id, "CREATE", data.model_dump(mode="json"))
        _commit(db, "BOQ number already exists for this contract.")
        db.refresh(boq)
        return boq
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="BOQ number already exists for this contract.")


def update_boq(db: Session, boq_id: uuid.UUID, data: BoqUpdate, current_user: User) -> Boq:
    boq = get_boq(db, boq_id)
    update_data = data.model_dump(exclude_unset=True)
    old_values = {}
    new_values = {}
    for field, value in update_data.items():
        old_value = getattr(boq, field)
        if old_value != value:
            old_values[field] = str(old_value)
            new_values[field] = str(value)
            setattr(boq, field, value)

    if new_values:
        add_audit_log(db, current_user.id, "BOQ", boq.id, "UPDATE", {"old": old_values, "new": new_values})
        _commit(db, "BOQ number already exists for this contract.")
        db.refresh(boq)
    return boq


def list_revisions(db: Session, boq_id: uuid.UUID) -> list[BoqRevision]:
    get_boq(db, boq_id)
    return (
        db.query(BoqRevision)
        .filter(BoqRevision.boq_id == boq_id)
        .order_by(BoqRevision.revision_number)
        .all()
    )


def create_revision(db: Session, boq_id: uuid.UUID, data: BoqRevisionCreate, current_user: User) -> BoqRevision:
    get_boq(db, boq_id)
    revision = BoqRevision(boq_id=boq_id, **data.model_dump())
    db.add(revision)
    try:
        db.flush()
        add_audit_log(db, current_user.id, "BOQRevision", revision.id, "CREATE", data.model_dump(mode="json"))
        _commit(db, "Revision number already exists for this BOQ.")
        db.refresh(revision)
        return revision
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Revision number already exists for this BOQ.")


def get_revision(db: Session, revision_id: uuid.UUID) -> BoqRevision:
    revision = db.query(BoqRevision).filter(BoqRevision.id == revision_id).first()
    if not revision:
        raise HTTPException(status_code=404, detail="BOQ revision not found.")
    return revision


def update_revision(
    db: Session, revision_id: uuid.UUID, data: BoqRevisionUpdate, current_user: User
) -> BoqRevision:
    revision = get_revision(db, revision_id)
    update_data = data.model_dump(exclude_unset=True)
    if revision.status != "Draft" and any(field != "status" for field in update_data):
        raise HTTPException(status_code=409, detail="Only Draft revisions can be modified.")
    if "status" in update_data and update_data["status"] not in REVISION_STATUS_TRANSITIONS[revision.status]:
        raise HTTPException(status_code=409, detail="Invalid BOQ revision status transition.")

    old_values = {}
    new_values = {}
    for field, value in update_data.items():
        old_value = getattr(revision, field)
        if old_value != value:
            old_values[field] = str(old_value)
            new_values[field] = str(value)
            setattr(revision, field, value)

    if new_values:
        add_audit_log(
            db, current_user.id, "BOQRevision", revision.id, "UPDATE", {"old": old_values, "new": new_values}
        )
        _commit(db, "Unable to update BOQ revision.")
        db.refresh(revision)
    return revision


def revision_detail(db: Session, revision_id: uuid.UUID) -> tuple[Boq, BoqRevision, list[BoqItem], Decimal]:
    revision = get_revision(db, revision_id)
    boq = get_boq(db, revision.boq_id)
    items = db.query(BoqItem).filter(BoqItem.revision_id == revision.id).order_by(BoqItem.item_number).all()
    total = sum((item.amount for item in items), Decimal("0.00")).quantize(MONEY_QUANTUM)
    return boq, revision, items, total


def list_items(db: Session, revision_id: uuid.UUID) -> list[BoqItem]:
    get_revision(db, revision_id)
    return db.query(BoqItem).filter(BoqItem.revision_id == revision_id).order_by(BoqItem.item_number).all()


def create_item(db: Session, revision_id: uuid.UUID, data: BoqItemCreate, current_user: User) -> BoqItem:
    revision = get_revision(db, revision_id)
    _ensure_revision_editable(revision)
    item_data = data.model_dump()
    item = BoqItem(revision_id=revision_id, amount=_amount(item_data["quantity"], item_data["rate"]), **item_data)
    db.add(item)
    try:
        db.flush()
        add_audit_log(db, current_user.id, "BOQItem", item.id, "CREATE", {**data.model_dump(mode="json"), "amount": str(item.amount)})
        _commit(db, "Item number already exists for this revision.")
        db.refresh(item)
        return item
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Item number already exists for this revision.")


def get_item(db: Session, item_id: uuid.UUID) -> BoqItem:
    item = db.query(BoqItem).filter(BoqItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="BOQ item not found.")
    return item


def update_item(db: Session, item_id: uuid.UUID, data: BoqItemUpdate, current_user: User) -> BoqItem:
    item = get_item(db, item_id)
    _ensure_revision_editable(item.revision)
    update_data = data.model_dump(exclude_unset=True)
    final_quantity = update_data.get("quantity", item.quantity)
    final_rate = update_data.get("rate", item.rate)
    update_data["amount"] = _amount(final_quantity, final_rate)

    old_values = {}
    new_values = {}
    for field, value in update_data.items():
        old_value = getattr(item, field)
        if old_value != value:
            old_values[field] = str(old_value)
            new_values[field] = str(value)
            setattr(item, field, value)

    if new_values:
        add_audit_log(db, current_user.id, "BOQItem", item.id, "UPDATE", {"old": old_values, "new": new_values})
        _commit(db, "Item number already exists for this revision.")
        db.refresh(item)
    return item