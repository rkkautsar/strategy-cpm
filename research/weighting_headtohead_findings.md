# CPM weighting head-to-head: is the quadratic min-var solver justified?

Throwaway research (research/ scratch). Read-only re production; no production
files changed, no commit.

## Question

For the CPM sleeve top-K=4 trend-qualified menu, is a full quadratic
min-variance solver (continuous min-var, SLSQP) needed, or does a simpler
scheme (inverse-vol / risk parity) match or beat it -- especially on the
DD-aware objective (Calmar / MaxDD)? No incumbent weighting; choosing
production.

## Config / window / execution / method (labeled)

- Sleeve: CPM, U=R=C on (production universe / ranker / canary).
- Selection: IDENTICAL across all schemes. K=4 top-half, vol-adjusted Faber
  ranker, positive-trend screen. Only the WEIGHTING of the top-K positives
  changes.
- Covariance lookback: 504 trading days (~2y).
- Execution: T+1 MOO exact (`mooex`), 10 bps/side (gross = 0 bps also reported).
- Windows: CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 ..).
- Schemes (all over the same top-K=4 positive set):
  - CONT  = continuous min-variance, FULL covariance (SLSQP quadratic). Optimizer.
  - IV4   = inverse-vol, w_i prop 1/sigma_i (diagonal only, NO correlations).
            This is the prior INVVOL-4 cell. == naive risk parity.
  - ERC   = equal-risk-contribution risk parity, FULL covariance (SLSQP on
            squared pairwise risk-contribution differences, long-only).
  - EW4   = equal-weight 1/N over the top-K positives (reference).
- Naive risk parity == inverse-vol: when correlations are ignored, equal risk
  contribution reduces to w_i prop 1/sigma_i. So IV4 IS naive risk parity; the
  distinct full-cov risk-parity scheme is ERC.
- Bootstrap: PAIRED stationary block bootstrap, B=2000, block=21, seed=42, same
  block index applied to both series each draw (matches
  bootstrap_ci_2026_05_28 / paired_bootstrap_pair_vs_continuous semantics).
- Harness: research/weighting_headtohead.py reuses inverse_vol_weighting (exact
  CONT + IV4 paths), paired_bootstrap_pair_vs_continuous primitives,
  exec_lag_moo_validation_2026_05_30 segment-returns, cpm_live selection.

## Verification (anchors reproduced exactly)

- CONT, K=4, 504d, CLEAN, 10 bps: Sharpe 1.2935 / MaxDD -15.15% / Calmar 0.9618
  -- matches the clean anchor 1.2935 / -15.15% / 0.9618.
- IV4 (= INVVOL-4), CLEAN, 10 bps: Sharpe 1.1491 / MaxDD -12.67% / Calmar 1.0614
  -- matches prior inverse_vol_weighting.json INVVOL-4 numbers.

## 1. Full metrics table

### CLEAN 18y -- net 10 bps/side

| scheme | full cov? | Sharpe | CAGR | Vol | MaxDD | Calmar | avg maxW | eff N |
|---|---|---|---|---|---|---|---|---|
| CONT continuous min-var | yes | 1.2935 | 14.57% | 11.03% | -15.15% | 0.9618 | 0.678 | 1.92 |
| IV4 inverse-vol (vols only) | no | 1.1491 | 13.44% | 11.61% | -12.67% | 1.0614 | 0.416 | 3.36 |
| ERC risk-parity | yes | 1.1723 | 13.50% | 11.40% | -12.59% | 1.0722 | 0.455 | 3.21 |
| EW4 1/N (reference) | no | 1.0875 | 13.28% | 12.20% | -16.86% | 0.7878 | 0.363 | 3.48 |

### CLEAN 18y -- gross 0 bps/side

| scheme | Sharpe | MaxDD | Calmar |
|---|---|---|---|
| CONT | 1.3517 | -14.51% | 1.0554 |
| IV4 | 1.1954 | -12.50% | 1.1247 |
| ERC | 1.2222 | -12.24% | 1.1558 |
| EW4 | 1.1303 | -16.64% | 0.8342 |

### EXT 27y -- net 10 bps/side

| scheme | full cov? | Sharpe | CAGR | Vol | MaxDD | Calmar | avg maxW | eff N |
|---|---|---|---|---|---|---|---|---|
| CONT continuous min-var | yes | 1.2091 | 13.27% | 10.79% | -15.15% | 0.8760 | 0.648 | 2.03 |
| IV4 inverse-vol (vols only) | no | 1.1878 | 13.85% | 11.48% | -15.93% | 0.8698 | 0.413 | 3.35 |
| ERC risk-parity | yes | 1.1816 | 13.45% | 11.21% | -15.63% | 0.8607 | 0.450 | 3.21 |
| EW4 1/N (reference) | no | 1.1567 | 14.27% | 12.17% | -20.18% | 0.7069 | 0.350 | 3.50 |

### EXT 27y -- gross 0 bps/side

| scheme | Sharpe | MaxDD | Calmar |
|---|---|---|---|
| CONT | 1.2719 | -15.02% | 0.9352 |
| IV4 | 1.2366 | -15.85% | 0.9150 |
| ERC | 1.2344 | -15.54% | 0.9093 |
| EW4 | 1.2009 | -19.77% | 0.7533 |

Read of the table: CONT buys its Sharpe edge with CONCENTRATION -- it parks
~65-68% in the single lowest-vol asset (eff N ~2), while IV4 / ERC spread across
all four (eff N ~3.2-3.4). 1/N ignores vol entirely and is clearly worst on
MaxDD / Calmar in BOTH windows (-16.86% / -20.18%), so vol-awareness matters.
The off-diagonal CORRELATION awareness (what separates CONT/ERC from IV4) does
NOT translate into a meaningful, robust edge.

## 2. Paired block bootstrap (B=2000, block=21, seed=42; positive = continuous wins)

Daily series highly correlated (corr CONT-IV4 ~0.91, CONT-ERC ~0.94), so paired
resampling is the right test. Diff = (continuous - alternative).

### CLEAN

| comparison | metric | P(cont wins) | mean diff | 95% CI | excludes 0? |
|---|---|---|---|---|---|
| CONT vs IV4 | Sharpe | 0.923 | +0.146 | [-0.054, +0.356] | NO |
| CONT vs IV4 | MaxDD | 0.718 | +0.016 | [-0.038, +0.078] | NO |
| CONT vs IV4 | Calmar | 0.811 | +0.151 | [-0.211, +0.545] | NO |
| CONT vs ERC | Sharpe | 0.919 | +0.122 | [-0.044, +0.298] | NO |
| CONT vs ERC | MaxDD | 0.667 | +0.009 | [-0.037, +0.062] | NO |
| CONT vs ERC | Calmar | 0.785 | +0.117 | [-0.192, +0.463] | NO |

### EXT

| comparison | metric | P(cont wins) | mean diff | 95% CI | excludes 0? |
|---|---|---|---|---|---|
| CONT vs IV4 | Sharpe | 0.611 | +0.021 | [-0.141, +0.176] | NO |
| CONT vs IV4 | MaxDD | 0.632 | +0.009 | [-0.046, +0.070] | NO |
| CONT vs IV4 | Calmar | 0.515 | +0.003 | [-0.265, +0.273] | NO |
| CONT vs ERC | Sharpe | 0.664 | +0.028 | [-0.101, +0.155] | NO |
| CONT vs ERC | MaxDD | 0.591 | +0.005 | [-0.042, +0.054] | NO |
| CONT vs ERC | Calmar | 0.546 | +0.010 | [-0.219, +0.243] | NO |

Answer to the key question: NO comparison excludes zero, on any metric, in
either window. Continuous's Sharpe edge over inverse-vol / ERC is NOT
statistically robust -- it is within noise, like everything else in this
strategy. The CLEAN Sharpe lean (P ~0.92) is suggestive but the CI straddles
zero; in EXT it collapses to a near coin-flip (P 0.61-0.66).

Caveat on bootstrap MaxDD: block bootstrap reshuffles the crisis sequence, so
the resampled MaxDD distribution understates path-dependent tail differences.
The realized (point/exact) MaxDD comparison in Section 3 is the reliable DD read.

## 3. DD objective: does inverse-vol or ERC BEAT continuous on Calmar / MaxDD?

Using exact realized MaxDD / Calmar (not the path-shuffled bootstrap):

### CLEAN (net 10 bps): YES, both beat continuous.

| | CONT | IV4 | ERC |
|---|---|---|---|
| MaxDD | -15.15% | -12.67% | -12.59% |
| Calmar | 0.9618 | 1.0614 | 1.0722 |

- IV4 vs CONT: MaxDD shallower by +2.48 pp; Calmar higher by +0.0996.
- ERC vs CONT: MaxDD shallower by +2.56 pp; Calmar higher by +0.1104 (best DD-adjusted).

### EXT (net 10 bps): NO, continuous edges (mildly).

| | CONT | IV4 | ERC |
|---|---|---|---|
| MaxDD | -15.15% | -15.93% | -15.63% |
| Calmar | 0.8760 | 0.8698 | 0.8607 |

- CONT vs IV4: MaxDD shallower by 0.78 pp; Calmar higher by 0.0062.
- CONT vs ERC: MaxDD shallower by 0.48 pp; Calmar higher by 0.0153.

Significance of the DD edge: paired bootstrap CIs on MaxDD and Calmar all
straddle zero in both windows -- so even the CLEAN DD advantage of IV4 / ERC is
not statistically significant by this test (and the bootstrap is conservative
for tail DD). The DD ranking is therefore window-dependent and within noise:
simple schemes win the DD objective in the modern (post-2008) regime, continuous
edges it over the full 27y by a hair. The one robust DD result is negative:
correlation-blind 1/N is clearly worst on DD in both windows.

## 4. Simplicity / robustness

### Inputs required

| scheme | needs full covariance (off-diagonal correlations)? | needs solver? |
|---|---|---|
| CONT | yes (full cov) | yes (SLSQP) |
| IV4 inverse-vol | NO -- only the vols (diagonal) | no |
| ERC | yes (full cov) | yes (SLSQP) |
| EW4 1/N | no -- nothing estimated | no |

Off-diagonal correlations are the noisiest, least-stable part of a sample
covariance estimate. Inverse-vol avoids them entirely and uses only the (much
more stable) per-asset vols.

### Estimation sensitivity -- cov lookback 504 -> 480 / 528, mean L1 weight drift (EXT sigs)

| scheme | full cov? | avg mean L1 drift | max L1 (480) | max L1 (528) |
|---|---|---|---|---|
| CONT continuous min-var | yes | 0.02264 | 0.303 | 0.227 |
| IV4 inverse-vol | no | 0.00785 | 0.216 | 0.236 |
| ERC risk-parity | yes | 0.00783 | 0.105 | 0.090 |
| EW4 1/N | no | 0.00000 | 0.000 | 0.000 |

As predicted, CONTINUOUS min-var is the most estimation-sensitive: ~2.9x the
mean weight drift of inverse-vol / ERC under a small lookback perturbation, and
it can swing a single weight by up to 0.30. Inverse-vol and ERC are roughly tied
on mean drift (~0.0078); ERC even has the smallest MAX swing (0.10 vs 0.22),
because ERC is a well-conditioned interior solution while min-var chases
low-vol corners. 1/N is trivially invariant.

So: min-var's better full-sample Sharpe comes from aggressive low-vol
concentration, and that concentration is exactly what makes it (a) deeper in
drawdown in the modern regime and (b) ~3x more sensitive to the cov estimate.

## 5. Verdict

The quadratic min-var solver is NOT justified for production.

- Sharpe: its only edge over inverse-vol / ERC is within noise -- no bootstrap
  CI excludes zero, and the edge nearly vanishes over the full 27y (P 0.61).
- DD-aware objective (the stated production objective): inverse-vol and ERC BEAT
  continuous on MaxDD and Calmar in the modern CLEAN window (Calmar 1.06-1.07
  vs 0.96; MaxDD ~-12.6% vs -15.2%), and only trail it by a hair over EXT. The
  DD differences are themselves within noise, but the asymmetry favors the
  simple schemes where it matters most.
- Robustness: continuous min-var is ~3x more estimation-sensitive and the most
  concentrated (eff N ~2, ~66% in one asset). It also depends on the noisiest
  estimate (off-diagonal correlations) for no significant payoff.

Recommended production weighting: INVERSE-VOL over the top-K=4 (IV4).
- No solver, no off-diagonal correlations (avoids the noisiest estimate), most
  robust on a per-input basis, DD-aware competitive-to-better, Sharpe within
  noise of the optimizer.

Where ERC sits: ERC is the strong runner-up. It is essentially tied with
inverse-vol on Sharpe and robustness, marginally best on CLEAN DD / Calmar
(1.0722), and the most stable on MAX weight swing. But it reintroduces both the
full covariance and a solver for a difference vs inverse-vol that is not
significant. Prefer ERC over inverse-vol ONLY if a full-cov risk-parity is
wanted for other reasons; otherwise inverse-vol's simplicity wins.

Do NOT use 1/N: it is correlation- AND vol-blind and is clearly the worst on the
DD objective in both windows (Calmar 0.79 / 0.71; MaxDD -16.9% / -20.2%).
Vol-awareness is the part that matters; correlation-awareness is not.

## Caveats / confidence

- Confidence MODERATE-HIGH on the central claim (min-var Sharpe edge is within
  noise; simple vol-aware schemes are competitive-to-better on DD). Anchors
  reproduce exactly; conclusion is consistent across windows and cost levels.
- DD-objective ranking is window-dependent (simple schemes win CLEAN, continuous
  edges EXT) and the DD differences are not individually significant; treat the
  DD verdict as "simple schemes at least match, and likely beat in the modern
  regime", not "strictly dominate".
- Block bootstrap on MaxDD is conservative (shuffles crisis paths); rely on the
  exact realized MaxDD/Calmar for the DD read.
- Single covariance lookback (504d) and single cost level (10 bps) for the
  headline; gross (0 bps) shown and agrees. Perturbation only +/-24 d.
- ERC solved via SLSQP on squared pairwise risk-contribution differences
  (long-only, fully invested); standard but one of several ERC formulations.

## Artifacts

- Harness: research/weighting_headtohead.py
- Results: research/weighting_headtohead.json
- Reused: research/inverse_vol_weighting.py (CONT + IV4 exact paths),
  research/paired_bootstrap_pair_vs_continuous.py (bootstrap primitives),
  research/exec_lag_moo_validation_2026_05_30.py (segment returns).

## Handoff

- Production wiring of inverse-vol weighting (if accepted) -> fixer.
- Release/decision adjudication on weighting choice -> oracle.
