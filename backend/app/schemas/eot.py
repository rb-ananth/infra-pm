import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class EOTApplicationBase(BaseModel):
    application_number: str = Field(..., max_length=100)
    event_date: date
    notice_date: date
    cause_of_delay: str = Field(..., min_length=1)
    claimed_days: int = Field(..., ge=0)

class EOTApplicationCreate(EOTApplicationBase):
    contract_id: uuid.UUID

class EOTApplicationUpdate(BaseModel):
    event_date: Optional[date] = None
    notice_date: Optional[date] = None
    cause_of_delay: Optional[str] = None
    claimed_days: Optional[int] = Field(None, ge=0)

class EOTApplicationDecision(BaseModel):
    approved_days: Optional[int] = Field(None, ge=0)
    decision_reason: str = Field(..., min_length=1)

class EOTApplicationOut(EOTApplicationBase):
    id: uuid.UUID
    contract_id: uuid.UUID
    status: str
    submission_date: Optional[date]
    approved_days: Optional[int]
    decision_maker_id: Optional[uuid.UUID]
    decision_date: Optional[datetime]
    decision_reason: Optional[str]
    previous_completion_date: Optional[date]
    revised_completion_date: Optional[date]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
