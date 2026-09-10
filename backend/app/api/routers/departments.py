from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.department import Department
from app.models.user import User
from app.schemas.department import DepartmentCreate, DepartmentResponse
from app.services.audit_service import add_audit_log

router = APIRouter()


@router.get("/", response_model=list[DepartmentResponse])
def list_departments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Department).filter(Department.is_active.is_(True)).order_by(Department.name).all()


@router.post("/", response_model=DepartmentResponse)
def create_department(
    data: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin")),
):
    department = Department(**data.model_dump())
    db.add(department)
    try:
        db.flush()
        add_audit_log(db, current_user.id, "Department", department.id, "CREATE", data.model_dump(mode="json"))
        db.commit()
        db.refresh(department)
        return department
    except Exception:
        db.rollback()
        raise
