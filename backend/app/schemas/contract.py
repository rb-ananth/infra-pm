import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractCreate(BaseModel):
    contract_number: str = Field(min_length=2, max_length=100)
    project_id: uuid.UUID
    contractor_id: uuid.UUID
    contract_type: str = Field(default="Works", min_length=2, max_length=50)
    award_date: date
    # Monetary values are always expressed in INR at the API boundary.
    contract_value: Decimal = Field(ge=0, description="Contract value in INR")
    start_date: date
    original_completion_date: date
    current_completion_date: date
    status: str = Field(
        default="Draft",
        pattern="^(Draft|Active|Suspended|Completed|Terminated)$",
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.original_completion_date < self.start_date:
            raise ValueError(
                "Original completion date cannot be before start date."
            )

        if self.current_completion_date < self.start_date:
            raise ValueError(
                "Current completion date cannot be before start date."
            )

        if self.award_date > self.start_date:
            raise ValueError(
                "Award date cannot be after contract start date."
            )

        return self


class ContractUpdate(BaseModel):
    contractor_id: uuid.UUID | None = None
    contract_type: str | None = Field(
        default=None,
        min_length=2,
        max_length=50,
    )
    award_date: date | None = None
    contract_value: Decimal | None = Field(
        default=None,
        ge=0,
        description="Contract value in INR",
    )
    start_date: date | None = None
    original_completion_date: date | None = None
    current_completion_date: date | None = None
    status: str | None = Field(
        default=None,
        pattern="^(Draft|Active|Suspended|Completed|Terminated)$",
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.start_date
            and self.original_completion_date
            and self.original_completion_date < self.start_date
        ):
            raise ValueError(
                "Original completion date cannot be before start date."
            )

        if (
            self.start_date
            and self.current_completion_date
            and self.current_completion_date < self.start_date
        ):
            raise ValueError(
                "Current completion date cannot be before start date."
            )

        if self.start_date and self.award_date:
            if self.award_date > self.start_date:
                raise ValueError(
                    "Award date cannot be after contract start date."
                )

        return self


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contract_number: str
    project_id: uuid.UUID
    contractor_id: uuid.UUID
    contract_type: str
    award_date: date
    contract_value: Decimal
    start_date: date
    original_completion_date: date
    current_completion_date: date
    status: str
    created_at: datetime
    updated_at: datetime
