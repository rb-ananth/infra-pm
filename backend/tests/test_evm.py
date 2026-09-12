
import uuid
from decimal import Decimal
from datetime import date, timedelta
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_current_user, get_db
from app.models.evm import EVMBaseline, EVMBaselinePeriod
from app.models.ra_bill import RABill, RABillItem
from app.models.boq import Boq
from app.models.boq_revision import BoqRevision
from app.models.boq_item import BoqItem
from app.models.contract import Contract
from app.models.project import Project
from app.models.measurement import Measurement
from app.models.user import User
from app.models.role import Role
from app.models.department import Department
from app.models.contractor import Contractor
from app.models.audit_log import AuditLog
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

from types import SimpleNamespace

def mock_auth(client_instance, user_id, role_name):
    def _override():
        class MockUser:
            def __init__(self):
                self.id = user_id
                self.role = SimpleNamespace(name=role_name)
        return MockUser()
    app.dependency_overrides[get_current_user] = _override

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()

@pytest.fixture
def setup_data(db_session):
    role = db_session.query(Role).filter(Role.name == "Admin").first()
    if not role:
        role = Role(name="Admin")
        db_session.add(role)
        db_session.flush()

    uid = str(uuid.uuid4())[:8]
    user = User(
        email=f"evm_{uid}@example.com",
        password_hash="hash",
        role_id=role.id,
    )
    db_session.add(user)
    db_session.flush()

    dept = Department(code=f"DEP-{uid}", name=f"Dept {uid}")
    db_session.add(dept)
    db_session.flush()

    project = Project(
        code=f"PRJ-{uid}",
        name=f"Project EVM {uid}",
        dept_id=dept.id,
        pm_id=user.id,
        status="Proposed",
        total_estimated_cost=Decimal("1000000.00"),
        start_date=date(2026, 1, 1),
        expected_completion=date(2026, 12, 31)
    )
    db_session.add(project)
    db_session.flush()

    contractor = Contractor(
        registration_number=f"CON-{uid}",
        name=f"Contractor {uid}",
        status="Active"
    )
    db_session.add(contractor)
    db_session.flush()

    contract = Contract(
        project_id=project.id,
        contractor_id=contractor.id,
        contract_number=f"CN-{uid}",
        award_date=date(2026, 1, 1),
        contract_value=Decimal("1000000.00"),
        start_date=date(2026, 1, 1),
        original_completion_date=date(2026, 12, 31),
        current_completion_date=date(2026, 12, 31),
        status="Active"
    )
    db_session.add(contract)
    db_session.flush()

    boq = Boq(
        contract_id=contract.id,
        boq_number=f"BOQ-{uid}",
        title="BOQ EVM",
        description=""
    )
    db_session.add(boq)
    db_session.flush()

    rev = BoqRevision(
        boq_id=boq.id,
        revision_number=1,
        revision_date=date(2026, 1, 1),
        status="Approved"
    )
    db_session.add(rev)
    db_session.flush()

    item = BoqItem(
        revision_id=rev.id,
        item_code="IT-1",
        item_number="1",
        description="Desc",
        unit="NOS",
        quantity=Decimal("100.00"),
        rate=Decimal("1000.00"),
        amount=Decimal("100000.00")
    )
    db_session.add(item)
    db_session.flush()

    return {
        "user_id": user.id,
        "project_id": project.id,
        "contract_id": contract.id,
        "item_id": item.id
    }


# 1. Baseline creation
def test_1_create_baseline(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    res = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-1", "name": "B1", "effective_date": "2026-01-01"})
    assert res.status_code == 200

# 2. Duplicate baseline number rejected
def test_2_duplicate_baseline_rejected(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-2", "name": "B1", "effective_date": "2026-01-01"})
    res = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-2", "name": "B2", "effective_date": "2026-01-01"})
    assert res.status_code == 400

# 3. Planned percentage validation (out of range/precision)
def test_3_planned_percentage_validation(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-3", "name": "B", "effective_date": "2026-01-01"}).json()
    res = client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "-1.0000"})
    assert res.status_code == 422
    res2 = client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-02", "planned_percentage": "105.0000"})
    assert res2.status_code == 422

# 4. Planned value calculated server-side
def test_4_planned_value_calculated(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-4", "name": "B", "effective_date": "2026-01-01"}).json()
    res = client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "10.0000"})
    assert Decimal(res.json()["planned_value"]) == Decimal("100000.00")

# 5. Period ordering
def test_5_period_ordering(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-5", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "10.0000"})
    res = client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2025-12-31", "planned_percentage": "20.0000"})
    assert res.status_code == 400
    assert "non-decreasing" in res.json()["detail"].lower()

# 6. Non-decreasing planned percentage
def test_6_non_decreasing_planned_percentage(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-6", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "10.0000"})
    res = client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-10", "planned_percentage": "5.0000"})
    assert res.status_code == 400

# 7. Approval requires final 100% period
def test_7_approval_requires_100_percent(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-7", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "50.0000"})
    res = client.post(f"/api/v1/evm-baselines/{b['id']}/approve")
    assert res.status_code == 400

# 8. Only one Approved baseline
def test_8_only_one_approved_baseline(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b1 = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-8-1", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b1['id']}/periods", json={"period_date": "2026-02-01", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b1['id']}/approve")
    b2 = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-8-2", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b2['id']}/periods", json={"period_date": "2026-02-01", "planned_percentage": "100.0000"})
    res = client.post(f"/api/v1/evm-baselines/{b2['id']}/approve")
    assert res.status_code == 400

# 9. Approved baseline cannot regress to Draft
def test_9_approved_cannot_regress_to_draft(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-9", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-02-01", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")
    res = client.put(f"/api/v1/evm-baselines/{b['id']}", json={"status": "Draft"})
    assert res.status_code == 403

# 10. Superseding a baseline works correctly
def test_10_superseding_baseline(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-10", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-02-01", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")
    res = client.post(f"/api/v1/evm-baselines/{b['id']}/supersede")
    assert res.status_code == 200

# 11. PV exact-period calculation
def test_11_pv_exact_period(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-11", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "10.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-01")
    assert Decimal(res.json()["pv"]) == Decimal("100000.00")

# 12. PV interpolation
def test_12_pv_interpolation(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-12", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "0.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-11", "planned_percentage": "10.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-06")
    assert Decimal(res.json()["pv"]) == Decimal("50000.00")

# 13. PV before and after final baseline period
def test_13_pv_before_and_after(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-13", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-10", "planned_percentage": "10.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")
    res_before = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-01")
    assert Decimal(res_before.json()["pv"]) == Decimal("0.00")
    res_after = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-02-10")
    assert Decimal(res_after.json()["pv"]) == Decimal("1000000.00")

# 14. EV uses Approved Measurements only
def test_14_ev_approved_measurements_only(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-14", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")

    m = Measurement(boq_item_id=setup_data["item_id"], measurement_date=date(2026, 1, 15), quantity=Decimal("10.000"), reference="R1", description="D1", status="Approved", created_by=setup_data["user_id"])
    db_session.add(m)
    db_session.flush()
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-20")
    assert Decimal(res.json()["ev"]) == Decimal("10000.00")

# 15. Draft/Submitted/Rejected measurements do not affect EV
def test_15_ev_ignores_unapproved(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-15", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")

    m = Measurement(boq_item_id=setup_data["item_id"], measurement_date=date(2026, 1, 15), quantity=Decimal("10.000"), reference="R1", description="D1", status="Draft", created_by=setup_data["user_id"])
    db_session.add(m)
    db_session.flush()
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-20")
    assert Decimal(res.json()["ev"]) == Decimal("0.00")

# 16. AC uses Approved RA Bills only
def test_16_ac_approved_bills_only(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-16", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")

    bill = RABill(contract_id=setup_data["contract_id"], bill_number="RB-16", bill_date=date(2026, 1, 20), period_from=date(2026, 1, 1), period_to=date(2026, 1, 20), status="Approved", gross_amount=Decimal("12000.00"), net_payable=Decimal("12000.00"), created_by=setup_data["user_id"])
    db_session.add(bill)
    db_session.flush()
    bill_item = RABillItem(ra_bill_id=bill.id, boq_item_id=setup_data["item_id"], current_quantity=Decimal("10.000"), rate=Decimal("1000.00"), current_amount=Decimal("12000.00"))
    db_session.add(bill_item)
    db_session.flush()
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-25")
    assert Decimal(res.json()["ac"]) == Decimal("12000.00")

# 17. Draft/Submitted/Rejected RA Bills do not affect AC
def test_17_ac_ignores_unapproved(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-17", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")

    bill = RABill(contract_id=setup_data["contract_id"], bill_number="RB-17", bill_date=date(2026, 1, 20), period_from=date(2026, 1, 1), period_to=date(2026, 1, 20), status="Draft", gross_amount=Decimal("12000.00"), net_payable=Decimal("12000.00"), created_by=setup_data["user_id"])
    db_session.add(bill)
    db_session.flush()
    bill_item = RABillItem(ra_bill_id=bill.id, boq_item_id=setup_data["item_id"], current_quantity=Decimal("10.000"), rate=Decimal("1000.00"), current_amount=Decimal("12000.00"))
    db_session.add(bill_item)
    db_session.flush()
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-25")
    assert Decimal(res.json()["ac"]) == Decimal("0.00")

# 18. Correct SV/CV/SPI/CPI
def test_18_metrics(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-18", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "0.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-11", "planned_percentage": "10.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")

    m1 = Measurement(boq_item_id=setup_data["item_id"], measurement_date=date(2026, 1, 5), quantity=Decimal("10.000"), reference="R1", description="D1", status="Approved", created_by=setup_data["user_id"])
    bill = RABill(contract_id=setup_data["contract_id"], bill_number="RB-18", bill_date=date(2026, 1, 5), period_from=date(2026, 1, 1), period_to=date(2026, 1, 5), status="Approved", gross_amount=Decimal("12000.00"), net_payable=Decimal("12000.00"), created_by=setup_data["user_id"])
    db_session.add_all([m1, bill])
    db_session.flush()
    bill_item = RABillItem(ra_bill_id=bill.id, boq_item_id=setup_data["item_id"], current_quantity=Decimal("10.000"), rate=Decimal("1000.00"), current_amount=Decimal("12000.00"))
    db_session.add(bill_item)
    db_session.flush()

    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-06")
    data = res.json()
    # PV at day 6 = 50000
    # EV = 10000
    # AC = 12000
    assert Decimal(data["sv"]) == Decimal("-40000.00")
    assert Decimal(data["cv"]) == Decimal("-2000.00")
    assert Decimal(data["spi"]) == Decimal("0.2000")
    assert Decimal(data["cpi"]) == Decimal("0.8333")

# 19. Zero-denominator handling
def test_19_zero_denominator(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-19", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "0.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")

    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-01")
    data = res.json()
    assert data["spi"] is None
    assert data["cpi"] is None

# 20. Actual percentage calculation
def test_20_actual_percentage(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-20", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")

    m = Measurement(boq_item_id=setup_data["item_id"], measurement_date=date(2026, 1, 15), quantity=Decimal("100.000"), reference="R1", description="D1", status="Approved", created_by=setup_data["user_id"])
    db_session.add(m)
    db_session.flush()
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-01-20")
    # EV = 100000, Total Est = 1000000 => 10%
    assert Decimal(res.json()["actual_percentage"]) == Decimal("10.0000")

# 21. Trend calculation
def test_21_trend_calculation(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-21", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "0.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")
    
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm/trend")
    assert len(res.json()) == 2

# 22. RBAC restrictions
def test_22_rbac(client, setup_data):
    mock_auth(client, setup_data["user_id"], "Viewer")
    res = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-22", "name": "B", "effective_date": "2026-01-01"})
    assert res.status_code == 403

# 23. Audit log creation
def test_23_audit_logs(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-23", "name": "B", "effective_date": "2026-01-01"})
    logs = db_session.execute(text("SELECT action FROM audit_logs WHERE action = 'EVM_BASELINE_CREATE'")).fetchall()
    assert len(logs) > 0

# 24. Transaction rollback behavior
def test_24_transaction_rollback(client, setup_data, db_session):
    from sqlalchemy.exc import IntegrityError
    from app.models.evm import EVMBaseline
    mock_auth(client, setup_data["user_id"], "Admin")

    try:
        with db_session.begin_nested():
            # Valid insert
            b1 = EVMBaseline(
                project_id=setup_data["project_id"],
                baseline_number="RB-1",
                name="Rollback 1",
                status="Draft",
                effective_date=date(2026, 1, 1),
                created_by=setup_data["user_id"]
            )
            db_session.add(b1)
            db_session.flush()

            # Intentionally fail by repeating the same baseline_number for the same project
            # This triggers uq_evm_baselines_project_number unique constraint
            b2 = EVMBaseline(
                project_id=setup_data["project_id"],
                baseline_number="RB-1",
                name="Rollback 2",
                status="Draft",
                effective_date=date(2026, 1, 1),
                created_by=setup_data["user_id"]
            )
            db_session.add(b2)
            db_session.flush()
    except IntegrityError:
        pass  # Context manager automatically rolls back the savepoint on exception

    # The rollback should have removed RB-1 entirely from the session/database
    check = db_session.query(EVMBaseline).filter_by(baseline_number="RB-1").first()
    assert check is None
    
    # Session is still usable
    b3 = EVMBaseline(
        project_id=setup_data["project_id"],
        baseline_number="RB-VALID",
        name="Valid",
        status="Draft",
        effective_date=date(2026, 1, 1),
        created_by=setup_data["user_id"]
    )
    db_session.add(b3)
    db_session.flush()
    assert b3.id is not None

# 25. EV filtering respects as_of_date
def test_25_ev_as_of_date_filtering(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-25", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")

    m_past = Measurement(boq_item_id=setup_data["item_id"], measurement_date=date(2026, 1, 15), quantity=Decimal("10.000"), reference="R1", description="D1", status="Approved", created_by=setup_data["user_id"])
    m_future = Measurement(boq_item_id=setup_data["item_id"], measurement_date=date(2026, 4, 1), quantity=Decimal("5.000"), reference="R2", description="D2", status="Approved", created_by=setup_data["user_id"])
    db_session.add_all([m_past, m_future])
    db_session.flush()
    
    # Query before future measurement
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-03-31")
    # Only past measurement should be included: 10 * 1000 = 10000
    assert Decimal(res.json()["ev"]) == Decimal("10000.00")

    # Query after future measurement
    res2 = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-04-02")
    assert Decimal(res2.json()["ev"]) == Decimal("15000.00")

# 26. AC filtering respects as_of_date
def test_26_ac_as_of_date_filtering(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-26", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")

    bill_past = RABill(contract_id=setup_data["contract_id"], bill_number="RB-26-1", bill_date=date(2026, 1, 20), period_from=date(2026, 1, 1), period_to=date(2026, 1, 20), status="Approved", gross_amount=Decimal("12000.00"), net_payable=Decimal("12000.00"), created_by=setup_data["user_id"])
    bill_future = RABill(contract_id=setup_data["contract_id"], bill_number="RB-26-2", bill_date=date(2026, 4, 1), period_from=date(2026, 3, 1), period_to=date(2026, 3, 31), status="Approved", gross_amount=Decimal("5000.00"), net_payable=Decimal("5000.00"), created_by=setup_data["user_id"])
    db_session.add_all([bill_past, bill_future])
    db_session.flush()
    
    bill_item_past = RABillItem(ra_bill_id=bill_past.id, boq_item_id=setup_data["item_id"], current_quantity=Decimal("10.000"), rate=Decimal("1000.00"), current_amount=Decimal("12000.00"))
    bill_item_future = RABillItem(ra_bill_id=bill_future.id, boq_item_id=setup_data["item_id"], current_quantity=Decimal("5.000"), rate=Decimal("1000.00"), current_amount=Decimal("5000.00"))
    db_session.add_all([bill_item_past, bill_item_future])
    db_session.flush()
    
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-03-31")
    assert Decimal(res.json()["ac"]) == Decimal("12000.00")

    res2 = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm?as_of_date=2026-04-02")
    assert Decimal(res2.json()["ac"]) == Decimal("17000.00")

# 27. Trend points independently exclude future dates
def test_27_trend_as_of_date_filtering(client, setup_data, db_session):
    mock_auth(client, setup_data["user_id"], "Admin")
    b = client.post(f"/api/v1/projects/{setup_data['project_id']}/evm/baselines", json={"baseline_number": "T-27", "name": "B", "effective_date": "2026-01-01"}).json()
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-01-01", "planned_percentage": "0.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/periods", json={"period_date": "2026-03-31", "planned_percentage": "100.0000"})
    client.post(f"/api/v1/evm-baselines/{b['id']}/approve")
    
    m_future = Measurement(boq_item_id=setup_data["item_id"], measurement_date=date(2026, 4, 1), quantity=Decimal("10.000"), reference="R1", description="D1", status="Approved", created_by=setup_data["user_id"])
    db_session.add(m_future)
    db_session.flush()
    
    res = client.get(f"/api/v1/projects/{setup_data['project_id']}/evm/trend")
    data = res.json()
    # Trend point for 2026-03-31 should NOT include the measurement from 2026-04-01
    assert Decimal(data[1]["ev"]) == Decimal("0.00")

# 28. Database level single approved baseline enforcement
def test_28_db_level_single_approved_baseline(db_session, setup_data):
    from sqlalchemy.exc import IntegrityError
    from app.models.evm import EVMBaseline
    
    b1 = EVMBaseline(
        project_id=setup_data["project_id"],
        baseline_number="DB-1",
        name="DB 1",
        status="Approved",
        effective_date=date(2026, 1, 1),
        created_by=setup_data["user_id"]
    )
    db_session.add(b1)
    db_session.flush()

    b2 = EVMBaseline(
        project_id=setup_data["project_id"],
        baseline_number="DB-2",
        name="DB 2",
        status="Approved",
        effective_date=date(2026, 1, 1),
        created_by=setup_data["user_id"]
    )
    db_session.add(b2)
    
    with pytest.raises(IntegrityError) as excinfo:
        db_session.flush()
        
    assert "ix_evm_baselines_single_approved" in str(excinfo.value)
    db_session.rollback()
