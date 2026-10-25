"""Load the source extracts into PostgreSQL, then run the cleaning, views and report SQL.

Usage:
    uv run python -m src.load_data --history          # history in data/raw (first load)
    uv run python -m src.load_data --month 2026-09    # one month from data/landing
The monthly run normally goes through src.monthly_refresh (load + checks + export).

Files already in load_log are skipped.
"""
import argparse
import csv
import time

import psycopg

from src.config import LANDING, RAW, SQL
from src.db import PG_URL, copy_csv, run_sql_file

FILES = ["customers", "cards", "card_statements", "collections_queue", "collections_calls", "recoveries"]

def already_loaded(label):
    with psycopg.connect(PG_URL) as con:
        row = con.execute("select 1 from load_log where file_name = %s", (label,)).fetchone()
        return row is not None

def copy_new_customers(path, columns):
    """Customers who open another card are not sent again in that mnth's file.
    Load into a staging table, then insert only the customer_ids not in the table yet."""
    with psycopg.connect(PG_URL, autocommit=True) as con:
        con.execute("drop table if exists customers_staging; create table customers_staging (like customers)")
    in_file = copy_csv(path, "customers_staging", columns)
    cols = ", ".join(columns)
    with psycopg.connect(PG_URL, autocommit=True) as con:
        added = con.execute(f"insert into customers ({cols}) select {cols} from customers_staging "
                                "on conflict (customer_id) do nothing").rowcount
        con.execute("drop table customers_staging")
    if added < in_file:
        print(f" {in_file - added:,} customers in the file were already in the table (they opened another card)")
    return added

def load_file(path, table, label):
    """Load one file. Returns the rows loaded, or 0 if it was already loaded."""
    if already_loaded(label):
        return 0
    with open(path, encoding="utf-8") as f:
        columns = next(csv.reader(f))   # the header row
    start = time.time()
    if table == "customers":
        rows = copy_new_customers(path, columns)
    else:
        rows = copy_csv(path, table, columns)
    with psycopg.connect(PG_URL, autocommit=True) as con:
        con.execute("insert into load_log (file_name, rows_loaded) values (%s, %s)", (label, rows))
    print(f" loaded {rows:>10,} rows into {table:<10} ({time.time() - start:.0f}s)")    
    return rows

def load_history():
    run_sql_file(SQL / "01_create_tables.sql")
    for name in FILES:
        load_file(RAW / f"{name}.csv", name, f"{name}.csv")

def load_month(month):
    """Load one month from data/landing/<month>. Returns {table: rows loaded}."""
    folder = LANDING / month
    if not folder.exists():
        raise SystemExit(f"no folder {folder}")
    rows = {}
    for name in FILES:
        rows[name] = load_file(folder / f"{name}.csv", name, f"{month}/{name}.csv")
    return rows

def refresh():
    """ Clean the data and rebuild the views and report tables. Runs after every load.""" 
    for name in ["02_clean.sql", "03_views.sql", "04_reports.sql"]:
        start = time.time()
        run_sql_file(SQL / name)
        print(f" ran{name} ({time.time() - start:.0f}s)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--month")
    args = parser.parse_args()

    if args.history:
        load_history()
    if args.month:
        load_month(args.month)
    refresh()
