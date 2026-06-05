# CPM-8: QQQ+SPHQ -> IWF+IWD swap, PROXY-BACKED extended window

Role: analyst (exploratory). Research only. CPM prod/memo/docs UNCHANGED. No commit.
Date: 2026-06-02. Script: `research/cpm_iwf_iwd_proxy_2026_06_02.py`
JSON: `research/cpm_iwf_iwd_proxy_2026_06_02.json`

## Question

The prior swap test (`cpm_iwf_iwd_swap_2026_06_02.py`) live-fetched IWF/IWD
(inception 2000-05-26), leaving a ~14-month pre-inception gap in the EXTENDED
window, so its EXT comparison was flagged untrustworthy. Raw EXT *hinted*
IWF+IWD slightly better (Sharpe 1.2712 vs 1.2549). This run proxies IWF/IWD back
through the full EXT window for a trustworthy head-to-head, then asks:

(a) With proper proxies, does the EXT verdict hold, vanish, or reverse?
(b) Combined clean+EXT: is growth+value a real improvement over QQQ+SPHQ, or
    within-noise?
(c) Proxy choice + stitching + residual caveat.

## Method

- Mechanism: full CPM R1 M1 (byte-identical `cpm_mech_wf` reused), universe
  CPM-8 with the only change being the US-equity pair.
  - Baseline: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC
  - Swap:     IWF, IWD, EFA, EEM, VNQ, GLD, TLT, DBC
- Convention: mooex (T+1 MOO), both-252, 10bps/side. Windows: CLEAN 2008-05-30..,
  EXT 1999-03-10..2026-05-22.

### Proxy + stitching (mirrors the repo's existing pre-ETF convention)

- IWF (Russell 1000 Growth ETF) <- VIGRX (Vanguard Growth Index, daily, from
  1992-10-30) for dates before IWF inception (2000-05-26); live IWF after.
- IWD (Russell 1000 Value  ETF) <- VIVAX (Vanguard Value  Index, daily) for
  dates before IWD inception; live IWD after.
- Return-continuous splice (same as `research/archive/stitch_kmlm.py` and
  `data/*_stitched_daily.csv`): scale = ETF[inception] / PROXY[inception];
  scaled proxy used for dates < inception (the proxy's own daily return drives
  the boundary day), live ETF for dates >= inception.

### Apples-to-apples with the baseline

- The QQQ+SPHQ baseline is itself proxied in EXT: QQQ <- NDX index proxy
  (`data/qqq_stitched_daily.csv`, 1985-1999), SPHQ <- long-history proxy panel
  column (`data/proxy_adjusted_close_daily.csv`, 1995+). Both sides use pre-ETF
  proxies through EXT.
- mooex falls back to close-to-close on rebalance days lacking real OHLC.
  Baseline SPHQ has no OHLC pre-2005 (cc-fallback in EXT); proxied IWF/IWD have
  no OHLC pre-2000-05-26 (same cc-fallback). Execution methodology matched.

## Gates (both PASS)

| gate                                   | actual    | target    | pass |
|----------------------------------------|-----------|-----------|------|
| CLEAN full CPM-8 anchor (QQQ+SPHQ)     | 1.255673  | 1.255673  | yes  |
| CLEAN swap reproduces prior live-fetch | 1.241674  | 1.2417    | yes  |

## Results

EXT span enabled by the proxy: 1999-03-10 .. 2026-05-22 (full coverage of the
style pair; prior run had IWF/IWD missing 1999-03 .. 2000-05).

### CLEAN (2008-05-30 .. 2026-05-22) -- unchanged, confirms prior

| metric        | QQQ+SPHQ | IWF+IWD  | delta    |
|---------------|----------|----------|----------|
| Sharpe        |  1.2557  |  1.2417  | -0.0140  |
| Sortino       |  1.8058  |  1.7845  | -0.0213  |
| CVaR95 ratio  |  8.2295  |  8.1706  | -0.0588  |
| Calmar        |  1.0076  |  0.9702  | -0.0374  |
| Martin        |  4.2571  |  3.7895  | -0.4676  |
| MaxDD         | -13.03%  | -13.03%  | +0.00pp  |
| CAGR          | 13.13%   | 12.64%   | -0.49pp  |
| Vol           | 10.28%   | 10.02%   | -0.25pp  |
| Turnover (ann)|  7.08    |  7.41    | +0.32    |

### EXT (1999-03-10 .. 2026-05-22) -- now PROXY-BACKED, trustworthy

| metric        | QQQ+SPHQ | IWF+IWD  | delta    |
|---------------|----------|----------|----------|
| Sharpe        |  1.2549  |  1.2712  | +0.0163  |
| Sortino       |  1.8114  |  1.8401  | +0.0287  |
| CVaR95 ratio  |  8.2770  |  8.4500  | +0.1730  |
| Calmar        |  0.9712  |  0.8866  | -0.0846  |
| Martin        |  4.1168  |  3.9497  | -0.1671  |
| MaxDD         | -13.14%  | -14.14%  | -1.00pp  |
| CAGR          | 12.76%   | 12.54%   | -0.23pp  |
| Vol           |  9.97%   |  9.66%   | -0.31pp  |
| Turnover (ann)|  6.80    |  6.98    | +0.17    |

Daily pair correlation: corr(IWF,IWD) 0.836 EXT / 0.864 CLEAN vs
corr(QQQ,SPHQ) 0.819 EXT / 0.881 CLEAN. IWF+IWD is slightly MORE correlated in
EXT and slightly less in CLEAN -- no clear orthogonality advantage for the
growth/value pair (the diversification hypothesis is not supported).

## Key finding: the ~14mo gap was never an artifact

The proxy-backed EXT metrics are **byte-identical** to the prior live-fetch
(gap) run (IWF+IWD Sharpe 1.2712, MaxDD -14.14%, Calmar 0.8866, CAGR 12.54%;
QQQ+SPHQ Sharpe 1.2549, etc.). Reason: across all 14 monthly rebalances in the
pre-inception sub-window (1999-03-31 .. 2000-04-28) the CPM mechanism was
**100% risk-off** -- canary triggered, holding only SHV (then IEF), zero risky
equity for BOTH universes. So proxy availability of IWF/IWD could not change
anything; the gap fell entirely inside a defensive period. The prior EXT hint
was real, not a data-gap artifact.

## Answers

(a) The EXT verdict HOLDS, exactly: IWF+IWD keeps a small Sharpe edge
    (+0.0163; 1.2712 vs 1.2549), unchanged by the proxy because the gap window
    was fully risk-off. It does not vanish or reverse. But the EXT read is MIXED
    -- IWF+IWD wins the vol-adjusted ratios (Sharpe/Sortino/CVaR) while QQQ+SPHQ
    wins every drawdown/return metric (MaxDD -1.00pp deeper, Calmar -0.085,
    Martin -0.167, CAGR -0.23pp).

(b) Combined clean+EXT: WITHIN-NOISE / no real improvement. CLEAN favors
    QQQ+SPHQ across the board (Sharpe +0.014, Calmar +0.037, Martin +0.468,
    CAGR +0.49pp, equal MaxDD). EXT is a wash (Sharpe edge to IWF+IWD, drawdown
    and CAGR edge to QQQ+SPHQ). All deltas are tiny (|dSharpe| <= 0.016). The
    growth+value style pair is NOT a compelling improvement over QQQ+SPHQ; no
    case to swap. The orthogonality hypothesis (IWF/IWD more diversifying) is
    also not borne out by the correlations.

(c) Proxy: IWF<-VIGRX, IWD<-VIVAX (Vanguard Growth/Value index funds, daily
    from 1992-10-30), return-continuous splice at the 2000-05-26 ETF inception.
    Residual caveats: (i) VIGRX/VIVAX track Vanguard's growth/value
    construction, not the exact Russell 1000 Growth/Value indices that
    IWF/IWD track -- minor pre-2000 style-construction drift is possible, but
    this is MOOT for the verdict since the entire pre-inception window was
    risk-off (no style exposure held); (ii) mooex pre-inception uses cc-fallback
    (no OHLC), identical to baseline SPHQ pre-2005. HIGH overfit caution: single
    2-ticker swap, single in-sample window, point-estimates only (no bootstrap).

## Reproduce

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
.venv/bin/python research/cpm_iwf_iwd_proxy_2026_06_02.py
```
