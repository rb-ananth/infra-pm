import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.boq import BoqItemResponse, _trim_required, _validate_decimal_places

MEASUREMENT_STATUSES = "^(Draft|Submitted|Approved|Rejected)$"


class MeasurementCreate(BaseModel):
    boq_item_id: uuid.UUID
    measurement_date: date
    quantity: Decimal = Field(ge=0)
    reference: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    remarks: str | None = None

    _trim_reference = field_validator("reference", mode="before")(_trim_required)
    _trim_description = field_validator("description", mode="before")(_trim_required)
    _trim_remarks = field_validator("remarks", mode="before")(_trim_required)

    @field_validator("quantity")
    @classmethod
    def validate_quantity_precision(cls, value: Decimal) -> Decimal:
        return _validate_decimal_places(value, 3, "Quantity")


class MeasurementUpdate(BaseModel):
    measurement_date: date | None = None
    quantity: Decimal | None = Field(default=None, ge=0)
    reference: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    remarks: str | None = None

    _trim_reference = field_validator("reference", mode="before")(_trim_required)
    _trim_description = field_validator("description", mode="before")(_trim_required)
    _trim_remarks = field_validator("remarks", mode="before")(_trim_required)

    @field_validator("quantity")
    @classmethod
    def validate_quantity_precision(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return _validate_decimal_places(value, 3, "Quantity")


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    boq_item_id: uuid.UUID
    measurement_date: date
    quantity: Decimal
    reference: str
    description: str
    remarks: str | None
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class MeasurementDetail(BaseModel):
    measurement: MeasurementOut
    boq_item: BoqItemResponse
    cumulative_approved_quantity: Decimal
    balance_quantity: Decimal
    percentage_executed: Decimal
    is_overrun: bool
    overrun_quantity: Decimal | None
