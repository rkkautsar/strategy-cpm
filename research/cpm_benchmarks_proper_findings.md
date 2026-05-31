# CPM vs Canonical AAA + Investor Benchmarks (proper) -- findings

Read-only research. No prod/memo edits, no commit.

## Question

Replace the memo's bespoke 8-of-10 AAA benchmark (EWJ/RWX excluded, EFA/VNQ
standing in for EZU/IYR) with a canonical 10-asset AAA, add the investor-relevant
alternatives (60/40, naive-12m momentum, buy-hold inverse-vol), report the full
risk-adjusted metric set for each plus CPM, and test whether CPM's Sharpe edge
over each is statistically distinguishable via a paired block-bootstrap
difference-CI.

## Method

- Convention (all series, byte-identical): T+1 MOO exact (mooex), 10 bps/side,
  monthly month-end signal, via `exec_lag_moo_validation_2026_05_30._segment_returns_conv`.
- Metrics via `cpm_live.perf_metrics`: Sharpe (raw, mean*252/vol), CAGR, Vol,
  MaxDD, Calmar, Martin (CAGR/Ulcer), Ulcer.
- Difference-CI: paired block bootstrap of (Sharpe_CPM - Sharpe_bench) on the
  common clean-window daily returns, B=2000, block=21, seed=12345, 95% percentile.
- Script: `research/cpm_benchmarks_proper.py` -> `research/cpm_benchmarks_proper.json`.
- Run: `.venv/bin/python research/cpm_benchmarks_proper.py`

ANCHOR CONFIRMED exactly: CPM clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615.

## Data sources + windows

- `load_panel()` in-repo frozen stitched panel (CPM/AAA closes; GLD/TLT/IEF/SHV/
  HYG/TIP stitched from Vanguard funds; QQQ via NDX proxy pre-1999).
- `/tmp/cpm_open_cache` yfinance auto_adjust OHLC for mooex real opens.
- `research/_macro_cache/{EWJ,RWX,EZU,IYR}_ohlc.csv` -- yfinance auto_adjust OHLC,
  fetched 2026-05-31. First valid closes: EWJ 1997-12-10 (panel-trimmed; raw
  inception 1996-03-18), EZU 2000-07-31, IYR 2000-06-19, RWX 2006-12-19.
- Panel: 1997-12-10 -> 2026-05-22.
- Windows: CLEAN 18y = 2008-05-30 -> 2026-05-22. EXT = 1999-03-10 -> end for CPM
  and all CPM-universe benchmarks.

### Canonical AAA spec + proxy note

Universe (canonical, exact names): SPY, EZU, EWJ, EEM, IYR, RWX, IEF, TLT, DBC, GLD.
Rules: top-half (ceil(10/2)=5) by 6-month total-return momentum, SLSQP
minimum-variance weighting over survivors, NO canary, NO positive/cash filter
(defense comes only from bonds/gold rising in the relative-momentum rank). This
is the faithful Butler-Philbrick-Gordillo AAA, not the repo's prior canary hybrid.

PROXY/SHORTEN: RWX inception (2006-12-19) + 12m momentum warmup forces the
canonical-AAA EXT start to 2008-01-19, i.e. AAA EXT == AAA CLEAN. No pre-2006
canonical AAA is possible without substituting a proxy for RWX; not done here.
EWJ/EZU/IYR are raw ETFs (no stitch), so AAA never extends before 2008.

### Other benchmark specs

- 60/40: SPY 0.60 / IEF 0.40, monthly rebal.
- Naive 12m: CPM risky universe (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC),
  positive-12m screen, equal-weight survivors, SHV when none. No canary, no inv-vol.
- Buy-hold inverse-vol: same 8 risky assets, static inverse-vol (504d) weights,
  monthly rebal, no momentum/canary.

## Results -- CLEAN 18y (2008-05-30 -> 2026-05-22)

| Series          | Sharpe | CAGR   | Vol    | MaxDD    | Calmar | Martin | Ulcer |
|-----------------|--------|--------|--------|----------|--------|--------|-------|
| CPM             | 1.1910 | 13.44% | 11.16% | -12.67%  | 1.0615 | 3.9646 | 3.39% |
| Canonical AAA   | 0.9435 | 9.23%  | 9.92%  | -21.76%  | 0.4241 | 1.6230 | 5.69% |
| 60/40           | 0.7946 | 8.75%  | 11.42% | -29.82%  | 0.2936 | 1.4023 | 6.24% |
| Naive 12m       | 0.6493 | 8.14%  | 13.54% | -26.59%  | 0.3061 | 1.0193 | 7.98% |
| BuyHold InvVol  | 0.6860 | 8.15%  | 12.64% | -34.92%  | 0.2333 | 1.1067 | 7.36% |

## Results -- EXT (per-series start; AAA limited to 2008 by RWX)

| Series          | Start      | Sharpe | CAGR   | MaxDD   | Calmar | Martin |
|-----------------|------------|--------|--------|---------|--------|--------|
| CPM             | 1999-03-10 | 1.2142 | 13.71% | -15.93% | 0.8608 | 3.8201 |
| Canonical AAA   | 2008-01-19 | 0.9303 | 9.07%  | -21.76% | 0.4166 | 1.6027 |
| 60/40           | 1999-03-10 | 0.6910 | 7.31%  | -31.44% | 0.2324 | 1.0706 |
| Naive 12m       | 1999-03-10 | 0.8159 | 10.11% | -26.59% | 0.3803 | 1.4279 |
| BuyHold InvVol  | 1999-03-10 | 0.8421 | 9.56%  | -35.61% | 0.2684 | 1.4355 |

## Difference-CI -- CPM minus benchmark Sharpe (CLEAN, paired block bootstrap, B=2000, block=21)

| vs benchmark    | dSharpe | CI low  | CI high | includes 0? | verdict        |
|-----------------|---------|---------|---------|-------------|----------------|
| Canonical AAA   | +0.2475 | -0.0688 | +0.6073 | YES         | within-noise   |
| 60/40           | +0.3964 | -0.0687 | +0.8262 | YES         | within-noise   |
| Naive 12m       | +0.5417 | +0.1781 | +0.9246 | NO          | significant    |
| BuyHold InvVol  | +0.5050 | +0.0855 | +0.9069 | NO          | significant    |

## Verdict

- vs CANONICAL AAA (proper 10-asset, 6m-mom top-half, min-var, no canary): CPM
  wins on every metric -- Sharpe +0.25, Calmar 1.06 vs 0.42, Martin 3.96 vs 1.62,
  MaxDD -12.67% vs -21.76%. BUT the Sharpe difference-CI [-0.07, +0.61] INCLUDES
  ZERO -> the raw-Sharpe edge is NOT statistically distinguishable at 95%. The
  decisive, large gaps are in tail/drawdown-adjusted metrics (Calmar, Martin,
  MaxDD), which the Sharpe-only test does not capture. AAA's min-var tilt buys it
  a low vol (9.92%) and a respectable Sharpe, but with no risk-off gate its MaxDD
  is ~1.7x CPM's.
- vs 60/40: CPM dominates all metrics (Sharpe +0.40, Calmar 1.06 vs 0.29, MaxDD
  -12.67% vs -29.82%), but the Sharpe difference-CI [-0.07, +0.83] also INCLUDES
  ZERO -> Sharpe edge within-noise; the unambiguous, large edge is drawdown
  control.
- vs NAIVE 12m momentum: CPM Sharpe edge +0.54 is SIGNIFICANT (CI [+0.18, +0.92]
  excludes zero), plus crushing Calmar (1.06 vs 0.31) and Martin (3.96 vs 1.02).
- vs BUY-HOLD inverse-vol: CPM Sharpe edge +0.51 is SIGNIFICANT (CI [+0.09, +0.91]
  excludes zero); buy-hold inv-vol is the worst on MaxDD (-34.92%) and Calmar (0.23).

Plain statement of where the edge is real: CPM's Sharpe advantage is statistically
distinguishable from the naive momentum and buy-hold inverse-vol benchmarks, but
WITHIN-NOISE versus the two strongest comparators (canonical AAA, 60/40). Across
ALL four benchmarks, CPM's edge in drawdown-adjusted performance (Calmar, Martin,
MaxDD) is large and consistent -- that is where CPM's real, robust advantage lives,
not in raw Sharpe. The Martin ratio (previously unbenchmarked) shows CPM 3.96 vs
1.0-1.6 for every alternative, the widest relative gap of any metric.

## Caveats / confidence

- Difference-CI is on Sharpe only; the dramatic Calmar/Martin/MaxDD gaps are not
  bootstrap-tested here (out of scope). Confidence in those point gaps: high
  (single deterministic mooex run, same harness). Confidence in significance
  reading: medium-high (standard paired block bootstrap; block=21 ~ 1 trading
  month; B=2000).
- Canonical AAA EXT == CLEAN (RWX 2006-12 inception). No long-history AAA without
  an RWX proxy.
- Canonical AAA uses faithful relative-momentum-only selection (no positive/cash
  filter), per the AAA paper; adding an absolute-momentum gate would lower its
  MaxDD and is a known AAA variant not tested here.
- mooex falls back to close-to-close on pre-ETF-inception dates in EXT windows
  (stitched proxies); this is the standard headline convention used by the memo.
- yfinance fetch dated 2026-05-31; cached under research/_macro_cache for repro.

## Handoff

fixer: to update the memo's AAA benchmark block to the canonical 10-asset spec
and add the three investor alternatives + difference-CIs (memo edit out of analyst
scope).
