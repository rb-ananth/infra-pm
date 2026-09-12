import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class BoqImportError(BaseModel):
    row: int | None = None
    field: str | None = None
    message: str


class BoqImportItemPreview(BaseModel):
    item_code: str
    item_number: str
    description: str
    unit: str
    quantity: Decimal
    rate: Decimal = Field(description="Rate in INR")
    amount: Decimal = Field(description="Calculated amount in INR")


class BoqImportPreviewResponse(BaseModel):
    valid: bool
    total_rows: int
    valid_rows: int
    invalid_rows: int
    warnings: list[str]
    ignored_columns: list[str]
    errors: list[BoqImportError]
    items: list[BoqImportItemPreview]


class BoqImportResponse(BaseModel):
    revision_id: uuid.UUID
    imported_count: int
    created_item_ids: list[uuid.UUID]
    total: Decimal = Field(description="Derived revision total in INR")