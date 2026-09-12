import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text, Index, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class EVMBaseline(Base):
    __tablename__ = "evm_baselines"
    __table_args__ = (
        UniqueConstraint("project_id", "baseline_number", name="uq_evm_baselines_project_number"),
        Index("ix_evm_baselines_single_approved", "project_id", postgresql_where=text("status = 'Approved'"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    baseline_number: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Draft", index=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project")
    creator = relationship("User")
    periods = relationship("EVMBaselinePeriod", back_populates="baseline", cascade="all, delete-orphan", order_by="EVMBaselinePeriod.period_date")


class EVMBaselinePeriod(Base):
    __tablename__ = "evm_baseline_periods"
    __table_args__ = (
        UniqueConstraint("baseline_id", "period_date", name="uq_evm_baseline_periods_baseline_date"),
        CheckConstraint("planned_percentage >= 0 AND planned_percentage <= 100", name="ck_evm_baseline_periods_percentage"),
        CheckConstraint("planned_value >= 0", name="ck_evm_baseline_periods_value_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    baseline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evm_baselines.id", ondelete="CASCADE"), nullable=False, index=True)
    period_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    planned_percentage: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    planned_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    baseline = relationship("EVMBaseline", back_populates="periods")
