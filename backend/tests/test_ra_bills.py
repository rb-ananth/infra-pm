
import uuid
from decimal import Decimal
from datetime import date, datetime
import threading
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.api.deps import get_current_user, get_db
from app.models.ra_bill import RABill, RABillItem, RABillMeasurement, RABillDeduction
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
from app.services.ra_bill_service import RABillService
from app.schemas.ra_bill import RABillCreate, RABillItemCreateMulti, RABillDeductionCreate, RABillUpdate

# Setup real engine
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()

@pytest.fixture
def db():
    db = SessionLocal()
    yield db
    db.close()

@pytest.fixture
def client():
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()

def setup_test_data(db):
    r_id = uuid.uuid4()
    r = Role(id=r_id, name=f"Admin-{str(r_id)[:8]}")
    db.add(r)
    
    u_id = uuid.uuid4()
    u = User(id=u_id, email=f"test_{str(u_id)[:8]}@infrapm.com", password_hash="pw", role_id=r_id, is_active=True)
    db.add(u)
    
    p_id = uuid.uuid4()
    d_id = uuid.uuid4()
    d = Department(id=d_id, code=f"D-{str(d_id)[:8]}", name="Dept")
    db.add(d)

    p = Project(id=p_id, code=f"P-{str(p_id)[:8]}", name="P", dept_id=d_id, pm_id=u_id, status="Active", total_estimated_cost=Decimal("100"), start_date=date.today(), expected_completion=date.today())
    db.add(p)
    
    c_id = uuid.uuid4()
    con_id = uuid.uuid4()
    con = Contractor(id=con_id, registration_number=f"R-{str(con_id)[:8]}", name="Con", status="Active")
    db.add(con)
    
    c = Contract(id=c_id, contract_number=f"C-{str(c_id)[:8]}", project_id=p_id, contractor_id=con_id, award_date=date.today(), contract_value=Decimal("10000"), start_date=date.today(), original_completion_date=date.today(), current_completion_date=date.today(), status="Active")
    db.add(c)
    
    boq_id = uuid.uuid4()
    boq = Boq(id=boq_id, contract_id=c_id, boq_number=f"B-{boq_id}", title="B", status="Approved")
    db.add(boq)
    
    rev_id = uuid.uuid4()
    rev = BoqRevision(id=rev_id, boq_id=boq_id, revision_number=1, revision_date=date.today(), remarks="", status="Approved")
    db.add(rev)
    
    bi_id = uuid.uuid4()
    bi = BoqItem(id=bi_id, revision_id=rev_id, item_code="I-1", item_number="1", description="desc", unit="m3", quantity=Decimal("100"), rate=Decimal("10"), amount=Decimal("1000"))
    db.add(bi)
    
    m_id1 = uuid.uuid4()
    m1 = Measurement(id=m_id1, boq_item_id=bi_id, measurement_date=date.today(), quantity=Decimal("10"), reference="R1", description="d1", status="Approved", created_by=u_id)
    db.add(m1)
    
    m_id2 = uuid.uuid4()
    m2 = Measurement(id=m_id2, boq_item_id=bi_id, measurement_date=date.today(), quantity=Decimal("5"), reference="R2", description="d2", status="Approved", created_by=u_id)
    db.add(m2)
    
    db.commit()
    
    return {
        "user_id": u_id,
        "contract_id": c_id,
        "boq_id": boq_id,
        "boq_item_id": bi_id,
        "measurement_1": m_id1,
        "measurement_2": m_id2,
        "user": u,
        "role": r
    }

from types import SimpleNamespace
def mock_auth(client, user, role_name):
    def _override():
        return SimpleNamespace(id=user.id, role=SimpleNamespace(name=role_name), is_active=True)
    app.dependency_overrides[get_current_user] = _override

# --- 1. RBAC Tests ---
def test_rbac_admin_pm_be_can_create(client, db):
    data = setup_test_data(db)
    for role in ["Admin", "Project Manager", "Billing Engineer"]:
        mock_auth(client, data["user"], role)
        res = client.post("/api/v1/ra-bills/", json={
            "contract_id": str(data["contract_id"]),
            "bill_number": f"RBAC-{role}-{uuid.uuid4()}",
            "bill_date": str(date.today()),
            "period_from": str(date.today()),
            "period_to": str(date.today())
        })
        assert res.status_code == 201

def test_rbac_engineer_viewer_cannot_create(client, db):
    data = setup_test_data(db)
    for role in ["Engineer", "Viewer"]:
        mock_auth(client, data["user"], role)
        res = client.post("/api/v1/ra-bills/", json={
            "contract_id": str(data["contract_id"]),
            "bill_number": f"RBAC-FAIL-{role}-{uuid.uuid4()}",
            "bill_date": str(date.today()),
            "period_from": str(date.today()),
            "period_to": str(date.today())
        })
        assert res.status_code == 403

def test_rbac_billing_engineer_cannot_approve(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]),
        "bill_number": f"RBAC-APP-{uuid.uuid4()}",
        "bill_date": str(date.today()),
        "period_from": str(date.today()),
        "period_to": str(date.today())
    })
    bill_id = res.json()["id"]
    client.post(f"/api/v1/ra-bills/{bill_id}/submit")
    
    mock_auth(client, data["user"], "Billing Engineer")
    res_app = client.post(f"/api/v1/ra-bills/{bill_id}/approve")
    assert res_app.status_code == 403

# --- 2. RA Bill Validation ---
def test_duplicate_bill_number(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    b_num = f"DUP-{uuid.uuid4()}"
    res1 = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": b_num,
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    assert res1.status_code == 201
    res2 = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": b_num,
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    assert res2.status_code == 409

def test_same_bill_number_different_contracts(client, db):
    data1 = setup_test_data(db)
    data2 = setup_test_data(db)
    mock_auth(client, data1["user"], "Admin")
    b_num = f"DUP-{uuid.uuid4()}"
    res1 = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data1["contract_id"]), "bill_number": b_num,
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    assert res1.status_code == 201
    res2 = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data2["contract_id"]), "bill_number": b_num,
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    assert res2.status_code == 201

def test_invalid_period(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"INV-{uuid.uuid4()}",
        "bill_date": "2024-01-01", "period_from": "2024-01-05", "period_to": "2024-01-01"
    })
    assert res.status_code == 422 # Integrity Error check violation trapped or Pydantic

def test_negative_monetary_values(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"INV-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    bill_id = res.json()["id"]
    res2 = client.post(f"/api/v1/ra-bills/{bill_id}/deductions", json={
        "deduction_type": "Tax", "amount": -500.00
    })
    assert res2.status_code == 422 # Pydantic schema validation

# --- 3. Measurement Eligibility ---
def test_measurement_eligibility(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    
    # create bill
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"B-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    bill_id = res.json()["id"]
    
    # Test approved
    res2 = client.post(f"/api/v1/ra-bills/{bill_id}/items", json={
        "measurement_ids": [str(data["measurement_1"])]
    })
    assert res2.status_code == 200
    
    # test duplicate billing
    res3 = client.post(f"/api/v1/ra-bills/{bill_id}/items", json={
        "measurement_ids": [str(data["measurement_1"])]
    })
    assert res3.status_code == 409
    
    # add unapproved measurement
    m3_id = uuid.uuid4()
    m3 = Measurement(id=m3_id, boq_item_id=data["boq_item_id"], measurement_date=date.today(), quantity=Decimal("5"), reference="R3", description="d3", status="Draft", created_by=data["user_id"])
    db.add(m3)
    db.commit()
    
    res4 = client.post(f"/api/v1/ra-bills/{bill_id}/items", json={
        "measurement_ids": [str(m3_id)]
    })
    assert res4.status_code == 422

# --- 4. Server derived calculations ---
def test_server_derived_totals_and_deductions(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"B-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    bill_id = res.json()["id"]
    
    # Add measurements 10 and 5, rate 10 => 150 total
    res2 = client.post(f"/api/v1/ra-bills/{bill_id}/items", json={
        "measurement_ids": [str(data["measurement_1"]), str(data["measurement_2"])]
    })
    assert res2.status_code == 200
    assert res2.json()["gross_amount"] == "150.00"
    
    # Add deduction of 200 => negative net payable => reject
    res3 = client.post(f"/api/v1/ra-bills/{bill_id}/deductions", json={
        "deduction_type": "Tax", "amount": 200.00
    })
    assert res3.status_code == 422
    
    # Add deduction of 50 => net payable 100
    res4 = client.post(f"/api/v1/ra-bills/{bill_id}/deductions", json={
        "deduction_type": "Tax", "amount": 50.00
    })
    assert res4.status_code == 201
    
    # Verify via get
    res5 = client.get(f"/api/v1/ra-bills/{bill_id}")
    assert res5.json()["gross_amount"] == "150.00"
    assert res5.json()["deductions_amount"] == "50.00"
    assert res5.json()["net_payable"] == "100.00"
    
    # Check current quantity (15) and current amount (150) are returned server side
    items = res5.json()["items"]
    assert len(items) == 1
    assert items[0]["current_quantity"] == "15.000"
    assert items[0]["current_amount"] == "150.00"

# --- 5 & 6. Cumulative Calculations & Rate Snapshot ---
def test_cumulative_and_snapshot(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    
    # Bill 1 (M1) -> Approved
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"B1-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    b1_id = res.json()["id"]
    client.post(f"/api/v1/ra-bills/{b1_id}/items", json={
        "measurement_ids": [str(data["measurement_1"])]
    })
    client.post(f"/api/v1/ra-bills/{b1_id}/submit")
    client.post(f"/api/v1/ra-bills/{b1_id}/approve")
    
    # Bill 2 (Draft) -> Should not affect cumulative yet
    res2 = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"B2-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    b2_id = res2.json()["id"]
    client.post(f"/api/v1/ra-bills/{b2_id}/items", json={
        "measurement_ids": [str(data["measurement_2"])]
    })
    
    b2_get = client.get(f"/api/v1/ra-bills/{b2_id}").json()
    # M1 was qty 10 rate 10. M2 is qty 5 rate 10.
    assert b2_get["items"][0]["previous_cumulative_quantity"] == "10.000"
    assert b2_get["items"][0]["cumulative_quantity"] == "15.000"
    
    # Test rate snapshot: change BOQ rate
    bi = db.query(BoqItem).filter(BoqItem.id == data["boq_item_id"]).first()
    bi.rate = Decimal("20")
    db.commit()
    
    # Make Bill 3 with new measurement
    m3_id = uuid.uuid4()
    m3 = Measurement(id=m3_id, boq_item_id=data["boq_item_id"], measurement_date=date.today(), quantity=Decimal("2"), reference="R3", description="d3", status="Approved", created_by=data["user_id"])
    db.add(m3)
    db.commit()
    
    res3 = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"B3-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    b3_id = res3.json()["id"]
    client.post(f"/api/v1/ra-bills/{b3_id}/items", json={
        "measurement_ids": [str(m3_id)]
    })
    
    b3_get = client.get(f"/api/v1/ra-bills/{b3_id}").json()
    item = b3_get["items"][0]
    assert item["rate"] == "20.00" # new rate
    assert item["current_amount"] == "40.00" # 2 * 20
    assert item["previous_cumulative_quantity"] == "10.000" # only B1 is approved! B2 is draft
    # 10 * 10 = 100 previous amount.
    assert item["cumulative_amount"] == "140.00" # 100 + 40

# --- 7. Workflow Tests ---
def test_workflow_transitions(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"W-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    b_id = res.json()["id"]
    
    # Submit requires items, so add one first
    client.post(f"/api/v1/ra-bills/{b_id}/items", json={"measurement_ids": [str(data["measurement_1"])]})
    client.post(f"/api/v1/ra-bills/{b_id}/submit")
    assert client.get(f"/api/v1/ra-bills/{b_id}").json()["status"] == "Submitted"
    
    # Try edit submitted -> fail
    res_err = client.post(f"/api/v1/ra-bills/{b_id}/items", json={"measurement_ids": [str(data["measurement_1"])]})
    assert res_err.status_code == 403
    
    # Reject -> Draft on edit
    client.post(f"/api/v1/ra-bills/{b_id}/reject")
    assert client.get(f"/api/v1/ra-bills/{b_id}").json()["status"] == "Rejected"
    
    # Edit sets back to Draft
    res_edit = client.put(f"/api/v1/ra-bills/{b_id}", json={"remarks": "edited"})
    assert res_edit.status_code == 200
    assert client.get(f"/api/v1/ra-bills/{b_id}").json()["status"] == "Draft"

# --- 8. Bill Item Operations ---
def test_delete_bill_item(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"D-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    b_id = res.json()["id"]
    client.post(f"/api/v1/ra-bills/{b_id}/items", json={"measurement_ids": [str(data["measurement_1"])]})
    
    b_get = client.get(f"/api/v1/ra-bills/{b_id}").json()
    item_id = b_get["items"][0]["id"]
    
    # delete item
    del_res = client.delete(f"/api/v1/ra-bills/{b_id}/items/{item_id}")
    assert del_res.status_code == 204
    
    # verify measurement still exists in DB and is unlinked
    m = db.query(Measurement).filter(Measurement.id == data["measurement_1"]).first()
    assert m is not None
    
    # verify totals recalculated to 0
    b_get_after = client.get(f"/api/v1/ra-bills/{b_id}").json()
    assert b_get_after["gross_amount"] == "0.00"

# --- 9. Deductions Operations ---
def test_deductions_crud(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"DED-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    b_id = res.json()["id"]
    client.post(f"/api/v1/ra-bills/{b_id}/items", json={"measurement_ids": [str(data["measurement_1"])]}) # 100 gross
    
    d_res = client.post(f"/api/v1/ra-bills/{b_id}/deductions", json={"deduction_type": "D1", "amount": 10})
    d_id = d_res.json()["id"]
    
    assert client.get(f"/api/v1/ra-bills/{b_id}").json()["net_payable"] == "90.00"
    
    client.put(f"/api/v1/ra-bills/{b_id}/deductions/{d_id}", json={"deduction_type": "D1", "amount": 20})
    assert client.get(f"/api/v1/ra-bills/{b_id}").json()["net_payable"] == "80.00"
    
    client.delete(f"/api/v1/ra-bills/{b_id}/deductions/{d_id}")
    assert client.get(f"/api/v1/ra-bills/{b_id}").json()["net_payable"] == "100.00"

# --- 10 & 11. Audit and Transaction Rollback ---
def test_audit_logs_and_transaction(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"AUD-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    b_id = res.json()["id"]
    
    # check audit log exists for creation
    logs = db.query(AuditLog).filter(AuditLog.entity_name == "ra_bills", AuditLog.entity_id == b_id).all()
    assert any(log.action == "RA_BILL_CREATE" for log in logs)
    
    # Try failing deduction
    res_fail = client.post(f"/api/v1/ra-bills/{b_id}/deductions", json={"deduction_type": "D1", "amount": 5000}) # > gross, triggers 422
    assert res_fail.status_code == 422
    
    # Ensure NO audit log was created for the failed deduction
    d_logs = db.query(AuditLog).filter(AuditLog.entity_name == "ra_bills", AuditLog.action == "RA_BILL_DEDUCTION_CREATE").all()
    # It might find logs from other tests, so we specifically look for one with the failing amount in changes
    for log in d_logs:
        if log.entity_id == b_id and "5000" in str(log.changes):
            pytest.fail("Audit log created for failed transaction")
            

def test_cross_contract_measurement_rejection(client, db):
    data1 = setup_test_data(db)
    data2 = setup_test_data(db)
    mock_auth(client, data1["user"], "Admin")
    
    # Bill for contract 1
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data1["contract_id"]), "bill_number": f"XC-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    bill_id = res.json()["id"]
    
    # Try adding measurement from contract 2
    res2 = client.post(f"/api/v1/ra-bills/{bill_id}/items", json={
        "measurement_ids": [str(data2["measurement_1"])]
    })
    # The service validates that measurement belongs to contract, returning 422 if mismatched
    assert res2.status_code == 422

def test_wrong_boq_revision_rejection(client, db):
    data = setup_test_data(db)
    mock_auth(client, data["user"], "Admin")
    
    # Bill for contract
    res = client.post("/api/v1/ra-bills/", json={
        "contract_id": str(data["contract_id"]), "bill_number": f"WR-{uuid.uuid4()}",
        "bill_date": str(date.today()), "period_from": str(date.today()), "period_to": str(date.today())
    })
    bill_id = res.json()["id"]
    
    # Create another BOQ revision that is NOT approved (or just different)
    rev_id2 = uuid.uuid4()
    rev2 = BoqRevision(id=rev_id2, boq_id=data["boq_id"], revision_number=2, revision_date=date.today(), remarks="", status="Draft")
    db.add(rev2)
    
    # Create a BOQ item under that wrong revision
    bi_id2 = uuid.uuid4()
    bi2 = BoqItem(id=bi_id2, revision_id=rev_id2, item_code="I-2", item_number="2", description="desc", unit="m3", quantity=Decimal("100"), rate=Decimal("10"), amount=Decimal("1000"))
    db.add(bi2)
    
    # Create an approved measurement for it
    m_id_wrong = uuid.uuid4()
    m_wrong = Measurement(id=m_id_wrong, boq_item_id=bi_id2, measurement_date=date.today(), quantity=Decimal("10"), reference="R_W", description="d1", status="Approved", created_by=data["user_id"])
    db.add(m_wrong)
    db.commit()
    
    # Try adding this measurement
    res2 = client.post(f"/api/v1/ra-bills/{bill_id}/items", json={
        "measurement_ids": [str(m_id_wrong)]
    })
    assert res2.status_code == 422

# --- 12. Retain original concurrency test ---
def test_concurrent_billing_race_condition():
    db = SessionLocal()
    data = setup_test_data(db)
    
    payload = RABillCreate(
        contract_id=data["contract_id"],
        bill_number=f"RACE-1-{uuid.uuid4()}",
        bill_date=date.today(),
        period_from=date.today(),
        period_to=date.today()
    )
    bill1 = RABillService.create_bill(db, payload, data["user_id"])
    
    payload2 = RABillCreate(
        contract_id=data["contract_id"],
        bill_number=f"RACE-2-{uuid.uuid4()}",
        bill_date=date.today(),
        period_from=date.today(),
        period_to=date.today()
    )
    bill2 = RABillService.create_bill(db, payload2, data["user_id"])
    b1_id = bill1.id
    b2_id = bill2.id
    db.close()
    
    successes = []
    failures = []
    
    def worker(bill_id):
        sess = SessionLocal()
        try:
            RABillService.add_measurements(sess, bill_id, [data["measurement_1"]], data["user_id"])
            successes.append(bill_id)
        except Exception as e:
            failures.append(e)
        finally:
            sess.close()
            
    t1 = threading.Thread(target=worker, args=(b1_id,))
    t2 = threading.Thread(target=worker, args=(b2_id,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 409

