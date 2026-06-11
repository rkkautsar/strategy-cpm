# CPM-NDX-VAL-RPV

60% CPM + 15% NDX + 15% VAL + 10% RPV.

Monthly rebalance, mooex execution (signal at month-end close, trade next-session open), no leverage, 10 bps per side base cost.

- CPM (60%): cross-asset momentum on QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC. Self-de-risks via the breadth cliff on its top-4 picks (risky fraction 0% when <=2 positives, 50% at 3, 100% at 4) and an additional HYG 13612U credit-momentum gate (forces 0% risky fraction when HYG 13612U momentum < 0); min-var 3-of-4 at full breadth; safe fraction routed to HAA best-of-safe (SHV/IEF).
- NDX (15%): top-5 PIT Nasdaq-100 momentum sleeve, gated by TIP 13612U > 0, SPY 13612U > 0, and SPY RV20 < RV252.
- VAL (15%): Nasdaq-100 fundamental value+quality stock-picking sleeve, gated by the same TIP-canary + SPY-trend + SPY-volatility activation model as NDX (routes to HAA best-of-safe when off).
- RPV (10%): 5-premia macro value sleeve (term, IG, HY, equity, real-yield) over SPY/TLT/LQD/HYG/TIP + SHV.


## Headline performance

Clean window: 2008-05-30 to 2026-04-30 (post-cost, mooex).

| Strategy | Raw Sharpe | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| PROD 60/15/15/10 | 1.61 | 1.47 | 16.0% | 9.5% | -7.1% | 2.27 |
| CPM | 1.28 | 1.16 | 13.9% | 10.6% | -10.7% | 1.30 |
| NDX | 1.14 | 1.08 | 26.5% | 23.0% | -31.8% | 0.83 |
| VAL | 1.46 | 1.36 | 20.3% | 13.3% | -17.4% | 1.16 |
| RPV | 1.05 | 0.90 | 8.8% | 8.4% | -13.4% | 0.66 |

Anchor (exact, clean CPM): Sharpe 1.2823, CAGR 13.89%, MaxDD -10.70%, Calmar 1.2978.

Extended window single row:

| Strategy | Window | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|
| CPM | 1999-03-10 to 2026-04-30 | 1.33 | 14.4% | -15.2% | 0.94 |


## Literature benchmarks

| Strategy | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| AAA + TIP canary | 0.96 | 10.1% | -18.8% | 0.54 |
| HAA-Simple SPY | 0.97 | 11.5% | -20.3% | 0.57 |
| QQQ 12m trend | 0.89 | 16.0% | -28.6% | 0.56 |
| Conservative lit blend (60% AAA+TIP / 40% HAA-Simple SPY) | 1.11 | 10.8% | -14.8% | 0.73 |
| Literature blend (60% AAA+TIP / 15% HAA-Simple QQQ / 15% HAA-Simple SPY / 10% PP) | 1.14 | 10.6% | -13.2% | 0.81 |
| PROD 60/15/15/10 | 1.61 | 16.0% | -7.1% | 2.27 |


## Concentration

Risk-contribution share, clean CPM.

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


## Robustness and operations

### Sharpe bootstrap CI (block bootstrap, B=2000, block=21, seed=42)

| Strategy | Point | 95% CI |
|---|---:|---:|
| CPM | 1.28 | [0.89, 1.68] |
| PROD 60/15/15/10 | 1.61 | [1.22, 2.02] |

### dSharpe verdicts (CPM vs baseline benchmarks)

| Pair | dSharpe point | CI includes zero |
|---|---:|---:|
| CPM - AAA | +0.35 | No |
| CPM - 60/40 | +0.50 | No |
| CPM - Naive 12m | +0.65 | No |
| CPM - Buy-hold vol-parity | +0.63 | No |

### Crisis MaxDD (extended series, within-calendar windows)

| Episode | Window | MaxDD |
|---|---|---:|
| GFC | 2007-10 to 2009-06 | -6.2% |
| Euro debt | 2011-04 to 2012-01 | -6.5% |
| COVID | 2020-02 to 2020-06 | -8.1% |
| 2022 bear | 2022-01 to 2022-12 | -5.2% |
| 2025 tariff shock | 2025-01 to 2025-12 | -10.7% |

### Gate/Cliff ablation (clean CPM)

| Variant | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| CPM (breadth cliff) | 1.28 | 13.9% | -10.7% | 1.30 |
| CPM (cliff OFF, full-invest) | 0.92 | 12.3% | -35.6% | 0.34 |

Read: breadth cliff keeps drawdown shallow; removing the cliff pushes MaxDD to -35.6%.

### Execution timing cliff (mooex, clean, CPM)

| EOM | EOM+1 | EOM+2 | EOM+3 | EOM to EOM+3 |
|---:|---:|---:|---:|---:|
| 1.2823 | 1.0520 | 1.0335 | 0.9412 | -26.6% |

- Longest underwater duration (clean CPM): 551 trading days.
- Cost sensitivity (10/25/50 bps per side): CPM Sharpe 1.28/1.19/1.05; PROD Sharpe 1.61/1.50/1.31.
- Turnover (one-way, annualized, excluding initial portfolio establishment): 3.079 per year.
- Fully-safe months (risky fraction exactly 0 at month-end target): 19.4% (42/216).


## Forward assumptions

Forward planning Sharpe ladder (CPM):

- In-sample: 1.2823
- x0.76 implementation/regime haircut -> 0.97
- x0.85 crowding/capacity haircut -> 0.83
- x0.88 governance margin -> 0.73

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

- Freeze parameter set (universe, ranker, breadth cliff, min-var 3-of-4, safe selector).
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
