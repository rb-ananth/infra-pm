from decimal import Decimal

from app.schemas.contract import ContractCreate
from app.schemas.project import ProjectCreate


def test_project_monetary_value_is_inr_decimal():
    project = ProjectCreate(
        code="INR-TEST-001",
        name="INR Monetary Test Project",
        dept_id="00000000-0000-0000-0000-000000000001",
        pm_id="00000000-0000-0000-0000-000000000002",
        total_estimated_cost=Decimal("485000000.00"),
        start_date="2026-01-01",
        expected_completion="2026-12-31",
    )

    assert project.total_estimated_cost == Decimal("485000000.00")


def test_contract_monetary_value_is_inr_decimal():
    contract = ContractCreate(
        contract_number="INR-TEST-001",
        project_id="00000000-0000-0000-0000-000000000001",
        contractor_id="00000000-0000-0000-0000-000000000002",
        award_date="2026-01-01",
        contract_value=Decimal("1250000000.00"),
        start_date="2026-01-02",
        original_completion_date="2026-12-31",
        current_completion_date="2026-12-31",
    )

    assert contract.contract_value == Decimal("1250000000.00")