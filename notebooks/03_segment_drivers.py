# %% [markdown]
# # 03 - Q2: Which segments drive delinquency? Is it the customers co-brand brings, or the channel itself?

# %% setup
import sys
from pathlib import Path

project = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(project))

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

from src.db import query, write_table
from src.style import apply_style, save, SERIES, INK_2

apply_style()

# %% 1. 30+ rate by segment in the latest month, with 95% confidence intervals (calculated in 04_reports.sql)
seg = query("select * from report_segments")
overall = query("select dpd30_rate from report_monthly_kpi order by statement_month desc limit 1").dpd30_rate[0]
print(f"latest month 30+ DPD rate: {overall:.2%}")
print(seg.to_string(index=False))

# %% Chart - dot = rate, line = 95% confidence interval, one small chart per segment type
dimensions = ["Channel", "Bureau score", "Utilisation", "Income type", "City tier", "Age band"]
fig, axes = plt.subplots(2, 3, figsize=(14, 7.5))
for ax, dim in zip(axes.flatten(), dimensions):
    d = seg[seg.dimension == dim].sort_values("segment", ascending=False)
    y = range(len(d))
    ax.errorbar(d.dpd30_rate, y, xerr=[d.dpd30_rate - d.ci_low, d.ci_high - d.dpd30_rate],
                fmt="o", color=SERIES[0], capsize=3)
    ax.axvline(overall, color=INK_2, linestyle="--", linewidth=1)
    ax.set_yticks(y, [f"{s} (n={n:,})" for s, n in zip(d.segment, d.accounts)], fontsize=8)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=1))
    ax.set_title(dim)
fig.suptitle("30+ DPD rate by segment, latest month (95% CI); dashed = book average", x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, "03_segments")

# %% 2. Is co-brand worse only because it signs up riskier customers? Compare at the same bureau score.
# New cards (opened Apr-2025 to Feb-2026) with at least 6 months on book. Bad = ever 30+ DPD within 6 months.
nc = query("""
    with first_bad as (
        select card_id,
               min(months_on_book) filter (where dpd_days >= 30) as mob_30,
               max(months_on_book) as last_mob
        from v_statements
        group by card_id
    )
    select c.card_id,
           c.channel = 'Fintech Co-brand' as cobrand,
           cu.bureau_score,
           case when f.mob_30 <= 6 then 1 else 0 end as bad_6m
    from cards c
    join first_bad f using (card_id)
    join customers cu using (customer_id)
    where c.open_month between '2025-04' and '2026-02'
      and not c.opened_before_window
      and f.last_mob >= 6
      and cu.bureau_score is not null
""")
nc["score_band"] = pd.cut(nc.bureau_score, [0, 500, 600, 700, 900], labels=["<500", "500-599", "600-699", "700+"])
by_band = nc.groupby(["score_band", "cobrand"], observed=True).bad_6m.agg(["mean", "size"]).unstack()
print(by_band.round(4))

same_score = nc.groupby(["score_band", "cobrand"], observed=True).bad_6m.agg(cards="size", bad_6m_rate="mean").reset_index()
same_score["channel_group"] = np.where(same_score.cobrand, "Fintech Co-brand", "Other channels")
same_score["score_band"] = same_score.score_band.astype(str)
write_table(same_score.drop(columns="cobrand"), "report_cobrand_same_score")

# expected co-brand bad rate = each co-brand card gets the other channels' bad rate for its score band
cobrand = nc[nc.cobrand]
others = nc[~nc.cobrand]
others_rate_by_band = others.groupby("score_band", observed=True).bad_6m.mean()
expected = cobrand.score_band.map(others_rate_by_band).astype(float).mean()
actual = cobrand.bad_6m.mean()
others_rate = others.bad_6m.mean()
print(f"6-month bad rate: co-brand {actual:.2%} | other channels {others_rate:.2%} | "
      f"co-brand if they behaved like other channels at the same score {expected:.2%}")
print(f"-> customer mix explains {(expected - others_rate) / (actual - others_rate):.0%} of the gap; "
      f"the channel itself explains {(actual - expected) / (actual - others_rate):.0%}")
write_table(pd.DataFrame([{"cobrand_bad_6m": round(actual, 4), "other_bad_6m": round(others_rate, 4),
                           "cobrand_expected_same_score": round(expected, 4)}]), "report_cobrand_gap")

# %% Chart - co-brand vs other channels inside each bureau score band
fig, ax = plt.subplots(figsize=(8, 4.2))
x = np.arange(len(by_band))
bars_other = ax.bar(x - 0.18, by_band["mean"][False], width=0.34, color=SERIES[0], label="Other channels")
bars_cb = ax.bar(x + 0.18, by_band["mean"][True], width=0.34, color=SERIES[3], label="Fintech Co-brand")
ax.bar_label(bars_other, fmt="{:.1%}", fontsize=8, padding=2)
ax.bar_label(bars_cb, fmt="{:.1%}", fontsize=8, padding=2)
ax.set_xticks(x, [f"Bureau {band}" for band in by_band.index])
ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
ax.set_ylabel("Ever 30+ DPD within 6 months")
ax.set_title("Co-brand cards go bad more often even at the same bureau score")
ax.legend()
fig.tight_layout()
save(fig, "03_cobrand_same_score")
