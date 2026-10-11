
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(str(settings.DATABASE_URL))
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()

import uuid
from datetime import date, timedelta
from app.models.contract import Contract
from app.models.eot import EOTApplication

def make_user(db_session, role):
    from app.models.user import User
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        password_hash="x",
        role_id=role.id,
        is_active=True
    )
    db_session.add(user)
    db_session.flush()
    return user

def make_role(db_session, role_name):
    from app.models.role import Role
    return db_session.query(Role).filter(Role.name == role_name).first()

def setup_project_contract(db_session, user, create_assignment=True):
    from app.models.project import Project
    from app.models.department import Department
    from app.models.contractor import Contractor
    from app.models.user import UserProjectAssignment
    from decimal import Decimal

    dept = Department(code=f"D-{str(uuid.uuid4())[:4]}", name="Dept")
    db_session.add(dept)
    db_session.flush()

    proj = Project(
        code=f"PRJ-{str(uuid.uuid4())[:6]}", name="P", dept_id=dept.id, pm_id=user.id,
        status="Active", total_estimated_cost=Decimal("500"),
        start_date=date(2026,1,1), expected_completion=date(2026,12,31)
    )
    db_session.add(proj)
    db_session.flush()

    if create_assignment:
        db_session.add(UserProjectAssignment(user_id=user.id, project_id=proj.id))
        db_session.flush()

    cont = Contractor(registration_number=f"R-{str(uuid.uuid4())[:4]}", name="C", status="Active")
    db_session.add(cont)
    db_session.flush()

    contract = Contract(
        contract_number=f"CON-{str(uuid.uuid4())[:4]}", project_id=proj.id, contractor_id=cont.id,
        award_date=date(2026,1,1), start_date=date(2026,1,1),
        original_completion_date=date(2026,12,31), current_completion_date=date(2026,12,31),
        contract_value=Decimal("100"), status="Active"
    )
    db_session.add(contract)
    db_session.flush()
    return proj, contract

def mock_auth(client_obj, user, db_session):
    from app.api.deps import get_current_user, get_db
    def _get_user(): return user
    def _get_db(): yield db_session
    from app.main import app
    app.dependency_overrides[get_current_user] = _get_user
    app.dependency_overrides[get_db] = _get_db

def test_eot_lifecycle_and_completion_date_update(db_session, client):
    pm = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_reviewer = make_user(db_session, make_role(db_session, "Project Manager"))
    proj, contract = setup_project_contract(db_session, pm)
    from app.models.user import UserProjectAssignment
    db_session.add(UserProjectAssignment(user_id=pm_reviewer.id, project_id=proj.id))
    db_session.flush()

    mock_auth(client, pm, db_session)

    # 1. Create Draft
    resp = client.post("/api/v1/eot/", json={
        "contract_id": str(contract.id),
        "application_number": "EOT-01",
        "event_date": "2026-06-01",
        "notice_date": "2026-06-05",
        "cause_of_delay": "Heavy Rain",
        "claimed_days": 10
    })
    assert resp.status_code == 201
    eot_id = resp.json()["id"]
    assert resp.json()["status"] == "Draft"

    # 2. Update Draft
    resp = client.put(f"/api/v1/eot/{eot_id}", json={"claimed_days": 15})
    assert resp.status_code == 200
    assert resp.json()["claimed_days"] == 15

    # 3. Submit
    resp = client.post(f"/api/v1/eot/{eot_id}/submit")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Submitted"

    # 4. Under Review
    mock_auth(client, pm_reviewer, db_session)
    resp = client.post(f"/api/v1/eot/{eot_id}/review")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Under Review"

    # 5. Approve
    resp = client.post(f"/api/v1/eot/{eot_id}/approve", json={"approved_days": 12, "decision_reason": "Agreed"})
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "Approved"
    assert data["approved_days"] == 12
    assert data["previous_completion_date"] == "2026-12-31"
    assert data["revised_completion_date"] == "2027-01-12"

    # Verify DB Contract Update
    assert contract.original_completion_date == date(2026, 12, 31)

def test_creator_cannot_approve_own_application(db_session, client):
    pm = make_user(db_session, make_role(db_session, "Project Manager"))
    proj, contract = setup_project_contract(db_session, pm)

    eot_app = EOTApplication(
        contract_id=contract.id, application_number="EOT-02", event_date=date(2026,6,1),
        notice_date=date(2026,6,5), cause_of_delay="X", claimed_days=5, status="Under Review", created_by=pm.id
    )
    db_session.add(eot_app)
    db_session.flush()

    mock_auth(client, pm, db_session)
    resp = client.post(f"/api/v1/eot/{eot_app.id}/approve", json={"approved_days": 5, "decision_reason": "Self"})
    assert resp.status_code == 403
    assert "Cannot approve your own" in resp.json()["detail"]

def test_cross_project_rejection(db_session, client):
    pm_a = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_b = make_user(db_session, make_role(db_session, "Project Manager"))

    proj_a, contract_a = setup_project_contract(db_session, pm_a)
    proj_b, contract_b = setup_project_contract(db_session, pm_b)

    mock_auth(client, pm_a, db_session)

    resp = client.post("/api/v1/eot/", json={
        "contract_id": str(contract_b.id),
        "application_number": "EOT-XX",
        "event_date": "2026-06-01",
        "notice_date": "2026-06-05",
        "cause_of_delay": "Cross",
        "claimed_days": 10
    })
    assert resp.status_code == 403

def test_duplicate_application_number(db_session, client):
    pm = make_user(db_session, make_role(db_session, "Project Manager"))
    proj, contract = setup_project_contract(db_session, pm)

    eot_app = EOTApplication(
        contract_id=contract.id, application_number="EOT-DUP", event_date=date(2026,6,1),
        notice_date=date(2026,6,5), cause_of_delay="X", claimed_days=5, status="Draft", created_by=pm.id
    )
    db_session.add(eot_app)
    db_session.flush()

    mock_auth(client, pm, db_session)
    resp = client.post("/api/v1/eot/", json={
        "contract_id": str(contract.id),
        "application_number": "EOT-DUP",
        "event_date": "2026-06-01",
        "notice_date": "2026-06-05",
        "cause_of_delay": "Y",
        "claimed_days": 10
    })
    assert resp.status_code == 409

def test_double_approve_prevented(client):
    # Uses concurrent requests to prove FOR UPDATE locking prevents race conditions
    from app.core.database import SessionLocal
    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models.eot import EOTApplication
    from app.models.user import UserProjectAssignment
    import uuid
    import concurrent.futures

    db = SessionLocal()
    pm = make_user(db, make_role(db, "Project Manager"))
    pm_reviewer = make_user(db, make_role(db, "Project Manager"))
    proj, contract = setup_project_contract(db, pm)
    db.add(UserProjectAssignment(user_id=pm_reviewer.id, project_id=proj.id))

    eot_app = EOTApplication(
        contract_id=contract.id, application_number=f"EOT-CONC-{uuid.uuid4().hex[:8]}", event_date=date(2026,6,1),
        notice_date=date(2026,6,5), cause_of_delay="X", claimed_days=5, status="Under Review", created_by=pm.id
    )
    db.add(eot_app)
    db.commit()
    eot_id = eot_app.id

    try:
        from app.api.deps import get_current_user, get_db
        def _get_user(): return pm_reviewer
        from app.main import app
        app.dependency_overrides[get_current_user] = _get_user
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]

        def approve_req():
            return client.post(f"/api/v1/eot/{eot_id}/approve", json={"approved_days": 5, "decision_reason": "Conc"})

        # Fire 3 concurrent approval requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(approve_req) for _ in range(3)]
            results = [f.result() for f in futures]

        status_codes = [r.status_code for r in results]

        # Exactly one should succeed (200), the others should be rejected (400) because of FOR UPDATE and status check
        assert status_codes.count(200) == 1
        assert status_codes.count(422) == 2

    finally:
        from app.models.audit_log import AuditLog
        db.query(AuditLog).filter_by(entity_id=eot_id).delete()
        db.query(type(eot_app)).filter_by(id=eot_app.id).delete(synchronize_session=False)
        db.query(type(contract)).filter_by(id=contract.id).delete(synchronize_session=False)
        db.query(type(proj)).filter_by(id=proj.id).delete(synchronize_session=False)
        db.query(type(pm)).filter_by(id=pm.id).delete(synchronize_session=False)
        db.query(type(pm_reviewer)).filter_by(id=pm_reviewer.id).delete(synchronize_session=False)
        db.commit()
        db.close()
        app.dependency_overrides.clear()

def test_draft_editing_by_non_creator_fails(db_session, client):
    pm1 = make_user(db_session, make_role(db_session, "Project Manager"))
    pm2 = make_user(db_session, make_role(db_session, "Project Manager"))
    proj, contract = setup_project_contract(db_session, pm1)

    # pm2 is also assigned to the same project
    from app.models.user import UserProjectAssignment
    db_session.add(UserProjectAssignment(user_id=pm2.id, project_id=proj.id))
    db_session.flush()

    eot_app = EOTApplication(
        contract_id=contract.id, application_number="EOT-04", event_date=date(2026,6,1),
        notice_date=date(2026,6,5), cause_of_delay="X", claimed_days=5, status="Draft", created_by=pm1.id
    )
    db_session.add(eot_app)
    db_session.flush()

    mock_auth(client, pm2, db_session)
    resp = client.put(f"/api/v1/eot/{eot_app.id}", json={"claimed_days": 10})
    assert resp.status_code == 403
    assert "Only the creator" in resp.json()["detail"]

def test_rollback_on_approval_failure(client, monkeypatch):
    # Use a completely fresh, isolated session to verify request-scoped behavior on the test DB
    from app.core.database import SessionLocal
    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models.contract import Contract
    from app.models.eot import EOTApplication
    from app.models.user import UserProjectAssignment
    import uuid
    from sqlalchemy import event

    db = SessionLocal()
    tracked = []
    def on_flush(sess, flush_context):
        for obj in sess.new:
            tracked.append((type(obj), getattr(obj, "id", None)))
    event.listen(db, "after_flush", on_flush)

    try:
        pm = make_user(db, make_role(db, "Project Manager"))
        pm_reviewer = make_user(db, make_role(db, "Project Manager"))
        proj, contract = setup_project_contract(db, pm)

        db.add(UserProjectAssignment(user_id=pm_reviewer.id, project_id=proj.id))

        eot_app = EOTApplication(
            contract_id=contract.id, application_number=f"EOT-FAIL-{uuid.uuid4().hex[:8]}", event_date=date(2026,6,1),
            notice_date=date(2026,6,5), cause_of_delay="X", claimed_days=5, status="Under Review", created_by=pm.id
        )
        db.add(eot_app)
        db.commit()

        eot_id = eot_app.id
        contract_id = contract.id

        def mock_add_audit_log(*args, **kwargs):
            raise ValueError("Simulated DB failure during audit logging")
        monkeypatch.setattr("app.services.eot_service.add_audit_log", mock_add_audit_log)

        def _get_user():
            return pm_reviewer

        app.dependency_overrides[get_current_user] = _get_user
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]

        try:
            resp = client.post(f"/api/v1/eot/{eot_id}/approve", json={"approved_days": 5, "decision_reason": "Yes"})
            assert resp.status_code == 500
        except ValueError:
            pass

        # Verify using a fresh session AFTER the request ends
        db_fresh = SessionLocal()
        try:
            fresh_app = db_fresh.query(EOTApplication).filter_by(id=eot_id).first()
            fresh_contract = db_fresh.query(Contract).filter_by(id=contract_id).first()

            assert fresh_app.status == "Under Review"
            assert fresh_app.approved_days is None
            assert fresh_contract.current_completion_date == date(2026, 12, 31)

            from app.models.audit_log import AuditLog
            audits = db_fresh.query(AuditLog).filter_by(entity_name="EOTApplication", entity_id=eot_id).all()
            assert len(audits) == 0
        finally:
            db_fresh.close()

    finally:
        event.remove(db, "after_flush", on_flush)
        try:
            db.rollback()
        except Exception:
            pass

        for model, pk in reversed(tracked):
            if pk:
                db.query(model).filter(model.id == pk).delete(synchronize_session=False)
        db.commit()
        db.close()
        app.dependency_overrides.clear()


def test_sequential_and_edge_case_approvals(db_session, client):
    # Tests sequential, zero-day, and negative-day approvals
    pm = make_user(db_session, make_role(db_session, "Project Manager"))
    pm_reviewer = make_user(db_session, make_role(db_session, "Project Manager"))
    proj, contract = setup_project_contract(db_session, pm)

    from app.models.user import UserProjectAssignment
    db_session.add(UserProjectAssignment(user_id=pm_reviewer.id, project_id=proj.id))
    db_session.flush()

    # 1. Zero day approval
    app1 = EOTApplication(
        contract_id=contract.id, application_number="EOT-0-DAY", event_date=date(2026,6,1),
        notice_date=date(2026,6,5), cause_of_delay="X", claimed_days=5, status="Under Review", created_by=pm.id
    )
    db_session.add(app1)

    # 2. Sequential approval
    app2 = EOTApplication(
        contract_id=contract.id, application_number="EOT-SEQ", event_date=date(2026,7,1),
        notice_date=date(2026,7,5), cause_of_delay="Y", claimed_days=10, status="Under Review", created_by=pm.id
    )
    db_session.add(app2)
    db_session.flush()

    mock_auth(client, pm_reviewer, db_session)

    # Zero day
    resp1 = client.post(f"/api/v1/eot/{app1.id}/approve", json={"approved_days": 0, "decision_reason": "Zero"})
    assert resp1.status_code == 200
    assert resp1.json()["approved_days"] == 0
    assert resp1.json()["previous_completion_date"] == "2026-12-31"
    assert resp1.json()["revised_completion_date"] == "2026-12-31"

    # Sequential
    resp2 = client.post(f"/api/v1/eot/{app2.id}/approve", json={"approved_days": 10, "decision_reason": "Ten"})
    assert resp2.status_code == 200
    assert resp2.json()["previous_completion_date"] == "2026-12-31"
    assert resp2.json()["revised_completion_date"] == "2027-01-10"

    # Negative days (should fail HTTP validation or DB constraint)
    resp3 = client.post(f"/api/v1/eot/{app2.id}/approve", json={"approved_days": -5, "decision_reason": "Negative"})
    assert resp3.status_code == 422
