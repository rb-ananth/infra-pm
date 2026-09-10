import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    entity_name: str
    entity_id: uuid.UUID
    action: str
    changes: dict[str, Any]
    timestamp: datetime
