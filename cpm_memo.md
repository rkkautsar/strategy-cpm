# CPM Research Memo

## Scope

This memo documents current CPM engine behavior at EVAL_END=2026-04-30.
All metrics are post-cost, mooex (signal at month-end close, execute at next-session open), 10 bps per side unless stated.

- Clean window: 2008-05-30 to 2026-04-30.
- Extended window: 1999-03-10 to 2026-04-30.


## 1) Headline

Anchor (exact, clean CPM): Sharpe 1.2373, CAGR 12.92%, MaxDD -13.03%, Calmar 0.9912.

| Strategy | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| CPM | 1.24 | 12.9% | -13.0% | 0.99 |
| PROD 60/20/20 | 1.41 | 15.8% | -10.5% | 1.51 |


## 2) Robustness snapshot

### 2.1 Sharpe bootstrap CI (block bootstrap, B=2000, block=21, seed=42)

| Strategy | Point | 95% CI |
|---|---:|---:|
| CPM | 1.24 | [0.84, 1.64] |
| PROD 60/20/20 | 1.41 | [1.00, 1.82] |

### 2.2 Benchmark comparison and dSharpe verdict

| Benchmark | Sharpe | CAGR | MaxDD | Calmar | dSharpe (CPM - benchmark) | dSharpe CI includes zero |
|---|---:|---:|---:|---:|---:|---:|
| AAA (canonical) | 0.94 | 9.1% | -21.8% | 0.42 | +0.30 | Yes |
| 60/40 SPY/IEF | 0.79 | 8.7% | -29.8% | 0.29 | +0.45 | Yes |
| Naive 12m momentum | 0.64 | 8.0% | -26.6% | 0.30 | +0.60 | No |
| Buy-hold vol-parity | 0.65 | 7.7% | -34.8% | 0.22 | +0.59 | No |

### 2.3 Crisis MaxDD (extended series, within-calendar windows)

| Episode | Window | MaxDD |
|---|---|---:|
| GFC | 2007-10 to 2009-06 | -13.1% |
| Euro debt | 2011-04 to 2012-01 | -8.0% |
| COVID | 2020-02 to 2020-06 | -10.2% |
| 2022 bear | 2022-01 to 2022-12 | -5.2% |
| 2025 tariff shock | 2025-01 to 2025-12 | -10.7% |

### 2.4 Extended window single row

| Strategy | Window | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|
| CPM | 1999-03-10 to 2026-04-30 | 1.24 | 12.6% | -13.1% | 0.96 |

### 2.5 No-canary ablation (clean)

| Variant | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| CPM (TIP canary ON) | 1.24 | 12.9% | -13.0% | 0.99 |
| CPM (canary OFF) | 1.15 | 13.3% | -22.1% | 0.60 |

Read: canary keeps drawdown materially shallower while preserving high Sharpe.

### 2.6 Underwater and execution-timing cliff

- Longest underwater duration (clean CPM): 510 trading days.

Offset cliff, mooex, clean:

| Strategy | EOM | EOM+1 | EOM+2 | EOM+3 | EOM to EOM+3 |
|---|---:|---:|---:|---:|---:|
| CPM | 1.2448 | 1.1753 | 1.0710 | 0.9867 | -20.7% |


## 3) Structural attribution

### 3.1 Coupled HAA to CPM ladder (clean)

| Step | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| HAA baseline (all OFF) | 0.8516 | 9.2% | -14.7% | 0.63 |
| +U universe | 0.9976 | 11.2% | -15.0% | 0.75 |
| +R ranker | 1.0660 | 11.6% | -13.0% | 0.89 |
| +M min-var 3-of-4 | 1.2373 | 12.9% | -13.0% | 0.99 |

### 3.2 2^3 main effects (clean)

| Factor | dSharpe | dCalmar | dMaxDD |
|---|---:|---:|---:|
| Universe (U) | +0.2151 | +0.2470 | +1.10pp |
| Ranker (R) | +0.0659 | +0.0435 | -0.03pp |
| Min-var (M) | +0.0906 | +0.0340 | -0.07pp |

Min-var corner increment at U1,R1: Sharpe 1.0660 -> 1.2373 (+0.1714), MaxDD change +0.01pp.

### 3.3 Leave-one-out and de-tilt checks (clean)

- ex-EFA is near-flat: dSharpe +0.0026.
- Drawdown-critical core remains GLD, TLT, VNQ.

| Variant | Sharpe | dSharpe vs CPM | MaxDD |
|---|---:|---:|---:|
| CPM baseline | 1.2373 | - | -13.03% |
| ex-GLD | 1.0550 | -0.1823 | -15.81% |
| ex-TLT | 1.1391 | -0.0982 | -14.00% |
| ex-VNQ | 1.1875 | -0.0498 | -12.98% |
| De-tilt US sleeve to SPY-only-US | 1.1065 | -0.1308 | -13.03% |


## 4) Concentration, turnover, and costs

### 4.1 Concentration (single table kept: risk-contribution share, clean)

| Asset | Share |
|---|---:|
| SPHQ | 23.1% |
| GLD | 18.0% |
| QQQ | 16.2% |
| EFA | 12.9% |
| DBC | 9.2% |
| VNQ | 8.6% |
| EEM | 6.3% |
| TLT | 5.8% |

Top-3 share: 57.2%.

### 4.2 Turnover and safe-state definitions

- One-way turnover per year: 3.516.
- Definition: monthly one-way turnover, annualized, excluding initial portfolio establishment.
- Fully-safe months: 26.4% (57/216).
- Definition: month-end target risky fraction equals 0.

### 4.3 Cost sensitivity (condensed)

At 10/25/50 bps per side, CPM Sharpe is 1.24/1.13/0.96; PROD Sharpe is about 1.41/1.31/1.13.


## 5) Forward assumptions, DSR, and governance

### 5.1 Deflated Sharpe verdict

DSR remains positive under conservative multiple-testing deflation.

### 5.2 Forward Sharpe haircut ladder

- In-sample CPM Sharpe: 1.2373.
- x0.76 implementation/regime haircut -> 0.94.
- x0.85 crowding/capacity haircut -> 0.80.
- x0.88 governance margin -> 0.70 forward planning Sharpe.

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
