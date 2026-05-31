# CPM Full-Factorial Interaction Grid (80 cells)

Role: analyst (read-only research; no production/memo edits, no commit).
Script: `research/cpm_grid_interaction_findings.py` -> `cpm_grid_interaction_findings.json` (full 80-cell grid).
Reuses the OFAT harness engine (`cpm_robust_param_sweep.py`: `cpm_weights_param` / `run_series` / `metr`).

## Setup

- Convention: mooex (T+1 MOO exact), 10 bps/side, monthly month-end signal.
- Windows: clean 2008-05-30..2026-05-22 (18y, headline); ext 1999-03-10..2026-05-22 (cheap, included in json).
- Grid (full Cartesian = 4 x 5 x 2 x 2 = 80):
  - Top-K {3,4,5,6} x momentum {faber_voladj,13612U,12m,6m,3m} x cov/vol lookback {252,504} x weighting {invvol,equal}.
- All other knobs at production: canary HYG-OR-TIP, safe SHV/IEF, strict-K partial-safe, vol cap, positive-trend screen.
- Caveat: under weighting=equal the cov/vol lookback is unused (only inv-vol consumes it), so the 252/504 cells are numerically identical there (40 distinct configs, reported as 80-cell Cartesian).

## ANCHOR GATE -- PASS

Cell {K=4, faber_voladj, lookback=504, invvol} reproduces EXACTLY:
clean Sharpe **1.1910** / MaxDD **-12.67%** / Calmar **1.0615** (expected 1.1910 / -0.1267 / 1.0615). Analysis proceeded only after this passed.

## 1. Joint distribution (clean)

| Metric | median | IQR (25-75) | min | max | mean+/-sd |
|---|---|---|---|---|---|
| Sharpe | 0.9414 | 0.9215 - 0.9817 | 0.8255 | 1.1910 | 0.957 +/- 0.078 |
| Calmar | 0.7295 | 0.5783 - 0.8451 | 0.4397 | 1.0615 | 0.726 +/- 0.151 |

- Sharpe > 1.0: **17/80 (21%)**; Sharpe > 1.1: **4/80 (5%)**.
- Calmar > 1.0: **4/80 (5%)**; Calmar > 1.1: **0/80**.
- Tight central mass (IQR width ~0.06 Sharpe) far below baseline -> the bulk of the grid is mediocre; high scores are rare.

## 2. Extremes (full knob combos)

- LOWEST Sharpe: **K3/6m/252/invvol = 0.8255** (Calmar 0.4533, DD -22.5%).
- HIGHEST Sharpe: **K4/faber_voladj/504/invvol = 1.1910** (= baseline).
- LOWEST Calmar: **K6/12m/252/invvol = 0.4397** (Sharpe 0.8702, DD -21.2%).
- HIGHEST Calmar: **K4/faber_voladj/504/invvol = 1.0615** (= baseline).

## 3. Worst vs best overall

- WORST: short-horizon raw momentum at the K extremes -- **6m @ K3** and **12m @ K6** (Sharpe ~0.83-0.87, Calmar 0.44-0.51, DD -21% to -22.5%). Raw 6m/12m rankers at extreme cardinality are the toxic region.
- BEST: **faber_voladj @ K4, invvol** (1.1910). The entire top-4 by Sharpe are K4/faber_voladj cells (1.1317-1.1910); the K4-5/faber/invvol ridge = {1.0673, 1.0901, 1.1658, 1.1910}.

## 4. Baseline placement -- LITERAL ARGMAX

- Production cell is the **#1 of 80** on both Sharpe and Calmar: percentile **100.0**, `is_literal_max=True`, **0 cells beat it**.
- Plateau width is razor-thin: **1** cell within 0.02 Sharpe (itself), **2** within 0.05, **4** within 0.10.
- Selection-on-peak bias = baseline Sharpe minus grid median = **1.1910 - 0.9414 = +0.2495**. Gap to 2nd-best cell (K4/faber/252/invvol) = **+0.0252**.

## 5. Plateaus vs cliffs + interactions OFAT could not see

Main effects (marginal mean Sharpe): momentum dominates -- faber_voladj **1.032** > 13612U 0.999 > 12m 0.937 > 3m 0.919 > 6m 0.900. K: K4 **1.010** > K5 0.976 > K6 0.934 > K3 0.910. invvol 0.966 > equal 0.949 (+0.017). lookback 504 0.962 > 252 0.953 (+0.010).

Cliffs from the baseline (single-knob, ~0.24-0.26 Sharpe drops):

- momentum axis: faber 1.191 -> **6m 0.933 (-0.258)** / 12m at K4 0.992; raw rankers cliff.
- K axis: K4 1.191 -> **K3/faber/504/invvol 0.947 (-0.244)**.

Key interactions (invisible to OFAT, which varied K only under faber and momentum only under K4):

- **faber's edge is conditional on K=4.** K x momentum mean-Sharpe table:
  - faber: K3 0.936, **K4 1.155**, K5 1.049, K6 0.987 -- a sharp ridge at K4.
  - At K3, faber (0.936) is actually BELOW 13612U (0.958). So "faber is the best ranker" is FALSE at K3. OFAT tested momentum only at K4 (faber's best slot) and concluded faber globally superior; the grid shows the superiority is K-dependent.
- **"K=4 is best" is also not universal.** It holds for faber (K4=1.155) and 13612U (K4=1.065), but for 3m the order flips (K6 0.938 > K4 0.921) and for 6m K4 is mid-pack. K-ordering depends on the ranker -- a pure interaction term.
- **equal-weight neither rescues nor ruins.** invvol >= equal in every momentum bucket but only mildly (delta +0.004 to +0.042, largest for faber). Weighting is a small monotone effect, not a regime switch; it does not save a bad ranker or break a good one.
- lookback 504 > 252 is negligible everywhere except at the peak itself (K4/faber: 1.1658 -> 1.1910, +0.0252).

## 6. VERDICT -- fragile peak (overfit flag)

The baseline is **the literal argmax of the 80-cell grid**, not a broad plateau: percentile 100, only itself within 0.02 Sharpe, surrounded by ~0.24-0.26 Sharpe cliffs on both the momentum and K axes. Selection-on-peak inflation vs grid median = **+0.2495 Sharpe** (and +0.0252 even vs the 2nd-best cell). Raise an overfit flag on the headline 1.1910.

Honest counterweight (keep proportionate): the *direction* is robust -- the faber + K4-5 + invvol family is consistently top in BOTH clean and ext windows (ext: K4/faber/504/invvol = 1.2142, also top), and 13612U@K4 is a solid backup. So the chosen *region* is genuinely better, but the exact cell sits on the peak of that region; the last ~0.025-0.06 Sharpe (504-vs-252, invvol-vs-equal at the optimum) is the part most exposed to selection bias. Report 1.1910 as a peak estimate, not a robust central tendency; a region-median (faber family) of ~1.02 is the more defensible expectation.
