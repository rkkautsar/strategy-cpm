# Why "CPM mechanics on the HAA universe" (cfg2) is weak: conditional decomposition

Source data: `research/cpm_haa_benchmark_ladder.json` (full 2^5 = 32-cell factorial grid;
SHV=BIL held fixed). Pure computation on the existing grid -- no backtest re-run.

Cell key bit order = `F1 F2 F3 F4 F6`:
F1 = credit canary, F2 = risk-adjusted ranker (faber/rv_252d vs 13612U),
F3 = inverse-vol weighting, F4 = trend screen (faber 10mo-SMA vs abs 13612U>0),
F6 = universe (0 = HAA-set, 1 = CPM-set).

cfg2 = `11110` = all four mechanisms ON, HAA universe.
CLEAN: Sharpe 0.958, Calmar 0.635, MaxDD -15.69%.
HAA baseline (`00000`): Sharpe 0.867, Calmar 0.639, MaxDD -14.68%.
cfg2 barely beats HAA on Sharpe and is WORSE on Calmar and MaxDD.

## 1. Conditional main effect of each mechanism (within universe)

Effect = mean(metric | factor ON) - mean(metric | factor OFF), computed separately
within the 16 HAA-universe cells and the 16 CPM-universe cells. `d` = CPM-effect - HAA-effect
(the complementarity / universe-conditioning term). Higher = better for Sharpe/Calmar;
for MaxDD, positive = shallower (better) drawdown.

### CLEAN (2008-05..2026-05)

| Mechanism | metric | HAA-univ effect | CPM-univ effect | d (CPM - HAA) |
|---|---|---|---|---|
| F1 canary | Sharpe | +0.0109 | +0.0404 | +0.0295 |
| F2 ranker | Sharpe | +0.0525 | +0.0744 | +0.0219 |
| F3 weight | Sharpe | +0.0352 | +0.0243 | -0.0109 |
| F4 screen | Sharpe | **-0.0049** | +0.0113 | +0.0163 |
| F1 canary | Calmar | +0.0637 | +0.0917 | +0.0280 |
| F2 ranker | Calmar | **-0.0184** | +0.1390 | +0.1574 |
| F3 weight | Calmar | +0.0355 | +0.0029 | -0.0326 |
| F4 screen | Calmar | **-0.0951** | +0.0123 | +0.1074 |
| F1 canary | MaxDD | +0.0026 | +0.0000 | -0.0026 |
| F2 ranker | MaxDD | **-0.0064** | +0.0176 | +0.0240 |
| F3 weight | MaxDD | +0.0112 | +0.0023 | -0.0089 |
| F4 screen | MaxDD | **-0.0203** | -0.0001 | +0.0202 |

### EXT (1999-03..2026-05)

| Mechanism | metric | HAA-univ effect | CPM-univ effect | d (CPM - HAA) |
|---|---|---|---|---|
| F1 canary | Sharpe | +0.0202 | +0.0463 | +0.0261 |
| F2 ranker | Sharpe | +0.0241 | +0.0289 | +0.0047 |
| F3 weight | Sharpe | +0.0246 | +0.0149 | -0.0098 |
| F4 screen | Sharpe | **-0.0239** | +0.0046 | +0.0285 |
| F1 canary | Calmar | +0.0607 | +0.0012 | -0.0595 |
| F2 ranker | Calmar | **-0.0573** | +0.0392 | +0.0965 |
| F3 weight | Calmar | +0.0145 | +0.0244 | +0.0098 |
| F4 screen | Calmar | **-0.0782** | +0.0039 | +0.0821 |
| F1 canary | MaxDD | -0.0031 | -0.0216 | -0.0185 |
| F2 ranker | MaxDD | **-0.0050** | +0.0115 | +0.0165 |
| F3 weight | MaxDD | +0.0100 | +0.0099 | -0.0001 |
| F4 screen | MaxDD | **-0.0129** | +0.0001 | +0.0130 |

Bold = net-negative on the HAA universe.

## 2. Net-negative-on-HAA mechanisms (drawdown axis)

Two mechanisms are net-NEGATIVE on the HAA universe, both on the exact axis where cfg2
underperforms (Calmar / MaxDD):

- **F4 trend screen (faber 10mo-SMA)** -- the dominant dragger.
  HAA-univ Calmar effect -0.0951 (CLEAN) / -0.0782 (EXT); MaxDD effect -0.0203 / -0.0129
  (i.e. it DEEPENS drawdown by ~2pp). On the CPM universe the same screen is ~neutral
  (Calmar +0.012, MaxDD ~0.000). This is the F4xF6 complementarity:
  grid interaction `F4xF6` Calmar = +0.0537 (CLEAN), +0.0410 (EXT).

- **F2 risk-adjusted ranker (faber/rv_252d)** -- secondary dragger.
  HAA-univ Calmar effect -0.0184 (CLEAN) / -0.0573 (EXT); MaxDD -0.0064 / -0.0050.
  On the CPM universe it FLIPS strongly positive (Calmar +0.139 / +0.039).
  F2xF6 Calmar interaction = +0.0787 (CLEAN), +0.0483 (EXT) -- the single largest
  positive two-way interaction in the grid.

F1 (canary) and F3 (inverse-vol) are positive or neutral on the HAA universe on the
drawdown axis; they are not the problem.

### The screen is the headline reason cfg2's drawdown is bad

cfg2 build path (CLEAN), adding mechanisms in order F1, F2, F3, F4:

| config | step | Calmar | MaxDD | Sharpe |
|---|---|---|---|---|
| 00000 | HAA baseline | 0.639 | -14.68% | 0.867 |
| 10000 | +F1 canary | 0.769 | -13.35% | 0.893 |
| 11000 | +F2 ranker | 0.709 | -14.12% | 0.905 |
| 11100 | +F3 weight | **0.762** | **-12.97%** | 0.958 |
| 11110 | +F4 screen = cfg2 | 0.635 | -15.69% | 0.958 |

Without the trend screen, "CPM mechanics on HAA universe" (`11100`) has Calmar 0.762 and
MaxDD -12.97% -- clearly BETTER than HAA on both. Adding F4 alone (`11100`->`11110`):
Calmar 0.762 -> 0.635 (-0.127), MaxDD -12.97% -> -15.69% (-2.72pp), Sharpe unchanged (0.958).
The faber SMA screen single-handedly turns a drawdown-improving stack into one that is
worse than HAA on drawdown.

## 3. Robustness (within-subset pairs, CLEAN)

F4 screen, all 8 HAA-univ OFF->ON pairs (others fixed) -- MaxDD deepens in EVERY pair:

| pair (F4 off->on) | Calmar | MaxDD |
|---|---|---|
| 00000->00010 | 0.639->0.588 | -14.68%->-15.61% |
| 00100->00110 | 0.688->0.609 | -12.97%->-14.64% |
| 01000->01010 | 0.621->0.561 | -14.90%->-16.63% |
| 01100->01110 | 0.708->0.598 | -12.97%->-15.69% |
| 10000->10010 | 0.769->0.639 | -13.35%->-15.61% |
| 10100->10110 | 0.751->0.657 | -12.97%->-14.64% |
| 11000->11010 | 0.709->0.599 | -14.12%->-16.63% |
| 11100->11110 | 0.762->0.635 | -12.97%->-15.69% |

8/8 pairs: deeper MaxDD, lower Calmar. The F4-on-HAA drag is robust, not a single cell.

F2 ranker is less robust: 6/8 pairs worse Calmar, but 2 improve (00100->01100 +0.020,
10100->11100 +0.011 -- both equal-weight, screen-OFF). So the F2 drag is real on average
but flips in some equal-weight subsets; treat F2 as a softer/secondary effect than F4.

## 4. Economic mechanism (why the screen hurts on HAA but not CPM)

Signature of the F4 drag on the HAA universe: **vol roughly flat (+0.0002), CAGR roughly
flat (-0.0004), but MaxDD ~2pp deeper.** That is NOT the profile of de-risking (which would
cut vol and CAGR). It is the profile of mis-timed switching / whipsaw: the SMA screen does
not push the book to cash on the HAA set, it changes WHICH asset is held at trend turning
points, and on the HAA universe it tends to drop assets that subsequently recover and/or
rotate into the wrong defensive asset right into the drawdown.

Why HAA universe is vulnerable to this and CPM is not:
- HAA's native screen is absolute momentum `13612U>0` (a blended 1/3/6/12-month return
  filter). HAA's universe (SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT) is broad/foreign/
  bond-heavy and flatter-trending; for these assets the 10-month SMA is a noisier, more
  lagging single-horizon signal than the 13612U blend, so swapping to the SMA adds whipsaw
  without adding protection -- it removes assets HAA's 13612U would have kept and re-adds
  them late, deepening the path drawdown.
- The CPM universe (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC) is higher-beta/more cleanly
  trending; on those names the 10-month SMA and the faber/rv ranker are co-designed and
  fire cleanly, so F4 is neutral-to-positive and F2 turns strongly positive (Calmar +0.139).
  The mechanism stack was tuned for that universe, hence the F2xF6 and F4xF6 complementarity.

Same logic for F2: the risk-adjusted ranker (return / 252d realized vol) tilts toward
low-vol assets; on the bond/foreign-heavy HAA set that over-weights already-defensive
sleeves and slightly worsens crisis-path drawdown (HAA Calmar -0.018 CLEAN / -0.057 EXT),
whereas on the CPM set the same vol-scaling sharpens selection among trending risk assets
(Calmar +0.139 CLEAN).

Caveat on the economics: holdings/monthly data are not in the grid JSON, so the
whipsaw/wrong-defensive-asset story is INFERRED from the metric signature (flat vol+CAGR,
deeper MaxDD, consistent across all 8 pairs), not confirmed by inspecting monthly weights.
Confirming it directly would need the monthly holdings/returns path (a re-run), which was
out of scope here.

## Verdict

The "machinery is weak off the CPM universe" headline is driven primarily by the
**F4 faber 10mo-SMA trend screen**, with the **F2 risk-adjusted ranker** as a secondary
contributor -- both on the drawdown axis.

- F4 on HAA universe: Calmar -0.095 (CLEAN) / -0.078 (EXT), MaxDD ~2pp deeper; robust 8/8.
- F2 on HAA universe: Calmar -0.018 (CLEAN) / -0.057 (EXT); softer (6/8).
- Both flip positive on the CPM universe (F4xF6 Calmar +0.054, F2xF6 Calmar +0.079 CLEAN),
  i.e. they are universe-complementary mechanisms, not standalone improvements.

Concrete size of the drag: dropping just F4 from cfg2 (`11110`->`11100`) restores
Calmar 0.635 -> 0.762 and MaxDD -15.69% -> -12.97% (a 2.72pp drawdown improvement) with no
Sharpe loss. So cfg2's sub-HAA drawdown is essentially entirely the trend-screen change
applied to the wrong universe.

Economic reason: the SMA screen and vol-scaled ranker are tuned for the high-beta,
cleanly-trending CPM universe; on HAA's flatter, bond/foreign-heavy universe they whipsaw
(swap out assets 13612U would keep, tilt into already-defensive sleeves) and deepen the
crisis path without cutting vol -- adding turnover/timing risk instead of protection.

## Honesty / limitations
- Conditional in-sample decomposition on a single historical path; one realization.
- Main effects are subset means; F2 in particular flips sign within equal-weight subsets,
  so its drag is not universal. F4's MaxDD drag IS consistent (8/8).
- All numbers are exact from `cpm_haa_benchmark_ladder.json`.
- Economic mechanism is inferred from metric signatures, not from inspected holdings
  (holdings/monthly path not present in the grid JSON; would require a re-run to confirm).
