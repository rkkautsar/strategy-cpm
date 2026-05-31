# BULL 10y3m-inversion + rv60 -- extended OOS over T10Y3M full history (1982-2026)

Role: analyst (read-only re production; writes only research/; no production/memo files changed; no commit). Harness `research/bull_10y3m_extended_1982.py`.

**Question:** the candidate BULL enhancement is 10y3m yield-curve inversion ADDED to the rv_60d<rv_252d (rv60) vol gate. Its clean-window (2008+) edge looked CONCENTRATED in COVID-2020 (n=1). Extend over T10Y3M's full FRED history (1982-01+, daily): is the 10y3m overlay's value COVID-only or multi-crisis robust? And does the rv60 vol gate's grind-protection replicate across 1990/2001 at the correct DAILY frequency over more history?

**Three first-class rungs** (every table): **(a) HAA-Simple** = BULL trend-only (canary + SPY 13612U), NO vol gate; **(b) BULL rv60** = trend + rv60 vol gate (current production); **(c) BULL rv60+10y3m** = trend + rv60 + 10y3m inversion ADD (candidate). Marginals: (b)-(a) = does rv60 earn its keep; (c)-(b) = does 10y3m add on top.

**Convention:** T+1 close-to-close (production run_bull_qqq_backtest), gates monkeypatched, 10 bps/side. Full window 1982-01-31..2026-05-22; continuity sub-window (clean) 2008-05-30..2026-05-22. BULL sleeve only (no CPM blend; this study isolates the gate). 10y3m gate: risk-on when T10Y3M >= 0 (not inverted), contemporaneous (L0, the cleanest spec from the prior study); warmup defaults risk-on.

**Data sources + provenance:**

| Leg | Source chain |
|---|---|
| equity | repo proxy SPY (load_panel 1995+) <- yfinance SPY TR (1993-95) <- ^GSPC price (pre-1993, NO div) |
| safe_IEF | repo IEF proxy (1991-10+) <- synth 10y CMT TR from FRED DGS10 (D=7.5) |
| cash_SHV | repo SHV proxy (1991-10+) <- synth T-bill carry from FRED DTB3 |
| canary_TIP | repo TIP proxy (2000-06+) <- synth inflation-aware TIPS = synth nominal10 + CPI accrual (FRED CPIAUCSL); real TIPS mkt 1997 |
| gate_T10Y3M | FRED T10Y3M daily 1982-01-04+ |

FRED windows: DGS10 1962-01-02..2026-05-28, DTB3 1954-01-04..2026-05-28, CPIAUCSL 1947-01-01..2026-04-01, T10Y3M 1982-01-04..2026-05-29. Repo-proxy real-data starts: SPY 1995-01-04, IEF 1991-10-28, SHV 1991-10-28, TIP 2000-06-29. Panel 1980-06-02..2026-05-22. Synth 10y modified duration D=7.5.

## 1. Full-window 1982-2026 -- headline metrics (BULL sleeve)

| Rung | Sharpe | CAGR | Vol | MaxDD | Calmar | Safe mo % | Turnover/yr |
|---|---:|---:|---:|---:|---:|---:|---:|
| a_HAA_simple (trend only) | 1.0137 | 12.59% | 12.02% | -20.28% | 0.6211 | 31% | 1.70 |
| b_BULL rv60 (prod) | 1.0638 | 10.79% | 9.75% | -19.56% | 0.5515 | 54% | 2.13 |
| c_BULL rv60+10y3m (cand) | 1.1088 | 10.75% | 9.28% | -19.56% | 0.5497 | 59% | 1.81 |

Marginals (full window): (b)-(a) Sharpe +0.05, Calmar -0.07, MaxDD -0.72pp; (c)-(b) Sharpe +0.05, Calmar -0.00, MaxDD +0.00pp.

## 2. Continuity check -- clean sub-window 2008-05-30..

Sanity vs prior mooex study (numbers differ slightly: this study uses production close-to-close T+1, the prior used mooex real-open T+1).

| Rung | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| a_HAA_simple (trend only) | 0.9635 | 11.63% | 11.77% | -20.28% | 0.5735 |
| b_BULL rv60 (prod) | 0.9936 | 9.93% | 9.70% | -13.60% | 0.7305 |
| c_BULL rv60+10y3m (cand) | 1.0021 | 9.35% | 9.04% | -12.02% | 0.7780 |

## 3. Per-episode max drawdown (BULL sleeve)

| Episode | (a) HAA | (b) rv60 | (c) rv60+yc |
|---|---:|---:|---:|
| 1990 recession | -16.77% | -16.77% | -16.77% |
| 2000-02 dot-com | -13.86% | -13.46% | -9.26% |
| 2008-09 GFC | -10.10% | -10.10% | -10.10% |
| 2011 euro/dgrade | -17.18% | -6.75% | -6.75% |
| 2015 china/oil | -2.89% | -2.89% | -2.89% |
| 2018-Q4 | -0.02% | -0.02% | -0.02% |
| 2020-COVID | -13.60% | -13.60% | -4.68% |
| 2022 grind | -10.61% | -0.30% | -0.30% |

## 4. Per-episode total return (BULL sleeve)

| Episode | (a) HAA | (b) rv60 | (c) rv60+yc |
|---|---:|---:|---:|
| 1990 recession | 1.74% | 1.74% | 1.74% |
| 2000-02 dot-com | 8.00% | 5.45% | 20.65% |
| 2008-09 GFC | 6.14% | 16.17% | 16.17% |
| 2011 euro/dgrade | -8.93% | 3.01% | 3.01% |
| 2015 china/oil | 4.56% | 4.56% | 4.56% |
| 2018-Q4 | 0.36% | 0.36% | 0.36% |
| 2020-COVID | 1.70% | -4.06% | 7.27% |
| 2022 grind | -1.27% | 0.94% | 0.94% |

## 5. Marginal effects per episode (return pp / drawdown pp)

(b)-(a) = rv60 vol gate contribution; (c)-(b) = 10y3m overlay contribution. d_ret +ve = gate added return; d_dd -ve = gate made drawdown shallower (better).

| Episode | (b)-(a) d_ret | (b)-(a) d_dd | (c)-(b) d_ret | (c)-(b) d_dd |
|---|---:|---:|---:|---:|
| 1990 recession | +0.00 | +0.00 | +0.00 | +0.00 |
| 2000-02 dot-com | -2.55 | -0.40 | +15.20 | -4.20 |
| 2008-09 GFC | +10.02 | +0.00 | +0.00 | +0.00 |
| 2011 euro/dgrade | +11.94 | -10.43 | +0.00 | +0.00 |
| 2015 china/oil | +0.00 | +0.00 | +0.00 | +0.00 |
| 2018-Q4 | +0.00 | +0.00 | +0.00 | +0.00 |
| 2020-COVID | -5.77 | +0.00 | +11.33 | -8.92 |
| 2022 grind | +2.21 | -10.31 | +0.00 | +0.00 |

## 6. Mechanism context

10y3m inverted (T10Y3M < 0) on 60 of 532 month-end signals; inverted years: 1989, 2000, 2006-07, 2019-20, 2022-25. But the contemporaneous (L0) gate only flipped the BULL decision *during* a drawdown when the inversion PERSISTED into the selloff. In 1989->1990 and 2006-07->2008 the curve had re-steepened before the crash hit, so the L0 gate was risk-on through those drops (zero marginal). In 2000 (dot-com) and 2019-20 (COVID) the inversion overlapped the drawdown, so the overlay protected. In 2022 the rv60 gate was already in cash, so 10y3m was redundant (zero marginal). Full-window worst drawdowns are NOT in the episode list: (a) HAA -20.28% troughing 2010-09 (summer-2010 correction), (b)/(c) -19.56% troughing 1998-09 (LTCM/Russia) -- neither gate catches these, so the headline MaxDD barely moves across rungs.

## 7. Verdict

### Q1 -- Does 10y3m+rv60 survive as a multi-crisis-robust enhancement (>=3 independent recessions), or is it COVID-2020-driven?

**PARTIAL -- not COVID-only, but below the >=3 bar. Keep as cheap optional overlay, do NOT promote as a proven multi-crisis mechanism.**

- Extending to 1982 DOWNGRADES the clean-window n=1 overfit flag: the 10y3m overlay is positive in TWO independent recessions, dot-com 2000-02 (+15.20pp return, -4.20pp drawdown) AND COVID-2020 (+11.33pp return, -8.92pp drawdown). So it is NOT solely COVID-driven -- dot-com is a genuine second, independent crisis.
- But it is zero in the other six episodes (1990, 2008, 2011, 2015, 2018-Q4, 2022), so 2 of 8. The >=3-independent-recession robustness bar is NOT met.
- The overlay is essentially FREE on the full window: Sharpe +0.045 (1.064 -> 1.109), CAGR -0.04pp (10.79% -> 10.75%), Calmar and MaxDD unchanged. That is the strongest point in its favor -- it adds risk-adjusted return at no CAGR cost and never hurt any episode.
- Overfit cautions remain: the L0-contemporaneous spec only earns when an inversion happens to persist into the drawdown (luck of overlap -- it missed 1990 and 2008 because the curve re-steepened first), and curve-choice (3m vs 2y) plus lag (L0 vs L6/L12) are still researcher degrees of freedom carried from the clean-window study.

Verdict: a defensible cheap-optionality overlay (free Sharpe, helps 2 distinct crises, never hurts) -- NOT a kill, but NOT a proven >=3-crisis mechanism either. Treat as optional, not must-have; do not over-claim.

### Q2 -- Does the rv60 vol gate's grind-protection replicate across 1990/2001 too, or stay 2018/2022-only?

**NO replication in the two OLDEST grinds (1990, 2001). rv60 grind-protection is a modern-era (2008+) phenomenon.**

- rv60 fires strongly in 2011 (+11.94pp return, -10.43pp drawdown) and 2022 (+2.21pp return, -10.31pp drawdown), and adds return in 2008-09 GFC (+10.02pp, same drawdown). So it does extend BEYOND 2018/2022 -- 2011 and 2008 are additional wins.
- But it does NOT replicate in 1990 (zero marginal -- all three rungs took the same -16.77%) or in 2001/dot-com (return -2.55pp, drawdown only -0.40pp -- effectively no protection).
- It also COSTS in COVID-2020 (-5.77pp return, zero drawdown help -- the crash was too fast for a 60d realized-vol crossover) and slightly in dot-com.
- Full-window cost: rv60 (b vs a) improves Sharpe +0.050 but LOWERS CAGR -1.80pp (12.59% -> 10.79%) and WORSENS Calmar (0.62 -> 0.55); MaxDD essentially unchanged (its worst DDs, 1998 LTCM and 2010, are not vol-crossover-catchable).

Verdict: rv60's "repeatable grind-protection mechanism" is supported for the modern/post-2008 regime (2008, 2011, 2022) but is REGIME-DEPENDENT -- it does not generalize to 1990 or 2001, whipsaws in fast crashes (COVID), and over 44 years costs CAGR and Calmar in exchange for a vol/Sharpe improvement. The grind-protection is real but narrower and more regime-conditioned than a clean-window read suggests.

### Drop-the-gate vs keep vs keep+10y3m (full 1982-2026, BULL sleeve)

| Option | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| (a) drop vol gate (HAA-Simple) | 1.014 | 12.59% | -20.28% | 0.62 |
| (b) keep rv60 (prod) | 1.064 | 10.79% | -19.56% | 0.55 |
| (c) keep rv60 + 10y3m | 1.109 | 10.75% | -19.56% | 0.55 |

- On Sharpe: (c) > (b) > (a). The gates buy risk-adjusted return by cutting vol.
- On CAGR and Calmar: (a) wins (highest CAGR 12.59%, best Calmar 0.62). The vol gate's protection in 2008/2011/2022 does not pay for its drag in the long bulls and its whipsaw in COVID/dot-com, over a 44-year horizon.
- 10y3m on top of rv60 is the strict free improvement over rv60 alone (Sharpe +0.045 at ~0 CAGR cost).
- Takeaway: if the objective is Sharpe/vol-control, keep+10y3m is best; if the objective is CAGR/Calmar, dropping the gate wins over the full history. The case for the vol gate is risk-control in the modern regime, not long-run return.

## 8. Overfitting flags + data caveats

- **10y3m overfit:** 2 of 8 episodes drive the overlay (dot-com, COVID); below the >=3 bar. L0-contemporaneous timing depends on the inversion overlapping the drawdown (missed 1990/2008). Curve-choice (3m vs 2y) and lag (L0/L6/L12) are researcher degrees of freedom from the prior study. Mitigant: the overlay is free on the full window and never hurts.
- **rv60 regime-dependence:** grind-protection works 2008+ (2008/2011/2022) but NOT 1990/2001, and costs CAGR/Calmar over 44y. Modern-regime conditioned.
- **Equity proxy:** pre-1993 equity = ^GSPC PRICE returns (NO dividends) -> understates equity total return ~3-4%/yr in the 1980s, depressing all-rung CAGR in 1982-1993 and most affecting the most-equity-exposed rung (a). The 1990-recession episode sits entirely in this price-only zone (its absolute returns are price-only).
- **TIP canary proxy:** real TIPS market began 1997; repo TIP proxy starts 2000-06. Pre-2000 the canary uses a SYNTHETIC inflation-aware TIPS proxy = synthetic nominal 10y (DGS10 duration return, D=7.5) + CPI principal accrual (FRED CPIAUCSL MoM). It is inflation-aware but model-derived, not market. The canary is a secondary gate here; treat the 1982-2000 canary state as approximate.
- **Safe/cash proxy:** pre-1991-10, IEF = synthetic 10y constant-maturity TR (carry + D*-dyield, D=7.5) from FRED DGS10; SHV = synthetic T-bill carry from FRED DTB3. Duration approximation, not a tradable fund.
- **Convention:** this study uses production close-to-close T+1 (run_bull_qqq_backtest) for apples-to-apples over 1982-2026 (real-open MOO data only exists 1999+). Clean-window numbers therefore differ from the prior mooex study (e.g. clean BULL rv60 Sharpe 0.994 here vs 1.1005 mooex); relative ordering (c > b > a in Sharpe) is preserved. Treat absolute Sharpe levels as convention-specific.

Data sources: FRED (T10Y3M, DGS10, DTB3, CPIAUCSL); yfinance (^GSPC, SPY); repo proxy panel via `cpm_live.load_panel`. Windows + provenance in section header. Harness: `research/bull_10y3m_extended_1982.py`; results JSON: `research/bull_10y3m_extended_1982.json`.

