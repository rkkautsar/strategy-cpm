# NDX vol gate: drop-vol-gate marginal analysis (mirror of BULL)

Role: analyst (hypothesis-driven; read-only re production; writes only to research/; no production/memo edits; no commit). EXPLORATION ONLY. Harness `research/ndx_gate_drop.py` (clones the production NDX offset=1 engine, injects a switchable vol gate).

**Question.** The NDX sleeve holds top-5 PIT Nasdaq-100 stocks when ACTIVE, else best-of-safe. Activation = the monthly BULL risk-on state = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND **vol(RV60<RV252)**. The vol gate is inherited 1:1 from BULL. Does it earn its keep over a no-gate (canary+trend-only) NDX baseline? NDX is higher-beta than BULL, so the gate could matter MORE -- tested honestly, not assumed to mirror BULL.

## BOTTOM LINE (decisive)

- **No-gate baseline (canary+trend only) clean: Calmar 0.8038 / MaxDD -38.77% / Sharpe 1.1445 / CAGR 31.17%.** With-gate (production): 0.8009 / -35.92% / 1.2035 / 28.77%.
- **Gate POINT marginal: Calmar -0.0030, Martin +0.5479, MaxDD -2.85pp, Sharpe +0.0590, CAGR -2.40pp.**
- **PAIRED BLOCK-BOOTSTRAP CI on the marginal INCLUDES 0 for Calmar [-0.3285, +0.6153] -> within noise.** Martin [-1.1396, +2.8710] excl0=False; Sharpe [-0.1929, +0.3181] excl0=False.
- **Attribution: 14 saves / 18 whipsaws (whipsaw rate 55%), net -32.3% gross QQQ over 18y.**

## 0. Anchor gate

NDX with-gate (production) clean: Sharpe **1.2035** / MaxDD **-35.92%** / Calmar **0.8009** / CAGR **28.77%** / ExcessSharpe **1.1462** vs frozen anchor 1.186 / -35.92% / 0.84 / 30.01% / 1.132 -> **MaxDD MATCH** (d=0.003pp), Sharpe MATCH. NDX constituent prices refreshed 2026-05-29; anchor CAGR/Sharpe drift ~1pp/0.02 vs frozen memo (MaxDD exact). Marginal uses SAME data both arms.

## (A) Baseline (no vol gate) vs with-gate + marginal

| Series | Window | CAGR | Vol | Sharpe | MaxDD | Calmar | Martin |
|---|---|---:|---:|---:|---:|---:|---:|
| Baseline (canary+trend) | Clean 18y | 31.17% | 26.93% | 1.1445 | -38.77% | 0.8038 | 2.4887 |
| Baseline (canary+trend) | Ext 27y | 22.48% | 23.32% | 0.9861 | -38.77% | 0.5798 | 1.9510 |
| Gate (+vol) | Clean 18y | 28.77% | 23.32% | 1.2035 | -35.92% | 0.8009 | 3.0366 |
| Gate (+vol) | Ext 27y | 20.90% | 19.83% | 1.0567 | -35.92% | 0.5819 | 2.5596 |

**Gate marginal = gate minus baseline:**
- Clean: dSharpe **+0.0590**, dCalmar **-0.0030**, dMartin **+0.5479**, dMaxDD **-2.85pp** (negative=shallower), dCAGR **-2.40pp**, dVol **-3.61pp**.
- Ext: dSharpe **+0.0706**, dCalmar **+0.0022**, dMartin **+0.6086**, dMaxDD **-2.85pp**, dCAGR **-1.57pp**.
- Flips (NDX active<->safe, clean): baseline **43**, gate **38** (gate ADDED **-5**).

### Per-crisis MaxDD: baseline vs gate (QQQ shown for scale)

| Crisis | Window | QQQ DD | Baseline DD | Gate DD | Gate dMaxDD | Gate dRet |
|---|---|---:|---:|---:|---:|---:|
| 2008 GFC | 2008-05-30..2009-06-30 | -49.37% | -9.11% | -9.11% | +0.00pp | +0.00pp |
| 2020 COVID | 2020-01-01..2020-06-30 | -28.56% | -20.46% | -20.46% | +0.00pp | -38.65pp |
| 2018-Q4 grind | 2018-09-01..2018-12-31 | -22.70% | -3.07% | -3.07% | +0.00pp | +0.00pp |
| 2022 grind | 2022-01-01..2022-12-31 | -34.83% | -26.25% | -0.30% | +25.95pp | +14.55pp |

*dMaxDD>0 => gate drawdown SHALLOWER than baseline (gate helped). ~0 => canary+trend already caught it; gate inert. dRet<0 with dMaxDD~0 => whipsaw cost.*

## (D) DECISIVE -- paired block-bootstrap CI on the marginal

**Method.** PAIRED stationary block bootstrap B=5000 block=21d seed=42 clean. Same blocks both streams; delta=metric(gate)-metric(base).

| Marginal (gate minus baseline) | p2.5 | p50 | p97.5 | mean | P(delta>0) | CI excludes 0? |
|---|---:|---:|---:|---:|---:|:--:|
| **Calmar** | -0.3285 | +0.0468 | +0.6153 | +0.0713 | 60.1% | NO (includes 0) |
| **Martin** | -1.1396 | +0.4676 | +2.8710 | +0.5731 | 72.6% | NO (includes 0) |
| **Sharpe** | -0.1929 | +0.0588 | +0.3181 | +0.0599 | 67.9% | NO (includes 0) |

**KEY -- does the marginal-Calmar CI exclude 0?** **NO -- the 95% CI INCLUDES 0; the gate edge is within noise.** (Calmar delta 95% CI [-0.3285, +0.6153], P(delta>0)=60.1%, median +0.0468.)

## (B) De-risk attribution -- every vol-gate activation classified

**Definition.** de-risk = canary_ok AND trend_ok AND NOT vol_ok (vol sole binding; NDX forced to safe). class by governed next-month QQQ return (Nasdaq proxy): >0 whipsaw; <=-4% crash-save; (-4%,0] grind-save.

- Total de-risk activations: **33** | Crash-saves **5** | Grind-saves **9** | Whipsaws **18** | unknown **1**
- Saves vs whipsaws: **14 saves / 18 whipsaws** (whipsaw rate **54.5%**)
- bp SAVED by TP (QQQ loss avoided): **+50.54%** | bp GIVEN UP by FP (QQQ upside forgone): **+82.80%** | NET **-32.26%**

| Applied month | QQQ fwd1 | QQQ fwd2 | QQQ fwd3 | Class |
|---|---:|---:|---:|---|
| 2010-06-30 | -5.98% | 0.85% | -4.32% | crash-save |
| 2010-08-31 | -5.13% | 7.37% | 14.17% | crash-save |
| 2011-08-31 | -5.07% | -9.33% | 0.1% | crash-save |
| 2011-11-30 | -2.69% | -3.29% | 4.85% | grind-save |
| 2011-12-31 | -0.61% | 7.75% | 14.66% | grind-save |
| 2012-01-31 | 8.42% | 15.37% | 21.2% | whipsaw |
| 2014-11-30 | 4.55% | 2.2% | 0.08% | whipsaw |
| 2014-12-31 | -2.24% | -4.28% | 2.64% | grind-save |
| 2015-01-31 | -2.08% | 4.99% | 2.51% | grind-save |
| 2015-02-28 | 7.22% | 4.69% | 6.7% | whipsaw |
| 2015-03-31 | -2.36% | -0.48% | 1.76% | grind-save |
| 2015-04-30 | 1.92% | 4.21% | 1.63% | whipsaw |
| 2016-04-30 | -3.19% | 1.04% | -1.26% | grind-save |
| 2018-02-28 | -1.29% | -5.32% | -4.84% | grind-save |
| 2018-04-30 | 0.51% | 6.21% | 7.42% | whipsaw |
| 2018-06-30 | 1.15% | 3.97% | 9.98% | whipsaw |
| 2019-02-28 | 2.99% | 7.03% | 12.92% | whipsaw |
| 2019-03-31 | 3.92% | 9.64% | 0.62% | whipsaw |
| 2020-05-31 | 6.6% | 13.3% | 21.63% | whipsaw |
| 2020-06-30 | 6.29% | 14.1% | 26.58% | whipsaw |
| 2021-12-31 | 1.15% | -7.7% | -11.83% | whipsaw |
| 2022-01-31 | -8.75% | -12.83% | -8.76% | crash-save |
| 2022-03-31 | 4.67% | -9.56% | -11.0% | whipsaw |
| 2024-09-30 | 2.62% | 1.73% | 7.18% | whipsaw |
| 2024-10-31 | -0.86% | 4.44% | 4.91% | grind-save |
| 2024-11-30 | 5.35% | 5.83% | 8.12% | whipsaw |
| 2025-02-28 | -2.7% | -10.08% | -8.83% | grind-save |
| 2025-03-31 | -7.59% | -6.3% | 2.31% | crash-save |
| 2025-05-31 | 9.18% | 16.15% | 18.97% | whipsaw |
| 2025-06-30 | 6.39% | 8.96% | 10.0% | whipsaw |
| 2025-07-31 | 2.42% | 3.4% | 8.96% | whipsaw |
| 2026-05-31 | 7.46% | n/a | n/a | whipsaw |
| 2026-06-30 | n/a | n/a | n/a | unknown |

## VERDICT

- Gate materially reduced per-crisis DD (>+1pp shallower) in: **['2022 grind']**
- Gate ~inert per-crisis (canary+trend already caught it): **['2008 GFC', '2020 COVID', '2018-Q4 grind']**
- Gate made DD WORSE (whipsaw, >1pp deeper) in: **none**
- Attribution: **14 saves / 18 whipsaws** (55% whipsaw), net **-32.3%** gross QQQ.

### Does the NDX vol gate earn its keep?

**NO -- within noise, same as BULL.** The marginal-Calmar CI INCLUDES 0, so the NDX gate's risk-adjusted edge is NOT statistically distinguishable from noise across reshuffled history. Despite NDX being higher-beta (where the gate could matter more), the drop-vol-gate result mirrors the BULL finding: the point estimate may look positive but rests on too few episodes to be reliable. Crash protection comes mostly from canary+trend; the vol gate adds whipsaw.

### Direct comparison to BULL

| | BULL (prior) | NDX (this) |
|---|---|---|
| Marginal Calmar (point) | +0.25 | -0.0030 |
| Marginal-Calmar CI | [-0.30, +0.60] (incl 0) | [-0.3285, +0.6153] (incl 0) |
| Whipsaw rate | 59% | 55% |
| CAGR cost/yr | -0.67pp | -2.40pp |
| Crisis win | only 2022 | ['2022 grind'] |

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit.
- NDX engine: T+1 MOO offset=1 close-to-close (exact-open engine unsupported for the per-stock PIT universe + delisting haircut), 10 bps/side, monthly month-end signal. Baseline and gate share the SAME stock selection, safe pool, and engine -- the vol gate (RV60<RV252) is the SINGLE differentiator (apples-to-apples).
- ANCHOR drift: NDX constituent prices were refreshed 2026-05-29 (yfinance auto_adjust re-adjusts full history), so reproduced anchor CAGR/Sharpe drift ~1pp/0.02 vs the frozen memo; MaxDD reproduces exactly (-35.92%). The marginal (gate vs no-gate) uses the SAME refreshed data on both arms, so the DELTA is unaffected by the drift.
- Attribution forward returns use calendar-month QQQ close-to-close as a Nasdaq proxy for what the NDX stock basket gave up while forced to safe (the sleeve's actual held names vary month to month; QQQ is a coarse but unbiased beta proxy). The save/whipsaw SPLIT is the robust signal.
- Per-crisis MaxDD from each window start (intra-window peak); understates DD if the episode peak preceded the window. 2018-Q4 = 2018-09-01..12-31.
- Survivorship bias on NDX selection pre-2017 (~28% delisted tickers missing from PIT prices); post-2020 PIT coverage clean. This affects BOTH arms equally (same selection).
- Single 18y in-sample. NDX PIT data starts 2006-01, so ext window NDX leg is near-cash pre-data; clean 18y is the decisive lens. No adoption without explicit user confirmation.
