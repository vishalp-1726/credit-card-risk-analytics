"""Data-quality checks. Each query counts bad rows, so 0 = pass.
ERROR: must be 0 before the numbers are used. WARN: known issue, reported only.

Usage: uv run python -m src.dq_checks
"""
import psycopg

from src.db import PG_URL

CHECKS = [
    # (name, level, query that counts bad rows)
    ("statements: duplicate card + month", "ERROR",
     "select count(*) - count(distinct (card_id, statement_month)) from card_statements"),
    ("statements: card not in cards table", "ERROR",
     "select count(*) from card_statements s left join cards c using (card_id) where c.card_id is null"),
    ("statements: negative dpd_days", "ERROR",
     "select count(*) from card_statements where dpd_days < 0"),
    ("statements: late but paid the full minimum", "ERROR",
     "select count(*) from card_statements where dpd_days > 0 and account_status = 'ACTIVE' and payment >= min_due"),
    ("statements: negative balance (credit balance)", "WARN",
     "select count(*) from card_statements where balance < 0"),
    ("statements: min_due missing", "WARN",
     "select count(*) from card_statements where min_due is null"),
    ("cards: unknown channel after cleaning", "ERROR",
     "select count(*) from cards where channel not in ('Branch', 'DSA', 'Digital', 'Fintech Co-brand')"),
    ("customers: employment date in the future", "ERROR",
     "select count(*) from customers where employment_start_date > current_date"),
    ("customers: bureau score missing", "WARN",
     "select count(*) from customers where bureau_score is null"),
    ("calls: timestamp could not be parsed", "ERROR",
     "select count(*) from collections_calls where call_time is null"),
    ("calls: missing outcome (set to UNKNOWN)", "WARN",
     "select count(*) from collections_calls where call_outcome = 'UNKNOWN'"),
    ("queue: cell not RANKED / RANDOM_TEST / NOT_CALLED", "ERROR",
     "select count(*) from collections_queue where assigned_cell not in ('RANKED', 'RANDOM_TEST', 'NOT_CALLED')"),
]


def run_checks(run_month="adhoc"):
    """Run every check, save the results in dq_results, and return them."""
    results = []
    with psycopg.connect(PG_URL, autocommit=True) as con:
        for name, level, sql in CHECKS:
            bad_rows = con.execute(sql).fetchone()[0]
            con.execute("insert into dq_results (run_month, check_name, severity, failed_rows) values (%s, %s, %s, %s)",
                        (run_month, name, level, bad_rows))
            results.append((name, level, bad_rows))
    return results


def show(results):
    for name, level, bad_rows in results:
        if bad_rows == 0:
            status = "PASS"
        elif level == "ERROR":
            status = "FAIL"
        else:
            status = "WARN"
        print(f"  [{status}] {name:<50} {bad_rows:>8,}")


if __name__ == "__main__":
    results = run_checks()
    show(results)
    if any(level == "ERROR" and bad_rows > 0 for name, level, bad_rows in results):
        raise SystemExit("data-quality ERROR: fix it before going on")
