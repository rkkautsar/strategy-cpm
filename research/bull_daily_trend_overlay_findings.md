# BULL Daily 200d-SMA Intramonth Trend-Exit Overlay - Findings

Question: does a conventional daily Faber 200-day SMA intramonth crash exit on the BULL sleeve reduce the LIVE 3-sleeve 60/20/20 blend drawdown, and at what CAGR/Sharpe cost? NO tuned percentage (pure SMA cross).

Primary eval = LIVE 3-sleeve 60/20/20 blend. BULL standalone + 60/40 two-sleeve reported for reference.


## Variants

- **V0**: monthly-only (prod baseline)

- **V1**: daily 200d SMA exit, NO intramonth re-entry, BULL-only (NDX monthly)

- **V2**: daily 200d SMA exit, WITH intramonth re-entry on 200d reclaim, BULL-only

- **V3**: daily 200d, NO re-entry, cascade exit to NDX intramonth

- **V4**: daily 200d, WITH re-entry, cascade exit to NDX intramonth

- **V5**: daily 210d SMA (10-month Faber, secondary signal), NO re-entry, BULL-only


Execution: exit observed at close[d] -> position effective day d+1 (T+1), matching the monthly gate. Safe leg = best-of-safe (SHV/IEF) at sig_d. Cost 10bps/side on every position change (incl intramonth).


## Window: Clean 2008-05-30..2026-05-22  (18.0y)


### LIVE 3-sleeve 60/20/20 blend (PRIMARY)

| Variant | RawSharpe | ExcessSharpe | CAGR | Vol | MaxDD | Calmar | BullFlips/yr |
|---|---|---|---|---|---|---|---|
| V0 | 1.503 | 1.503 | 17.94% | 11.43% | -11.62% | 1.54 | 3.7 |
| V1 | 1.476 | 1.476 | 17.44% | 11.35% | -11.49% | 1.52 | 4.0 |
| V2 | 1.492 | 1.492 | 17.72% | 11.38% | -11.72% | 1.51 | 4.6 |
| V3 | 1.422 | 1.422 | 16.56% | 11.24% | -10.63% | 1.56 | 4.0 |
| V4 | 1.479 | 1.479 | 17.41% | 11.31% | -11.27% | 1.54 | 4.6 |
| V5 | 1.479 | 1.479 | 17.44% | 11.32% | -11.49% | 1.52 | 3.9 |

### BULL standalone

| Variant | RawSharpe | ExcessSharpe | CAGR | Vol | MaxDD | Calmar | Flips/yr |
|---|---|---|---|---|---|---|---|
| V0 | 1.100 | 1.100 | 11.78% | 10.66% | -12.02% | 0.98 | 3.7 |
| V1 | 0.926 | 0.926 | 9.46% | 10.36% | -12.68% | 0.75 | 4.0 |
| V2 | 1.027 | 1.027 | 10.73% | 10.47% | -14.51% | 0.74 | 4.6 |
| V3 | 0.926 | 0.926 | 9.46% | 10.36% | -12.68% | 0.75 | 4.0 |
| V4 | 1.027 | 1.027 | 10.73% | 10.47% | -14.51% | 0.74 | 4.6 |
| V5 | 0.928 | 0.928 | 9.44% | 10.30% | -12.68% | 0.74 | 3.9 |

### 60/40 two-sleeve (60% CPM + 40% BULL) - reference

| Variant | RawSharpe | ExcessSharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|
| V0 | 1.347 | 1.347 | 13.60% | 9.84% | -9.82% | 1.38 |
| V1 | 1.275 | 1.275 | 12.64% | 9.72% | -9.82% | 1.29 |
| V2 | 1.317 | 1.317 | 13.17% | 9.77% | -10.50% | 1.25 |
| V3 | 1.275 | 1.275 | 12.64% | 9.72% | -9.82% | 1.29 |
| V4 | 1.317 | 1.317 | 13.17% | 9.77% | -10.50% | 1.25 |
| V5 | 1.280 | 1.280 | 12.64% | 9.68% | -9.82% | 1.29 |

### Intramonth-crash episodes - blend MaxDD (and total return)

| Episode | V0 | V1 | V2 | V3 | V4 | V5 |
|---|---|---|---|---|---|---|
| 2008 GFC (2008-05-30..2009-06-30) | -9.3%/+3.5% | -9.3%/+3.5% | -9.3%/+3.5% | -9.3%/+3.5% | -9.3%/+3.5% | -9.3%/+3.5% |
| 2018Q4 (2018-10-01..2018-12-31) | -11.6%/-10.2% | -11.0%/-10.0% | -11.2%/-10.3% | -8.9%/-8.5% | -9.6%/-9.1% | -11.0%/-10.0% |
| 2020 COVID (2020-02-01..2020-04-30) | -9.8%/+6.7% | -9.8%/+6.7% | -9.8%/+6.7% | -9.8%/+6.7% | -9.8%/+6.7% | -9.8%/+6.7% |
| 2020 full (2020-01-01..2020-12-31) | -9.8%/+40.8% | -9.8%/+40.8% | -9.8%/+40.8% | -9.8%/+40.8% | -9.8%/+40.8% | -9.8%/+40.8% |
| 2022 (2022-01-01..2022-12-31) | -5.8%/+4.8% | -5.8%/+4.8% | -5.8%/+4.8% | -5.8%/+4.8% | -5.8%/+4.8% | -5.8%/+4.8% |

(cell = MaxDD% / total-return% over the episode window)


### Whipsaw / false-positive cohort (V1 daily 200d, no re-entry)

- Exit events fired: **8** (0.4/yr)

- Genuine crashes avoided (SPY fwd<=0 from exit to month-end): **3** (38%), mean fwd SPY -0.90%

- Whipsaws (SPY fwd>0, exit locked loss + missed rebound): **5** (62%), mean fwd SPY +3.38%

- Net mean fwd SPY across all exits: **+1.77%** (negative = exits net-protective)


  Exit episodes detail (sig month -> exit day -> fwd SPY to month-end):

  - 2010-04-30 -> exit 2010-05-20 -> +0.24%

  - 2012-10-31 -> exit 2012-11-14 -> +4.75%

  - 2014-09-30 -> exit 2014-10-13 -> +7.44%

  - 2016-05-31 -> exit 2016-06-27 -> +3.09%

  - 2018-09-28 -> exit 2018-10-11 -> -1.93%

  - 2019-04-30 -> exit 2019-05-31 -> +0.00%

  - 2023-09-29 -> exit 2023-10-25 -> +1.37%

  - 2026-02-27 -> exit 2026-03-20 -> -0.77%


## Window: Stress 1999-03-10..2026-05-22  (27.2y)


### LIVE 3-sleeve 60/20/20 blend (PRIMARY)

| Variant | RawSharpe | ExcessSharpe | CAGR | Vol | MaxDD | Calmar | BullFlips/yr |
|---|---|---|---|---|---|---|---|
| V0 | 1.397 | 1.397 | 15.54% | 10.75% | -12.69% | 1.22 | 3.8 |
| V1 | 1.383 | 1.383 | 15.21% | 10.65% | -12.69% | 1.20 | 4.1 |
| V2 | 1.382 | 1.382 | 15.24% | 10.68% | -12.69% | 1.20 | 5.4 |
| V3 | 1.344 | 1.344 | 14.61% | 10.56% | -12.69% | 1.15 | 4.1 |
| V4 | 1.360 | 1.360 | 14.88% | 10.61% | -12.69% | 1.17 | 5.4 |
| V5 | 1.385 | 1.385 | 15.21% | 10.63% | -12.69% | 1.20 | 4.0 |

### BULL standalone

| Variant | RawSharpe | ExcessSharpe | CAGR | Vol | MaxDD | Calmar | Flips/yr |
|---|---|---|---|---|---|---|---|
| V0 | 0.980 | 0.980 | 10.27% | 10.54% | -12.49% | 0.82 | 3.8 |
| V1 | 0.884 | 0.884 | 8.72% | 10.02% | -12.68% | 0.69 | 4.1 |
| V2 | 0.887 | 0.887 | 8.87% | 10.16% | -14.51% | 0.61 | 5.4 |
| V3 | 0.884 | 0.884 | 8.72% | 10.02% | -12.68% | 0.69 | 4.1 |
| V4 | 0.887 | 0.887 | 8.87% | 10.16% | -14.51% | 0.61 | 5.4 |
| V5 | 0.885 | 0.885 | 8.70% | 9.98% | -12.68% | 0.69 | 4.0 |

### 60/40 two-sleeve (60% CPM + 40% BULL) - reference

| Variant | RawSharpe | ExcessSharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|
| V0 | 1.292 | 1.292 | 12.65% | 9.58% | -11.79% | 1.07 |
| V1 | 1.249 | 1.249 | 12.00% | 9.44% | -11.79% | 1.02 |
| V2 | 1.250 | 1.250 | 12.07% | 9.48% | -11.79% | 1.02 |
| V3 | 1.249 | 1.249 | 12.00% | 9.44% | -11.79% | 1.02 |
| V4 | 1.250 | 1.250 | 12.07% | 9.48% | -11.79% | 1.02 |
| V5 | 1.252 | 1.252 | 12.00% | 9.41% | -11.79% | 1.02 |

### Intramonth-crash episodes - blend MaxDD (and total return)

| Episode | V0 | V1 | V2 | V3 | V4 | V5 |
|---|---|---|---|---|---|---|
| 2008 GFC (2008-05-30..2009-06-30) | -9.3%/+3.6% | -9.3%/+3.6% | -9.3%/+3.6% | -9.3%/+3.6% | -9.3%/+3.6% | -9.3%/+3.6% |
| 2018Q4 (2018-10-01..2018-12-31) | -11.6%/-10.2% | -11.0%/-10.0% | -11.2%/-10.3% | -8.9%/-8.5% | -9.6%/-9.1% | -11.0%/-10.0% |
| 2020 COVID (2020-02-01..2020-04-30) | -9.8%/+6.7% | -9.8%/+6.7% | -9.8%/+6.7% | -9.8%/+6.7% | -9.8%/+6.7% | -9.8%/+6.7% |
| 2020 full (2020-01-01..2020-12-31) | -9.8%/+40.8% | -9.8%/+40.8% | -9.8%/+40.8% | -9.8%/+40.8% | -9.8%/+40.8% | -9.8%/+40.8% |
| 2022 (2022-01-01..2022-12-31) | -5.8%/+4.8% | -5.8%/+4.8% | -5.8%/+4.8% | -5.8%/+4.8% | -5.8%/+4.8% | -5.8%/+4.8% |

(cell = MaxDD% / total-return% over the episode window)


### Whipsaw / false-positive cohort (V1 daily 200d, no re-entry)

- Exit events fired: **16** (0.6/yr)

- Genuine crashes avoided (SPY fwd<=0 from exit to month-end): **6** (38%), mean fwd SPY -1.35%

- Whipsaws (SPY fwd>0, exit locked loss + missed rebound): **10** (62%), mean fwd SPY +2.21%

- Net mean fwd SPY across all exits: **+0.88%** (negative = exits net-protective)


  Exit episodes detail (sig month -> exit day -> fwd SPY to month-end):

  - 1999-08-31 -> exit 1999-09-23 -> +0.78%

  - 2000-06-30 -> exit 2000-07-28 -> +0.00%

  - 2000-08-31 -> exit 2000-09-21 -> -1.14%

  - 2002-03-28 -> exit 2002-04-03 -> -4.27%

  - 2004-06-30 -> exit 2004-07-21 -> +0.87%

  - 2004-07-30 -> exit 2004-08-03 -> +0.83%

  - 2004-09-30 -> exit 2004-10-13 -> +2.31%

  - 2005-09-30 -> exit 2005-10-06 -> +0.43%

  - 2010-04-30 -> exit 2010-05-20 -> +0.24%

  - 2012-10-31 -> exit 2012-11-14 -> +4.75%

  - 2014-09-30 -> exit 2014-10-13 -> +7.44%

  - 2016-05-31 -> exit 2016-06-27 -> +3.09%

  - 2018-09-28 -> exit 2018-10-11 -> -1.93%

  - 2019-04-30 -> exit 2019-05-31 -> +0.00%

  - 2023-09-29 -> exit 2023-10-25 -> +1.37%

  - 2026-02-27 -> exit 2026-03-20 -> -0.77%


## Verdict

### Blend deltas vs V0 (Clean window)

- V1: MaxDD -11.49% (d+0.14pp), CAGR 17.44% (d-0.49pp), Sharpe 1.476 (d-0.027), Calmar 1.52 (d-0.02)

- V2: MaxDD -11.72% (d-0.10pp), CAGR 17.72% (d-0.22pp), Sharpe 1.492 (d-0.010), Calmar 1.51 (d-0.03)

- V3: MaxDD -10.63% (d+1.00pp), CAGR 16.56% (d-1.37pp), Sharpe 1.422 (d-0.081), Calmar 1.56 (d+0.02)

- V4: MaxDD -11.27% (d+0.35pp), CAGR 17.41% (d-0.53pp), Sharpe 1.479 (d-0.024), Calmar 1.54 (d+0.00)

- V5: MaxDD -11.49% (d+0.14pp), CAGR 17.44% (d-0.49pp), Sharpe 1.479 (d-0.024), Calmar 1.52 (d-0.02)


### Blend deltas vs V0 (Stress window)

- V1: MaxDD -12.69% (d+0.00pp), CAGR 15.21% (d-0.33pp), Sharpe 1.383 (d-0.015)

- V2: MaxDD -12.69% (d+0.00pp), CAGR 15.24% (d-0.30pp), Sharpe 1.382 (d-0.015)

- V3: MaxDD -12.69% (d+0.00pp), CAGR 14.61% (d-0.93pp), Sharpe 1.344 (d-0.053)

- V4: MaxDD -12.69% (d+0.00pp), CAGR 14.88% (d-0.66pp), Sharpe 1.360 (d-0.037)

- V5: MaxDD -12.69% (d+0.00pp), CAGR 15.21% (d-0.33pp), Sharpe 1.385 (d-0.012)


### Synthesis

**1. Where the blend MaxDD actually lives.** V0 blend MaxDD = -11.62% (Clean) is the 2018-Q4 selloff - the one genuine intramonth-crash episode the monthly gate missed (Nov-30 signal stayed risk-on; crash accelerated into late Dec; next re-eval Dec-31). The daily 200d exit fired 2018-10-11 and DID cut that episode: 2018Q4 blend MaxDD -11.6% -> -11.0% (V1 bull-only) -> -8.9% (V3 cascade).

**2. But cutting one episode barely moves the blend floor.** Bull-only (V1): once 2018Q4 is trimmed, the next-worst blend drawdown elsewhere (~-11.5%, not an intramonth crash) becomes binding, so global blend MaxDD improves only +0.14pp (-11.62% -> -11.49%) while CAGR drops -0.49pp and Sharpe -0.027. Net: a wash on DD, a real cost on return. Stress window: V1 MaxDD identical to V0 (-12.69%, 0.00pp) with -0.33pp CAGR.

**3. 2020-COVID is NOT a daily-overlay win.** Contrary to the premise, the monthly gate already handled 2020 (blend DD -9.8%, identical across ALL variants). The Feb-28 month-end signal de-risked BULL for March before the daily 200d cross could add value; the intramonth exit only touched the last 1-2 days of Feb. So of the two hypothesized 'missed' episodes, only 2018-Q4 is real.

**4. The signal is whipsaw-dominated.** Daily 200d exit fired 8x (Clean) / 16x (Stress). Only 38% were genuine crashes avoided; 62% were whipsaws (SPY rose after exit, mean +3.38% Clean / +2.21% Stress missed). Net mean forward SPY across ALL exits = +1.77% (Clean) / +0.88% (Stress) - POSITIVE, i.e. on average the exit fired and then the market went UP. Same false-positive structure as the RV-gate cohort, but worse: the RV gate at least had net-protective true-positive vol asymmetry; this raw SMA cross forfeits return on net.

**5. Cascade (V3) buys more DD but at a steep price.** Cascading the (whipsaw-prone) daily exit to the high-momentum NDX sleeve cuts blend MaxDD by -1.00pp (-11.62% -> -10.63%, Clean) - the only variant with a material DD reduction. But it costs -1.37pp CAGR and -0.081 Sharpe, because the 62% false-positive exits now also forfeit NDX rebound upside. Calmar barely budges (1.54 -> 1.56). In Stress, cascade does NOT even reduce MaxDD (-12.69%, 0.00pp) yet still costs -0.93pp CAGR.

**6. Re-entry (V2/V4) is not a fix.** Allowing 200d-reclaim re-entry recovers some CAGR vs no-reentry but worsens BULL standalone MaxDD to -14.51% (re-entering mid-chop, whipsawed again) and pushes V2 blend MaxDD to -11.72% - WORSE than V0. The 10-month (210d, V5) secondary signal is materially identical to the 200d primary.

### Philosophy cost

The overlay converts BULL (V1/V2/V5) - and for the only DD-meaningful variant V3, ALSO NDX - from a monthly-simple, end-of-month-only strategy into a DAILY-monitored one. That is a large operational/complexity increase (daily SPY-vs-200d check, intramonth rebalances, daily execution discipline) against the explicit monthly-simple design intent.

### Adopt / Reject / Conditional

**REJECT** (all bull-only variants V1/V2/V5): no meaningful blend-DD reduction (<=0.14pp Clean, 0.00pp Stress), a real CAGR cost (-0.3 to -0.5pp), Sharpe/Calmar both down, and the trigger is whipsaw-dominated (62% false positives, net-positive forfeited return). Fails the user's own bar (meaningful MaxDD cut, acceptable CAGR cost, not whipsaw-dominated) on all three counts.

**REJECT** (cascade V3/V4): the only variant with a material DD cut (-1.0pp Clean) pays -1.37pp CAGR and -0.08 Sharpe, leaves Calmar flat, does nothing in the Stress window, and doubles the daily-monitoring burden to two sleeves. The DD/CAGR trade is poor and regime-fragile.

**Bottom line:** The daily 200d-SMA overlay does NOT cleanly reduce the blend drawdown. It cuts the single 2018-Q4 episode but the next-worst non-crash drawdown re-binds the floor, so bull-only is a wash; the only material cut (cascade) is bought with disproportionate CAGR/Sharpe loss and only in one window. Combined with the whipsaw-dominated trigger and the monthly-simple philosophy cost, this is not a worthwhile change. Keep V0.
