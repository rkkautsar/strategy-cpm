"""
FCP Probabilistic Sharpe Ratio (PSR) / Deflated Sharpe analysis.

Bailey/Lopez de Prado 2014. Account for selection bias from sweep tuning.

For each plausible N (number of effective trials tested), compute PSR:
P(true SR > threshold under null with N trials).

PSR > 95% = robustly above null. Below = selection bias plausible.

Tests:
  - FCP production (vol-target ON and OFF) on extended 28.7y
  - FCP production on live-only 18y
  - Sensitivity to N_trials estimate (10, 50, 100, 250, 500)

Compare to MVP's PSR (failed at N=50 live-only).
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from strategy_fcp.fcp_live import load_panel, run_fcp_backtest


def deflated_sharpe(point_sh_annual, n_obs_daily, n_trials, sk=0, kt=3):
    """Bailey/Lopez de Prado 2014 PSR.
    Returns (PSR, threshold_sr_annual).
    """
    sr = point_sh_annual / np.sqrt(252)
    var_sr = (1 - sk * sr + (kt - 1) / 4 * sr ** 2) / (n_obs_daily - 1)
    sr_std = np.sqrt(var_sr)
    e_gamma = 0.5772
    if n_trials < 2:
        e_max_std = 0.0
    else:
        e_max_std = (np.sqrt(2 * np.log(n_trials))
                     - (e_gamma + np.log(np.log(n_trials))) / np.sqrt(2 * np.log(n_trials)))
    sr_threshold = e_max_std * sr_std
    z = (sr - sr_threshold) / sr_std
    psr = norm.cdf(z)
    return float(psr), float(sr_threshold * np.sqrt(252))


def get_fcp_returns(panel, start, end, vol_target=True):
    daily, _ = run_fcp_backtest(panel, start, end, apply_vol_target=vol_target)
    return daily.dropna()


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    print("=" * 145)
    print("FCP DEFLATED SHARPE / PSR ANALYSIS")
    print("Bailey & Lopez de Prado 2014: P(true SR > E[max under null with N trials])")
    print("=" * 145)

    print("""
Number of distinct strategy variants effectively tested across FCP development:
  - Universe (factor lists, intl, diversifiers) ~ 5
  - TOP_K_CANDIDATES (3 5, 7, 10, 12, 15) ~ 6
  - HOLD_BUFFER (0, 1, 2, 3, 4, 5) ~ 6
  - CORR_LOOKBACK_DAYS (126, 189, 252, 378, 504, 756) ~ 6
  - TARGET_VOL (6, 8, 10, 12, 15, 20) ~ 6
  - VOL_LOOKBACK_DAYS (21, 42, 63, 126, 252) ~ 5
  - MAX_LEVERAGE (1.0, 1.2, 1.5, 2.0) ~ 4
  - Vol target on/off ~ 2
  - Canary variants tested historically ~ 4
  - Pair selection rule (lowcorr/minvol/topK/lowvol) ~ 4
  - Cost levels tested ~ 5
  - Signal (Faber SMA, 13612W, 6mo) ~ 3
  - SAFE_POOL composition ~ 3

  Conservative product N: ~50-100 effective trials.
  Aggressive product (cross effects): ~250-500.
""")

    # FCP returns
    print("=" * 145)
    print("Extended 28.7y window (1997-08 to 2026-05)")
    print("=" * 145)
    for vt in [True, False]:
        r = get_fcp_returns(panel, hybrid_start, end, vol_target=vt)
        n_obs = len(r)
        sh = (r.mean() * 252) / (r.std() * np.sqrt(252))
        tag = "vol-target ON" if vt else "vol-target OFF"
        print(f"\n  FCP {tag}: point Sharpe = {sh:.3f}, n_obs = {n_obs}")
        print(f"  {'N trials':>10s}  {'threshold SR':>14s}  {'PSR':>7s}  {'Survives?':>10s}")
        print("  " + "-" * 50)
        for n_trials in [1, 10, 50, 100, 250, 500, 1000]:
            psr, thr = deflated_sharpe(sh, n_obs, n_trials)
            survives = "YES *" if psr >= 0.95 else "no"
            print(f"  {n_trials:>10d}  {thr:>13.3f}  {psr*100:>6.1f}%  {survives:>10s}")

    print()
    print("=" * 145)
    print("Live-only 18y window (2008-09 to 2026-05)")
    print("=" * 145)
    for vt in [True, False]:
        r = get_fcp_returns(panel, live_start, end, vol_target=vt)
        n_obs = len(r)
        sh = (r.mean() * 252) / (r.std() * np.sqrt(252))
        tag = "vol-target ON" if vt else "vol-target OFF"
        print(f"\n  FCP {tag}: point Sharpe = {sh:.3f}, n_obs = {n_obs}")
        print(f"  {'N trials':>10s}  {'threshold SR':>14s}  {'PSR':>7s}  {'Survives?':>10s}")
        print("  " + "-" * 50)
        for n_trials in [1, 10, 50, 100, 250, 500, 1000]:
            psr, thr = deflated_sharpe(sh, n_obs, n_trials)
            survives = "YES *" if psr >= 0.95 else "no"
            print(f"  {n_trials:>10d}  {thr:>13.3f}  {psr*100:>6.1f}%  {survives:>10s}")

    # Reference: MVP (already established to fail at N>=50)
    print()
    print("=" * 145)
    print("REFERENCE: MVP comparison (live-only 18y)")
    print("=" * 145)
    print("  MVP standalone Sharpe ~0.76 (live-only 18y)")
    print("  N_trials = 10:  PSR ~96%")
    print("  N_trials = 50:  PSR ~88%  (FAILS robustness threshold)")
    print("  N_trials = 100: PSR ~83%  (FAILS)")
    print("  -> MVP marked as selection-bias-suspect, archived as not-deployable")
    print("  Compare above: does FCP do better or worse?")


if __name__ == "__main__":
    main()
