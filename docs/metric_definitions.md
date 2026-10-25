# Metric definitions

Every number in this project uses one of these definitions. Each one says exactly what is counted
(numerator), out of what (denominator), and where the logic lives, so anyone can check it.

## Book and KPI

| Metric | Definition | Where |
|---|---|---|
| Account carrying a balance | A card's statement row where the account is not written off and it owes more than Rs 1,000, or it is already late (`account_status <> 'CHARGED_OFF' and (balance > 1000 or dpd_days > 0)`) | `v_statements.carries_balance` |
| **30+ DPD rate** | Accounts carrying a balance that are 30 or more days late ÷ all accounts carrying a balance, per statement month | `v_monthly_kpi.dpd30_rate` |
| 30+ DPD rate by balance | Balance (Rs) of the 30+ accounts ÷ balance of all accounts carrying a balance | `v_monthly_kpi.dpd30_balance_rate` |
| DPD bucket | 0 = on time · 1 = 1-29 days late · 2 = 30-59 · 3 = 60-89 · 4 = 90-119 · 5 = 120-149 · 6 = 150-179 · 7 = 180+ (written off) | `v_statements.bucket` |
| Utilisation | Balance ÷ credit limit; if the balance is above the limit, it counts as 100% | `v_statements.utilisation` |
| Months on book (MOB) | Months between the card's opening month and the statement month | `v_statements.months_on_book` |
| Book part | **Existing book** = opened before Apr-2025 (the co-brand launch) or before the data starts · **New: Fintech Co-brand** · **New: other channels** | `report_book_segments` |

## Q1 and Q2: where the rise comes from

| Metric | Definition | Where |
|---|---|---|
| Roll rate | Of the accounts in bucket X this month, the share in bucket Y next month. Only pairs of back-to-back months, last 12 months | `report_roll_rates` |
| Vintage | All cards opened in the same calendar quarter (e.g. 2025-Q2) | `report_vintage` |
| Ever 30+ rate at MOB k | Share of a vintage's cards that were 30+ days late at least once by month k on book. A point is shown only when every card of the quarter has reached month k, and only for groups of 200+ cards | `report_vintage.ever_30_rate` |
| 95% confidence interval | Wilson interval of a segment's 30+ rate (works better than the simple formula for small rates) | `report_segments.ci_low / ci_high` |
| 6-month bad rate (same-score test) | Cards opened Apr-2025 to Feb-2026 that have at least 6 months on book: share that were ever 30+ late within 6 months | notebook 03 |

## Q3a: collections

| Metric | Definition | Where |
|---|---|---|
| Cured | A queue account (late at the start of the month) that is on time (bucket 0) on that month's statement | notebook 04 |
| Written off within 6 months | Charged off in the queue month or in the 5 months after it | notebook 04 |
| Call effect (cure uplift) | Cure rate of the random test group − cure rate of accounts not called, by bucket. Used only where p < 0.05 | `report_call_effect` |
| LGD (loss given default) | 1 − (all money recovered so far ÷ balance at write-off), amount-weighted, for write-offs at least 12 months old | `report_collections_value.lgd` |
| Loss avoided by one call | Cure uplift × (write-off rate if not cured − if cured, from accounts nobody called) × balance × LGD | notebook 04, `src/collections_list.py` |
| Extra loss avoided per month | Over the last 12 back-test months: average loss avoided by calling the top 15% by "loss avoided", minus the same for today's order (top 15% by overdue amount) | `report_collections_value`, `report_collections_range` |

## Q3b: approvals

| Metric | Definition | Where |
|---|---|---|
| 12-month bad rate | Cards opened Apr-2024 to Aug-2025 (outcome known): share that were ever 60+ days late within 12 months on book | notebook 05 |
| Approval rate | Cards a policy would approve ÷ all cards in that group (a simulation on cards that were approved in reality) | `report_policy_curve` |
| Policy A / Policy B | A = one bureau-score cut-off for every channel. B = a separate cut-off for co-brand, chosen so that total approvals are the same as A | `report_policy_tradeoff` |
| Swap-in / swap-out | Swap-in = cards B approves and A declines. Swap-out = cards A approves and B declines | `report_swap_set` |
