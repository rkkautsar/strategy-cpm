# BULL sleeve risk-asset choice -- findings

Question: Is SPY the right broad-equity expression for the BULL sleeve, or do
equal-weight (RSP) / factor (MTUM, SPHQ) / higher-beta (QQQ) alternatives
improve risk-adjusted return or drawdown -- without adding book concentration?

Method: vary ONLY the held risk asset in the BULL 3-layer gate (canary
HYG/TIP, asset 13612U>0, asset RV_20d<RV_252d), keeping gate structure, safe
pool, costs, and all other sleeves fixed. Evaluated primarily on the LIVE
3-sleeve 60/20/20 (CPM 60 / BULL 20 / NDX 20); also BULL standalone and a
CPM/BULL 60/40 reference.

- Script: `research/bull_risk_asset_choice.py`
- Raw table dump: `research/bull_risk_asset_choice_results.txt`
- Run: `.venv/bin/python research/bull_risk_asset_choice.py`
- Inputs: production `load_panel` (1995+), `data/ndx_constituents/prices.parquet`,
  plus live RSP / MTUM / PDP pulls (yfinance, cached `/tmp/bull_choice_cache`).
- No production file edited. The held ticker is swapped by monkeypatching
  `bull_qqq_live.BULL_TICKER` (read at call time) and a copy of
  `ndx_sleeve_live.compute_ndx_weights` whose gate keys on the current BULL
  ticker instead of hardcoded "SPY".

Verification gate PASSED. A0 (SPY) reproduces live baselines:
- 3-sleeve clean: Sharpe 1.505 / CAGR 17.94% / MaxDD -11.62% / Calmar 1.54
  (baseline 1.503 / 17.93% / -11.62%; 0.002 Sharpe diff = warmup-day rounding).
- BULL standalone clean: 1.102 / 11.78% / -12.02% (baseline ~1.10 / 11.77% / -12.02%).

## Variants

- A0 SPY (PROD) | A1 QQQ | A2 RSP (S&P500 equal-weight) | A3 MTUM (momentum) | A4 SPHQ (quality)

## Headline -- LIVE 3-sleeve 60/20/20, clean window (2008-05-30..2026-05-22)

| Variant | Sharpe | ExSharpe | CAGR% | Vol% | MaxDD% | Calmar | turn/yr |
|---------|-------:|---------:|------:|-----:|-------:|-------:|--------:|
| **A0 SPY** | **1.505** | 1.390 | 17.94 | 11.43 | **-11.62** | **1.54** | 3.70 |
| A1 QQQ  | 1.423 | 1.314 | 17.95 | 12.17 | -12.24 | 1.47 | 4.14 |
| A2 RSP  | 1.428 | 1.313 | 17.14 | 11.59 | -12.92 | 1.33 | 3.42 |
| A3 MTUM | 1.265 | 1.137 | 13.38 | 10.39 | -12.35 | 1.08 | 3.64 |
| A4 SPHQ | 1.430 | 1.312 | 16.66 | 11.26 | -13.22 | 1.26 | 3.59 |

SPY wins the primary metric (Sharpe) AND best drawdown/Calmar. No variant beats
SPY on risk-adjusted return; none improves drawdown.

## Stress window (variant start..2026-05-22)

| Variant | Sharpe | ExSharpe | CAGR% | Vol% | MaxDD% | Calmar | from |
|---------|-------:|---------:|------:|-----:|-------:|-------:|------|
| A0 SPY  | 1.397 | 1.187 | 15.54 | 10.75 | -12.69 | 1.22 | 1999-03-10 |
| A1 QQQ  | 1.327 | 1.132 | 16.08 | 11.76 | -13.25 | 1.21 | 1999-03-10 |
| A2 RSP  | 1.365 | 1.221 | 15.80 | 11.23 | -12.92 | 1.22 | 2003-05-01* |
| A3 MTUM | 1.292 | 1.143 | 13.57 | 10.27 | -12.35 | 1.10 | 2007-03-01* |
| A4 SPHQ | 1.343 | 1.129 | 14.65 | 10.60 | -13.22 | 1.11 | 1999-03-10 |

SPY best Sharpe. RSP edges SPY on Excess-Sharpe (1.221 vs 1.187) but over a
shorter, easier window (starts 2003, misses the 2000-02 bust). Not comparable.

## Sub-periods (3-sleeve)

2008: A0=A2=A3 identical (Sharpe 1.420, MaxDD -9.99) -- BULL gate was defensive
through the GFC for SPY/RSP/MTUM, so the held asset never mattered; only
QQQ/SPHQ briefly turned risk-on and lost (MaxDD -11.5/-11.0).

2020: A0 SPY dominates (Sharpe 2.193, Calmar 4.17). RSP collapses (Sharpe 1.582,
Calmar 2.14, CAGR 26.0 vs SPY 41.0) -- equal-weight badly lagged the mega-cap-led
recovery. MTUM 1.899, SPHQ 1.829, QQQ 2.056.

2022: all variants converge (Sharpe ~0.81, MaxDD -5.84) -- gate defensive nearly
all year, held asset irrelevant.

## BULL standalone, clean window

| Variant | Sharpe | CAGR% | Vol% | MaxDD% | Calmar |
|---------|-------:|------:|-----:|-------:|-------:|
| A0 SPY  | 1.102 | 11.78 | 10.66 | -12.02 | 0.98 |
| A1 QQQ  | 0.985 | 13.29 | 13.66 | -14.31 | 0.93 |
| A2 RSP  | 0.903 | 10.27 | 11.61 | -20.16 | 0.51 |
| A3 MTUM | 0.612 |  6.27 | 10.97 | -16.50 | 0.38 |
| A4 SPHQ | 1.029 | 10.90 | 10.64 | -13.42 | 0.81 |

SPY best standalone Sharpe and best MaxDD. RSP standalone drawdown -20.16% is
far worse than SPY -- its self-consistent gate (trend+RV on RSP) flipped into a
deeper hole; diluted in the blend but still a negative signal for RSP.

## CPM/BULL 60/40 reference (60% CPM / 40% BULL), clean window

| Variant | Sharpe | CAGR% | MaxDD% | Calmar |
|---------|-------:|------:|-------:|-------:|
| A0 SPY  | 1.350 | 13.60 | -9.82 | 1.38 |
| A1 QQQ  | 1.299 | 14.26 | -12.62 | 1.13 |
| A2 RSP  | 1.264 | 12.99 | -12.08 | 1.08 |
| A3 MTUM | 1.198 | 11.38 | -10.41 | 1.09 |
| A4 SPHQ | 1.334 | 13.25 | -11.04 | 1.20 |

(Interpretation note: "60/40" read as 60% CPM / 40% BULL two-sleeve, since the
study varies the BULL sleeve. SPY again best Sharpe + Calmar.)

## 2. Concentration angle (RSP) -- does equal-weight help?

The exposure report flagged mega-cap stacking. RSP genuinely de-stacks it:
SPY top-10 names ~35% of sleeve vs RSP ~0.2% each; corr(BULL,NDX) drops from
0.616 (SPY) to **0.517 (RSP)** -- the lowest of all variants. So the overlap
concern is REAL and RSP addresses it.

BUT it does not improve outcomes:
- 3-sleeve clean MaxDD: RSP **-12.92%** vs SPY **-11.62%** (130bps WORSE).
- 3-sleeve clean Calmar: RSP 1.33 vs SPY 1.54.
- 2020 recovery: RSP Calmar 2.14 vs SPY 4.17 (equal-weight missed the mega-cap rally).
- Standalone MaxDD -20.16% (worst of all).

Why: the monthly gate already exits before sustained drawdowns, so SPY's mega-cap
beta is captured on the way up and de-risked on the way down. De-stacking via
RSP only forfeits upside; the diversification (lower corr) does NOT convert to
lower blend drawdown or higher risk-adjusted return.

## 3. Overlap angle (QQQ / SPHQ) -- double-counting

- corr(BULL,NDX): QQQ **0.747**, MTUM **0.773** (highest) vs SPY 0.616. BULL=QQQ
  stacks Nasdaq on top of the NDX sleeve (always Nasdaq) and CPM's QQQ holdings
  (CPM holds QQQ in 19.4% of clean-window signal months). Book gets
  over-concentrated in Nasdaq/large-growth, raising vol (12.17%) with no Sharpe gain.
- SPHQ: CPM holds SPHQ in **57.6%** of signal months -- BULL=SPHQ is heavily
  redundant with CPM (quality double-count), and gives the worst 3-sleeve MaxDD
  (-13.22%) despite Sharpe ~ SPY.
- MTUM: highest NDX correlation (0.773, momentum tilts mega-cap tech) and the
  worst returns (CAGR 13.38%, Sharpe 1.265) -- adds concentration and lags.

## 4. Verdict -- KEEP SPY

SPY is the right BULL risk asset.

- It is best-or-tied on the PRIMARY metric (3-sleeve clean Sharpe 1.505) and
  clearly best on drawdown (-11.62%) and Calmar (1.54). It also wins the stress
  window Sharpe and the 60/40 reference.
- RSP directly addresses the exposure-report concentration finding (corr to NDX
  drops 0.616 -> 0.517) but the de-stacking does NOT improve risk-adjusted
  return or drawdown -- it WORSENS both (MaxDD -12.92% vs -11.62%, Calmar 1.33 vs
  1.54), because the gate already neutralizes mega-cap downside while RSP forfeits
  mega-cap upside (esp. 2020). The concentration concern is real at the holdings
  level but does not manifest as worse realized outcomes for SPY.
- Factors add book concentration without payoff: QQQ/MTUM double-count Nasdaq
  with the NDX sleeve (corr 0.75-0.77) and SPHQ double-counts CPM (57.6% of
  months), none beating SPY on Sharpe.

Tradeoff stated explicitly: switching to RSP would reduce measured mega-cap
overlap with the NDX sleeve, but at a cost of ~130bps worse max drawdown and a
materially lower Calmar -- the opposite of the exposure report's intent. SPY's
"concentration" is gate-protected and is a feature, not a bug, in this design.

## Caveats / confidence

- History flags: RSP live 2003-05-01 (no clean equal-weight proxy pre-2003; stress
  restricted to 2003+). MTUM live 2013-04-18, backstitched with PDP (Invesco DWA
  Momentum, live 2007-03-01) for the clean window; stress restricted to 2007+.
  SPHQ uses the production panel's existing proxy pre-2005-12. QQQ/SPY use full
  panel proxy history. Stress-window cross-variant comparisons are therefore NOT
  apples-to-apples on start date (flagged in tables).
- MTUM/PDP are different momentum methodologies (MSCI USA Momentum vs DWA relative
  strength); MTUM pre-2013 is a proxy approximation.
- Turnover = one-way annualized BULL-sleeve weight turnover only (CPM turnover is
  constant across variants since CPM is unchanged). All variants 3.4-4.1/yr; QQQ
  highest (4.14), RSP lowest (3.42). Not a differentiator.
- Confidence: HIGH for clean-window 3-sleeve conclusion (full live history, A0
  reproduces). MEDIUM for stress/factor conclusions (proxy + unequal start dates).

## Next handoff

None required -- measurement complete, recommendation is keep-SPY (no production
change). If a config change were desired despite this, route to fixer; this study
recommends against it.
