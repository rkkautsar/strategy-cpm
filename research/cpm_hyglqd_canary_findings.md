# HYG/LQD Credit-Spread Z-Score as a CPM Canary -- Findings

MEASUREMENT ONLY. No production files edited. Engine fixed (positive-Faber + EAA vol-adj rank + K=4 + min-var pair); only the CPM canary varies. BULL sleeve fixed at production (HYG OR TIP). Blend = 60% CPM + 40% BULL.

## Verification gate

- variant-C0 vs production `run_cpm_backtest` max abs daily-return diff: `0.00e+00` (exact).
- C0 CPM standalone (clean): Sharpe 1.263 / CAGR 14.58% / vol 11.30% / MaxDD -15.41%  (target 1.263 / 14.58% / 11.30% / -15.41%).
- C0 60/40 blend (clean): Sharpe 1.347 / CAGR 13.59% / MaxDD -9.82%  (target 1.347 / 13.59% / -9.82%).
- Reproduction: CPM_ok=True, blend_ok=True.

## Data caveat

HYG live 2007-04 (VWEHX stitch pre); LQD live 2002-07 (VFICX IG corp bond fund stitch 1993-11+). HYG/LQD ratio is CLEAN post-2007-04. Pre-2007 the ratio is a mutual-fund proxy (VWEHX/VFICX 1999-2002, VWEHX/LQD 2002-2007). All Stress-window rows for Z1/Z2/Z3 are PROXY-FLAGGED (marked Stress*). Clean-window (2008-05-30+) HYG/LQD is fully live.

## CPM standalone metrics

| Variant | Window | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover |
|---|---|---|---|---|---|---|---|---|
| C0_PROD_HYGorTIP | Clean | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 314% |
| C0_PROD_HYGorTIP | Stress* | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 326% |
| C3_HYGonly | Clean | 1.318 | 1.196 | 14.57% | 10.78% | -13.12% | 1.11 | 311% |
| C3_HYGonly | Stress* | 1.286 | 1.079 | 14.28% | 10.84% | -15.87% | 0.90 | 346% |
| Z1_ratio_trend | Clean | 1.080 | 0.958 | 11.75% | 10.85% | -20.00% | 0.59 | 369% |
| Z1_ratio_trend | Stress* | 1.088 | 0.876 | 11.64% | 10.64% | -20.00% | 0.58 | 374% |
| Z2_z_gt_-1 | Clean | 0.949 | 0.836 | 11.11% | 11.86% | -34.56% | 0.32 | 347% |
| Z2_z_gt_-1 | Stress* | 1.042 | 0.843 | 12.04% | 11.55% | -34.94% | 0.34 | 370% |
| Z2_z_gt_0 | Clean | 1.090 | 0.968 | 11.81% | 10.79% | -20.00% | 0.59 | 328% |
| Z2_z_gt_0 | Stress* | 1.096 | 0.884 | 11.69% | 10.60% | -20.00% | 0.58 | 342% |
| Z3_OR_z-1 | Clean | 1.036 | 0.926 | 12.62% | 12.20% | -34.56% | 0.37 | 317% |
| Z3_OR_z-1 | Stress* | 1.122 | 0.928 | 13.37% | 11.81% | -34.94% | 0.38 | 331% |
| Z3_AND_z-1 | Clean | 1.233 | 1.106 | 13.04% | 10.39% | -11.01% | 1.18 | 342% |
| Z3_AND_z-1 | Stress* | 1.205 | 0.993 | 12.94% | 10.56% | -15.87% | 0.82 | 385% |

## 60/40 CPM+BULL blend metrics

| Variant | Window | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover |
|---|---|---|---|---|---|---|---|---|
| C0_PROD_HYGorTIP | Clean | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 | 314% |
| C0_PROD_HYGorTIP | Stress* | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 | 326% |
| C3_HYGonly | Clean | 1.376 | 1.239 | 13.58% | 9.60% | -9.82% | 1.38 | 311% |
| C3_HYGonly | Stress* | 1.327 | 1.091 | 12.80% | 9.42% | -11.79% | 1.09 | 346% |
| Z1_ratio_trend | Clean | 1.267 | 1.125 | 11.93% | 9.25% | -11.98% | 1.00 | 369% |
| Z1_ratio_trend | Stress* | 1.223 | 0.978 | 11.25% | 9.05% | -11.98% | 0.94 | 374% |
| Z2_z_gt_-1 | Clean | 1.160 | 1.024 | 11.56% | 9.86% | -21.14% | 0.55 | 347% |
| Z2_z_gt_-1 | Stress* | 1.185 | 0.950 | 11.51% | 9.58% | -21.95% | 0.52 | 370% |
| Z2_z_gt_0 | Clean | 1.276 | 1.133 | 11.97% | 9.20% | -11.98% | 1.00 | 328% |
| Z2_z_gt_0 | Stress* | 1.230 | 0.985 | 11.29% | 9.02% | -11.98% | 0.94 | 342% |
| Z3_OR_z-1 | Clean | 1.212 | 1.080 | 12.46% | 10.12% | -21.14% | 0.59 | 317% |
| Z3_OR_z-1 | Stress* | 1.235 | 1.005 | 12.30% | 9.78% | -21.95% | 0.56 | 331% |
| Z3_AND_z-1 | Clean | 1.328 | 1.186 | 12.66% | 9.32% | -9.22% | 1.37 | 342% |
| Z3_AND_z-1 | Stress* | 1.277 | 1.036 | 12.01% | 9.21% | -11.79% | 1.02 | 385% |

*Stress rows for HYG/LQD variants (Z1/Z2/Z3) are proxy-flagged pre-2007.

## Crisis sub-periods (stress panel)

Cal-return col only meaningful for full calendar years (NaN for partial windows).

| Variant | Crisis | CPM cal-ret | CPM Sharpe | CPM MaxDD | Blend Sharpe | Blend MaxDD |
|---|---|---|---|---|---|---|
| C0_PROD_HYGorTIP | 2008 GFC | nan | 0.74 | -15.91% | 0.91 | -9.99% |
| C0_PROD_HYGorTIP | 2015-16 | nan | 1.37 | -4.32% | 1.07 | -4.15% |
| C0_PROD_HYGorTIP | 2020 COVID | 0.1692 | 1.07 | -13.12% | 1.54 | -9.82% |
| C0_PROD_HYGorTIP | 2022 | 0.0749 | 0.76 | -9.60% | 0.82 | -5.84% |
| C3_HYGonly | 2008 GFC | nan | 1.42 | -6.98% | 1.35 | -6.03% |
| C3_HYGonly | 2015-16 | nan | 0.91 | -4.32% | 0.80 | -4.15% |
| C3_HYGonly | 2020 COVID | 0.1135 | 0.81 | -13.12% | 1.42 | -9.82% |
| C3_HYGonly | 2022 | 0.0245 | 0.75 | -3.20% | 0.93 | -1.94% |
| Z1_ratio_trend | 2008 GFC | nan | 0.81 | -8.97% | 0.91 | -7.01% |
| Z1_ratio_trend | 2015-16 | nan | 0.12 | -10.11% | 0.37 | -6.85% |
| Z1_ratio_trend | 2020 COVID | 0.1001 | 1.37 | -4.68% | 2.12 | -4.68% |
| Z1_ratio_trend | 2022 | -0.0607 | -0.33 | -20.00% | -0.29 | -11.98% |
| Z2_z_gt_-1 | 2008 GFC | nan | -0.11 | -34.94% | 0.21 | -21.95% |
| Z2_z_gt_-1 | 2015-16 | nan | 0.26 | -10.11% | 0.44 | -7.37% |
| Z2_z_gt_-1 | 2020 COVID | 0.0865 | 0.85 | -7.38% | 1.52 | -7.74% |
| Z2_z_gt_-1 | 2022 | -0.0607 | -0.33 | -20.00% | -0.29 | -11.98% |
| Z2_z_gt_0 | 2008 GFC | nan | 0.66 | -10.40% | 0.82 | -9.29% |
| Z2_z_gt_0 | 2015-16 | nan | 0.10 | -10.11% | 0.35 | -6.85% |
| Z2_z_gt_0 | 2020 COVID | 0.1001 | 1.37 | -4.68% | 2.12 | -4.68% |
| Z2_z_gt_0 | 2022 | -0.0617 | -0.34 | -20.00% | -0.30 | -11.98% |
| Z3_OR_z-1 | 2008 GFC | nan | 0.02 | -34.94% | 0.32 | -21.95% |
| Z3_OR_z-1 | 2015-16 | nan | 0.26 | -10.11% | 0.43 | -7.37% |
| Z3_OR_z-1 | 2020 COVID | 0.1135 | 0.81 | -13.12% | 1.42 | -9.82% |
| Z3_OR_z-1 | 2022 | -0.0607 | -0.33 | -20.00% | -0.29 | -11.98% |
| Z3_AND_z-1 | 2008 GFC | nan | 1.25 | -6.98% | 1.22 | -6.03% |
| Z3_AND_z-1 | 2015-16 | nan | 0.91 | -4.32% | 0.81 | -4.15% |
| Z3_AND_z-1 | 2020 COVID | 0.0865 | 0.85 | -7.38% | 1.52 | -7.74% |
| Z3_AND_z-1 | 2022 | 0.0245 | 0.75 | -3.20% | 0.93 | -1.94% |

## Cohort / gating diagnostics (% months gated, forward 1m EW-risky return)

Blocked = canary risk-off. bad-forward = blocked & fwd<0 (correct de-risk). false-positive = blocked & fwd>=0 (gave up upside).

| Variant | Window | %gated | n_block | blocked mean fwd | blocked %neg | allowed mean fwd | bad-fwd | false-pos |
|---|---|---|---|---|---|---|---|---|
| C0_PROD_HYGorTIP | Clean | 13.4% | 29 | -1.78% | 66% | 1.17% | 19 | 10 |
| C0_PROD_HYGorTIP | Stress* | 10.7% | 35 | -1.51% | 63% | 1.08% | 22 | 13 |
| C3_HYGonly | Clean | 19.4% | 42 | -0.60% | 55% | 1.10% | 23 | 19 |
| C3_HYGonly | Stress* | 19.0% | 62 | -0.35% | 52% | 1.08% | 32 | 30 |
| Z1_ratio_trend | Clean | 34.6% | 75 | 0.76% | 32% | 0.78% | 24 | 51 |
| Z1_ratio_trend | Stress* | 38.2% | 125 | 0.53% | 37% | 0.97% | 46 | 79 |
| Z2_z_gt_-1 | Clean | 18.9% | 41 | 1.14% | 27% | 0.69% | 11 | 30 |
| Z2_z_gt_-1 | Stress* | 20.5% | 67 | 0.39% | 37% | 0.91% | 25 | 42 |
| Z2_z_gt_0 | Clean | 38.2% | 83 | 0.87% | 31% | 0.71% | 26 | 57 |
| Z2_z_gt_0 | Stress* | 41.3% | 135 | 0.65% | 36% | 0.91% | 48 | 87 |
| Z3_OR_z-1 | Clean | 8.3% | 18 | 0.68% | 44% | 0.78% | 8 | 10 |
| Z3_OR_z-1 | Stress* | 10.7% | 35 | 0.20% | 46% | 0.88% | 16 | 19 |
| Z3_AND_z-1 | Clean | 30.0% | 65 | 0.14% | 40% | 1.04% | 26 | 39 |
| Z3_AND_z-1 | Stress* | 28.7% | 94 | -0.03% | 44% | 1.14% | 41 | 53 |

## Earliness into credit crises (first risk-off month before crisis)

Earlier (lower) month = flips defensive sooner. 'never' = stayed risk-on through window.

- **2008 GFC (off before 2008-09)**: C0_PROD_HYGorTIP=2008-09, C3_HYGonly=2007-07, Z1_ratio_trend=2007-07, Z2_z_gt_-1=2007-07, Z2_z_gt_0=2007-07, Z3_OR_z-1=2007-07, Z3_AND_z-1=2007-07
- **2015-16 credit (off before 2016-02)**: C0_PROD_HYGorTIP=2015-06, C3_HYGonly=2015-06, Z1_ratio_trend=2015-08, Z2_z_gt_-1=2015-09, Z2_z_gt_0=2015-08, Z3_OR_z-1=2015-09, Z3_AND_z-1=2015-06
- **2020 COVID (off before 2020-03)**: C0_PROD_HYGorTIP=never, C3_HYGonly=2020-03, Z1_ratio_trend=2019-10, Z2_z_gt_-1=2019-10, Z2_z_gt_0=2019-10, Z3_OR_z-1=2020-03, Z3_AND_z-1=2019-10

## Verdict

### 1. Is HYG/LQD z-score a sharper/earlier credit canary than HYG-absolute?

**Earlier: yes. Sharper: no.** The HYG/LQD ratio/z signals flip defensive sooner into
credit crises (2008: 2007-07 vs C0 2008-09; 2020: 2019-10 vs C3 2020-03), but the
earliness is mostly low-precision noise, not skill:

- They gate 2-4x more months than HYG-absolute (Z1 34.6%, Z2-z>0 38.2% vs C3 19.4%, C0 13.4%).
- Blocked months are **majority false-positives** (forward EW-risky return POSITIVE):
  Z1 blocked mean +0.76% / only 32% negative; Z2-z>0 +0.87% / 31% neg. By contrast
  HYG-only (C3) blocked months are -0.60% mean / 55% negative -- the only single-leg
  credit signal whose blocks have genuine de-risk skill (bad-forward >= false-positive).
- The noise shows up in returns: Z1/Z2/Z3-OR all crater in 2022 (CPM -20% MaxDD,
  cal-ret ~-6%) because the ratio stayed risk-off through a recovering tape, and
  Z2-z>-1 / Z3-OR miss 2008 entirely (CPM MaxDD -34.6% / -34.9%).

The 2020 "earliness" (2019-10) is itself a false early flip: COVID was a March-2020
exogenous shock; flipping off in Oct-2019 forfeited the Q4-2019 rally. HYG-absolute's
2020-03 flip is the timely one.

### 2. Does any variant match HYG-only's crisis-DD win WHILE preserving breadth (a 2nd de-risk-capable leg)?

**Yes -- Z3-AND (HYG-trend AND HYG/LQD-z>-1).** It is a genuine 2-leg credit gate with
no TIP, and it matches the crisis-DD win:

- Clean blend MaxDD **-9.22%** (beats C0 -9.82%, edges C3); 2008-GFC CPM MaxDD **-6.98%**
  (identical to HYG-only); clean CPM MaxDD -11.01% (best CPM DD of all variants).
- It is de-risk-capable: the AND requires BOTH credit legs healthy, so either leg can
  pull the gate defensive. The permissive **Z3-OR fails** (-34.6% DD) -- adding a loose
  z-leg via OR REMOVES de-risking power (the z>-1 leg keeps it risk-on through 2008).
- Cost: Z3-AND blend Sharpe **1.328** sits below both C0 (1.347) and C3 (1.376), i.e.
  ~0.02-0.05 Sharpe given up for the breadth/redundancy.

### 3. Recommendation

1. **Strongest single change remains HYG-only (C3)**: blend Sharpe 1.376 / DD -9.82% /
   Calmar 1.38 / 2008-GFC CPM DD -6.98%. Highest Sharpe AND best crisis DD. (In-sample
   winner, as flagged.)
2. **If the oracle's "2nd de-risk-capable credit leg without TIP" is the goal, use
   Z3-AND** (HYG-trend AND HYG/LQD-z>-1). It preserves breadth, matches the crisis-DD
   win, and removes TIP-dependence, at a small (~0.02-0.05) Sharpe cost vs C0/C3.
3. **Reject the pure HYG/LQD z and the OR forms** (Z1, Z2 both thresholds, Z3-OR):
   they gate on false positives, are unstable in 2022, and the OR construction is
   actively dangerous in 2008 (DD -34.6%).

**Bottom line:** the HYG/LQD z-score is an *earlier* but *noisier* credit canary; it is
not a sharper standalone replacement. Its best role is a *confirming AND-leg* (Z3-AND)
that reproduces HYG-only's crisis protection while adding a second, TIP-free,
de-risk-capable credit signal. Pure HYG-only still posts the highest Sharpe.

### Caveats / confidence

- C0 reproduces production exactly (daily-return diff 0.0; CPM 1.263/14.58%/-15.41%;
  blend 1.347/13.59%/-9.82%). High confidence in the engine and relative ordering.
- HYG/LQD ratio is fully live only post-2007-04. Clean-window (2008-05-30+) numbers are
  solid; Stress* rows pre-2007 use a VWEHX/VFICX(->LQD) mutual-fund proxy and should be
  read directionally, not precisely.
- Crisis-window earliness is sensitive to exact lookback bounds; treat month-level flip
  timing as approximate.
- All comparisons in-sample over a single history; Sharpe gaps of ~0.03-0.05 are within
  noise. The robust, repeatable result is the **DD ranking** (C3 ~ Z3-AND << C0; Z1/Z2/Z3-OR worst).
