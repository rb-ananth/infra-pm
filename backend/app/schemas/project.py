import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=3, max_length=255)
    dept_id: uuid.UUID
    pm_id: uuid.UUID
    status: str = Field(default="Proposed", pattern="^(Proposed|Execution|Closed|Suspended)$")
    total_estimated_cost: Decimal = Field(ge=0)
    start_date: date
    expected_completion: date

    @model_validator(mode="after")
    def validate_dates(self):
        if self.expected_completion < self.start_date:
            raise ValueError("Expected completion date cannot be before start date.")
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    dept_id: uuid.UUID | None = None
    pm_id: uuid.UUID | None = None
    status: str | None = Field(default=None, pattern="^(Proposed|Execution|Closed|Suspended)$")
    total_estimated_cost: Decimal | None = Field(default=None, ge=0)
    start_date: date | None = None
    expected_completion: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.expected_completion and self.expected_completion < self.start_date:
            raise ValueError("Expected completion date cannot be before start date.")
        return self


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    dept_id: uuid.UUID
    pm_id: uuid.UUID
    status: str
    total_estimated_cost: Decimal
    start_date: date
    expected_completion: date
    created_at: datetime
    updated_at: datetime
