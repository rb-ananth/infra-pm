import uuid
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException

from app.models.contract import Contract
from app.models.eot import EOTApplication
from app.schemas.eot import EOTApplicationCreate, EOTApplicationUpdate, EOTApplicationDecision
from app.services.audit_service import add_audit_log

class EOTService:
    @staticmethod
    def get_application(db: Session, application_id: uuid.UUID) -> EOTApplication:
        app = db.query(EOTApplication).filter(EOTApplication.id == application_id).first()
        if not app:
            raise HTTPException(status_code=404, detail="EOT Application not found")
        return app

    @staticmethod
    def create_application(db: Session, payload: EOTApplicationCreate, user_id: uuid.UUID) -> EOTApplication:
        existing = db.query(EOTApplication).filter(
            EOTApplication.contract_id == payload.contract_id,
            EOTApplication.application_number == payload.application_number
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Application number already exists for this contract")

        app = EOTApplication(
            **payload.model_dump(),
            status="Draft",
            created_by=user_id
        )
        db.add(app)
        db.flush()
        add_audit_log(db, user_id, "EOTApplication", app.id, "CREATE", payload.model_dump(mode="json"))
        db.commit()
        db.refresh(app)
        return app

    @staticmethod
    def update_application(db: Session, application_id: uuid.UUID, payload: EOTApplicationUpdate, user_id: uuid.UUID) -> EOTApplication:
        app = EOTService.get_application(db, application_id)
        if app.status != "Draft":
            raise HTTPException(status_code=422, detail="Only Draft applications can be edited")

        if app.created_by != user_id:
            raise HTTPException(status_code=403, detail="Only the creator can edit this application")

        changes = payload.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(app, key, value)

        db.flush()
        add_audit_log(db, user_id, "EOTApplication", app.id, "UPDATE", changes)
        db.commit()
        db.refresh(app)
        return app

    @staticmethod
    def submit_application(db: Session, application_id: uuid.UUID, user_id: uuid.UUID) -> EOTApplication:
        app = EOTService.get_application(db, application_id)
        if app.status != "Draft":
            raise HTTPException(status_code=422, detail="Only Draft applications can be submitted")

        if app.created_by != user_id:
            raise HTTPException(status_code=403, detail="Only the creator can submit this application")

        app.status = "Submitted"
        app.submission_date = date.today()
        db.flush()
        add_audit_log(db, user_id, "EOTApplication", app.id, "SUBMIT", {"status": "Submitted"})
        db.commit()
        db.refresh(app)
        return app

    @staticmethod
    def review_application(db: Session, application_id: uuid.UUID, user_id: uuid.UUID) -> EOTApplication:
        app = EOTService.get_application(db, application_id)
        if app.status != "Submitted":
            raise HTTPException(status_code=422, detail="Only Submitted applications can be moved to Under Review")

        app.status = "Under Review"
        db.flush()
        add_audit_log(db, user_id, "EOTApplication", app.id, "REVIEW", {"status": "Under Review"})
        db.commit()
        db.refresh(app)
        return app

    @staticmethod
    def approve_application(db: Session, application_id: uuid.UUID, payload: EOTApplicationDecision, user_id: uuid.UUID) -> EOTApplication:
        with db.begin_nested():
                app = db.execute(
                    select(EOTApplication).where(EOTApplication.id == application_id).with_for_update()
                ).scalar_one_or_none()

                if not app:
                    raise HTTPException(status_code=404, detail="EOT Application not found")

                if app.status != "Under Review":
                    raise HTTPException(status_code=422, detail="Only applications Under Review can be approved")

                if app.created_by == user_id:
                    raise HTTPException(status_code=403, detail="Cannot approve your own application")

                if payload.approved_days is None or payload.approved_days < 0:
                    raise HTTPException(status_code=422, detail="Approved days must be provided and non-negative")

                contract = db.execute(
                    select(Contract).where(Contract.id == app.contract_id).with_for_update()
                ).scalar_one()

                app.status = "Approved"
                app.approved_days = payload.approved_days
                app.decision_reason = payload.decision_reason
                app.decision_maker_id = user_id
                app.decision_date = datetime.utcnow()

                app.previous_completion_date = contract.current_completion_date
                app.revised_completion_date = contract.current_completion_date + timedelta(days=payload.approved_days)

                contract.current_completion_date = app.revised_completion_date

                db.flush()
                add_audit_log(db, user_id, "EOTApplication", app.id, "APPROVE", {
                    "status": "Approved",
                    "approved_days": app.approved_days,
                    "previous_completion_date": str(app.previous_completion_date),
                    "revised_completion_date": str(app.revised_completion_date)
                })

        # Commit the outer transaction
        db.commit()
        db.refresh(app)
        return app

    @staticmethod
    def reject_application(db: Session, application_id: uuid.UUID, payload: EOTApplicationDecision, user_id: uuid.UUID) -> EOTApplication:
        app = EOTService.get_application(db, application_id)

        if app.status != "Under Review":
            raise HTTPException(status_code=422, detail="Only applications Under Review can be rejected")

        if app.created_by == user_id:
            raise HTTPException(status_code=403, detail="Cannot reject your own application")

        if not payload.decision_reason:
            raise HTTPException(status_code=422, detail="Rejection requires a reason")

        app.status = "Rejected"
        app.decision_reason = payload.decision_reason
        app.decision_maker_id = user_id
        app.decision_date = datetime.utcnow()

        db.flush()
        add_audit_log(db, user_id, "EOTApplication", app.id, "REJECT", {"status": "Rejected", "reason": payload.decision_reason})
        db.commit()
        db.refresh(app)
        return app
