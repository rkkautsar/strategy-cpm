"""Final validation: bootstrap + walk-forward for 80/20 PROD with all 2026 changes:
- FCP canary: HYG+TIP+GLD (3-asset, GLD added for AI-rally regimes)
- BULL-QQQ: HYG+LQD+TIP canary + composite trend + +20% equity override + +-+ XLP rotation
"""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_fcp")
import numpy as np, pandas as pd, yfinance as yf
from fcp_live import load_panel, run_fcp_backtest, sig_13612W
import bull_spy_live as bqq

panel = load_panel(start=pd.Timestamp("1985-01-01"))
END = panel.index[-1]
LOG = "/Users/rkautsar/personal/scripts/strategy_fcp/research/validate_final_2026.log"
fh = open(LOG, "w")
def log(s=""):
    print(s, flush=True); fh.write(s + "\n"); fh.flush()

# Stitch
def stitch(live, proxy, splice_date):
    L = yf.Ticker(live).history(period="max", auto_adjust=True)["Close"]
    P = yf.Ticker(proxy).history(period="max", auto_adjust=True)["Close"]
    L.index = pd.DatetimeIndex(L.index).tz_localize(None); P.index = pd.DatetimeIndex(P.index).tz_localize(None)
    splice = pd.Timestamp(splice_date); la = L[L.index >= splice]
    if la.empty: return None
    f = la.index[0]; op = P[P.index < f]
    if op.empty: return L
    scale = la.iloc[0] / P.loc[:f].dropna().iloc[-1]
    return pd.concat([op * scale, la])
for live, proxy, splice, name in [
    ("TIP","VBMFX","2003-12-04","TIP"),
    ("LQD","VFICX","2002-07-30","LQD"),
    ("SHV","VFISX","2007-01-05","SHV"),
    ("QQQ","^NDX","1999-03-10","QQQ"),
    ("XLP","VCSAX","1998-12-22","XLP"),
]:
    s = stitch(live, proxy, splice)
    if s is not None: panel[name] = s.reindex(panel.index).ffill()
log(f"Panel ready: {panel.index[0].date()} -> {panel.index[-1].date()}\n")

def run_prod(start, end):
    fcp, _ = run_fcp_backtest(panel, start, end)
    bull = bqq.run_bull_spy_backtest(panel, start, end)
    common = fcp.index.intersection(bull.index)
    return 0.8 * fcp.loc[common] + 0.2 * bull.loc[common]

def stats(d):
    yrs = len(d)/252; eq = (1+d).cumprod()
    return dict(sharpe=d.mean()*252/(d.std()*np.sqrt(252)) if d.std()>0 else 0,
                cagr=eq.iloc[-1]**(1/yrs)-1 if yrs>0 else 0,
                vol=d.std()*np.sqrt(252),
                max_drawdown=(eq/eq.cummax()-1).min())
def ulcer(d):
    eq = (1+d).cumprod(); dd = (eq/eq.cummax()-1)*100
    return float(np.sqrt((dd**2).mean()))

# ============================================================
# 1. BLOCK BOOTSTRAP CI on final design
# ============================================================
log("=" * 75)
log("1. BLOCK BOOTSTRAP CI on final 80/20 PROD (block_size=21d, 2000 reps)")
log("=" * 75)

def boot(rets, n=2000, b=21, seed=42):
    rng = np.random.default_rng(seed); n_ret = len(rets); nb = (n_ret + b - 1) // b
    arr = rets.values
    sh, cg, dd, ul = [], [], [], []
    for _ in range(n):
        starts = rng.integers(0, n_ret - b, size=nb)
        idx = np.concatenate([np.arange(s, s + b) for s in starts])[:n_ret]
        r = pd.Series(arr[idx])
        sh.append(r.mean()*252/(r.std()*np.sqrt(252)) if r.std() > 0 else 0)
        eq = (1+r).cumprod()
        cg.append(eq.iloc[-1]**(252/len(r))-1 if len(r)>0 else 0)
        ddv = (eq/eq.cummax()-1).min()
        dd.append(ddv)
        u = (eq/eq.cummax()-1)*100
        ul.append(float(np.sqrt((u**2).mean())))
    return dict(
        sharpe=(np.percentile(sh,2.5), np.percentile(sh,97.5), np.median(sh)),
        cagr=(np.percentile(cg,2.5), np.percentile(cg,97.5), np.median(cg)),
        max_drawdown=(np.percentile(dd,2.5), np.percentile(dd,97.5), np.median(dd)),
        ulcer=(np.percentile(ul,2.5), np.percentile(ul,97.5), np.median(ul)),
    )

for wlabel, start in [
    ("LIVE 18y", pd.Timestamp("2008-09-30")),
    ("EXT 24y (full canary)", pd.Timestamp("2002-07-30")),
    ("EXT 32y (full stitched)", pd.Timestamp("1995-01-01")),
]:
    log(f"\n--- {wlabel} ({start.date()} -> {END.date()}) ---")
    blend = run_prod(start, END)
    pt = stats(blend)
    log(f"Point: Sh={pt['sharpe']:.3f}  CAGR={pt['cagr']*100:.2f}%  DD={pt['max_drawdown']*100:.2f}%  Ulcer={ulcer(blend):.2f}%")
    log("Bootstrapping ...")
    ci = boot(blend)
    log(f"  Sharpe : 95% CI [{ci['sharpe'][0]:.3f}, {ci['sharpe'][1]:.3f}]  median {ci['sharpe'][2]:.3f}")
    log(f"  CAGR   : 95% CI [{ci['cagr'][0]*100:.2f}%, {ci['cagr'][1]*100:.2f}%]  median {ci['cagr'][2]*100:.2f}%")
    log(f"  MaxDD  : 95% CI [{ci['max_drawdown'][0]*100:.2f}%, {ci['max_drawdown'][1]*100:.2f}%]  median {ci['max_drawdown'][2]*100:.2f}%")
    log(f"  Ulcer  : 95% CI [{ci['ulcer'][0]:.2f}%, {ci['ulcer'][1]:.2f}%]  median {ci['ulcer'][2]:.2f}%")

# ============================================================
# 2. WALK-FORWARD: rolling 5y windows
# ============================================================
log("\n" + "=" * 75)
log("2. WALK-FORWARD: rolling 5y windows (final design)")
log("=" * 75)

windows = []
year_start = 1996
while True:
    s = pd.Timestamp(f"{year_start}-01-01")
    e = pd.Timestamp(f"{year_start+5}-01-01")
    if e > END: break
    windows.append((f"{year_start}-{year_start+5}", s, e))
    year_start += 3

log(f"\n{'Window':12s}  {'PROD Sh / CAGR':>18s}  {'FCP Sh':>8s}  {'BULL Sh':>9s}  {'SPY Sh':>8s}")
log("-" * 80)
for wname, ws, we in windows:
    try:
        blend = run_prod(ws, we)
        fcp, _ = run_fcp_backtest(panel, ws, we)
        bull = bqq.run_bull_spy_backtest(panel, ws, we)
        spy = panel["SPY"].ffill().pct_change().loc[ws:we].fillna(0)
        pm = stats(blend); fm = stats(fcp); bm = stats(bull); sm = stats(spy)
        log(f"  {wname:11s} Sh={pm['sharpe']:5.2f} {pm['cagr']*100:5.1f}%  Sh={fm['sharpe']:5.2f}  Sh={bm['sharpe']:6.2f}  Sh={sm['sharpe']:5.2f}")
    except Exception as e:
        log(f"  {wname:11s} ERR: {e}")

# ============================================================
# 3. OOS test for the new pieces: +20% override, GLD canary, XLP rotation
# ============================================================
log("\n" + "=" * 75)
log("3. OOS tests for each new component")
log("=" * 75)

import fcp_live as fcp_mod

# Test by toggling each component and measuring OOS Sharpe
def run_prod_toggled(start, end, gld_in_fcp=True, override_active=True, xlp_rot_active=True):
    orig_canary = list(fcp_mod.CANARY_ASSETS)
    orig_override = bqq.EQUITY_OVERRIDE_THRESHOLD
    orig_rot = dict(bqq.BULL_BY_STATE)
    try:
        fcp_mod.CANARY_ASSETS = ["HYG_stitched","TIP","GLD"] if gld_in_fcp else ["HYG_stitched","TIP"]
        bqq.EQUITY_OVERRIDE_THRESHOLD = 0.20 if override_active else 999  # disabled
        bqq.BULL_BY_STATE = {"+-+":"XLP"} if xlp_rot_active else {}
        return run_prod(start, end)
    finally:
        fcp_mod.CANARY_ASSETS = orig_canary
        bqq.EQUITY_OVERRIDE_THRESHOLD = orig_override
        bqq.BULL_BY_STATE = orig_rot

log(f"\n{'Freeze year':12s}  {'OOS window':18s}  {'Sh w/all':>10s}  {'no override':>11s}  {'no GLD':>9s}  {'no rotation':>11s}  {'all off':>9s}")
log("-" * 100)
for freeze_y in [2010, 2013, 2016, 2019, 2021]:
    oos_start = pd.Timestamp(f"{freeze_y+1}-01-01")
    if oos_start > END: continue
    r_all = run_prod_toggled(oos_start, END, True, True, True)
    r_no_override = run_prod_toggled(oos_start, END, True, False, True)
    r_no_gld = run_prod_toggled(oos_start, END, False, True, True)
    r_no_rot = run_prod_toggled(oos_start, END, True, True, False)
    r_none = run_prod_toggled(oos_start, END, False, False, False)
    common = r_all.index
    s_all = stats(r_all.reindex(common))
    s_no_o = stats(r_no_override.reindex(common))
    s_no_g = stats(r_no_gld.reindex(common))
    s_no_r = stats(r_no_rot.reindex(common))
    s_none = stats(r_none.reindex(common))
    log(f"  {freeze_y:11d}  {oos_start.date()}->{END.date().strftime('%Y-%m')}  Sh={s_all['sharpe']:7.2f}  Sh={s_no_o['sharpe']:8.2f}  Sh={s_no_g['sharpe']:6.2f}  Sh={s_no_r['sharpe']:8.2f}  Sh={s_none['sharpe']:6.2f}")

log("\n=== DONE ===")
fh.close()
print(f"\nOutput: {LOG}")
