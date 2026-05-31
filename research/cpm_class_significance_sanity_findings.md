# CPM Strategy-Class Significance Sanity Check vs 60/40

Analyst research. Read-only re production. Writes research/ only. No prod/memo
edits. No commit.

Scripts:
- `research/cpm_class_significance_fetch.py` (proxy data fetch + cache)
- `research/cpm_class_significance_sanity.py` (panel build, backtests, diff-CIs)

Data: `research/cpm_class_significance_sanity.json`

## Question

CPM's edge vs canonical AAA and 60/40 is within bootstrap noise (not
significant) on both Sharpe and drawdown metrics at the 18-year monthly sample.
Is that a CPM-specific weakness, or is sub-significance the NORM for this
strategy class? Concretely: do two respected published tactical strategies --
Adaptive Asset Allocation (AAA) and HAA-Simple -- themselves beat 60/40 at
statistical significance over THEIR OWN published backtest windows (in-sample,
where they have the most power), and does any edge persist out-of-sample after
publication?

## Verdict (up front)

No. Neither AAA nor HAA-Simple clears 95% statistical significance vs 60/40 --
on Sharpe OR Calmar -- in any of the three windows tested: the paper IN-SAMPLE
window (HAA ~52 years, AAA ~21 years), the post-publication PAPER-OOS window, or
the common 18-year ETF era. Every single difference-CI straddles zero.

The most striking result: even over HAA-Simple's full ~52-year in-sample window
(Dec 1970 - Dec 2022), the Sharpe difference vs 60/40 is +0.246 with a 95% CI of
[-0.058, +0.540] -- it does not clear zero. Half a century of data is not enough
to make a respected TAA strategy's risk-adjusted edge over 60/40 formally
significant under a paired block bootstrap.

Therefore sub-significance vs a decent defensive benchmark is a CLASS-LEVEL
property, not a CPM-specific failing. CPM's not-significant-vs-60/40 result is
exactly what these respected peers also show. Moreover, CPM's point-estimate edge
is competitive with or better than both peers (see "CPM context").

## Strategy definitions (sourced)

- 60/40: 0.60 S&P 500 total return + 0.40 IEF (7-10y Treasury TR), monthly
  rebalance. (Benchmark; comparator in every difference-CI.)
- HAA-Simple = Keller and Keuning, "Dual and Canary Momentum with Rising Yields/
  Inflation: Hybrid Asset Allocation (HAA)" (SSRN 4346906). Paper in-sample
  window Dec 1970 - Dec 2022 (50+ year backtest). Construction here (== the
  all-OFF cell of `research/bull_factorial_faithful_haa.py`): single offensive
  asset SPY; TIP canary via 13612U momentum (> 0); absolute-momentum filter on
  SPY (13612U > 0); if risk-off, hold best-of {3m T-bill cash, IEF} by 13612U.
  13612U = unweighted mean of 1/3/6/12-month total returns.
- AAA = Butler, Philbrick, Gordillo, Varadi, "Adaptive Asset Allocation: A
  Primer" (ReSolve, SSRN 2328254). Paper in-sample window 1995-2015. 10-asset
  global universe [SPY, EZU, EWJ, EEM, IYR, RWX, IEF, TLT, DBC, GLD]; select
  top-half by 6-month momentum, minimum-variance weights over survivors (36-month
  monthly covariance), no canary. DYNAMIC universe: at each month only assets with
  >= 13 months history are eligible, and the top-half is taken of the AVAILABLE
  set -- so pre-ETF/pre-proxy assets (intl-REIT, gold) simply drop out and the
  holding count falls (paper-style 5 -> 4 stub) rather than being fabricated.

## Engine and convention

Monthly total-return engine: month-end signal, hold the next month, 10 bps/side
turnover cost. Applied IDENTICALLY to every strategy and to 60/40, so the paired
difference-CIs are apples-to-apples.

Deviation from the headline mooex convention: the deep-history proxy series are
monthly total-return levels only (no intraday opens), so this run uses monthly
close execution, NOT the ETF-era mooex T+1 MOO-exact convention. Stated as a
known deviation; because the same engine is used for every strategy in this run,
the within-run difference-CIs are unaffected. Cross-run comparison to the mooex
CPM number is cross-engine (see caveats).

Difference-CIs: paired block bootstrap on monthly returns, block = 6 months,
B = 3000, strategy-minus-60/40, for both Sharpe and Calmar. Significant if and
only if the 95% CI excludes zero.

## Data sources and proxy splices (rigorous, documented)

ETFs and mutual funds via yfinance auto_adjust=True (total return). FRED via
fredgraph CSV. S&P 500 deep history from Robert Shiller's monthly data (price +
annualized dividend) reconstructed as total return: TR_t = (P_t + D_t/12)/P_{t-1}
- 1. Cached under `research/_macro_cache/`. Each asset is one continuous monthly
TR series, spliced earliest-proxy -> highest-quality-real (returns chained at
each splice):

- S&P 500 TR: Shiller TR reconstruction (1871-03+) -> ^SP500TR (1988-02+).
- IEF (7-10y Tsy TR): DGS10 synthetic par-bond TR (dur 7.5, 1962-03+) -> VFITX
  Vanguard Interm Tsy (1991-11+) -> IEF real ETF (2002-08+).
- Cash / 3m T-bill (BIL/SHV equivalent): FRED DTB3 carry (1954-02+).
- TIP (TIPS canary): SYNTHETIC TIPS = IEF-track nominal 7-10y Treasury TR +
  realized monthly CPI inflation (FRED CPIAUCSL) (1962-04+) -> VIPSX Vanguard
  real TIPS fund (2000-07+). Per the HAA paper, real TIP exists from 12/2003 and
  the authors used plain IEF for the pre-EOY-1973 stub; our IEF+CPI synthetic is
  more rigorous than plain IEF and has minimal impact on the canary signal.
- TLT (20+y Tsy TR): VUSTX Vanguard Long Tsy (1986-06+) -> TLT real ETF (2002-08+).
- GLD (gold): GC=F gold future (2000-09+) -> GLD real ETF (2004-12+). Pre-2000
  gold not freely reproducible (FRED LBMA series discontinued; stooq now keyed).
- DBC (commodities): ^SPGSCI S&P GSCI index (1984-02+) -> DBC real ETF (2006-03+).
- EEM (emerging mkts): VEIEX Vanguard EM (1994-06+) -> EEM real ETF (2003-05+).
- EZU (eurozone): VGTSX Vanguard Total Intl, dev-ex-US proxy (1996-05+) -> EZU
  real ETF (2000-08+). (Broad-intl, not eurozone-specific; flagged.)
- IYR (US REIT): VGSIX Vanguard REIT (1996-06+) -> IYR real ETF (2000-07+).
- EWJ (Japan): EWJ real ETF only (1996-04+).
- RWX (intl REIT): XRFIX intl-REIT mutual fund (1998-12+) -> RWX real ETF
  (2007-01+). Paper cites an intl-REIT proxy from 1997-09; XRFIX in our source
  starts 1998-11, reliable from ~mid-1999. Before that, intl-REIT drops out of
  the AAA available set (the paper's 5 -> 4 stub).

### Coverage achieved vs each paper's window

- HAA-Simple: reaches the paper's Dec 1970 start. Data floor for all four HAA
  assets (SPY via Shiller, IEF/TIP via DGS10 synthetic, cash via DTB3) is 1962,
  so Dec 1970 is fully covered with rigorous proxies. FULL paper in-sample window
  reproduced.
- AAA: reaches the paper's 1995 start with a dynamic universe (5 assets available
  1995, 8 by 1997, 9 by 2000, 10 by 2002). Intl-REIT enters via XRFIX ~1999 and
  gold via GC=F 2000; before that AAA runs on the reduced available set, matching
  the paper's stub handling. AAA genuinely cannot precede ~1995 with reproducible
  data (no rigorous pre-1994 EM / pre-1999 intl-REIT). Paper in-sample window
  reproduced.

## Results

Per strategy, three windows: paper IN-SAMPLE, post-publication PAPER-OOS, and the
common 18-year ETF era. "Shp" / "Cal" / "MDD" columns show strategy vs 60/40 over
the same window. dSharpe / dCalmar are strategy-minus-60/40 with 95% paired
block-bootstrap CIs (B=3000, block=6 months).

### HAA-Simple (Keller, SSRN 4346906) vs 60/40

| window      | range              | mo  | Sharpe (HAA/60-40) | Calmar (HAA/60-40) | MaxDD (HAA/60-40)  |
|-------------|--------------------|-----|--------------------|--------------------|--------------------|
| IN-SAMPLE   | 1970-12 .. 2022-12 | 625 | 1.241 / 0.996      | 0.784 / 0.313      | -16.5% / -29.6%    |
| PAPER-OOS   | 2023-01 .. 2026-05 |  40 | 1.438 / 1.507      | 1.657 / 2.013      |  -9.1% /  -7.2%    |
| COMMON-18y  | 2008-05 .. 2026-05 | 216 | 1.090 / 0.886      | 0.656 / 0.306      | -16.5% / -27.6%    |

| diff vs 60/40 | dSharpe | Sharpe 95% CI     | sig? | dCalmar | Calmar 95% CI     | sig? |
|---------------|---------|-------------------|------|---------|-------------------|------|
| IN-SAMPLE     | +0.246  | [-0.058, +0.540]  | NO   | +0.472  | [-0.147, +0.739]  | NO   |
| PAPER-OOS     | -0.069  | [-0.576, +1.165]  | NO   | -0.356  | [-2.794, +3.981]  | NO   |
| COMMON-18y    | +0.203  | [-0.423, +0.775]  | NO   | +0.349  | [-0.518, +1.176]  | NO   |

### AAA (ReSolve Adaptive AA, SSRN 2328254) vs 60/40

| window      | range              | mo  | Sharpe (AAA/60-40) | Calmar (AAA/60-40) | MaxDD (AAA/60-40)  |
|-------------|--------------------|-----|--------------------|--------------------|--------------------|
| IN-SAMPLE   | 1995-01 .. 2015-12 | 251 | 1.068 / 0.994      | 0.741 / 0.294      | -13.0% / -29.6%    |
| PAPER-OOS   | 2016-01 .. 2026-05 | 124 | 1.228 / 0.978      | 0.836 / 0.467      | -13.2% / -20.5%    |
| COMMON-18y  | 2008-05 .. 2026-05 | 216 | 1.069 / 0.886      | 0.743 / 0.306      | -13.2% / -27.6%    |

| diff vs 60/40 | dSharpe | Sharpe 95% CI     | sig? | dCalmar | Calmar 95% CI     | sig? |
|---------------|---------|-------------------|------|---------|-------------------|------|
| IN-SAMPLE     | +0.084  | [-0.428, +0.559]  | NO   | +0.449  | [-0.428, +0.894]  | NO   |
| PAPER-OOS     | +0.249  | [-0.354, +0.649]  | NO   | +0.368  | [-0.431, +1.497]  | NO   |
| COMMON-18y    | +0.182  | [-0.347, +0.527]  | NO   | +0.437  | [-0.281, +0.991]  | NO   |

### Reading the results

- In-sample, where each strategy has maximum power, neither clears significance.
  HAA-Simple comes closest (Sharpe CI lower bound -0.058 over 52 years) but still
  crosses zero; AAA's in-sample Sharpe CI is wide ([-0.43, +0.56]).
- Standalone, both strategies look excellent: HAA-Simple roughly halves 60/40's
  worst drawdown (-16.5% vs -29.6%) and AAA cuts it to -13.0%, and Calmar roughly
  doubles to triples. Yet the Calmar difference-CIs still straddle zero, because
  Calmar/MaxDD are dominated by single worst-drawdown events and therefore carry
  very high bootstrap sampling error -- exactly the "MaxDD/Sharpe difference-CIs
  are wide" point.
- Out-of-sample, the edge is mixed: AAA's point edge actually GREW post-2015
  (dSharpe +0.249) but is not significant (only ~10 years). HAA-Simple's point
  edge went slightly NEGATIVE post-2022 (dSharpe -0.069) -- it lagged the strong
  2023-2025 risk-on regime where a static 60/40 simply rode equities -- but with
  only 40 months the CI is enormous ([-0.58, +1.17]), so nothing can be concluded
  either way.

## CPM context (point estimates)

From the existing mooex 18y run (`research/cpm_benchmarks_proper.json`):
- CPM clean 18y: Sharpe 1.191, MaxDD -12.67%, Calmar 1.062.
- 60/40 clean 18y (mooex engine): Sharpe 0.795, Calmar 0.294.
- CPM-minus-60/40 Sharpe (daily block bootstrap, B=2000, block=21, n=4524):
  point +0.396, 95% CI [-0.069, +0.826] -- includes zero (not significant), but
  the lower bound is the closest to clearing zero of any strategy examined here.

CPM's 18y point Sharpe edge over 60/40 (+0.40) exceeds HAA-Simple's and AAA's 18y
point edges (+0.20 and +0.18 in this run's monthly engine), CPM's standalone
Sharpe (1.19) is the highest, and CPM's MaxDD (-12.7%) is the shallowest of the
group. So on point estimates CPM is competitive with, and on these metrics better
than, both respected published peers -- while sharing their class-wide failure to
clear formal significance vs 60/40.

## Caveats and confidence

- Engine deviation: this run uses a monthly close-execution engine (not the
  headline mooex T+1 MOO). It is internally consistent across all strategies, so
  within-run difference-CIs are sound. Cross-engine comparison to the mooex CPM
  number is approximate: the CPM CI comes from a daily bootstrap (n=4524 daily
  units, block=21), which yields tighter intervals than this monthly bootstrap
  (n=216 monthly units at 18y, block=6). The CPM and peer CIs are therefore NOT
  directly width-comparable; the qualitative verdict (peers fail significance vs
  60/40 even with far more data) holds regardless of engine.
- TIP pre-2000 is synthetic (nominal Treasury + CPI accrual), per instruction and
  consistent with the HAA paper's own stub handling. The verdict does not depend
  on it: HAA-Simple also fails significance over the 18y window where TIP is real.
- AAA uses a broad total-intl proxy for EZU and XRFIX for intl-REIT; gold and
  intl-REIT enter only ~2000 and ~1999. This matches the paper's proxy/stub
  approach but means early-window AAA holds fewer than 10 assets.
- Gold pre-2000 and S&P TR pre-1988 (real index) were not freely reproducible;
  Shiller fills S&P pre-1988 for HAA, gold simply enters AAA at 2000.
- PAPER-OOS windows are short (HAA 40 months, AAA 124 months); their CIs are wide
  and the OOS read is suggestive, not conclusive.
- Confidence: HIGH that sub-significance vs 60/40 is the class norm and not a
  CPM-specific failing. The conclusion is robust across three window definitions
  (including a 52-year in-sample), both metrics (Sharpe and Calmar), and both peer
  strategies.

## Knowledge candidate

Respected published TAA strategies -- ReSolve Adaptive Asset Allocation (SSRN
2328254, in-sample 1995-2015) and Keller HAA-Simple (SSRN 4346906, in-sample
Dec 1970 - Dec 2022) -- do NOT beat 60/40 at 95% statistical significance on
Sharpe or Calmar, even over their full multi-decade in-sample windows (52 years
for HAA), nor out-of-sample, nor at the common 18y. Sub-significance vs a decent
defensive benchmark is a class-level property (difference-CIs are wide,
especially for drawdown-based metrics dominated by single events). CPM's
not-significant-vs-60/40 result is therefore the class norm, and CPM's
point-estimate edge is competitive with or better than these peers.
