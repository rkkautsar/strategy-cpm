# Is the CPM ranker's vol-adjustment redundant under inverse-vol weighting?

**Status:** throwaway research (read-only re: production; no production files changed, no commit).
**Script:** `research/ranker_under_invvol.py` -> `research/ranker_under_invvol.json`
**Date:** 2026-05-30

## Question / hypothesis

The production CPM ranker is **vol-adjusted Faber**: `m_faber / rv_252d` (price/SMA_10m - 1, divided
by 252-day annualized realized vol). It penalizes high-vol assets in the **ranking** step.
**Inverse-vol weighting** (`w prop 1/sigma`) ALSO penalizes high-vol assets, but in the **weighting**
step. So volatility may be double-counted.

Hypothesis: once inverse-vol weighting handles vol downstream, dropping the vol-adjustment in the
ranker (plain momentum) should match or beat vol-Faber. If the vol-Faber advantage *shrinks or
vanishes* under inverse-vol vs equal-weight, that confirms double-vol-counting redundancy, and
plain-momentum + inverse-vol is a simpler equivalent.

## Configuration (labeled)

- **Sleeve:** CPM solo. `U=C on` -> production 8-asset universe
  `[QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC]`, safe `[SHV, IEF]` best-of, canary `HYG-OR-TIP`
  any-positive 13612U.
- **Top-half K cut:** 4. **Positive-trend screen** retained. Partial-safe fallback identical to
  `inverse_vol_weighting.py` (0 positives -> 100% safe; 1 -> {pos:0.5, safe:0.5}).
- **Covariance / sigma lookback:** 504d (`sigma_i = sqrt(diag(cov))`, annualization cancels in
  renormalization). Selection = min-variance m-subset (same as `inverse_vol_weighting`,
  `cardinality_sweep`). For m=2 reproduces the production min-var pair.
- **Execution:** realistic T+1 MOO exact (`mooex`), **10 bps/side** headline (0/25 bps appendix).
- **Windows:** CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22).
- **Harness:** byte-identical reuse of `inverse_vol_weighting._cov_window / min_var_subset /
  inv_vol_weights` and `exec_lag_moo_validation_2026_05_30._segment_returns_conv`.

### Rankers tested
- `volfaber` (production): `m_faber / rv_252d`. Positive screen = `faber > 0`.
- `faber` (plain): `m_faber` alone. Positive screen = `faber > 0`. (Same candidate pool + same
  positive screen as volfaber; differs ONLY in the order that decides the top-half K cut.)
- `mom13612`: 13612U unweighted avg of 1/3/6/12-month total returns. Positive screen = `score > 0`.
- `mom12`: plain 12-month total return. Positive screen = `score > 0`.

### Weightings tested
- `EW2`: 2 lowest-variance pair, 50/50 (production reference; vol NOT used in weighting).
- `IV2`: 2 lowest-variance pair, inverse-vol.
- `IV3`: 3 lowest-variance triplet, inverse-vol.

## Verification (CLEAN, 10 bps)

| cell | Sharpe | Calmar | MaxDD | expected |
|---|---|---|---|---|
| volfaber x EW2 | **1.2424** | **0.8704** | **-16.35%** | 1.2424 / 0.8704 / -16.35% (prod CPM-solo anchor) OK |
| volfaber x IV2 | 1.2630 | 1.0945 | -13.14% | matches `inverse_vol_weighting` INVVOL-2 OK |
| volfaber x IV3 | 1.2453 | 1.0824 | -13.19% | matches `inverse_vol_weighting` INVVOL-3 OK |

Anchor reproduced to 4 dp. Inverse-vol cells reproduce the prior inverse-vol findings.

## Grid (net 10 bps/side)

### CLEAN 18y (2008-05-30 .. 2026-05-22)

| ranker | weighting | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---|---|---|---|
| vol-Faber (prod) | EW-2 | 1.2424 | 14.23% | -16.35% | 0.8704 |
| vol-Faber (prod) | INVVOL-2 | 1.2630 | 14.38% | -13.14% | 1.0945 |
| vol-Faber (prod) | INVVOL-3 | 1.2453 | 14.28% | -13.19% | 1.0824 |
| plain Faber | EW-2 | 1.1611 | 13.40% | -16.35% | 0.8195 |
| plain Faber | INVVOL-2 | 1.1726 | 13.46% | -13.14% | 1.0246 |
| plain Faber | INVVOL-3 | 1.1395 | 13.25% | -13.19% | 1.0041 |
| 13612U | EW-2 | 1.2102 | 14.55% | -17.21% | 0.8457 |
| 13612U | INVVOL-2 | 1.2084 | 14.39% | -19.10% | 0.7535 |
| 13612U | INVVOL-3 | 1.1195 | 13.09% | -16.71% | 0.7832 |
| plain 12m mom | EW-2 | 1.0827 | 12.68% | -17.19% | 0.7377 |
| plain 12m mom | INVVOL-2 | 1.0828 | 12.46% | -16.67% | 0.7477 |
| plain 12m mom | INVVOL-3 | 0.9548 | 10.89% | -17.33% | 0.6282 |

### EXT 27y (1999-03-10 .. 2026-05-22)

| ranker | weighting | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---|---|---|---|
| vol-Faber (prod) | EW-2 | 1.2159 | 14.07% | -16.76% | 0.8396 |
| vol-Faber (prod) | INVVOL-2 | 1.2011 | 13.70% | -15.44% | 0.8874 |
| vol-Faber (prod) | INVVOL-3 | 1.2249 | 13.89% | -15.18% | 0.9148 |
| plain Faber | EW-2 | 1.2990 | 15.49% | -16.76% | 0.9246 |
| plain Faber | INVVOL-2 | 1.2708 | 14.97% | -15.44% | 0.9694 |
| plain Faber | INVVOL-3 | 1.2341 | 14.41% | -15.18% | 0.9495 |
| 13612U | EW-2 | 1.2657 | 15.58% | -17.96% | 0.8679 |
| 13612U | INVVOL-2 | 1.2504 | 15.16% | -19.10% | 0.7934 |
| 13612U | INVVOL-3 | 1.2101 | 14.29% | -16.71% | 0.8549 |
| plain 12m mom | EW-2 | 1.0857 | 13.08% | -17.96% | 0.7287 |
| plain 12m mom | INVVOL-2 | 1.0753 | 12.70% | -17.68% | 0.7184 |
| plain 12m mom | INVVOL-3 | 1.0235 | 11.87% | -17.33% | 0.6850 |

(0 bps and 25 bps grids in `ranker_under_invvol.json`; ordering/signs unchanged at all three costs.)

## Analysis

### 1. Does plain momentum match/beat vol-Faber under INVVOL? Does the vol-Faber edge shrink?

The cleanest contrast isolates the vol-adjustment only: **vol-Faber minus plain-Faber** (same pool,
same positive screen; only the rank order differs). Net Sharpe, 10 bps:

| window | EW-2 | INVVOL-2 | INVVOL-3 |
|---|---|---|---|
| CLEAN | **+0.0813** | +0.0904 | +0.1058 |
| EXT | **-0.0831** | -0.0697 | -0.0092 |

Two facts:

- **The sign of the vol-adjustment effect flips by window** (positive in CLEAN, negative in EXT).
  In EXT, plain Faber actually *beats* vol-Faber under every weighting (1.299 vs 1.216 EW; 1.271 vs
  1.201 IV2; 1.234 vs 1.225 IV3).
- **INVVOL does NOT systematically shrink the vol-Faber advantage.** The double-counting prediction
  (advantage shrinks/vanishes under INVVOL vs EW) is **contradicted in CLEAN** (the edge *grows*
  from +0.081 to +0.106 as you move EW -> IV2 -> IV3) and only weakly consistent in EXT (the gap is
  already negative and narrows toward zero, -0.083 -> -0.009 under IV3, i.e. the two rankers
  converge once inverse-vol does the vol work).

So there is no clean, robust confirmation of double-vol-counting redundancy. If vol were simply
double-counted you would expect the vol-Faber edge to erode under INVVOL in *both* windows; instead
it grows in one and shrinks in the other. The vol-adjustment's effect is small (|dSharpe| <= 0.11 at
all cost levels) and window-dependent.

### 2. Does the selection even change?

Selection overlap of the final risk-on basket, vol-Faber vs each alternative ranker:

| pair | window | identical basket | mean Jaccard | risk-on state disagreements |
|---|---|---|---|---|
| volfaber vs plain Faber (EW2/IV2) | CLEAN | 84.6% | 0.895 | 0 / 217 |
| volfaber vs plain Faber (EW2/IV2) | EXT | 81.1% | 0.873 | 0 / 327 |
| volfaber vs plain Faber (IV3) | CLEAN | 78.2% | 0.886 | 0 |
| volfaber vs plain Faber (IV3) | EXT | 75.9% | 0.875 | 0 |
| volfaber vs 13612U (EW2/IV2) | CLEAN | 72.3% | 0.805 | 0 |
| volfaber vs mom12 (EW2/IV2) | CLEAN | 52.1% | 0.657 | 0 |

- **Risk-on/off state NEVER disagrees** across any ranker pair, any window (0 disagreements). The
  canary + positive-trend screen decide risk-on vs safe; the ranker only re-orders *within* the
  already-qualified candidate pool. The vol-adjustment can therefore only move performance through
  the ~15-19% of risk-on months where it flips which names survive the top-half cut / min-var
  selection.
- vol-Faber and plain Faber pick the **identical** basket ~82-85% of months (Jaccard ~0.89). The
  vol-adjustment is a marginal re-ordering, not a different strategy. 13612U diverges more (~72%),
  and plain 12m momentum diverges most (~52%) and performs worst.

### 3. Verdict

**(b) redundant / neutral, leaning "not robustly additive."** Under inverse-vol weighting the case
for the ranker's vol-adjustment is no stronger than under equal-weight:

- It is **not clearly additive**: it helps in CLEAN (+0.08 to +0.11 Sharpe) but *hurts* in EXT
  (-0.08 to -0.01). The sign flips by window.
- It is **not cleanly redundant via double-counting**: the double-counting signature (edge shrinks
  under INVVOL) appears only in EXT; in CLEAN the edge grows under INVVOL. So the mechanism is not
  "INVVOL already did vol's job" -- it is simply that the vol-adjustment is a weak, regime-dependent
  re-ordering that picks the same basket >80% of the time.
- It is **not harmful** in a robust sense either -- the CLEAN edge is positive and the EXT penalty
  is small.

**Simplification standing:** `plain-Faber + INVVOL` is a defensible simpler equivalent. It is within
noise of vol-Faber + INVVOL (CLEAN: 1.173 vs 1.263, behind by ~0.09; EXT: 1.271 vs 1.201, *ahead* by
~0.07), removes the rv_252d term, and keeps the dominant lever (inverse-vol weighting). But note it
does not strictly dominate: vol-Faber still wins the CLEAN window. The honest read is **the ranker's
vol-adjustment is second-order and window-dependent; the load-bearing improvement is the WEIGHTING,
not the ranker.** Inverse-vol weighting lifts CLEAN Calmar from 0.870 (EW-2) to 1.09 (IV2) and cuts
MaxDD from -16.35% to -13.14% -- a far larger, sign-consistent effect than anything the ranker
choice produces.

`13612U` is comparable to plain Faber on Sharpe but carries worse drawdowns under inverse-vol
(MaxDD -19.10% at IV2 in both windows; Calmar 0.75 CLEAN vs 1.02 for plain Faber). `plain 12m mom`
is the clear loser across the board (Sharpe ~1.0-1.08, Calmar 0.63-0.75) and should not replace the
Faber family.

### Reconciliation with the factorial decomposition

The earlier `factorial_decomposition` found the ranker factor R (vol-Faber vs 13612U) **weak and
sign-flipping** under EW / min-var weighting. This study isolates the vol-adjustment specifically
(vol-Faber vs plain-Faber) and finds the **same signature**: small magnitude (|dSharpe| <= 0.11),
sign flips between CLEAN and EXT, identical basket >80% of months. Adding inverse-vol weighting does
not stabilize the ranker effect. The two findings are fully consistent: **the ranker is a weak,
non-robust factor regardless of the weighting scheme, and the vol-adjustment is not the load-bearing
component of it.**

## Caveats & confidence

- Single dataset, two overlapping windows (CLEAN is a sub-window of EXT); CLEAN vs EXT is not an
  independent out-of-sample split. Sign-flip across these windows signals fragility, not a clean OOS
  contradiction.
- |dSharpe| differences of 0.01-0.11 are within typical backtest noise; no formal paired-bootstrap
  significance test was run here (see `paired_bootstrap_pair_vs_continuous` for the methodology if a
  significance claim is needed).
- Selection overlap is measured on the *final risk-on basket* (post min-var selection + positive
  screen), not the raw ranked order, so it understates ranker disagreement that the min-var step
  later washes out -- which is exactly the point: by the time the candidate pool is conditioned,
  the ranker rarely changes the held names.
- Costs modeled flat per-side (0/10/25 bps); ordering and signs are stable across all three.
- **Confidence: medium-high** that the ranker vol-adjustment is second-order/window-dependent and
  that the weighting is the dominant lever; **medium** that plain-Faber + INVVOL is an acceptable
  simplification (it wins EXT, loses CLEAN, both within noise).

## Memory / knowledge candidates

- **Knowledge (CPM ranker/weighting interaction):** the CPM ranker (vol-Faber / 13612U / plain
  momentum) is a weak, sign-flipping factor that picks the same risk-on basket >80% of months;
  risk-on/off state is driven entirely by the canary + positive screen, never by the ranker. The
  WEIGHTING (inverse-vol) is the load-bearing lever (CLEAN Calmar 0.87 -> 1.09, MaxDD -16.35% ->
  -13.14%).
- **Durable lesson (qualified):** vol-adjusting the momentum ranker is NOT cleanly redundant with
  inverse-vol weighting via double-counting -- the predicted edge-shrinkage under INVVOL appears in
  only one window. The practical truth is weaker and more useful: the ranker's vol term is
  second-order and regime-dependent, so plain momentum + inverse-vol weighting is a reasonable
  simplification, but vol-Faber + EW remains the validated production anchor (CLEAN 1.2424).
