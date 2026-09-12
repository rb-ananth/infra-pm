from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator, ConfigDict

from app.schemas.boq import BoqItemResponse
from app.schemas.measurement import MeasurementOut

class RABillDeductionBase(BaseModel):
    deduction_type: str = Field(..., max_length=100)
    description: Optional[str] = None
    amount: Decimal = Field(..., ge=0, decimal_places=2)

class RABillDeductionCreate(RABillDeductionBase):
    pass

class RABillDeductionUpdate(RABillDeductionBase):
    pass

class RABillDeductionOut(RABillDeductionBase):
    id: uuid.UUID
    ra_bill_id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)

class RABillItemBase(BaseModel):
    boq_item_id: uuid.UUID
    current_quantity: Decimal = Field(..., ge=0, decimal_places=3)
    rate: Decimal = Field(..., ge=0, decimal_places=2)
    current_amount: Decimal = Field(..., ge=0, decimal_places=2)

class RABillItemOut(RABillItemBase):
    id: uuid.UUID
    ra_bill_id: uuid.UUID
    
    # Derived from logic/joins
    boq_item: BoqItemResponse
    previous_cumulative_quantity: Decimal = Field(..., decimal_places=3)
    cumulative_quantity: Decimal = Field(..., decimal_places=3)
    balance_quantity: Decimal = Field(..., decimal_places=3)
    cumulative_amount: Decimal = Field(..., decimal_places=2)
    percentage_executed: Decimal = Field(..., decimal_places=2)
    
    measurements: List[MeasurementOut] = []
    model_config = ConfigDict(from_attributes=True)

class RABillItemCreateMulti(BaseModel):
    measurement_ids: List[uuid.UUID]

class RABillBase(BaseModel):
    contract_id: uuid.UUID
    bill_number: str = Field(..., max_length=100)
    bill_date: date
    period_from: date
    period_to: date
    remarks: Optional[str] = None

    @field_validator("period_to")
    def validate_periods(cls, v, info):
        if "period_from" in info.data and v < info.data["period_from"]:
            raise ValueError("period_to must be after period_from")
        return v

class RABillCreate(RABillBase):
    pass

class RABillUpdate(BaseModel):
    bill_number: Optional[str] = Field(None, max_length=100)
    bill_date: Optional[date] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    remarks: Optional[str] = None

    @field_validator("period_to")
    def validate_periods(cls, v, info):
        if "period_from" in info.data and v < info.data["period_from"]:
            raise ValueError("period_to must be after period_from")
        return v

class RABillOut(RABillBase):
    id: uuid.UUID
    status: str
    gross_amount: Decimal
    deductions_amount: Decimal
    net_payable: Decimal
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class RABillDetailOut(RABillOut):
    items: List[RABillItemOut] = []
    deductions: List[RABillDeductionOut] = []
    model_config = ConfigDict(from_attributes=True)
