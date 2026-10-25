# %% [markdown]
# # 02 - Q1: Is the rise coming from new cards or from the existing book?
# KPI: 30+ DPD rate = accounts carrying a balance that are 30+ days late / all accounts carrying a balance

# %% setup
import sys
from pathlib import Path

project = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(project))

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd
from matplotlib.colors import ListedColormap

from src.db import query, write_table
from src.style import apply_style, save, SERIES, BLUES, INK, INK_2

apply_style()

# %% 1. The headline: 30+ DPD rate by month
kpi = query("select * from report_monthly_kpi where statement_month >= '2024-09' order by statement_month")
print(kpi[["statement_month", "active_accounts", "dpd30_rate", "dpd60_rate", "dpd30_balance_rate"]].tail(13).to_string(index=False))

fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
top.plot(kpi.statement_month, kpi.dpd30_rate, marker="o", markersize=3, label="30+ DPD (accounts)")
top.plot(kpi.statement_month, kpi.dpd30_balance_rate, label="30+ DPD (balance Rs)")
for month in ["2025-08", "2026-08"]:
    rate = kpi.loc[kpi.statement_month == month, "dpd30_rate"].iloc[0]
    top.annotate(f"{rate:.1%}", (month, rate), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=9)
top.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=1))
top.set_title("30+ DPD rate, accounts carrying a balance")
top.legend(loc="upper left")
bottom.bar(kpi.statement_month, kpi.active_accounts, color=SERIES[2], width=0.7)
bottom.set_title("Accounts carrying a balance (the denominator)")
bottom.tick_params(axis="x", rotation=90)
fig.tight_layout()
save(fig, "02_kpi_trend")

# %% 2. Split the book into 3 parts and see how much of the change each part explains
book = query("""select statement_month, book_segment, active_accounts, dpd30_accounts
                from report_book_segments
                where statement_month in ('2025-08', '2026-08')""")
book["rate"] = book.dpd30_accounts / book.active_accounts
book["share"] = book.active_accounts / book.groupby("statement_month").active_accounts.transform("sum")

before = book[book.statement_month == "2025-08"].set_index("book_segment").sort_index()
after = book[book.statement_month == "2026-08"].set_index("book_segment").sort_index()
print(pd.concat({"Aug-2025": before[["share", "rate"]], "Aug-2026": after[["share", "rate"]]}, axis=1).round(4))

# mix = the book now has more of some parts (more new cards); rate = a part itself got better or worse
mix = ((after.share - before.share) * before.rate).sum()
rate = (after.share * (after.rate - before.rate)).sum()
total_before = (before.share * before.rate).sum()
total_after = (after.share * after.rate).sum()
print(f"Aug-2025 {total_before:.2%} -> Aug-2026 {total_after:.2%}: mix {mix * 100:+.2f} pp, rate {rate * 100:+.2f} pp")

# what each part added to the change, in % points
contribution = after.share * after.rate - before.share * before.rate
print((contribution * 100).round(2))

# %% Chart - where the extra 30+ accounts came from (counts are easier to explain than % points)
change = after.dpd30_accounts - before.dpd30_accounts
print(pd.DataFrame({"Aug-2025": before.dpd30_accounts, "Aug-2026": after.dpd30_accounts, "change": change}))

change = change.sort_values()
fig, ax = plt.subplots(figsize=(9, 3.8))
colors = [SERIES[3] if "Co-brand" in name else SERIES[0] for name in change.index]
bars = ax.barh(change.index.str.replace(" (opened", "\n(opened"), change.values, color=colors, height=0.55)
ax.bar_label(bars, labels=[f"{v:+,}" for v in change.values], padding=4, fontsize=9)
ax.axvline(0, color=INK_2, linewidth=1)
ax.margins(x=0.2)
ax.set_xlabel("Change in number of 30+ DPD accounts, Aug-2025 to Aug-2026")
ax.set_title(f"30+ accounts: {before.dpd30_accounts.sum():,} -> {after.dpd30_accounts.sum():,}. "
             "Almost all new delinquency is in new cards")
fig.tight_layout()
save(fig, "02_contribution")

q1 = pd.DataFrame({
    "contribution_pp": (contribution * 100).round(3),
    "rate_aug25": before.rate.round(4), "rate_aug26": after.rate.round(4),
    "share_aug25": before.share.round(4), "share_aug26": after.share.round(4),
    "dpd30_accounts_aug25": before.dpd30_accounts, "dpd30_accounts_aug26": after.dpd30_accounts,
})
write_table(q1.rename_axis("segment").reset_index(), "report_q1_contribution")

# %% 3. Is the existing book getting worse? Split by utilisation
old = query("""select statement_month, utilisation >= 0.7 as high_util,
                      count(*) filter (where carries_balance) as accounts,
                      avg((dpd_days >= 30)::int) filter (where carries_balance) as dpd30_rate
               from v_statements
               where (open_month < '2025-04' or opened_before_window)
                 and statement_month >= '2025-01'
                 and utilisation is not null
               group by 1, 2 order by 1, 2""")
fig, ax = plt.subplots(figsize=(10, 4))
for high, color, label in [(True, SERIES[1], "Utilisation 70%+"), (False, SERIES[0], "Utilisation < 70%")]:
    d = old[old.high_util == high]
    ax.plot(d.statement_month, d.dpd30_rate, marker="o", markersize=3, color=color, label=label)
ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=1))
ax.set_title("Existing book only (opened before Apr-2025): 30+ DPD rate by utilisation")
ax.tick_params(axis="x", rotation=90)
ax.legend()
fig.tight_layout()
save(fig, "02_existing_book_util")
print(old.pivot(index="statement_month", columns="high_util", values="dpd30_rate")
         .loc[["2025-01", "2025-07", "2026-01", "2026-08"]].round(4))
write_table(old, "report_existing_book_util")

# %% 4. Vintage curves: how fast do new cards go bad? Same 4 opening quarters, co-brand vs other channels
v = query("select * from report_vintage where vintage between '2025-Q2' and '2026-Q1'")
vintages = sorted(v.vintage.unique())
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
for ax, group in zip(axes, ["Other channels", "Fintech Co-brand"]):
    for i, vintage in enumerate(vintages):           # same colour = same quarter in both charts
        d = v[(v.channel_group == group) & (v.vintage == vintage)]
        ax.plot(d.mob, d.ever_30_rate, color=SERIES[i], label=vintage)
    ax.set_title(group)
    ax.set_xlabel("Months on book")
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.legend(title="Opened in", fontsize=8)
axes[0].set_ylabel("Cumulative % of cards ever 30+ DPD")
fig.suptitle("Vintage curves: co-brand cards go bad about 3x faster than cards opened in the same quarter elsewhere",
             x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
save(fig, "02_vintage_curves")
print(v[v.mob == 6].pivot(index="vintage", columns="channel_group", values="ever_30_rate").round(4))

# %% 5. Roll rates, last 12 months: from each bucket, where are accounts one month later?
rr = query("select * from report_roll_rates")
m = rr.pivot(index="from_name", columns="to_name", values="roll_pct").fillna(0)
fig, ax = plt.subplots(figsize=(9, 5.5))
ax.imshow(m.values, cmap=ListedColormap(BLUES), vmin=0, vmax=1, aspect="auto")
ax.grid(False)
ax.set_xticks(range(len(m.columns)), [name[2:] for name in m.columns], rotation=30)     # drop the "0 " prefix
ax.set_yticks(range(len(m.index)), [name[2:] for name in m.index])
for i in range(len(m.index)):
    for j in range(len(m.columns)):
        value = m.values[i, j]
        if value >= 0.005:
            ax.text(j, i, f"{value:.0%}", ha="center", va="center", fontsize=9, color="white" if value > 0.45 else INK)
ax.set_xlabel("Bucket next month")
ax.set_ylabel("Bucket this month")
ax.set_title("Roll rates, last 12 months: once 60+ DPD, most accounts keep rolling")
fig.tight_layout()
save(fig, "02_roll_rates")
