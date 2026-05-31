"""Throwaway research harness: fill the genuine gaps in the 100% CPM strategy
headline number set (NOT covered verbatim by existing research files).

Role: analyst (read-only re production; NO production/memo edits; NO commit).

Reuses the VALIDATED mooex (T+1 MOO exact, real auto_adjust opens, 10 bps/side)
CPM daily-return builder from exec_lag_moo_validation_2026_05_30 to:

  1. Re-confirm the CPM clean anchor (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615)
     and ext (Sharpe 1.2161 / MaxDD -15.93% / Calmar 0.8654).
  2. Bootstrap 95% CI on CPM clean Sharpe (stationary block, B=2000, block=21,
     seed=42) -> low / MEDIAN / high (median is the genuine gap; low/high already
     reported in cpm_iv4_final_numbers).
  3. Crisis drawdown EPISODES on the 100% CPM equity curve (NOT blend): GFC,
     COVID, 2022 -- peak date, trough date, depth, recovery date (global episode
     detection, not within-window MaxDD).

Everything else in the assembled set is pulled from existing research/*.json /
findings and is NOT recomputed here.
"""
import sys
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import load_panel, perf_metrics
import exec_lag_moo_validation_2026_05_30 as V

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")


def drawdown_episodes(equity, min_depth=0.05):
    """Return list of drawdown episodes: peak, trough, depth, recovery (or None)."""
    eq = equity.dropna()
    run_max = eq.cummax()
    dd = eq / run_max - 1.0
    episodes = []
    in_dd = False
    peak_date = None
    trough_date = None
    trough_val = 0.0
    for d, v in dd.items():
        if not in_dd:
            if v < 0:
                in_dd = True
                peak_date = run_max.loc[:d].index[run_max.loc[:d].values.argmax()]
                # peak = last date equity == running max before this dip
                peak_date = eq.loc[:d][eq.loc[:d] == run_max.loc[d]].index[-1]
                trough_date = d
                trough_val = v
        else:
            if v < trough_val:
                trough_val = v
                trough_date = d
            if v >= 0:  # recovered
                episodes.append({
                    "peak": peak_date, "trough": trough_date,
                    "depth": trough_val, "recovery": d, "recovered": True})
                in_dd = False
                peak_date = trough_date = None
                trough_val = 0.0
    if in_dd:
        episodes.append({
            "peak": peak_date, "trough": trough_date,
            "depth": trough_val, "recovery": None, "recovered": False})
    return [e for e in episodes if e["depth"] <= -min_depth]


def find_episode(episodes, lo, hi):
    """Pick the deepest episode whose TROUGH falls in [lo, hi]."""
    lo, hi = pd.Timestamp(lo), pd.Timestamp(hi)
    cand = [e for e in episodes if lo <= e["trough"] <= hi]
    if not cand:
        return None
    return min(cand, key=lambda e: e["depth"])


def block_bootstrap_sharpe(daily, B=2000, block=21, seed=42):
    r = daily.dropna().values
    n = len(r)
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    out = np.empty(B)
    for b in range(B):
        starts = rng.integers(0, n, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) % n for s in starts])[:n]
        sample = r[idx]
        sd = sample.std()
        out[b] = (sample.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan
    out = out[~np.isnan(out)]
    return {
        "point": float(daily.mean() / daily.std() * np.sqrt(252)),
        "low": float(np.percentile(out, 2.5)),
        "median": float(np.percentile(out, 50)),
        "high": float(np.percentile(out, 97.5)),
        "B": B, "block": block, "seed": seed, "n_eff": int(len(out)),
    }


def main():
    end = pd.Timestamp("2026-05-30")
    panel = load_panel(start=EXT_START, end=end)
    end = min(end, panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    open_df, close_yf = V.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    # CPM mooex daily series over full ext range, then slice windows.
    cpm_full, fb = V.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, "mooex")
    print(f"CPM mooex coverage: real={fb[0]} fallback={fb[1]} rebal days")

    clean = cpm_full.loc[(cpm_full.index >= CLEAN_START) & (cpm_full.index <= end)]
    ext = cpm_full.loc[(cpm_full.index >= EXT_START) & (cpm_full.index <= end)]

    mc = perf_metrics(clean, cash_daily)
    me = perf_metrics(ext, cash_daily)

    print("\n=== ANCHOR GATE (100% CPM, mooex) ===")
    print(f"clean: Sharpe={mc['sharpe']:.4f} MaxDD={mc['max_drawdown']*100:.2f}% "
          f"Calmar={mc['calmar']:.4f} CAGR={mc['cagr']*100:.2f}% Vol={mc['vol']*100:.2f}%")
    print(f"  expect 1.1910 / -12.67% / 1.0615")
    print(f"ext:   Sharpe={me['sharpe']:.4f} MaxDD={me['max_drawdown']*100:.2f}% "
          f"Calmar={me['calmar']:.4f} CAGR={me['cagr']*100:.2f}% Vol={me['vol']*100:.2f}%")
    print(f"  expect 1.2161 / -15.93% / 0.8654")

    anchor_ok = (abs(mc['sharpe'] - 1.1910) < 0.0010 and
                 abs(mc['max_drawdown'] * 100 + 12.67) < 0.05 and
                 abs(mc['calmar'] - 1.0615) < 0.0050)
    print(f"\nANCHOR clean match: {anchor_ok}")

    # Bootstrap CI on CLEAN Sharpe.
    print("\n=== BOOTSTRAP 95% CI -- CPM clean Sharpe (block, B=2000, block=21, seed=42) ===")
    bs = block_bootstrap_sharpe(clean, B=2000, block=21, seed=42)
    print(f"point={bs['point']:.4f}  low={bs['low']:.4f}  median={bs['median']:.4f}  "
          f"high={bs['high']:.4f}  (n_eff={bs['n_eff']})")

    # Crisis episodes on CPM equity (full ext curve for episode continuity).
    eq_full = (1.0 + cpm_full).cumprod()
    eps = drawdown_episodes(eq_full, min_depth=0.04)
    print("\n=== CPM drawdown episodes (global, depth>=4%) ===")
    for e in eps:
        rec = e["recovery"].date() if e["recovery"] else "NOT RECOVERED"
        rdays = ((e["recovery"] - e["trough"]).days if e["recovery"] else None)
        print(f"  peak {e['peak'].date()} -> trough {e['trough'].date()} "
              f"({e['depth']*100:.2f}%) -> recovery {rec}"
              + (f" (+{rdays}d)" if rdays else ""))

    crises = {
        "GFC_2008_09": ("2008-06-01", "2009-12-31"),
        "COVID_2020": ("2020-02-01", "2020-12-31"),
        "bear_2022": ("2022-01-01", "2023-06-30"),
    }
    crisis_out = {}
    print("\n=== CRISIS EPISODES (deepest CPM episode troughing in window) ===")
    for name, (lo, hi) in crises.items():
        e = find_episode(eps, lo, hi)
        if e is None:
            print(f"  {name}: no episode >=4% troughing in window")
            crisis_out[name] = None
            continue
        rec = e["recovery"].isoformat()[:10] if e["recovery"] else None
        rdays = ((e["recovery"] - e["trough"]).days if e["recovery"] else None)
        ttdays = (e["trough"] - e["peak"]).days
        crisis_out[name] = {
            "peak": e["peak"].isoformat()[:10],
            "trough": e["trough"].isoformat()[:10],
            "depth_pct": round(e["depth"] * 100, 2),
            "recovery": rec,
            "peak_to_trough_days": ttdays,
            "trough_to_recovery_days": rdays,
            "recovered": e["recovered"],
        }
        print(f"  {name}: peak {e['peak'].date()} -> trough {e['trough'].date()} "
              f"({e['depth']*100:.2f}%, {ttdays}d) -> recovery {rec or 'NONE'}"
              + (f" (+{rdays}d)" if rdays else ""))

    result = {
        "convention": "mooex T+1 MOO exact, 10 bps/side, monthly month-end signal, CPM = cpm_live (HYG-OR-TIP canary)",
        "windows": {"clean": ["2008-05-30", str(end.date())],
                    "ext": ["1999-03-10", str(end.date())]},
        "anchor": {
            "clean": {"sharpe": mc['sharpe'], "maxdd_pct": mc['max_drawdown'] * 100,
                      "calmar": mc['calmar'], "cagr_pct": mc['cagr'] * 100, "vol_pct": mc['vol'] * 100},
            "ext": {"sharpe": me['sharpe'], "maxdd_pct": me['max_drawdown'] * 100,
                    "calmar": me['calmar'], "cagr_pct": me['cagr'] * 100, "vol_pct": me['vol'] * 100},
            "clean_match_1910": anchor_ok,
        },
        "bootstrap_clean_sharpe": bs,
        "crisis_episodes": crisis_out,
        "mooex_coverage": {"real": fb[0], "fallback": fb[1]},
    }
    out_path = Path(__file__).resolve().parent / "cpm_headline_gaps_compute.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
