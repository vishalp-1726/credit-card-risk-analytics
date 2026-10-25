"""Monthly refresh: everything that has to happen when a new month's extract lands.

Usage:
    uv run python -m src.monthly_refresh
    uv run python -m src.monthly_refresh --month 2026-09      # re-run one month, e.g. after a fix
    uv run python -m src.monthly_refresh --as-of 2026-11-20   # run as if today were another date (testing)

Rules (months come from today's date and the landing folders, never hard-coded; months YYYY-MM, dates YYYY-MM-DD):
  - last month's data must land in data/landing/<YYYY-MM> by the 15th of this month (settings.yaml)
  - every month that has landed and is not loaded yet gets processed, oldest first
  - the current month is never loaded: it is not finished yet

For each month: load -> clean -> rebuild reports -> data checks -> export -> summary.
A failed ERROR check stops the run before the export, so Tableau and Collections never get bad numbers.
Each step is logged in refresh_log.
"""
import argparse

import pandas as pd
import psycopg

from src.config import LANDING, SETTINGS
from src.db import PG_URL, query
from src.dq_checks import run_checks, show
from src.export import export_csv, export_excel
from src.load_data import already_loaded, load_month, refresh


def log(month, step, status, detail=""):
    with psycopg.connect(PG_URL, autocommit=True) as con:
        con.execute("insert into refresh_log (run_month, step, status, detail) values (%s, %s, %s, %s)",
                    (month, step, status, detail))


def months_waiting(today):
    """Months in data/landing that are not loaded yet, oldest first (the current month is skipped)."""
    this_month = str(today.to_period("M"))
    waiting = []
    for folder in sorted(LANDING.iterdir()):
        if not folder.is_dir():                     # skip files such as .DS_Store
            continue
        month = folder.name
        if already_loaded(f"{month}/card_statements.csv"):
            continue
        if month >= this_month:
            print(f"  skip {month}: this month is not finished yet")
            continue
        waiting.append(month)
    return waiting


def process(month):
    print(f"\n--- {month} ---")
    print("load, clean, rebuild reports")
    rows = load_month(month)
    refresh()
    log(month, "load", "OK", f"{sum(rows.values())} rows")

    print("data checks")
    results = run_checks(month)
    show(results)
    failed = [name for name, level, bad_rows in results if level == "ERROR" and bad_rows > 0]
    if failed:
        log(month, "checks", "FAILED", "; ".join(failed))
        raise SystemExit(f"STOPPED: data check failed for {month}. Nothing was exported.")
    log(month, "checks", "OK")

    print("export")
    export_csv()
    export_excel()
    log(month, "export", "OK")

    # a short summary for the team
    kpi = query(f"select * from report_monthly_kpi where statement_month = '{month}'").iloc[0]
    last_month = query(f"""select dpd30_rate from report_monthly_kpi
                           where statement_month = '{pd.Period(month, "M") - 1}'""").dpd30_rate[0]
    queue = query(f"select count(*) as n from collections_queue where month = '{month}'").n[0]
    calls = query("select count(*) as n from report_call_list").n[0]
    new_cards = query(f"select count(*) as n from cards where open_month = '{month}'").n[0]
    print(f"summary: 30+ DPD rate {kpi.dpd30_rate:.2%} (last month {last_month:.2%}), "
          f"{int(kpi.dpd30_accounts):,} of {int(kpi.active_accounts):,} accounts, "
          f"{int(kpi.write_offs)} write-offs, {new_cards:,} new cards, call list {calls:,} of {queue:,} accounts")
    log(month, "done", "OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--month")
    parser.add_argument("--as-of")
    args = parser.parse_args()

    today = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.today().normalize()
    due_month = str(today.to_period("M") - 1)                       # last month
    deadline = today.replace(day=SETTINGS["refresh"]["landing_deadline_day"])
    print(f"monthly refresh on {today:%Y-%m-%d}: {due_month} data is due by {deadline:%Y-%m-%d}")

    # 1. is last month's data here?
    if (LANDING / due_month).exists():
        status = "OK"
    elif today <= deadline:
        status = "WAITING"                                           # not due yet
    else:
        status = "LATE"
    print(f"  landing check: {status}")
    log(due_month, "landing", status)

    # 2. process every month that is waiting (a late run catches up on all of them)
    months = [args.month] if args.month else months_waiting(today)
    if not months:
        print("  nothing new to load")
    for month in months:
        process(month)

    # 3. a non-zero exit when data is late, so a scheduler (cron, Airflow) can alert the team
    if status == "LATE":
        raise SystemExit(f"ALERT: {due_month} data has not landed and was due by {deadline:%Y-%m-%d}")
