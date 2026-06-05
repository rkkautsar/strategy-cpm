from __future__ import annotations
import pandas as pd
from dashboard.helpers import fmt_pct, fmt_num
from config import CPM_WEIGHT as CPM_W, NDX_WEIGHT as NDX_W, VAL_WEIGHT as VAL_W, RPV_WEIGHT as RPV_W

# Production blend weights
CPM_WEIGHT = CPM_W
NDX_WEIGHT = NDX_W
VAL_WEIGHT = VAL_W
RPV_WEIGHT = RPV_W

def alpha_beta_table_html(rows: list[dict]) -> str:
    """rows: list of {strategy, benchmark, alpha_ann_pct, beta, corr}."""
    body = ""
    for r in rows:
        body += ("<tr>"
                  f"<td>{r['strategy']}</td>"
                  f"<td class='ab-benchmark'>{r['benchmark']}</td>"
                  f"<td style='text-align:right'>{r['alpha_ann_pct']:+.2f}%</td>"
                  f"<td style='text-align:right'>{r['beta']:.3f}</td>"
                  f"<td style='text-align:right'>{r['corr']:.3f}</td>"
                  "</tr>\n")
    return f"""<div class='table-scroll'><table class='perf alpha-beta'>
<thead><tr><th>Strategy</th><th>Benchmark</th><th>Alpha (%/yr)</th><th>Beta</th><th>Corr</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


def perf_table_html(rows: list[dict], compact: bool = False) -> str:
    """rows: list of {strategy, cagr, vol, sharpe, excess_sharpe, max_drawdown, ulcer, calmar, martin, ...}.
    compact=True drops Ulcer/Calmar/Martin (keep them for collapsed details view)."""
    df = pd.DataFrame(rows)
    if compact:
        cols = ["strategy", "sharpe", "excess_sharpe", "cagr", "vol", "max_drawdown"]
    else:
        cols = ["strategy", "cagr", "vol", "sharpe", "excess_sharpe", "max_drawdown", "ulcer", "calmar", "martin"]
    cols = [c for c in cols if c in df.columns]
    df = df[cols]
    rename = {"strategy": "Strategy", "cagr": "CAGR", "vol": "Vol", "sharpe": "Raw Sharpe", "excess_sharpe": "Excess Sharpe",
              "max_drawdown": "MaxDD", "ulcer": "Ulcer", "calmar": "Calmar", "martin": "Martin"}
    df.columns = [rename[c] for c in cols]
    body = ""
    pct_cols = {"CAGR", "Vol", "MaxDD", "Ulcer"}
    for _, r in df.iterrows():
        body += f"<tr><td>{r['Strategy']}</td>"
        for c in df.columns[1:]:
            val = r[c]
            cell = fmt_pct(val) if c in pct_cols else fmt_num(val)
            body += f"<td style='text-align:right'>{cell}</td>"
        body += "</tr>\n"
    header = "".join(f"<th>{c}</th>" for c in df.columns)
    return f"""<div class='table-scroll'><table class='perf'>
<thead><tr>{header}</tr></thead>
<tbody>{body}</tbody></table></div>"""


def yearly_table_html(blended: pd.Series, qqq: pd.Series, cpm: pd.Series,
                       rpv: pd.Series, ndx: pd.Series, naive: pd.Series) -> str:
    yr_b = ((1 + blended).resample("YE").prod() - 1)
    yr_f = ((1 + cpm).resample("YE").prod() - 1)
    yr_bu = ((1 + rpv).resample("YE").prod() - 1)
    yr_nd = ((1 + ndx).resample("YE").prod() - 1)
    yr_q = ((1 + qqq.reindex(blended.index)).resample("YE").prod() - 1)
    yr_n = ((1 + naive.reindex(blended.index)).resample("YE").prod() - 1)
    df = pd.DataFrame({"Year": yr_b.index.year,
                       "PROD": yr_b.values * 100,
                       "CPM": yr_f.reindex(yr_b.index).values * 100,
                       "RPV": yr_bu.reindex(yr_b.index).values * 100,
                       "NDX": yr_nd.reindex(yr_b.index).values * 100,
                       "Lit blend": yr_n.reindex(yr_b.index).values * 100,
                       "QQQ": yr_q.reindex(yr_b.index).values * 100})
    df["Excess vs Lit blend"] = df["PROD"] - df["Lit blend"]
    df["Excess vs QQQ"] = df["PROD"] - df["QQQ"]
    body = ""
    for _, r in df.iterrows():
        ex_n = r["Excess vs Lit blend"]
        ex_q = r["Excess vs QQQ"]
        exn_class = "pos" if ex_n > 0 else "neg"
        exq_class = "pos" if ex_q > 0 else "neg"
        body += f"<tr><td>{int(r['Year'])}</td>"
        for col in ["PROD", "CPM", "RPV", "NDX", "Lit blend", "QQQ"]:
            v = r[col]
            cls = "pos" if v > 0 else "neg"
            body += f"<td style='text-align:right' class='{cls}'>{v:+.2f}%</td>"
        body += f"<td style='text-align:right' class='{exn_class}'>{ex_n:+.2f}pp</td>"
        body += f"<td style='text-align:right' class='{exq_class}'>{ex_q:+.2f}pp</td></tr>\n"
    return f"""<div class='table-scroll'><table class='yearly'>
<thead><tr><th>Year</th><th>PROD<br>({int(CPM_WEIGHT*100)}/{int(NDX_WEIGHT*100)}/{int(VAL_WEIGHT*100)}/{int(RPV_WEIGHT*100)})</th><th>CPM only</th><th>RPV only</th><th>NDX only</th><th>Literature blend</th><th>QQQ</th><th>Ex vs Lit blend</th><th>Ex vs QQQ</th></tr></thead>
<tbody>{body}</tbody></table></div>"""
