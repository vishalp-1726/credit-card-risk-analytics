-- 01_create_tables.sql
-- One table per source extract, plus the load, data-check and refresh logs.
-- Safe to re-run (if not exists).

create table if not exists customers (
    customer_id            bigint primary key,
    gender                 text,
    date_of_birth          date,
    employment_start_date  date,        -- year 3026 = dummy for 'not working', set to null in 02_clean.sql
    income_type            text,
    education              text,
    family_status          text,
    occupation             text,
    annual_income          numeric,
    bureau_score           int,         -- 300-900
    ext_score_1            numeric,     -- external scores, 0-1, often missing
    ext_score_3            numeric,
    bureau_active_loans    int,
    region_rating          int,
    city                   text,
    state                  text,
    city_tier              text,
    owns_car               text,
    owns_home              text,
    children               int,
    family_members         numeric,
    has_email              int
);

create table if not exists cards (
    card_id               bigint primary key,
    customer_id           bigint references customers (customer_id),
    open_month            text,         -- 'YYYY-MM'
    opened_before_window  boolean,      -- opened before Nov-2018, when the data starts
    initial_credit_limit  numeric,
    channel               text          -- inconsistent spellings, standardised in 02_clean.sql
);

-- card x month, ~3.5M rows
create table if not exists card_statements (
    card_id           bigint,
    statement_month   text,             -- 'YYYY-MM'
    credit_limit      numeric,
    balance           numeric,
    cash_withdrawals  numeric,
    pos_spend         numeric,
    other_spend       numeric,
    total_spend       numeric,
    transactions      numeric,
    min_due           numeric,
    payment           numeric,
    overdue_amount    numeric,
    dpd_days          int,              -- days past due
    account_status    text              -- ACTIVE / CLOSED / CHARGED_OFF
);

-- delinquent accounts per month and the collections cell each was assigned to
create table if not exists collections_queue (
    month             text,
    card_id           bigint,
    bucket_at_start   int,              -- 1 = 1-29 DPD, 2 = 30-59 ... 6 = 150-179
    overdue_amount    numeric,
    balance           numeric,
    assigned_cell     text              -- RANKED / RANDOM_TEST / NOT_CALLED
);

create table if not exists collections_calls (
    call_id       text,
    card_id       bigint,
    customer_id   bigint,
    call_ts       text,                 -- 3 formats, parsed into call_time in 02_clean.sql
    agent_id      text,
    call_outcome  text,
    duration_sec  int,
    agent_note    text                  -- free text, can contain names and phone numbers
);

-- amounts recovered after write-off
create table if not exists recoveries (
    card_id         bigint,
    recovery_month  text,
    amount          numeric
);

-- files already loaded (load_data.py skips these)
create table if not exists load_log (
    file_name   text primary key,
    rows_loaded bigint,
    loaded_at   timestamptz default now()
);

-- one row per data check per run (src/dq_checks.py)
create table if not exists dq_results (
    run_month   text,
    check_name  text,
    severity    text,
    failed_rows bigint,
    checked_at  timestamptz default now()
);

-- one row per step of each monthly refresh (src/monthly_refresh.py)
create table if not exists refresh_log (
    run_month   text,
    step        text,              -- landing / load / checks / export / done
    status      text,              -- OK / WAITING / LATE / FAILED
    detail      text,
    logged_at   timestamptz default now()
);

-- for the usual card / month filters and joins
create index if not exists ix_stmt_card_month on card_statements (card_id, statement_month);
create index if not exists ix_stmt_month      on card_statements (statement_month);
create index if not exists ix_queue           on collections_queue (card_id, month);
create index if not exists ix_calls_card      on collections_calls (card_id);
