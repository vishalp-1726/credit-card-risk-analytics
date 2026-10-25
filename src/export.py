"""Exports for the business:
  - CSVs of the report tables for the Tableau Public dashboard (totals only, no account rows)
  - one Excel file for Collections and Credit Policy: this month's call list and the approval trade-off

Usage: uv run python -m src.export   (needs the report tables from notebooks 02-05)
"""
import pandas as pd

from src.collections_list import build_call_list
from src.config import PROCESSED
from src.db import query

# dashboard tables: totals per month / segment / bucket only, no card IDs or personal data
TABLES = [
    "report_monthly_kpi", "report_book_segments", "report_q1_contribution", "report_existing_book_util",
    "report_roll_rates", "report_vintage", "report_segments", "report_cobrand_gap", "report_cobrand_same_score",
    "report_call_effect", "report_collections_policy", "report_collections_value", "report_collections_backtest",
    "report_collections_range", "report_policy_curve", "report_swap_set", "report_policy_tradeoff",
]


def export_csv():
    out = PROCESSED / "dashboard"
    out.mkdir(parents=True, exist_ok=True)
    for t in TABLES:
        query(f"select * from {t}").to_csv(out / f"{t}.csv", index=False)
    print(f"  wrote {len(TABLES)} CSV files to {out}")


def export_excel():
    # the call list has card IDs: Excel only (data/ is git-ignored), never Tableau Public
    # build_call_list() ranks the latest queue month, so each new month gets its own list
    path = PROCESSED / "handoff_collections_credit_policy.xlsx"
    with pd.ExcelWriter(path) as xl:
        build_call_list().to_excel(xl, sheet_name="call_list", index=False)
        query("select * from report_policy_tradeoff order by approval_target").to_excel(
            xl, sheet_name="approval_tradeoff", index=False)
    print(f"  wrote {path}")


if __name__ == "__main__":
    export_csv()
    export_excel()
