import uuid
from datetime import date
from decimal import Decimal
from typing import List

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.evm import EVMBaseline, EVMBaselinePeriod
from app.models.project import Project
from app.models.contract import Contract
from app.models.boq import Boq
from app.models.boq_revision import BoqRevision
from app.models.boq_item import BoqItem
from app.models.measurement import Measurement
from app.models.ra_bill import RABill, RABillItem
from app.schemas.evm import (
    EVMBaselineCreate,
    EVMBaselineUpdate,
    EVMBaselinePeriodCreate,
    EVMBaselinePeriodUpdate,
    EVMResponse,
    EVMTrendPoint,
)
from app.services.audit_service import add_audit_log


class EVMService:
    @staticmethod
    def create_baseline(db: Session, project_id: uuid.UUID, payload: EVMBaselineCreate, user_id: uuid.UUID) -> EVMBaseline:
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        existing = db.execute(
            select(EVMBaseline).where(EVMBaseline.project_id == project_id, EVMBaseline.baseline_number == payload.baseline_number)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Baseline number must be unique within project")

        baseline = EVMBaseline(
            project_id=project_id,
            baseline_number=payload.baseline_number,
            name=payload.name,
            effective_date=payload.effective_date,
            remarks=payload.remarks,
            created_by=user_id,
            status="Draft",
        )
        db.add(baseline)
        db.flush()

        add_audit_log(
            db, user_id, "EVMBaseline", baseline.id, "EVM_BASELINE_CREATE",
            {"baseline_number": baseline.baseline_number}
        )
        db.commit()
        db.refresh(baseline)
        return baseline

    @staticmethod
    def get_baseline(db: Session, baseline_id: uuid.UUID) -> EVMBaseline:
        baseline = db.execute(select(EVMBaseline).where(EVMBaseline.id == baseline_id)).scalar_one_or_none()
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")
        return baseline

    @staticmethod
    def update_baseline(db: Session, baseline_id: uuid.UUID, payload: EVMBaselineUpdate, user_id: uuid.UUID) -> EVMBaseline:
        baseline = db.execute(select(EVMBaseline).where(EVMBaseline.id == baseline_id).with_for_update()).scalar_one_or_none()
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")
        if baseline.status != "Draft":
            raise HTTPException(status_code=403, detail="Only Draft baselines can be edited")

        if payload.baseline_number and payload.baseline_number != baseline.baseline_number:
            existing = db.execute(
                select(EVMBaseline).where(EVMBaseline.project_id == baseline.project_id, EVMBaseline.baseline_number == payload.baseline_number)
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(status_code=400, detail="Baseline number must be unique within project")

        changes = {}
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(baseline, k, v)
            changes[k] = str(v)
            
        if changes:
            add_audit_log(db, user_id, "EVMBaseline", baseline.id, "EVM_BASELINE_UPDATE", changes)
            
        db.commit()
        db.refresh(baseline)
        return baseline

    @staticmethod
    def approve_baseline(db: Session, baseline_id: uuid.UUID, user_id: uuid.UUID) -> EVMBaseline:
        baseline = db.execute(select(EVMBaseline).where(EVMBaseline.id == baseline_id).with_for_update()).scalar_one_or_none()
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")
        if baseline.status != "Draft":
            raise HTTPException(status_code=403, detail="Only Draft baselines can be approved")

        periods = sorted(baseline.periods, key=lambda p: p.period_date)
        if not periods or periods[-1].planned_percentage != Decimal("100.0000"):
            raise HTTPException(status_code=400, detail="Baseline must contain a final 100% period before it can be Approved")

        # Check for existing approved
        existing_approved = db.execute(
            select(EVMBaseline).where(EVMBaseline.project_id == baseline.project_id, EVMBaseline.status == "Approved")
        ).scalar_one_or_none()
        if existing_approved:
            raise HTTPException(status_code=400, detail="Only one Approved baseline may exist for a project")

        baseline.status = "Approved"
        add_audit_log(db, user_id, "EVMBaseline", baseline.id, "EVM_BASELINE_APPROVE", {"status": "Approved"})
        db.commit()
        db.refresh(baseline)
        return baseline

    @staticmethod
    def supersede_baseline(db: Session, baseline_id: uuid.UUID, user_id: uuid.UUID) -> EVMBaseline:
        baseline = db.execute(select(EVMBaseline).where(EVMBaseline.id == baseline_id).with_for_update()).scalar_one_or_none()
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")
        if baseline.status != "Approved":
            raise HTTPException(status_code=403, detail="Only Approved baselines can be superseded")

        baseline.status = "Superseded"
        add_audit_log(db, user_id, "EVMBaseline", baseline.id, "EVM_BASELINE_SUPERSEDE", {"status": "Superseded"})
        db.commit()
        db.refresh(baseline)
        return baseline

    @staticmethod
    def add_period(db: Session, baseline_id: uuid.UUID, payload: EVMBaselinePeriodCreate, user_id: uuid.UUID) -> EVMBaselinePeriod:
        baseline = db.execute(select(EVMBaseline).where(EVMBaseline.id == baseline_id).with_for_update()).scalar_one_or_none()
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")
        if baseline.status != "Draft":
            raise HTTPException(status_code=403, detail="Can only add periods to Draft baselines")

        project = db.execute(select(Project).where(Project.id == baseline.project_id)).scalar_one_or_none()
        
        # Check chronology and non-decreasing rules
        periods = sorted(baseline.periods, key=lambda p: p.period_date)
        
        # Non-decreasing logic relative to periods before and after
        for p in periods:
            if p.period_date == payload.period_date:
                raise HTTPException(status_code=400, detail="Period dates cannot duplicate")
            if p.period_date < payload.period_date and p.planned_percentage > payload.planned_percentage:
                raise HTTPException(status_code=400, detail="Planned percentages must be non-decreasing")
            if p.period_date > payload.period_date and p.planned_percentage < payload.planned_percentage:
                raise HTTPException(status_code=400, detail="Planned percentages must be non-decreasing")

        planned_value = (project.total_estimated_cost * payload.planned_percentage / Decimal("100")).quantize(Decimal("0.01"))
        
        period = EVMBaselinePeriod(
            baseline_id=baseline_id,
            period_date=payload.period_date,
            planned_percentage=payload.planned_percentage,
            planned_value=planned_value
        )
        db.add(period)
        db.flush()
        
        add_audit_log(
            db, user_id, "EVMBaselinePeriod", period.id, "EVM_BASELINE_PERIOD_ADD",
            {"period_date": str(period.period_date), "percentage": str(period.planned_percentage)}
        )
        db.commit()
        db.refresh(period)
        return period

    @staticmethod
    def update_period(db: Session, period_id: uuid.UUID, payload: EVMBaselinePeriodUpdate, user_id: uuid.UUID) -> EVMBaselinePeriod:
        period = db.execute(select(EVMBaselinePeriod).where(EVMBaselinePeriod.id == period_id).with_for_update()).scalar_one_or_none()
        if not period:
            raise HTTPException(status_code=404, detail="Period not found")
            
        baseline = db.execute(select(EVMBaseline).where(EVMBaseline.id == period.baseline_id)).scalar_one_or_none()
        if baseline.status != "Draft":
            raise HTTPException(status_code=403, detail="Can only update periods in Draft baselines")

        new_date = payload.period_date if payload.period_date else period.period_date
        new_pct = payload.planned_percentage if payload.planned_percentage is not None else period.planned_percentage

        periods = sorted(baseline.periods, key=lambda p: p.period_date)
        for p in periods:
            if p.id == period.id:
                continue
            if p.period_date == new_date:
                raise HTTPException(status_code=400, detail="Period dates cannot duplicate")
            if p.period_date < new_date and p.planned_percentage > new_pct:
                raise HTTPException(status_code=400, detail="Planned percentages must be non-decreasing")
            if p.period_date > new_date and p.planned_percentage < new_pct:
                raise HTTPException(status_code=400, detail="Planned percentages must be non-decreasing")
                
        project = db.execute(select(Project).where(Project.id == baseline.project_id)).scalar_one_or_none()

        period.period_date = new_date
        period.planned_percentage = new_pct
        period.planned_value = (project.total_estimated_cost * new_pct / Decimal("100")).quantize(Decimal("0.01"))
        
        db.flush()
        add_audit_log(
            db, user_id, "EVMBaselinePeriod", period.id, "EVM_BASELINE_PERIOD_UPDATE",
            {"period_date": str(new_date), "percentage": str(new_pct)}
        )
        db.commit()
        db.refresh(period)
        return period

    @staticmethod
    def get_evm(db: Session, project_id: uuid.UUID, as_of_date: date) -> EVMResponse:
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        baseline = db.execute(
            select(EVMBaseline).where(EVMBaseline.project_id == project_id, EVMBaseline.status == "Approved")
        ).scalar_one_or_none()

        pv = Decimal("0.00")
        planned_percentage = Decimal("0.0000")
        if baseline and baseline.periods:
            periods = sorted(baseline.periods, key=lambda p: p.period_date)
            if as_of_date < periods[0].period_date:
                pv = Decimal("0.00")
                planned_percentage = Decimal("0.0000")
            elif as_of_date >= periods[-1].period_date:
                pv = periods[-1].planned_value
                planned_percentage = periods[-1].planned_percentage
            else:
                for i in range(len(periods) - 1):
                    p1, p2 = periods[i], periods[i+1]
                    if p1.period_date <= as_of_date <= p2.period_date:
                        if p1.period_date == as_of_date:
                            pv = p1.planned_value
                            planned_percentage = p1.planned_percentage
                        elif p2.period_date == as_of_date:
                            pv = p2.planned_value
                            planned_percentage = p2.planned_percentage
                        else:
                            days_total = Decimal((p2.period_date - p1.period_date).days)
                            days_elapsed = Decimal((as_of_date - p1.period_date).days)
                            ratio = days_elapsed / days_total
                            pv = p1.planned_value + (p2.planned_value - p1.planned_value) * ratio
                            planned_percentage = p1.planned_percentage + (p2.planned_percentage - p1.planned_percentage) * ratio
                        break
        pv = pv.quantize(Decimal("0.01"))
        planned_percentage = planned_percentage.quantize(Decimal("0.0000"))

        ev = db.execute(
            select(func.sum(Measurement.quantity * BoqItem.rate))
            .select_from(Measurement)
            .join(BoqItem, Measurement.boq_item_id == BoqItem.id)
            .join(BoqRevision, BoqItem.revision_id == BoqRevision.id)
            .join(Boq, BoqRevision.boq_id == Boq.id)
            .join(Contract, Boq.contract_id == Contract.id)
            .where(
                Contract.project_id == project_id,
                Measurement.status == "Approved",
                Measurement.measurement_date <= as_of_date
            )
        ).scalar() or Decimal("0.00")
        ev = ev.quantize(Decimal("0.01"))
        
        ac = db.execute(
            select(func.sum(RABillItem.current_amount))
            .select_from(RABillItem)
            .join(RABill, RABillItem.ra_bill_id == RABill.id)
            .join(Contract, RABill.contract_id == Contract.id)
            .where(
                Contract.project_id == project_id,
                RABill.status == "Approved",
                RABill.bill_date <= as_of_date
            )
        ).scalar() or Decimal("0.00")
        ac = ac.quantize(Decimal("0.01"))

        sv = ev - pv
        cv = ev - ac
        
        spi = ev / pv if pv > 0 else None
        if spi is not None:
            spi = spi.quantize(Decimal("0.0000"))
            
        cpi = ev / ac if ac > 0 else None
        if cpi is not None:
            cpi = cpi.quantize(Decimal("0.0000"))
            
        actual_percentage = Decimal("0.0000")
        if project.total_estimated_cost > 0:
            actual_percentage = (ev / project.total_estimated_cost * Decimal("100")).quantize(Decimal("0.0000"))
            
        schedule_status = "ON_SCHEDULE"
        if spi is not None:
            if spi < Decimal("1"): schedule_status = "BEHIND"
            elif spi > Decimal("1"): schedule_status = "AHEAD"
            
        cost_status = "ON_BUDGET"
        if cpi is not None:
            if cpi < Decimal("1"): cost_status = "INEFFICIENT"
            elif cpi > Decimal("1"): cost_status = "EFFICIENT"
            
        return EVMResponse(
            project_id=project_id,
            as_of_date=as_of_date,
            pv=pv,
            ev=ev,
            ac=ac,
            sv=sv,
            cv=cv,
            spi=spi,
            cpi=cpi,
            planned_percentage=planned_percentage,
            actual_percentage=actual_percentage,
            schedule_status=schedule_status,
            cost_status=cost_status
        )

    @staticmethod
    def get_evm_trend(db: Session, project_id: uuid.UUID) -> List[EVMTrendPoint]:
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        baseline = db.execute(
            select(EVMBaseline).where(EVMBaseline.project_id == project_id, EVMBaseline.status == "Approved")
        ).scalar_one_or_none()
        
        if not baseline or not baseline.periods:
            return []
            
        dates = sorted([p.period_date for p in baseline.periods])
        
        trend = []
        for d in dates:
            evm = EVMService.get_evm(db, project_id, d)
            trend.append(EVMTrendPoint(
                date=d,
                pv=evm.pv,
                ev=evm.ev,
                ac=evm.ac,
                sv=evm.sv,
                cv=evm.cv,
                spi=evm.spi,
                cpi=evm.cpi
            ))
            
        return trend
