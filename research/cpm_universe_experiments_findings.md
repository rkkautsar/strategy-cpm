# CPM Universe Add/Swap/Remove Experiments vs Production

Analyst, read-only re production. No production files touched. No commit.
Single in-sample evaluation. Universe is the dominant edge lever (per HAA
decomposition) and the easiest to overfit; results below are decision-lens
clean-window point estimates, NOT adoption recommendations.

## Question

Holding ALL non-universe CPM machinery fixed (rank = m_faber / rv_252;
screen = m_faber > 0; top-4; inverse-vol cov-252 weights; HYG-or-TIP
any-positive 13612U canary; best-of-safe {SHV, IEF} by 13612U; partial-safe
breadth scaling; both-252 lookbacks), does any universe add/swap/remove
variant beat production CPM?

## Method

- Engine: `cpm_live` production functions (faber_sma_xs, sig_13612U, best_safe,
  inv_vol_weights) wrapped in a generic `cpm_variant_wf(close, sd, universe)`
  that is gated to equal `compute_target_weights` exactly when universe = CPM.
- Execution: mooex T+1 MOO realistic (prev basket earns overnight
  close[T] -> open[af]; new basket earns intraday open[af] -> close[af],
  compounded), 10 bps/side, real cached yfinance opens
  (`/tmp/cpm_open_cache`, includes IWM/VEA/VWO/SPY/IEF).
- Windows: CLEAN = 2008-05-30 .. 2026-05-22 (decision lens); EXT = 1999-03-10 ..
  2026-05-22 (proxy-stitched pre-inception tail).
- Crisis MaxDD: GFC (2007-10..2009-06), COVID (2020-02..2020-04),
  2022 (2022-01..2022-10), 2025-tariff (2025-02..2025-05-22).
- Bootstrap: paired block bootstrap (B=5000, block=21 trading days) on the
  marginal (variant - prod) over CLEAN, run on any variant beating prod on
  BOTH Sharpe and Calmar, plus a targeted MaxDD-marginal bootstrap on the
  Treasury-in / gold-out variants (the drawdown-relevant cases).
- TOP_K held FIXED at 4 for all variants (per spec "top-4 held at full CPM"),
  including 9-asset (+IEF/+IWM) and 7-asset (-GLD) universes. This is a
  deliberate held-constant choice, not ceil(N/2).

## Reproduction gate (PASS)

- Weight-by-weight match of `cpm_variant_wf(CPM)` vs `compute_target_weights`:
  0 mismatch months over the full signal set.
- Production CLEAN anchor reproduced EXACTLY:
  Sharpe 1.1658 / MaxDD -12.97% / Calmar 1.0137.

## Results (CLEAN, decision lens)

| Variant | Sharpe | Calmar | Martin | MaxDD | vs prod |
|---|---|---|---|---|---|
| PROD (CPM) | 1.1658 | 1.0137 | 3.6907 | -12.97% | - |
| 1. +IEF (offensive) | 1.1076 | 0.9598 | 3.3519 | -11.97% | worse (better DD pt-est) |
| 2. +IWM (US small) | 1.0722 | 0.8825 | 3.0235 | -14.22% | worse |
| 3. -GLD | 1.0404 | 0.8222 | 3.0319 | -14.45% | worse |
| 4. EEM -> VWO | 1.1212 | 0.9588 | 3.4337 | -13.02% | wash/slightly worse |
| 5. EFA -> VEA | 1.1594 | 0.9370 | 3.5162 | -14.03% | wash on Sharpe, worse DD |
| 6. QQQ -> SPY | 1.1215 | 0.9034 | 3.2079 | -13.68% | worse |
| 7a. cheap-ETF (VWO+VEA) | 1.1143 | 0.8852 | 3.2766 | -14.08% | worse |
| 7b. HAA-leaning | 1.0342 | 0.6950 | 2.8962 | -15.69% | clearly worse |
| 7c. +IEF -GLD | 1.0645 | 0.8626 | 3.1933 | -12.73% | worse (better DD pt-est) |

EXT window (proxy tail, secondary): same ordering, prod best on Sharpe (1.2004)
and Martin; -GLD and +IEF-GLD show the lowest EXT MaxDD (-14.50%) but at
materially lower Sharpe.

## Per-crisis MaxDD (%)

| Variant | GFC | COVID | 2022 | 2025-tariff |
|---|---|---|---|---|
| PROD (CPM) | -11.88 | -10.50 | -8.32 | -12.97 |
| 1. +IEF | -11.27 | -8.42 | -8.32 | **-8.09** |
| 2. +IWM | -13.49 | -10.50 | -8.32 | -13.16 |
| 3. -GLD | -11.27 | **-12.54** | -8.32 | **-14.45** |
| 4. EEM->VWO | -11.91 | -10.50 | -8.32 | -13.02 |
| 5. EFA->VEA | -11.88 | -10.50 | -8.32 | -14.03 |
| 6. QQQ->SPY | -11.63 | -8.97 | -7.21 | -13.68 |
| 7a. VWO+VEA | -11.69 | -10.50 | -8.32 | -14.08 |
| 7b. HAA-leaning | -13.82 | -7.11 | -7.21 | -12.25 |
| 7c. +IEF -GLD | -12.37 | -7.77 | -8.32 | **-10.07** |

The prod CLEAN MaxDD (-12.97%) is the 2025-tariff drawdown. Treasury-in
variants (+IEF, +IEF-GLD) cut that episode substantially; -GLD deepens COVID and
2025-tariff.

## Selection frequency of added offensive assets

Over 291 risk-on months (full signal set):
- +IEF: IEF picked as a top-4 risky holding in 129 / 291 risk-on months
  (44.3% of risk-on, 39.4% of all). IEF binds frequently and competes for risky
  slots; when picked it also remains the safe-leg candidate, so risk-off and
  partial-safe remainder can stack additional IEF.
- +IWM: IWM picked in 103 / 291 (35.4% of risk-on). Binds regularly but is a
  worse risk-adjusted holding than the factor/international/diversifier set it
  displaces.
- +IEF-GLD: IEF picked in 143 / 291 (49.1%) -- higher than +IEF alone because
  removing GLD opens a diversifier slot IEF fills.

These additions are NOT inert: they actively bind and displace stronger risky
picks, which is the mechanism behind their Sharpe/Calmar degradation.

## Bootstrap (discipline)

No variant beats prod on BOTH Sharpe and Calmar (CLEAN), so the
Sharpe-and-Calmar marginal bootstrap was not triggered for any variant.

Targeted MaxDD-marginal paired block bootstrap (CLEAN, B=5000, block=21),
marginal = variant_dd - prod_dd (positive = shallower/better drawdown):

| Variant | DD marginal | 95% CI | p(improve) |
|---|---|---|---|
| 1. +IEF | +1.08 pp | [-2.95, +5.85] pp | 0.698 |
| 7c. +IEF -GLD | -0.03 pp | [-6.08, +5.98] pp | 0.498 |
| 3. -GLD | -2.09 pp | [-8.36, +3.12] pp | 0.219 |

All three CIs straddle 0. The striking +IEF 2025-tariff drawdown improvement is
NOT statistically distinguishable from noise across the full CLEAN window; the
-GLD drawdown deterioration is directional but also within noise.

## Per-variant verdict

1. +IEF (offensive): WORSE on Sharpe/Calmar/Martin. Lower-return, lower-risk
   profile (CLEAN MaxDD -11.97% < prod, and -8.09% in 2025-tariff), but the DD
   gain is within bootstrap noise and comes with a real Sharpe cost. Note the
   safe/offensive double-role: IEF can be a risky pick AND the safe leg
   simultaneously, stacking exposure. Interesting but not an upgrade.
2. +IWM (US small): WORSE across the board, deepens GFC DD. No case.
3. -GLD: WORSE (Sharpe 1.04). Deepens COVID and 2025-tariff drawdowns
   (point estimate); confirms GLD contributes to the diversifier crisis tail.
   The DD deterioration is within noise statistically but consistently directional
   and paired with a clear Sharpe loss -- do NOT remove gold.
4. EEM -> VWO: WASH / slightly worse (Sharpe 1.1212 vs 1.1658, Calmar 0.9588,
   MaxDD essentially unchanged -13.02%). The cheaper/broader EM swap is close to
   free on risk but does not improve anything in-sample.
5. EFA -> VEA: WASH on Sharpe (1.1594), but worse Calmar and deeper MaxDD
   (-14.03%). Not free -- the developed-intl swap costs drawdown here.
6. QQQ -> SPY: WORSE (Sharpe -0.044, Calmar -0.110). De-tilt reconfirmed
   negative on both-252 mooex, but the magnitude is milder than the prior
   A2 estimate (~-0.18 Sharpe); convention/window differences likely explain
   the gap. Still a net negative.
7a. cheap-ETF (VWO+VEA): WORSE (stacked drag of both swaps; deepest-ish MaxDD
   -14.08%). The two cheap swaps are not jointly free in-sample.
7b. HAA-leaning: CLEARLY WORSE (Sharpe 1.0342, Calmar 0.6950, MaxDD -15.69%).
   Confirms the gradient: moving the universe toward HAA degrades CPM, consistent
   with the universe being the dominant CPM edge.
7c. +IEF -GLD: WORSE on Sharpe/Calmar; best 2025-tariff/COVID DD point
   estimates among Treasury variants, but DD marginal is ~0 (pure noise) and
   Sharpe cost is real. Not an upgrade.

## OOS / walk-forward recommendation

None of the variants merit adoption on this single in-sample point.
- No variant is an in-sample winner (none beats prod on Sharpe AND Calmar), so
  there is no positive signal to validate OOS.
- The only genuinely interesting effect is the +IEF / +IEF-GLD recent-crisis
  drawdown reduction, which the bootstrap shows is within noise. If drawdown in
  rate-shock regimes (2025-tariff style) is a priority, a +IEF (or partial-IEF
  diversifier) variant could be carried into a walk-forward / OOS study focused
  specifically on drawdown and conditioned on rate regime -- but only as a
  risk-management experiment, NOT as a Sharpe upgrade, and not before
  walk-forward confirms the DD effect is stable rather than a 2025-specific
  artifact.

## Caveats and confidence

- Single in-sample evaluation; universe changes are high overfit risk. None of
  these point estimates should be read as an upgrade without walk-forward/OOS.
- mooex T+1 MOO uses real opens where available; pre-ETF-inception months
  (VWO 2005-03, VEA 2007-07, IWM 2000-05) fall back to close-to-close on the
  rebal day and use proxy-stitched closes in EXT -- EXT numbers are
  lower-confidence than CLEAN for the swap variants.
- 2025-tariff crisis MaxDD window ends at the EVAL_END pin (2026-05-22) clean
  cutoff; it is the binding CLEAN drawdown for prod.
- TOP_K fixed at 4 even for 9-asset universes is a held-constant choice; a
  ceil(N/2)=5 cap for +IEF/+IWM would be a different (untested) configuration.
- Confidence: HIGH on the verdicts (gate exact, anchor exact, effects
  consistent CLEAN/EXT). HIGH that no variant is an in-sample upgrade. MEDIUM on
  the "+IEF helps recent-crisis DD" being real (point estimate strong, bootstrap
  inconclusive).

## Artifacts

- Harness: `research/cpm_universe_experiments.py`
- DD bootstrap: `research/cpm_universe_dd_bootstrap.py`
- Data: `research/cpm_universe_experiments.json`,
  `research/cpm_universe_dd_bootstrap.json`
- Run: `.venv/bin/python research/cpm_universe_experiments.py` then
  `.venv/bin/python research/cpm_universe_dd_bootstrap.py`
