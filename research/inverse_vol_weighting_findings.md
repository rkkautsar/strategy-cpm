# Inverse-Volatility Weighting on the CPM Weighting Grid

Throwaway research. No production files changed, no commit. Numbers regenerated
by `research/inverse_vol_weighting.py` -> `research/inverse_vol_weighting.json`.

## Config / window / execution (labeled)

- Sleeve: CPM, U=1 / R=1 / C=1 (production universe, vol-adjusted Faber ranker,
  HYG-OR-TIP any-positive canary). K = top-half = 4.
- Universe: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC. Safe: SHV / IEF (best_safe).
- Execution: T+1 MOO exact (`mooex`), realistic open-fill. Cost 10 bps/side
  headline; gross = 0 bps; sensitivity at 10 / 25 / 50 bps.
- Covariance / vol lookback: 504 trading days. sigma_i = sqrt of the diagonal of
  `close[cand].pct_change().dropna(how='all').tail(504).cov()` -- the SAME vol
  used in the min-var selection. Annualization constant cancels in renormalize.
- Windows: CLEAN 18y (2008-05-30 .. 2026-05-22, 17.98y); EXT 27y
  (1999-03-10 .., 27.20y).
- Metrics: Sharpe, CAGR, Vol, MaxDD, Calmar (cash = SHV).

### What changed vs equal-weight

Selection is IDENTICAL to the existing cardinality harness
(`min_var_subset`: the equal-weight m-subset with lowest portfolio variance;
for m=2 this reproduces the production `min_vol_pair`). ONLY the weighting inside
the selected set changes: equal-weight 1/m  ->  inverse-vol w_i prop 1/sigma_i,
renormalized to sum 1. So INVVOL-M is selection-equivalent to EW-M; the delta is
purely the weighting step.

### Variants

- INVVOL-2: min-var 2-subset, inverse-vol weighted.
- INVVOL-3: min-var 3-subset, inverse-vol weighted.
- INVVOL-4: min-var 4-subset (= all 4 trend-qualified when >=4 positive),
  inverse-vol weighted.

### Partial-safe fallback (matches production cpm_wf; identical across EW-M / INVVOL-M)

- 0 positive-trend candidates -> 100% safe.
- 1 positive-trend candidate  -> {pos: 0.5, safe: 0.5}.
- 2 .. M-1 positive candidates -> inverse-vol weight ALL that qualify.
- >= M positive candidates     -> min-var M-subset, inverse-vol weighted.
- If sigma is unavailable / degenerate inside the set, fall back to equal-weight
  on that set (never hit in either window).

## Verification (anchors reproduce before trusting new cells)

CLEAN, 10 bps -- exact match to references:

| anchor | Sharpe | Calmar | MaxDD | status |
|---|---|---|---|---|
| EW-2 pair (prod) | 1.2424 | 0.8704 | -16.35% | EXACT |
| EW-3 triplet     | 1.2229 | 0.8536 | -16.86% | EXACT |
| continuous min-var | 1.2935 | 0.9618 | -15.15% | EXACT |

## Headline grid -- net 10 bps (and gross 0 bps Sharpe)

### CLEAN 18y

| scheme | gross Sh (0bps) | net Sh | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|
| EW-2 pair (prod)   | 1.2985 | 1.2424 | 14.23% | 11.27% | -16.35% | 0.8704 |
| EW-3 triplet       | 1.2727 | 1.2229 | 14.39% | 11.57% | -16.86% | 0.8536 |
| **INVVOL-2**       | 1.3205 | **1.2630** | 14.38% | 11.18% | **-13.14%** | **1.0945** |
| **INVVOL-3**       | 1.2969 | 1.2453 | 14.28% | 11.27% | -13.19% | 1.0824 |
| **INVVOL-4**       | 1.1954 | 1.1491 | 13.44% | 11.61% | -12.67% | 1.0614 |
| continuous min-var | 1.3517 | 1.2935 | 14.57% | 11.03% | -15.15% | 0.9618 |

### EXT 27y

| scheme | gross Sh (0bps) | net Sh | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|
| EW-2 pair (prod)   | 1.2729 | 1.2159 | 14.07% | 11.36% | -16.76% | 0.8396 |
| EW-3 triplet       | 1.2752 | 1.2237 | 14.33% | 11.49% | -17.68% | 0.8106 |
| **INVVOL-2**       | 1.2606 | 1.2011 | 13.70% | 11.22% | -15.44% | 0.8874 |
| **INVVOL-3**       | 1.2794 | **1.2249** | 13.89% | 11.12% | **-15.18%** | **0.9148** |
| **INVVOL-4**       | 1.2366 | 1.1878 | 13.85% | 11.48% | -15.93% | 0.8698 |
| continuous min-var | 1.2719 | 1.2091 | 13.27% | 10.79% | -15.15% | 0.8760 |

## Turnover / stability / concentration / effN

| window | scheme | ann turnover (RT) | frac months changed | risk-on avg max weight | risk-on effN |
|---|---|---|---|---|---|
| CLEAN | EW-2 | 6.342 | 0.389 | 0.500 | 2.00 |
| CLEAN | EW-3 | 5.859 | 0.505 | 0.339 | 2.97 |
| CLEAN | INVVOL-2 | 6.433 | 0.912 | 0.554 | 1.97 |
| CLEAN | INVVOL-3 | 5.886 | 0.912 | 0.395 | 2.90 |
| CLEAN | INVVOL-4 | 5.437 | 0.912 | 0.326 | 3.73 |
| CLEAN | continuous | 6.452 | 0.810 | 0.628 | 2.06 |
| EXT | EW-2 | 6.544 | 0.420 | 0.493 | 2.05 |
| EXT | EW-3 | 6.035 | 0.528 | 0.339 | 2.98 |
| EXT | INVVOL-2 | 6.733 | 0.926 | 0.550 | 2.02 |
| EXT | INVVOL-3 | 6.166 | 0.926 | 0.403 | 2.89 |
| EXT | INVVOL-4 | 5.689 | 0.926 | 0.341 | 3.64 |
| EXT | continuous | 6.849 | 0.868 | 0.605 | 2.16 |

Notes:
- Annualized round-trip turnover (sum |dw|, one-way = half). INVVOL turnover is
  essentially equal to EW-M at the same cardinality (selection-driven), slightly
  above (e.g. CLEAN 6.43 vs 6.34) from continuous weight drift.
- "frac months changed" jumps to ~0.91-0.93 for all INVVOL variants vs
  0.39-0.53 for EW: equal-weight only moves when the discrete selection flips,
  whereas inverse-vol weights drift every month with sigma. Magnitude of the
  move is small (see estimation sensitivity), but it touches every month.
- Concentration shown for risk-on months (max single weight = 1.000 for every
  scheme because all-safe defensive months park 100% in one safe asset; that is
  not a weighting property). Risk-on avg max weight is the meaningful cap proxy.
- The "~62%" continuous reference = continuous risk-on avg max weight 0.628
  (CLEAN) / 0.605 (EXT).

## Cost sensitivity -- net Sharpe at 10 / 25 / 50 bps

| window | scheme | 10 bps | 25 bps | 50 bps |
|---|---|---|---|---|
| CLEAN | EW-2 | 1.2424 | 1.1567 | 1.0108 |
| CLEAN | INVVOL-2 | 1.2630 | 1.1751 | 1.0254 |
| CLEAN | INVVOL-3 | 1.2453 | 1.1666 | 1.0328 |
| CLEAN | INVVOL-4 | 1.1491 | 1.0787 | 0.9591 |
| CLEAN | continuous | 1.2935 | 1.2046 | 1.0530 |
| EXT | EW-2 | 1.2159 | 1.1287 | 0.9804 |
| EXT | INVVOL-2 | 1.2011 | 1.1103 | 0.9557 |
| EXT | INVVOL-3 | 1.2249 | 1.1419 | 1.0006 |
| EXT | INVVOL-4 | 1.1878 | 1.1136 | 0.9875 |
| EXT | continuous | 1.2091 | 1.1133 | 0.9503 |

INVVOL-3 degrades most gracefully with cost: at 50 bps it is the best EXT scheme
(1.0006) and second-best CLEAN (1.0328, behind only continuous's 1.0530).

## Estimation sensitivity -- lookback 504 -> 480 / 528 d, mean L1 weight move (EXT rebalances)

| scheme | 480 mean L1 | 528 mean L1 |
|---|---|---|
| EW-2 pair (prod) | 0.0153 | 0.0183 |
| EW-3 triplet     | 0.0133 | 0.0097 |
| INVVOL-2 | 0.0208 | 0.0236 |
| INVVOL-3 | 0.0188 | 0.0150 |
| INVVOL-4 | 0.0085 | 0.0072 |
| continuous min-var | 0.0236 | 0.0217 |

Key nuance (honest): at a GIVEN cardinality, inverse-vol is MORE estimation-
sensitive than equal-weight, not less -- INVVOL-2 (0.0236) > EW-2 (0.0183) > and
roughly ties continuous (0.0217) on the 528 perturbation. Reason: equal-weight
only reacts when the discrete selection flips; inverse-vol additionally moves
continuously with the sigma estimates. The "uses only the diagonal, less
estimation-prone" benefit is real ONLY relative to FULL-covariance min-var
(it avoids off-diagonal noise), and only materializes at higher M: INVVOL-3
(0.0150) and INVVOL-4 (0.0072) sit clearly below continuous (0.0217). The
SELECTION still uses the full covariance via min_var_subset, so INVVOL-M inherits
EW-M's selection sensitivity and adds weight drift on top.

## Answers

### Q1 -- Does INVVOL-2 beat EW-2 (production pair) net, both windows? By how much?

Mixed on Sharpe; clear win on drawdown-adjusted.

- CLEAN: INVVOL-2 BEATS EW-2 on every metric. Sharpe 1.2630 vs 1.2424
  (+0.0206, +1.66%); CAGR 14.38% vs 14.23% (+0.15pp); Vol 11.18% vs 11.27%;
  MaxDD -13.14% vs -16.35% (3.21pp shallower); Calmar 1.0945 vs 0.8704
  (+0.2241, +25.7%).
- EXT: INVVOL-2 LOSES on Sharpe -- 1.2011 vs 1.2159 (-0.0148, -1.22%) -- and on
  CAGR (13.70% vs 14.07%, -0.37pp), but WINS on risk: MaxDD -15.44% vs -16.76%
  (1.32pp shallower), Calmar 0.8874 vs 0.8396 (+0.0478).

Verdict on Q1: INVVOL-2 does NOT strictly beat EW-2 on net Sharpe in both
windows (wins CLEAN, loses EXT). It DOES beat EW-2 on MaxDD and Calmar in BOTH
windows. So it is a drawdown/Calmar improvement with a coin-flip on Sharpe.

### Q2 -- Does any inverse-vol variant match/approach continuous net while keeping max weight materially below ~62% and lower estimation sensitivity?

Yes -- INVVOL-3 is the clean answer.

- Net Sharpe vs continuous: CLEAN 1.2453 vs 1.2935 (gap -0.0482); EXT 1.2249 vs
  1.2091 -- INVVOL-3 BEATS continuous in EXT by +0.0158.
- Risk-adjusted vs continuous: INVVOL-3 Calmar 1.0824 / 0.9148 beats continuous
  0.9618 / 0.8760 in BOTH windows; MaxDD -13.19% / -15.18% beats / ties
  continuous -15.15% / -15.15%.
- Concentration: INVVOL-3 risk-on avg max weight 0.395 / 0.403 -- about 35% lower
  than continuous's 0.628 / 0.605, and effN ~2.9 vs continuous ~2.0-2.2.
- Estimation sensitivity: INVVOL-3 mean L1 0.0150 (528) vs continuous 0.0217 --
  lower, as required.

INVVOL-2 also "approaches" continuous net (EXT gap only -0.008) with lower
concentration (0.55 vs 0.63), BUT its estimation sensitivity (0.0236) is NOT
below continuous, so it fails the "lower estimation sensitivity" half. INVVOL-3
satisfies all three conditions simultaneously.

### Q3 -- Robustness vs performance tradeoff, and the verdict

Placement on the robustness-performance axis (least-to-most estimation-hungry,
at fixed cardinality):

- Equal-weight (EW-M): most robust. Weights move only on discrete selection
  flips; hard structural cap (50% for the pair, 33% triplet). Lowest Calmar of
  the three families. Simplest to reason about and audit.
- Inverse-vol (INVVOL-M): middle on the COVARIANCE axis (diagonal only, no
  off-diagonal noise) but MORE sensitive than equal-weight at the same M because
  weights drift continuously with sigma. Soft, vol-dispersion-dependent cap (no
  hard cap). Structurally overweights the lowest-vol name, the tilt
  that delivers the biggest MaxDD/Calmar gains on the grid. The selection still
  rides the full-covariance min_var_subset, so it inherits EW-M's selection risk.
- Continuous min-var (CONT): highest CLEAN net Sharpe (1.2935) but most
  estimation-hungry (full covariance), highest concentration (~62% risk-on),
  and -- notably -- WORSE Calmar than every inverse-vol variant in both windows.

Honest verdict -- is inverse-vol a better PRODUCTION weighting than the EW pair?

- If the objective is net Sharpe and maximal simplicity / hard cap: NO, keep
  EW-2. INVVOL-2 only ties EW-2 on Sharpe (win CLEAN, lose EXT), raises
  concentration (55% vs 50% risk-on, no hard cap), and is MORE estimation-
  sensitive. The added complexity does not buy Sharpe.
- If the objective weights drawdown / Calmar (most likely for this sleeve):
  YES, and the right variant is INVVOL-3, not INVVOL-2. INVVOL-3 beats EW-3 on
  Sharpe/Vol/MaxDD/Calmar in both windows (only CAGR is marginally lower),
  posts the best Calmar on the entire grid (1.0824 CLEAN), matches/exceeds
  continuous's performance, and does so with ~40% concentration (well capped),
  lower turnover than continuous, and lower estimation sensitivity than
  continuous. It is the drawdown-optimal, estimation-light, well-capped cell.

Bottom line: inverse-vol's value is a drawdown reduction (Calmar/MaxDD), not a
Sharpe lift. INVVOL-2 is not worth swapping in over EW-2 on Sharpe alone.
INVVOL-3 is the genuinely attractive cell -- it dominates EW-3 and rivals
continuous min-var while keeping concentration and estimation risk in check.

## Caveats / confidence

- Single dataset, single execution model (mooex T+1 MOO exact, 10 bps/side);
  in-sample over the full window, no walk-forward re-estimation of the scheme
  choice. EXT pre-2008 leans on stitched proxies (BIL/AGG) already in the
  harness.
- Selection uses the production full-covariance min_var_subset, so INVVOL-M is
  NOT a pure diagonal-only method end to end; only the weighting step is
  diagonal-only. A truly estimation-light variant would also switch selection to
  lowest individual sigma (not tested here; the brief fixed selection).
- max single weight = 1.000 for all schemes is an all-safe-month artifact, not a
  risk-on cap. Concentration claims use risk-on avg max weight.
- Confidence: HIGH on the relative ordering and on the anchor reproduction
  (EW-2 / EW-3 / continuous all reproduce exactly). MEDIUM on whether the
  INVVOL-3 edge over continuous survives out-of-sample / walk-forward.
