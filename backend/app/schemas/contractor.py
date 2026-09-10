import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContractorCreate(BaseModel):
    registration_number: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=255)
    status: str = Field(default="Active", pattern="^(Active|Suspended|Inactive)$")


class ContractorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    status: str | None = Field(default=None, pattern="^(Active|Suspended|Inactive)$")


class ContractorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registration_number: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime
