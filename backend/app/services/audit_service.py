import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def add_audit_log(
    db: Session,
    user_id: uuid.UUID | None,
    entity_name: str,
    entity_id: uuid.UUID,
    action: str,
    changes: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            entity_name=entity_name,
            entity_id=entity_id,
            action=action,
            changes=changes,
        )
    )
