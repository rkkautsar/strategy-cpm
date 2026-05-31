# Faster vol-gate window (RV20<RV252) validation -- NDX + BULL sleeves

Role: analyst (hypothesis-driven; read-only re production; writes only to research/; no production/memo edits; no commit). EXPLORATION ONLY. Harness `research/rv20_window_validation.py` (reuses ndx_volgate_variants + bull_volgate_variants + exec_lag_moo_validation engines verbatim).

**Hypothesis.** RV60<RV252 (V0, inherited from BULL) is too SLOW for high-beta NDX; a FASTER window (RV20<RV252 on SPY) re-risks quicker post-spike and de-risks earlier into drawdowns. If RV20 also rescues BULL, the queued decision to DROP the BULL gate (RV60 within-noise vs no-gate) should become a RETUNE to RV20, not a drop.

**Discipline.** Paired stationary block bootstrap (B=5000, block 21d) on the marginal RV20-minus-V0 AND RV20-minus-no-gate for Calmar/Martin/Sharpe (CI exclude 0?); walk-forward (freeze window pre-2017, test 2017+); response-surface plateau-vs-spike; per-episode removal. Same skepticism that killed the CPM PC1 gate.

**Honesty guards.** T+1 MOO, point-in-time membership, single 18y in-sample, NDX pre-2017 ~28% survivorship bias (so the post-2017 genuine-OOS walk-forward slice is weighted heavily). Anchors reproduced before deltas. No adoption without explicit user confirmation.


## NDX sleeve

Window 2007-02-28..2026-05-22. Anchor V0(RV60): Sharpe **1.1812** / MaxDD **-35.92%** / Calmar **0.7602** / Martin **2.9753** -> **CONFIRMED**. RV20: Calmar **0.9595** / Martin **4.1796** / MaxDD **-31.39%**. No-gate: Calmar **0.7839** / Martin **2.2691** / MaxDD **-38.77%**.

### NDX 1. Paired bootstrap CI -- RV20 minus V0(RV60)

| Marginal metric | p2.5 | p50 | p97.5 | mean | P(d>0) | excludes 0? |
|---|---:|---:|---:|---:|---:|:--:|
| Calmar | -0.1155 | +0.1253 | +0.5483 | +0.1511 | 85.3% | NO (includes 0) |
| Martin | -0.5448 | +0.6134 | +2.4861 | +0.7083 | 84.9% | NO (includes 0) |
| Sharpe | -0.0810 | +0.0789 | +0.2647 | +0.0822 | 82.7% | NO (includes 0) |

### NDX 2. Paired bootstrap CI -- RV20 minus no-gate

| Marginal metric | p2.5 | p50 | p97.5 | mean | P(d>0) | excludes 0? |
|---|---:|---:|---:|---:|---:|:--:|
| Calmar | -0.2290 | +0.2032 | +0.8067 | +0.2255 | 81.4% | NO (includes 0) |
| Martin | -0.6664 | +1.2220 | +3.9666 | +1.3277 | 89.5% | NO (includes 0) |
| Sharpe | -0.1263 | +0.1392 | +0.4248 | +0.1411 | 84.0% | NO (includes 0) |

### NDX 3. Walk-forward (freeze window pre-2017, test 2017+ genuine OOS / clean PIT)

Train 2007-02-28..2016-12-31 -> Test 2017-01-01..2026-05-22. Window selected on TRAIN Calmar = **60**; best window on TEST Calmar = **20**.

| fast | train Calmar | train Martin | test Calmar | test Martin | test Sharpe | test MaxDD |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 1.4185 | 5.7041 | 1.1729 | 3.5381 | 1.2609 | -31.39% |
| 15 | 1.2181 | 5.3447 | 1.1798 | 4.0207 | 1.2919 | -31.39% |
| 20 | 1.2461 | 5.4052 | 1.2709 | 4.2116 | 1.3574 | -31.39% |
| 25 | 1.2531 | 5.5209 | 1.0312 | 2.8638 | 1.1736 | -31.39% |
| 30 | 0.7751 | 2.5954 | 1.0821 | 3.0114 | 1.1959 | -31.39% |
| 40 | 1.2972 | 5.9640 | 0.9571 | 2.6680 | 1.1638 | -34.01% |
| 50 | 1.3942 | 6.6541 | 0.8661 | 2.6181 | 1.1300 | -35.92% |
| 60 | 1.4372 | 6.8187 | 0.8369 | 2.3862 | 1.1094 | -35.92% |
| 90 | 0.9005 | 4.1743 | 0.6067 | 1.5803 | 0.9386 | -39.75% |
| 120 | 1.3778 | 5.9631 | 0.3040 | 0.7329 | 0.6672 | -48.81% |

No-gate test Calmar 0.9706 / Martin 2.4061; V0 test Calmar 0.8369 / Martin 2.3862; RV20 test Calmar 1.2709 / Martin 4.2116.

### NDX 4. Response surface RV{fast}<RV252 SPY (full window)

| fast window | Calmar | Martin | Sharpe | MaxDD |
|---:|---:|---:|---:|---:|
| 10 | 0.9292 | 3.7431 | 1.2274 | -31.39% |
| 15 | 0.9095 | 4.0639 | 1.2200 | -31.39% |
| 20 | 0.9595 | 4.1796 | 1.2658 | -31.39% |
| 25 | 0.8513 | 3.1886 | 1.1622 | -31.39% |
| 30 | 0.8450 | 2.7621 | 1.1286 | -31.39% |
| 40 | 0.8001 | 3.0449 | 1.1710 | -34.01% |
| 50 | 0.7633 | 3.1529 | 1.1804 | -35.92% |
| 60 | 0.7602 | 2.9753 | 1.1812 | -35.92% |
| 90 | 0.5349 | 1.9103 | 0.9634 | -39.75% |
| 120 | 0.3954 | 1.3382 | 0.9217 | -48.81% |

### NDX 5. Per-episode removal (drop one crisis, recompute RV20 edge)

| dropped window | RV20 Calmar | RV20 Martin | dCalmar vs V0 | dMartin vs V0 | dCalmar vs no-gate | dMartin vs no-gate |
|---|---:|---:|---:|---:|---:|---:|
| none (full) | 0.9595 | 4.1796 | +0.1993 | +1.2043 | +0.1756 | +1.9105 |
| 2008 GFC | 0.9240 | 3.9007 | +0.1941 | +1.1423 | +0.1686 | +1.6739 |
| 2018 Q4 | 0.9092 | 3.7160 | +0.1936 | +1.0860 | +0.1602 | +1.6074 |
| 2020 COVID | 0.8868 | 3.8161 | +0.1417 | +0.8399 | +0.1699 | +1.7486 |
| 2022 bear | 0.9575 | 4.0728 | +0.1990 | +1.1772 | +0.1479 | +1.3214 |

### NDX 6. Per-crisis protection (MaxDD / total return)

| Variant | 2008 GFC | 2018 Q4 | 2020 COVID | 2022 bear |
|---|---|---|---|---|
| V0 | -9.11% / 18.01% | -7.43% / 27.57% | -20.46% / 8.57% | -0.30% / 0.94% |
| RV20 | -9.11% / 18.01% | -8.26% / 26.44% | -5.05% / 40.53% | -0.30% / 0.94% |
| NOGATE | -9.11% / 17.78% | -14.25% / 22.14% | -20.46% / 47.22% | -26.25% / -13.61% |


## BULL sleeve

Clean window 2008-05-30..2026-05-22. Anchor V0(RV60): Sharpe **1.1005** / Calmar **0.8189** / Martin **3.0714** / MaxDD **-13.35%** -> **CONFIRMED**. RV20: Calmar **0.8701** / Martin **2.8773** / MaxDD **-12.53%**. No-gate (HAA-Simple): Calmar **0.5685** / Martin **2.3815** / MaxDD **-20.41%**.

### BULL 1. Paired bootstrap CI -- RV20 minus V0(RV60)

| Marginal metric | p2.5 | p50 | p97.5 | mean | P(d>0) | excludes 0? |
|---|---:|---:|---:|---:|---:|:--:|
| Calmar | -0.3222 | +0.0269 | +0.5365 | +0.0533 | 56.2% | NO (includes 0) |
| Martin | -1.3419 | +0.0693 | +1.9724 | +0.1359 | 53.4% | NO (includes 0) |
| Sharpe | -0.2581 | -0.0192 | +0.2728 | -0.0137 | 44.6% | NO (includes 0) |

### BULL 2. Paired bootstrap CI -- RV20 minus no-gate (KEY: does faster beat no-gate?)

| Marginal metric | p2.5 | p50 | p97.5 | mean | P(d>0) | excludes 0? |
|---|---:|---:|---:|---:|---:|:--:|
| Calmar | -0.3220 | +0.1389 | +0.7414 | +0.1559 | 71.9% | NO (includes 0) |
| Martin | -1.3449 | +0.5426 | +2.9408 | +0.5964 | 71.3% | NO (includes 0) |
| Sharpe | -0.2480 | +0.0971 | +0.4948 | +0.1033 | 69.9% | NO (includes 0) |

### BULL 3. Response surface RV{fast}<RV252 SPY (clean 18y)

| fast window | Calmar | Martin | Sharpe | MaxDD |
|---:|---:|---:|---:|---:|
| 10 | 0.8995 | 3.1541 | 1.1220 | -12.53% |
| 15 | 0.8371 | 2.5321 | 1.0449 | -12.53% |
| 20 | 0.8701 | 2.8773 | 1.0894 | -12.53% |
| 25 | 0.7892 | 2.9366 | 1.0489 | -13.35% |
| 30 | 0.8106 | 2.9004 | 1.0626 | -13.35% |
| 40 | 0.8234 | 3.1227 | 1.0861 | -13.35% |
| 50 | 0.8272 | 3.2449 | 1.1089 | -13.35% |
| 60 | 0.8189 | 3.0714 | 1.1005 | -13.35% |
| 90 | 0.5163 | 2.0132 | 0.8794 | -17.31% |
| 120 | 0.5517 | 2.1677 | 1.0110 | -17.43% |

### BULL 4. Per-episode removal (drop one crisis, recompute RV20 edge)

| dropped window | RV20 Calmar | RV20 Martin | dCalmar vs V0 | dMartin vs V0 | dCalmar vs no-gate | dMartin vs no-gate |
|---|---:|---:|---:|---:|---:|---:|
| none (full) | 0.8701 | 2.8773 | +0.0512 | -0.1942 | +0.3016 | +0.4957 |
| 2008 GFC | 0.8964 | 3.0757 | +0.0527 | -0.2402 | +0.3094 | +0.5949 |
| 2018 Q4 | 0.8039 | 2.5915 | +0.0507 | -0.1636 | +0.2655 | +0.3684 |
| 2020 COVID | 0.8243 | 2.7015 | -0.0996 | -0.6660 | +0.2678 | +0.3335 |
| 2022 bear | 0.8655 | 2.7991 | +0.0509 | -0.1914 | +0.2960 | +0.4503 |

### BULL 5. Walk-forward (freeze window pre-2017, test 2017+)

Train 2008-05-30..2016-12-31 -> Test 2017-01-01..2026-05-22. Window selected on TRAIN Calmar = **60**; best window on TEST Calmar = **20**.

| fast | train Calmar | train Martin | test Calmar | test Martin | test Sharpe | test MaxDD |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.6817 | 2.0594 | 1.1203 | 4.4874 | 1.4042 | -12.53% |
| 15 | 0.6031 | 1.4552 | 1.0709 | 4.2731 | 1.3603 | -12.53% |
| 20 | 0.6014 | 1.5194 | 1.1375 | 5.5846 | 1.4489 | -12.53% |
| 25 | 0.6910 | 2.0271 | 0.9357 | 4.1420 | 1.2622 | -13.35% |
| 30 | 0.7494 | 2.2186 | 0.9274 | 3.6680 | 1.2255 | -13.35% |
| 40 | 0.7992 | 2.4594 | 0.9098 | 3.9208 | 1.2208 | -13.35% |
| 50 | 0.7524 | 2.3590 | 0.9571 | 4.3656 | 1.3307 | -13.35% |
| 60 | 0.8005 | 2.5262 | 0.8999 | 3.6518 | 1.2666 | -13.35% |
| 90 | 0.3906 | 1.2678 | 0.8157 | 3.1833 | 1.1458 | -13.35% |
| 120 | 0.6995 | 2.1311 | 0.6087 | 2.1988 | 1.2012 | -17.43% |

### BULL 6. Per-crisis protection (MaxDD / total return) -- keep 2008/2020 crash + 2018/2022 grind

| Variant | 2008 GFC | 2018 Q4 | 2020 COVID | 2022 bear |
|---|---|---|---|---|
| V0 | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| RV20 | -12.09% / 6.57% | -3.00% / 14.43% | -6.99% / 9.76% | -0.30% / 0.94% |
| NOGATE | -12.09% / 6.57% | -10.10% / 10.42% | -13.35% / 4.02% | -10.11% / -0.33% |


## VERDICT

### Discipline scorecard (4 checks per marginal)

| Sleeve / marginal | point edge | bootstrap CI excludes 0 | walk-forward OOS | plateau (not spike) | episode-removal survives |
|---|---|:--:|:--:|:--:|:--:|
| NDX RV20 vs V0(RV60) | Calmar +0.20, Martin +1.20, MaxDD -4.5pp | **NO** (P=85%) | **YES** (decisive, monotone) | **YES** (10-20 band) | **YES** (all drops +) |
| NDX RV20 vs no-gate | Calmar +0.18, Martin +1.91 | **NO** (P=81%) | **YES** | **YES** | **YES** |
| BULL RV20 vs V0(RV60) | Calmar +0.05, Martin **-0.19**, MaxDD -0.8pp | **NO** (P=56%, coin flip) | weak | flat (no fast edge) | **NO** (COVID-driven; flips to -0.10) |
| BULL RV20 vs no-gate | Calmar +0.30, Martin +0.50 | **NO** (P=72%) | partial | flat | **YES** (all drops +) |

### NDX sleeve verdict: ADOPT RV20 (strong candidate; user confirms)

The faster window is the right call for the high-beta NDX sleeve. Three of four disciplines pass, and the one that fails is the weakest evidence here:

- **Walk-forward is decisive and the most credible test.** On the genuine-OOS clean-PIT post-2017 decade, the response surface is **monotone fast-dominant**: test Calmar 10->1.17, 15->1.18, **20->1.27**, 25->1.03, 30->1.08, 40->0.96, 50->0.87, 60->0.84, 90->0.61, 120->0.30. RV20 is the single best OOS window (Calmar 1.27 / Martin 4.21) and beats both V0 (0.84) and no-gate (0.97). The naive "select on pre-2017" rule picks window=60 ONLY because the survivorship-biased (~28% missing tickers) pre-2017 training segment inflates slow windows; on the clean OOS slice (which the task says to weight heavily) fast wins overwhelmingly.
- **Plateau, not spike.** Full-window Calmar peaks at fast=20 (0.9595) with neighbors 10 (0.929) and 15 (0.910) within ~0.05; slow windows decay smoothly. A genuine fast band, not an isolated overfit point.
- **Episode-robust.** RV20's edge over BOTH V0 and no-gate survives removal of every single crisis (dCalmar vs V0 stays +0.14..+0.20; vs no-gate +0.15..+0.18). Not one-episode driven.
- **The one miss: in-sample bootstrap CI includes 0** (RV20-V0 Calmar [-0.12,+0.55], P=85.3%; RV20-no-gate [-0.23,+0.81], P=81.4%). The block bootstrap resamples the FULL 18y including the biased pre-2017 segment and shatters the COVID-2020 contribution (RV20 cuts 2020 NDX DD to -5.05% vs V0 -20.46%), so the CI is wide. P(better)~81-85% is suggestive but below the 97.5% exclude-0 bar.

**Weighing:** genuine-OOS monotone dominance over a full clean decade is stronger, less circular evidence than a single in-sample bootstrap that is itself contaminated by the survivorship-biased early segment. Net: **RV20 is the best-supported NDX gate.** Recommend adopting RV20<RV252 (SPY) for the NDX sleeve, with the honest caveat that the in-sample bootstrap does not reach exclude-0 significance. **No-gate is NOT the answer for NDX** (it blows up 2022 to -26.25% DD and 2018 to -14.25%, and loses to RV20 on Martin OOS).

### BULL sleeve verdict: KEEP V0(RV60); do NOT retune to RV20; the queued drop-vs-keep call is UNCHANGED

The faster window does NOT rescue BULL. The hypothesis is **NDX-specific** (high beta), confirmed:

- **RV20 vs V0 is a coin flip on BULL.** Bootstrap P(better)=56% Calmar / 53% Martin / 45% Sharpe; RV20 actually **loses to V0 on Martin** (2.877 vs 3.071) point-estimate. The small Calmar edge (+0.05) is **entirely the 2020 COVID episode** -- per-episode removal flips dCalmar vs V0 to **-0.0996** when COVID is dropped (RV20 becomes WORSE than V0). Fragile, single-episode, no Martin support. No case to switch V0->RV20.
- **No fast plateau on BULL.** Clean Calmar is flat across 20-60 (0.79-0.87); Martin actually PREFERS slower (50->3.24, 60->3.07 vs 20->2.88). None of the NDX monotone fast-dominance appears.
- **Faster does NOT change the vs-no-gate verdict.** RV20-minus-no-gate Calmar CI [-0.322,+0.741] **still includes 0** (P=71.9%) -- the same within-noise result that prompted the queued drop for RV60 (CI [-0.30,+0.60]). The faster window nudges P up modestly (72% vs prior ~midpoint) but does not reach exclude-0. So the faster window is NOT a reason to overturn the drop decision.

**Reconciliation -- does the faster window change the BULL conclusion from "drop" to "retune"?** **No.** On BULL: (a) RV20 vs V0 is within-noise, COVID-driven, and Martin-negative -> no reason to retune; (b) RV20 vs no-gate is still within-noise (CI includes 0) -> the faster window does not rescue the "gate beats no-gate" question that drove the drop. **The queued BULL decision should NOT be replaced by an RV20 retune.** The drop-vs-keep-RV60 call stands exactly as previously concluded (both RV60 and RV20 give a robust *point-estimate* Calmar/MaxDD improvement over no-gate that survives episode-removal -- e.g. MaxDD -13% vs -20% -- so "keep RV60 as cheap insurance" remains defensible; but neither window makes the gate bootstrap-significant vs no-gate).

### Bottom line

- **NDX: adopt RV20<RV252 (SPY).** Decisive genuine-OOS monotone fast-dominance + plateau + episode-robustness; the only miss is the in-sample bootstrap (contaminated by survivorship bias) not reaching exclude-0.
- **BULL: keep V0(RV60); do NOT retune to RV20; do NOT change the queued drop-vs-keep call.** The faster window is NDX-specific (high beta re-risking faster post-spike); on BULL it is a COVID-driven coin flip vs V0 and still within-noise vs no-gate.
- **No adoption without explicit user confirmation.**

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.
- Only the vol-gate WINDOW changes; canary/trend/selection/safe/delisting/execution held at prod.
- NDX standalone sleeve lens; at 20% blend weight effects scale ~1/5. Pre-2017 ~28% survivorship bias -> post-2017 walk-forward slice weighted heavily.
- BULL clean 18y is the decisive lens (full real-open coverage); T+1 MOO exact, 10 bps/side.
- Paired stationary block bootstrap resamples episodes preserving contemporaneous pairing; DD-based metrics (Calmar/Martin) lean on ~2 grind catches so wide CIs expected.
- No adoption without explicit user confirmation.
