import uuid
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, require_roles
from app.models.user import User
from app.schemas.ra_bill import (
    RABillCreate,
    RABillUpdate,
    RABillOut,
    RABillDetailOut,
    RABillDeductionCreate,
    RABillDeductionUpdate,
    RABillDeductionOut,
    RABillItemCreateMulti,
)
from app.schemas.measurement import MeasurementOut
from app.services.ra_bill_service import RABillService

router = APIRouter(prefix="/ra-bills", tags=["RA Bills"])

@router.get("/", response_model=List[RABillOut])
def list_bills(
    contract_id: uuid.UUID = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer", "Billing Engineer", "Viewer")),
):
    return RABillService.list_bills(db, contract_id=contract_id)

@router.post("/", response_model=RABillOut, status_code=201)
def create_bill(
    payload: RABillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    return RABillService.create_bill(db, payload, current_user.id)

@router.get("/{bill_id}", response_model=RABillDetailOut)
def get_bill(
    bill_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Engineer", "Billing Engineer", "Viewer")),
):
    bill = RABillService.get_bill(db, bill_id)
    return RABillService.decorate_bill_detail(db, bill)

@router.put("/{bill_id}", response_model=RABillOut)
def update_bill(
    bill_id: uuid.UUID,
    payload: RABillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    return RABillService.update_bill(db, bill_id, payload, current_user.id)

@router.post("/{bill_id}/submit", response_model=RABillOut)
def submit_bill(
    bill_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    return RABillService.submit_bill(db, bill_id, current_user.id)

@router.post("/{bill_id}/approve", response_model=RABillOut)
def approve_bill(
    bill_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager")),
):
    return RABillService.approve_bill(db, bill_id, current_user.id)

@router.post("/{bill_id}/reject", response_model=RABillOut)
def reject_bill(
    bill_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    return RABillService.reject_bill(db, bill_id, current_user.id)

@router.post("/{bill_id}/items", response_model=RABillDetailOut)
def add_items(
    bill_id: uuid.UUID,
    payload: RABillItemCreateMulti,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    bill = RABillService.add_measurements(db, bill_id, payload.measurement_ids, current_user.id)
    return RABillService.decorate_bill_detail(db, bill)

@router.delete("/{bill_id}/items/{item_id}", status_code=204)
def remove_item(
    bill_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    RABillService.remove_item(db, bill_id, item_id, current_user.id)

@router.post("/{bill_id}/deductions", response_model=RABillDeductionOut, status_code=201)
def add_deduction(
    bill_id: uuid.UUID,
    payload: RABillDeductionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    return RABillService.add_deduction(db, bill_id, payload, current_user.id)

@router.put("/{bill_id}/deductions/{deduction_id}", response_model=RABillDeductionOut)
def update_deduction(
    bill_id: uuid.UUID,
    deduction_id: uuid.UUID,
    payload: RABillDeductionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    return RABillService.update_deduction(db, bill_id, deduction_id, payload, current_user.id)

@router.delete("/{bill_id}/deductions/{deduction_id}", status_code=204)
def remove_deduction(
    bill_id: uuid.UUID,
    deduction_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    RABillService.remove_deduction(db, bill_id, deduction_id, current_user.id)

@router.get("/{contract_id}/eligible-measurements", response_model=List[MeasurementOut])
def get_eligible_measurements(
    contract_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Project Manager", "Billing Engineer")),
):
    return RABillService.get_eligible_measurements(db, contract_id)
