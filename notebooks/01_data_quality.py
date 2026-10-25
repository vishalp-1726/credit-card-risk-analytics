# %% [markdown]
# # 01 - Data quality: size, period, issues in the raw files, and checks after cleaning
# Needs the history loaded (src.load_data --history).

# %% setup
import sys
from pathlib import Path

# make src importable from notebooks/ (VS Code) and from the project folder (terminal)
project = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(project))

import pandas as pd

from src.config import RAW
from src.db import query
from src.dq_checks import run_checks, show

# %% 1. Rows in each table
for table in ["customers", "cards", "card_statements", "collections_queue", "collections_calls", "recoveries"]:
    n = query(f"select count(*) as n from {table}").n[0]
    print(f"{table:<20} {n:>12,}")

# %% 2. Period covered, and how big the book is
print(query("""select min(statement_month) as first_month, max(statement_month) as last_month,
                      count(distinct card_id) as cards
               from card_statements"""))
print(query("""select statement_month,
                      count(*) as cards_with_statement,
                      count(*) filter (where carries_balance) as cards_carrying_balance
               from v_statements
               where statement_month in ('2024-08', '2025-08', '2026-08')
               group by 1 order by 1"""))

# %% 3. What 02_clean.sql fixed: compare the raw files with the cleaned tables
raw_statements = pd.read_csv(RAW / "card_statements.csv", usecols=["card_id", "statement_month"])
print("duplicate statement rows in the file:", raw_statements.duplicated().sum())

raw_cards = pd.read_csv(RAW / "cards.csv")
print("channel spellings in the file:", raw_cards.channel.nunique(),
      "-> after cleaning:", query("select count(distinct channel) as n from cards").n[0])

raw_customers = pd.read_csv(RAW / "customers.csv", usecols=["employment_start_date", "income_type"])
year_3026 = raw_customers[raw_customers.employment_start_date.str.startswith("3026")]
print("employment date in year 3026:", len(year_3026), "rows ->", year_3026.income_type.value_counts().to_dict())

# %% 4. Missing values that matter
print(query("""select count(*) filter (where bureau_score is null) as bureau_missing,
                      count(*) filter (where ext_score_1 is null) as ext1_missing,
                      count(*) filter (where occupation is null) as occupation_missing,
                      count(*) as customers
               from customers"""))

# %% 5. Data-quality checks: every ERROR check must be 0 before the numbers are used
show(run_checks("notebook-01"))
