-- 02_clean.sql
-- Fixes for the issues found when profiling the raw extracts (notebook 01).
-- Each fix only touches rows that are still wrong, so it can run after every load.

-- 1. duplicate statements (same card + month sent twice): keep one row
delete from card_statements a
using card_statements b
where a.card_id = b.card_id
  and a.statement_month = b.statement_month
  and a.ctid > b.ctid;

-- 2. channel: 4 channels, 13 spellings
update cards set channel = case
        when lower(channel) like '%fintech%'                 then 'Fintech Co-brand'
        when lower(replace(channel, '.', '')) like '%dsa%'   then 'DSA'
        when lower(trim(channel)) = 'digital'                then 'Digital'
        when lower(trim(channel)) = 'branch'                 then 'Branch'
        else channel end
where channel not in ('Fintech Co-brand', 'DSA', 'Digital', 'Branch');

-- 3. employment year 3026 = dummy for 'not working' (mostly pensioners) -> null
update customers set employment_start_date = null
where extract(year from employment_start_date) = 3026;

-- 4. gender 'XNA' = unknown
update customers set gender = null where gender = 'XNA';

-- 5. call_ts comes in 3 formats ('2026-03-14 10:25:00', '14/03/2026 10:25', '14-Mar-2026') -> one timestamp
alter table collections_calls add column if not exists call_time timestamp;
update collections_calls set call_time = case
        when call_ts ~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$' then to_timestamp(call_ts, 'YYYY-MM-DD HH24:MI:SS')::timestamp
        when call_ts ~ '^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$'       then to_timestamp(call_ts, 'DD/MM/YYYY HH24:MI')::timestamp
        when call_ts ~ '^\d{2}-[A-Za-z]{3}-\d{4}$'             then to_timestamp(call_ts, 'DD-Mon-YYYY')::timestamp
    end
where call_time is null;

-- 6. calls: agent ids upper case, blank outcomes -> UNKNOWN, duplicate calls dropped
update collections_calls set agent_id = upper(trim(agent_id)) where agent_id <> upper(trim(agent_id));
update collections_calls set call_outcome = coalesce(nullif(upper(trim(call_outcome)), ''), 'UNKNOWN')
where call_outcome is null or call_outcome <> upper(trim(call_outcome));
delete from collections_calls a using collections_calls b
where a.call_id = b.call_id and a.ctid > b.ctid;

-- refresh planner stats after the deletes (04_reports.sql ran for minutes without this)
analyze card_statements;
