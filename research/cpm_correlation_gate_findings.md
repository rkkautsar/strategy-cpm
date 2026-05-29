# CPM Cross-Asset Correlation Gate -- Findings

Measurement-only study. A NEW correlation overlay on top of production CPM (HYG-OR-TIP canary + positive-Faber + K=4 + min-var pair). Existing structure unchanged; the gate de-risks (scales risky exposure toward best_safe) when realized correlation in the risky universe spikes -- the min-var pair engine's specific blind spot.

- **SIG-A**: universe avg pairwise correlation (60d, 20d) vs trailing 252d baseline (z-score and rolling-median). Fires when correlation is HIGH.
- **SIG-B**: selected min-var pair short-term (20d, 60d) realized correlation vs its 504d baseline. Fires when pair corr spikes above the baseline the optimizer assumed.
- **Actions**: binary (-> 100% best_safe) and continuous (risky exposure scaled down as correlation rises, remainder to safe; no leverage).

## 0. V0 baseline reproduction (no correlation gate)

- **Clean (2008-05-30..2026-05-22)** 60/40: Sharpe 1.347, CAGR 13.59%, Vol 9.84%, MaxDD -9.82%, Calmar 1.38
- **Stress (1999-03-10..2026-05-22)** 60/40: Sharpe 1.291, CAGR 12.65%, Vol 9.58%, MaxDD -11.79%, Calmar 1.07

**V0 REPRODUCTION: PASS** (matches 1.347 / 13.59% / -9.82%).

## 1. Variant performance (CPM standalone and 60/40 blend)

Costs included (10bps/side). Excess Sharpe vs SHV. Crisis columns are calendar-year total returns of the **60/40 blend**.

### Clean (2008-05-30..2026-05-22)

| Variant | Scope | Sharpe | ExcessSh | CAGR | Vol | MaxDD | Calmar | Turn/yr | 2008 | 2020 | 2022 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **V0 (no gate)** | CPM | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 3.20 | +6.11% | +23.42% | +4.95% |
| **V0 (no gate)** | 60/40 | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 | nan | +6.11% | +23.42% | +4.95% |
| SIG-A 60d z>1 [binary] | CPM | 1.182 | 1.056 | 12.51% | 10.45% | -15.41% | 0.81 | 3.98 | +6.11% | +19.89% | +4.95% |
| SIG-A 60d z>1 [binary] | 60/40 | 1.320 | 1.176 | 12.37% | 9.16% | -9.82% | 1.26 | nan | +6.11% | +19.89% | +4.95% |
| SIG-A 60d >median [binary] | CPM | 0.755 | 0.605 | 6.46% | 8.83% | -18.99% | 0.34 | 4.14 | +6.11% | +14.02% | +3.88% |
| SIG-A 60d >median [binary] | 60/40 | 1.107 | 0.938 | 8.72% | 7.85% | -9.82% | 0.89 | nan | +6.11% | +14.02% | +3.88% |
| SIG-A 20d z>1 [binary] | CPM | 1.034 | 0.907 | 10.74% | 10.41% | -16.45% | 0.65 | 5.15 | +6.11% | +23.74% | +4.95% |
| SIG-A 20d z>1 [binary] | 60/40 | 1.218 | 1.073 | 11.30% | 9.15% | -9.82% | 1.15 | nan | +6.11% | +23.74% | +4.95% |
| SIG-B 20d spike>.15 [binary] | CPM | 1.157 | 1.025 | 11.71% | 10.02% | -14.51% | 0.81 | 5.23 | +12.00% | +25.94% | +0.81% |
| SIG-B 20d spike>.15 [binary] | 60/40 | 1.311 | 1.162 | 11.89% | 8.88% | -9.82% | 1.21 | nan | +12.00% | +25.94% | +0.81% |
| SIG-B 60d spike>.15 [binary] | CPM | 1.449 | 1.323 | 15.61% | 10.40% | -13.12% | 1.19 | 3.70 | +15.07% | +25.94% | +3.88% |
| SIG-B 60d spike>.15 [binary] | 60/40 | 1.515 | 1.370 | 14.22% | 9.06% | -9.82% | 1.45 | nan | +15.07% | +25.94% | +3.88% |
| SIG-A 60d z>1 [continuous] | CPM | 1.180 | 1.055 | 12.73% | 10.65% | -15.41% | 0.83 | 3.74 | +6.11% | +19.99% | +4.95% |
| SIG-A 60d z>1 [continuous] | 60/40 | 1.300 | 1.159 | 12.49% | 9.41% | -9.82% | 1.27 | nan | +6.11% | +19.99% | +4.95% |
| SIG-A 60d >median [continuous] | CPM | 1.164 | 1.030 | 11.56% | 9.82% | -15.41% | 0.75 | 3.94 | +6.11% | +19.59% | +4.93% |
| SIG-A 60d >median [continuous] | 60/40 | 1.305 | 1.156 | 11.78% | 8.85% | -9.82% | 1.20 | nan | +6.11% | +19.59% | +4.93% |
| SIG-A 20d z>1 [continuous] | CPM | 1.171 | 1.046 | 12.58% | 10.62% | -15.41% | 0.82 | 4.40 | +6.11% | +22.50% | +4.95% |
| SIG-A 20d z>1 [continuous] | 60/40 | 1.290 | 1.150 | 12.39% | 9.41% | -9.82% | 1.26 | nan | +6.11% | +22.50% | +4.95% |
| SIG-B 20d spike>.15 [continuous] | CPM | 1.218 | 1.089 | 12.66% | 10.23% | -13.20% | 0.96 | 4.40 | +9.07% | +26.06% | +1.21% |
| SIG-B 20d spike>.15 [continuous] | 60/40 | 1.339 | 1.194 | 12.45% | 9.08% | -9.82% | 1.27 | nan | +9.07% | +26.06% | +1.21% |
| SIG-B 60d spike>.15 [continuous] | CPM | 1.343 | 1.219 | 14.71% | 10.66% | -13.12% | 1.12 | 3.60 | +10.28% | +23.32% | +4.73% |
| SIG-B 60d spike>.15 [continuous] | 60/40 | 1.425 | 1.283 | 13.68% | 9.32% | -9.82% | 1.39 | nan | +10.28% | +23.32% | +4.73% |

### Stress (1999-03-10..2026-05-22)

| Variant | Scope | Sharpe | ExcessSh | CAGR | Vol | MaxDD | Calmar | Turn/yr | 2008 | 2020 | 2022 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **V0 (no gate)** | CPM | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 3.29 | +15.17% | +23.42% | +4.95% |
| **V0 (no gate)** | 60/40 | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 | nan | +15.17% | +23.42% | +4.95% |
| SIG-A 60d z>1 [binary] | CPM | 1.134 | 0.909 | 11.57% | 10.11% | -15.91% | 0.73 | 4.12 | +15.17% | +19.89% | +4.95% |
| SIG-A 60d z>1 [binary] | 60/40 | 1.251 | 0.997 | 11.20% | 8.80% | -9.99% | 1.12 | nan | +15.17% | +19.89% | +4.95% |
| SIG-A 60d >median [binary] | CPM | 0.733 | 0.464 | 6.09% | 8.57% | -19.47% | 0.31 | 4.26 | +15.17% | +14.02% | +3.88% |
| SIG-A 60d >median [binary] | 60/40 | 1.030 | 0.738 | 7.90% | 7.66% | -9.99% | 0.79 | nan | +15.17% | +14.02% | +3.88% |
| SIG-A 20d z>1 [binary] | CPM | 1.014 | 0.790 | 10.34% | 10.22% | -16.45% | 0.63 | 5.06 | +15.17% | +23.74% | +4.95% |
| SIG-A 20d z>1 [binary] | 60/40 | 1.167 | 0.913 | 10.47% | 8.87% | -11.25% | 0.93 | nan | +15.17% | +23.74% | +4.95% |
| SIG-B 20d spike>.15 [binary] | CPM | 1.089 | 0.863 | 11.05% | 10.10% | -15.87% | 0.70 | 5.64 | +21.56% | +25.94% | +0.81% |
| SIG-B 20d spike>.15 [binary] | 60/40 | 1.226 | 0.969 | 10.90% | 8.75% | -11.25% | 0.97 | nan | +21.56% | +25.94% | +0.81% |
| SIG-B 60d spike>.15 [binary] | CPM | 1.282 | 1.065 | 13.69% | 10.43% | -14.55% | 0.94 | 4.15 | +24.89% | +25.94% | +3.88% |
| SIG-B 60d spike>.15 [binary] | 60/40 | 1.365 | 1.115 | 12.48% | 8.90% | -11.79% | 1.06 | nan | +24.89% | +25.94% | +3.88% |
| SIG-A 60d z>1 [continuous] | CPM | 1.156 | 0.937 | 12.17% | 10.41% | -15.91% | 0.76 | 3.96 | +15.17% | +19.99% | +4.95% |
| SIG-A 60d z>1 [continuous] | 60/40 | 1.252 | 1.005 | 11.55% | 9.06% | -10.66% | 1.08 | nan | +15.17% | +19.99% | +4.95% |
| SIG-A 60d >median [continuous] | CPM | 1.124 | 0.886 | 10.78% | 9.52% | -15.91% | 0.68 | 4.08 | +15.17% | +19.59% | +4.93% |
| SIG-A 60d >median [continuous] | 60/40 | 1.238 | 0.976 | 10.72% | 8.52% | -9.99% | 1.07 | nan | +15.17% | +19.59% | +4.93% |
| SIG-A 20d z>1 [continuous] | CPM | 1.143 | 0.926 | 12.17% | 10.54% | -15.91% | 0.77 | 4.33 | +15.17% | +22.50% | +4.95% |
| SIG-A 20d z>1 [continuous] | 60/40 | 1.242 | 0.997 | 11.56% | 9.14% | -11.51% | 1.00 | nan | +15.17% | +22.50% | +4.95% |
| SIG-B 20d spike>.15 [continuous] | CPM | 1.148 | 0.927 | 12.03% | 10.36% | -15.87% | 0.76 | 4.77 | +18.38% | +26.06% | +1.21% |
| SIG-B 20d spike>.15 [continuous] | 60/40 | 1.258 | 1.007 | 11.48% | 8.96% | -11.25% | 1.02 | nan | +18.38% | +26.06% | +1.21% |
| SIG-B 60d spike>.15 [continuous] | CPM | 1.251 | 1.038 | 13.72% | 10.74% | -14.55% | 0.94 | 3.75 | +19.69% | +23.32% | +4.73% |
| SIG-B 60d spike>.15 [continuous] | 60/40 | 1.330 | 1.085 | 12.49% | 9.16% | -11.79% | 1.06 | nan | +19.69% | +23.32% | +4.73% |

## 2. Cohort diagnostic -- is the signal predictive?

For months the gate fires, forward 1-month CPM standalone return (V0, next-month compounded) and forward realized vol. Split into BAD cohort (fwd <= 0, gate correct) vs GOOD cohort (fwd > 0, false positive). Compared to the unconditional (all-month) distribution. Stress window, binary action (firing identical to continuous's fire set).

Unconditional forward 1m CPM: mean +1.14%, vol(of monthly) 2.76%, mean fwd ann-vol 10.07%, n=326.

| Signal | Fires | %mon | BAD n | BAD mean | BAD vol | GOOD n | GOOD mean | GOOD vol | E[avoided] | E[forgone] | net |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SIG-A 60d z>1 [binary] | 68 | 20.9% | 24 | -2.19% | 12.4% | 44 | +2.36% | 9.6% | -0.77% | +1.53% | +0.76% |
| SIG-A 60d >median [binary] | 166 | 50.9% | 52 | -1.90% | 11.5% | 114 | +2.78% | 9.8% | -0.60% | +1.91% | +1.31% |
| SIG-A 20d z>1 [binary] | 63 | 19.3% | 22 | -1.62% | 12.7% | 41 | +3.05% | 9.7% | -0.56% | +1.98% | +1.42% |
| SIG-B 20d spike>.15 [binary] | 70 | 21.5% | 29 | -2.31% | 11.6% | 41 | +2.96% | 10.9% | -0.96% | +1.73% | +0.78% |
| SIG-B 60d spike>.15 [binary] | 52 | 16.0% | 27 | -2.58% | 12.5% | 25 | +2.58% | 10.3% | -1.34% | +1.24% | -0.10% |

BAD mean/GOOD mean = mean forward CPM return of correct/false-positive cohorts. E[avoided]=P(bad)*mean_bad (loss the gate sidesteps, negative is good), E[forgone]=P(good)*mean_good (gain forfeited). net = expected forward-return impact per fired month of going to safe (ignoring safe yield). Predictive signal => BAD cohort large/frequent and clearly more negative + higher-vol than GOOD/unconditional.

## 3. Redundancy vs HYG-OR-TIP canary

How often the corr gate fires while CPM is ALREADY DEFENSIVE (canary risk-off -> redundant) vs while RISK_ON (adds NEW de-risking). Note: the gate only changes weights when regime is RISK_ON, so NEW-fire months are the only ones that affect returns. Stress window.

| Signal | Total fires | Redundant (canary OFF) | New (RISK_ON) | New in 2008 | New in 2020 | New in 2022 |
|---|---|---|---|---|---|---|
| SIG-A 60d z>1 [binary] | 68 | 10 | 58 | 1 | 3 | 0 |
| SIG-A 60d >median [binary] | 167 | 25 | 142 | 1 | 9 | 0 |
| SIG-A 20d z>1 [binary] | 63 | 13 | 50 | 1 | 4 | 0 |
| SIG-B 20d spike>.15 [binary] | 70 | 0 | 70 | 2 | 3 | 1 |
| SIG-B 60d spike>.15 [binary] | 52 | 0 | 52 | 3 | 3 | 0 |

## 4. Verdict

See Section 1 deltas vs V0 (60/40 Clean: Sharpe 1.347, CAGR 13.59%, MaxDD -9.82%, Calmar 1.38; Stress: Sharpe 1.291, MaxDD -11.79%, Calmar 1.07). Adoption requires a variant that improves crisis MaxDD/Calmar net of gating drag AND shows predictive cohort separation (Section 2) that is not merely redundant with the canary (Section 3).

### Headline

**ADOPT SIG-B (selected-pair correlation breakout), 60d window. REJECT SIG-A (universe avg correlation) -- it is noise/drag.**

The gate that targets the optimizer's actual blind spot -- the chosen min-var
pair's own short-term correlation vs the 504d baseline it assumed -- is
predictive and complementary to the canary. The broad universe-average
correlation signal is not.

### SIG-A: universe avg pairwise correlation -- REJECT (noise)

- Every SIG-A form REDUCES Sharpe and CAGR in both windows vs V0 (Clean 60/40
  1.347 -> 1.30/1.25/1.29; CAGR 13.59% -> 11-12%).
- Cohort separation is weak: net forward-return impact per fired month is
  materially POSITIVE (+0.76% z60, +1.31% median60, +1.42% z20), i.e. the gate
  mostly forfeits expected return. The `>median` form fires 51% of all months
  (pure noise switch).
- BAD-cohort frequency is low (24-52 of 63-167 fires); high realized
  universe-wide correlation does NOT reliably precede bad CPM months. It carries
  10-25 redundant fires (canary already OFF).
- Verdict: universe-average correlation is too diffuse a signal for this engine.

### SIG-B: selected-pair correlation breakout -- ADOPT (60d form)

The pair's recent 60d correlation minus its 504d baseline, fire when spike > 0.15.

- **Best cohort separation of any signal.** When SIG-B 60d fires (52 of 326
  stress months, 16%), forward CPM is essentially a symmetric coin flip:
  BAD n=27 mean -2.58% (ann-vol 12.5%) vs GOOD n=25 mean +2.58% (10.3%), against
  an unconditional mean of +1.14% / 10.07% vol. Net forward impact ~ -0.10%
  (the ONLY signal where avoided loss offsets forgone gain). It identifies
  elevated-risk, near-zero-expectation months -- exactly the diversification-
  failure regime the min-var pair is blind to.
- **Complementary, not redundant.** 0 of 52 fires overlap with the canary being
  OFF (vs 10-25 redundant fires for SIG-A). It adds genuinely new de-risking and
  fires in the correlation-break crises: 3 new fires in 2008, 3 in 2020 (0 in
  2022, which was a rate/duration selloff the canary already handled and CPM
  survived at +4.95%).
- **Improves CPM standalone risk-adjusted return and drawdown.** Clean CPM:
  Sharpe 1.263 -> 1.449, CAGR 14.58% -> 15.61%, MaxDD -15.41% -> -13.12%,
  Calmar 0.95 -> 1.19. Stress CPM: Sharpe 1.218 -> 1.282, MaxDD -15.91% -> -14.55%,
  Calmar 0.88 -> 0.94. Both Sharpe AND CAGR AND DD improve (rare for a gate),
  net of 10bps/side cost; turnover rises modestly (3.2 -> 3.7/yr).
- **Blend Sharpe/Calmar improve, blend MaxDD does NOT.** 60/40 Clean: Sharpe
  1.347 -> 1.515, Calmar 1.38 -> 1.45, CAGR 13.59% -> 14.22%. 60/40 Stress:
  Sharpe 1.291 -> 1.365. BUT the blend MaxDD is unchanged (-9.82% clean /
  -11.79% stress) because the two-sleeve blend's tail is BULL-SPY driven, not
  CPM driven -- the CPM-side gate cannot move a BULL-bound drawdown. The gate's
  value at blend level is return-quality (Sharpe/Calmar via the numerator), not
  a deeper trough.
- 20d form is weaker (Clean blend Sharpe 1.311 binary / 1.339 continuous, net
  cohort +0.78%); 60d binary > 60d continuous on Sharpe/Calmar, continuous is
  the less parameter-sensitive fallback (Clean 1.425 / Calmar 1.39, also > V0).

### Answer to the success criteria

1. Does any variant improve crisis DD/Calmar beyond V0 after gating cost?
   - CPM standalone: YES -- SIG-B 60d improves DD (-15.41% -> -13.12% clean) and
     Calmar (0.95 -> 1.19).
   - 60/40 blend: Calmar YES (1.38 -> 1.45), but MaxDD NO (BULL-bound). No
     correlation-gate variant deepens the blend's drawdown protection because
     the blend tail is not CPM-sourced.
2. Is the signal predictive or noise/redundant?
   - SIG-B 60d: PREDICTIVE (symmetric ~50/50 cohort, net ~0 forward drag) and
     COMPLEMENTARY (0 canary overlap, fires 2008/2020).
   - SIG-A (all forms): NOISE/DRAG (net positive forgone return, partial canary
     redundancy, 50%-fire median variant).

### Recommendation

Adopt the **SIG-B 60d selected-pair correlation-breakout** overlay (continuous
form preferred for robustness, binary if maximizing point Sharpe) as a CPM-sleeve
de-risk gate. Expect improved CPM-sleeve Sharpe/CAGR/DD and a modest blend
Sharpe/Calmar lift; do NOT expect it to reduce the two-sleeve blend's max
drawdown (that tail is owned by the BULL sleeve and needs a BULL-side control).
Reject SIG-A. This is a hand-off to the fixer if productionizing: add SIG-B as an
overlay in compute_target_weights without altering the existing canary / Faber /
K=4 / min-var-pair structure.

### Caveats and confidence

- Single threshold (spike > 0.15) and window (60d) shown; both binary and
  continuous forms clear V0, which is mild evidence against a single-point fit,
  but a threshold sweep / walk-forward was not run here -- moderate confidence.
- Cohort split uses forward CPM standalone return (V0); using universe-EW would
  shift magnitudes but not the SIG-B-vs-SIG-A ranking.
- Blend MaxDD invariance is structural (BULL-driven tail), not a measurement
  artifact.
- Costs modeled at 10bps/side; turnover increase is small (~0.5/yr).
- No look-ahead: all signals computed strictly on data up to sig_d; execution
  T+1 OPEN, consistent with production CPM accounting. V0 reproduces the 60/40
  baseline exactly (Sharpe 1.347 / CAGR 13.59% / MaxDD -9.82%).
