# BULL vol-gate HYSTERESIS: dead-zone band + confirmation-count vs symmetric V0

Role: analyst (hypothesis-driven; READ-ONLY re production; writes only to research/; NO production/memo edits; NO commit). EXPLORATION ONLY -- a POTENTIAL production BULL vol-gate tweak; OOS-gated before adoption. Harness `research/bull_volgate_hysteresis.py` (reuses `bull_volgate_variants` sleeve machinery verbatim; swaps ONLY the vol-gate decision rule).

**Question.** Does HYSTERESIS on the EXISTING rv60/rv252 vol gate cut whipsaw WITHOUT losing crash (2008/2020) / grind (2018-Q4/2022) protection? PRIMARY metric = Calmar + Martin (BULL is a drawdown-control overlay). Windows HELD at 60/252; ONLY the decision rule on the rv60/rv252 ratio changes.

**Forms tested (unified generator `hysteresis_state(ratio, b, k)`):**
- **BAND / dead-zone (b)**: de-risk (OFF) when ratio > 1+b; re-risk (ON) when ratio < 1-b; HOLD prior state inside [1-b, 1+b]. b in {0.02, 0.05, 0.10}. (b=0 -> V0.)
- **CONFIRMATION-COUNT (k)**: flip only after the desired state persists k consecutive months. k in {2, 3}. (k=1 -> V0.)
- **COMBO**: band b=0.02 with k=2.

**Prior-round context (cited, NOT repeated).** `vol_gate_timing_hysteresis_findings.md` + `bull_volgate_variants*` already tested slower windows (sw_90/sw_120), symmetric 2-month confirmation (hyst_sym2 == conf_k2 here), asymmetric confirmation (hyst_asym), and single-threshold SHIFTS (k_105/k_110). Verdict there: every slower/confirmation variant DEGRADED modern clean Sharpe (1.0813 -> 0.89-1.03) and worsened clean MaxDD -13.35% -> ~-17.31% by LAGGING the Aug-2011 debt-downgrade vol-spike exit; k_110 LOST the 2022 catch (-0.30% -> -9.73%); k_105 was a near-no-op. The GAP tested here: a TRUE dead-zone BAND (hold-in-band; k_105/k_110 only shifted the single ON threshold, they are NOT bands), confirmation k=3, and a band/confirmation combo, all led on Calmar/Martin.

**Convention.** T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side, monthly month-end signal. Clean 2008-05-30..2026-05-22 (18y, full real-open coverage, decisive lens); ext 1999-03-10..2026-05-22 (27y, partly proxy-backed pre-2006-08). Canary (TIP 13612U>0) + trend (SPY 13612U>0) + safe (best{SHV,IEF}) HELD at production; vol gate is the single differentiator.

## 0. Anchor gate

BULL V0 (b=0,k=1) clean Sharpe **1.1005** / Calmar **0.8189** / Martin **3.0714** / MaxDD **-13.35%** vs anchor 1.1005 / 0.8189 / 3.0714 / -13.35% -> **CONFIRMED**.

## 1. PRIMARY -- Calmar / Martin (+ Sharpe / MaxDD / CAGR), BULL clean 18y

| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR | Vol |
|---|---:|---:|---:|---:|---:|---:|
| V0 sym rv60<rv252 (PROD) | 0.8189 | 3.0714 | 1.1005 | -13.35% | 10.93% | 9.90% |
| band b=0.02 (k=1) | 0.8189 | 3.0714 | 1.1005 | -13.35% | 10.93% | 9.90% |
| band b=0.05 (k=1) | 0.8203 | 3.0439 | 1.0844 | -13.35% | 10.95% | 10.08% |
| band b=0.10 (k=1) | 0.5255 | 2.1105 | 0.8825 | -17.31% | 9.10% | 10.53% |
| confirm k=2 (b=0) | 0.4953 | 1.7792 | 0.8331 | -17.31% | 8.57% | 10.58% |
| confirm k=3 (b=0) | 0.4165 | 1.4396 | 0.7934 | -19.36% | 8.06% | 10.51% |
| combo b=0.02,k=2 | 0.4953 | 1.7792 | 0.8331 | -17.31% | 8.57% | 10.58% |

### Delta vs V0 (clean)

| Variant | dCalmar | dMartin | dSharpe | dMaxDD (pp) | dCAGR (pp) |
|---|---:|---:|---:|---:|---:|
| V0 sym rv60<rv252 (PROD) | +0.0000 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| band b=0.02 (k=1) | +0.0000 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| band b=0.05 (k=1) | +0.0014 | -0.0275 | -0.0162 | -0.00 | +0.02 |
| band b=0.10 (k=1) | -0.2933 | -0.9609 | -0.2180 | +3.96 | -1.83 |
| confirm k=2 (b=0) | -0.3236 | -1.2922 | -0.2674 | +3.96 | -2.36 |
| confirm k=3 (b=0) | -0.4024 | -1.6318 | -0.3072 | +6.02 | -2.86 |
| combo b=0.02,k=2 | -0.3236 | -1.2922 | -0.2674 | +3.96 | -2.36 |

*dCalmar/dMartin/dSharpe > 0 = better. dMaxDD > 0 = deeper (worse). dCAGR > 0 = more return.*

### Ext 27y (partly proxy-backed)

| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR |
|---|---:|---:|---:|---:|---:|
| V0 sym rv60<rv252 (PROD) | 0.7101 | 2.5820 | 1.0207 | -13.35% | 9.48% |
| band b=0.02 (k=1) | 0.7043 | 2.5203 | 1.0145 | -13.35% | 9.40% |
| band b=0.05 (k=1) | 0.6957 | 2.5286 | 0.9920 | -13.35% | 9.29% |
| band b=0.10 (k=1) | 0.4906 | 2.0768 | 0.8864 | -17.31% | 8.49% |
| confirm k=2 (b=0) | 0.4825 | 1.9549 | 0.8696 | -17.31% | 8.35% |
| confirm k=3 (b=0) | 0.4200 | 1.6721 | 0.8511 | -19.36% | 8.13% |
| combo b=0.02,k=2 | 0.4811 | 1.9494 | 0.8685 | -17.31% | 8.33% |

## 2. Whipsaw reduction (clean 18y monthly signals)

Vol-gate de-risk = canary_ok AND trend_ok AND NOT vol_ok (vol the SOLE binding leg). False de-risk = governed next-month SPY return > 0. Flip count = vol-gate state changes over the clean window (hysteresis should REDUCE this).

| Variant | flips | de-risk mo | false-pos | false-pos rate | mean SPY next | turnover/yr |
|---|---:|---:|---:|---:|---:|---:|
| V0 sym rv60<rv252 (PROD) | 34 | 32 | 19 | 59.4% | +0.50% | 378.3% |
| band b=0.02 (k=1) | 30 | 32 | 19 | 59.4% | +0.50% | 378.3% |
| band b=0.05 (k=1) | 28 | 31 | 18 | 58.1% | +0.41% | 356.0% |
| band b=0.10 (k=1) | 24 | 34 | 22 | 64.7% | +1.08% | 333.8% |
| confirm k=2 (b=0) | 26 | 33 | 23 | 69.7% | +1.71% | 378.3% |
| confirm k=3 (b=0) | 21 | 37 | 29 | 78.4% | +1.89% | 322.6% |
| combo b=0.02,k=2 | 26 | 34 | 23 | 67.6% | +1.59% | 356.0% |

## 3. Crash + grind protection (BULL sleeve MaxDD / total return in window)

Must KEEP: 2008 GFC + 2020 COVID crashes; 2018-Q4 + 2022 grinds (V0: 2018-Q4 -2.14%, 2022 -0.30%). Dead-zone/confirmation may LAG these -- checked explicitly.

| Variant | 2008 GFC DD/Ret | 2018 Q4 DD/Ret | 2020 COVID DD/Ret | 2022 bear DD/Ret |
|---|---|---|---|---|
| V0 sym rv60<rv252 (PROD) | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| band b=0.02 (k=1) | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| band b=0.05 (k=1) | -12.09% / 6.57% | -10.10% / 11.30% | -13.35% / -3.82% | -0.30% / 1.03% |
| band b=0.10 (k=1) | -12.09% / 6.57% | -10.10% / 6.67% | -13.35% / -3.82% | -9.73% / -4.35% |
| confirm k=2 (b=0) | -12.09% / 6.57% | -10.10% / 6.67% | -13.35% / -3.82% | -0.30% / 1.03% |
| confirm k=3 (b=0) | -12.09% / 6.57% | -10.10% / 3.81% | -13.35% / -3.82% | -9.73% / -4.35% |
| combo b=0.02,k=2 | -12.09% / 6.57% | -10.10% / 6.67% | -13.35% / -3.82% | -0.30% / 1.03% |

*Windows: 2008 GFC 2008-05-30..2009-06-30; 2018 Q4 2018-01-01..2018-12-31; 2020 COVID 2020-01-01..2020-06-30; 2022 bear 2022-01-01..2022-12-31.*

## 4. Live current state (latest signal month)

| Variant | signal date | canary | trend | vol_ok | risk-on | rv60 | rv252 |
|---|---|:--:|:--:|:--:|:--:|---:|---:|
| V0 sym rv60<rv252 (PROD) | 2026-05-22 | Y | Y | n | OFF | 14.59% | 12.43% |
| band b=0.02 (k=1) | 2026-05-22 | Y | Y | n | OFF | 14.59% | 12.43% |
| band b=0.05 (k=1) | 2026-05-22 | Y | Y | n | OFF | 14.59% | 12.43% |
| band b=0.10 (k=1) | 2026-05-22 | Y | Y | n | OFF | 14.59% | 12.43% |
| confirm k=2 (b=0) | 2026-05-22 | Y | Y | n | OFF | 14.59% | 12.43% |
| confirm k=3 (b=0) | 2026-05-22 | Y | Y | Y | ON | 14.59% | 12.43% |
| combo b=0.02,k=2 | 2026-05-22 | Y | Y | n | OFF | 14.59% | 12.43% |

## 5. VERDICT

Scorecard (clean 18y; V0 flips = 34, Calmar 0.8189, Martin 3.0714). keeps crash = 2008 & 2020 DD not >2pp deeper than V0; keeps grind = 2018-Q4 & 2022 DD not >3pp deeper than V0; beats primary = BOTH Calmar AND Martin above V0.

| Variant | Calmar | Martin | Sharpe | MaxDD | flips | keeps crash? | keeps grind? | beats Calmar+Martin? |
|---|---:|---:|---:|---:|---:|:--:|:--:|:--:|
| band b=0.02 (k=1) | 0.8189 | 3.0714 | 1.1005 | -13.35% | 30 | Y | Y | NO |
| band b=0.05 (k=1) | 0.8203 | 3.0439 | 1.0844 | -13.35% | 28 | Y | NO | NO |
| band b=0.10 (k=1) | 0.5255 | 2.1105 | 0.8825 | -17.31% | 24 | Y | NO | NO |
| confirm k=2 (b=0) | 0.4953 | 1.7792 | 0.8331 | -17.31% | 26 | Y | NO | NO |
| confirm k=3 (b=0) | 0.4165 | 1.4396 | 0.7934 | -19.36% | 21 | Y | NO | NO |
| combo b=0.02,k=2 | 0.4953 | 1.7792 | 0.8331 | -17.31% | 26 | Y | NO | NO |

**No band/confirmation setting beats V0 on BOTH Calmar AND Martin while keeping crash and grind protection.** The whipsaw-reduction (fewer flips) is real but does NOT outweigh the crash/grind LAG introduced by the dead-zone / confirmation offset -- the same structural failure the prior slower/confirmation round found. **Keep production symmetric rv60<rv252.**

## 6. Whipsaw-reduction vs crash-lag tradeoff

The hysteresis forms DO cut flips/turnover (Section 2), confirming the whipsaw mechanism works. The question is whether that pays. Each de-risk/re-risk delay (band hold-in-zone, or k-month confirmation) postpones the OFF transition into a vol spike -- which is exactly where the gate earns its keep (fast crashes 2008/2020 + the Aug-2011 spike that bound the prior round's MaxDD). It ALSO postpones the re-risk ON, giving up rebound. See Sections 1 (Calmar/Martin/MaxDD deltas) + 3 (per-crisis DD) for the realized net.

## 7. Caveats / OVERFITTING / OOS

- EXPLORATION ONLY; READ-ONLY re production; NO production/memo edits; NO commit.
- Small, principled, NON-grid-tuned param set (b in {0.02,0.05,0.10}, k in {2,3}, one combo). ANY rule mined on the same 18y sample risks in-sample selection. A live production change REQUIRES OOS / walk-forward (e.g. freeze pre-2015, test 2015+) + paired bootstrap on the Calmar/Martin/Sharpe deltas before adoption.
- Modern Sharpe deltas sit inside the memo's bootstrap Sharpe 95% CI; read directional, not individually significant point estimates.
- Only the vol-gate decision rule changes; canary/trend/safe held at production. Hysteresis state depends ONLY on past/current month rv signals (no lookahead); warmup months default risk-on (matches production).
- mooex T+1 MOO exact, 10 bps/side, via the canonical exec_lag_moo_validation_2026_05_30._segment_returns_conv engine. Ext pre-2006-08 proxy-backed; clean 18y is the decisive lens.
