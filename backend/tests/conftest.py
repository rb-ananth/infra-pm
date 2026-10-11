import os
import sys
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure the backend directory is importable during pytest collection.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Tests expect PostgreSQL to be running and the schema to have been migrated.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://infra_user:infra_password@localhost:5432/infra_pm_test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

from app.core.config import settings

db_url = make_url(str(settings.DATABASE_URL))
if db_url.database not in {"infra_pm_test_db", "infra_pm_golden_test_db"}:
    sys.exit(f"CRITICAL CONFIG ERROR: Target database '{db_url.database}' is unauthorized.")

def pytest_runtest_setup(item):
    db_url = make_url(str(settings.DATABASE_URL))
    if db_url.database == "infra_pm_test_db":
        if item.get_closest_marker("golden"):
            pytest.fail(f"ERROR: Test '{item.name}' strictly requires infra_pm_golden_test_db, but current is {db_url.database}")
    elif db_url.database == "infra_pm_golden_test_db":
        if not item.get_closest_marker("golden"):
            pytest.fail(f"ERROR: Generic test '{item.name}' cannot run against infra_pm_golden_test_db")

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture(autouse=True)
def ensure_auth_test_users(request):
    # Only seed authentication users when the test requests a database session.
    if "db_session" not in request.fixturenames:
        return

    db_session = request.getfixturevalue("db_session")

    from app.models.user import User
    from app.models.role import Role
    from app.core.security import get_password_hash

    test_users = [
    ("admin@infrapm.gov", "Admin@123", "Admin"),
    ("pm@infrapm.gov", "PM@123", "Project Manager"),
    ("eng@infrapm.gov", "Eng@123", "Engineer"),
    ("billing@infrapm.gov", "Bill@123", "Billing Engineer"),
    ("viewer@infrapm.gov", "View@123", "Viewer"),
    ]

    for email, password, role_name in test_users:
        role = db_session.query(Role).filter_by(name=role_name).first()

        if role is None:
            role = Role(name=role_name)
            db_session.add(role)
            db_session.flush()

        user = db_session.query(User).filter_by(email=email).first()

        if user is None:
            user = User(
                email=email,
                password_hash=get_password_hash(password),
                role_id=role.id,
                is_active=True,
            )
            db_session.add(user)
        else:
            user.password_hash = get_password_hash(password)
            user.role_id = role.id
            user.is_active = True

    db_session.commit()

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

@pytest.fixture
def populate_golden_dataset(db_session, golden_data):
    from app.models.department import Department
    from app.models.user import User, UserProjectAssignment
    from app.models.contractor import Contractor
    from app.models.project import Project
    from app.models.contract import Contract
    from app.models.boq import Boq
    from app.models.boq_revision import BoqRevision
    from app.models.boq_item import BoqItem
    from app.models.measurement import Measurement
    from app.models.ra_bill import RABill, RABillItem, RABillMeasurement
    from app.models.evm import EVMBaseline, EVMBaselinePeriod
    from decimal import Decimal
    from datetime import date
    from app.models.role import Role
    from app.core.security import get_password_hash

    db = db_session

    dept = db.query(Department).filter_by(code="PWD").first()
    if not dept:
        dept = Department(code="PWD", name="Public Works Department", is_active=True)
        db.add(dept)
        db.flush()

    # Ensure the Project Manager role exists.
    pm_role = db.query(Role).filter_by(name="Project Manager").first()
    if not pm_role:
        pm_role = Role(name="Project Manager")
        db.add(pm_role)
        db.flush()

    # Ensure the project manager exists with valid credentials.
    pm = db.query(User).filter_by(email="pm@infrapm.gov").first()
    if not pm:
        pm = User(
            email="pm@infrapm.gov",
            password_hash=get_password_hash("PM@123"),
            role_id=pm_role.id,
            is_active=True,
        )
        db.add(pm)
        db.flush()
    else:
        # Repair an existing fixture user created by an earlier failed run.
        pm.role_id = pm_role.id
        pm.password_hash = get_password_hash("PM@123")
        pm.is_active = True
        db.flush()


    p_data = golden_data["project"]
    proj = db.query(Project).filter_by(code=p_data["code"]).first()
    if not proj:
        proj = Project(
            code=p_data["code"], name=p_data["name"],
            dept_id=dept.id, pm_id=pm.id, status="Execution",
            total_estimated_cost=Decimal("485000000.00"), start_date=date(2026,4,1), expected_completion=date(2027,3,31)
        )
        db.add(proj)
        db.flush()

    upa = db.query(UserProjectAssignment).filter_by(user_id=pm.id, project_id=proj.id).first()
    if not upa:
        upa = UserProjectAssignment(user_id=pm.id, project_id=proj.id)
        db.add(upa)
        db.flush()

    cont = db.query(Contractor).first()
    if not cont:
        cont = Contractor(registration_number="XYZ-123", name="Golden Contractor")
        db.add(cont)
        db.flush()

    c_data = golden_data["contract"]

    contract = db.query(Contract).filter_by(
        contract_number=c_data["contract_number"]
    ).first()

    if contract is None:
        contract = Contract(
            project_id=proj.id,
            contractor_id=cont.id,
            contract_number=c_data["contract_number"],
            contract_value=Decimal(c_data["contract_value"]),
            status="Execution",
            award_date=date(2026, 4, 1),
            start_date=date(2026, 4, 1),
            original_completion_date=date(2027, 3, 31),
            current_completion_date=date(2027, 3, 31),
        )
        db.add(contract)
        db.flush()
    elif contract.project_id != proj.id:
        raise AssertionError(
            "Golden contract exists but is linked to a different project"
        )

    boq_data = golden_data["boq"]
    boq = Boq(
        contract_id=contract.id, boq_number=boq_data["boq_number"],
        title="Golden BOQ", status="Approved"
    )
    db.add(boq)
    db.flush()

    boq_rev = BoqRevision(
        boq_id=boq.id, revision_number=int(boq_data["approved_revision_number"]),
        revision_date=date(2026,4,1), status="Approved"
    )
    db.add(boq_rev)
    db.flush()

    item_map = {}
    for i_data in boq_data["items"]:
        b_item = BoqItem(
            revision_id=boq_rev.id, item_code=i_data["item_code"], item_number=i_data["item_number"],
            description=i_data["description"], unit=i_data["unit"],
            quantity=Decimal(i_data["quantity"]), rate=Decimal(i_data["rate"]),
            amount=Decimal(i_data["amount"])
        )
        db.add(b_item)
        db.flush()
        item_map[b_item.item_code] = b_item

    real_measurements = []
    for m_data in golden_data["measurements"]:
        m = Measurement(
            boq_item_id=item_map[m_data["boq_item_code"]].id, reference=m_data["reference"],
            quantity=Decimal(m_data["quantity"]), status=m_data["status"],
            measurement_date=date.fromisoformat(m_data["measurement_date"]),
            created_by=pm.id, description="Golden Measurement"
        )
        db.add(m)
        db.flush()
        real_measurements.append(m)

    from collections import defaultdict
    measurement_queue = real_measurements.copy()

    for r_data in golden_data["ra_bills"]:
        bill = RABill(
            contract_id=contract.id, bill_number=r_data["bill_number"],
            bill_date=date.fromisoformat(r_data["bill_date"]), status=r_data["status"],
            gross_amount=Decimal(r_data["gross_amount"]), net_payable=Decimal(r_data["net_payable"]),
            period_from=date(2026,4,1), period_to=date(2026,4,30), created_by=pm.id
        )
        db.add(bill)
        db.flush()

        linked_count = r_data["linked_measurements"]
        bill_measurements = [measurement_queue.pop(0) for _ in range(linked_count)]

        item_groups = defaultdict(list)
        for m in bill_measurements:
            item_groups[m.boq_item_id].append(m)

        for boq_item_id, m_list in item_groups.items():
            b_item = db.query(BoqItem).filter_by(id=boq_item_id).first()
            total_qty = sum(m.quantity for m in m_list)
            total_amount = total_qty * b_item.rate

            bill_item = RABillItem(
                ra_bill_id=bill.id, boq_item_id=boq_item_id,
                current_quantity=total_qty, rate=b_item.rate, current_amount=total_amount
            )
            db.add(bill_item)
            db.flush()

            for m in m_list:
                db.add(RABillMeasurement(ra_bill_item_id=bill_item.id, measurement_id=m.id))
        db.flush()

    e_data = golden_data["evm"]
    baseline = EVMBaseline(
        project_id=proj.id, baseline_number=e_data["baseline_number"],
        status=e_data["baseline_status"], effective_date=date(2026,4,1),
        name="Golden Baseline", created_by=pm.id
    )
    db.add(baseline)
    db.flush()

    for p_data in e_data["periods"]:
        bp = EVMBaselinePeriod(
            baseline_id=baseline.id, period_date=date.fromisoformat(p_data["period_date"]),
            planned_percentage=Decimal(p_data["planned_percentage"]),
            planned_value=Decimal(p_data["planned_percentage"]) / Decimal("100") * Decimal(c_data["contract_value"])
        )
        db.add(bp)
        db.flush()

    db.commit()
    try:
        yield proj
    finally:
        db.rollback()

@pytest.fixture
def db_session():
    engine = create_engine(settings.DATABASE_URL)
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()

@pytest.fixture
def isolated_project_and_contract(db_session):
    from app.models.project import Project
    from app.models.contract import Contract
    from app.models.user import User
    from app.models.role import Role
    from app.models.department import Department
    from app.models.contractor import Contractor
    from app.models.user import UserProjectAssignment
    import uuid
    from datetime import date

    admin_role = db_session.query(Role).filter_by(name="Admin").first()
    if not admin_role:
        admin_role = Role(id=uuid.uuid4(), name="Admin")
        db_session.add(admin_role)
        db_session.flush()

    dept = db_session.query(Department).first()
    if not dept:
        dept = Department(id=uuid.uuid4(), name="Test Dept", code=f"DEPT-{uuid.uuid4().hex[:6]}")
        db_session.add(dept)
        db_session.flush()

    contractor = db_session.query(Contractor).first()
    if not contractor:
        contractor = Contractor(id=uuid.uuid4(), name="Test Contractor", registration_number=f"REG-{uuid.uuid4().hex[:6]}")
        db_session.add(contractor)
        db_session.flush()

    admin_user = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hash",
        role_id=admin_role.id,
        is_active=True
    )
    db_session.add(admin_user)
    db_session.flush()

    project = Project(
        code=f"PRJ-{uuid.uuid4().hex[:6]}",
        name="Isolated Test Project",
        dept_id=dept.id,
        pm_id=admin_user.id,
        status="Active",
        total_estimated_cost=1000000.0,
        start_date=date(2026, 1, 1),
        expected_completion=date(2026, 12, 31)
    )
    db_session.add(project)
    db_session.flush()

    contract = Contract(
        project_id=project.id,
        contract_number=f"CON-{uuid.uuid4().hex[:6]}",
        contractor_id=contractor.id,
        contract_value=1000000.0,
        award_date=date(2026, 1, 1),
        start_date=date(2026, 1, 1),
        original_completion_date=date(2026, 12, 31),
        current_completion_date=date(2026, 12, 31),
        status="Active"
    )
    db_session.add(contract)
    db_session.flush()

    pm_user = db_session.query(User).filter_by(email="pm@infrapm.gov").first()
    if pm_user:
        assignment = UserProjectAssignment(user_id=pm_user.id, project_id=project.id)
        db_session.add(assignment)
        db_session.flush()

    db_session.commit()

    try:
        yield {"project": project, "contract": contract, "admin_user": admin_user}
    finally:
        db_session.rollback()

@pytest.fixture(autouse=True, scope="function")
def global_exact_id_cleanup():
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    tracked = []

    def on_flush(sess, flush_context):
        for obj in sess.new:
            pk = getattr(obj, "id", None)
            if pk is not None:
                tracked.append((type(obj), pk))

    event.listen(Session, "after_flush", on_flush)

    try:
        yield
    finally:
        event.remove(Session, "after_flush", on_flush)

        cleanup_list = []
        seen = set()
        for model, pk in tracked:
            key = (model, pk)
            if key not in seen:
                seen.add(key)
                cleanup_list.append((model, pk))

        if cleanup_list:
            from app.core.database import SessionLocal
            from app.models.base import Base
            from app.models.document import DocumentChunk

            cleanup_sess = SessionLocal()
            try:
                # Order tracked models child-first using registered FK metadata.
                table_order = {
                    table.name: index
                    for index, table in enumerate(Base.metadata.sorted_tables)
                }
                cleanup_list.sort(
                    key=lambda item: table_order.get(item[0].__table__.name, -1),
                    reverse=True,
                )

                # Clear self-references among tracked chunks before deleting them.
                chunk_ids = [
                    pk for model, pk in cleanup_list
                    if model is DocumentChunk
                ]
                if chunk_ids:
                    cleanup_sess.query(DocumentChunk).filter(
                        DocumentChunk.id.in_(chunk_ids)
                    ).update(
                        {DocumentChunk.parent_chunk_id: None},
                        synchronize_session=False,
                    )

                for model, pk in cleanup_list:
                    cleanup_sess.query(model).filter(
                        model.id == pk
                    ).delete(synchronize_session=False)

                cleanup_sess.commit()
            except Exception:
                cleanup_sess.rollback()
                raise
            finally:
                cleanup_sess.close()