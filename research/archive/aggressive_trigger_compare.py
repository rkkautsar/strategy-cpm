"""Compare 4 aggressive triggers (with 15% QLD additive swap)."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fcp_live as fcp
from fcp_live import load_panel, run_fcp_backtest, perf_metrics, sig_13612W

ALIASES = {"AGG": "AGG_stitched", "HYG": "HYG_stitched"}


def fetch_qld(panel):
    s = yf.Ticker("QLD").history(period="max", auto_adjust=True)["Close"]
    s.index = pd.DatetimeIndex(s.index).tz_localize(None)
    return s.reindex(panel.index, method="ffill")


def get_state(monthly, sig_d, canaries):
    state = {}
    for c in canaries:
        col = ALIASES.get(c, c)
        if col not in monthly.columns:
            return None
        v = sig_13612W(monthly[col].loc[:sig_d])
        if pd.isna(v):
            return None
        state[c] = bool(v > 0)
    return state


def trigger_dates(panel, start, end, canaries, rule_fn):
    monthly_idx = pd.DataFrame({"x":1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    triggers = {}
    for sd in sigs:
        mon = panel.loc[:sd].resample("ME").last()
        state = get_state(mon, sd, canaries)
        triggers[sd] = (state is not None) and rule_fn(state)
    return triggers, sigs


def compute_swap(panel, base_rets, sigs, triggers, swap_pct, asset_px):
    swap_ret = asset_px.pct_change().fillna(0).reindex(base_rets.index, fill_value=0)
    firing = pd.Series(0.0, index=base_rets.index)
    for i, sd in enumerate(sigs):
        if not triggers.get(sd, False): continue
        future = panel.index[panel.index > sd]
        if len(future) < 2: continue
        apply_from = future[1]
        if i + 1 < len(sigs):
            next_sig = sigs[i+1]
            nf = panel.index[panel.index > next_sig]
            end_apply = nf[1] if len(nf) >= 2 else panel.index[-1]
        else:
            end_apply = panel.index[-1]
        mask = (base_rets.index >= apply_from) & (base_rets.index < end_apply)
        firing.loc[mask] = swap_pct
    return base_rets * (1 - firing) + firing * swap_ret


TRIGGERS = [
    ("X6_orig:   HYG+ TIP+ EEM+ SPY+",  ["HYG","TIP","EEM","SPY"],
     lambda s: all(s.get(c, False) for c in ["HYG","TIP","EEM","SPY"])),
    ("X6_TLT:    HYG+ TIP+ TLT-",       ["HYG","TIP","TLT"],
     lambda s: s.get("HYG",False) and s.get("TIP",False) and not s.get("TLT",True)),
    ("X6_EEM_TLT: HYG+ TIP+ EEM+ TLT-", ["HYG","TIP","EEM","TLT"],
     lambda s: s.get("HYG",False) and s.get("TIP",False) and s.get("EEM",False) and not s.get("TLT",True)),
    ("X6_strict: HYG+ TIP+ TLT- AGG-",  ["HYG","TIP","TLT","AGG"],
     lambda s: s.get("HYG",False) and s.get("TIP",False) and not s.get("TLT",True) and not s.get("AGG",True)),
]

SWAP_PCTS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]


def main():
    out = Path(__file__).parent / "aggressive_trigger_compare.log"
    log_lines = []
    def log(s=""): log_lines.append(s); print(s)

    log("=" * 110)
    log("COMPARE 4 AGGRESSIVE TRIGGERS WITH QLD SWAP SWEEP")
    log("Base canary deployed: HYG+TIP any+ rule. Base=100% FCP-15 standard.")
    log("=" * 110)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    qld = fetch_qld(panel)
    start = pd.Timestamp("2008-09-30")
    end = panel.index[-1]

    base, _ = run_fcp_backtest(panel, start, end)
    bm = perf_metrics(base)
    log(f"\nBASE FCP-15: Sh={bm['sharpe']:+.3f}  CAGR={bm['cagr']*100:+.2f}%  DD={bm['max_drawdown']*100:+.2f}%")
    log("")

    for label, cans, rule in TRIGGERS:
        log(f"--- {label} ---")
        triggers, sigs = trigger_dates(panel, start, end, cans, rule)
        n_fire = sum(1 for v in triggers.values() if v)
        cov = n_fire / len(sigs) * 100
        log(f"  Fires {n_fire}/{len(sigs)} ({cov:.1f}%)")
        for sw in SWAP_PCTS:
            combined = compute_swap(panel, base, sigs, triggers, sw, qld)
            m = perf_metrics(combined)
            log(f"    swap {int(sw*100):2d}% QLD  Sh={m['sharpe']:+.3f}  "
                f"CAGR={m['cagr']*100:+.2f}%  DD={m['max_drawdown']*100:+.2f}%  "
                f"d_Sh={m['sharpe']-bm['sharpe']:+.3f}  "
                f"d_CAGR={(m['cagr']-bm['cagr'])*100:+.2f}pp  "
                f"d_DD={(m['max_drawdown']-bm['max_drawdown'])*100:+.2f}pp")
        log("")

    log("=" * 110)
    with open(out, "w") as f: f.write("\n".join(log_lines))
    print(f"\nLog: {out}")


if __name__ == "__main__":
    main()
