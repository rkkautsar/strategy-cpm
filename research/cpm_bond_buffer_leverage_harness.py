"""Throwaway research (SCOPED, read-only; writes research/ only).

IDEA (user, from https://nlxfinance.wordpress.com/2024/03/07/the-haa-strategy-revisited/):
HAA-Simple revisited replaces the 100% SPY offensive leg with a 60/40 SPY/IEF
blend (HAA.60.40); the always-on bond pocket (cushioned by a TIP/IEF momentum
filter that suspends the position when stock-bond decorrelation is likely to
fail) lowers vol enough to optionally apply leverage (HAA.75.75 = 75% SPY
futures + 75% IEF; HAA.100.50 = 100% SPY futures + 50% IEF) to beat plain SPY /
unlevered HAA at controlled risk. Article ignores fees/spreads/financing and
uses futures for the levered legs.

CPM ANALOG: CPM already dynamically routes to bonds (TLT when trending,
IEF/SHV when defensive). Test whether an ALWAYS-ON bond buffer / dedicated
diversifier slot adds risk reduction BEYOND CPM's dynamic routing (unlevered),
then whether a levered-buffered blend beats unlevered CPM / 60/40 (levered).

ANCHOR: CPM clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615 / Martin 3.9646.

Reuses production engine (cpm_live.compute_target_weights) + the memo's mooex
T+1 MOO exact harness (_segment_returns_conv). All variants -- CPM, blends,
diversifier slots, leverage -- pass through the SAME accounting (T+1 MOO exact,
10 bps/side, monthly rebalance, point-in-time signals).
"""
import sys, math, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import bull_spy_live  # noqa: F401 (harness parity; H reads bull_spy_live._vol_gate_ok)
# exec_lag module is stale vs current bull_spy_live (vol gate renamed/removed).
# We only use H._segment_returns_conv + H.load_open_close (gate-independent), so
# stub the attribute the module reads at import time. No bull sleeve is used here.
if not hasattr(bull_spy_live, "_vol_gate_ok"):
    bull_spy_live._vol_gate_ok = lambda *a, **k: (True, {})

# PROD BASELINE UPDATE: CPM is now standardized to BOTH-252 (rank-vol AND
# weight-vol both 252d; cpm_live.CORR_LOOKBACK_DAYS = 252). The both-252 prod
# anchor is clean Sharpe 1.1658 / MaxDD -12.97% / Calmar 1.0137 (NOT the old
# 504-config 1.1910 / -12.67% / 1.0615). Pin 252 in-process so the anchor
# reproduces deterministically regardless of working-tree state. (Read-only: sets
# the in-process module constant for THIS research run; cpm_live.py is not edited.)
import cpm_live as _cpm_live
_cpm_live.CORR_LOOKBACK_DAYS = 252
from cpm_live import (
    load_panel, perf_metrics, compute_target_weights, best_safe,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
import exec_lag_moo_validation_2026_05_30 as H

CONV = "mooex"
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")   # bonds (IEF/TLT/BND) available from ~2005-10 in panel
END = pd.Timestamp("2026-05-22")
SEED = 12345
B = 2000
BLOCK = 21
BORROW_SPREAD_BPS = 50.0   # financing = SHV t-bill rate + 50 bps on borrowed notional


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def build_data():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    open_df, close_yf = H.load_open_close()
    panel = panel[panel.index <= end].sort_index()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    return panel, intraday, overnight, end


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "ulcer": m.get("ulcer"),
            "excess_sharpe": m.get("excess_sharpe")}


def sharpe_of(r):
    v = r.std(ddof=0) * np.sqrt(252)
    return float((r.mean() * 252) / v) if v > 0 else float("nan")


def run_wf(close, daily, intraday, overnight, start, end, wf):
    s, fb = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                    COST_BPS_PER_SIDE, intraday, overnight)
    return s


def paired_block_bootstrap(a_s, b_s, block=BLOCK, B=B, seed=SEED):
    common = a_s.index.intersection(b_s.index)
    a = a_s.reindex(common).fillna(0.0).values
    b = b_s.reindex(common).fillna(0.0).values
    n = len(a)
    point = sharpe_of(pd.Series(a)) - sharpe_of(pd.Series(b))
    if n < block * 3:
        return {"point": point, "lo": float("nan"), "hi": float("nan"), "includes_zero": True}
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / block))
    pool = np.arange(0, n - block + 1)
    diffs = np.empty(B)
    for i in range(B):
        starts = rng.choice(pool, size=nb, replace=True)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        ra, rb = a[idx], b[idx]
        va = ra.std(ddof=0) * np.sqrt(252); vb = rb.std(ddof=0) * np.sqrt(252)
        sa = (ra.mean() * 252) / va if va > 0 else np.nan
        sb = (rb.mean() * 252) / vb if vb > 0 else np.nan
        diffs[i] = sa - sb
    lo, hi = np.nanpercentile(diffs, [2.5, 97.5])
    return {"point": float(point), "lo": float(lo), "hi": float(hi),
            "includes_zero": bool(lo <= 0.0 <= hi)}


# --------------------------------------------------------------------------
# weight functions
# --------------------------------------------------------------------------
def cpm_wf(close):
    return lambda sd: compute_target_weights(close, sd)[0]


def blend_wf(close, w_cpm, bond):
    """Static blend: w_cpm * CPM + (1-w_cpm) * single fixed bond. Monthly rebal."""
    base = cpm_wf(close)
    def wf(sd):
        cw = {t: v * w_cpm for t, v in base(sd).items()}
        cw[bond] = cw.get(bond, 0.0) + (1.0 - w_cpm)
        return cw
    return wf


def diversifier_dyn_wf(close, frac):
    """Dedicated diversifier slot: always-on `frac` to the DYNAMIC safe asset
    (best_safe IEF/SHV duration selector), CPM on the remaining (1-frac).
    Distinct from the static-bond blend because the buffer's duration adapts."""
    base = cpm_wf(close)
    def wf(sd):
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE_POOL)
        cw = {t: v * (1.0 - frac) for t, v in base(sd).items()}
        cw[safe] = cw.get(safe, 0.0) + frac
        return cw
    return wf


def sixty40_wf():
    return lambda sd: {"SPY": 0.60, "IEF": 0.40}


# --------------------------------------------------------------------------
# leverage overlays (applied to a post-cost daily return series)
# --------------------------------------------------------------------------
def lever_series(r, cash_daily, L, spread_bps=BORROW_SPREAD_BPS):
    """Constant leverage L with financing on the borrowed (L-1) notional.
    financing_daily = cash (SHV) daily return + spread/252."""
    spread_d = spread_bps / 10000.0 / 252.0
    fin = cash_daily.reindex(r.index).fillna(0.0) + spread_d
    return L * r - (L - 1.0) * fin


def voltarget_capped(r, target_vol, lookback=21, cap=1.0):
    """Vol-target overlay that only DE-levers (exposure capped at `cap`, never
    levers up in calm). Scales next-day exposure by target/realized using a
    trailing window (point-in-time, shifted by 1)."""
    rv = r.rolling(lookback).std(ddof=0) * np.sqrt(252)
    expo = (target_vol / rv).clip(upper=cap).shift(1).fillna(cap)
    return expo * r


# --------------------------------------------------------------------------
def main():
    panel, intraday, overnight, end = build_data()
    cash = panel["SHV"].ffill().pct_change().dropna()
    bm_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS +
                         [DEFAULT_CASH, "SPY", "IEF", "TLT", "BND"]) & set(panel.columns))
    close = panel[bm_cols]
    daily = close.ffill().pct_change()
    print(f"Panel {panel.index[0].date()} -> {end.date()} ({len(panel)} rows)")
    print(f"Convention={CONV} cost={COST_BPS_PER_SIDE}bps/side borrow=SHV+{BORROW_SPREAD_BPS}bps\n")

    def clean(s):
        return s.loc[(s.index >= CLEAN_START) & (s.index <= end)]

    def extw(s, start):
        return s.loc[(s.index >= start) & (s.index <= end)]

    out = {"meta": {"convention": CONV, "cost_bps": COST_BPS_PER_SIDE,
                    "borrow_spread_bps": BORROW_SPREAD_BPS,
                    "clean_start": str(CLEAN_START.date()), "end": str(end.date())},
           "anchor": {}, "static_blend": {}, "diversifier_slot": {},
           "leverage": {}, "diff_ci": {}}

    # ---- anchor + baselines ----
    cpm = run_wf(close, daily, intraday, overnight, EXT_START, end, cpm_wf(close))
    sixty = run_wf(close, daily, intraday, overnight, EXT_START, end, sixty40_wf())
    mc = met(clean(cpm), cash)
    out["anchor"]["CPM_clean"] = mc
    print("=== ANCHOR (CLEAN 18y, mooex) ===")
    print(f"  CPM Sharpe={mc['sharpe']:.4f} MaxDD={mc['maxdd']*100:.2f}% "
          f"Calmar={mc['calmar']:.4f} Martin={mc['martin']:.4f} Vol={mc['vol']*100:.2f}%")
    print("  (expect both-252 prod: 1.1658 / -12.97% / 1.0137)\n")
    out["anchor"]["60_40_clean"] = met(clean(sixty), cash)

    # bond first-valid (affects buffered-blend start, since bond is always-on)
    bond_fv = {b: (close[b].first_valid_index()) for b in ["IEF", "TLT", "BND"] if b in close.columns}
    # buffered blends only valid once the always-on bond exists; use clean window
    # (2008+) where IEF/TLT/BND all live (panel bonds start 2005-10).

    # ---- (a) STATIC BLEND ----
    print("=== (a) STATIC BLEND: w*CPM + (1-w)*bond (clean 18y) ===")
    for bond in ["IEF", "TLT", "BND"]:
        if bond not in close.columns:
            continue
        out["static_blend"][bond] = {}
        for w in [1.0, 0.9, 0.8, 0.7, 0.6]:
            s = run_wf(close, daily, intraday, overnight, CLEAN_START, end, blend_wf(close, w, bond))
            m = met(clean(s), cash)
            out["static_blend"][bond][f"w{w}"] = m
            tag = "CPM(w=1.0)" if w == 1.0 else f"w={w}"
            print(f"  {bond:>3} {tag:>10}: Sharpe={m['sharpe']:.4f} Vol={m['vol']*100:5.2f}% "
                  f"MaxDD={m['maxdd']*100:6.2f}% Calmar={m['calmar']:.4f} Martin={m['martin']:.4f} CAGR={m['cagr']*100:5.2f}%")
        print()

    # ---- (b) DEDICATED DIVERSIFIER SLOT ----
    print("=== (b) DEDICATED DIVERSIFIER SLOT (clean 18y) ===")
    print("  NOTE: a fixed slot to a single static bond == (a) blend with w=1-frac.")
    print("  Distinct test: slot to DYNAMIC safe (best_safe IEF/SHV) -> duration-adaptive buffer.\n")
    for frac in [0.2, 0.3, 0.4]:
        s = run_wf(close, daily, intraday, overnight, CLEAN_START, end, diversifier_dyn_wf(close, frac))
        m = met(clean(s), cash)
        out["diversifier_slot"][f"dyn_frac{frac}"] = m
        print(f"  dyn-safe frac={frac}: Sharpe={m['sharpe']:.4f} Vol={m['vol']*100:5.2f}% "
              f"MaxDD={m['maxdd']*100:6.2f}% Calmar={m['calmar']:.4f} Martin={m['martin']:.4f} CAGR={m['cagr']*100:5.2f}%")
    print()

    # ---- (c) LEVERAGE on lowest-vol buffered blend ----
    # pick lowest-vol buffered blend across (a)+(b) by vol (exclude pure CPM w=1)
    cand = {}
    for bond, d in out["static_blend"].items():
        for k, m in d.items():
            if k == "w1.0":
                continue
            cand[f"{bond}/{k}"] = m["vol"]
    for k, m in out["diversifier_slot"].items():
        cand[k] = m["vol"]
    lowest = min(cand, key=cand.get)
    print(f"=== (c) LEVERAGE: lowest-vol buffered blend = {lowest} (vol={cand[lowest]*100:.2f}%) ===")

    # rebuild that blend's daily series
    if "/" in lowest:
        bond, wk = lowest.split("/")
        w = float(wk[1:])
        base_s = run_wf(close, daily, intraday, overnight, CLEAN_START, end, blend_wf(close, w, bond))
        label = f"{lowest} ({int(round((1-w)*100))}% {bond})"
    else:
        frac = float(lowest.replace("dyn_frac", ""))
        base_s = run_wf(close, daily, intraday, overnight, CLEAN_START, end, diversifier_dyn_wf(close, frac))
        label = f"dyn-safe {int(frac*100)}%"
    base_c = clean(base_s)
    cpm_c = clean(cpm)
    sixty_c = clean(sixty)
    out["leverage"]["base_label"] = label
    out["leverage"]["base"] = met(base_c, cash)

    # fixed 1.5x / 2x (article-faithful constant leverage)
    for L in [1.0, 1.5, 2.0]:
        ls = lever_series(base_c, cash, L)
        m = met(ls, cash)
        out["leverage"][f"L{L}"] = m
        print(f"  L={L}x  : Sharpe={m['sharpe']:.4f} Vol={m['vol']*100:5.2f}% "
              f"MaxDD={m['maxdd']*100:7.2f}% Calmar={m['calmar']:.4f} Martin={m['martin']:.4f} CAGR={m['cagr']*100:5.2f}%")

    # vol-matched-to-CPM leverage (IN-SAMPLE constant scale; illustrative)
    L_match = mc["vol"] / out["leverage"]["base"]["vol"]
    ls = lever_series(base_c, cash, L_match)
    mm = met(ls, cash)
    out["leverage"]["vol_matched"] = {"L": L_match, **mm}
    print(f"  L={L_match:.3f}x (vol-matched to CPM {mc['vol']*100:.2f}%, IN-SAMPLE): "
          f"Sharpe={mm['sharpe']:.4f} Vol={mm['vol']*100:.2f}% MaxDD={mm['maxdd']*100:.2f}% "
          f"Calmar={mm['calmar']:.4f} CAGR={mm['cagr']*100:.2f}%")

    # vol-target capped overlay (de-lever only) for contrast, target = CPM vol
    vt = voltarget_capped(base_c, mc["vol"], lookback=21, cap=1.0)
    mvt = met(vt, cash)
    out["leverage"]["voltarget_capped"] = mvt
    print(f"  vol-target capped@1x (target={mc['vol']*100:.2f}%): Sharpe={mvt['sharpe']:.4f} "
          f"Vol={mvt['vol']*100:.2f}% MaxDD={mvt['maxdd']*100:.2f}% Calmar={mvt['calmar']:.4f}")

    print("\n  Reference: unlevered CPM Sharpe={:.4f} Vol={:.2f}% MaxDD={:.2f}% Calmar={:.4f}".format(
        mc["sharpe"], mc["vol"]*100, mc["maxdd"]*100, mc["calmar"]))
    print("  Reference: 60/40     Sharpe={:.4f} Vol={:.2f}% MaxDD={:.2f}% Calmar={:.4f}".format(
        out["anchor"]["60_40_clean"]["sharpe"], out["anchor"]["60_40_clean"]["vol"]*100,
        out["anchor"]["60_40_clean"]["maxdd"]*100, out["anchor"]["60_40_clean"]["calmar"]))

    # ---- difference CIs (clean) ----
    print("\n=== PAIRED BLOCK-BOOTSTRAP 95% CI: Sharpe diff (clean) ===")
    tests = {
        "unlev_buffer_minus_CPM": (base_c, cpm_c),
        "L1.5_buffer_minus_CPM": (lever_series(base_c, cash, 1.5), cpm_c),
        "L2.0_buffer_minus_CPM": (lever_series(base_c, cash, 2.0), cpm_c),
        "volmatched_buffer_minus_CPM": (lever_series(base_c, cash, L_match), cpm_c),
        "unlev_buffer_minus_6040": (base_c, sixty_c),
        "L1.5_buffer_minus_6040": (lever_series(base_c, cash, 1.5), sixty_c),
    }
    for name, (a, b) in tests.items():
        ci = paired_block_bootstrap(a, b)
        out["diff_ci"][name] = ci
        print(f"  {name:>34}: dSharpe={ci['point']:+.4f} CI[{ci['lo']:+.4f},{ci['hi']:+.4f}] "
              f"{'(includes 0)' if ci['includes_zero'] else '(SIGNIFICANT)'}")

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    print(f"\nWrote {Path(__file__).with_suffix('.json').name}")


if __name__ == "__main__":
    main()
