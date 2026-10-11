#!/usr/bin/env python3
import sys
import json
import argparse
import hashlib
from sqlalchemy import create_engine, MetaData, inspect
from app.core.config import settings

def get_row_fingerprint(row, pk_col):
    row_dict = dict(row._mapping)
    if pk_col in row_dict:
        del row_dict[pk_col]
    # Simple deterministic hash for fingerprinting
    serialized = json.dumps(row_dict, default=str, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Read-only test leakage verifier")
    parser.add_argument("action", choices=["snapshot", "compare"])
    parser.add_argument("--output", default="manifests/pre_test_baseline.json")
    parser.add_argument("--baseline", default="manifests/pre_test_baseline.json")
    args = parser.parse_args()

    from sqlalchemy.engine import make_url
    db_url_str = str(settings.DATABASE_URL)
    db_url = make_url(db_url_str)

    if db_url.database not in {"infra_pm_test_db", "infra_pm_golden_test_db"}:
        sys.exit(f"CRITICAL: Leakage verifier must only run against allowed test DBs. Rejected: {db_url.database}")

    # Enforce read-only at PostgreSQL connection level
    engine = create_engine(db_url_str).execution_options(postgresql_readonly=True)
    metadata = MetaData()
    metadata.reflect(bind=engine)

    # Core operational + foundational tables
    target_tables = [
        "roles", "users", "departments", "contractors",
        "projects", "user_project_assignments", "contracts",
        "boqs", "boq_revisions", "boq_items", "measurements",
        "ra_bills", "ra_bill_items", "ra_bill_measurements", "ra_bill_deductions",
        "evm_baselines", "evm_baseline_periods", "eot_applications",
        "documents", "document_chunks", "document_facts", "audit_logs"
    ]

    current_state = {}
    with engine.connect() as conn:
        for table_name in target_tables:
            if table_name not in metadata.tables:
                continue
            table = metadata.tables[table_name]
            pk_col = table.primary_key.columns.keys()[0]

            rows = conn.execute(table.select()).fetchall()
            current_state[table_name] = {
                str(getattr(row, pk_col)): get_row_fingerprint(row, pk_col)
                for row in rows
            }

    if args.action == "snapshot":
        import os
        os.makedirs("manifests", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(current_state, f, indent=2)
        print(f"Snapshot saved to {args.output}")

    elif args.action == "compare":
        try:
            with open(args.baseline, "r") as f:
                baseline = json.load(f)
        except FileNotFoundError:
            sys.exit(f"Baseline {args.baseline} not found.")

        has_leaks = False
        print(f"Comparing current state of {engine.url.database} against {args.baseline}...\n")
        for table in target_tables:
            base_records = baseline.get(table, {})
            curr_records = current_state.get(table, {})

            base_ids = set(base_records.keys())
            curr_ids = set(curr_records.keys())

            added = curr_ids - base_ids
            deleted = base_ids - curr_ids

            modified = []
            for shared_id in base_ids.intersection(curr_ids):
                if base_records[shared_id] != curr_records[shared_id]:
                    modified.append(shared_id)

            if added or deleted or modified:
                has_leaks = True
                print(f"--- Table: {table} ---")
                if added: print(f"  + Added: {len(added)} records")
                if deleted: print(f"  - Deleted: {len(deleted)} records")
                if modified: print(f"  ~ Modified: {len(modified)} records")

        if not has_leaks:
            print("No test data leakage detected! Database matches baseline.")
        else:
            print("\nWARNING: Residual artifacts detected.")

if __name__ == "__main__":
    main()
