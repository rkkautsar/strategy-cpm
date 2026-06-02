# CPM-BULL-NDX

60% CPM + 20% BULL + 20% NDX.

Monthly rebalance, mooex execution (signal at month-end close, trade next-session open), no leverage, 10 bps per side base cost.

- CPM (60%): cross-asset momentum on QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC with TIP canary, strict-4 partial-safe routing, and min-var 3-of-4 at full breadth.
- BULL (20%): HAA-Simple SPY sleeve (TIP canary + SPY trend gate).
- NDX (20%): top-5 PIT Nasdaq-100 momentum sleeve with TIP + SPY trend + SPY RV20<RV252 gate.


## Headline performance

Clean window: 2008-05-30 to 2026-04-30 (post-cost, mooex).

| Strategy | Raw Sharpe | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| CPM | 1.24 | 1.11 | 12.9% | 10.3% | -13.0% | 0.99 |
| BULL | 0.97 | 0.86 | 11.4% | 11.9% | -20.4% | 0.56 |
| NDX | 1.17 | 1.11 | 27.4% | 23.1% | -31.8% | 0.86 |
| CPM-BULL 60/40 (two-sleeve) | 1.25 | 1.11 | 12.5% | 9.8% | -11.2% | 1.11 |
| PROD 60/20/20 | 1.41 | 1.29 | 15.8% | 10.9% | -10.5% | 1.51 |

Anchor (exact, clean CPM): Sharpe 1.2373, CAGR 12.92%, MaxDD -13.03%, Calmar 0.9912.

Extended window single row (canonical start):

| Strategy | Window | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|
| CPM | 1999-03-10 to 2026-04-30 | 1.24 | 12.6% | -13.1% | 0.96 |


## Literature benchmarks (clean window)

| Strategy | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| B2: AAA + TIP canary | 0.96 | 10.0% | -18.8% | 0.53 |
| B3: HAA-Simple SPY | 0.97 | 11.5% | -20.3% | 0.57 |
| B5: QQQ 12m trend | 0.89 | 16.0% | -28.6% | 0.56 |
| BB1: 60% B2 + 40% B3 | 1.11 | 10.8% | -14.8% | 0.73 |
| BB4: 60% B2 + 20% B3 + 20% B5 | 1.18 | 11.9% | -14.6% | 0.82 |
| PROD 60/20/20 | 1.41 | 15.8% | -10.5% | 1.51 |


## Concentration (single table kept: risk-contribution share, clean CPM)

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


## Robustness and operations

### Sharpe bootstrap CI (block bootstrap, B=2000, block=21, seed=42)

| Strategy | Point | 95% CI |
|---|---:|---:|
| CPM | 1.24 | [0.84, 1.64] |
| PROD 60/20/20 | 1.41 | [1.00, 1.82] |

### dSharpe verdicts (CPM vs baseline benchmarks)

| Pair | dSharpe point | CI includes zero |
|---|---:|---:|
| CPM - AAA | +0.30 | Yes |
| CPM - 60/40 | +0.45 | Yes |
| CPM - Naive 12m | +0.60 | No |
| CPM - Buy-hold vol-parity | +0.59 | No |

### Crisis MaxDD (extended series, within-calendar windows)

| Episode | Window | MaxDD |
|---|---|---:|
| GFC | 2007-10 to 2009-06 | -13.1% |
| Euro debt | 2011-04 to 2012-01 | -8.0% |
| COVID | 2020-02 to 2020-06 | -10.2% |
| 2022 bear | 2022-01 to 2022-12 | -5.2% |
| 2025 tariff shock | 2025-01 to 2025-12 | -10.7% |

### No-canary ablation (clean CPM)

| Variant | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| TIP canary ON | 1.24 | 12.9% | -13.0% | 0.99 |
| Canary OFF | 1.15 | 13.3% | -22.1% | 0.60 |

### Execution timing cliff (mooex, clean, CPM)

| EOM | EOM+1 | EOM+2 | EOM+3 | EOM to EOM+3 |
|---:|---:|---:|---:|---:|
| 1.2448 | 1.1753 | 1.0710 | 0.9867 | -20.7% |

- Longest underwater duration (clean CPM): 510 trading days.
- Cost sensitivity (10/25/50 bps per side): CPM Sharpe 1.24/1.13/0.96; PROD Sharpe about 1.41/1.31/1.13.
- Turnover (one-way, annualized, excluding initial portfolio establishment): 3.516 per year.
- Fully-safe months (risky fraction exactly 0 at month-end target): 26.4% (57/216).


## Forward assumptions

Forward planning Sharpe ladder (CPM):

- In-sample: 1.2373
- x0.76 implementation/regime haircut -> 0.94
- x0.85 crowding/capacity haircut -> 0.80
- x0.88 governance margin -> 0.70

Deflated Sharpe verdict: positive under conservative multiple-testing deflation.


## Governance and caveats

- Backtest only. Not yet live-traded.
- Tax-aware deployment required due monthly rotation.
- Engine is month-end discipline dependent; offset drift degrades Sharpe.
- Parameter set is fixed unless falsification gates fail.

Falsification gates:

1. Two consecutive years with out-of-sample Sharpe below 0.20.
2. Realized MaxDD worse than -18% without benchmark-relative protection benefit.
3. Slippage+fees above 35 bps per side for six consecutive rebalances.
4. Persistent process drift from month-end signal/execution schedule.


## Files

- `cpm_live.py` - CPM sleeve engine.
- `bull_spy_live.py` - BULL sleeve engine.
- `ndx_sleeve_live.py` - NDX sleeve engine.
- `build_dashboard.py` - blend assembly and dashboard generation.
- `research/` - research scripts and audit logs.
