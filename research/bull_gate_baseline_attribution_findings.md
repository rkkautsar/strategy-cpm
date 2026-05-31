# BULL vol gate: baseline marginal contribution + de-risk attribution + trend-conditional gating

Role: analyst (hypothesis-driven; read-only re production; writes only to research/; no production/memo edits; no commit). EXPLORATION ONLY. Harness `research/bull_gate_baseline_attribution.py` (reuses bull_tiponly_recompute + exec_lag_moo_validation canonical engine verbatim).

**Question.** User uneasy that V0's vol gate behaves INCONSISTENTLY (whipsaws / catches sharp crash / catches slow grind, not reliably). Does the gate earn its keep over a canary+trend-only baseline, and is a trend-conditional variant worth a walk-forward?

## BOTTOM LINE (decisive)

- **No-gate baseline = HAA-Simple (canary+trend only): Calmar 0.5685 / MaxDD -20.41% / Sharpe 0.984 / CAGR 11.60%** (reconciles exactly to bull_volgate_episode_decomp_findings.md). V0 (with gate): 0.8189 / -13.35% / 1.1005 / 10.93%.
- **Gate POINT-ESTIMATE marginal looks strong (Calmar +0.25, Martin +0.69, MaxDD -7.06pp, CAGR -0.67pp) -- but the PAIRED BLOCK-BOOTSTRAP CI on that marginal INCLUDES 0 for Calmar [-0.30,+0.60], Martin [-1.15,+2.54] AND Sharpe [-0.20,+0.45].** The gate's edge is within noise; it rests on ~2 non-repeatable episodes (the median resample benefit is only Calmar +0.08).
- **Attribution: 12 saves / 19 whipsaws (59% false-positive); the gate's ONLY material per-crisis DD win is 2022 (+9.8pp). 2008/2020/2018-Q4 are caught FREE by canary+trend.** The gate is NOT crash insurance; it is a single-episode (2022) DD saver + chronic vol-dampener.
- **Trend-conditional gating: FAILS the oracle gate (marginal CI includes 0) AND its own bar (does not beat V0 on Calmar+Martin in clean or ext) AND it destroys the 2022 catch (2022-01 de-risk fired at strong trend spym=0.14). Do NOT adopt.**
- **Honest verdict: KEEP V0 as cheap insurance (adds no net flips, ~0.67pp/yr CAGR cost); do NOT adopt trend-conditional. The gate does not statistically 'earn its keep' on risk-adjusted metrics -- but it is cheap and harmless, so retaining it as lottery-ticket 2022-style insurance is defensible.**

**Convention.** T+1 MOO exact (`mooex`, real auto_adjust opens), 10 bps/side, monthly month-end signal. BULL canary TIP-only (`['TIP']`), safe best{SHV,IEF}. Baseline / V0 / trend-conditional share canary+trend+safe so the vol gate (and its conditioning) is the SINGLE differentiator. Windows: clean 2008-05-30..2026-05-22 (18y); ext 1999-03-10..2026-05-22 (27y).

## 0. Anchor gate

V0 (canary+trend+vol) clean: Sharpe **1.1005** / MaxDD **-13.35%** / Calmar **0.8189** / Martin **3.0714** vs anchor 1.1005 / -13.35% / 0.8189 / 3.0714 -> **CONFIRMED** (dS=0.0000, dDD=0.004pp, dCal=0.0000, dMar=0.0000).

## (A) Baseline = canary+trend ONLY (vol gate REMOVED) + V0 marginal contribution

| Series | Window | CAGR | Vol | Sharpe | MaxDD | Calmar | Martin |
|---|---|---:|---:|---:|---:|---:|---:|
| Baseline (canary+trend) | Clean 18y | 11.60% | 11.92% | 0.9840 | -20.41% | 0.5685 | 2.3815 |
| Baseline (canary+trend) | Ext 27y | 10.73% | 11.11% | 0.9735 | -20.41% | 0.5259 | 2.4751 |
| V0 (+vol gate) | Clean 18y | 10.93% | 9.90% | 1.1005 | -13.35% | 0.8189 | 3.0714 |
| V0 (+vol gate) | Ext 27y | 9.48% | 9.30% | 1.0207 | -13.35% | 0.7101 | 2.5820 |

**V0 marginal contribution = V0 minus baseline:**
- Clean: dSharpe **+0.1165**, dCalmar **+0.2504**, dMartin **+0.6899**, dMaxDD **-7.06pp** (negative=shallower), dCAGR **-0.67pp**, dVol **-2.01pp**.
- Ext: dSharpe **+0.0471**, dCalmar **+0.1842**, dMartin **+0.1069**, dMaxDD **-7.06pp**, dCAGR **-1.26pp**.
- Flips (allocation state changes, clean): baseline **35**, V0 **34** (gate ADDED **-1** flips).

### Per-crisis MaxDD: baseline vs V0 (where does the gate actually change the outcome?)

| Crisis | Window | SPY DD | Baseline DD | V0 DD | Gate dMaxDD | Gate dRet |
|---|---|---:|---:|---:|---:|---:|
| 2008 GFC | 2008-05-30..2009-06-30 | -50.70% | -12.09% | -12.09% | +0.00pp | +0.00pp |
| 2020 COVID | 2020-01-01..2020-06-30 | -33.72% | -13.35% | -13.35% | +0.00pp | -7.84pp |
| 2018-Q4 grind | 2018-09-01..2018-12-31 | -19.35% | -0.81% | -0.81% | +0.00pp | +0.00pp |
| 2022 grind | 2022-01-01..2022-12-31 | -24.50% | -10.11% | -0.30% | +9.81pp | +1.26pp |

*Gate dMaxDD>0 => V0 drawdown SHALLOWER than baseline (gate helped). ~0 => baseline (canary+trend) already caught it; gate inert. dRet<0 with dMaxDD~0 => whipsaw.*

## (D) DECISIVE -- paired block-bootstrap CI on the gate's MARGINAL contribution

**Method.** PAIRED stationary block bootstrap, B=5000, block=21d, seed=42, clean 18y. SAME random time blocks drawn from BOTH daily streams; delta = metric(V0_resample) - metric(baseline_resample). CI of the deltas.

**Baseline reconciliation vs existing HAA-Simple** (bull_volgate_episode_decomp_findings.md): this run baseline clean Calmar 0.5685 / MaxDD -20.41% / Sharpe 0.9840 / CAGR 11.60% vs HAA-Simple 0.5685 / -20.41% / 0.984 / 11.60% -> MATCH (same no-gate series).

| Marginal (V0 minus baseline) | p2.5 | p50 | p97.5 | mean | P(delta>0) | CI excludes 0? |
|---|---:|---:|---:|---:|---:|:--:|
| **Calmar** | -0.2961 | +0.0805 | +0.5961 | +0.1026 | 66.2% | NO (includes 0) |
| **Martin** | -1.1492 | +0.3871 | +2.5426 | +0.4605 | 68.9% | NO (includes 0) |
| **Sharpe** | -0.1950 | +0.1148 | +0.4530 | +0.1170 | 75.6% | NO (includes 0) |

**KEY QUESTION -- does the marginal-Calmar CI exclude 0?** **NO -- the 95% CI INCLUDES 0; the gate benefit is within noise.** (Calmar delta 95% CI [-0.2961, +0.5961], P(delta>0)=66.2%.) Martin CI [-1.1492, +2.5426] excludes 0: False; Sharpe CI [-0.1950, +0.4530] excludes 0: False.

*Block bootstrap preserves autocorrelation but RESAMPLES episodes -- it tests whether the gate's edge is reliable across reshuffled history or rests on a few non-repeatable episodes. The DD-based metrics (Calmar/Martin) lean on the 2018/2022 grind catches (N~=2), so wide CIs are expected.*

## (B) De-risk attribution -- every vol-gate activation classified

**Definition.** de-risk activation = canary_ok AND trend_ok AND NOT vol_ok (vol gate the sole binding leg). class by governed next-month SPY return (fwd1): >0 whipsaw; <=-4% crash-save; (-4%,0] grind-save.

- Total de-risk activations: **32**
- Crash-saves: **5** | Grind-saves: **7** | Whipsaws (false-positive): **19** | unknown: **1**
- Saves vs whipsaws: **12 saves / 19 whipsaws** (whipsaw rate **59.4%**)
- bp SAVED by true positives (loss avoided, sum of -SPY fwd1): **+45.00%**
- bp GIVEN UP by false positives (upside forgone, sum of SPY fwd1): **+60.64%**
- NET (saved minus given up, gross of safe-asset carry): **-15.64%**

### All de-risk months (governed next-month SPY = fwd1; fwd2/fwd3 = 2/3-month compounded)

| Applied month | SPY 13612U | SPY fwd1 | SPY fwd2 | SPY fwd3 | Class |
|---|---:|---:|---:|---:|---|
| 2010-06-30 | 0.1677 | -5.17% | 1.3% | -3.25% | crash-save |
| 2011-08-31 | 0.0867 | -5.5% | -12.06% | -2.46% | crash-save |
| 2011-11-30 | 0.0235 | -0.41% | 0.63% | 5.3% | grind-save |
| 2011-12-31 | 0.0089 | 1.04% | 5.73% | 10.32% | whipsaw |
| 2012-01-31 | 0.0089 | 4.64% | 9.18% | 12.69% | whipsaw |
| 2014-11-30 | 0.0808 | 2.75% | 2.49% | -0.55% | whipsaw |
| 2014-12-31 | 0.0808 | -0.25% | -3.21% | 2.23% | grind-save |
| 2015-01-31 | 0.0605 | -2.96% | 2.49% | 0.88% | grind-save |
| 2015-02-28 | 0.0605 | 5.62% | 3.96% | 4.98% | whipsaw |
| 2015-03-31 | 0.0374 | -1.57% | -0.6% | 0.68% | grind-save |
| 2015-04-30 | 0.0442 | 0.98% | 2.28% | 0.2% | whipsaw |
| 2016-04-30 | 0.0455 | 0.39% | 2.1% | 2.46% | whipsaw |
| 2018-02-28 | 0.1438 | -3.64% | -6.28% | -5.79% | grind-save |
| 2018-06-30 | 0.0503 | 0.58% | 4.3% | 7.63% | whipsaw |
| 2019-02-28 | 0.0071 | 3.24% | 5.11% | 9.4% | whipsaw |
| 2019-03-31 | 0.0161 | 1.81% | 5.97% | -0.79% | whipsaw |
| 2020-03-31 | 0.093 | -12.49% | -1.37% | 3.32% | crash-save |
| 2020-05-31 | 0.0028 | 4.76% | 6.62% | 12.9% | whipsaw |
| 2020-06-30 | 0.0028 | 1.77% | 7.77% | 15.29% | whipsaw |
| 2021-12-31 | 0.0929 | 4.62% | -0.89% | -3.82% | whipsaw |
| 2022-01-31 | 0.1403 | -5.27% | -8.07% | -4.61% | crash-save |
| 2022-03-31 | 0.0172 | 3.76% | -5.35% | -5.13% | whipsaw |
| 2024-09-30 | 0.1202 | 2.1% | 1.19% | 7.22% | whipsaw |
| 2024-10-31 | 0.1357 | -0.89% | 5.02% | 2.49% | grind-save |
| 2024-11-30 | 0.1362 | 5.96% | 3.41% | 6.19% | whipsaw |
| 2025-02-28 | 0.1127 | -1.27% | -6.77% | -7.58% | grind-save |
| 2025-03-31 | 0.0555 | -5.57% | -6.39% | -0.51% | crash-save |
| 2025-05-31 | 0.0039 | 6.28% | 11.75% | 14.32% | whipsaw |
| 2025-06-30 | 0.0039 | 5.14% | 7.56% | 9.77% | whipsaw |
| 2025-07-31 | 0.0923 | 2.3% | 4.4% | 8.12% | whipsaw |
| 2026-05-31 | 0.1292 | 2.87% | n/a | n/a | whipsaw |
| 2026-06-30 | 0.1292 | n/a | n/a | n/a | unknown |

## (C) Trend-conditional gating (one added parameter -> overfit risk)

**Rule.** apply vol de-risk ONLY when SPY 13612U <= tau (weak/neutral trend); skip vol gate when spym > tau (strong trend). trend_ok (spym>0) still required for any risk-on. So vol gate active only in band 0 < spym <= tau.

| Variant | Clean Calmar | Clean Martin | Clean MaxDD | Clean Sharpe | Clean CAGR | 2022 | Ext Calmar | Ext Martin | Flips | de-risk (whip/save) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **V0 (always-on)** | 0.8189 | 3.0714 | -13.35% | 1.1005 | 10.93% | 0.94% | 0.7101 | 2.5820 | 34 | 32 (19/13) |
| tau=0.02 | 0.5003 | 1.9851 | -20.41% | 0.9001 | 10.21% | -4.35% | 0.4616 | 2.0392 | 35 | 9 (9/0) |
| tau=0.05 | 0.7780 | 2.2150 | -13.35% | 0.9927 | 10.38% | -4.35% | 0.6767 | 2.0369 | 35 | 13 (11/2) |
| tau=0.1 | 0.8331 | 2.7797 | -13.35% | 1.0832 | 11.12% | -4.81% | 0.7194 | 2.4249 | 35 | 23 (16/7) |

### Per-crisis MaxDD: V0 vs trend-conditional (keep the catches?)

| Crisis | V0 DD | tau=0.02 DD | tau=0.05 DD | tau=0.1 DD |
|---|---:|---:|---:|---:|
| 2008 GFC | -12.09% | -12.09% | -12.09% | -12.09% |
| 2020 COVID | -13.35% | -13.35% | -13.35% | -13.35% |
| 2018-Q4 grind | -0.81% | -0.81% | -0.81% | -0.81% |
| 2022 grind | -0.30% | -9.73% | -9.73% | -9.73% |

## VERDICT

### Does the gate earn its keep over canary+trend-only?

Baseline (canary+trend) clean Calmar **0.5685** / Martin **2.3815** / MaxDD **-20.41%**; V0 **0.8189** / **3.0714** / **-13.35%**. Gate marginal: Calmar +0.2504, Martin +0.6899, MaxDD -7.06pp, CAGR -0.67pp.

- Gate materially reduced per-crisis DD (>+1pp shallower) in: **['2022 grind']**
- Gate ~inert per-crisis (canary+trend already caught it): **['2008 GFC', '2020 COVID', '2018-Q4 grind']**
- De-risk attribution: **12 saves / 19 whipsaws** (59% whipsaw), net **-15.64%** gross upside over 18y.

**Reconciliation (data-grounded answer to "is V0 inconsistent?").** YES, quantified. (1) On AGGREGATE risk-adjusted metrics the gate earns its keep (point estimates): Calmar 0.5685->0.8189 (+0.2504), Martin 2.3815->3.0714 (+0.6899), MaxDD -20.41%->-13.35% (-7.06pp), Vol -2.01pp, at CAGR cost -0.67pp/yr. **BUT see section (D): the bootstrap CI tells us whether these point estimates survive noise.** (2) The DD win is LUMPY: across all four crises the gate's ONLY material per-crisis DD contribution is **2022** (+9.81pp); 2008 GFC, 2020 COVID and 2018-Q4 are caught FREE by canary+trend (gate inert). The full-sample -7pp MaxDD improvement is essentially the single 2022 grind catch (deepest baseline drawdown) plus general vol-dampening from sitting in cash during chop. (3) Cost: **59% whipsaw rate** (19 of 32 de-risk activations false), giving up 60.6% gross upside vs 45.0% losses avoided -> net -15.6% gross. **The gate is NOT crash insurance (canary+trend is); it is a single-episode (2022) drawdown saver bundled with a chronic high-false-positive vol-dampener. The 'inconsistency' is real: 19/32 activations are noise.**

*Flip nuance: gate did NOT add net allocation flips (baseline 35 -> V0 34, net -1). The 19 whipsaws are de-risk months whose governed month rose, not extra round-trips; the gate reshuffles WHICH months are risk-off rather than churning more.*

### Is trend-conditional worth a walk-forward? (gated on the bootstrap CI)

**Oracle gate: trend-conditional is only worth pursuing IF the marginal-Calmar CI EXCLUDES 0.** Here marginal-Calmar CI = [-0.2961, +0.5961] -> **INCLUDES 0**.

Best trend-conditional by clean Calmar = **tau=0.1**: clean Calmar 0.8331 / Martin 2.7797 (V0 0.8189 / 3.0714); ext Calmar 0.7194 / Martin 2.4249 (V0 0.7101 / 2.5820). Whipsaws 16 vs V0 19. Beats V0 on Calmar+Martin clean: **False**; ext: **False**.

*Mechanism: trend-conditional with tau<0.14 SKIPS the vol gate in strong-trend months, but the single most valuable de-risk -- 2022-01-31 (spym=0.1403, crash-save, SPY fwd1 -5.27%) -- happened in a STRONG-trend month. So 'skip de-risk into strength' discards the one episode that gives the gate its only material DD win: every tau in {0.02,0.05,0.1} re-opens 2022 DD to ~-9.7% (vs V0 -0.30%). To keep 2022 you need tau>0.14, i.e. effectively always-on V0.*

**Verdict: marginal-Calmar CI INCLUDES 0 -> the gate's benefit is within noise, so the oracle gate FAILS at step 1. Do NOT pursue trend-conditional (it also fails its own bar: does not beat V0 on Calmar+Martin and sacrifices the 2022 catch). Honest conclusion: KEEP V0 as cheap insurance (adds no net flips, costs ~0.67pp/yr CAGR), do NOT adopt trend-conditional.**

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit. V0 anchor reproduced exactly (Sharpe 1.1005 / MaxDD -13.35% / Calmar 0.8189 / Martin 3.0714) before trusting deltas.
- Baseline / V0 / trend-conditional share canary (TIP-only) + trend (SPY 13612U>0) + safe (SHV/IEF) at production values; the vol gate (and its trend-conditioning) is the SINGLE differentiator (apples-to-apples).
- Sleeves: T+1 MOO exact (mooex, real opens), 10 bps/side via canonical exec_lag_moo_validation._segment_returns_conv + run_bull_cell.
- Per-crisis MaxDD computed from each window start (intra-window peak); understates DD if the episode peak preceded the window. 2018-Q4 = 2018-09-01..12-31.
- Attribution forward returns use calendar-month SPY close-to-close (governed next month = fwd1); the daily sleeve backtest uses mooex. Monthly attribution is a coarser counting lens.
- Classification thresholds (whipsaw fwd1>0; crash-save fwd1<=-4%; grind-save in (-4%,0]) are judgment cuts; the save/whipsaw SPLIT is the robust signal, not the crash/grind boundary.
- (C) adds ONE parameter (tau) -> overfit risk. Single 18y in-sample; ANY tcond winner needs walk-forward before adoption. ext window 1999-03-10 is TIP-data-limited (TIP real from 2000-06; canary cash-default pre-~2001-07) -- the requested 'ext-1995' maps here.
- No adoption without explicit user confirmation.
