"""
Create the canonical InfraPM demonstration dataset.

This script is intentionally conservative:
- It uses the existing PWD demo project and contract.
- It never creates projects or contracts.
- It refuses to run if any part of the demo dataset already exists.
- It creates data through application services.
- It validates the final BOQ, measurements, RA Bills, and EVM baseline.
"""

import os
import sys
import traceback
from datetime import date
from decimal import Decimal

sys.path.append(os.path.abspath("backend"))

from app.core.database import SessionLocal
from app.models.user import User
from app.models.project import Project
from app.models.contract import Contract
from app.models.boq import Boq
from app.models.boq_revision import BoqRevision
from app.models.boq_item import BoqItem
from app.models.measurement import Measurement
from app.models.ra_bill import RABill, RABillMeasurement
from app.models.evm import EVMBaseline, EVMBaselinePeriod

from app.schemas.boq import BoqCreate, BoqRevisionCreate, BoqRevisionUpdate, BoqItemCreate
from app.schemas.measurement import MeasurementCreate
from app.schemas.ra_bill import RABillCreate
from app.schemas.evm import EVMBaselineCreate, EVMBaselinePeriodCreate

from app.services import boq_service
from app.services import measurement_service
from app.services.ra_bill_service import RABillService
from app.services.evm_service import EVMService


PROJECT_CODE = "PWD-2026-001"
CONTRACT_NUMBER = "CNT-PWD-2026-001"
BOQ_NUMBER = "BOQ-DEMO-001"
BASELINE_NUMBER = "BL-DEMO-001"

EXPECTED_CONTRACT_VALUE = Decimal("485000000.00")


ITEMS = [
    ("EW-01", "1.1", "Earthwork in excavation for foundation", "CUM", "50000", "450"),
    ("CC-01", "2.1", "Providing and laying PCC 1:4:8", "CUM", "10000", "4500"),
    ("RCC-01", "3.1", "RCC work in columns and footings (M25)", "CUM", "22000", "8500"),
    ("ST-01", "4.1", "Thermo-mechanically treated steel reinforcement", "MT", "2000", "65000"),
    ("BW-01", "5.1", "Brick work with common burnt clay F.P.S.", "CUM", "10000", "6200"),
    ("PL-01", "6.1", "12 mm cement plaster of mix 1:6", "SQM", "40680", "250"),
    ("FL-01", "7.1", "Vitrified floor tiles 600x600mm", "SQM", "8000", "1200"),
    ("PT-01", "8.1", "Wall painting with premium acrylic emulsion", "SQM", "30000", "150"),
    ("DR-01", "9.1", "Flush door shutters 35mm thick", "SQM", "500", "3500"),
    ("AL-01", "10.1", "Aluminum glazed windows", "SQM", "2600", "4800"),
]


MEASUREMENT_PLAN = [
    (4, [("EW-01", "21500")]),
    (5, [("EW-01", "28500"), ("CC-01", "1460")]),
    (6, [("CC-01", "3540"), ("RCC-01", "2110")]),
    (7, [("RCC-01", "3000"), ("ST-01", "355")]),
    (8, [("RCC-01", "3000"), ("ST-01", "427")]),
    (9, [("RCC-01", "2500"), ("ST-01", "500"), ("BW-01", "1500")]),
]


EVM_PERIODS = [
    (date(2026, 4, 30), "5.00"),
    (date(2026, 5, 31), "12.00"),
    (date(2026, 6, 30), "22.00"),
    (date(2026, 7, 31), "35.00"),
    (date(2026, 8, 31), "50.00"),
    (date(2026, 9, 30), "66.00"),
    (date(2026, 10, 31), "82.00"),
    (date(2026, 11, 30), "100.00"),
]


BILL_GROUPINGS = [
    (4, "RA-04", [4]),
    (6, "RA-06", [5, 6]),
    (9, "RA-09", [7, 8, 9]),
]


def fail(message: str) -> None:
    print(f"BLOCKER: {message}")
    raise SystemExit(1)


db = SessionLocal()

try:
    print("=== 1. VERIFYING EXISTING PROJECT / CONTRACT ===")

    admin = db.query(User).filter(
        User.email == "admin@infrapm.gov"
    ).first()

    if not admin:
        fail("Admin user admin@infrapm.gov does not exist.")

    project = db.query(Project).filter(
        Project.code == PROJECT_CODE
    ).first()

    if not project:
        fail(f"Project {PROJECT_CODE} does not exist.")

    contract = db.query(Contract).filter(
        Contract.project_id == project.id,
        Contract.contract_number == CONTRACT_NUMBER
    ).first()

    if not contract:
        fail(f"Contract {CONTRACT_NUMBER} does not exist for {PROJECT_CODE}.")

    if contract.contract_value != EXPECTED_CONTRACT_VALUE:
        fail(
            f"Expected contract value {EXPECTED_CONTRACT_VALUE}, "
            f"found {contract.contract_value}."
        )

    print(f"Project: {project.code} | {project.name}")
    print(f"Contract: {contract.contract_number}")
    print(f"Contract Value: ₹{contract.contract_value:,.2f}")


    print("\n=== 2. REFUSING PARTIAL / DUPLICATE DEMO STATE ===")

    existing_boq = db.query(Boq).filter(
        Boq.contract_id == contract.id,
        Boq.boq_number == BOQ_NUMBER
    ).first()

    existing_baseline = db.query(EVMBaseline).filter(
        EVMBaseline.project_id == project.id,
        EVMBaseline.baseline_number == BASELINE_NUMBER
    ).first()

    existing_measurements = (
        db.query(Measurement)
        .join(BoqItem, Measurement.boq_item_id == BoqItem.id)
        .join(BoqRevision, BoqItem.revision_id == BoqRevision.id)
        .join(Boq, BoqRevision.boq_id == Boq.id)
        .filter(Boq.id == existing_boq.id)
        .all()
        if existing_boq
        else []
    )

    existing_bills = db.query(RABill).filter(
        RABill.contract_id == contract.id
    ).all()

    if existing_boq or existing_baseline or existing_measurements or existing_bills:
        fail(
            "Demo dataset already exists or is partially populated. "
            "Use the application state inspection/recovery workflow instead "
            "of rerunning this clean seeder."
        )

    print("Precondition passed: no demo BOQ, measurements, RA Bills, or baseline exist.")


    print("\n=== 3. CREATING BOQ ===")

    boq = boq_service.create_boq(
        db,
        BoqCreate(
            contract_id=contract.id,
            boq_number=BOQ_NUMBER,
            title="District Hospital Upgrades - Main BOQ",
            description="Structural and Civil Works - Demonstration BOQ",
        ),
        admin,
    )

    revision = boq_service.create_revision(
        db,
        boq.id,
        BoqRevisionCreate(
            revision_number=1,
            revision_date=date(2026, 3, 1),
            remarks="Initial Demonstration Baseline",
        ),
        admin,
    )

    created_items = []

    for code, number, description, unit, quantity, rate in ITEMS:
        item = boq_service.create_item(
            db,
            revision.id,
            BoqItemCreate(
                item_code=code,
                item_number=number,
                description=description,
                unit=unit,
                quantity=quantity,
                rate=rate,
            ),
            admin,
        )
        created_items.append(item)

    boq_service.update_revision(
        db,
        revision.id,
        BoqRevisionUpdate(status="Submitted"),
        admin,
    )

    boq_service.update_revision(
        db,
        revision.id,
        BoqRevisionUpdate(status="Approved"),
        admin,
    )

    db.refresh(revision)

    revision_detail = boq_service._revision_detail(db, revision)
    boq_total = revision_detail["total"]

    if boq_total != EXPECTED_CONTRACT_VALUE:
        fail(
            f"BOQ total mismatch. Expected {EXPECTED_CONTRACT_VALUE}, "
            f"found {boq_total}."
        )

    print(f"BOQ created: {boq.boq_number}")
    print(f"Revision: {revision.revision_number} | {revision.status}")
    print(f"BOQ Total: ₹{boq_total:,.2f}")


    print("\n=== 4. CREATING APPROVED MEASUREMENTS ===")

    items_by_code = {item.item_code: item for item in created_items}
    month_to_measurement_ids = {}

    counter = 1

    for month, plan_items in MEASUREMENT_PLAN:
        month_ids = []
        measurement_date = date(2026, month, 25)

        for code, quantity in plan_items:
            reference = f"MB-2026-{month:02d}-{counter:03d}"

            detail = measurement_service.create_measurement(
                db,
                MeasurementCreate(
                    boq_item_id=items_by_code[code].id,
                    measurement_date=measurement_date,
                    quantity=quantity,
                    reference=reference,
                    description=f"Monthly progress for {month}/2026",
                ),
                admin,
            )

            measurement_id = detail.measurement.id

            measurement_service.submit_measurement(
                db,
                measurement_id,
                admin,
            )

            measurement_service.approve_measurement(
                db,
                measurement_id,
                admin,
            )

            month_ids.append(measurement_id)
            counter += 1

        month_to_measurement_ids[month] = month_ids
        print(f"Month {month}: {len(month_ids)} approved measurement(s).")


    print("\n=== 5. VALIDATING MEASUREMENTS ===")

    measurements = db.query(Measurement).filter(
        Measurement.boq_item_id.in_(
            [item.id for item in created_items]
        )
    ).all()

    if len(measurements) != 12:
        fail(f"Expected 12 measurements, found {len(measurements)}.")

    if not all(m.status == "Approved" for m in measurements):
        fail("Not all demo measurements are Approved.")

    print("CHECKPOINT PASSED: 12 Approved measurements.")


    print("\n=== 6. CREATING APPROVED RA BILLS ===")

    for bill_month, bill_number, months_to_bill in BILL_GROUPINGS:
        measurement_ids = []

        for month in months_to_bill:
            measurement_ids.extend(month_to_measurement_ids[month])

        bill_date = date(2026, bill_month, 28)

        bill = RABillService.create_bill(
            db,
            RABillCreate(
                contract_id=contract.id,
                bill_number=bill_number,
                bill_date=bill_date,
                period_from=date(2026, months_to_bill[0], 1),
                period_to=bill_date,
                remarks=f"RA Bill up to month {bill_month}/2026",
            ),
            admin.id,
        )

        RABillService.add_measurements(
            db,
            bill.id,
            measurement_ids,
            admin.id,
        )

        RABillService.submit_bill(
            db,
            bill.id,
            admin.id,
        )

        RABillService.approve_bill(
            db,
            bill.id,
            admin.id,
        )

        print(
            f"Created and Approved {bill_number} "
            f"with {len(measurement_ids)} measurement link(s)."
        )


    print("\n=== 7. VALIDATING RA BILLS ===")

    bills = db.query(RABill).filter(
        RABill.contract_id == contract.id
    ).all()

    if len(bills) != 3:
        fail(f"Expected 3 RA Bills, found {len(bills)}.")

    expected_bill_numbers = {"RA-04", "RA-06", "RA-09"}
    actual_bill_numbers = {bill.bill_number for bill in bills}

    if actual_bill_numbers != expected_bill_numbers:
        fail(
            f"RA Bill number mismatch. Expected {expected_bill_numbers}, "
            f"found {actual_bill_numbers}."
        )

    if not all(bill.status == "Approved" for bill in bills):
        fail("Not all demo RA Bills are Approved.")

    linked_measurements = db.query(RABillMeasurement).filter(
        RABillMeasurement.measurement_id.in_(
            [measurement.id for measurement in measurements]
        )
    ).count()

    if linked_measurements != 12:
        fail(
            f"Expected 12 RA Bill measurement links, "
            f"found {linked_measurements}."
        )

    print("CHECKPOINT PASSED: 3 Approved RA Bills with 12 links.")


    print("\n=== 8. CREATING EVM BASELINE ===")

    baseline = EVMService.create_baseline(
        db,
        project.id,
        EVMBaselineCreate(
            baseline_number=BASELINE_NUMBER,
            name="Original Schedule",
            effective_date=date(2026, 4, 1),
            remarks="Approved master schedule for demonstration",
        ),
        admin.id,
    )

    for period_date, percentage in EVM_PERIODS:
        EVMService.add_period(
            db,
            baseline.id,
            EVMBaselinePeriodCreate(
                period_date=period_date,
                planned_percentage=Decimal(percentage),
            ),
            admin.id,
        )

    EVMService.approve_baseline(
        db,
        baseline.id,
        admin.id,
    )

    db.refresh(baseline)

    if baseline.status != "Approved":
        fail(
            f"Expected EVM baseline Approved, found {baseline.status}."
        )

    periods = db.query(EVMBaselinePeriod).filter(
        EVMBaselinePeriod.baseline_id == baseline.id
    ).all()

    if len(periods) != 8:
        fail(f"Expected 8 EVM periods, found {len(periods)}.")

    print(
        f"Baseline: {baseline.baseline_number} | "
        f"{baseline.status} | {len(periods)} periods"
    )


    print("\n=== 9. FINAL EVM VALIDATION ===")

    evm = EVMService.get_evm(
        db,
        project.id,
        date(2026, 9, 30),
    )

    print(f"PV: ₹{evm.pv:,.2f}")
    print(f"EV: ₹{evm.ev:,.2f}")
    print(f"AC: ₹{evm.ac:,.2f}")
    print(f"SV: ₹{evm.sv:,.2f}")
    print(f"CV: ₹{evm.cv:,.2f}")
    print(f"SPI: {evm.spi}")
    print(f"CPI: {evm.cpi}")
    print(f"Planned: {evm.planned_percentage}%")
    print(f"Actual: {evm.actual_percentage}%")
    print(f"Schedule Status: {evm.schedule_status}")
    print(f"Cost Status: {evm.cost_status}")

    if evm.pv != Decimal("320100000.00"):
        fail(f"Unexpected September PV: {evm.pv}")

    if evm.ev != Decimal("227815000.00"):
        fail(f"Unexpected September EV: {evm.ev}")

    if evm.ac != Decimal("227815000.00"):
        fail(f"Unexpected September AC: {evm.ac}")

    if evm.planned_percentage != Decimal("66.0000"):
        fail(f"Unexpected planned percentage: {evm.planned_percentage}")

    print("CHECKPOINT PASSED: September EVM values match the canonical demo dataset.")

    print("\n=== DEMO DATASET CREATION COMPLETE ===")

except Exception:
    print(
        "\nFAILED: Service methods commit independently, "
        "so inspect the database before attempting any rerun."
    )
    traceback.print_exc()
    sys.exit(1)

finally:
    db.close()
