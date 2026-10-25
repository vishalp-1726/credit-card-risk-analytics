"""Helpers to read from and write to PostgreSQL."""
import io

import pandas as pd
import psycopg
from sqlalchemy import create_engine, text
from src.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
# psycopg needs the same login without "+psycopg"
PG_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")

def query(sql):
    """Run a select and return the results as a DataFrame."""
    with engine.connect() as con:
        return pd.read_sql(text(sql), con)

def run_sql_file(path):
    """Run all the statements in a .sql file."""
    with psycopg.connect(PG_URL, autocommit=True) as con:
        con.execute(open(path, encoding="utf-8").read())

def copy_csv(path, table, columns):
    """Load a CSV file into a table with COPY (much faster than row-by-row inserts).
    Returns the number of rows loaded."""
    sql = f"copy {table} ({', '.join(columns)}) from stdin with (format csv, header true)"
    with psycopg.connect(PG_URL) as con, con.cursor() as cur:
        with cur.copy(sql) as cp, open(path, "rb") as f:
            while True:
                chunk = f.read(1_000_000)       # 1 MB at a time
                if not chunk:
                    break
                cp.write(chunk)
        return cur.rowcount

def write_table(df, table):
    """Save a DataFrame as a table, replacing the old one. Also uses COPY, so big tables are quick."""
    df.head(0).to_sql(table, engine, if_exists="replace", index = False)        # creates the empty table
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    with psycopg.connect(PG_URL) as con, con.cursor() as cur:
        with cur.copy(f"copy {table} from stdin with (format csv)") as cp:
            cp.write(buf.getvalue())
