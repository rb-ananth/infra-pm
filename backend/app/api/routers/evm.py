import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.evm import (
    EVMBaselineCreate,
    EVMBaselineUpdate,
    EVMBaselineOut,
    EVMBaselinePeriodCreate,
    EVMBaselinePeriodUpdate,
    EVMBaselinePeriodOut,
    EVMResponse,
    EVMTrendPoint,
)
from app.services.evm_service import EVMService
from app.api.deps import require_roles

router = APIRouter(tags=["evm"])

require_edit = require_roles("Admin", "Project Manager")

# Since these routes attach to multiple prefixes, we define them individually
# GET /api/v1/projects/{project_id}/evm
@router.get("/projects/{project_id}/evm", response_model=EVMResponse)
def get_evm(
    project_id: uuid.UUID,
    as_of_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EVMService.get_evm(db, project_id, as_of_date)

@router.get("/projects/{project_id}/evm/trend", response_model=List[EVMTrendPoint])
def get_evm_trend(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EVMService.get_evm_trend(db, project_id)

@router.post("/projects/{project_id}/evm/baselines", response_model=EVMBaselineOut, dependencies=[Depends(require_edit)])
def create_baseline(
    project_id: uuid.UUID,
    payload: EVMBaselineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EVMService.create_baseline(db, project_id, payload, current_user.id)

@router.get("/projects/{project_id}/evm/baselines", response_model=List[EVMBaselineOut])
def list_baselines(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.evm import EVMBaseline
    from sqlalchemy import select
    return db.execute(select(EVMBaseline).where(EVMBaseline.project_id == project_id)).scalars().all()

@router.get("/evm-baselines/{baseline_id}", response_model=EVMBaselineOut)
def get_baseline(
    baseline_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EVMService.get_baseline(db, baseline_id)

@router.put("/evm-baselines/{baseline_id}", response_model=EVMBaselineOut, dependencies=[Depends(require_edit)])
def update_baseline(
    baseline_id: uuid.UUID,
    payload: EVMBaselineUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EVMService.update_baseline(db, baseline_id, payload, current_user.id)

@router.post("/evm-baselines/{baseline_id}/approve", response_model=EVMBaselineOut, dependencies=[Depends(require_edit)])
def approve_baseline(
    baseline_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EVMService.approve_baseline(db, baseline_id, current_user.id)

@router.post("/evm-baselines/{baseline_id}/supersede", response_model=EVMBaselineOut, dependencies=[Depends(require_edit)])
def supersede_baseline(
    baseline_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EVMService.supersede_baseline(db, baseline_id, current_user.id)

@router.get("/evm-baselines/{baseline_id}/periods", response_model=List[EVMBaselinePeriodOut])
def get_baseline_periods(
    baseline_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.evm import EVMBaselinePeriod
    from sqlalchemy import select
    return db.execute(select(EVMBaselinePeriod).where(EVMBaselinePeriod.baseline_id == baseline_id).order_by(EVMBaselinePeriod.period_date)).scalars().all()

@router.post("/evm-baselines/{baseline_id}/periods", response_model=EVMBaselinePeriodOut, dependencies=[Depends(require_edit)])
def add_baseline_period(
    baseline_id: uuid.UUID,
    payload: EVMBaselinePeriodCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EVMService.add_period(db, baseline_id, payload, current_user.id)

@router.put("/evm-baseline-periods/{period_id}", response_model=EVMBaselinePeriodOut, dependencies=[Depends(require_edit)])
def update_baseline_period(
    period_id: uuid.UUID,
    payload: EVMBaselinePeriodUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return EVMService.update_period(db, period_id, payload, current_user.id)

