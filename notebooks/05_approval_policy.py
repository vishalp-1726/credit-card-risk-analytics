# %% [markdown]
# # 05 - Q3b: Should we approve fewer cards? How much volume we lose vs how much the bad rate improves
# Cards opened Apr-2024 to Aug-2025 (all have 12 months on book by Aug-2026).
# Bad = ever 60+ DPD within the first 12 months on book.
# Policy A: one bureau-score cut-off for everyone. Policy B: a stricter cut-off for co-brand only.

# %% setup
import sys
from pathlib import Path

project = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(project))

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd

from src.config import SETTINGS
from src.db import query, write_table
from src.style import apply_style, save, SERIES, INK_2

apply_style()

# %% 1. One row per card: bureau score at application, channel, and the 12-month outcome
d = query("""
    with perf as (
        select card_id,
               min(months_on_book) filter (where dpd_days >= 60) as mob_60,
               max(months_on_book) as last_mob
        from v_statements
        group by card_id
    )
    select c.card_id, c.channel, c.open_month, cu.bureau_score,
           case when p.mob_60 <= 12 then 1 else 0 end as bad_12m
    from cards c
    join perf p using (card_id)
    join customers cu using (customer_id)
    where c.open_month between '2024-04' and '2025-08'
      and not c.opened_before_window
      and (p.last_mob >= 12 or p.mob_60 <= 12)          -- outcome is known
      and cu.bureau_score is not null
""")
d["cobrand"] = d.channel == "Fintech Co-brand"
print(f"{len(d):,} cards; 12-month bad rate {d.bad_12m.mean():.2%}")
print(d.groupby("cobrand").bad_12m.agg(["size", "mean"]).round(4))

# %% 2. Policy A: one cut-off for all. How much volume do we lose, how much does the bad rate fall?
rows = []
for cut in range(400, 701, 10):                    # above 700 there are too few cards left to judge
    approved = d[d.bureau_score >= cut]
    rows.append({"cutoff": cut,
                 "approval_rate": len(approved) / len(d),
                 "bad_rate": approved.bad_12m.mean(),
                 "bads_avoided_pct": 1 - approved.bad_12m.sum() / d.bad_12m.sum(),
                 "cobrand_approval": approved.cobrand.sum() / d.cobrand.sum()})
curve = pd.DataFrame(rows)
print(curve.iloc[::3].round(4).to_string(index=False))
write_table(curve, "report_policy_curve")


# %% 3. Policy B: a stricter cut-off for co-brand and an easier one for the other channels,
# at the same total approvals as Policy A (same volume, so a fair comparison)
def policy_b(target):
    """Try co-brand cut-offs from 400 to 800. For each one, set the other channels' cut-off so that total
    approvals stay at the target. Keep the pair with the lowest bad rate."""
    other_scores = d[~d.cobrand].bureau_score.sort_values(ascending=False)
    best = None
    for cut_cobrand in range(400, 801, 5):
        cobrand_ok = d.cobrand & (d.bureau_score >= cut_cobrand)
        left_for_others = target * len(d) - cobrand_ok.sum()
        if left_for_others <= 0 or left_for_others > len(other_scores):
            continue
        cut_other = other_scores.iloc[int(left_for_others) - 1]     # score of the last other-channel card we approve
        approved = cobrand_ok | (~d.cobrand & (d.bureau_score >= cut_other))
        bad_rate = d[approved].bad_12m.mean()
        if best is None or bad_rate < best["bad_rate"]:
            best = {"cut_cobrand": cut_cobrand, "cut_other": int(cut_other), "bad_rate": bad_rate, "approved": approved}
    return best


target = SETTINGS["approval"]["target_rate"]          # 90%
cut_a = d.bureau_score.quantile(1 - target)           # one cut-off that approves 90%
best = policy_b(target)
d["approve_a"] = d.bureau_score >= cut_a
d["approve_b"] = best["approved"]
print(f"Policy A: one cut-off {cut_a:.0f} -> approval {d.approve_a.mean():.1%}, bad rate {d[d.approve_a].bad_12m.mean():.2%}")
print(f"Policy B: co-brand {best['cut_cobrand']}, others {best['cut_other']} -> approval {d.approve_b.mean():.1%}, "
      f"bad rate {d[d.approve_b].bad_12m.mean():.2%}")

# %% 4. Swap-set: the cards that get a different decision under A and B, and how they performed
d["group"] = "Both decline"
d.loc[d.approve_a & d.approve_b, "group"] = "Both approve"
d.loc[~d.approve_a & d.approve_b, "group"] = "Swap-in (B approves, A declines)"
d.loc[d.approve_a & ~d.approve_b, "group"] = "Swap-out (B declines, A approves)"
swap = d.groupby("group").agg(cards=("bad_12m", "size"), bad_rate=("bad_12m", "mean"),
                              cobrand_share=("cobrand", "mean")).reset_index()
print(swap.round(4).to_string(index=False))
write_table(swap, "report_swap_set")

# %% Chart - approval rate vs bad rate, with the two policies marked
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(curve.approval_rate, curve.bad_rate, color=SERIES[0], marker="o", markersize=3, label="Policy A: one cut-off")
ax.scatter(d.approve_b.mean(), d[d.approve_b].bad_12m.mean(), color=SERIES[1], s=70, zorder=3,
           label="Policy B: stricter co-brand cut-off")
ax.scatter(1.0, d.bad_12m.mean(), color=INK_2, zorder=3)
ax.annotate("approve all (today)", (1.0, d.bad_12m.mean()), xytext=(-8, 8), textcoords="offset points", ha="right", fontsize=9)
ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=1))
ax.set_xlabel("Approval rate (share of these cards we would still have opened)")
ax.set_ylabel("12-month bad rate (ever 60+ DPD)")
ax.set_title("Tightening approvals: volume vs risk")
ax.legend()
fig.tight_layout()
save(fig, "05_policy_curve")

# %% 5. Trade-off table for Credit Policy: the same comparison at 85%, 90% and 95% approval
# "cards declined" and "bad cards avoided" are counted against approving every card (today)
rows = []
for t in SETTINGS["approval"]["tradeoff_rates"]:
    cut = d.bureau_score.quantile(1 - t)
    approve_a = d.bureau_score >= cut
    b = policy_b(t)
    rows.append({"approval_target": t, "cut_one_for_all": round(cut), "cut_cobrand": b["cut_cobrand"],
                 "cut_other": b["cut_other"], "cards_declined": (~approve_a).sum(),
                 "bad_rate_all": d.bad_12m.mean(), "bad_rate_a": d[approve_a].bad_12m.mean(), "bad_rate_b": b["bad_rate"],
                 "bad_cards_avoided_a": d.bad_12m.sum() - d[approve_a].bad_12m.sum(),
                 "bad_cards_avoided_b": d.bad_12m.sum() - d[b["approved"]].bad_12m.sum()})
tradeoff = pd.DataFrame(rows)
print(tradeoff.round(4).to_string(index=False))
write_table(tradeoff, "report_policy_tradeoff")
