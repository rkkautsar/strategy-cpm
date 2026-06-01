# Corrected HAA -> CPM factor attribution: coupled-factor 2^5 factorial

Role: analyst (read-only relative to production; no production files changed; no commit). Throwaway harness in `research/`.

Script: `research/cpm_haa_coupled_factorial.py` -> `research/cpm_haa_coupled_factorial.json`. Engine: shared `_segment_returns_conv` mooex T+1 market-on-open execution, 10 bps/side, identical to every production CPM study. Cash leg for excess metrics is SHV. Production CPM = both-252 (`CORR_LOOKBACK_DAYS = 252`).

## Why this re-run exists

The prior ladder (`cpm_haa_benchmark_ladder.py`) split the single shared trend metric into two independently-toggled factors: a RANKER factor (F2: 13612U -> Faber/rv, which silently coupled the rank metric and the vol-adjust together) and a separate SCREEN factor (F4: absolute 13612U>0 -> Faber>0). That decoupling let the trend-screen metric move independently of the rank metric, producing off-diagonal cells (rank by Faber but screen on 13612U, or vice versa) that neither HAA nor CPM ever runs. Any main effect or universe-conditional sign read off those cells is contaminated by configs that do not correspond to a real strategy.

This harness re-derives the factorial with factors defined the way the real strategies actually couple them.

## Corrected factor set (5 factors, 2^5 = 32 cells)

| factor | OFF (HAA) | ON (CPM) | what it touches |
|---|---|---|---|
| **T** trend metric | 13612U | Faber 10mo-SMA distance `m_faber` | **couples** rank numerator AND absolute screen (one flip changes both) |
| **V** vol-adjust | raw rank | rank numerator / `rv_252d` | **only** the rank denominator (screen untouched) |
| **W** weighting | equal-weight | inverse-vol (cov tail 252) | weight of surviving picks |
| **C** canary | TIP-only (13612U>0) | HYG-or-TIP (any-positive) | risk-on/off gate |
| **U** universe | HAA 8-set | CPM 8-set | candidate assets |

HAA 8-set = [SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT]; CPM 8-set = [QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC]. Held fixed throughout (not factors): TOP-4 cap; partial-safe breadth scaling (`risky_fraction = n_pass/4`, remainder -> safe); best-of-safe {SHV, IEF} by 13612U; SHV=BIL ultra-short T-bill wash.

The key structural difference from the prior harness: **T flips the metric for both the rank numerator and the screen at once**, and **V is a clean denominator-only modifier**. The resulting off-diagonal cells are all real plausible strategies (e.g. T=ON/V=OFF = raw Faber rank+screen; T=OFF/V=ON = risk-adjusted 13612U), so every interior cell is a coherent interpolation between two real endpoints.

## Endpoints reproduce (all four gates PASS)

| gate | check | result |
|---|---|---|
| all-OFF == canonical HAA | weight-by-weight vs standalone HAA fn, every rebalance | 0 mismatches, PASS |
| all-ON == production CPM | weight-by-weight vs `cpm_live.compute_target_weights` | 0 mismatches, PASS |
| all-OFF hits HAA anchor | CLEAN Sharpe 0.8670 / MaxDD -14.68% / Calmar 0.6386 | actual 0.8670 / -14.68% / 0.6386, PASS |
| all-ON hits CPM anchor | CLEAN Sharpe 1.1658 / MaxDD -12.97% / Calmar 1.0137 | actual 1.1658 / -12.97% / 1.0137, PASS |

Both endpoints reproduce to 4 decimals. The cube is anchored by construction.

Windows: CLEAN = 2008-05-30..2026-05-22 (18y, full real-open coverage; the decision lens). EXT = 1999-03-10..2026-05-22 (27y, partly proxy-backed pre-2006; robustness only). Single in-sample evaluation: read direction and robustness (sign-flip across the 16 backgrounds) over decimals.

## Endpoint benchmark (same window / costs / engine)

| strategy | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| HAA (canonical, all-OFF) | 0.8670 | 9.37% | 11.08% | -14.68% | 0.6386 |
| CPM (both-252, all-ON) | 1.1658 | 13.15% | 11.18% | -12.97% | 1.0137 |

At matched ~11% vol, CPM earns ~3.8 pp/yr more CAGR with a shallower MaxDD.

## Headline 2x2: mechanism x universe (with the completing cell)

The cleanest mechanism-vs-universe attribution is the full 2x2: bundle all four mechanism factors (T, V, W, C) into a single HAA-mech vs CPM-mech axis, cross it with the universe axis, and read all four corners -- including the cell the prior writeup omitted, **HAA's simple machinery on the CPM universe**.

- cfg1 HAA-mech / HAA-universe = canonical HAA (13612U coupled rank+screen, raw, equal-weight, TIP).
- cfg2 CPM-mech / HAA-universe (Faber coupled, /rv, inverse-vol, HYG-or-TIP, on HAA's assets).
- cfg3 CPM-mech / CPM-universe = production CPM both-252.
- cfg4 HAA-mech / CPM-universe (the completing cell: HAA's 13612U machinery on [QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC]).

CLEAN (decision lens):

| cell | mech / universe | Sharpe | Calmar | MaxDD | CAGR |
|---|---|---:|---:|---:|---:|
| cfg1 | HAA-mech / HAA-univ (= canonical HAA) | 0.8670 | 0.6386 | -14.68% | 9.37% |
| cfg2 | CPM-mech / HAA-univ | 0.9575 | 0.6350 | -15.69% | 9.96% |
| cfg4 | **HAA-mech / CPM-univ** | **1.0189** | **0.7693** | -14.96% | 11.51% |
| cfg3 | CPM-mech / CPM-univ (= CPM both-252) | 1.1658 | 1.0137 | -12.97% | 13.15% |

EXT (robustness):

| cell | mech / universe | Sharpe | Calmar | MaxDD | CAGR |
|---|---|---:|---:|---:|---:|
| cfg1 | HAA-mech / HAA-univ | 1.0307 | 0.7527 | -14.68% | 11.05% |
| cfg2 | CPM-mech / HAA-univ | 1.0663 | 0.6900 | -15.69% | 10.83% |
| cfg4 | HAA-mech / CPM-univ | 1.1141 | 0.8156 | -15.35% | 12.52% |
| cfg3 | CPM-mech / CPM-univ | 1.2004 | 0.8571 | -15.73% | 13.48% |

Key reads (CLEAN):

- **cfg4 vs cfg1 -- pure universe lift on HAA's own machinery: +0.152 Sharpe / +0.131 Calmar / -0.28pp MaxDD.** Just handing HAA's simple, fast 13612U machinery the CPM asset set carries it from 0.867 to 1.019 Sharpe and 0.639 to 0.769 Calmar. That is ~51% of the total Sharpe lift (0.299) and ~35% of the total Calmar lift (0.375) achieved with **none** of CPM's mechanism changes.
- **cfg4 vs cfg3 -- what CPM's machinery adds once it has the better universe: +0.147 Sharpe / +0.244 Calmar / +1.99pp MaxDD.** So HAA's machinery does NOT capture most of the edge once it has the universe: on Sharpe the two halves split roughly 51/49, but on the risk-adjusted metrics CPM's machinery does the heavier lifting (+0.244 Calmar, +1.99pp shallower MaxDD). The drawdown-control payoff of vol-adjust + inverse-vol + Faber is what HAA's plain machinery leaves on the table.
- **cfg2 vs cfg1 -- CPM's machinery on HAA's universe: +0.091 Sharpe but -0.004 Calmar / -1.01pp MaxDD.** On HAA's own assets the full CPM mechanism bundle buys a little Sharpe and actually gives back Calmar and drawdown. The mechanism is not a portable upgrade.
- **Mechanism x universe interaction (Calmar) = +0.248** (mechanism helps Calmar by +0.244 on the CPM universe but by -0.004 on the HAA universe). The entire risk-adjusted value of CPM's machinery is universe-conditional.

EXT tempers this: there the completing cell cfg4 (1.114 / 0.816) sits very close to full CPM cfg3 (1.200 / 0.857) -- HAA's machinery on the CPM universe captures most of the EXT edge, and CPM's machinery adds only +0.086 Sharpe / +0.042 Calmar. The mechanism x universe Calmar interaction is +0.104, same sign but about half the CLEAN size. So the "machinery earns its keep, but only on the CPM universe" conclusion holds in both windows; its magnitude is larger and more drawdown-driven on the CLEAN window.

Bottom line of the 2x2: the **better universe is necessary and does most of the Sharpe work even with HAA's plain machinery (cfg4)**; CPM's machinery is **complementary, not redundant** -- it adds little (and hurts Calmar) on HAA's universe, but on the CPM universe it contributes the majority of the Calmar/drawdown improvement that lifts cfg4 (0.77 Calmar) to cfg3 (1.01 Calmar).

## Head-to-head: Faber vs 13612U WITHIN the full CPM stack (CPM universe)

The realistic metric comparison holds everything at full CPM (vol-adjust ON, inverse-vol, HYG-or-TIP, CPM universe) and flips ONLY the coupled trend metric. This isolates production's actual choice -- slow Faber 10mo-SMA distance vs fast 13612U multi-horizon momentum -- both vol-adjusted, on the growth-tilted CPM universe.

- Production CPM = T=Faber (1,1,1,1,1).
- CPM-13612U = T=13612U, everything else full CPM (0,1,1,1,1).

| metric variant | window | Sharpe | Calmar | MaxDD | CAGR | Vol |
|---|---|---:|---:|---:|---:|---:|
| CPM-Faber (production) | CLEAN | 1.1658 | 1.0137 | -12.97% | 13.15% | 11.18% |
| CPM-13612U | CLEAN | 1.1540 | 0.9876 | -13.32% | 13.15% | 11.31% |
| CPM-Faber (production) | EXT | 1.2004 | 0.8571 | -15.73% | 13.48% | 11.05% |
| CPM-13612U | EXT | 1.1808 | 0.7170 | -18.72% | 13.42% | 11.20% |

Faber-minus-13612U: CLEAN +0.012 Sharpe / +0.026 Calmar / +0.34pp MaxDD; EXT +0.020 Sharpe / +0.140 Calmar / +2.99pp MaxDD.

Read:

- **Faber's edge over 13612U is a drawdown-control edge, not a return edge.** CAGR is identical to two decimals in both windows (13.15% CLEAN, ~13.4% EXT). The slower 10mo-SMA does not pick better winners; it whipsaws less in drawdowns.
- **On the CLEAN decision window the choice is marginal / within noise:** +0.012 Sharpe and +0.026 Calmar. Production's Faber is a small, same-direction improvement, but a 13612U-metric CPM (Sharpe 1.154 / Calmar 0.988) would be a very close substitute -- the fast metric is not meaningfully worse on the clean window.
- **The Faber benefit is materially larger and more robust in the longer EXT window:** +0.140 Calmar and +2.99pp shallower MaxDD (-15.73% vs -18.72%), driven by the extra crisis windows (2000-02, 2008). So Faber's payoff is concentrated in tail/crash periods that the 18y CLEAN window underweights.
- **Net:** production's choice of Faber over 13612U on the CPM universe is paying off, but mainly as crisis-drawdown insurance rather than higher Sharpe/CAGR. On clean-window risk-adjusted return it is a marginal call; the longer history is what makes Faber the clearer pick (shallower tails, +0.14 Calmar). This contrasts with the HAA universe, where the metric swap (T) was robustly negative -- on the CPM universe the Faber-vs-13612U decision is at worst a wash and on the full window a real drawdown win.

(The completing 2x2 cell cfg4 -- HAA-mech / CPM-universe, 13612U coupled, raw/no-vol-adjust, equal-weight, TIP canary -- is reported in the 2x2 table above: CLEAN 1.0189 / 0.7693 / -14.96%, EXT 1.1141 / 0.8156 / -15.35%.)

## Per-factor background-averaged main effects (CLEAN, decision lens)

Each effect is the average ON-minus-OFF delta over all 16 backgrounds. `flip` = the sign of the delta is not consistent across all backgrounds.

| factor | dSharpe | flip | dCalmar | flip | dMaxDD | flip |
|---|---:|:--:|---:|:--:|---:|:--:|
| **U** universe | **+0.192** | no | **+0.236** | no | +0.83pp | yes |
| **V** vol-adjust | +0.047 | yes | +0.049 | yes | +0.64pp | no |
| **C** canary | +0.024 | yes | +0.077 | no | +0.14pp | no |
| **W** weighting | +0.024 | yes | +0.010 | yes | +0.60pp | no |
| **T** trend metric | +0.020 | yes | **-0.030** | yes | **-1.10pp** | yes |

EXT (robustness) main effects, same ordering of magnitude: U dominates (Sharpe +0.123, Calmar +0.109); C positive (Sharpe +0.031, no flip); T is again the weakest/negative on Calmar (-0.014) and deepens drawdown on average.

Read:

- **UNIVERSE (U) is the dominant, robust edge driver.** Largest main effect on every metric, no sign-flip on Sharpe or Calmar in either window. Roughly four to ten times the size of any mechanism factor.
- **VOL-ADJUST (V)** is the strongest *mechanism* factor on average (Sharpe/Calmar) and reliably shallows drawdown (+0.64pp, no flip), but its Sharpe/Calmar sign flips across backgrounds, i.e. it is conditionally good.
- **CANARY (C)** helps Calmar robustly (+0.077, no flip) by cutting tail exposure.
- **WEIGHTING (W)** is a small positive; inverse-vol mostly buys a bit of drawdown control.
- **TREND METRIC (T)**, on a pooled average, *worsens* Calmar (-0.030) and *deepens* MaxDD (-1.10pp). This is the headline correction (next section).

## Universe-conditional effects (CLEAN): the corrected attribution

For each non-universe factor, the average ON-minus-OFF delta is computed twice: across the 8 backgrounds *within the HAA universe* (U=0) and across the 8 *within the CPM universe* (U=1).

Calmar (mean delta [min, max], flip):

| factor | within HAA universe | within CPM universe |
|---|---|---|
| **T** trend metric | **-0.096** [-0.163, -0.039] no flip | **+0.037** [+0.015, +0.069] no flip |
| **V** vol-adjust | -0.017 [-0.056, +0.014] flip | **+0.114** [+0.091, +0.132] no flip |
| **W** weighting | +0.013 [-0.067, +0.050] flip | +0.008 [-0.021, +0.042] flip |
| **C** canary | +0.064 [+0.037, +0.130] no flip | +0.090 [+0.080, +0.103] no flip |

MaxDD (mean delta, positive = shallower):

| factor | within HAA universe | within CPM universe |
|---|---|---|
| **T** trend metric | **-2.81pp** [-3.63, -1.95] no flip | **+0.62pp** [+0.34, +1.07] no flip |
| **V** vol-adjust | +0.14pp [-0.00, +0.78] no flip | +1.13pp [+0.85, +1.24] no flip |
| **W** weighting | +0.85pp no flip | +0.35pp no flip |
| **C** canary | +0.28pp no flip | -0.00pp no flip |

Sharpe (mean delta, flip):

| factor | within HAA universe | within CPM universe |
|---|---|---|
| T trend metric | +0.027 flip | +0.013 flip |
| V vol-adjust | +0.021 flip | **+0.072** no flip |
| W weighting | +0.027 flip | +0.020 no flip |
| C canary | +0.010 flip | +0.038 no flip |

### Which factor is net-negative on the HAA universe?

**The TREND METRIC (T) is net-negative on the HAA universe -- and the drag is real, not a decoupling artifact.** Swapping HAA's 13612U rank-and-screen for CPM's Faber metric, *as a coupled unit*, costs -0.096 Calmar and deepens MaxDD by -2.81pp on HAA's own eight assets, with **no sign-flip** across any of the eight backgrounds (robustly bad). Its Sharpe contribution there is a weak +0.027 that does flip sign, i.e. not a real Sharpe gain. The same swap on the CPM universe *helps* (+0.037 Calmar, +0.62pp MaxDD, both no flip). The trend metric is therefore the factor whose benefit is entirely universe-conditional, and it is the only factor that is robustly damaging off the CPM universe.

### Was the prior negative an artifact? Is vol-adjust the culprit, or the metric?

The prior decoupled harness located a net-negative on the HAA universe inside its entangled "ranker" factor (13612U -> Faber/rv, metric and vol-adjust bundled). With the corrected coupling we can separate the two:

- **It is the METRIC, not the vol-adjust.** Vol-adjust (V) on the HAA universe is essentially neutral (Calmar -0.017 with a sign-flip; MaxDD +0.14pp; Sharpe +0.021 flip) -- it neither helps nor hurts robustly there. The whole HAA-universe drag comes from the Faber metric (T), which is robustly negative on Calmar and MaxDD.
- **The drag is genuine, the prior attribution was mislocated.** The prior study was right that *something* in the metric/ranker bundle drags on HAA's universe, but bundling vol-adjust into the ranker blurred which half. The decoupling artifact was in attribution precision, not in the existence of the drag: Faber really is the wrong trend metric for the HAA asset set (those assets -- broad equity/bond/REIT/commodity sleeves -- rank better under 13612U's multi-horizon momentum than under a single 10-month SMA distance).
- **Vol-adjust is the cleanest mechanism win, but only on the CPM universe.** V is strongly positive on the CPM universe (Calmar +0.114, Sharpe +0.072, MaxDD +1.13pp, all no flip) and neutral on the HAA universe. It is conditionally good, not universally good -- which is exactly why its pooled main effect sign-flips.

## Sequential ladder (HAA -> CPM) and order-dependence

Sensible order T, V, W, C, U (mechanism first, universe last):

| config | step | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| 00000 | HAA (all-OFF) | 0.8670 | 0.6386 | -14.68% |
| 10000 | +T trend metric | 0.8708 | 0.5678 | -16.63% |
| 11000 | +V vol-adjust | 0.8980 | 0.5606 | -16.63% |
| 11100 | +W weighting | 0.9653 | 0.5977 | -15.69% |
| 11110 | +C canary | 0.9575 | 0.6350 | -15.69% |
| 11111 | +U universe = CPM | 1.1658 | 1.0137 | -12.97% |

Alternate order U, T, V, W, C (universe first):

| config | step | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| 00000 | HAA (all-OFF) | 0.8670 | 0.6386 | -14.68% |
| 00001 | +U universe | 1.0189 | 0.7693 | -14.96% |
| 10001 | +T trend metric | 1.0415 | 0.8077 | -14.29% |
| 11001 | +V vol-adjust | 1.0874 | 0.9118 | -13.05% |
| 11101 | +W weighting | 1.1290 | 0.9166 | -12.97% |
| 11111 | +C canary = CPM | 1.1658 | 1.0137 | -12.97% |

**Strong order-dependence, driven entirely by T x U.** In the mechanism-first ladder, adding T as the very first step on HAA's universe *drops* Calmar 0.639 -> 0.568 and deepens MaxDD -14.68% -> -16.63%; the path stays drawdown-deep until U is switched last and delivers the entire jump to CPM (Calmar 0.635 -> 1.014). In the universe-first ladder, U alone lifts Sharpe 0.867 -> 1.019 / Calmar 0.639 -> 0.769, and then the *same* T step now *adds* (Calmar 0.808 -> ... up the path). T looks damaging or helpful depending purely on whether the universe has already been switched. Do not read a single ladder as causal attribution for T.

## Key two-way interactions (CLEAN)

Largest-magnitude interactions confirm the universe-conditional story:

| interaction | dCalmar | dSharpe |
|---|---:|---:|
| **T x U** | **+0.067** | -0.007 |
| **V x U** | **+0.066** | +0.026 |
| C x U | +0.013 | +0.014 |
| T x W | +0.006 | +0.015 |

The two dominant interactions are both *factor x universe*: T x U (+0.067 Calmar) and V x U (+0.066 Calmar). Both the trend metric and the vol-adjust are far more valuable once the universe is the CPM set -- they are CPM-universe-specialized mechanisms, not portable improvements. Canary x universe is a smaller, same-signed positive. No large mechanism x mechanism interaction.

## Crisis MaxDD (continuous curve, trough in window)

| crisis | HAA | CPM-mech on HAA universe | CPM full |
|---|---:|---:|---:|
| Dot-com | -7.1% | -6.5% | -6.0% |
| GFC | -12.7% | -13.8% | -11.9% |
| COVID | -8.9% | -7.4% | -10.5% |
| 2022 | -7.1% | -6.0% | -8.3% |

CPM's full machinery does not strictly dominate HAA crisis-by-crisis (HAA is shallower in COVID and 2022); HAA remains a genuine diversifier of CPM's worst episodes.

## Verdict

With realistic coupled factors and both endpoints reproduced exactly:

1. **The CPM edge over HAA is overwhelmingly a UNIVERSE effect.** Switching to the CPM asset set [QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC] is the single dominant, robust driver (CLEAN main effect +0.192 Sharpe / +0.236 Calmar, no sign-flip; ~4-10x any mechanism factor; same ranking in EXT). It is the only change that is unconditionally good.

2. **The mechanism factors are CPM-universe-specialized, not portable.** Vol-adjust and the Faber trend metric each carry their value through a large positive factor-x-universe interaction (V x U +0.066, T x U +0.067 Calmar). On the CPM universe both help robustly; ported onto HAA's universe vol-adjust goes neutral and the trend metric goes negative.

3. **The trend metric (Faber, as the coupled rank+screen unit) is net-negative on the HAA universe -- robustly (no sign-flip on Calmar or MaxDD), and this is a real drag, not a decoupling artifact.** The prior decoupled study correctly sensed a metric/ranker drag on HAA's assets but mislocated it inside an entangled ranker factor. Cleanly separated: the **metric** is the culprit (Calmar -0.096, MaxDD -2.81pp on HAA universe), the **vol-adjust is not** (roughly neutral on HAA universe; strongly positive only on CPM universe). 13612U is the better trend metric for HAA's broad-sleeve assets; Faber is the better metric only once paired with CPM's asset set.

4. **Canary (HYG-or-TIP) is the most portable mechanism improvement** -- it helps Calmar robustly on both universes (no sign-flip) by trimming tail exposure, though its absolute size is small.

5. **Ladder attribution is order-dependent and must not be over-read** for the trend metric: T appears damaging when added before the universe switch and helpful after it, a direct consequence of the T x U interaction.

Bottom line for the memo: CPM's documented dominance over HAA is primarily its asset universe, amplified by two mechanism choices (vol-adjusted Faber ranking, HYG-or-TIP canary) that are tuned to that universe. The Faber trend metric in particular is not a free upgrade -- it underperforms 13612U on HAA's own assets -- so the mechanism edge should be claimed jointly with the universe, not as a standalone, universe-independent improvement.

## Caveats and confidence

- Single in-sample evaluation over one historical path; magnitudes are in-sample. Confidence is in *direction and robustness* (sign-flip across 16 backgrounds), highest for the no-flip results: U dominance, T net-negative on HAA universe, V positive only on CPM universe, C positive on Calmar.
- EXT (pre-2006) is partly proxy-backed; treated as robustness only. Main-effect ordering is stable between CLEAN and EXT.
- Effects are linear-model (Yates) main effects / two-way interactions; higher-order interactions are folded into the residual but the dominant structure is captured by the two factor-x-universe terms.
- BIL->SHV is a cosmetic same-instrument wash held fixed; TOP-4 cap and partial-safe routing are common to both ends and not tested here.

## Reproduce

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
.venv/bin/python research/cpm_haa_coupled_factorial.py
```

Outputs `research/cpm_haa_coupled_factorial.json` (gates, 32 cells x 2 windows, main effects, universe-conditional effects, both ladders, interactions, crisis table). Prior decoupled harness left intact at `research/cpm_haa_benchmark_ladder.{py,json,md}`.
