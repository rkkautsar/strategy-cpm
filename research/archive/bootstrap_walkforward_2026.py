"""Bootstrap CI + Walk-forward validation for 80/20 PROD (BULL-QQQ + FCP)
on the new 32y stitched window."""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_fcp")
import numpy as np, pandas as pd, yfinance as yf
from fcp_live import load_panel, run_fcp_backtest, sig_13612W, perf_metrics
import bull_qqq_live as bqq

panel = load_panel(start=pd.Timestamp("1985-01-01"))
END = panel.index[-1]

LOG = "/Users/rkautsar/personal/scripts/strategy_fcp/research/bootstrap_wf_2026.log"
fh = open(LOG, "w")
def log(s=""):
    print(s, flush=True); fh.write(s + "\n"); fh.flush()

# Stitch all proxies
def stitch(live, proxy, splice_date):
    L = yf.Ticker(live).history(period="max", auto_adjust=True)["Close"]
    P = yf.Ticker(proxy).history(period="max", auto_adjust=True)["Close"]
    L.index = pd.DatetimeIndex(L.index).tz_localize(None)
    P.index = pd.DatetimeIndex(P.index).tz_localize(None)
    splice = pd.Timestamp(splice_date)
    la = L[L.index >= splice]
    if la.empty: return None
    f = la.index[0]; op = P.loc[:f]
    if op.empty: return None
    sc = la.iloc[0] / op.iloc[-1]
    return pd.concat([P[P.index < f] * sc, la])

for live, proxy, splice, name in [
    ("TIP","VBMFX","2003-12-04","TIP"),
    ("LQD","VFICX","2002-07-30","LQD"),
    ("SHV","VFISX","2007-01-05","SHV"),
    ("QQQ","^NDX","1999-03-10","QQQ"),
    ("XLP","VCSAX","1998-12-22","XLP"),
]:
    s = stitch(live, proxy, splice)
    if s is not None:
        panel[name] = s.reindex(panel.index).ffill()

START_32 = pd.Timestamp("1994-12-31")
START_LIVE = pd.Timestamp("2008-09-30")
log(f"Panel ready. Backtest window 32y: {START_32.date()} to {END.date()}")

# Compute production blend
def run_prod(start, end):
    fcp, _ = run_fcp_backtest(panel, start, end)
    bull = bqq.run_bull_qqq_backtest(panel, start, end)
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

# ======================================================================
# 1. BLOCK BOOTSTRAP CI
# ======================================================================
log("\n" + "=" * 70)
log("1. BLOCK BOOTSTRAP CI (block_size=21d, 2000 reps)")
log("=" * 70)

def block_bootstrap(rets, n_boot=2000, block_size=21, seed=42):
    rng = np.random.default_rng(seed)
    n = len(rets); n_blocks = (n + block_size - 1) // block_size
    arr = rets.values
    sh, cg, dd, ul = [], [], [], []
    for _ in range(n_boot):
        starts = rng.integers(0, n - block_size, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block_size) for s in starts])[:n]
        b = pd.Series(arr[idx])
        sh.append(b.mean()*252/(b.std()*np.sqrt(252)) if b.std() > 0 else 0)
        eq = (1+b).cumprod()
        cg.append(eq.iloc[-1]**(252/len(b))-1 if len(b)>0 else 0)
        ddv = (eq/eq.cummax()-1).min()
        dd.append(ddv)
        u = (eq/eq.cummax()-1)*100
        ul.append(float(np.sqrt((u**2).mean())))
    return dict(sharpe=(np.percentile(sh,2.5), np.percentile(sh,97.5), np.median(sh)),
                cagr=(np.percentile(cg,2.5), np.percentile(cg,97.5), np.median(cg)),
                max_drawdown=(np.percentile(dd,2.5), np.percentile(dd,97.5), np.median(dd)),
                ulcer=(np.percentile(ul,2.5), np.percentile(ul,97.5), np.median(ul)))

for wlabel, start in [
    ("LIVE 18y", START_LIVE),
    ("EXT 26y stitched", pd.Timestamp("2000-07-30")),
    ("EXT 32y full stitched", START_32),
]:
    log(f"\n--- {wlabel} ({start.date()} -> {END.date()}) ---")
    blend = run_prod(start, END)
    pt = stats(blend)
    log(f"Point: Sh={pt['sharpe']:.3f}  CAGR={pt['cagr']*100:.2f}%  DD={pt['max_drawdown']*100:.2f}%  Ulcer={ulcer(blend):.2f}%")
    log("Bootstrapping ...")
    ci = block_bootstrap(blend)
    log(f"  Sharpe : 95% CI [{ci['sharpe'][0]:.3f}, {ci['sharpe'][1]:.3f}]  median {ci['sharpe'][2]:.3f}")
    log(f"  CAGR   : 95% CI [{ci['cagr'][0]*100:.2f}%, {ci['cagr'][1]*100:.2f}%]  median {ci['cagr'][2]*100:.2f}%")
    log(f"  MaxDD  : 95% CI [{ci['max_drawdown'][0]*100:.2f}%, {ci['max_drawdown'][1]*100:.2f}%]  median {ci['max_drawdown'][2]*100:.2f}%")
    log(f"  Ulcer  : 95% CI [{ci['ulcer'][0]:.2f}%, {ci['ulcer'][1]:.2f}%]  median {ci['ulcer'][2]:.2f}%")

# ======================================================================
# 2. WALK-FORWARD: rolling 5y windows
# ======================================================================
log("\n" + "=" * 70)
log("2. WALK-FORWARD: rolling 5y windows (PROD vs FCP-only vs SPY)")
log("=" * 70)

windows = []
year_start = 1996
while True:
    s = pd.Timestamp(f"{year_start}-01-01")
    e = pd.Timestamp(f"{year_start+5}-01-01")
    if e > END: break
    windows.append((f"{year_start}-{year_start+5}", s, e))
    year_start += 3  # overlapping 5y windows every 3y

log(f"\n{'Window':12s}  {'PROD Sh / CAGR / DD':>26s}  {'FCP Sh / CAGR':>20s}  {'SPY Sh / CAGR':>20s}")
log("-" * 90)
for wname, ws, we in windows:
    try:
        blend = run_prod(ws, we)
        fcp, _ = run_fcp_backtest(panel, ws, we)
        spy = panel["SPY"].ffill().pct_change().loc[ws:we].fillna(0)
        pm = stats(blend); fm = stats(fcp); sm = stats(spy)
        log(f"  {wname:11s} Sh={pm['sharpe']:5.2f} {pm['cagr']*100:5.1f}% {pm['max_drawdown']*100:5.1f}%  Sh={fm['sharpe']:5.2f} {fm['cagr']*100:5.1f}%  Sh={sm['sharpe']:5.2f} {sm['cagr']*100:5.1f}%")
    except Exception as e:
        log(f"  {wname:11s} ERR: {e}")

# ======================================================================
# 3. WALK-FORWARD freeze test: did XLP rotation help OOS?
# ======================================================================
log("\n" + "=" * 70)
log("3. XLP rotation OOS test: freeze at multiple cutoffs, test OOS")
log("=" * 70)

# Test: does +-+ XLP rotation help OOS after each freeze year?
# Compare blend WITH and WITHOUT XLP rotation
def run_blend_no_rotation(start, end):
    """BULL-QQQ but without +-+ XLP rotation (always QQQ when bull)."""
    orig = bqq.BULL_BY_STATE.copy()
    bqq.BULL_BY_STATE = {}  # disable rotation
    try:
        fcp, _ = run_fcp_backtest(panel, start, end)
        bull = bqq.run_bull_qqq_backtest(panel, start, end)
        common = fcp.index.intersection(bull.index)
        return 0.8 * fcp.loc[common] + 0.2 * bull.loc[common]
    finally:
        bqq.BULL_BY_STATE = orig

log(f"\n{'Freeze year':12s}  {'OOS window':18s}  {'PROD (with XLP) Sh':>20s}  {'no-rotation Sh':>16s}  {'diff':>8s}")
log("-" * 90)
for freeze_y in [2010, 2013, 2016, 2019, 2021]:
    oos_start = pd.Timestamp(f"{freeze_y+1}-01-01")
    if oos_start > END: continue
    with_rot = run_prod(oos_start, END)
    no_rot = run_blend_no_rotation(oos_start, END)
    common = with_rot.index.intersection(no_rot.index)
    w = stats(with_rot.loc[common]); n = stats(no_rot.loc[common])
    log(f"  {freeze_y:11d}  {oos_start.date()}->{END.date().strftime('%Y-%m')}  Sh={w['sharpe']:5.2f} CAGR={w['cagr']*100:4.1f}%  Sh={n['sharpe']:5.2f}  {w['sharpe']-n['sharpe']:+6.2f}")

# Count XLP rotation firings in each OOS window
log(f"\n--- `+-+` state firings per OOS window ---")
monthly_idx = pd.DataFrame({"x":1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
for freeze_y in [2010, 2013, 2016, 2019, 2021]:
    oos_start = pd.Timestamp(f"{freeze_y+1}-01-01")
    if oos_start > END: continue
    sigs = monthly_idx.index[(monthly_idx.index >= oos_start) & (monthly_idx.index <= END)].tolist()
    fires = 0
    for sd in sigs:
        mon = panel.loc[:sd].resample("ME").last()
        h = sig_13612W(mon["HYG_stitched"].loc[:sd])
        l = sig_13612W(mon["LQD"].loc[:sd])
        t = sig_13612W(mon["TIP"].loc[:sd])
        if any(pd.isna(v) for v in [h,l,t]): continue
        state = ("+" if h>0 else "-") + ("+" if l>0 else "-") + ("+" if t>0 else "-")
        if state == "+-+": fires += 1
    log(f"  Freeze {freeze_y} -> OOS {oos_start.date()} to {END.date()}: {len(sigs)} months, {fires} +-+ firings")

log("\n=== DONE ===")
fh.close()
print(f"Output: {LOG}")
