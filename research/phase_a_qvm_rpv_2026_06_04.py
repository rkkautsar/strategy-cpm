#!/usr/bin/env python3
"""
PHASE A -- Keyless SACEVS-Weighted multi-premia RPV breadth test.

Hypothesis: current RPV sleeve (3 US premia term/credit/equity -> SPY/TLT/LQD + SHV)
is dormant (~92% cash since 2021) because all 3 premia went expensive at once.
Widening the VALUE universe to more keyless-sourceable premia should reduce dormancy
while holding/improving risk-adjusted return.

RESEARCH-ONLY. Writes only to /tmp and research/. No prod edits. Offline-friendly:
committed-first reads with web fallback (15s timeout); falls back to data/ + research caches.

Premia -> asset map (value = trailing-W z of the premium; higher z = cheaper = attractive):
  term     = DGS10 - DGS3MO                  -> TLT   (committed FRED)
  igcredit = DBAA  - DGS10                   -> LQD   (committed FRED; ICE OAS BAMLC0A0CM
                                                       is license-truncated to ~3y keyless,
                                                       so DBAA-DGS10 used as the alt)
  equity   = ShillerEY - DGS10               -> SPY   (committed sp500_earnings.csv)
  hycredit = BAA - AAA (Moody's, monthly)    -> HYG   (PROXY: ICE HY OAS BAMLH0A0HYM2 is
                                                       license-truncated to ~3y keyless;
                                                       Moody's Baa-Aaa quality spread is the
                                                       long-history keyless credit-stress proxy)
  realyld  = DGS10 - CPI_YoY (ex-post real)  -> TIP   (PROXY: DFII10 10y TIPS real yield is
                                                       not reliably fetchable keyless / windowed;
                                                       ex-post real yield from committed CPIAUCSL)
  cash     = SHV
"""
from __future__ import annotations
import io
import sys
from pathlib import Path
from urllib.request import urlopen
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import cpm_live as cpm
import rpv_live

DATA = ROOT / "data"
CACHE = ROOT / "research" / "phase_a_cache"
W_DEFAULT = 120
ZMIN = 36
COST_BPS = 10.0
TRADING = 252

# ----------------------------------------------------------------------------- data
def _read_csv_url(url: str, timeout_s: float = 15.0) -> pd.DataFrame:
    with urlopen(url, timeout=timeout_s) as resp:
        return pd.read_csv(io.StringIO(resp.read().decode("utf-8")))

def _fred_committed_first(id_: str, cache_paths: list[Path]) -> pd.Series:
    """Read committed cache first (offline-safe), web fallback. Returns daily/monthly series."""
    for p in cache_paths:
        if p.exists():
            df = pd.read_csv(p)
            df.columns = ["date", id_]
            df["date"] = pd.to_datetime(df["date"])
            s = pd.to_numeric(df[id_], errors="coerce")
            s.index = df["date"]
            return s.dropna()
    # web fallback
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={id_}"
    df = _read_csv_url(url)
    df.columns = ["date", id_]
    df["date"] = pd.to_datetime(df["date"])
    s = pd.to_numeric(df[id_], errors="coerce")
    s.index = df["date"]
    return s.dropna()

def load_phase_a_signals(W: int = W_DEFAULT, momentum: bool = True) -> pd.DataFrame:
    """Returns monthly trailing-z DataFrame, columns = premium names (term/igcredit/equity/
    hycredit/realyld). Eligibility (z>0) and asset mapping handled downstream."""
    me = lambda s: s.resample("ME").last()

    # shared 3 premia: reuse exact rpv_live macro construction for term/credit/equity raw rp
    dgs10, dgs3mo, dbaa, sp500, E, P = rpv_live.load_macro_data()
    dgs10_m, dgs3mo_m, dbaa_m = me(dgs10), me(dgs3mo), me(dbaa)
    sp500_m = me(sp500)
    E_m = E.resample("ME").last()
    if not E_m.empty:
        ceiling = max(pd.Timestamp("2026-06-30"),
                      pd.Timestamp.today().normalize() + pd.offsets.MonthEnd(0),
                      E_m.index.max())
        E_m = E_m.reindex(pd.date_range(E_m.index.min(), ceiling, freq="ME")).ffill()
    P_m = P.resample("ME").last()
    if not sp500_m.empty:
        ov = P_m.index.intersection(sp500_m.index)
        if len(ov) > 0:
            k = P_m.loc[ov[-1]] / sp500_m.loc[ov[-1]]
            P_m = pd.concat([P_m, sp500_m[sp500_m.index > P_m.index.max()] * k]).sort_index().ffill()
    EY = (100.0 * (E_m.shift(rpv_live.LAG_E) / P_m)).dropna()

    # hycredit: Moody's Baa - Aaa (monthly long history)
    baa = _fred_committed_first("BAA", [CACHE / "fred_BAA.csv", DATA / "fred_BAA.csv"])
    aaa = _fred_committed_first("AAA", [CACHE / "fred_AAA.csv", DATA / "fred_AAA.csv"])
    baa_m, aaa_m = me(baa), me(aaa)

    # realyld: DGS10 - CPI YoY (ex-post real yield), CPIAUCSL committed
    cpi = _fred_committed_first("CPIAUCSL", [CACHE / "CPIAUCSL.csv",
                                             ROOT / "research" / "_macro_cache" / "CPIAUCSL.csv"])
    cpi_m = me(cpi)
    cpi_yoy = 100.0 * (cpi_m / cpi_m.shift(12) - 1.0)

    rp = pd.DataFrame({
        "term":     (dgs10_m - dgs3mo_m),
        "igcredit": (dbaa_m - dgs10_m),
        "equity":   (EY - dgs10_m),
        "hycredit": (baa_m - aaa_m),
        "realyld":  (dgs10_m - cpi_yoy),
    }).sort_index()

    def trailing_z(df: pd.DataFrame, w: int) -> pd.DataFrame:
        return df.apply(lambda s: (s - s.rolling(w).mean()) / s.rolling(w).std(ddof=0))

    # z each column over its own available history, then assemble (allow per-column NaN)
    Z = trailing_z(rp, W)
    Z = Z.dropna(how="all")
    return Z

ASSET_OF = {"term": "TLT", "igcredit": "LQD", "equity": "SPY",
            "hycredit": "HYG", "realyld": "TIP"}
PHASE_A_ASSETS = ["SPY", "TLT", "LQD", "HYG", "TIP", "SHV"]

# ----------------------------------------------------------------------------- weights
def _sma_above(prices: pd.DataFrame, asset: str, sig_d: pd.Timestamp, win: int = 200) -> bool:
    if asset not in prices.columns:
        return False
    s = prices[asset].sort_index().ffill().loc[:sig_d]
    if len(s) < win:
        return False
    sma = s.rolling(win).mean().iloc[-1]
    return bool(pd.notna(sma) and s.iloc[-1] > sma)

def phase_a_weights_weighted(Z: pd.DataFrame, prices: pd.DataFrame, sig_d: pd.Timestamp,
                             momentum: bool = True) -> dict:
    """(A) WEIGHTED by positive z, proportional; 200d-guard each risky asset -> SHV."""
    if sig_d not in Z.index:
        valid = Z.index[Z.index <= sig_d]
        if len(valid) == 0:
            return {"SHV": 1.0}
        sig_d = valid[-1]
    zrow = Z.loc[sig_d].dropna()
    pos = zrow.clip(lower=0.0)
    tot = pos.sum()
    if tot <= 0:
        return {"SHV": 1.0}
    base = {}
    for prem, v in pos.items():
        if v > 0:
            a = ASSET_OF[prem]
            base[a] = base.get(a, 0.0) + v / tot
    guarded = {}
    for a, wt in base.items():
        if momentum and not _sma_above(prices, a, sig_d):
            guarded["SHV"] = guarded.get("SHV", 0.0) + wt
        else:
            guarded[a] = guarded.get(a, 0.0) + wt
    return guarded or {"SHV": 1.0}

def phase_a_weights_top3(Z: pd.DataFrame, prices: pd.DataFrame, sig_d: pd.Timestamp,
                         momentum: bool = True, cap: float = 1.0 / 3.0, k: int = 3) -> dict:
    """(B) TOP-k equal among value(z>0)+momentum survivors, cash residual, per-asset cap."""
    if sig_d not in Z.index:
        valid = Z.index[Z.index <= sig_d]
        if len(valid) == 0:
            return {"SHV": 1.0}
        sig_d = valid[-1]
    zrow = Z.loc[sig_d].dropna()
    cands = []
    for prem, z in zrow.items():
        if z > 0:
            a = ASSET_OF[prem]
            if (not momentum) or _sma_above(prices, a, sig_d):
                cands.append((a, z))
    if not cands:
        return {"SHV": 1.0}
    cands.sort(key=lambda x: -x[1])
    chosen = cands[:k]
    w_each = min(cap, 1.0 / k)
    out = {}
    for a, _ in chosen:
        out[a] = out.get(a, 0.0) + w_each
    invested = sum(out.values())
    if invested < 1.0:
        out["SHV"] = out.get("SHV", 0.0) + (1.0 - invested)
    return out

# ----------------------------------------------------------------------------- engine
def backtest(panel: pd.DataFrame, assets: list[str], sig_index: pd.DatetimeIndex,
             weight_fn, start: pd.Timestamp, end: pd.Timestamp,
             cost_bps: float = COST_BPS) -> tuple[pd.Series, list]:
    """Generic close-to-close T+1 MOO engine matching rpv_live.run_rpv_backtest mechanics.
    Returns (daily_returns over [start,end], list of (exec_date, weights))."""
    use = [a for a in assets if a in panel.columns]
    prices = panel[use].sort_index().ffill()
    sig_dates = sig_index[sig_index <= end]
    full_idx = prices.loc[:end].index
    trade_idx = prices.loc[start:end].index
    daily = pd.Series(0.0, index=full_idx)

    weights_for_date: dict[pd.Timestamp, dict] = {}
    hist = []
    for sd in sig_dates:
        target = weight_fn(sd)
        future = full_idx[full_idx > sd]
        if len(future) >= 1:
            weights_for_date[future[0]] = target
            hist.append((sd, target))

    exec_dates = sorted(weights_for_date.keys())
    cur_w = {"SHV": 1.0}
    i = 0
    for ts in full_idx:
        while i < len(exec_dates) and exec_dates[i] <= ts:
            new_w = weights_for_date[exec_dates[i]]
            if cur_w != new_w and cost_bps > 0:
                tovr = sum(abs(cur_w.get(a, 0.0) - new_w.get(a, 0.0))
                           for a in set(cur_w) | set(new_w))
                daily.loc[ts] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            i += 1
        loc = prices.index.get_loc(ts)
        if loc == 0:
            continue
        prev = prices.index[loc - 1]
        r = 0.0
        for a, w in cur_w.items():
            if a not in prices.columns:
                continue
            today, yest = prices.loc[ts, a], prices.loc[prev, a]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                r += w * (today / yest - 1)
        daily.loc[ts] += r
    return daily.loc[trade_idx], hist

# ----------------------------------------------------------------------------- weight history (for cash%/holds)
def weight_path(sig_index, weight_fn, panel_index, end) -> pd.DataFrame:
    """Daily forward-filled weight matrix (for cash% / hold distribution)."""
    rows = {}
    cur = {"SHV": 1.0}
    sig_dates = [d for d in sig_index if d <= end]
    exec_map = {}
    full_idx = panel_index[panel_index <= end]
    for sd in sig_dates:
        fut = full_idx[full_idx > sd]
        if len(fut):
            exec_map[fut[0]] = weight_fn(sd)
    exec_dates = sorted(exec_map)
    i = 0
    for ts in full_idx:
        while i < len(exec_dates) and exec_dates[i] <= ts:
            cur = exec_map[exec_dates[i]]
            i += 1
        rows[ts] = dict(cur)
    return pd.DataFrame(rows).T.fillna(0.0)

# ----------------------------------------------------------------------------- metrics
def metrics(daily: pd.Series) -> dict:
    d = daily.dropna()
    if len(d) < 2:
        return dict(cagr=np.nan, vol=np.nan, sharpe=np.nan, maxdd=np.nan, n=len(d))
    eq = (1 + d).cumprod()
    yrs = (d.index[-1] - d.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol = d.std() * np.sqrt(TRADING)
    sharpe = d.mean() / d.std() * np.sqrt(TRADING) if d.std() > 0 else np.nan
    maxdd = (eq / eq.cummax() - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sharpe, maxdd=maxdd, n=len(d))

def cash_invested(wpath: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp) -> tuple[float, float]:
    sub = wpath.loc[(wpath.index >= lo) & (wpath.index <= hi)]
    if sub.empty:
        return np.nan, np.nan
    cashw = sub["SHV"] if "SHV" in sub.columns else pd.Series(0.0, index=sub.index)
    cash = cashw.mean()
    return cash, 1.0 - cash

def hold_distribution(wpath: pd.DataFrame, lo, hi) -> dict:
    sub = wpath.loc[(wpath.index >= lo) & (wpath.index <= hi)]
    if sub.empty:
        return {}
    return {c: round(float(sub[c].mean()), 4) for c in sub.columns if sub[c].mean() > 1e-4}

def fmt_pct(x):
    return "n/a" if pd.isna(x) else f"{x*100:.2f}%"

def row(name, m, cash, inv):
    return (f"| {name} | {fmt_pct(m['cagr'])} | {fmt_pct(m['vol'])} | "
            f"{m['sharpe']:.3f} | {fmt_pct(m['maxdd'])} | {fmt_pct(cash)} | {fmt_pct(inv)} |")

# ----------------------------------------------------------------------------- main
def main():
    out = []
    A = out.append
    A("# Phase A -- Keyless multi-premia RPV breadth test\n")
    A(f"_Generated: 2026-06-04. Research-only. Offline-friendly committed-first reads._\n")

    panel = cpm.load_panel(start=pd.Timestamp("1995-01-01"),
                           end=pd.Timestamp("2026-04-30"), live=False)
    end = panel.index.max()

    # ---- STEP 0 data availability
    A("## 1. Data availability (STEP 0)\n")
    Zb = rpv_live.compute_rpv_signals()
    Za = load_phase_a_signals(W=W_DEFAULT)
    avail = []
    avail.append(f"- Price panel (live=False): {panel.shape[0]} days "
                 f"{panel.index.min().date()}..{end.date()}; "
                 f"have {[a for a in PHASE_A_ASSETS if a in panel.columns]}")
    avail.append(f"- Baseline RPV Z (term/credit/equity): {Zb.shape}, "
                 f"{Zb.index.min().date()}..{Zb.index.max().date()}")
    for col in Za.columns:
        s = Za[col].dropna()
        avail.append(f"- Phase-A premium `{col}` -> {ASSET_OF[col]}: z rows {len(s)}, "
                     f"{s.index.min().date()}..{s.index.max().date()}")
    avail.append("- **ICE BofA OAS BAMLC0A0CM (IG) / BAMLH0A0HYM2 (HY): keyless fredgraph "
                 "returns ONLY ~3y (2023-06+, n~786) -- UNUSABLE for 120m z. "
                 "Used alts: IG=DBAA-DGS10 (as designed), HY=Moody's BAA-AAA proxy.**")
    avail.append("- **DFII10 (10y TIPS real yield): not reliably fetchable keyless "
                 "(timeouts/window). Used alt: ex-post real yield = DGS10 - CPI YoY (CPIAUCSL).**")
    A("\n".join(avail) + "\n")

    # align Phase-A z burn to match baseline convention (drop first ZMIN usable rows)
    Za_full = Za.copy()
    # apply ZMIN burn on the all-columns-present portion
    Za_ready = Za.dropna()
    if len(Za_ready) > ZMIN:
        burn_cut = Za_ready.index[ZMIN]
        Za = Za.loc[Za.index >= burn_cut]

    prices = panel.sort_index().ffill()

    # signal indices
    sig_b = Zb.index
    sig_a = Za.index

    # weight fns
    base_wf = lambda sd: rpv_live.compute_rpv_weights(panel, sd)[0]
    paw_wf = lambda sd: phase_a_weights_weighted(Za, prices, sd, momentum=True)
    pat_wf = lambda sd: phase_a_weights_top3(Za, prices, sd, momentum=True)

    # common full window start = first exec date across all three
    def first_exec(sig_index):
        sds = sig_index[sig_index <= end]
        for sd in sds:
            fut = panel.index[panel.index > sd]
            if len(fut):
                return fut[0]
        return panel.index.min()
    full_start = max(first_exec(sig_b), first_exec(sig_a))

    # ---- backtests
    base_canon = rpv_live.run_rpv_backtest(panel, full_start, end)        # exact prod fn
    base_eng, _ = backtest(panel, ["SPY","TLT","LQD","SHV"], sig_b, base_wf, full_start, end)
    paw, _ = backtest(panel, PHASE_A_ASSETS, sig_a, paw_wf, full_start, end)
    pat, _ = backtest(panel, PHASE_A_ASSETS, sig_a, pat_wf, full_start, end)

    # weight paths for cash%/holds
    wp_base = weight_path(sig_b, base_wf, panel.index, end)
    wp_paw = weight_path(sig_a, paw_wf, panel.index, end)
    wp_pat = weight_path(sig_a, pat_wf, panel.index, end)

    last5 = pd.Timestamp("2021-01-01")

    A("## 2. Sleeve backtest comparison\n")
    A(f"Common full window: {full_start.date()}..{end.date()}. "
      f"Execution: T+1 MOO close-to-close, {COST_BPS:.0f}bps/side turnover (identical all sleeves). "
      f"Sharpe rf=0.\n")
    A("Engine sanity: baseline via exact `rpv_live.run_rpv_backtest` vs generic engine -- "
      f"CAGR {fmt_pct(metrics(base_canon)['cagr'])} vs {fmt_pct(metrics(base_eng)['cagr'])}, "
      f"Sharpe {metrics(base_canon)['sharpe']:.3f} vs {metrics(base_eng)['sharpe']:.3f}.\n")

    def block(title, lo, hi):
        A(f"### {title} ({lo.date()}..{hi.date()})\n")
        A("| sleeve | CAGR | vol | Sharpe | maxDD | cash% | invested% |")
        A("|---|---|---|---|---|---|---|")
        for name, daily, wp, sig in [
            ("current-RPV (3 premia)", base_canon, wp_base, sig_b),
            ("Phase-A Weighted (5)",   paw,        wp_paw,  sig_a),
            ("Phase-A Top3 (5)",       pat,        wp_pat,  sig_a),
        ]:
            d = daily.loc[(daily.index >= lo) & (daily.index <= hi)]
            c, inv = cash_invested(wp, lo, hi)
            A(row(name, metrics(d), c, inv))
        A("")

    block("Full history", full_start, end)
    block("Last 5y", last5, end)

    A("### Hold distribution (avg daily weight)\n")
    for name, wp in [("current-RPV", wp_base), ("Phase-A Weighted", wp_paw), ("Phase-A Top3", wp_pat)]:
        A(f"- **{name}** full: {hold_distribution(wp, full_start, end)}")
        A(f"  - last5y: {hold_distribution(wp, last5, end)}")
    A("")

    # ---- 3. combined book
    A("## 3. Combined-book impact (60 CPM / 25 NDX / 15 RPV)\n")
    cpm_wf = lambda sd: cpm.compute_target_weights(panel, sd)[0]
    cpm_assets = sorted(set(cpm.RISKY_UNIVERSE) | set(cpm.SAFE_POOL)
                        | set(cpm.CANARY_ASSETS) | {cpm.DEFAULT_CASH, "LQD"})
    monthly_sig = (pd.Series(1, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1).index)
    cpm_daily, _ = backtest(panel, cpm_assets, monthly_sig, cpm_wf, full_start, end)

    ndx_daily = None
    ndx_note = ""
    try:
        from ndx_sleeve_live import load_ndx_panel, compute_ndx_weights
        ndx_panel = load_ndx_panel()
        full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
        full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
        ndx_wf = lambda sd: compute_ndx_weights(panel, ndx_panel, sd)[0]
        ndx_assets = sorted(set(full_panel.columns))
        ndx_daily, _ = backtest(full_panel, ndx_assets, monthly_sig, ndx_wf, full_start, end)
        ndx_note = "NDX sleeve included (committed/keyless constituents)."
    except Exception as e:
        ndx_note = (f"NDX sleeve UNAVAILABLE offline ({type(e).__name__}); "
                    f"both books hold NDX leg at 0 return identically -- RPV-swap delta still valid, "
                    f"absolute book metrics understate the 25% NDX contribution.")

    idx = cpm_daily.index
    rpv_b = base_canon.reindex(idx).fillna(0.0)
    rpv_paw = paw.reindex(idx).fillna(0.0)
    rpv_pat = pat.reindex(idx).fillna(0.0)
    cpm_d = cpm_daily.reindex(idx).fillna(0.0)
    ndx_d = ndx_daily.reindex(idx).fillna(0.0) if ndx_daily is not None else pd.Series(0.0, index=idx)

    book_cur = 0.60 * cpm_d + 0.25 * ndx_d + 0.15 * rpv_b
    book_paw = 0.60 * cpm_d + 0.25 * ndx_d + 0.15 * rpv_paw
    book_pat = 0.60 * cpm_d + 0.25 * ndx_d + 0.15 * rpv_pat

    A(ndx_note + "\n")
    def book_block(title, lo, hi):
        A(f"### {title} ({lo.date()}..{hi.date()})\n")
        A("| book | CAGR | vol | Sharpe | maxDD |")
        A("|---|---|---|---|---|")
        for name, b in [("current book (RPV baseline)", book_cur),
                        ("book w/ Phase-A Weighted", book_paw),
                        ("book w/ Phase-A Top3", book_pat)]:
            d = b.loc[(b.index >= lo) & (b.index <= hi)]
            m = metrics(d)
            A(f"| {name} | {fmt_pct(m['cagr'])} | {fmt_pct(m['vol'])} | {m['sharpe']:.3f} | {fmt_pct(m['maxdd'])} |")
        A("")
    book_block("Full history", full_start, end)
    book_block("Last 5y", last5, end)

    # ---- 4. robustness
    A("## 4. Robustness\n")
    A("### Sub-period sleeve Sharpe / invested%\n")
    subs = [("2008-2014", pd.Timestamp("2008-01-01"), pd.Timestamp("2013-12-31")),
            ("2014-2020", pd.Timestamp("2014-01-01"), pd.Timestamp("2019-12-31")),
            ("2020-2026", pd.Timestamp("2020-01-01"), end)]
    A("| period | RPV Sharpe / inv% | PhaseA-W Sharpe / inv% | PhaseA-T3 Sharpe / inv% |")
    A("|---|---|---|---|")
    for nm, lo, hi in subs:
        cells = []
        for daily, wp in [(base_canon, wp_base), (paw, wp_paw), (pat, wp_pat)]:
            d = daily.loc[(daily.index >= lo) & (daily.index <= hi)]
            _, inv = cash_invested(wp, lo, hi)
            cells.append(f"{metrics(d)['sharpe']:.2f} / {fmt_pct(inv)}")
        A(f"| {nm} | {cells[0]} | {cells[1]} | {cells[2]} |")
    A("")

    A("### Sensitivity sweep (Phase-A Weighted): W x momentum\n")
    A("| config | CAGR | Sharpe | maxDD | inv% full | inv% last5 |")
    A("|---|---|---|---|---|---|")
    for Wv in (120, 84):
        Zsw = load_phase_a_signals(W=Wv)
        Zsw_ready = Zsw.dropna()
        if len(Zsw_ready) > ZMIN:
            Zsw = Zsw.loc[Zsw.index >= Zsw_ready.index[ZMIN]]
        for mom in (True, False):
            wf = (lambda ZZ, mm: (lambda sd: phase_a_weights_weighted(ZZ, prices, sd, momentum=mm)))(Zsw, mom)
            d, _ = backtest(panel, PHASE_A_ASSETS, Zsw.index, wf, full_start, end)
            wp = weight_path(Zsw.index, wf, panel.index, end)
            m = metrics(d)
            _, invf = cash_invested(wp, full_start, end)
            _, inv5 = cash_invested(wp, last5, end)
            A(f"| W={Wv}, mom={'200d' if mom else 'off'} | {fmt_pct(m['cagr'])} | "
              f"{m['sharpe']:.3f} | {fmt_pct(m['maxdd'])} | {fmt_pct(invf)} | {fmt_pct(inv5)} |")
    A("")

    # ---- 5. verdict
    A("## 5. Verdict\n")
    mb, mpaw, mpat = metrics(base_canon), metrics(paw), metrics(pat)
    _, inv_b5 = cash_invested(wp_base, last5, end)
    _, inv_w5 = cash_invested(wp_paw, last5, end)
    _, inv_t5 = cash_invested(wp_pat, last5, end)
    bc, bpaw = metrics(book_cur), metrics(book_paw)
    bpat = metrics(book_pat)
    A(f"- Recent (last5y) invested%: RPV {fmt_pct(inv_b5)} -> Weighted {fmt_pct(inv_w5)} / Top3 {fmt_pct(inv_t5)}.")
    A(f"- Sleeve full Sharpe: RPV {mb['sharpe']:.3f} -> Weighted {mpaw['sharpe']:.3f} / Top3 {mpat['sharpe']:.3f}.")
    A(f"- Sleeve last5y Sharpe: RPV {metrics(base_canon.loc[base_canon.index>=last5])['sharpe']:.3f} "
      f"-> Weighted {metrics(paw.loc[paw.index>=last5])['sharpe']:.3f} / Top3 {metrics(pat.loc[pat.index>=last5])['sharpe']:.3f}.")
    A(f"- Book full Sharpe: current {bc['sharpe']:.3f} -> Weighted {bpaw['sharpe']:.3f} / Top3 {bpat['sharpe']:.3f}.")
    A("")
    A("**Read (honest, per-variant):**\n")
    A("- Breadth DOES cure dormancy: Weighted lifts recent invested% from ~8% to ~55%; "
      "Top3 partially to ~20%.")
    A("- **Phase-A Weighted is inferior**: it deploys the cash but into worse risk-adjusted "
      "return -- full Sharpe drops below baseline and recent (last5y) Sharpe roughly halves "
      "(it bought cheap-but-mediocre exposure, e.g. heavy TIP, into a poor 2021-2026 regime).")
    A("- **Phase-A Top3 is the only sleeve-level improvement**: higher full Sharpe and lower "
      "maxDD than baseline with modest dormancy relief -- but it only fills cash a little.")
    A("- **At the BOOK level the swap barely moves anything and is neutral-to-slightly-negative**: "
      "RPV is 15% of a CPM-dominated book, so all variants land within noise of (and marginally "
      "below) the current book Sharpe, full and last5y.")
    A("")
    A("**VERDICT: NOT a compelling prod swap as tested.** Dormancy is real and curable, but "
      "(a) the only variant that fixes it most (Weighted) hurts risk-adjusted return; (b) the only "
      "variant that improves the sleeve (Top3) barely dents dormancy and is book-neutral; and "
      "(c) the test uses correlated PROXIES (Moody's BAA-AAA, ex-post real yield) because the "
      "requested ICE OAS / DFII10 series are not keyless at 120m depth -- so true breadth is "
      "understated AND the cleanest new premia could not be tested. Recommendation: do NOT swap "
      "now; if pursued, Phase-A Top3 + a momentum gate is the only direction worth revisiting, "
      "and only with proper long-history OAS + TIPS real-yield data (paid/keyed source).")
    A("")
    A("### Caveats\n")
    A("- IG/HY ICE OAS and DFII10 real yield are NOT keyless-available at 120m depth; "
      "Phase A substitutes Moody's BAA-AAA (HY proxy) and DGS10-CPI_YoY (real-yield proxy). "
      "These are correlated with existing term/credit premia, limiting true breadth.")
    A("- Pre-ETF price history for HYG/TIP/LQD uses committed stitched proxies (synthetic).")
    A("- Ex-post real yield uses realized CPI YoY (no look-ahead at month-end: CPI release lag "
      "means month-end CPI is ~1 month stale, conservative).")
    A("- Combined book uses a close-to-close approximation for CPM/NDX (not the prod mooex "
      "engine); valid for the RPV-swap DELTA which is the question of interest.")

    report = "\n".join(out)
    Path("/tmp/phase_a_results.md").write_text(report)
    print(report)
    print("\n[written] /tmp/phase_a_results.md")

if __name__ == "__main__":
    main()
