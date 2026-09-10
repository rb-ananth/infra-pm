from datetime import date, datetime
from decimal import Decimal

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.contractor import Contractor
from app.models.department import Department
from app.models.project import Project
from app.models.role import Role
from app.models.user import User


ROLES = ["Admin", "Project Manager", "Engineer", "Billing Engineer", "Viewer"]

USERS = [
    ("admin@infrapm.gov", "Admin", "Admin@123"),
    ("pm@infrapm.gov", "Project Manager", "PM@123"),
    ("eng@infrapm.gov", "Engineer", "Eng@123"),
    ("billing@infrapm.gov", "Billing Engineer", "Bill@123"),
    ("viewer@infrapm.gov", "Viewer", "View@123"),
]


def run_seed():
    db = SessionLocal()
    try:
        role_map = {}
        for role_name in ROLES:
            role = db.query(Role).filter(Role.name == role_name).first()
            if not role:
                role = Role(name=role_name)
                db.add(role)
                db.flush()
            role_map[role_name] = role.id

        for email, role_name, password in USERS:
            if not db.query(User).filter(User.email == email).first():
                db.add(
                    User(
                        email=email,
                        password_hash=get_password_hash(password),
                        role_id=role_map[role_name],
                        is_active=True,
                    )
                )
        db.flush()

        departments = [
            ("PWD", "Public Works Department"),
            ("NHAI", "National Highways Authority"),
            ("GSIDC", "Infrastructure Development Corporation"),
        ]
        department_map = {}
        for code, name in departments:
            department = db.query(Department).filter(Department.code == code).first()
            if not department:
                department = Department(code=code, name=name, is_active=True)
                db.add(department)
                db.flush()
            department_map[code] = department.id

        contractors = [
            ("CTR-001", "ABC Infrastructure Pvt Ltd"),
            ("CTR-002", "National Buildcon Ltd"),
            ("CTR-003", "Western Engineering Works"),
        ]
        for registration_number, name in contractors:
            if not db.query(Contractor).filter(Contractor.registration_number == registration_number).first():
                db.add(Contractor(registration_number=registration_number, name=name, status="Active"))

        db.flush()

        pm = db.query(User).filter(User.email == "pm@infrapm.gov").first()
        if not db.query(Project).filter(Project.code == "PWD-2026-001").first():
            db.add(
                Project(
                    code="PWD-2026-001",
                    name="District Hospital Infrastructure Upgrade",
                    dept_id=department_map["PWD"],
                    pm_id=pm.id,
                    status="Execution",
                    total_estimated_cost=Decimal("48.50"),
                    start_date=date(2026, 4, 1),
                    expected_completion=date(2027, 3, 31),
                )
            )
        if not db.query(Project).filter(Project.code == "NHAI-2026-001").first():
            db.add(
                Project(
                    code="NHAI-2026-001",
                    name="Highway Improvement Package",
                    dept_id=department_map["NHAI"],
                    pm_id=pm.id,
                    status="Proposed",
                    total_estimated_cost=Decimal("125.00"),
                    start_date=date(2026, 10, 1),
                    expected_completion=date(2028, 3, 31),
                )
            )

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
