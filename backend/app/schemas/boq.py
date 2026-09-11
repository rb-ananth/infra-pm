import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BOQ_STATUSES = "^(Draft|Submitted|Approved|Superseded)$"


def _trim_required(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("Value cannot be blank.")
    return trimmed


def _validate_decimal_places(value: Decimal, max_places: int, field_name: str) -> Decimal:
    if value.as_tuple().exponent < -max_places:
        raise ValueError(f"{field_name} cannot have more than {max_places} decimal places.")
    return value


class BoqCreate(BaseModel):
    contract_id: uuid.UUID
    boq_number: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: str = Field(default="Draft", pattern=BOQ_STATUSES)

    _trim_boq_number = field_validator("boq_number", mode="before")(_trim_required)
    _trim_title = field_validator("title", mode="before")(_trim_required)


class BoqUpdate(BaseModel):
    boq_number: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern=BOQ_STATUSES)

    _trim_boq_number = field_validator("boq_number", mode="before")(_trim_required)
    _trim_title = field_validator("title", mode="before")(_trim_required)
    _trim_description = field_validator("description", mode="before")(_trim_required)


class BoqResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contract_id: uuid.UUID
    boq_number: str
    title: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class BoqRevisionCreate(BaseModel):
    revision_number: int = Field(ge=1)
    revision_date: date
    remarks: str | None = None
    status: str = Field(default="Draft", pattern=BOQ_STATUSES)


class BoqRevisionUpdate(BaseModel):
    revision_date: date | None = None
    remarks: str | None = None
    status: str | None = Field(default=None, pattern=BOQ_STATUSES)

    _trim_remarks = field_validator("remarks", mode="before")(_trim_required)


class BoqRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    boq_id: uuid.UUID
    revision_number: int
    revision_date: date
    status: str
    remarks: str | None
    created_at: datetime
    updated_at: datetime


class BoqItemCreate(BaseModel):
    item_code: str = Field(min_length=1, max_length=100)
    item_number: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    unit: str = Field(min_length=1, max_length=50)
    quantity: Decimal = Field(ge=0)
    rate: Decimal = Field(ge=0, description="Rate in INR")

    _trim_item_code = field_validator("item_code", mode="before")(_trim_required)
    _trim_item_number = field_validator("item_number", mode="before")(_trim_required)
    _trim_description = field_validator("description", mode="before")(_trim_required)
    _trim_unit = field_validator("unit", mode="before")(_trim_required)

    @field_validator("quantity")
    @classmethod
    def validate_quantity_precision(cls, value: Decimal) -> Decimal:
        return _validate_decimal_places(value, 3, "Quantity")

    @field_validator("rate")
    @classmethod
    def validate_rate_precision(cls, value: Decimal) -> Decimal:
        return _validate_decimal_places(value, 2, "Rate")


class BoqItemUpdate(BaseModel):
    item_code: str | None = Field(default=None, min_length=1, max_length=100)
    item_number: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    quantity: Decimal | None = Field(default=None, ge=0)
    rate: Decimal | None = Field(default=None, ge=0, description="Rate in INR")

    _trim_item_code = field_validator("item_code", mode="before")(_trim_required)
    _trim_item_number = field_validator("item_number", mode="before")(_trim_required)
    _trim_description = field_validator("description", mode="before")(_trim_required)
    _trim_unit = field_validator("unit", mode="before")(_trim_required)

    @field_validator("quantity")
    @classmethod
    def validate_quantity_precision(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return _validate_decimal_places(value, 3, "Quantity")

    @field_validator("rate")
    @classmethod
    def validate_rate_precision(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return _validate_decimal_places(value, 2, "Rate")


class BoqItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    revision_id: uuid.UUID
    item_code: str
    item_number: str
    description: str
    unit: str
    quantity: Decimal
    rate: Decimal
    amount: Decimal
    created_at: datetime
    updated_at: datetime


class BoqRevisionDetailResponse(BaseModel):
    boq: BoqResponse
    revision: BoqRevisionResponse
    items: list[BoqItemResponse]
    total: Decimal