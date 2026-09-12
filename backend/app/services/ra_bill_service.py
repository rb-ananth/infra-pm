import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import List

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.ra_bill import RABill, RABillItem, RABillMeasurement, RABillDeduction
from app.models.boq import Boq
from app.models.boq_revision import BoqRevision
from app.models.boq_item import BoqItem
from app.models.contract import Contract
from app.models.measurement import Measurement
from app.schemas.ra_bill import (
    RABillCreate,
    RABillUpdate,
    RABillDeductionCreate,
    RABillDeductionUpdate,
)
from app.services.audit_service import add_audit_log

def quantize_amount(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def quantize_qty(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

class RABillService:
    @staticmethod
    def _recalculate_totals(db: Session, ra_bill: RABill):
        # We assume the RA Bill is locked (SELECT FOR UPDATE)
        gross = Decimal("0.00")
        for item in ra_bill.items:
            gross += item.current_amount
            
        deductions = Decimal("0.00")
        for ded in ra_bill.deductions:
            deductions += ded.amount
            
        net = gross - deductions
        if net < 0:
            raise HTTPException(status_code=422, detail="Net payable cannot be negative")
            
        ra_bill.gross_amount = quantize_amount(gross)
        ra_bill.deductions_amount = quantize_amount(deductions)
        ra_bill.net_payable = quantize_amount(net)
        db.flush()

    @staticmethod
    def _validate_bill_editable(ra_bill: RABill):
        if ra_bill.status not in ["Draft", "Rejected"]:
            raise HTTPException(status_code=403, detail=f"Bill is {ra_bill.status} and cannot be modified")

    @staticmethod
    def _ensure_draft(ra_bill: RABill):
        if ra_bill.status == "Rejected":
            ra_bill.status = "Draft"

    @staticmethod
    def create_bill(db: Session, payload: RABillCreate, user_id: uuid.UUID) -> RABill:
        # Validate contract
        contract = db.execute(select(Contract).where(Contract.id == payload.contract_id)).scalar_one_or_none()
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        # Check unique bill number
        existing = db.execute(
            select(RABill).where(RABill.contract_id == payload.contract_id, RABill.bill_number == payload.bill_number)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Bill number already exists for this contract")

        bill = RABill(
            contract_id=payload.contract_id,
            bill_number=payload.bill_number,
            bill_date=payload.bill_date,
            period_from=payload.period_from,
            period_to=payload.period_to,
            remarks=payload.remarks,
            created_by=user_id,
        )
        db.add(bill)
        db.flush()

        add_audit_log(db, user_id, "ra_bills", bill.id, "RA_BILL_CREATE", {"bill_number": bill.bill_number})
        db.commit()
        db.refresh(bill)
        return bill

    @staticmethod
    def update_bill(db: Session, bill_id: uuid.UUID, payload: RABillUpdate, user_id: uuid.UUID) -> RABill:
        bill = db.execute(select(RABill).where(RABill.id == bill_id).with_for_update()).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")

        RABillService._validate_bill_editable(bill)

        if payload.bill_number and payload.bill_number != bill.bill_number:
            existing = db.execute(
                select(RABill).where(RABill.contract_id == bill.contract_id, RABill.bill_number == payload.bill_number)
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(status_code=409, detail="Bill number already exists for this contract")
            bill.bill_number = payload.bill_number

        if payload.bill_date: bill.bill_date = payload.bill_date
        if payload.period_from: bill.period_from = payload.period_from
        if payload.period_to: bill.period_to = payload.period_to
        if payload.remarks is not None: bill.remarks = payload.remarks

        RABillService._ensure_draft(bill)
        
        db.flush()
        add_audit_log(db, user_id, "ra_bills", bill.id, "RA_BILL_UPDATE", {})
        db.commit()
        db.refresh(bill)
        return bill

    @staticmethod
    def submit_bill(db: Session, bill_id: uuid.UUID, user_id: uuid.UUID) -> RABill:
        bill = db.execute(select(RABill).where(RABill.id == bill_id).with_for_update()).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")
        if bill.status != "Draft":
            raise HTTPException(status_code=403, detail=f"Cannot submit from {bill.status}")
        
        if not bill.items:
            raise HTTPException(status_code=422, detail="Cannot submit an empty RA Bill")

        bill.status = "Submitted"
        db.flush()
        add_audit_log(db, user_id, "ra_bills", bill.id, "RA_BILL_SUBMIT", {})
        db.commit()
        db.refresh(bill)
        return bill

    @staticmethod
    def approve_bill(db: Session, bill_id: uuid.UUID, user_id: uuid.UUID) -> RABill:
        bill = db.execute(select(RABill).where(RABill.id == bill_id).with_for_update()).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")
        if bill.status != "Submitted":
            raise HTTPException(status_code=403, detail=f"Cannot approve from {bill.status}")

        bill.status = "Approved"
        db.flush()
        add_audit_log(db, user_id, "ra_bills", bill.id, "RA_BILL_APPROVE", {})
        db.commit()
        db.refresh(bill)
        return bill

    @staticmethod
    def reject_bill(db: Session, bill_id: uuid.UUID, user_id: uuid.UUID) -> RABill:
        bill = db.execute(select(RABill).where(RABill.id == bill_id).with_for_update()).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")
        if bill.status != "Submitted":
            raise HTTPException(status_code=403, detail=f"Cannot reject from {bill.status}")

        bill.status = "Rejected"
        db.flush()
        add_audit_log(db, user_id, "ra_bills", bill.id, "RA_BILL_REJECT", {})
        db.commit()
        db.refresh(bill)
        return bill

    @staticmethod
    def get_bill(db: Session, bill_id: uuid.UUID) -> RABill:
        bill = db.execute(select(RABill).where(RABill.id == bill_id)).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")
        return bill

    @staticmethod
    def list_bills(db: Session, contract_id: uuid.UUID = None) -> List[RABill]:
        stmt = select(RABill).order_by(RABill.created_at.desc())
        if contract_id:
            stmt = stmt.where(RABill.contract_id == contract_id)
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def add_measurements(db: Session, bill_id: uuid.UUID, measurement_ids: List[uuid.UUID], user_id: uuid.UUID):
        bill = db.execute(select(RABill).where(RABill.id == bill_id).with_for_update()).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")
        
        RABillService._validate_bill_editable(bill)
        RABillService._ensure_draft(bill)

        if not measurement_ids:
            return bill

        # Lock measurements and validate
        measurements = db.execute(
            select(Measurement).where(Measurement.id.in_(measurement_ids)).with_for_update()
        ).scalars().all()
        
        if len(measurements) != len(measurement_ids):
            raise HTTPException(status_code=404, detail="One or more measurements not found")

        # Group by boq_item_id
        grouped = {}
        for m in measurements:
            if m.status != "Approved":
                raise HTTPException(status_code=422, detail=f"Measurement {m.reference} is not Approved")
            if m.boq_item_id not in grouped:
                grouped[m.boq_item_id] = []
            grouped[m.boq_item_id].append(m)

        for boq_item_id, ms in grouped.items():
            # Validate Cross-Contract Integrity and get rate
            boq_item = db.execute(select(BoqItem).where(BoqItem.id == boq_item_id)).scalar_one()
            revision = db.execute(select(BoqRevision).where(BoqRevision.id == boq_item.revision_id)).scalar_one()
            boq = db.execute(select(Boq).where(Boq.id == revision.boq_id)).scalar_one()
            
            if boq.contract_id != bill.contract_id:
                raise HTTPException(status_code=422, detail="Measurement does not belong to this contract")
            if revision.status != "Approved":
                raise HTTPException(status_code=422, detail="Measurement belongs to an unapproved BOQ revision")

            # Check if bill item exists
            bill_item = db.execute(
                select(RABillItem).where(RABillItem.ra_bill_id == bill_id, RABillItem.boq_item_id == boq_item_id)
            ).scalar_one_or_none()

            total_qty_to_add = sum(m.quantity for m in ms)

            if not bill_item:
                bill_item = RABillItem(
                    ra_bill_id=bill_id,
                    boq_item_id=boq_item_id,
                    current_quantity=quantize_qty(total_qty_to_add),
                    rate=boq_item.rate,
                    current_amount=quantize_amount(total_qty_to_add * boq_item.rate)
                )
                db.add(bill_item)
                db.flush()
            else:
                bill_item.current_quantity = quantize_qty(bill_item.current_quantity + total_qty_to_add)
                bill_item.current_amount = quantize_amount(bill_item.current_quantity * bill_item.rate)
                db.flush()

            # Insert links (Catches Double Billing via UNIQUE constraint on measurement_id)
            for m in ms:
                try:
                    link = RABillMeasurement(ra_bill_item_id=bill_item.id, measurement_id=m.id)
                    db.add(link)
                    db.flush()
                except IntegrityError:
                    db.rollback()
                    raise HTTPException(status_code=409, detail=f"Measurement {m.reference} is already billed")

            add_audit_log(db, user_id, "ra_bill_items", bill_item.id, "RA_BILL_ITEM_ADD", {
                "boq_item_id": str(boq_item_id),
                "measurement_ids": [str(m.id) for m in ms],
                "added_quantity": float(total_qty_to_add),
                "rate": float(bill_item.rate),
            })

        RABillService._recalculate_totals(db, bill)
        db.commit()
        db.refresh(bill)
        return bill

    @staticmethod
    def remove_item(db: Session, bill_id: uuid.UUID, item_id: uuid.UUID, user_id: uuid.UUID):
        bill = db.execute(select(RABill).where(RABill.id == bill_id).with_for_update()).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")
        
        RABillService._validate_bill_editable(bill)
        RABillService._ensure_draft(bill)

        item = db.execute(select(RABillItem).where(RABillItem.id == item_id, RABillItem.ra_bill_id == bill_id)).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="RA Bill Item not found")

        measurement_ids = [str(m.measurement_id) for m in item.measurements]
        qty = float(item.current_quantity)
        rate = float(item.rate)

        db.delete(item)
        db.flush()

        RABillService._recalculate_totals(db, bill)
        
        add_audit_log(db, user_id, "ra_bill_items", item_id, "RA_BILL_ITEM_REMOVE", {
            "boq_item_id": str(item.boq_item_id),
            "measurement_ids": measurement_ids,
            "removed_quantity": qty,
            "rate": rate,
        })
        db.commit()

    @staticmethod
    def add_deduction(db: Session, bill_id: uuid.UUID, payload: RABillDeductionCreate, user_id: uuid.UUID) -> RABillDeduction:
        bill = db.execute(select(RABill).where(RABill.id == bill_id).with_for_update()).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")
        
        RABillService._validate_bill_editable(bill)
        RABillService._ensure_draft(bill)

        deduction = RABillDeduction(
            ra_bill_id=bill_id,
            deduction_type=payload.deduction_type,
            description=payload.description,
            amount=quantize_amount(payload.amount),
        )
        db.add(deduction)
        db.flush()

        RABillService._recalculate_totals(db, bill)

        add_audit_log(db, user_id, "ra_bill_deductions", deduction.id, "RA_BILL_DEDUCTION_CREATE", {})
        db.commit()
        db.refresh(deduction)
        return deduction

    @staticmethod
    def update_deduction(db: Session, bill_id: uuid.UUID, deduction_id: uuid.UUID, payload: RABillDeductionUpdate, user_id: uuid.UUID):
        bill = db.execute(select(RABill).where(RABill.id == bill_id).with_for_update()).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")
        
        RABillService._validate_bill_editable(bill)
        RABillService._ensure_draft(bill)

        ded = db.execute(select(RABillDeduction).where(RABillDeduction.id == deduction_id, RABillDeduction.ra_bill_id == bill_id)).scalar_one_or_none()
        if not ded:
            raise HTTPException(status_code=404, detail="Deduction not found")

        ded.deduction_type = payload.deduction_type
        ded.description = payload.description
        ded.amount = quantize_amount(payload.amount)
        db.flush()

        RABillService._recalculate_totals(db, bill)
        add_audit_log(db, user_id, "ra_bill_deductions", ded.id, "RA_BILL_DEDUCTION_UPDATE", {})
        db.commit()
        db.refresh(ded)
        return ded
        
    @staticmethod
    def remove_deduction(db: Session, bill_id: uuid.UUID, deduction_id: uuid.UUID, user_id: uuid.UUID):
        bill = db.execute(select(RABill).where(RABill.id == bill_id).with_for_update()).scalar_one_or_none()
        if not bill:
            raise HTTPException(status_code=404, detail="RA Bill not found")
        
        RABillService._validate_bill_editable(bill)
        RABillService._ensure_draft(bill)

        ded = db.execute(select(RABillDeduction).where(RABillDeduction.id == deduction_id, RABillDeduction.ra_bill_id == bill_id)).scalar_one_or_none()
        if not ded:
            raise HTTPException(status_code=404, detail="Deduction not found")

        db.delete(ded)
        db.flush()

        RABillService._recalculate_totals(db, bill)
        add_audit_log(db, user_id, "ra_bill_deductions", deduction_id, "RA_BILL_DEDUCTION_DELETE", {})
        db.commit()

    @staticmethod
    def decorate_bill_detail(db: Session, bill: RABill) -> dict:
        """Derives cumulative data for items on the fly by scanning historical approved bills."""
        result = {
            "id": bill.id,
            "contract_id": bill.contract_id,
            "bill_number": bill.bill_number,
            "bill_date": bill.bill_date,
            "period_from": bill.period_from,
            "period_to": bill.period_to,
            "status": bill.status,
            "gross_amount": bill.gross_amount,
            "deductions_amount": bill.deductions_amount,
            "net_payable": bill.net_payable,
            "remarks": bill.remarks,
            "created_by": bill.created_by,
            "created_at": bill.created_at,
            "updated_at": bill.updated_at,
            "items": [],
            "deductions": bill.deductions,
        }

        # Query all approved historical items for the relevant boq_items to calc cumulative
        boq_item_ids = [i.boq_item_id for i in bill.items]
        
        historical_stats = {}
        if boq_item_ids:
            # We want SUM(current_quantity) and SUM(current_amount) for these boq items from APPROVED bills
            hist_stmt = select(
                RABillItem.boq_item_id,
                func.sum(RABillItem.current_quantity).label("sum_qty"),
                func.sum(RABillItem.current_amount).label("sum_amt")
            ).join(RABill, RABill.id == RABillItem.ra_bill_id).where(
                RABill.status == "Approved",
                RABillItem.boq_item_id.in_(boq_item_ids)
            )
            # If the current bill is Approved, we MUST exclude it from the "previous" sum
            # so we can compute previous = hist_without_current
            # Since cumulative = previous + current
            hist_stmt = hist_stmt.where(RABill.id != bill.id).group_by(RABillItem.boq_item_id)
            
            for row in db.execute(hist_stmt).all():
                historical_stats[row.boq_item_id] = {
                    "sum_qty": row.sum_qty or Decimal("0.000"),
                    "sum_amt": row.sum_amt or Decimal("0.00"),
                }

        for item in bill.items:
            h = historical_stats.get(item.boq_item_id, {"sum_qty": Decimal("0.000"), "sum_amt": Decimal("0.00")})
            
            prev_qty = h["sum_qty"]
            prev_amt = h["sum_amt"]
            
            cum_qty = prev_qty + item.current_quantity
            cum_amt = prev_amt + item.current_amount
            bal_qty = item.boq_item.quantity - cum_qty
            
            perc = Decimal("0.00")
            if item.boq_item.quantity > 0:
                perc = quantize_amount((cum_qty / item.boq_item.quantity) * 100)
            
            item_dict = {
                "id": item.id,
                "ra_bill_id": item.ra_bill_id,
                "boq_item_id": item.boq_item_id,
                "current_quantity": item.current_quantity,
                "rate": item.rate,
                "current_amount": item.current_amount,
                "boq_item": item.boq_item,
                "previous_cumulative_quantity": prev_qty,
                "cumulative_quantity": cum_qty,
                "balance_quantity": bal_qty,
                "cumulative_amount": cum_amt,
                "percentage_executed": perc,
                "measurements": [rm.measurement for rm in item.measurements]
            }
            result["items"].append(item_dict)

        return result

    @staticmethod
    def get_eligible_measurements(db: Session, contract_id: uuid.UUID) -> List[Measurement]:
        # Measurements that are Approved
        # Belongs to the given contract (via boq_item -> revision -> boq)
        # Belongs to an Approved revision
        # Not in ra_bill_measurements
        
        subq = select(RABillMeasurement.measurement_id)
        
        stmt = (
            select(Measurement)
            .join(BoqItem, Measurement.boq_item_id == BoqItem.id)
            .join(BoqRevision, BoqItem.revision_id == BoqRevision.id)
            .join(Boq, BoqRevision.boq_id == Boq.id)
            .where(
                Measurement.status == "Approved",
                Boq.contract_id == contract_id,
                BoqRevision.status == "Approved",
                Measurement.id.not_in(subq)
            )
        )
        return list(db.execute(stmt).scalars().all())
