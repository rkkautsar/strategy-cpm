# CPM-NDX-VAL-RPV

60% CPM + 15% NDX + 15% VAL + 10% RPV.

Monthly rebalance, mooex execution (signal at month-end close, trade next-session open), no leverage, 10 bps per side base cost.

- CPM (60%): cross-asset momentum on QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC. Self-de-risks via the C1 breadth cliff on its top-4 picks: risky fraction 0% when <=2 positives, 50% at 3, 100% at 4; min-var 3-of-4 at full breadth; safe fraction routed to HAA best-of-safe (SHV/IEF).
- NDX (15%): top-5 PIT Nasdaq-100 momentum sleeve, gated by TIP 13612U > 0, SPY 13612U > 0, and SPY RV20 < RV252.
- VAL (15%): Nasdaq-100 fundamental value+quality stock-picking sleeve.
- RPV (10%): 5-premia macro value sleeve (term, IG, HY, equity, real-yield) over SPY/TLT/LQD/HYG/TIP + SHV.


## Headline performance

Clean window: 2008-05-30 to 2026-04-30 (post-cost, mooex).

| Strategy | Raw Sharpe | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| PROD 60/15/15/10 | 1.57 | 1.44 | 16.7% | 10.2% | -9.9% | 1.69 |
| CPM | 1.26 | 1.14 | 13.8% | 10.7% | -10.7% | 1.29 |
| NDX | 1.17 | 1.11 | 27.4% | 23.1% | -31.8% | 0.86 |
| VAL | 1.52 | 1.43 | 23.5% | 14.6% | -17.4% | 1.35 |
| RPV | 1.29 | 0.93 | 4.7% | 3.6% | -6.0% | 0.77 |

Anchor (exact, clean CPM): Sharpe 1.2613, CAGR 13.81%, MaxDD -10.70%, Calmar 1.2911.

Extended window single row:

| Strategy | Window | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|
| CPM | 1999-03-10 to 2026-04-30 | 1.28 | 14.0% | -15.2% | 0.92 |


## Literature benchmarks

| Strategy | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| B2: AAA + TIP canary | 0.96 | 10.0% | -18.8% | 0.53 |
| B3: HAA-Simple SPY | 0.97 | 11.5% | -20.3% | 0.57 |
| B5: QQQ 12m trend | 0.89 | 16.0% | -28.6% | 0.56 |
| BB1: 60% B2 + 40% B3 | 1.11 | 10.8% | -14.8% | 0.73 |
| BB4: 60% B2 + 20% B3 + 20% B5 | 1.18 | 11.9% | -14.6% | 0.82 |
| PROD 60/15/15/10 | 1.57 | 16.7% | -9.9% | 1.69 |


## Concentration

Risk-contribution share, clean CPM.

| Asset | Share |
|---|---:|
| SPHQ | 19.9% |
| QQQ | 18.8% |
| GLD | 17.4% |
| EFA | 13.2% |
| TLT | 9.4% |
| DBC | 8.7% |
| EEM | 7.7% |
| VNQ | 4.9% |

Top-3 share: 56.1%.


## Robustness and operations

### Sharpe bootstrap CI (block bootstrap, B=2000, block=21, seed=42)

| Strategy | Point | 95% CI |
|---|---:|---:|
| CPM | 1.26 | [0.86, 1.67] |
| PROD 60/15/15/10 | 1.57 | [1.16, 1.99] |

### dSharpe verdicts (CPM vs baseline benchmarks)

| Pair | dSharpe point | CI includes zero |
|---|---:|---:|
| CPM - AAA | +0.33 | Yes |
| CPM - 60/40 | +0.47 | No |
| CPM - Naive 12m | +0.62 | No |
| CPM - Buy-hold vol-parity | +0.61 | No |

### Crisis MaxDD (extended series, within-calendar windows)

| Episode | Window | MaxDD |
|---|---|---:|
| GFC | 2007-10 to 2009-06 | -9.1% |
| Euro debt | 2011-04 to 2012-01 | -6.5% |
| COVID | 2020-02 to 2020-06 | -8.1% |
| 2022 bear | 2022-01 to 2022-12 | -5.2% |
| 2025 tariff shock | 2025-01 to 2025-12 | -10.7% |

### Gate/Cliff ablation (clean CPM)

| Variant | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| CPM (C1 cliff) | 1.26 | 13.8% | -10.7% | 1.29 |
| CPM (cliff OFF, full-invest) | 0.92 | 12.3% | -35.6% | 0.34 |

Read: C1 breadth cliff keeps drawdown shallow; removing the cliff pushes MaxDD to -35.6%.

### Execution timing cliff (mooex, clean, CPM)

| EOM | EOM+1 | EOM+2 | EOM+3 | EOM to EOM+3 |
|---:|---:|---:|---:|---:|
| 1.2685 | 1.1036 | 1.0310 | 1.0211 | -19.5% |

- Longest underwater duration (clean CPM): 360 trading days.
- Cost sensitivity (10/25/50 bps per side): CPM Sharpe 1.26/1.18/1.04; PROD Sharpe 1.57/1.50/1.38.
- Turnover (one-way, annualized, excluding initial portfolio establishment): 2.893 per year.
- Fully-safe months (risky fraction exactly 0 at month-end target): 11.6% (25/216).


## Forward assumptions

Forward planning Sharpe ladder (CPM):

- In-sample: 1.2613
- x0.76 implementation/regime haircut -> 0.96
- x0.85 crowding/capacity haircut -> 0.81
- x0.88 governance margin -> 0.72

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

Operational controls:

- Freeze parameter set (universe, ranker, C1 cliff, min-var 3-of-4, safe selector).
- Monthly runbook with pre-trade and post-trade audit logs.
- Quarterly revalidation of data lineage and PIT assumptions.
- Annual decision memo for keep/trim/retire based on falsification gates.


## Files

- `cpm_live.py` - CPM sleeve engine.
- `ndx_sleeve_live.py` - NDX sleeve engine.
- `value_sleeve_live.py` - VAL sleeve engine.
- `rpv_live.py` - RPV sleeve engine.
- `config.py` - production sleeve weights and constants.
- `dashboard_engine.py` - data assembly and metrics layer.
- `build_dashboard.py` - dashboard build entrypoint.
- `research/` - research scripts and audit logs.
