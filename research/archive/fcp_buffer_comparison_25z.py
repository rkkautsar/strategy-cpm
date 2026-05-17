"""
FCP HOLD_BUFFER ∈ {2.0, 2.5, 3.0} — Comprehensive Experimental Comparison
===========================================================================
EXPERIMENTS ONLY. No conclusions or recommendations. Raw empirical tables.

Sections
--------
1. PSR / Deflated Sharpe (Bailey/Lopez de Prado 2014)
   N_trials ∈ {50, 100, 250, 500, 1000}
   Windows: extended 28.7y (1997-08-31) + live-only 18y (2008-09-30)
   Vol-target: ON and OFF

2. SOTA peer comparison — extended metrics on live-only 18y
   FCP-2.0z, FCP-2.5z, FCP-3.0z vs AAA K=5 (HAA-9), AAA K=5+canary FCP-15,
   Keller HAA-Balanced, Faber GTAA-5, 60/40 SPY/IEF, PP-IEF, SPY buy-hold
   Metrics: Sharpe, Sortino, Calmar, MaxDD, UPI, Pain, Avg36mDD, SWR, CAGR, TO

3. Bootstrap Sharpe-difference (B=3000, block=21d)
   Each FCP-X vs each peer — point delta + 95% CI + P(>0)

4. Cost-stress: FCP at 5/10/20/40/80 bps RT cost × each buffer

5. Subwindow Sharpe split (2008-09→2014-12, 2015-01→2019-12, 2020-01→2026-05)
   Per buffer setting

Output: strategy_fcp/research/fcp_buffer_comparison_25z.log
"""
from __future__ import annotations
import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import minimize

# ── paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import (
    load_panel, sig_13612W, RISKY_UNIVERSE as FCP15,
    SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    faber_sma_xs, min_vol_pair, best_safe as fcp_best_safe,
    run_fcp_backtest,
)

LOG_PATH = ROOT / "strategy_fcp" / "research" / "fcp_buffer_comparison_25z.log"

BUFFERS = [2.0, 2.5, 3.0]
HYBRID_START = pd.Timestamp("1997-08-31")
LIVE_START   = pd.Timestamp("2008-09-30")

HAA9 = ["SPY","QQQ","IWM","VEA","VWO","VNQ","DBC","GLD","TLT"]
SAFE_POOL_AAA = ["SHV","IEF"]
COST_BPS_SIDE = 10

# ══════════════════════════════════════════════════════════════════════════
# Utility: logging to file + stdout simultaneously
# ══════════════════════════════════════════════════════════════════════════

_log_lines: list[str] = []

def log(line: str = "") -> None:
    _log_lines.append(line)
    print(line, flush=True)


def flush_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════
# Section 1 helpers — PSR / Deflated Sharpe
# ══════════════════════════════════════════════════════════════════════════

def deflated_sharpe(sh_ann: float, n_obs: int, n_trials: int, sk: float = 0, kt: float = 3):
    """Bailey/Lopez de Prado 2014. Returns (PSR, threshold_SR_annual)."""
    sr = sh_ann / np.sqrt(252)
    var_sr = (1 - sk * sr + (kt - 1) / 4 * sr**2) / max(n_obs - 1, 1)
    sr_std = np.sqrt(var_sr)
    e_gamma = 0.5772
    if n_trials < 2:
        e_max_std = 0.0
    else:
        e_max_std = (
            np.sqrt(2 * np.log(n_trials))
            - (e_gamma + np.log(np.log(n_trials))) / np.sqrt(2 * np.log(n_trials))
        )
    sr_threshold = e_max_std * sr_std
    z = (sr - sr_threshold) / sr_std
    psr = float(norm.cdf(z))
    return psr, float(sr_threshold * np.sqrt(252))


def fcp_daily_returns(panel, start, end, vol_target: bool) -> pd.Series:
    daily, _ = run_fcp_backtest(panel, start, end, apply_vol_target=vol_target)
    return daily.dropna()


def compute_psr_block(panel, end, buf_label, start, win_label):
    rows = []
    for vt in [True, False]:
        r = fcp_daily_returns(panel, start, end, vol_target=vt)
        n_obs = len(r)
        sh = (r.mean() * 252) / (r.std() * np.sqrt(252))
        vt_tag = "ON " if vt else "OFF"
        for n_trials in [50, 100, 250, 500, 1000]:
            psr, thr = deflated_sharpe(sh, n_obs, n_trials)
            survives = "YES" if psr >= 0.95 else "no"
            rows.append(dict(
                buffer=buf_label, window=win_label, vol_target=vt_tag,
                point_sharpe=sh, n_obs=n_obs, n_trials=n_trials,
                threshold_sr=thr, psr=psr, survives=survives
            ))
    return rows


# ══════════════════════════════════════════════════════════════════════════
# Peer strategies (borrowed from fcp_aaa_sota_extended)
# ══════════════════════════════════════════════════════════════════════════

def get_eom_dates(panel, start, end):
    idx = panel.loc[start:end].index
    return list(pd.Series(idx).groupby(idx.to_period("M")).last())


def best_safe_aaa(monthly):
    avail = [s for s in SAFE_POOL_AAA if s in monthly.columns and pd.notna(monthly[s].iloc[-1])]
    if not avail: return DEFAULT_CASH
    sc = {s: sig_13612W(monthly[s]) for s in avail}
    sc = {k: v for k, v in sc.items() if pd.notna(v)}
    return max(sc, key=sc.get) if sc else avail[0]


def dynamic_avail(panel, sig_d, universe, daily_lb=252):
    monthly = panel.loc[:sig_d].resample("ME").last()
    out = []
    for u in universe:
        if u not in panel.columns: continue
        m = monthly[u].dropna() if u in monthly.columns else pd.Series(dtype=float)
        d = panel[u].loc[:sig_d].dropna()
        if len(m) < 13 or len(d) < daily_lb: continue
        out.append(u)
    return out


def canary_pass(panel, sig_d):
    monthly = panel.loc[:sig_d].resample("ME").last()
    scs = []
    for c in CANARY_ASSETS:
        if c not in monthly.columns: continue
        s = sig_13612W(monthly[c])
        if pd.notna(s): scs.append(s)
    if not scs: return False
    return sum(1 for s in scs if s > 0) > len(scs) // 2


def mom_6mo(panel, sig_d, asset):
    p = panel[asset].loc[:sig_d].dropna()
    if len(p) < 127: return np.nan
    return p.iloc[-1] / p.iloc[-127] - 1


def aaa_canonical(panel, sig_d, universe=HAA9, K=5, apply_canary=False):
    monthly = panel.loc[:sig_d].resample("ME").last()
    bs = best_safe_aaa(monthly)
    if apply_canary and not canary_pass(panel, sig_d):
        return {bs: 1.0}
    avail = dynamic_avail(panel, sig_d, universe, daily_lb=126)
    moms = {u: mom_6mo(panel, sig_d, u) for u in avail}
    moms = {k: v for k, v in moms.items() if pd.notna(v) and v > 0}
    if len(moms) < 2: return {bs: 1.0}
    ranked = sorted(moms.items(), key=lambda kv: kv[1], reverse=True)[:K]
    selected = [u for u, _ in ranked]
    if len(selected) < 2: return {bs: 1.0}
    rets_c = panel.loc[:sig_d, selected].iloc[-126:].pct_change().dropna()
    rets_v = panel.loc[:sig_d, selected].iloc[-20:].pct_change().dropna()
    if len(rets_c) < 63 or len(rets_v) < 10: return {bs: 1.0}
    corr = rets_c.corr().values
    vols = rets_v.std().values
    cov = corr * np.outer(vols, vols)
    n = len(selected)
    cons = ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)
    bnds = [(0.0, 1.0)] * n
    x0 = np.ones(n) / n
    res = minimize(lambda w: w @ cov @ w, x0, method="SLSQP", bounds=bnds,
                   constraints=cons, options={"maxiter": 200, "ftol": 1e-9})
    w = res.x if res.success else x0
    return {selected[i]: float(w[i]) for i in range(n) if w[i] > 1e-4}


def haa_balanced(panel, sig_d):
    monthly = panel.loc[:sig_d].resample("ME").last()
    bs = best_safe_aaa(monthly)
    if "TIP" in monthly.columns and pd.notna(monthly["TIP"].iloc[-1]):
        tip_s = sig_13612W(monthly["TIP"])
        if pd.isna(tip_s) or tip_s <= 0: return {bs: 1.0}
    avail = dynamic_avail(panel, sig_d, ["SPY","IWM","VEA","VWO","VNQ","DBC","GLD","TLT"])
    scs = {u: sig_13612W(monthly[u]) for u in avail}
    scs = {k: v for k, v in scs.items() if pd.notna(v)}
    if not scs: return {bs: 1.0}
    ranked = sorted(scs.items(), key=lambda kv: kv[1], reverse=True)[:4]
    n = len(ranked); w = {}
    for t, sc in ranked:
        if sc > 0: w[t] = w.get(t, 0) + 1.0/n
        else:       w[bs] = w.get(bs, 0) + 1.0/n
    return w


def faber_gtaa5(panel, sig_d):
    monthly = panel.loc[:sig_d].resample("ME").last()
    weights = {}
    for asset in ["SPY","EFA","IEF","VNQ","DBC"]:
        if asset not in monthly.columns: continue
        p = monthly[asset].dropna()
        if len(p) < 11: continue
        sma = p.iloc[-11:-1].mean()
        if p.iloc[-1] > sma: weights[asset] = 0.20
    cash = 1.0 - sum(weights.values())
    if cash > 0.001: weights["SHV"] = cash
    return weights or {"SHV": 1.0}


def static_60_40(p, d):   return {"SPY": 0.6, "IEF": 0.4}
def static_pp_ief(p, d):  return {"SPY": 0.25, "IEF": 0.25, "GLD": 0.25, "SHV": 0.25}
def buyhold_spy(p, d):    return {"SPY": 1.0}


def simulate(panel, start, end, target_fn, cost_bps=COST_BPS_SIDE):
    eom = get_eom_dates(panel, start, end)
    target_at = {}
    for d in eom:
        try: w = target_fn(panel, d)
        except Exception: continue
        future = panel.loc[d:].index
        if len(future) >= 2: target_at[future[1]] = w
    daily_ret = panel.pct_change()
    eq = 1.0; holdings = {}; nav = []; turnovers = []
    for d in panel.loc[start:end].index:
        if holdings:
            r = sum(w * daily_ret.loc[d, t]
                    for t, w in holdings.items()
                    if t in daily_ret.columns and pd.notna(daily_ret.loc[d, t]))
            eq *= (1 + r)
        if d in target_at:
            new_w = target_at[d]
            old_w = holdings.copy()
            all_t = set(old_w) | set(new_w)
            to = sum(abs(new_w.get(t, 0) - old_w.get(t, 0)) for t in all_t)
            turnovers.append(to)
            eq *= (1 - to * cost_bps / 10000.0)
            holdings = new_w
        nav.append((d, eq))
    df = pd.DataFrame(nav, columns=["date","equity"]).set_index("date")
    df["daily_ret"] = df["equity"].pct_change()
    return df, np.array(turnovers)


# ══════════════════════════════════════════════════════════════════════════
# Extended metrics
# ══════════════════════════════════════════════════════════════════════════

def ulcer_index(eq_s):
    cummax = eq_s.cummax()
    dd = (eq_s / cummax - 1) * 100
    return float(np.sqrt((dd**2).mean()))


def upi_martin(eq_s):
    n_y = len(eq_s.pct_change().dropna()) / 252.0
    cagr = (eq_s.iloc[-1] / eq_s.iloc[0]) ** (1 / n_y) - 1
    ulcer = ulcer_index(eq_s)
    return (cagr * 100) / ulcer if ulcer > 0 else np.nan


def pain_index(eq_s):
    cummax = eq_s.cummax()
    dd = (eq_s / cummax - 1) * 100
    return float(-dd.mean())


def rolling_36m_dd(eq_s):
    window_days = 36 * 21
    if len(eq_s) < window_days: return np.nan
    rolling_max = eq_s.rolling(window_days, min_periods=1).max()
    rolling_dd = (eq_s / rolling_max - 1) * 100
    worst_in_window = rolling_dd.rolling(window_days).min()
    return float(worst_in_window.mean())


def safe_withdrawal_rate(eq_s):
    daily_returns = eq_s.pct_change().dropna()
    n_years = int(len(daily_returns) / 252)
    if n_years < 5: return np.nan
    annual_returns = []
    for y in range(n_years):
        chunk = daily_returns.iloc[y*252:(y+1)*252]
        if len(chunk) > 0:
            annual_returns.append((1 + chunk).prod() - 1)
    annual_returns = np.array(annual_returns)
    survivors = []
    for w_rate in np.arange(0.02, 0.15, 0.0025):
        capital = 1.0; survived = True
        for r in annual_returns:
            capital = capital * (1 + r) - w_rate
            if capital <= 0: survived = False; break
        if survived: survivors.append(w_rate)
    return max(survivors) * 100 if survivors else 0.0


def all_metrics(eq):
    r = eq["daily_ret"].dropna() if isinstance(eq, pd.DataFrame) else eq.pct_change().dropna()
    eq_s = eq["equity"] if isinstance(eq, pd.DataFrame) else eq
    if r.empty: return {}
    n_y = len(r) / 252.0
    cagr = eq_s.iloc[-1] ** (1/n_y) - 1
    vol = r.std() * np.sqrt(252)
    sh = (r.mean()*252) / vol if vol > 0 else np.nan
    dd = (eq_s / eq_s.cummax() - 1).min()
    dn = r[r < 0].std() * np.sqrt(252) if len(r[r<0]) > 1 else np.nan
    sortino = (r.mean()*252) / dn if dn and dn > 0 else np.nan
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    return dict(
        years=round(n_y, 1), cagr=cagr, vol=vol, sharpe=sh,
        sortino=sortino, calmar=calmar, maxdd=dd,
        upi=upi_martin(eq_s), pain=pain_index(eq_s),
        avg_36m_dd=rolling_36m_dd(eq_s),
        swr=safe_withdrawal_rate(eq_s),
    )


def fcp_eq_from_daily(daily_ret: pd.Series) -> pd.DataFrame:
    eq = (1 + daily_ret.fillna(0)).cumprod()
    return pd.DataFrame({"equity": eq, "daily_ret": daily_ret})


# ══════════════════════════════════════════════════════════════════════════
# Bootstrap helpers
# ══════════════════════════════════════════════════════════════════════════

def block_bootstrap_sharpe_ci(daily, B=3000, block=21, seed=42):
    r = daily.dropna().values
    n = len(r)
    if n < block * 2: return np.nan, np.nan
    rng = np.random.default_rng(seed)
    n_blocks = n // block + 1
    starts = rng.integers(0, n - block + 1, size=(B, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(B, -1)[:, :n]
    samples = r[idx]
    m = samples.mean(axis=1) * 252
    s = samples.std(axis=1) * np.sqrt(252)
    sharpes = np.where(s > 0, m / s, 0.0)
    return float(np.percentile(sharpes, 2.5)), float(np.percentile(sharpes, 97.5))


def bootstrap_diff(daily_a, daily_b, B=3000, block=21, seed=42):
    df = pd.concat([daily_a.rename("a"), daily_b.rename("b")], axis=1).dropna()
    a = df["a"].values; b = df["b"].values
    n = len(a)
    if n < block * 2: return np.nan, np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    n_blocks = n // block + 1
    starts = rng.integers(0, n - block + 1, size=(B, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(B, -1)[:, :n]
    sa, sb = a[idx], b[idx]
    ma = sa.mean(axis=1)*252; sda = sa.std(axis=1)*np.sqrt(252) + 1e-9
    mb = sb.mean(axis=1)*252; sdb = sb.std(axis=1)*np.sqrt(252) + 1e-9
    diffs = (ma/sda) - (mb/sdb)
    pt_a = (a.mean()*252)/(a.std()*np.sqrt(252))
    pt_b = (b.mean()*252)/(b.std()*np.sqrt(252))
    return (pt_a - pt_b,
            float(np.percentile(diffs, 2.5)),
            float(np.percentile(diffs, 97.5)),
            float((diffs > 0).mean()))


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    log(f"FCP HOLD_BUFFER COMPARISON — EXPERIMENT LOG")
    log(f"Generated: {pd.Timestamp.now().isoformat()}")
    log(f"Buffers tested: {BUFFERS}")
    log(f"Python: {sys.version.split()[0]}")
    log()

    # ─── load panel once ──────────────────────────────────────────────────
    log("Loading price panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    log(f"Panel: {panel.index[0].date()} → {end.date()}, {len(panel.columns)} assets")
    log()

    # Pre-compute FCP returns for each buffer × vol_target × window
    # Store as dict keyed by (buf, vt, win)
    log("Pre-computing FCP backtests for all (buffer × vol_target × window) combinations ...")
    fcp_returns: dict = {}
    for buf in BUFFERS:
        fcp.HOLD_BUFFER = buf
        for vt in [True, False]:
            for win_label, wstart in [("hybrid28", HYBRID_START), ("live18", LIVE_START)]:
                key = (buf, vt, win_label)
                r, _ = run_fcp_backtest(panel, wstart, end, apply_vol_target=vt)
                fcp_returns[key] = r.dropna()
                log(f"  buf={buf} vt={'ON' if vt else 'OFF'} {win_label}: n={len(fcp_returns[key])} days, Sh={fcp_returns[key].mean()*252/fcp_returns[key].std()/np.sqrt(252):.3f}")

    # Restore to default
    fcp.HOLD_BUFFER = 3.0

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 1: PSR / Deflated Sharpe
    # ══════════════════════════════════════════════════════════════════════
    log()
    log("=" * 160)
    log("SECTION 1: PSR / DEFLATED SHARPE  (Bailey & Lopez de Prado 2014)")
    log("  P(true SR > expected max under null with N_trials)")
    log("  PSR ≥ 95%  →  'YES'  (survives selection-bias correction at 5% level)")
    log("=" * 160)
    log()

    hdr = (f"  {'Buffer':>8s}  {'Window':>12s}  {'VT':>4s}  {'PointSh':>8s}  "
           f"{'N_obs':>6s}  {'N_trials':>9s}  {'ThrSR':>7s}  {'PSR':>7s}  {'Survives':>9s}")
    div = "  " + "-" * (len(hdr) - 2)
    log(hdr)
    log(div)

    for buf in BUFFERS:
        for win_label, wstart in [("hybrid28", HYBRID_START), ("live18", LIVE_START)]:
            for vt in [True, False]:
                r = fcp_returns[(buf, vt, win_label)]
                n_obs = len(r)
                sh = (r.mean() * 252) / (r.std() * np.sqrt(252))
                vt_tag = "ON " if vt else "OFF"
                for n_trials in [50, 100, 250, 500, 1000]:
                    psr, thr = deflated_sharpe(sh, n_obs, n_trials)
                    survives = "YES *" if psr >= 0.95 else "no"
                    log(f"  {buf:>8.1f}  {win_label:>12s}  {vt_tag:>4s}  {sh:>8.3f}  "
                        f"{n_obs:>6d}  {n_trials:>9d}  {thr:>7.3f}  {psr*100:>6.1f}%  {survives:>9s}")
        log()

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 2: SOTA peer comparison — extended metrics (live-only 18y)
    # ══════════════════════════════════════════════════════════════════════
    log()
    log("=" * 160)
    log("SECTION 2: SOTA PEER COMPARISON — extended metrics, live-only 18y (2008-09 → present)")
    log("  Note: FCP results use vol-target OFF (no-VT) for fair momentum peer comparison;")
    log("        vol-target ON row also shown separately.")
    log("=" * 160)
    log()

    # Build peer equity series once (live-only 18y)
    log("  Computing peer strategy equity curves ...")
    peers_live: dict = {}
    peer_defs = [
        ("AAA K=5 (HAA-9)",       lambda p, d: aaa_canonical(p, d, HAA9, K=5, apply_canary=False)),
        ("AAA K=5+can(FCP-15)",   lambda p, d: aaa_canonical(p, d, FCP15, K=5, apply_canary=True)),
        ("Keller HAA-Balanced",   haa_balanced),
        ("Faber GTAA-5",          faber_gtaa5),
        ("60/40 SPY/IEF",         static_60_40),
        ("PP-IEF static",         static_pp_ief),
        ("SPY buy-hold",          buyhold_spy),
    ]
    for label, fn in peer_defs:
        eq, to = simulate(panel, LIVE_START, end, fn)
        peers_live[label] = (eq, to)
        log(f"    {label}: done")

    def metric_row(label, m, to_arr, sh_ci=None):
        ann_to = to_arr.mean()*12*100 if len(to_arr) > 1 else 0.0
        ci_str = f"[{sh_ci[0]:+.2f},{sh_ci[1]:+.2f}]" if sh_ci and not np.isnan(sh_ci[0]) else "   n/a   "
        calmar_str = f"{m['calmar']:+.2f}" if m.get('calmar') and not np.isnan(m['calmar']) else "   nan"
        upi_str = f"{m['upi']:+.2f}" if m.get('upi') and not np.isnan(m['upi']) else "  nan"
        avg36_str = f"{m['avg_36m_dd']:+.2f}" if m.get('avg_36m_dd') and not np.isnan(m['avg_36m_dd']) else "  nan"
        swr_str = f"{m['swr']:5.2f}" if m.get('swr') and not np.isnan(m['swr']) else "  nan"
        return (f"  {label:<42s}"
                f"  Sh {m['sharpe']:+.3f}  CI {ci_str}"
                f"  Srt {m.get('sortino', float('nan')):+.2f}"
                f"  Cal {calmar_str}"
                f"  MDD {m['maxdd']*100:+.2f}%"
                f"  UPI {upi_str}"
                f"  Pain {m['pain']:+.2f}%"
                f"  Avg36m {avg36_str}%"
                f"  SWR {swr_str}%"
                f"  CAGR {m['cagr']*100:+.2f}%"
                f"  TO {ann_to:.0f}%")

    hdr2 = (f"  {'Strategy':<42s}  {'Sharpe':>9s}  {'95% CI (boot)':>14s}"
            f"  {'Sortino':>7s}  {'Calmar':>7s}  {'MaxDD':>8s}"
            f"  {'UPI':>6s}  {'Pain%':>7s}  {'Avg36mDD%':>10s}"
            f"  {'SWR%':>6s}  {'CAGR%':>7s}  {'Ann.TO%':>7s}")
    div2 = "  " + "-" * (len(hdr2) - 2)

    log()
    log(hdr2)
    log(div2)

    # FCP variants first
    for buf in BUFFERS:
        for vt in [True, False]:
            r = fcp_returns[(buf, vt, "live18")]
            eq_df = fcp_eq_from_daily(r)
            m = all_metrics(eq_df)
            ci = block_bootstrap_sharpe_ci(r)
            label = f"FCP-{buf:.1f}z vt={'ON ' if vt else 'OFF'}"
            log(metric_row(label, m, np.array([0]), sh_ci=ci))
    log()

    for label, (eq, to) in peers_live.items():
        r = eq["daily_ret"].dropna()
        m = all_metrics(eq)
        ci = block_bootstrap_sharpe_ci(r)
        log(metric_row(label, m, to, sh_ci=ci))

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 3: Bootstrap Sharpe-difference test
    # ══════════════════════════════════════════════════════════════════════
    log()
    log("=" * 160)
    log("SECTION 3: BOOTSTRAP SHARPE-DIFFERENCE TEST  (B=3000, block=21d, live-only 18y)")
    log("  FCP uses vol-target OFF for direct peer comparison.")
    log("  Point: observed Sharpe(FCP) - Sharpe(peer)")
    log("  95% CI: percentile block-bootstrap distribution of difference")
    log("  P(>0): fraction of bootstrap iterations where FCP wins")
    log("  Sig: * = CI does not straddle 0")
    log("=" * 160)

    for buf in BUFFERS:
        log()
        log(f"  ── Buffer = {buf:.1f}z ──────────────────────────────────────────────────────────────────")
        log(f"  {'Comparison':<50s}  {'PointDiff':>10s}  {'95% CI':>22s}  {'P(>0)':>7s}  Sig")
        log("  " + "-" * 100)
        fcp_r = fcp_returns[(buf, False, "live18")]  # vol-target OFF
        for label, (peer_eq, _) in peers_live.items():
            peer_r = peer_eq["daily_ret"].dropna()
            pt, lo, hi, p_pos = bootstrap_diff(fcp_r, peer_r)
            sig = " *" if (lo > 0 or hi < 0) else ""
            log(f"  FCP-{buf:.1f}z - {label:<44s}  {pt:>+.3f}      [{lo:>+.3f}, {hi:>+.3f}]  {p_pos*100:>5.1f}%  {sig}")

    # Also show cross-buffer diff (FCP-2.0z vs FCP-3.0z)
    log()
    log("  ── Cross-buffer differences (vol-target OFF, live-only 18y) ──────────────────────────────")
    log(f"  {'Comparison':<50s}  {'PointDiff':>10s}  {'95% CI':>22s}  {'P(>0)':>7s}  Sig")
    log("  " + "-" * 100)
    for (ba, bb) in [(2.0, 2.5), (2.0, 3.0), (2.5, 3.0)]:
        ra = fcp_returns[(ba, False, "live18")]
        rb = fcp_returns[(bb, False, "live18")]
        pt, lo, hi, p_pos = bootstrap_diff(ra, rb)
        sig = " *" if (lo > 0 or hi < 0) else ""
        log(f"  FCP-{ba:.1f}z - FCP-{bb:.1f}z{'':<38s}  {pt:>+.3f}      [{lo:>+.3f}, {hi:>+.3f}]  {p_pos*100:>5.1f}%  {sig}")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 4: Cost-stress
    # ══════════════════════════════════════════════════════════════════════
    log()
    log("=" * 160)
    log("SECTION 4: COST-STRESS  — FCP per buffer at 5/10/20/40/80 bps RT cost, live-only 18y")
    log("  Vol-target OFF.  Metrics: Sharpe / CAGR% / MaxDD%")
    log("=" * 160)
    log()

    cost_levels = [5, 10, 20, 40, 80]
    hdr4 = f"  {'Buffer':>8s}  {'CostBps':>8s}  {'Sharpe':>8s}  {'CAGR%':>8s}  {'MaxDD%':>8s}"
    log(hdr4)
    log("  " + "-" * (len(hdr4) - 2))

    for buf in BUFFERS:
        fcp.HOLD_BUFFER = buf
        for cost in cost_levels:
            r, _ = run_fcp_backtest(panel, LIVE_START, end, apply_vol_target=False, cost_bps=cost)
            r = r.dropna()
            eq_s = (1 + r).cumprod()
            n_y = len(r) / 252
            cagr = eq_s.iloc[-1] ** (1/n_y) - 1 if n_y > 0 else np.nan
            vol = r.std() * np.sqrt(252)
            sh = (r.mean()*252) / vol if vol > 0 else np.nan
            mdd = (eq_s / eq_s.cummax() - 1).min()
            log(f"  {buf:>8.1f}  {cost:>8d}  {sh:>8.3f}  {cagr*100:>8.2f}  {mdd*100:>8.2f}")
        log()

    fcp.HOLD_BUFFER = 3.0

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 5: Subwindow Sharpe split
    # ══════════════════════════════════════════════════════════════════════
    log()
    log("=" * 160)
    log("SECTION 5: SUBWINDOW SHARPE SPLIT  (vol-target OFF, live-only windows)")
    log("  Windows: 2008-09→2014-12 | 2015-01→2019-12 | 2020-01→present")
    log("=" * 160)
    log()

    subwindows = [
        ("2008-09→2014-12", pd.Timestamp("2008-09-30"), pd.Timestamp("2014-12-31")),
        ("2015-01→2019-12", pd.Timestamp("2015-01-02"), pd.Timestamp("2019-12-31")),
        ("2020-01→2026-05", pd.Timestamp("2020-01-02"), end),
    ]

    hdr5 = f"  {'Buffer':>8s}  {'Window':>20s}  {'Sharpe':>8s}  {'CAGR%':>8s}  {'MaxDD%':>8s}  {'N_days':>7s}"
    log(hdr5)
    log("  " + "-" * (len(hdr5) - 2))

    for buf in BUFFERS:
        fcp.HOLD_BUFFER = buf
        for win_label, wstart, wend in subwindows:
            try:
                r, _ = run_fcp_backtest(panel, wstart, wend, apply_vol_target=False)
                r = r.dropna()
                if len(r) < 50:
                    log(f"  {buf:>8.1f}  {win_label:>20s}  {'---':>8s}  {'---':>8s}  {'---':>8s}  {len(r):>7d}")
                    continue
                eq_s = (1 + r).cumprod()
                n_y = len(r) / 252
                cagr = eq_s.iloc[-1] ** (1/n_y) - 1
                vol = r.std() * np.sqrt(252)
                sh = (r.mean()*252) / vol if vol > 0 else np.nan
                mdd = (eq_s / eq_s.cummax() - 1).min()
                log(f"  {buf:>8.1f}  {win_label:>20s}  {sh:>8.3f}  {cagr*100:>8.2f}  {mdd*100:>8.2f}  {len(r):>7d}")
            except Exception as e:
                log(f"  {buf:>8.1f}  {win_label:>20s}  ERROR: {e}")
        log()

    # Also show peer subwindow for reference
    log()
    log("  ── Peer subwindow Sharpe (reference rows) ──────────────────────────────────────────")
    hdr5b = f"  {'Strategy':<42s}  {'Window':>20s}  {'Sharpe':>8s}  {'CAGR%':>8s}  {'MaxDD%':>8s}"
    log(hdr5b)
    log("  " + "-" * (len(hdr5b) - 2))
    for label, fn in peer_defs:
        for win_label, wstart, wend in subwindows:
            try:
                eq, _ = simulate(panel, wstart, wend, fn)
                r = eq["daily_ret"].dropna()
                eq_s = eq["equity"]
                n_y = len(r) / 252
                cagr = eq_s.iloc[-1] ** (1/n_y) - 1
                vol = r.std() * np.sqrt(252)
                sh = (r.mean()*252) / vol if vol > 0 else np.nan
                mdd = (eq_s / eq_s.cummax() - 1).min()
                log(f"  {label:<42s}  {win_label:>20s}  {sh:>8.3f}  {cagr*100:>8.2f}  {mdd*100:>8.2f}")
            except Exception as e:
                log(f"  {label:<42s}  {win_label:>20s}  ERROR: {e}")
        log()

    elapsed = time.time() - t0
    log()
    log("=" * 160)
    log(f"END OF EXPERIMENT LOG  |  elapsed: {elapsed:.1f}s  |  {pd.Timestamp.now().isoformat()}")
    log("=" * 160)

    flush_log()
    print(f"\nLog written → {LOG_PATH}", flush=True)


if __name__ == "__main__":
    main()
