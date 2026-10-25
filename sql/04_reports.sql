-- 04_reports.sql
-- Summary tables for the charts, Tableau and the export. Rebuilt after every load.

-- 1. monthly KPIs as a table, for the export
drop table if exists report_monthly_kpi;
create table report_monthly_kpi as
select * from v_monthly_kpi order by statement_month;

-- 2. Q1: book split - existing book, new co-brand cards, other new cards
drop table if exists report_book_segments;
create table report_book_segments as
select statement_month,
       case when open_month < '2025-04' or opened_before_window then 'Existing book (opened before Apr-2025)'
            when channel = 'Fintech Co-brand' then 'New cards: Fintech Co-brand'
            else 'New cards: other channels' end                               as book_segment,
       count(*) filter (where carries_balance)                                 as active_accounts,
       count(*) filter (where carries_balance and dpd_days >= 30)              as dpd30_accounts
from v_statements
where statement_month >= '2024-09'
group by 1, 2;

-- 3. Q1: roll rates, last 12 months
drop table if exists report_roll_rates;
create table report_roll_rates as
with t as (
    select from_bucket, to_bucket, count(*) as accounts
    from v_transitions
    where next_month = (to_date(statement_month, 'YYYY-MM') + interval '1 month')::date   -- consecutive months only
      and statement_month >= to_char((select max(month_date) from v_statements) - interval '12 month', 'YYYY-MM')
      and from_bucket between 0 and 6
    group by 1, 2
)
select t.from_bucket, f.bucket_name as from_name, t.to_bucket, o.bucket_name as to_name, t.accounts,
       round(t.accounts::numeric / sum(t.accounts) over (partition by t.from_bucket), 4) as roll_pct
from t
join v_bucket_names f on f.bucket = t.from_bucket
join v_bucket_names o on o.bucket = t.to_bucket
order by 1, 3;

-- 4. Q1: vintage curves - % of each opening quarter ever 30+ / 60+ DPD, by months on book (0-18)
drop table if exists report_vintage;
create table report_vintage as
with first_bad as (
    select card_id,
           min(months_on_book) filter (where dpd_days >= 30) as mob_30,
           min(months_on_book) filter (where dpd_days >= 60) as mob_60
    from v_statements group by card_id
),
v as (
    select c.card_id,
           case when c.channel = 'Fintech Co-brand' then 'Fintech Co-brand' else 'Other channels' end as channel_group,
           to_char(to_date(c.open_month, 'YYYY-MM'), 'YYYY-"Q"Q')  as vintage,
           to_date(c.open_month, 'YYYY-MM')                         as open_date,
           f.mob_30, f.mob_60
    from cards c join first_bad f using (card_id)
    where not c.opened_before_window and c.open_month >= '2023-01'
)
select vintage, channel_group, k.mob,
       count(*)                                            as cards,
       round(avg((coalesce(mob_30, 999) <= k.mob)::int), 5) as ever_30_rate,
       round(avg((coalesce(mob_60, 999) <= k.mob)::int), 5) as ever_60_rate
from v
cross join generate_series(0, 18) as k(mob)
where (date_trunc('quarter', open_date) + interval '2 month' + make_interval(months => k.mob))::date
      <= (select max(month_date) from v_statements)          -- only months every card in the quarter has reached
group by 1, 2, 3
having count(*) >= 200                                       -- drop small vintages
order by 1, 2, 3;

-- 5. Q2: 30+ rate by segment, latest month, with a 95% Wilson interval (better than the normal approximation for small rates)
drop table if exists report_segments;
create table report_segments as
with latest as (
    select s.*, cu.income_type, cu.city_tier, cu.bureau_score,
           date_part('year', age(s.month_date, cu.date_of_birth)) as age
    from v_statements s join customers cu using (customer_id)
    where s.statement_month = (select max(statement_month) from card_statements)
      and s.carries_balance
),
long as (
    select 'Channel' as dimension, channel as segment, (dpd_days >= 30)::int as bad from latest
    union all select 'City tier', city_tier, (dpd_days >= 30)::int from latest
    union all select 'Income type', income_type, (dpd_days >= 30)::int from latest
    union all select 'Utilisation', case when utilisation < 0.3 then '1: <30%' when utilisation < 0.7 then '2: 30-70%'
                                         when utilisation < 0.9 then '3: 70-90%' else '4: 90%+' end, (dpd_days >= 30)::int from latest
    union all select 'Bureau score', case when bureau_score is null then 'Missing' when bureau_score < 500 then '1: <500'
                                          when bureau_score < 600 then '2: 500-599' when bureau_score < 700 then '3: 600-699'
                                          else '4: 700+' end, (dpd_days >= 30)::int from latest
    union all select 'Age band', case when age < 30 then '1: <30' when age < 40 then '2: 30-39'
                                      when age < 50 then '3: 40-49' else '4: 50+' end, (dpd_days >= 30)::int from latest
),
agg as (select dimension, segment, count(*) as accounts, sum(bad) as dpd30, avg(bad::numeric) as p
        from long group by 1, 2)
select dimension, segment, accounts, dpd30, round(p, 4) as dpd30_rate,
       round((((p + 1.96^2/(2*accounts)) - 1.96*sqrt(p*(1-p)/accounts + 1.96^2/(4*accounts^2)))
             / (1 + 1.96^2/accounts))::numeric, 4) as ci_low,
       round((((p + 1.96^2/(2*accounts)) + 1.96*sqrt(p*(1-p)/accounts + 1.96^2/(4*accounts^2)))
             / (1 + 1.96^2/accounts))::numeric, 4) as ci_high
from agg
where accounts >= 30
order by 1, 2;
