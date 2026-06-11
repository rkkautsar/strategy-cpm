# CPM Research Memo

## Scope

This memo documents current CPM engine behavior at EVAL_END=2026-04-30.
All metrics are post-cost, mooex (signal at month-end close, execute at next-session open), 10 bps per side unless stated.

- Clean window: 2008-05-30 to 2026-04-30.
- Extended window: 1999-03-10 to 2026-04-30.


## 1) Headline

Anchor (exact, clean CPM): Sharpe 1.2823, CAGR 13.89%, MaxDD -10.70%, Calmar 1.2978.

| Strategy | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| CPM | 1.28 | 13.9% | -10.7% | 1.30 |
| PROD 60/15/15/10 | 1.61 | 16.0% | -7.1% | 2.27 |


## 2) Robustness snapshot

### 2.1 Sharpe bootstrap CI (block bootstrap, B=2000, block=21, seed=42)

| Strategy | Point | 95% CI |
|---|---:|---:|
| CPM | 1.28 | [0.89, 1.68] |
| PROD 60/15/15/10 | 1.61 | [1.22, 2.02] |

### 2.2 Benchmark comparison and dSharpe verdict

| Benchmark | Sharpe | CAGR | MaxDD | Calmar | dSharpe (CPM - benchmark) | dSharpe CI includes zero |
|---|---:|---:|---:|---:|---:|---:|
| AAA (canonical) | 0.94 | 9.1% | -21.8% | 0.42 | +0.35 | No |
| 60/40 SPY/IEF | 0.79 | 8.7% | -29.8% | 0.29 | +0.50 | No |
| Naive 12m momentum | 0.64 | 8.0% | -26.6% | 0.30 | +0.65 | No |
| Buy-hold vol-parity | 0.65 | 7.7% | -34.7% | 0.22 | +0.63 | No |

### 2.3 Crisis MaxDD (extended series, within-calendar windows)

| Episode | Window | MaxDD |
|---|---|---:|
| GFC | 2007-10 to 2009-06 | -6.2% |
| Euro debt | 2011-04 to 2012-01 | -6.5% |
| COVID | 2020-02 to 2020-06 | -8.1% |
| 2022 bear | 2022-01 to 2022-12 | -5.2% |
| 2025 tariff shock | 2025-01 to 2025-12 | -10.7% |

### 2.4 Extended window single row

| Strategy | Window | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|
| CPM | 1999-03-10 to 2026-04-30 | 1.33 | 14.4% | -15.2% | 0.94 |

### 2.5 Gate/Cliff ablation (clean)

| Variant | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| CPM (C1 cliff) | 1.28 | 13.9% | -10.7% | 1.30 |
| CPM (cliff-OFF naive full-invest) | 0.92 | 12.3% | -35.6% | 0.34 |

Read: C1 cliff keeps drawdown materially shallower while preserving high Sharpe.

### 2.6 Underwater and execution-timing cliff

- Longest underwater duration (clean CPM): 551 trading days.

Offset cliff, mooex, clean:

| Strategy | EOM | EOM+1 | EOM+2 | EOM+3 | EOM to EOM+3 |
|---|---:|---:|---:|---:|---:|
| CPM | 1.2823 | 1.0520 | 1.0335 | 0.9412 | -26.6% |


## 3) Structural attribution

### 3.1 Coupled HAA to CPM ladder (clean)

| Step | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| HAA baseline (all OFF) | 0.8536 | 9.2% | -14.7% | 0.63 |
| +U universe | 0.9996 | 11.3% | -15.0% | 0.75 |
| +R ranker | 1.0681 | 11.7% | -13.0% | 0.89 |
| +M min-var 3-of-4 | 1.2396 | 12.9% | -13.0% | 0.99 |
| +C cliff/HYG/de-canary | 1.2823 | 13.9% | -10.7% | 1.30 |

The U/R/M factorial captures only universe, ranker, and min-var selection. The final +C step adds the three 2026-06-09 risk-control changes (breadth-cliff curve, HYG 13612U credit gate, de-canary) that sit outside the HAA<->CPM factor set; it closes the +0.043 Sharpe gap to current production CPM.

### 3.2 2^3 main effects (clean)

| Factor | dSharpe | dCalmar | dMaxDD |
|---|---:|---:|---:|
| Universe (U) | +0.2153 | +0.2473 | +1.10pp |
| Ranker (R) | +0.0659 | +0.0435 | -0.03pp |
| Min-var (M) | +0.0907 | +0.0340 | -0.07pp |

Min-var corner increment at U1,R1: Sharpe 1.0681 -> 1.2396 (+0.1716), MaxDD change +0.01pp.

These main effects are computed over the U/R/M cube (terminating at the pre-2026-06-09 ramp+TIP CPM, Sharpe 1.2396); the breadth-cliff, HYG, and de-canary changes are not factors in this cube. See the +C step in 3.1 for the path to current production CPM (1.2823).

### 3.3 Leave-one-out and de-tilt checks (clean)

- ex-EFA and ex-VNQ are near-flat: dSharpe -0.0114 and -0.0142.
- Drawdown-critical core remains GLD, DBC, TLT.

| Variant | Sharpe | dSharpe vs CPM | MaxDD |
|---|---:|---:|---:|
| CPM baseline | 1.2823 | - | -10.70% |
| ex-GLD | 1.0409 | -0.2414 | -13.25% |
| ex-TLT | 1.1997 | -0.0826 | -12.13% |
| ex-VNQ | 1.2681 | -0.0142 | -10.73% |
| De-tilt US sleeve to SPY-only-US | 1.1210 | -0.1613 | -13.64% |


## 4) Concentration, turnover, and costs

### 4.1 Concentration (single table kept: risk-contribution share, clean)

| Asset | Share |
|---|---:|
| SPHQ | 29.3% |
| QQQ | 20.2% |
| EFA | 18.6% |
| VNQ | 11.1% |
| EEM | 8.2% |
| GLD | 6.5% |
| DBC | 6.1% |
| TLT | 0.0% |

Top-3 share: 68.1%. TLT contributes ~0 (its raw risk contribution is slightly negative; it acts as a hedge).

### 4.2 Turnover and safe-state definitions

- One-way turnover per year: 3.079.
- Definition: monthly one-way turnover, annualized, excluding initial portfolio establishment.
- Fully-safe months: 19.4% (42/216).
- Definition: month-end target risky fraction equals 0.

### 4.3 Cost sensitivity (condensed)

At 10/25/50 bps per side, CPM Sharpe is 1.28/1.19/1.05; PROD Sharpe is about 1.61/1.50/1.31.


## 5) Forward assumptions, DSR, and governance

### 5.1 Deflated Sharpe verdict

DSR remains positive under conservative multiple-testing deflation.

### 5.2 Forward Sharpe haircut ladder

- In-sample CPM Sharpe: 1.2823.
- x0.76 implementation/regime haircut -> 0.97.
- x0.85 crowding/capacity haircut -> 0.83.
- x0.88 governance margin -> 0.73 forward planning Sharpe.

### 5.3 Falsification and governance

Hard fail conditions:

1. Two consecutive years with out-of-sample Sharpe below 0.20.
2. Realized MaxDD worse than -18% without benchmark-relative protection benefit.
3. Median slippage+fees greater than 35 bps per side for six consecutive rebalances.
4. Signal/execution drift from month-end process discipline.

Operational controls:

- Freeze parameter set (universe, ranker, strict-4, min-var 3-of-4, safe selector).
- Monthly runbook with pre-trade and post-trade audit logs.
- Quarterly revalidation of data lineage and PIT assumptions.
- Annual decision memo for keep/trim/retire based on falsification gates above.
