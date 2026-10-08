import json
import os
from decimal import Decimal
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.project import Project
from app.models.contract import Contract
from app.models.boq import Boq
from app.models.boq_revision import BoqRevision
from app.models.boq_item import BoqItem
from app.models.measurement import Measurement
from app.models.ra_bill import RABill, RABillItem, RABillMeasurement
from app.models.evm import EVMBaseline, EVMBaselinePeriod
from app.services.evm_service import EVMService

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def golden_data():
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "fixtures", "golden_project", "v1_ground_truth.json"
    )
    with open(fixture_path, "r") as f:
        data = json.load(f)

    # Structure validation
    assert "project" in data
    assert "contract" in data
    assert "boq" in data
    assert "measurements" in data
    assert "ra_bills" in data
    assert "evm" in data
    return data

def test_v1_golden_dataset(db_session, golden_data):
    # 1. Project
    p_data = golden_data["project"]
    project = db_session.query(Project).filter(Project.code == p_data["code"]).first()
    assert project is not None, f"Project {p_data['code']} not found"
    assert project.name == p_data["name"]

    # 2. Contract
    c_data = golden_data["contract"]
    contract = db_session.query(Contract).filter(Contract.project_id == project.id).first()
    assert contract is not None, "Contract not found"
    assert contract.contract_number == c_data["contract_number"]
    assert contract.contract_value == Decimal(c_data["contract_value"])

    # 3. BOQ & Revision
    b_data = golden_data["boq"]
    boq = db_session.query(Boq).filter(Boq.contract_id == contract.id).first()
    assert boq is not None, "BOQ not found"
    assert boq.boq_number == b_data["boq_number"]

    revision = db_session.query(BoqRevision).filter(BoqRevision.boq_id == boq.id).first()
    assert revision is not None, "BOQ Revision not found"
    assert str(revision.revision_number) == b_data["approved_revision_number"]
    assert revision.status == b_data["revision_status"]

    # BOQ Items
    items = db_session.query(BoqItem).filter(BoqItem.revision_id == revision.id).all()
    assert len(items) == b_data["item_count"]

    total_boq_value = sum(i.amount for i in items)
    assert total_boq_value == Decimal(b_data["total_boq_value"])

    diff = total_boq_value - contract.contract_value
    assert diff == Decimal(b_data["difference"])

    # Validate each item
    item_map = {i.item_code: i for i in items}
    for item_data in b_data["items"]:
        i_code = item_data["item_code"]
        assert i_code in item_map, f"Item {i_code} missing in DB"
        db_item = item_map[i_code]
        assert db_item.item_number == item_data["item_number"]
        assert db_item.description == item_data["description"]
        assert db_item.unit == item_data["unit"]
        assert db_item.quantity == Decimal(item_data["quantity"])
        assert db_item.rate == Decimal(item_data["rate"])
        assert db_item.amount == Decimal(item_data["amount"])

    # 4. Measurements
    m_data_list = golden_data["measurements"]
    item_ids = [i.id for i in items]
    db_measurements = db_session.query(Measurement).filter(Measurement.boq_item_id.in_(item_ids)).all()
    assert len(db_measurements) == len(m_data_list)

    db_m_map = {m.reference: m for m in db_measurements}

    id_to_code = {i.id: i.item_code for i in items}

    for m_data in m_data_list:
        ref = m_data["reference"]
        assert ref in db_m_map, f"Measurement {ref} missing in DB"
        db_m = db_m_map[ref]
        assert str(db_m.measurement_date) == m_data["measurement_date"]
        assert id_to_code[db_m.boq_item_id] == m_data["boq_item_code"]
        assert db_m.quantity == Decimal(m_data["quantity"])
        assert db_m.status == m_data["status"]

    # 5. RA Bills
    r_data_list = golden_data["ra_bills"]
    db_bills = db_session.query(RABill).filter(RABill.contract_id == contract.id).all()
    assert len(db_bills) == len(r_data_list)

    db_b_map = {b.bill_number: b for b in db_bills}
    for r_data in r_data_list:
        b_num = r_data["bill_number"]
        assert b_num in db_b_map, f"RA Bill {b_num} missing in DB"
        db_b = db_b_map[b_num]

        assert str(db_b.bill_date) == r_data["bill_date"]
        assert db_b.status == r_data["status"]
        assert db_b.gross_amount == Decimal(r_data["gross_amount"])
        assert db_b.net_payable == Decimal(r_data["net_payable"])

        b_item_ids = [ri.id for ri in db_session.query(RABillItem).filter(RABillItem.ra_bill_id == db_b.id).all()]
        linked_count = db_session.query(RABillMeasurement).filter(RABillMeasurement.ra_bill_item_id.in_(b_item_ids)).count() if b_item_ids else 0
        assert linked_count == r_data["linked_measurements"]

    # 6. EVM
    e_data = golden_data["evm"]
    baseline = db_session.query(EVMBaseline).filter(EVMBaseline.project_id == project.id).first()
    assert baseline is not None, "EVM Baseline not found"
    assert baseline.baseline_number == e_data["baseline_number"]
    assert baseline.status == e_data["baseline_status"]

    periods = db_session.query(EVMBaselinePeriod).filter(EVMBaselinePeriod.baseline_id == baseline.id).order_by(EVMBaselinePeriod.period_date).all()
    assert len(periods) == e_data["period_count"]
    assert len(periods) == len(e_data["periods"])

    for db_p, p_data in zip(periods, e_data["periods"]):
        assert str(db_p.period_date) == p_data["period_date"]
        assert db_p.planned_percentage == Decimal(p_data["planned_percentage"])

    # EVM Checkpoints
    for c_data in e_data["checkpoints"]:
        chk_date = date.fromisoformat(c_data["date"])
        stats = EVMService.get_evm(db_session, project.id, chk_date)

        assert stats.pv == Decimal(c_data["pv"]), f"PV mismatch for {chk_date}"
        assert stats.ev == Decimal(c_data["ev"]), f"EV mismatch for {chk_date}"
        assert stats.ac == Decimal(c_data["ac"]), f"AC mismatch for {chk_date}"
        assert stats.planned_percentage == Decimal(c_data["planned_percentage"]), f"Planned % mismatch for {chk_date}"
