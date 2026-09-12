import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class RABill(Base):
    __tablename__ = "ra_bills"
    __table_args__ = (
        UniqueConstraint("contract_id", "bill_number", name="uq_ra_bills_contract_bill_number"),
        CheckConstraint("period_from <= period_to", name="ck_ra_bills_period"),
        CheckConstraint("gross_amount >= 0", name="ck_ra_bills_gross_nonnegative"),
        CheckConstraint("deductions_amount >= 0", name="ck_ra_bills_deductions_nonnegative"),
        CheckConstraint("net_payable >= 0", name="ck_ra_bills_net_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False, index=True)
    bill_number: Mapped[str] = mapped_column(String(100), nullable=False)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Draft", index=True)
    
    # These are strictly server-controlled, recalculated inside locked transactions
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    deductions_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    net_payable: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0.00"))
    
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    contract = relationship("Contract")
    creator = relationship("User")
    items = relationship("RABillItem", back_populates="ra_bill", cascade="all, delete-orphan")
    deductions = relationship("RABillDeduction", back_populates="ra_bill", cascade="all, delete-orphan")

class RABillItem(Base):
    __tablename__ = "ra_bill_items"
    __table_args__ = (
        UniqueConstraint("ra_bill_id", "boq_item_id", name="uq_ra_bill_items_bill_boq"),
        CheckConstraint("current_quantity >= 0", name="ck_ra_bill_items_qty_nonnegative"),
        CheckConstraint("rate >= 0", name="ck_ra_bill_items_rate_nonnegative"),
        CheckConstraint("current_amount >= 0", name="ck_ra_bill_items_amt_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ra_bill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ra_bills.id", ondelete="CASCADE"), nullable=False, index=True)
    boq_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("boq_items.id"), nullable=False, index=True)
    
    # Server derived
    current_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)

    ra_bill = relationship("RABill", back_populates="items")
    boq_item = relationship("BoqItem")
    measurements = relationship("RABillMeasurement", back_populates="ra_bill_item", cascade="all, delete-orphan")

class RABillMeasurement(Base):
    __tablename__ = "ra_bill_measurements"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ra_bill_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ra_bill_items.id", ondelete="CASCADE"), nullable=False, index=True)
    # The crucial backstop against double-billing
    measurement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("measurements.id"), nullable=False, unique=True)
    
    ra_bill_item = relationship("RABillItem", back_populates="measurements")
    measurement = relationship("Measurement")

class RABillDeduction(Base):
    __tablename__ = "ra_bill_deductions"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_ra_bill_deductions_amt_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ra_bill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ra_bills.id", ondelete="CASCADE"), nullable=False, index=True)
    deduction_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)

    ra_bill = relationship("RABill", back_populates="deductions")
