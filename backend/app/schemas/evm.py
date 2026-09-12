import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EVMBaselinePeriodBase(BaseModel):
    period_date: date
    planned_percentage: Decimal = Field(..., ge=0, le=100, decimal_places=4)


class EVMBaselinePeriodCreate(EVMBaselinePeriodBase):
    pass


class EVMBaselinePeriodUpdate(BaseModel):
    period_date: Optional[date] = None
    planned_percentage: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=4)


class EVMBaselinePeriodOut(EVMBaselinePeriodBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    baseline_id: uuid.UUID
    planned_value: Decimal = Field(..., decimal_places=2)
    created_at: datetime
    updated_at: datetime


class EVMBaselineBase(BaseModel):
    baseline_number: str
    name: str
    effective_date: date
    remarks: Optional[str] = None


class EVMBaselineCreate(EVMBaselineBase):
    pass


class EVMBaselineUpdate(BaseModel):
    baseline_number: Optional[str] = None
    name: Optional[str] = None
    effective_date: Optional[date] = None
    remarks: Optional[str] = None


class EVMBaselineOut(EVMBaselineBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    periods: List[EVMBaselinePeriodOut] = []


class EVMResponse(BaseModel):
    project_id: uuid.UUID
    as_of_date: date
    pv: Decimal = Field(..., decimal_places=2)
    ev: Decimal = Field(..., decimal_places=2)
    ac: Decimal = Field(..., decimal_places=2)
    sv: Decimal = Field(..., decimal_places=2)
    cv: Decimal = Field(..., decimal_places=2)
    spi: Optional[Decimal] = Field(None, decimal_places=4)
    cpi: Optional[Decimal] = Field(None, decimal_places=4)
    planned_percentage: Decimal = Field(..., decimal_places=4)
    actual_percentage: Decimal = Field(..., decimal_places=4)
    schedule_status: str
    cost_status: str


class EVMTrendPoint(BaseModel):
    date: date
    pv: Decimal = Field(..., decimal_places=2)
    ev: Decimal = Field(..., decimal_places=2)
    ac: Decimal = Field(..., decimal_places=2)
    sv: Decimal = Field(..., decimal_places=2)
    cv: Decimal = Field(..., decimal_places=2)
    spi: Optional[Decimal] = Field(None, decimal_places=4)
    cpi: Optional[Decimal] = Field(None, decimal_places=4)
