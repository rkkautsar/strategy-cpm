"""
CPM Cross-Universe Validation: Run the final upgraded CPM standalone sleeve
on the original universes of other major TAA strategies:

  1. AAA / PAAA / EAA Universe (10 assets):
     SPY, EFA, EEM, VNQ, DBC, GLD, TLT, IEF, LQD, HYG  [safe = SHV]
  2. DAA / GPM Universe (12 assets):
     SPY, IWM, QQQ, VGK, EWJ, EEM, VNQ, DBC, GLD, TLT, HYG, LQD  [safe = SHV]
  3. FAA Universe (7 assets):
     SPY, VEA, VWO, SHY, LQD, IBB, VNQ  [safe = SHY]
  4. Our Custom CPM Universe (9 assets):
     SPY, QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC  [safe = SHV]

Window: 2008-05-30 to 2026-05-22 (strict live-ETF-only start date)
Cost: 10bps/side friction
Rebalance: monthly sig_date, execution T+1 MOO
"""
import sys, os, math
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "canonical_peer_implementations"))

from cpm_live import load_panel, perf_metrics, sig_13612U, best_safe, SAFE_POOL, CORR_LOOKBACK_DAYS, RISKY_UNIVERSE, min_vol_pair
from build_dashboard import _b_monthly_signal_dates, alpha_beta_corr
from run_peer_audit import fetch_extra_etfs, get_monthly_rets
from faa_canonical import FAA_UNIVERSE, FAA_SAFE
from eaa_canonical import EAA_UNIVERSE, EAA_SAFE
from daa_canonical import DAA_UNIVERSE, DAA_SAFE

# Define universes
AAA_PAAA_EAA_UNIVERSE = EAA_UNIVERSE   # 10 assets
DAA_GPM_UNIVERSE = DAA_UNIVERSE        # 12 assets


def compute_cpm_weights_custom(close_panel, sig_d, universe, safe_asset):
    """Run final upgraded CPM spec on an arbitrary universe:
       - Canary: HYG OR TIP any_positive
       - Ranker: EAA Vol-Adj (Faber / Vol_252d)
       - Selection: top-K = ceil(N/2) candidates
       - Weights: min-vol pair (50/50) over 504d cov
    """
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    daily = close_panel.loc[:sig_d]

    # 1. Canary check
    canary_passes = []
    for c in ["HYG", "TIP"]:
        if c not in monthly.columns: continue
        mom = sig_13612U(monthly[c])
        canary_passes.append(pd.notna(mom) and mom > 0)
    canary_ok = any(canary_passes)

    actual_safe = safe_asset if safe_asset in close_panel.columns else "SHV"
    if not canary_ok:
        return {actual_safe: 1.0}

    avail = [t for t in universe if t in monthly.columns and t in daily.columns]
    if not avail:
        return {actual_safe: 1.0}

    # 2. Vol-Adj Faber Ranking
    daily_rets = close_panel[avail].ffill().pct_change()
    
    faber = {}
    for t in avail:
        s = monthly[t].dropna()
        if len(s) < 10: continue
        faber[t] = (s.iloc[-1] - s.tail(10).mean()) / s.tail(10).mean()

    scores = {}
    for t in avail:
        if t not in faber: continue
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9: v = 1.0
        scores[t] = float(faber[t]) / v

    # Rank top-half of the universe
    N = len(avail)
    top_k_candidates = max(2, math.ceil(N / 2.0))
    
    # Filter to positive-momentum only (Faber > 0)
    sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
    candidates = [t for t, _ in sorted_scores[:top_k_candidates] if faber.get(t, -np.inf) > 0]

    if len(candidates) < 2:
        if len(candidates) == 1:
            return {candidates[0]: 0.5, actual_safe: 0.5}
        return {actual_safe: 1.0}

    # 3. Min-vol pair 50/50 over 504d cov
    pair = min_vol_pair(daily, candidates, CORR_LOOKBACK_DAYS)
    if pair is None:
        pair = (candidates[0], candidates[1])

    return {pair[0]: 0.5, pair[1]: 0.5}


def main():
    print("Loading base proxy panel ...")
    base_panel = load_panel(start=pd.Timestamp("1996-01-01"))
    start = pd.Timestamp("2008-05-30")   # strict live-only start
    end = pd.Timestamp("2026-05-22")

    # missing peer-universe ETFs download
    all_peer_tickers = set(FAA_UNIVERSE + EAA_UNIVERSE + DAA_UNIVERSE + ["VWO", "AGG", "BIL", "IBB", "VEA"])
    extra_tickers = sorted(all_peer_tickers - set(base_panel.columns))
    extra_px = fetch_extra_etfs(extra_tickers)

    # Merge master panel
    master_df = base_panel.copy()
    for t, s in extra_px.items():
        master_df[t] = s
    master_df = master_df.ffill().dropna(how="all")
    daily_rets = master_df.pct_change().fillna(0.0)

    sig_dates = _b_monthly_signal_dates(master_df, start, end)
    common_idx = daily_rets.loc[start:end].index

    # Run CPM in each of the alternative universes
    runs = []

    # 1. AAA / PAAA / EAA Universe (10 assets, SHV safe)
    print("Running CPM on AAA/PAAA/EAA 10-asset universe ...")
    w_aaa = [ (sd, compute_cpm_weights_custom(master_df, sd, AAA_PAAA_EAA_UNIVERSE, "SHV")) for sd in sig_dates ]
    runs.append(("CPM on AAA/PAAA/EAA Universe (10 assets, SHV)", get_monthly_rets(daily_rets, w_aaa, start, end)))

    # 2. DAA / GPM Universe (12 assets, SHV safe)
    print("Running CPM on DAA/GPM 12-asset universe ...")
    w_daa = [ (sd, compute_cpm_weights_custom(master_df, sd, DAA_GPM_UNIVERSE, "SHV")) for sd in sig_dates ]
    runs.append(("CPM on DAA/GPM Universe (12 assets, SHV)", get_monthly_rets(daily_rets, w_daa, start, end)))

    # 3. FAA Universe (7 assets, SHY safe)
    print("Running CPM on FAA 7-asset universe ...")
    w_faa = [ (sd, compute_cpm_weights_custom(master_df, sd, FAA_UNIVERSE, "SHY")) for sd in sig_dates ]
    runs.append(("CPM on FAA Universe (7 assets, SHY)", get_monthly_rets(daily_rets, w_faa, start, end)))

    # 4. Custom CPM Universe (9 assets, SHV safe) — REFERENCE
    print("Running CPM on Custom CPM 9-asset universe (Baseline) ...")
    w_cpm = [ (sd, compute_cpm_weights_custom(master_df, sd, RISKY_UNIVERSE, "SHV")) for sd in sig_dates ]
    runs.append(("CPM on Custom CPM Universe (9 assets, SHV)  [Baseline]", get_monthly_rets(daily_rets, w_cpm, start, end)))

    print(f"\n{'='*140}")
    print(f"CPM CROSS-UNIVERSE SENSITIVITY ROBUSTNESS CHECK (2008-05-30 to 2026-05-22, 10bps/side cost)")
    print(f"{'='*140}")
    print(f"{'Strategy Universe Config':<60} {'Sharpe':>8} {'CAGR':>8} {'MaxDD':>9} {'Calmar':>8}")
    print("-" * 140)
    for name, r in runs:
        m = perf_metrics(r)
        cal = m["cagr"]/abs(m["max_drawdown"]) if m["max_drawdown"] else 0
        print(f"{name:<60} {m['sharpe']:>8.3f} {m['cagr']*100:>7.2f}% {m['max_drawdown']*100:>8.2f}% {cal:>8.2f}")
    print(f"====================================================================================================")


if __name__ == "__main__":
    main()
