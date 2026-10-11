import uuid
from datetime import date, datetime
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class EOTApplication(Base):
    __tablename__ = "eot_applications"
    __table_args__ = (
        UniqueConstraint("contract_id", "application_number", name="uq_eot_contract_app_number"),
        CheckConstraint("claimed_days >= 0", name="ck_eot_claimed_days_nonnegative"),
        CheckConstraint("approved_days IS NULL OR approved_days >= 0", name="ck_eot_approved_days_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    application_number: Mapped[str] = mapped_column(String(100), nullable=False)

    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    notice_date: Mapped[date] = mapped_column(Date, nullable=False)
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    cause_of_delay: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_days: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Draft", index=True)

    decision_maker_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decision_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revised_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    contract = relationship("Contract")
    creator = relationship("User", foreign_keys=[created_by])
    decision_maker = relationship("User", foreign_keys=[decision_maker_id])
