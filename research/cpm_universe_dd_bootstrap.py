# -*- coding: utf-8 -*-
"""Follow-up: paired block bootstrap on MaxDD marginal (CLEAN) for the Treasury-in
variants (+IEF, +IEF -GLD) and -GLD vs prod. Tests whether the drawdown
difference is within noise. Read-only; no production touched; no commit."""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpm_universe_experiments as X
from cpm_live import load_panel, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, compute_target_weights
import exec_lag_moo_validation_2026_05_30 as H


def maxdd_of(r):
    r = r.dropna()
    if len(r) < 2:
        return np.nan
    eq = (1.0 + r).cumprod()
    return (eq / eq.cummax() - 1).min()


def boot_maxdd(var_s, prod_s, B=5000, block=21, seed=7):
    df = pd.concat([var_s.rename("v"), prod_s.rename("p")], axis=1).dropna()
    n = len(df); rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block)); idx = np.arange(n)
    v = df["v"].to_numpy(); p = df["p"].to_numpy()
    diffs = []
    for _ in range(B):
        starts = rng.integers(0, n - block + 1, size=nb)
        sel = np.concatenate([idx[s:s + block] for s in starts])[:n]
        diffs.append(maxdd_of(pd.Series(v[sel])) - maxdd_of(pd.Series(p[sel])))
    diffs = np.array(diffs)
    # marginal = variant_dd - prod_dd ; positive (less negative) = improvement
    return {"dd_marg_mean": float(np.nanmean(diffs)),
            "dd_marg_ci": [float(np.nanpercentile(diffs, 2.5)), float(np.nanpercentile(diffs, 97.5))],
            "p_improve": float(np.mean(diffs > 0)), "p_le0": float(np.mean(diffs <= 0)),
            "n": n, "B": B, "block": block}


def main():
    end = pd.Timestamp("2026-05-22"); ext = pd.Timestamp("1999-03-10"); clean = pd.Timestamp("2008-05-30")
    panel = load_panel(start=ext, end=end); end = min(end, panel.index[-1])
    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    cols = sorted(set(sum(X.VARIANTS.values(), []) + X.SAFE + X.CANARY) & set(panel.columns))
    close = panel[cols]; daily = close.ffill().pct_change()

    prod_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    prod_close = panel[prod_cols]; prod_daily = prod_close.ffill().pct_change()
    prod_s = X.run_series(prod_close, prod_daily, intraday, overnight,
                          lambda sd: compute_target_weights(prod_close, sd)[0], ext, end)
    ps_c = prod_s.loc[(prod_s.index >= clean) & (prod_s.index <= end)]

    targets = ["1.+IEF (offensive)", "7c.+IEF -GLD", "3.-GLD"]
    out = {}
    for name in targets:
        uni = X.VARIANTS[name]
        ser = X.run_series(close, daily, intraday, overnight,
                           lambda sd, u=uni: X.cpm_variant_wf(close, sd, u), ext, end)
        vs_c = ser.loc[(ser.index >= clean) & (ser.index <= end)]
        b = boot_maxdd(vs_c, ps_c)
        out[name] = b
        print(f"{name:<22} dd_marg(var-prod)={b['dd_marg_mean']*100:+.2f}pp "
              f"CI=[{b['dd_marg_ci'][0]*100:+.2f},{b['dd_marg_ci'][1]*100:+.2f}]pp "
              f"p(improve)={b['p_improve']:.3f}")
    json.dump(out, open(Path(__file__).resolve().parent / "cpm_universe_dd_bootstrap.json", "w"), indent=2)
    print("done")


if __name__ == "__main__":
    main()
