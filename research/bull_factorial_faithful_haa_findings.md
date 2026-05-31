# BULL Factorial with a Faithful HAA-Simple Baseline (2^2: C x V)

Read-only re production. No production/memo edits. No commit.

Script: `research/bull_factorial_faithful_haa.py`
Data:   `research/bull_factorial_faithful_haa_findings.json`
Harness: `_segment_returns_conv(..., convention="mooex")` (T+1 MOO exact),
10 bps/side, from `research/exec_lag_moo_validation_2026_05_30.py`.
Engines reused: faithful HAA-Simple logic from `/tmp/true_aaa_haa.py`;
production BULL from `bull_qqq_live.py`.

Windows:
- CLEAN: 2008-05-30 .. 2026-05-22
- EXT:   1999-03-10 .. 2026-05-22

## Design

The all-OFF baseline is the PAPER HAA-Simple (faithful). The audit found the
HAA-Simple core in our code is faithful (single-SPY, 13612U, TIP+SPY dual gate);
only the defensive pool nominally differs. SHV vs BIL are near-identical
ultra-short T-bill cash, so the safe-pool swap is a data-proxy substitution,
NOT a strategy design lever, and is held FIXED (production {SHV, IEF}, best-of
by 13612U) across all 4 cells. It is reported separately as an immateriality
check (Section 6).

Two factors (OFF = HAA-Simple value, ON = production BULL value):

- C canary: OFF = TIP-only 13612U > 0 ; ON = (HYG OR TIP) 13612U > 0
- V vol gate: OFF = none ; ON = rv_60d(SPY) < rv_252d(SPY) (annualized daily-return std)

Common to every cell (NOT a factor): SPY 13612U trend gate (> 0).
Risk-on (canary AND SPY-trend AND vol) -> 100% SPY; else best-of {SHV, IEF}.

- all-OFF (cv) == faithful HAA-Simple
- all-ON  (CV) == production BULL

## 1. Anchor Confirmation (GATE-FIRST)

| Gate | Target | Actual | Pass |
|------|--------|--------|------|
| all-OFF (cv) clean Sharpe == faithful HAA-Simple | ~0.9840 | 0.9840 | YES |
| all-OFF clean MaxDD / Calmar | -20.41% / 0.5685 | -20.41% / 0.5685 | YES |
| all-OFF ext Sharpe / Calmar | ~0.9735 / 0.5259 | 0.9735 / 0.5259 | YES |
| all-ON (CV) logic == production BULL (weight-by-weight) | 0 mismatches | 0 mismatches | YES |
| all-ON (CV) clean Sharpe (mooex) | ~1.081 | 1.0813 | YES |
| production BULL native engine (bull_qqq_live) clean Sharpe | ~1.08-1.12 | 1.1200 | YES |

Notes:
- all-OFF reproduces the audit HAA-Simple anchor to 4 dp (0.983999).
- all-ON cell is logically identical to `compute_bull_qqq_weights` (0 weight
  mismatches across all month-ends 1999-2026). Under the apples-to-apples mooex
  harness it scores 1.0813 clean; the native bull_qqq_live engine (close-to-close
  on apply_from, a ~5-10 bps/yr-optimistic approximation) scores 1.1200. The
  ~1.081 anchor is the conservative MOO-exact number.

## 2. 8-cell -> 4-cell Grid (clean + ext)

Cell key: lower = OFF, upper = ON. Order [C][V].

CLEAN (2008-05-30 .. 2026-05-22)

| Cell | C | V | Sharpe | Calmar | MaxDD | CAGR | Vol |
|------|---|---|--------|--------|-------|------|-----|
| cv (HAA-Simple) | off | off | 0.9840 | 0.5685 | -20.41% | 11.60% | 11.92% |
| Cv | ON | off | 1.0377 | 0.6432 | -20.41% | 13.13% | 12.70% |
| cV | off | ON | 1.1005 | 0.8189 | -13.35% | 10.93% |  9.90% |
| CV (prod BULL) | ON | ON | 1.0813 | 0.8573 | -13.35% | 11.44% | 10.57% |

EXT (1999-03-10 .. 2026-05-22)

| Cell | C | V | Sharpe | Calmar | MaxDD | CAGR | Vol |
|------|---|---|--------|--------|-------|------|-----|
| cv (HAA-Simple) | off | off | 0.9735 | 0.5259 | -20.41% | 10.73% | 11.11% |
| Cv | ON | off | 0.9528 | 0.5800 | -20.41% | 11.84% | 12.57% |
| cV | off | ON | 1.0207 | 0.7101 | -13.35% |  9.48% |  9.30% |
| CV (prod BULL) | ON | ON | 0.9196 | 0.6800 | -13.96% |  9.49% | 10.45% |

## 3. Main Effects (avg ON - avg OFF), with sign-flip flags

A "sign flip" = the effect changes sign between CLEAN and EXT.

| Factor | Metric | CLEAN | EXT | Sign flip? |
|--------|--------|-------|-----|------------|
| C canary | Sharpe | +0.0172 | -0.0609 | YES (flip) |
| C canary | Calmar | +0.0565 | +0.0120 | no |
| V vol    | Sharpe | +0.0801 | +0.0070 | no |
| V vol    | Calmar | +0.2322 | +0.1421 | no |

Reading:
- V (vol gate) is the dominant lever. It lifts Sharpe and (strongly) Calmar in
  both windows by cutting MaxDD from -20.41% to about -13.4%. Most of the
  HAA-Simple -> BULL improvement is the vol gate.
- C (HYG-OR-TIP canary) is marginal-to-harmful on Sharpe. It is mildly positive
  clean (+0.017) but NEGATIVE ext (-0.061) -> sign flip. On Calmar it is mildly
  positive in both windows. The HYG breadth extension does not pay for itself on
  a risk-adjusted-return basis over the full history.

## 4. Interaction C x V (clean + ext), BOTH metrics, explicitly labeled

Interaction = 0.5 * [ (CV - cV) - (Cv - cv) ]. This is the non-additivity of
turning both factors on vs the sum of each alone.

CAUTION / prior-memo correction: the prior memo reported the CLEAN C x V
**Sharpe** interaction (-0.036) but placed it under a **Calmar** column. Each
metric has a DIFFERENT value; they are labeled distinctly below.

| Interaction | Metric | CLEAN | EXT |
|-------------|--------|-------|-----|
| C x V | Sharpe | -0.0365 | -0.0402 |
| C x V | Calmar | -0.0181 | -0.0421 |

Reading:
- The C x V interaction is NEGATIVE on both metrics in both windows: canary and
  vol gate are partly redundant (each already times exposure away from drawdowns),
  so stacking them yields less than the additive sum.
- The clean Sharpe value (-0.0365) is NOT the clean Calmar value (-0.0181). Do
  not conflate them.

## 5. Contribution Ladder (CLEAN Sharpe; path-dependent due to negative C x V)

Because C x V < 0, ladder order matters. Both orders shown.

V-first (dominant lever first):
| Step | Cell | Sharpe | Delta |
|------|------|--------|-------|
| Baseline (HAA-Simple) | cv | 0.9840 | -- |
| + V (vol gate) | cV | 1.1005 | +0.1165 |
| + C (HYG-OR-TIP canary) -> prod BULL | CV | 1.0813 | -0.0192 |

C-first:
| Step | Cell | Sharpe | Delta |
|------|------|--------|-------|
| Baseline (HAA-Simple) | cv | 0.9840 | -- |
| + C (HYG-OR-TIP canary) | Cv | 1.0377 | +0.0537 |
| + V (vol gate) -> prod BULL | CV | 1.0813 | +0.0436 |

Net all-OFF -> all-ON (clean Sharpe): +0.0973 (0.9840 -> 1.0813).
Decomposition: V dominates; the last-added C is a drag when V is already on
(V-first ladder), reflecting the negative interaction. On the EXT window the
net is NEGATIVE for Sharpe (0.9735 -> 0.9196, -0.0539) but POSITIVE for Calmar
(0.5259 -> 0.6800) -- the BULL gates buy drawdown protection at some Sharpe cost
over the long sample.

CLEAN Calmar ladder (V-first), for completeness:
| Step | Cell | Calmar | Delta |
|------|------|--------|-------|
| Baseline | cv | 0.5685 | -- |
| + V | cV | 0.8189 | +0.2504 |
| + C -> prod BULL | CV | 0.8573 | +0.0384 |

## 6. Safe-Pool Immateriality Check (NOT a factorial axis)

Swap the safe pool {IEF, BIL} (paper) vs {SHV, IEF} (production) on the all-OFF
HAA-Simple baseline. BIL fetched live (inception 2007-05-30); deltas measured
where BIL is live.

| Window | Metric | paper {IEF,BIL} | prod {SHV,IEF} | Delta (prod - paper) |
|--------|--------|-----------------|----------------|----------------------|
| CLEAN | Sharpe | 0.9838 | 0.9840 | +0.0002 |
| CLEAN | Calmar | 0.5684 | 0.5685 | +0.0001 |
| EXT   | Sharpe | 0.9751 | 0.9735 | -0.0016 |
| EXT   | Calmar | 0.5296 | 0.5259 | -0.0036 |

Deltas are ~0 (|delta| < 0.004 on every metric). The {IEF,BIL} vs {SHV,IEF}
distinction is immaterial -> correctly excluded from the factorial.

Data-history reason SHV is preferred over BIL:
- SHV is stitched from VFISX (Vanguard Short-Term Treasury) back to 1991 in the
  panel, so it covers the full extended (1999+) window.
- BIL has no stitched long history (real inception ~2007-05) and is absent from
  the production panel. Using BIL would truncate or gap the extended backtest.
- SHV/BIL daily-return correlation is low (0.31) only because both are
  near-zero-noise cash; their price LEVELS track closely, hence the negligible
  performance delta.

## Caveats / Confidence

- All 4 cells, both anchors, and the immateriality check run on a single
  apples-to-apples harness (mooex, 10 bps/side). HIGH confidence in the
  relative effects.
- all-ON is logically identical to production BULL (0 weight mismatches). The
  mooex clean Sharpe (1.0813) is the conservative MOO-exact figure; the native
  bull_qqq_live engine reports 1.1200 (close-to-close approximation).
- BIL deltas are measured only on the post-2007 overlap (the only window where
  BIL exists); the extended-window safe-pool delta uses SHV throughout by
  necessity. This does not change the immateriality conclusion.
- HAA-Simple universe note inherited from the audit: BIL proxied/held as SHV in
  the baseline cash leg (anchor matches the audit to 4 dp).
