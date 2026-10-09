from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles, get_allowed_project_ids, ADMIN_BYPASS
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogResponse

router = APIRouter()

@router.get("/", response_model=list[AuditLogResponse])
def list_audit_logs(
    db: Session = Depends(get_db),
    # Still allow Viewer to attempt the request, but we will block them programmatically
    # if we cannot filter. This fulfills the "safest compatible behavior" requirement.
    current_user: User = Depends(require_roles("Admin", "Viewer")),
    allowed_projects = Depends(get_allowed_project_ids),
):
    if allowed_projects is not ADMIN_BYPASS:
        # SECURITY LIMITATION: The AuditLog schema currently relies on polymorphic
        # entity_name/entity_id pairs without a denormalized project_id.
        # Filtering logs in the database across 10+ relation chains for project isolation
        # is unreliable and unscalable.
        # Safest compatible behavior: Deny operational users access to global logs.
        raise HTTPException(
            status_code=403,
            detail="Project-scoped audit log access is not supported by the current schema. "
                   "Only Admin can access global audit logs."
        )
        
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(200).all()
