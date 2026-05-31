# BULL vol-gate per-episode earns-keep vs whipsaw decomposition (MODERN sample)

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). EXPLORATION ONLY -- informs a design decision about whether the BULL slow vol gate (rv_60d<rv_252d) earns its keep modern. Harness `research/bull_volgate_episode_decomp.py`.

**Question.** Prior 1970s work (research/stagflation_1970s_*) found the vol gate is a crash-SPIKE tightener BLIND to slow grinds and WHIPSAW-prone in chop (58% false-pos 1977-82, ~1.2pp/yr CAGR cost). Does it earn its keep in the MODERN sample, or is it narrow 2020/2008-crash insurance that costs in grinds/chop?

**Ladder (three rungs).**
- (a) **SPY buy-hold**: SPY buy-hold (always 100% SPY)
- (b) **HAA-Simple** (trend ONLY): TIP canary + SPY 13612U>0 -> SPY, else best{SHV,IEF}; NO vol gate (K=0,V=0,S=1)
- (c) **BULL** (trend + vol gate): HAA-Simple + rv_60d<rv_252d vol gate (K=0,V=1,S=1)

Vol-gate **marginal effect** per episode = (c) minus (b).

**Convention (canonical).** T+1 MOO exact (`mooex`, real auto_adjust opens), 10 bps/side, monthly month-end signal. Production BULL canary `CANARY_ASSETS=['TIP']` (TIP-only). HAA-Simple and BULL share canary (TIP-only) and safe (SHV/IEF) so the vol gate is the SINGLE differentiator.

## 0. Anchor gate

BULL (TIP-only, vol gate) clean Sharpe **1.1005** / MaxDD **-13.35%** vs anchor ~1.1005 / -13.35% -> **CONFIRMED**.

### Full clean-window (18y) context

| Rung | CAGR | Vol | Sharpe | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| (a) SPY buy-hold | 11.73% | 19.82% | 0.6603 | -50.70% | 0.2313 |
| (b) HAA-Simple | 11.60% | 11.92% | 0.9840 | -20.41% | 0.5685 |
| (c) BULL | 10.93% | 9.90% | 1.1005 | -13.35% | 0.8189 |

## 1. Per-episode ladder -- vol-gate marginal effect (c) minus (b)

MaxDD and total return per episode window; key number = vol-gate marginal effect. dMaxDD>0 means BULL drawdown is SHALLOWER (vol gate earned insurance); dRet<0 with dMaxDD~0 means WHIPSAW (de-risked, missed upside, no DD benefit).

| Episode | Window | (a) SPY DD / Ret | (b) HAA DD / Ret | (c) BULL DD / Ret | Vol dMaxDD | Vol dRet | Verdict |
|---|---|---|---|---|---:|---:|---|
| 2012 eurozone wobble (calm) | 2012-01-01..2012-12-31 | -9.69% / 15.99% | -11.84% / 8.08% | -11.84% / 2.96% | +0.00pp | -5.11pp | WHIPSAW (de-risked, no DD benefit, cost upside) |
| 2015 China deval + H2 chop | 2015-07-01..2016-02-29 | -13.02% / -4.92% | -2.89% / 4.11% | -2.89% / 4.11% | +0.00pp | +0.00pp | INERT (vol gate ~no effect; trend filter did the work) |
| 2018 volmageddon + Q4 selloff | 2018-01-01..2018-12-31 | -19.35% / -4.57% | -10.10% / 10.42% | -2.14% / 15.33% | +7.96pp | +4.91pp | EARNED (vol gate reduced DD) |
| 2020 COVID crash | 2020-01-01..2020-06-30 | -33.72% / -3.21% | -13.35% / 4.02% | -13.35% / -3.82% | +0.00pp | -7.84pp | WHIPSAW (de-risked, no DD benefit, cost upside) |
| 2022 slow grind bear (KEY) | 2022-01-01..2022-12-31 | -24.50% / -18.18% | -10.11% / -0.33% | -0.30% / 0.94% | +9.81pp | +1.26pp | EARNED (vol gate reduced DD) |
| 2008-09 GFC (completeness) | 2008-05-30..2009-06-30 | -50.70% / -32.21% | -12.09% / 6.57% | -12.09% / 6.57% | +0.00pp | +0.00pp | INERT (vol gate ~no effect; trend filter did the work) |

*dMaxDD positive = BULL DD less negative than HAA (vol gate reduced drawdown). dRet positive = vol gate added return; negative = vol gate cost return (whipsaw/missed upside).*

## 2. 2022 attribution -- trend filter vs vol gate (THE key one)

- (a) SPY buy-hold 2022: MaxDD **-24.50%**, Ret **-18.18%**
- (b) HAA-Simple 2022: MaxDD **-10.11%**, Ret **-0.33%**
- (c) BULL 2022: MaxDD **-0.30%**, Ret **0.94%**
- Vol-gate marginal 2022 DD effect: **+9.81pp** (BULL -0.30% minus HAA -10.11%)
- 2022 months trend filter de-risked (SPY 13612U<=0): **7**
- 2022 months vol gate was SOLE binding leg (trend+canary on, vol off): **2**

**Attribution:** VOL GATE caught 2022 -- HAA-Simple bled, BULL saved it (HAA DD -10.11% -> BULL DD -0.30%).

### 2022 monthly signal calendar

| Applied month | canary | trend | vol | risk-on | trend de-risk | vol-only de-risk | SPY mo ret |
|---|:--:|:--:|:--:|:--:|:--:|:--:|---:|
| 2022-01-31 | Y | Y | n | off | - | Y | -5.27% |
| 2022-02-28 | n | Y | n | off | - | - | -2.95% |
| 2022-03-31 | Y | Y | n | off | - | Y | 3.76% |
| 2022-04-30 | n | Y | n | off | - | - | -8.78% |
| 2022-05-31 | n | Y | n | off | - | - | 0.23% |
| 2022-06-30 | n | n | n | off | - | - | -8.25% |
| 2022-07-31 | n | n | n | off | - | - | 9.21% |
| 2022-08-31 | n | n | n | off | - | - | -4.08% |
| 2022-09-30 | n | n | n | off | - | - | -9.24% |
| 2022-10-31 | n | n | Y | off | - | - | 8.13% |
| 2022-11-30 | n | n | n | off | - | - | 5.56% |
| 2022-12-31 | n | n | n | off | - | - | -5.76% |

## 3. Full modern-sample (clean 18y) vol-gate whipsaw / false-positive rate

**Definition.** vol-gate de-risk month = canary_ok AND trend_ok AND NOT vol_ok (vol gate is sole binding leg). false de-risk = governed SPY month return > 0.

- Vol-gate de-risk months (vol sole binding leg): **32**
- False de-risk (governed SPY month POSITIVE): **19** -> **false-positive rate 59.4%**
- True de-risk (SPY month negative): **12**
- Mean SPY month return on de-risk months: **0.50%**
- Full-sample (c)-vs-(b) CAGR drag: BULL 10.93% minus HAA 11.60% = **-0.67pp/yr**
- Calm-year (excl [2008, 2020, 2022]) avg marginal: **-0.33pp/yr** (total -5.31pp over calm yrs)

**1970s mirror:** 1977-82 false-positive 58%, cost ~1.2pp/yr CAGR. Modern: false-positive **59.4%**, full-sample CAGR drag **-0.67pp/yr**, calm-year avg **-0.33pp/yr**.

### Per-calendar-year vol-gate marginal (c)-(b)

| Year | (b) HAA ret | (c) BULL ret | Vol marginal | Crisis yr |
|---|---:|---:|---:|:--:|
| 2008 | 16.41% | 16.41% | +0.00pp | Y |
| 2009 | 3.23% | 3.23% | +0.00pp | - |
| 2010 | -2.22% | 14.18% | +16.39pp | - |
| 2011 | 2.76% | 13.68% | +10.93pp | - |
| 2012 | 8.08% | 2.96% | -5.11pp | - |
| 2013 | 15.33% | 15.33% | +0.00pp | - |
| 2014 | 5.12% | 4.51% | -0.61pp | - |
| 2015 | 0.96% | 0.09% | -0.88pp | - |
| 2016 | 16.28% | 14.45% | -1.82pp | - |
| 2017 | 15.53% | 15.53% | +0.00pp | - |
| 2018 | 10.42% | 15.33% | +4.91pp | - |
| 2019 | 12.80% | 8.66% | -4.14pp | - |
| 2020 | 27.17% | 16.66% | -10.50pp | Y |
| 2021 | 28.73% | 24.43% | -4.29pp | - |
| 2022 | -0.33% | 0.94% | +1.26pp | Y |
| 2023 | 10.51% | 10.51% | +0.00pp | - |
| 2024 | 18.43% | 7.24% | -11.19pp | - |
| 2025 | 16.35% | 9.54% | -6.81pp | - |
| 2026 | 8.71% | 6.03% | -2.68pp | - |

### Vol-gate de-risk months (clean 18y) + governed SPY return

| Applied month | SPY mo ret |
|---|---:|
| 2010-06-30 | -5.17% |
| 2011-08-31 | -5.5% |
| 2011-11-30 | -0.41% |
| 2011-12-31 | 1.04% |
| 2012-01-31 | 4.64% |
| 2014-11-30 | 2.75% |
| 2014-12-31 | -0.25% |
| 2015-01-31 | -2.96% |
| 2015-02-28 | 5.62% |
| 2015-03-31 | -1.57% |
| 2015-04-30 | 0.98% |
| 2016-04-30 | 0.39% |
| 2018-02-28 | -3.64% |
| 2018-06-30 | 0.58% |
| 2019-02-28 | 3.24% |
| 2019-03-31 | 1.81% |
| 2020-03-31 | -12.49% |
| 2020-05-31 | 4.76% |
| 2020-06-30 | 1.77% |
| 2021-12-31 | 4.62% |
| 2022-01-31 | -5.27% |
| 2022-03-31 | 3.76% |
| 2024-09-30 | 2.1% |
| 2024-10-31 | -0.89% |
| 2024-11-30 | 5.96% |
| 2025-02-28 | -1.27% |
| 2025-03-31 | -5.57% |
| 2025-05-31 | 6.28% |
| 2025-06-30 | 5.14% |
| 2025-07-31 | 2.3% |
| 2026-05-31 | 2.87% |
| 2026-06-30 | n/a% |

## 4. VERDICT

- **Vol gate EARNED its keep (reduced DD):** ['2018 volmageddon + Q4 selloff', '2022 slow grind bear (KEY)']
- **Vol gate WHIPSAW (de-risked, cost upside, no DD benefit):** ['2012 eurozone wobble (calm)', '2020 COVID crash']
- **Vol gate INERT (trend filter did the work):** ['2015 China deval + H2 chop', '2008-09 GFC (completeness)']

**Honest BULL justification: NEITHER clean framing fits -- it is MIXED, and the surprise is WHICH episodes the vol gate earns.** The vol gate's drawdown wins are the SLOW GRINDS where the 13612U trend filter LAGGED -- ['2018 volmageddon + Q4 selloff', '2022 slow grind bear (KEY)'] -- not the sharp spikes. In the spikes it either WHIPSAWED (2020 COVID: same DD floor as HAA but gave up ~7.8pp on the V recovery) or was INERT because the trend filter already caught it (2008-09 GFC, 2015). Episodes inert/whipsaw: ['2012 eurozone wobble (calm)', '2020 COVID crash', '2015 China deval + H2 chop', '2008-09 GFC (completeness)']. So the naive "narrow 2020/2008 spike insurance" story is BACKWARDS -- the vol gate did NOT earn its keep in 2020 or 2008. Its real modern value is front-running the lagging trend filter in grinds (2018 Q4, early-2022), bought at a steady calm-year CAGR drag.

**Bottom line.** Not "trend does all the work" (the vol gate genuinely caught the early-2022 grind the trend filter missed: HAA 2022 DD -10.11% -> BULL -0.30%, +9.81pp), and NOT "robustly additive" (it whipsaws/inert in 4 of 6 episodes, 59.4% monthly false-positive, -0.67pp/yr full-sample CAGR drag). The defensible justification is: **the vol gate is a LAGGING-TREND INSURANCE rider that earns in slow grinds (2018/2022) and pays a steady calm-year premium (~0.3pp/yr) elsewhere; it is NOT the 2020/2008 crash insurance it is often assumed to be.**

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.
- HAA-Simple and BULL share canary (TIP-only) and safe (SHV/IEF) at production values; the vol gate (rv_60d<rv_252d) is the SINGLE differentiator (apples-to-apples isolation).
- Sleeves run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side via the canonical harness exec_lag_moo_validation_2026_05_30 + bull_tiponly_recompute.run_bull_cell.
- Episode windows are sensible calendar/peak-to-trough spans (stated per row); MaxDD is computed from each window start (intra-window peak), so it understates DD if the episode peak preceded the window. 2020 uses 2020-01-01..06-30 to capture crash+recovery; GFC uses the clean-window start 2008-05-30 (clean 18y begins there).
- Whipsaw/false-positive uses calendar-month SPY close-to-close return as the governed next-month return proxy (monthly signal -> following calendar month). The daily sleeve backtest uses mooex; the monthly attribution is a coarser month-grain lens for counting.
- Calm-year drag excludes 2008/2020/2022; 'crisis' classification is for drag accounting only, not a claim about which leg caught each crisis.
