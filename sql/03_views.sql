-- 03_views.sql
-- Shared definitions, so notebooks and reports use the same logic.

-- statements + bucket, KPI base, utilisation, months on book
create or replace view v_statements as
select s.*,
       to_date(s.statement_month, 'YYYY-MM')                                   as month_date,
       -- bucket: 0 = current, 1 = 1-29 DPD, 2 = 30-59 ... 6 = 150-179, 7 = 180+
       case when s.dpd_days = 0   then 0  when s.dpd_days < 30  then 1
            when s.dpd_days < 60  then 2  when s.dpd_days < 90  then 3
            when s.dpd_days < 120 then 4  when s.dpd_days < 150 then 5
            when s.dpd_days < 180 then 6  else 7 end                            as bucket,
       -- KPI base: not charged off, and balance > 1,000 or already late
       (s.account_status <> 'CHARGED_OFF' and (s.balance > 1000 or s.dpd_days > 0)) as carries_balance,
       -- utilisation capped at 1 (balance can be over the limit)
       s.balance / nullif(greatest(s.credit_limit, s.balance), 0)              as utilisation,
       c.customer_id, c.channel, c.open_month, c.opened_before_window,
       -- months on book, from the 'YYYY-MM' text columns
       (substr(s.statement_month, 1, 4)::int - substr(c.open_month, 1, 4)::int) * 12
        + substr(s.statement_month, 6, 2)::int - substr(c.open_month, 6, 2)::int as months_on_book
from card_statements s
join cards c using (card_id);

-- bucket labels for charts
create or replace view v_bucket_names as
select * from (values (0, '0 Current'), (1, '1 DPD 1-29'), (2, '2 DPD 30-59'), (3, '3 DPD 60-89'),
                      (4, '4 DPD 90-119'), (5, '5 DPD 120-149'), (6, '6 DPD 150-179'),
                      (7, '7 Charged off')) t(bucket, bucket_name);

-- monthly KPIs; definitions in docs/metric_definitions.md
create or replace view v_monthly_kpi as
select statement_month,
       count(*) filter (where carries_balance)                                   as active_accounts,
       count(*) filter (where carries_balance and dpd_days >= 30)                as dpd30_accounts,
       round(count(*) filter (where carries_balance and dpd_days >= 30)::numeric
             / nullif(count(*) filter (where carries_balance), 0), 4)            as dpd30_rate,
       round(count(*) filter (where carries_balance and dpd_days >= 60)::numeric
             / nullif(count(*) filter (where carries_balance), 0), 4)            as dpd60_rate,
       round(count(*) filter (where carries_balance and dpd_days >= 90)::numeric
             / nullif(count(*) filter (where carries_balance), 0), 4)            as dpd90_rate,
       round(sum(balance) filter (where carries_balance and dpd_days >= 30)
             / nullif(sum(balance) filter (where carries_balance), 0), 4)        as dpd30_balance_rate,
       round(sum(balance) filter (where carries_balance) / 1e7, 2)               as balance_crore,
       count(*) filter (where account_status = 'CHARGED_OFF')                    as write_offs,
       round(coalesce(sum(balance) filter (where account_status = 'CHARGED_OFF'), 0) / 1e7, 2) as write_off_crore
from v_statements
group by statement_month;

-- each card's bucket this month and next month (for roll rates)
create or replace view v_transitions as
select card_id, statement_month, bucket as from_bucket,
       lead(bucket)     over w as to_bucket,
       lead(month_date) over w as next_month
from v_statements
window w as (partition by card_id order by month_date);
