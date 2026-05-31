# CPM factor stability across subperiod halves -- findings

Role: analyst (read-only re production; writes `research/` only; no production/memo edits; no commit). Throwaway harness in `research/`.

Scripts: `research/cpm_factor_stability_halves.py` (reuses `cpm_wf` + `run_cell` from `research/cpm_factorial_iv4_6factor.py`) -> `research/cpm_factor_stability_halves.json`.

## Question

The memo splits the clean window into 2008-16 (Sharpe ~1.00, includes the GFC) and 2017-26 (~1.38, a trending-asset tailwind). Two subperiods is thin and factor contributions may be regime-concentrated. Specifically test: (1) is the canary's benefit concentrated in the GFC half and ~absent/negative in 2017-26; (2) does the ranker edge survive in 2017-26 specifically, or was it earned mainly in 2008-16; (3) which of the other factors (U,S,W,P) are regime-robust vs regime-concentrated.

## Method

Reuse the EXACT 6-factor CPM factorial harness whose all-ON cell reproduces production `cpm_live.compute_target_weights`. Run the 2^6 = 64 cells ONCE over the EXT panel via the shared `_segment_returns_conv` harness (realistic T+1 MOO exact `mooex`, post-cost 10 bps/side, cov tail(504), CPM has no vol gate), then slice each cell's daily return series into the two halves and recompute metrics. Two contribution lenses per factor per half:

- **At-production marginal** = metric(all-ON) - metric(all-ON with that one factor toggled OFF), holding every other factor at production. This is exactly "CPM with X vs without X, holding else at production".
- **Background-averaged main effect** = mean on-minus-off over all 2^5 = 32 backgrounds, as a robustness cross-check. SIGN-FLIP = the on-minus-off delta changes sign across backgrounds (effect is interaction-dependent, not a stable independent contribution).

Factor map (off = AAA baseline / on = production):

| factor | OFF (baseline) | ON (production) |
|---|---|---|
| **C** canary | TIP-only (13612U(TIP)>0) | HYG-OR-TIP any-positive |
| **U** universe | AAA SPY-set (7) | CPM 8-asset (QQQ/SPHQ...) |
| **R** ranker | plain 12m momentum | vol-adjusted Faber (faber / rv_252d) |
| **S** screen | hold top-K any sign | positive-trend only |
| **W** weight | equal-weight | inverse-vol |
| **P** partial-safe | fully invested | risky_frac = min(breadth,4)/4, remainder to safe |

## Anchor + per-half endpoints (production all-ON CPM, mooex, post-cost)

Anchor gate: full clean all-ON Sharpe = 1.1910 (target 1.191) -> PASS.

| window | dates | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|
| FULL | 2008-05-30..2026-05-22 | 1.1910 | 13.44% | -12.67% | 1.0615 |
| H1_2008_2016 | 2008-05-30..2016-12-31 | 0.9970 | 11.19% | -9.83% | 1.1384 |
| H2_2017_2026 | 2017-01-01..2026-05-22 | 1.3753 | 15.53% | -12.67% | 1.2262 |

The two halves reproduce the memo's regime story: H1 (GFC) materially lower Sharpe than H2 (trending tailwind). This is the backdrop against which factor contributions are read.

## Per-half factor-contribution table (at-production marginal, holding else at production)

Each row: toggle ONE factor off from full production CPM, in each half. dSharpe = production minus (production-with-that-factor-off). Positive = the production setting helps in that half.

| factor | H1 2008-16 dSharpe | H2 2017-26 dSharpe | H1 dCalmar | H2 dCalmar | H1 dMaxDD(pp) | H2 dMaxDD(pp) |
|---|---:|---:|---:|---:|---:|---:|
| **C** | +0.1516 | -0.0758 | +0.2475 | +0.0144 | +0.00 | +0.00 |
| **U** | +0.2533 | +0.0954 | +0.4415 | +0.0977 | +1.35 | -0.92 |
| **R** | +0.3010 | +0.1081 | +0.6690 | +0.1337 | +6.55 | +1.06 |
| **S** | +0.0432 | -0.0140 | +0.3741 | +0.0661 | +4.39 | +1.34 |
| **W** | +0.0873 | +0.0247 | +0.3190 | +0.0025 | +3.22 | +0.08 |
| **P** | +0.0680 | +0.0193 | +0.2941 | -0.0374 | +2.83 | +0.00 |

## Background-averaged main effect per half (cross-check; dSharpe)

Mean on-minus-off over all 32 backgrounds. SIGN-FLIP = direction not robust across backgrounds.

| factor | H1 dSharpe | H1 flip | H2 dSharpe | H2 flip | H1 dCalmar | H2 dCalmar |
|---|---:|---|---:|---|---:|---:|
| **C** | +0.1333 |  | -0.0595 | FLIP | +0.1395 | +0.0039 |
| **U** | +0.1391 | FLIP | +0.1576 |  | +0.1059 | +0.3390 |
| **R** | +0.1778 | FLIP | +0.1507 |  | +0.2072 | +0.1673 |
| **S** | -0.1033 | FLIP | -0.0105 | FLIP | -0.0486 | +0.0837 |
| **W** | +0.0187 | FLIP | +0.0380 |  | +0.0490 | +0.0619 |
| **P** | +0.0215 |  | +0.0049 | FLIP | +0.0434 | +0.0077 |

## Stability verdict

Reading rule: a factor is **regime-robust** only if it is positive in BOTH halves AND the two
lenses (at-production marginal and background-averaged main effect) agree in sign; it is
**regime-concentrated** if its benefit lives almost entirely in one half or the lenses disagree.

### Direct answers to the brief

**1. Canary (C) -- CRITIQUE CONFIRMED. The canary's value is GFC-concentrated and turns slightly
negative post-2016.** At-production marginal dSharpe: H1 (2008-16) **+0.1516**, H2 (2017-26)
**-0.0758**. The background-averaged main effect agrees: H1 +0.1333, H2 **-0.0595 (SIGN-FLIP)**.
Both lenses say the same thing -- the HYG-OR-TIP canary helps in the GFC half and is a small drag
in the trending half. Its Calmar lift is +0.2475 in H1 but only +0.0144 in H2, and at the
production background it does not move MaxDD in either half (0.00 pp) because the other
protections (S, P, safe leg) already cap the tail. The canary is a **regime-concentrated
crisis-insurance factor**: it earns its keep in the GFC half and is a slight performance tax in
the trending half -- exactly as the critique predicted.

**2. Ranker (R) -- EDGE SURVIVES post-2016.** At-production marginal dSharpe: H1 **+0.3010**, H2
**+0.1081** -- positive and the single largest Sharpe contributor in BOTH halves. Background-
averaged main effect agrees: H1 +0.1778, H2 +0.1507. Calmar: H1 +0.669, H2 +0.134 (largest in
both). The vol-adjusted Faber ranker earned MORE in the GFC half (~3x the H2 marginal) but its
edge clearly persists in 2017-26 -- it is not a 2008-16 artifact. Verdict: **regime-robust, edge
holds post-2016** (larger in the GFC half, but materially positive in both).

**3. Other factors (U, S, W, P):**

- **U (universe) -- regime-robust.** dSharpe H1 +0.2533, H2 +0.0954; main effect H1 +0.139, H2
  +0.158 (if anything STRONGER post-2016 on the background-averaged lens, consistent with the
  tech/quality tailwind). Positive in both halves on both lenses. Small MaxDD cost in H2
  (-0.92 pp) from the growthier universe; immaterial.
- **W (inverse-vol weighting) -- regime-robust but small.** dSharpe H1 +0.0873, H2 +0.0247; main
  effect H1 +0.019, H2 +0.038. Positive in both halves on both lenses; magnitude small.
- **S (positive-trend screen) -- interaction-dependent, DD value GFC-concentrated.** Sharpe is
  near-zero and lens-inconsistent (at-prod +0.043 H1 / -0.014 H2; main effect -0.103 H1 / -0.011
  H2, SIGN-FLIP both halves) -- not a clean Sharpe contributor. Its real value is drawdown:
  Calmar +0.374 H1 / +0.066 H2 and MaxDD +4.39 pp H1 / +1.34 pp H2, both clearly concentrated in
  the GFC half. Regime-concentrated (DD protection, GFC-weighted).
- **P (partial-safe) -- small, GFC-weighted, mostly a robustness choice.** dSharpe H1 +0.068, H2
  +0.019; Calmar H1 +0.294, H2 -0.037. Modest positive in H1, near-zero/slightly negative in H2.
  Concentrated in the GFC half; not a post-2016 return driver.

### Summary classification

| factor | classification | H1 dSharpe | H2 dSharpe | read |
|---|---|---:|---:|---|
| **R** ranker | **regime-robust** | +0.301 | +0.108 | largest in both halves; edge survives post-2016 |
| **U** universe | **regime-robust** | +0.253 | +0.095 | positive both; bkgd-avg if anything stronger in H2 |
| **W** inverse-vol | regime-robust (small) | +0.087 | +0.025 | small positive both halves, both lenses |
| **C** canary | **regime-concentrated (GFC)** | +0.152 | -0.076 | positive H1, NEGATIVE H2 on both lenses -- crisis insurance |
| **S** screen | regime-concentrated (DD, GFC) | +0.043 | -0.014 | Sharpe unstable; DD/Calmar value GFC-weighted |
| **P** partial-safe | regime-concentrated (GFC) | +0.068 | +0.019 | small, GFC-weighted robustness factor |

### Bottom line for forward reliability

The **return engine that survives the trending regime is the ranker (R) plus the universe (U)** --
both are positive in both halves on both lenses, and the universe's background-averaged edge is
if anything stronger post-2016. **Inverse-vol weighting (W)** is a small, stable positive. The
**protective stack -- canary (C), positive-trend screen (S), partial-safe (P) -- is
GFC-concentrated**: it carried the 2008-16 half (the canary in particular flips to a small drag
post-2016). This is not a flaw -- crisis-insurance factors are SUPPOSED to be quiet in calm
regimes -- but the memo should not credit the canary (or P, or S's Sharpe) with the strong
2017-26 Sharpe. Forward reliability of the headline Sharpe rests primarily on R and U continuing
to work; the protective factors are a tail hedge whose value will show up only in the next
GFC-like regime, and should be justified as insurance, not as a 2017-26 return source.

## Caveats / confidence

- all-ON cell reproduces the task anchor (full clean Sharpe 1.1910 vs 1.191). Execution is byte-identical across all 64 cells (shared harness, single EXT run sliced per window).
- **Each half is ~8-9 years of monthly rebalances; per-half Sharpe CIs are wide (order ~0.4-0.6). Per-factor per-half deltas are directional, not statistically significant on their own. The robust read is the SIGN and whether it agrees across the two lenses (at-production marginal vs background-averaged main effect), not the magnitude.**
- At-production marginal isolates the factor at the production background (most decision-relevant); the background-averaged main effect guards against that single background being unrepresentative. Where they agree in sign, confidence is higher.
- P (partial-safe) is inert when S is off (breadth==4); its main effect is diluted across the S-off half of the cube. Read P together with S.
- Two halves is exactly the thin split the brief flags; this analysis quantifies the concentration but cannot manufacture more regimes. Confidence: high on direction/sign agreement, moderate on magnitudes.
