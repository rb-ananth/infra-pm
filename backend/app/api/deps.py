import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.role import Role
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        subject = payload.get("sub")
        if not subject:
            raise credentials_exception
        user_id = uuid.UUID(subject)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*allowed_roles: str) -> Callable:
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.name not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return current_user

    return role_checker

class AdminBypass:
    pass

ADMIN_BYPASS = AdminBypass()

def get_allowed_project_ids(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> list[uuid.UUID] | AdminBypass:
    if current_user.role.name == "Admin":
        return ADMIN_BYPASS
    
    from app.models.user import UserProjectAssignment
    assignments = db.query(UserProjectAssignment).filter(
        UserProjectAssignment.user_id == current_user.id
    ).all()
    return [a.project_id for a in assignments]

def verify_project_access(project_id: uuid.UUID, allowed_projects: list[uuid.UUID] | AdminBypass) -> bool:
    if allowed_projects is ADMIN_BYPASS:
        return True
    if project_id not in allowed_projects:
        raise HTTPException(status_code=403, detail="Access denied to this project.")
    return True

def resolve_measurement_project(db: Session, measurement_id: uuid.UUID) -> uuid.UUID:
    from app.models.measurement import Measurement
    from app.models.boq_item import BoqItem
    from app.models.boq import Boq
    from app.models.contract import Contract
    from fastapi import HTTPException
    
    contract = (
        db.query(Contract)
        .join(Boq, Boq.contract_id == Contract.id)
        .join(BoqItem, BoqItem.boq_id == Boq.id)
        .join(Measurement, Measurement.boq_item_id == BoqItem.id)
        .filter(Measurement.id == measurement_id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return contract.project_id

def resolve_boq_item_project(db: Session, boq_item_id: uuid.UUID) -> uuid.UUID:
    from app.models.boq_item import BoqItem
    from app.models.boq import Boq
    from app.models.contract import Contract
    from fastapi import HTTPException
    
    contract = (
        db.query(Contract)
        .join(Boq, Boq.contract_id == Contract.id)
        .join(BoqItem, BoqItem.boq_id == Boq.id)
        .filter(BoqItem.id == boq_item_id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=404, detail="BOQ Item not found")
    return contract.project_id

def resolve_ra_bill_project(db: Session, bill_id: uuid.UUID) -> uuid.UUID:
    from app.models.ra_bill import RABill
    from app.models.contract import Contract
    from fastapi import HTTPException
    
    contract = (
        db.query(Contract)
        .join(RABill, RABill.contract_id == Contract.id)
        .filter(RABill.id == bill_id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=404, detail="RA Bill not found")
    return contract.project_id

def resolve_contract_project(db: Session, contract_id: uuid.UUID) -> uuid.UUID:
    from app.models.contract import Contract
    from fastapi import HTTPException
    
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract.project_id

def resolve_evm_baseline_project(db: Session, baseline_id: uuid.UUID) -> uuid.UUID:
    from app.models.evm import EVMBaseline
    from fastapi import HTTPException
    
    baseline = db.query(EVMBaseline).filter(EVMBaseline.id == baseline_id).first()
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return baseline.project_id

def resolve_boq_project(db: Session, boq_id: uuid.UUID) -> uuid.UUID:
    from app.models.boq import Boq
    from app.models.contract import Contract
    from fastapi import HTTPException
    
    contract = (
        db.query(Contract)
        .join(Boq, Boq.contract_id == Contract.id)
        .filter(Boq.id == boq_id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=404, detail="BOQ not found")
    return contract.project_id

def resolve_boq_revision_project(db: Session, revision_id: uuid.UUID) -> uuid.UUID:
    from app.models.boq_revision import BoqRevision
    from app.models.boq import Boq
    from app.models.contract import Contract
    from fastapi import HTTPException
    
    contract = (
        db.query(Contract)
        .join(Boq, Boq.contract_id == Contract.id)
        .join(BoqRevision, BoqRevision.boq_id == Boq.id)
        .filter(BoqRevision.id == revision_id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=404, detail="BOQ Revision not found")
    return contract.project_id

def resolve_evm_period_project(db: Session, period_id: uuid.UUID) -> uuid.UUID:
    from app.models.evm import EVMBaselinePeriod, EVMBaseline
    from fastapi import HTTPException
    
    baseline = (
        db.query(EVMBaseline)
        .join(EVMBaselinePeriod, EVMBaselinePeriod.baseline_id == EVMBaseline.id)
        .filter(EVMBaselinePeriod.id == period_id)
        .first()
    )
    if not baseline:
        raise HTTPException(status_code=404, detail="EVM Period not found")
    return baseline.project_id
