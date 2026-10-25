"""This month's call list: rank the latest collections queue by the loss a call can avoid, keep the top 15%.
Uses the call effect and the LGD measured in notebook 04 (report_call_effect, report_collections_value)."""
import numpy as np

from src.config import SETTINGS
from src.db import query, write_table


def build_call_list():
    # 1. extra cure rate from a call, by bucket. Only where the random test showed it (p < 0.05)
    effect = query("select bucket, difference, p_value from report_call_effect where metric = 'cured'")
    effect["uplift"] = np.where((effect.p_value < 0.05) & (effect.difference > 0), effect.difference, 0)
    uplift = effect.set_index("bucket").uplift

    # 2. write-off rate within 6 months, cured vs not cured, from accounts nobody called
    wo = query("""
        with write_offs as (
            select card_id, min(statement_month) as wo_month
            from card_statements where account_status = 'CHARGED_OFF'
            group by card_id
        )
        select q.bucket_at_start as bucket,
               s.dpd_days = 0 as cured,
               avg(case when w.wo_month <= to_char(to_date(q.month, 'YYYY-MM') + interval '5 month', 'YYYY-MM')
                        then 1 else 0 end) as wo_rate
        from collections_queue q
        join card_statements s on s.card_id = q.card_id and s.statement_month = q.month
        left join write_offs w on w.card_id = q.card_id
        where q.assigned_cell = 'NOT_CALLED'
          and q.month <= to_char((select max(to_date(statement_month, 'YYYY-MM')) from card_statements) - interval '6 month', 'YYYY-MM')
        group by 1, 2
    """).pivot(index="bucket", columns="cured", values="wo_rate")
    wo_gap = wo[False] - wo[True]

    # 3. how much one call lowers the chance of write-off
    wo_drop = (uplift * wo_gap).fillna(0)
    lgd = query("select lgd from report_collections_value").lgd[0]

    # 4. loss avoided = drop in write-off chance x balance x LGD, then keep the top 15%
    latest = query("""select month, card_id, bucket_at_start, overdue_amount, balance
                      from collections_queue
                      where month = (select max(month) from collections_queue)""")
    latest["expected_loss_avoided"] = latest.bucket_at_start.map(wo_drop).fillna(0) * latest.balance * lgd
    n_calls = round(SETTINGS["collections"]["capacity_pct"] * len(latest))
    call_list = latest.nlargest(n_calls, "expected_loss_avoided").round(2)
    write_table(call_list, "report_call_list")
    return call_list
