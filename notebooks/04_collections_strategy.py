# %% [markdown]
# # 04 - Q3a: Collections can call only 15% of late accounts. Whom should they call?
# Today: biggest overdue amount first. Idea: call first where a call avoids the most loss.
#   loss avoided by a call = drop in the chance of write-off x balance x LGD
# 20% of calls go to randomly picked late accounts (RANDOM_TEST cell), which works as an A/B test of the call effect.

# %% setup
import sys
from pathlib import Path

project = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(project))

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint, proportions_ztest

from src.config import SETTINGS
from src.db import query, write_table
from src.style import apply_style, save, SERIES

apply_style()
CAPACITY = SETTINGS["collections"]["capacity_pct"]       # 15%

# %% 1. The queue, and what happened to each account: cured that month? written off within 6 months?
q = query("""
    with write_offs as (
        select card_id, min(statement_month) as wo_month
        from card_statements where account_status = 'CHARGED_OFF'
        group by card_id
    )
    select q.month, q.card_id, q.bucket_at_start, q.overdue_amount, q.balance, q.assigned_cell,
           s.bucket as bucket_after,
           case when w.wo_month <= to_char(to_date(q.month, 'YYYY-MM') + interval '5 month', 'YYYY-MM')
                then 1 else 0 end as written_off_6m
    from collections_queue q
    left join v_statements s on s.card_id = q.card_id and s.statement_month = q.month
    left join write_offs w on w.card_id = q.card_id
    -- only queue months with 6 months of results after them
    where q.month <= to_char((select max(month_date) from v_statements) - interval '6 month', 'YYYY-MM')
""")
q["cured"] = (q.bucket_after == 0).astype(int)
print(f"{len(q):,} queue account-months:", q.assigned_cell.value_counts().to_dict())

# %% 2. Randomisation check: RANDOM_TEST should look like NOT_CALLED
# (RANKED is different by design: biggest overdues first)
print(q[q.assigned_cell != "RANKED"].groupby("assigned_cell")[["bucket_at_start", "overdue_amount", "balance"]].mean().round(1))

# %% 3. What does a call do? Random test vs not called, bucket by bucket
rows = []
for bucket, g in q[q.assigned_cell != "RANKED"].groupby("bucket_at_start"):
    called = g[g.assigned_cell == "RANDOM_TEST"]
    not_called = g[g.assigned_cell == "NOT_CALLED"]
    if len(called) < 30:                                   # too small to compare
        continue
    for metric in ["cured", "written_off_6m"]:
        z, p = proportions_ztest([called[metric].sum(), not_called[metric].sum()], [len(called), len(not_called)])
        low, high = proportion_confint(called[metric].sum(), len(called), method="wilson")
        rows.append({"bucket": bucket, "metric": metric,
                     "called": called[metric].mean(), "called_ci": f"{low:.1%}-{high:.1%}",
                     "not_called": not_called[metric].mean(),
                     "difference": called[metric].mean() - not_called[metric].mean(),
                     "p_value": p, "n_called": len(called), "n_not_called": len(not_called)})
effect = pd.DataFrame(rows)
print(effect.round(4).to_string(index=False))
write_table(effect, "report_call_effect")

# %% Chart - cure rate and 6-month write-off rate, called vs not called
fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
for ax, metric, title in [(axes[0], "cured", "Cured in the month"), (axes[1], "written_off_6m", "Written off within 6 months")]:
    d = effect[effect.metric == metric]
    x = np.arange(len(d))
    ax.bar(x - 0.18, d.not_called, width=0.34, color=SERIES[0], label="Not called")
    ax.bar(x + 0.18, d.called, width=0.34, color=SERIES[2], label="Called (random test)")
    ax.set_xticks(x, [f"Bucket {b}" for b in d.bucket])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.set_title(title)
    ax.legend()
fig.suptitle("A call works best early: bigger effect in buckets 1-2 than in deep delinquency", x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, "04_call_effect")

# %% 4. LGD = share of a written-off balance we never get back (write-offs with at least 12 months of recoveries)
wo = query("""
    with write_offs as (
        select card_id, statement_month as wo_month, balance as written_off
        from card_statements where account_status = 'CHARGED_OFF'
    )
    select w.card_id, w.written_off, coalesce(sum(r.amount), 0) as recovered
    from write_offs w
    left join recoveries r on r.card_id = w.card_id
    where w.wo_month <= to_char((select max(month_date) from v_statements) - interval '12 month', 'YYYY-MM')
    group by w.card_id, w.wo_month, w.written_off
""")
LGD = float(1 - wo.recovered.sum() / wo.written_off.sum())   # amount-weighted: big balances count more
print(f"{len(wo):,} write-offs with 12 months of recoveries; LGD = {LGD:.1%}")

# %% 5. Loss a call avoids, per account, by bucket
# Only trust the cure effect where p < 0.05 (the write-off differences above are too noisy).
# A cure matters because cured accounts are written off much less often; that gap comes from accounts nobody called.
cure = effect[effect.metric == "cured"].set_index("bucket")
cure_uplift = pd.Series(np.where((cure.p_value < 0.05) & (cure.difference > 0), cure.difference, 0), index=cure.index)

nc = q[q.assigned_cell == "NOT_CALLED"]
wo_if_not_cured = nc[nc.cured == 0].groupby("bucket_at_start").written_off_6m.mean()
wo_if_cured = nc[nc.cured == 1].groupby("bucket_at_start").written_off_6m.mean()
wo_gap = wo_if_not_cured - wo_if_cured

wo_drop = (cure_uplift * wo_gap).fillna(0)                    # how much one call lowers the chance of write-off
print(pd.DataFrame({"cure_uplift": cure_uplift, "wo_gap_if_not_cured": wo_gap, "wo_drop_per_call": wo_drop}).round(4))
q["loss_avoided"] = q.bucket_at_start.map(wo_drop).fillna(0) * q.balance * LGD

# %% 6. Back-test: every past month, call 15% of the queue with each order, add up the loss avoided
TODAY, NEW = "Highest overdue first (today)", "Highest loss avoided first (new)"


def backtest(q):
    rows = []
    for month, g in q.groupby("month"):
        n_calls = round(CAPACITY * len(g))
        for order, sort_by in [(TODAY, "overdue_amount"), (NEW, "loss_avoided")]:
            top = g.nlargest(n_calls, sort_by)
            rows.append({"month": month, "policy": order, "calls": n_calls,
                         "loss_avoided": top.loss_avoided.sum(), "avg_bucket_called": top.bucket_at_start.mean()})
    return pd.DataFrame(rows)


def extra_per_month(bt):
    """Average extra loss avoided per month by the new order, over the last 12 back-test months."""
    last_12 = bt[bt.month >= sorted(bt.month.unique())[-12]]
    avg = last_12.groupby("policy").loss_avoided.mean()
    return avg[NEW] - avg[TODAY]


bt = backtest(q)
summary = bt.groupby("policy").agg(months=("month", "nunique"), calls_per_month=("calls", "mean"),
                                   loss_avoided_per_month=("loss_avoided", "mean"),
                                   avg_bucket_called=("avg_bucket_called", "mean")).reset_index()
print(summary.round(2).to_string(index=False))
gain = extra_per_month(bt)
print(f"last 12 months: extra loss avoided Rs {gain / 1e5:.1f} lakh a month (Rs {gain * 12 / 1e7:.2f} crore a year), same team")
write_table(summary, "report_collections_policy")
write_table(pd.DataFrame([{"lgd": round(LGD, 4), "extra_loss_avoided_per_month": round(gain, 0)}]), "report_collections_value")

# %% Chart - loss avoided per month with each order (last two years)
recent = bt[bt.month >= "2024-09"]
write_table(recent, "report_collections_backtest")
fig, ax = plt.subplots(figsize=(10, 4))
for order, color in [(NEW, SERIES[1]), (TODAY, SERIES[0])]:
    d = recent[recent.policy == order]
    ax.plot(d.month, d.loss_avoided / 1e5, color=color, marker="o", markersize=3, label=order)
ax.set_ylabel("Expected loss avoided (Rs lakh / month)")
ax.set_title("Same 15% capacity, different queue order")
ax.set_xticks(sorted(recent.month.unique())[::2])
ax.tick_params(axis="x", rotation=90)
ax.legend()
fig.tight_layout()
save(fig, "04_policy_backtest")

# %% 7. How sure are we about the rupee value? Redo it with the low and high end of the call effect
# The +8.6 / +5.7 points come from a small random group, so each has a 95% confidence interval.
rows = []
for bucket in cure_uplift[cure_uplift > 0].index:
    g = q[(q.bucket_at_start == bucket) & (q.assigned_cell != "RANKED")]
    called = g[g.assigned_cell == "RANDOM_TEST"]
    not_called = g[g.assigned_cell == "NOT_CALLED"]
    low, high = confint_proportions_2indep(called.cured.sum(), len(called), not_called.cured.sum(), len(not_called),
                                           compare="diff", method="newcomb")
    rows.append({"bucket": bucket, "low": max(low, 0), "central": cure_uplift[bucket], "high": high})
uplift_ci = pd.DataFrame(rows).set_index("bucket")
print(uplift_ci.round(4))

cases = []
for case in ["low", "central", "high"]:
    uplift = uplift_ci[case].reindex(cure_uplift.index).fillna(0)
    q_case = q.copy()
    q_case["loss_avoided"] = q_case.bucket_at_start.map((uplift * wo_gap).fillna(0)).fillna(0) * q_case.balance * LGD
    cases.append({"case": case, "extra_loss_avoided_per_month": round(extra_per_month(backtest(q_case)), 0)})
value_range = pd.DataFrame(cases)
print(value_range.assign(rs_lakh=(value_range.extra_loss_avoided_per_month / 1e5).round(1)))
write_table(value_range, "report_collections_range")

# %% 8. This month's call list
# same function as the Excel export (src/export.py), so the two always match
from src.collections_list import build_call_list

call_list = build_call_list()
print(f"queue month {call_list.month.iloc[0]}: {len(call_list):,} accounts to call")
print(call_list.head(10).to_string(index=False))
