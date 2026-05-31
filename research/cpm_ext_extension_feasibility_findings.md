# CPM Extended-Window Extension Feasibility

Analyst research. Read-only re production. Writes research/ only. No prod/memo
edits. No commit. Data-availability + proxy-feasibility assessment ONLY (no full
backtest run).

## Question

CPM's extended ("ext") window currently starts 1999-03-10 (~27y).
1. Which asset BINDS that start?
2. Per CPM-universe asset: proxy used + earliest reliable date.
3. How far back could CPM be rigorously extended with proper proxies; realistic
   floor + fidelity tradeoffs?

## Verdict (up front)

- **Binding asset (data floor):** VNQ. Under the current proxy panel the latest
  first-valid date among the risky+safe pool is VNQ 1996-05-14 (proxy = Vanguard
  VGSIX, inception 1996-05-13). Next-binding: EFA 1996-04-30. Everything else in
  the pool reaches back to <=1995-01-04 (the proxy file's hard floor) or earlier.
- **The 1999-03-10 ext_start is a CONVENTION anchor, not a hard data limit.** It
  equals QQQ's live ETF inception (1999-03-10; see `stitch_qqq_ndx.py:3`) and is
  hardcoded in the research harnesses (`research/bull_factorial_faithful_haa.py:97`).
  Given VNQ data from 1996-05-14 plus the 504d inverse-vol cov warmup, the panel
  could already produce valid weights from ~1998-04 -- about 11 months of slack
  is left on the table under existing proxies.
- **Realistic FAITHFUL floor: ~1994-05** (EEM via Vanguard VEIEX real fund 1994-05;
  VNQ via FTSE NAREIT 1972; SPHQ via S&P 500 Quality index backfill ~1994). That
  is +5y over the current ext_start (27y -> ~32y). Weak spots there: SPHQ (index
  backfill, not a tradeable fund) and VNQ (index vs fund).
- **Stretched floor: ~1988** (EEM via MSCI EM index 1987-12, non-investable;
  SPHQ via an academic quality-factor reconstruction). +11y (-> ~38y) but EM and
  quality become synthetic/index proxies -- material fidelity loss.
- **Pre-1988: infeasible** for a faithful CPM. No investable EM index/data exist
  before MSCI EM (Dec 1987); EM is the hard wall. NDX (QQQ) reaches 1985 and
  EAFE/GSCI/gold/Treasuries reach ~1970, but without EM the universe is no longer
  CPM.
- **Recommendation: not worth stretching below ~1994.** The class-significance
  sanity check (`research/cpm_class_significance_sanity_findings.md`) shows even a
  ~52-year sample fails to clear 95% significance vs 60/40 for respected TAA
  peers; going 27y -> 32y (+18% sample) or even -> 38y (+40%) buys marginal power
  while importing synthetic EM/quality history. The cheap, clean win is reclaiming
  the ~11mo already-available slack (1998-04 .. 1999-03) and, if a longer
  descriptive (not inferential) panel is wanted, a faithful 1994 floor. The clean
  18y ETF-era window (2008-05-30..) remains the decisive lens regardless.

## How the panel/proxy is constructed (code refs)

- Universe definitions: `cpm_live.py:33-50` (risky 8 = QQQ, SPHQ, EFA, EEM, VNQ,
  GLD, TLT, DBC), `cpm_live.py:52` (SAFE_POOL = SHV, IEF), `cpm_live.py:56`
  (CANARY = HYG, TIP; rule any_positive, `cpm_live.py:57`).
- `load_panel`: `cpm_live.py:129`.
  - Long-history proxy panel loaded first: `cpm_live.py:138-140`
    (`data/proxy_adjusted_close_daily.csv`, all columns floored at 1995-01-04).
  - Audited stitch overwrites: `cpm_live.py:147-161` (each stitched CSV replaces
    the same-named proxy column). Documented proxies in the comment block
    `cpm_live.py:147-153`:
    - HYG <- VWEHX (Vanguard HY) 1980-01+
    - TIP <- VIPSX (Vanguard TIPS) 2000-06+
    - SHV <- VFISX (Vanguard ST Treasury) 1991-10+
    - IEF <- VFITX (Vanguard Int Treasury) 1991-10+
    - TLT <- VUSTX (Vanguard LT Treasury) 1986-05+
    - GLD <- World Bank monthly pre-2000-08 (`cpm_live.py:155`)
    - QQQ <- ^NDX (Nasdaq-100 index) 1985-10 .. 1999-03 (`cpm_live.py:161`,
      `research/archive/stitch_qqq_ndx.py:1-9`)
  - Fully-missing tickers backfilled from yfinance: `cpm_live.py:175-194`.
- ext_start convention 1999-03-10 hardcoded: `research/bull_factorial_faithful_haa.py:97`
  (= QQQ live inception). Confirmed VNQ->ext gap = 1030 days (~2.82y).

## Per-asset table (post-stitch panel)

Group: R=risky, S=safe, C=canary. "Panel start" = first_valid in the live
post-stitch panel. "Current proxy" = what fills pre-live history today.

| Asset | Grp | Live ETF inception | Current proxy | Panel start | Longer proxy (start) | Faithful? |
|-------|-----|--------------------|---------------|-------------|----------------------|-----------|
| QQQ  | R | 1999-03-10 | ^NDX index | 1985-10-01 | ^NDX (1985-10); index pre-launch 1985-01 | good (index QQQ tracks) |
| SPHQ | R | 2005-12-06 | synthetic (proxy file floor) | 1995-01-04 | S&P 500 Quality idx backfill ~1994; AQR QMJ quality factor 1957 (academic); SPY/^GSPC crude (loses quality) | WEAK (no tradeable quality fund pre-2005) |
| EFA  | R | 2001-08-14 | EAFE-type fund (proxy) | 1996-04-30 | MSCI EAFE TR (USD) 1970; VEURX/Europe 1990 | good (EAFE is a real index) |
| EEM  | R | 2003-04-07 | EM fund (proxy file floor) | 1995-01-04 | VEIEX (Vanguard EM fund) 1994-05; MSCI EM index 1987-12 (non-investable) | OK to 1994 (fund); WEAK 1988-94 (index); WALL pre-1988 |
| VNQ  | R | 2004-09-23 | VGSIX (Vanguard REIT idx) | 1996-05-14 | FTSE NAREIT All-Equity REIT TR 1972; Wilshire US REIT 1978 | good (NAREIT is a real index) |
| GLD  | R | 2004-11-18 | World Bank gold monthly pre-2000-08 | 1995-01-02 | LBMA/World Bank gold spot ~1968-1970 | good (spot gold) |
| TLT  | R | 2002-07-22 | VUSTX (Vanguard LT Tsy) | 1986-05-19 | FRED long-Treasury TR (20-30y) 1970s | good |
| DBC  | R | 2006-02-03 | synthetic commodity (proxy file floor) | 1995-01-04 | S&P GSCI TR 1970; Bloomberg/DJ-UBS Cmdty 1991 | moderate (GSCI energy-heavy vs DBC broad basket) |
| HYG  | C | 2007-04-11 | VWEHX (Vanguard HY) | 1980-01-02 | VWEHX 1980; ICE BofA US HY index 1986 | good |
| TIP  | C | 2003-12-05 | VIPSX/stitch | 2000-06-29 | synthetic IEF+CPI real-return (TIPS market began 1997) | WEAK pre-1997 (synthetic); but HYG-OR-TIP canary so HYG covers |
| SHV  | S | 2007-01-11 | VFISX (Vanguard ST Tsy) | 1991-10-28 | FRED 3m T-bill 1954/1970s | good |
| IEF  | S | 2002-07-22 | VFITX (Vanguard Int Tsy) | 1991-10-28 | FRED 7-10y Treasury TR 1970s | good |

Fund-inception checks (yfinance auto_adjust min date) confirm the panel starts:
VGSIX 1996-05-13, VEIEX 1994-05-04, VWEHX 1980-01-02, VUSTX 1986-05-19,
VFITX/VFISX 1991-10-28, ^NDX 1985-10-01, ^GSPC 1970-01-02, VEURX 1990-06-18.

## Binding ladder (current panel, risky+safe common start)

```
HYG  C 1980-01-02   (canary; HYG-or-TIP)
QQQ  R 1985-10-01
TLT  R 1986-05-19
SHV  S 1991-10-28
IEF  S 1991-10-28
GLD  R 1995-01-02   <- proxy-file floor
SPHQ R 1995-01-04   <- proxy-file floor
EEM  R 1995-01-04   <- proxy-file floor
DBC  R 1995-01-04   <- proxy-file floor
EFA  R 1996-04-30   <- next-binding
VNQ  R 1996-05-14   <- BINDING (data floor)
TIP  C 2000-06-29   (canary; covered by HYG)
```

Common risky+safe start = 1996-05-14 (VNQ). +504d cov warmup -> usable ~1998-04-20.
Chosen ext_start 1999-03-10 (= QQQ inception) sits ~11mo above the usable floor.

## Realistic-floor map (fidelity tiers)

- **Clean ETF era (~2008-05-30):** all live ETFs, real opens, full fidelity. The
  decisive inferential lens.
- **Good proxy (current, 1999-03 convention; data-capable ~1996-05/usable ~1998-04):**
  VNQ=VGSIX, EFA=EAFE fund, EEM/SPHQ/DBC at 1995 floor, QQQ=NDX, treasuries/gold
  audited. Minor proxy contamination pre-2006 (no real opens -> close-to-close on
  a minority of rebal days; documented across prior findings).
- **Faithful proxy floor (~1994-05):** EEM=VEIEX (real fund), VNQ=NAREIT (1972),
  SPHQ=S&P Quality backfill (~1994), DBC=GSCI/Bloomberg, others fine. Binding =
  EEM (VEIEX 1994-05) and SPHQ backfill. Fidelity compromise: SPHQ (index, not
  fund), VNQ (index vs fund), DBC (GSCI basket differs). +5y (-> ~32y).
- **Stretched proxy floor (~1988):** EEM=MSCI EM index (1987-12, non-investable),
  SPHQ=academic quality factor (QMJ-style). EFA EAFE 1970, GSCI 1970, NDX 1985,
  gold/treasuries 1970s all fine. EM + quality are synthetic/index -> material
  fidelity loss. +11y (-> ~38y).
- **Infeasible (pre-1988):** no investable EM data before MSCI EM (Dec 1987). EM
  is the wall; dropping/substituting EM changes the strategy. Quality also only
  via academic factors.

## Power vs fidelity

- Sanity check (`research/cpm_class_significance_sanity_findings.md`): even
  HAA-Simple's ~52y in-sample (Dec 1970 - Dec 2022) gives Sharpe diff vs 60/40 of
  +0.246, 95% CI [-0.058, +0.540] -- does NOT clear zero. Sub-significance is a
  class-level property.
- Going 27y -> 32y (faithful, +5y, +~18% months) or -> 38y (stretched, +11y,
  +~40% months) is unlikely to flip the significance verdict, since ~52y already
  fails. Gain is descriptive (more regimes: deeper dot-com, 1994 bond rout) not
  inferential.
- Fidelity cost of going below ~1994 is concentrated in EM (synthetic/index) and
  quality SPHQ (factor reconstruction) -- the two assets with no clean long fund
  history. High cost, low marginal power.

## Recommendation

1. Cheap clean win: reclaim the ~11mo slack already available under current
   proxies (usable from ~1998-04 vs the 1999-03 convention anchor) if a slightly
   longer ext window is desired -- zero new proxy risk.
2. Optional faithful 1994 floor (EEM=VEIEX, VNQ=NAREIT, SPHQ=S&P Quality backfill)
   for descriptive regime coverage only; flag SPHQ/VNQ as index-backfilled.
3. Do NOT stretch below ~1994 for inference: synthetic EM/quality fidelity cost
   outweighs the marginal power, and even 52y cannot clear 60/40 significance.
4. Keep the clean 18y ETF-era window as the decisive lens in all cases.

## Caveats / confidence

- High confidence: binding asset = VNQ; ext_start = QQQ-inception convention; per-
  asset panel starts (verified against proxy CSV first_valid and fund inceptions).
- Medium confidence on exact longer-proxy start dates for index series (MSCI EAFE/EM,
  NAREIT, GSCI, S&P 500 Quality backfill) -- these are standard vendor index base
  dates from domain knowledge, not re-fetched here; would need vendor confirmation
  before building. EM (MSCI EM Dec 1987) and the no-pre-1988-EM wall are robust.
- No backtest was run; this is a data-availability/feasibility assessment only.
- Proxy file is hard-floored at 1995-01-04 for several columns (SPHQ/EEM/DBC/GLD);
  underlying funds (e.g. VEIEX 1994-05) reach slightly earlier, so even the current
  proxy file is artificially capped above the faithful floor.

## Next handoff

- fixer: if a faithful 1994 floor is adopted, build/extend stitched proxy CSVs
  (EEM<-VEIEX, VNQ<-NAREIT, SPHQ<-S&P Quality backfill) and rebuild the proxy panel.
- operator/explorer: if vendor index base-date confirmation needed (MSCI/NAREIT/S&P).
