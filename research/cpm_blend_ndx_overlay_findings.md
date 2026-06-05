# NDX de-risk overlay at the FULL PRODUCTION BLEND level

Analyst findings. Research-only. Point-estimates, single in-sample, HIGH overfit
caution (mult chosen a-priori). Cached frozen dataset.

## Question / hypothesis

Does plugging the settled NDX tail-protection overlay (top-5 discrete
drop-lowest-momentum, target = m * expanding-window QQQ vol) into the **whole**
60/20/20 production book improve portfolio risk-adjusted metrics, or does the
diversified blend already absorb NDX's sleeve drawdown so the overlay only costs
blend CAGR?

User hypothesis under test: "maybe NDX should maximize CAGR" -- at 20% blend
weight the NDX sleeve -31% diversifies away while the -19% CAGR cost persists.

## Method

- PROD blend construction REUSED verbatim from `build_dashboard.build_artifacts`
  (`CPM_W=0.60`, `BULL_W=0.20`, `NDX_W=0.20`; blend = 0.6*CPM + 0.2*BULL +
  0.2*NDX). CPM + BULL sleeves IDENTICAL across all configs.
- Only the NDX sleeve varies: monkeypatch `ndx_sleeve_live.compute_ndx_weights`
  with the QQQ_EXPAND overlay (`research/cpm_ndx_voltarget_expandqqq_harness.make_compute`),
  unmodified `run_ndx_backtest` reused (gate / safe rotation / T+1 MOO / 10bps /
  delist / PIT all preserved).
- Configs: PROD (top-5 EW, no de-risk), m=1.00 (~fixed-0.25), m=1.25
  (~fixed-0.30), m=1.50.
- Metrics at the BLEND level: Sharpe, Sortino, CVaR(95) ratio, Calmar, Martin,
  MaxDD, CAGR, ann.vol; CLEAN window 2008-05-30 -> 2026-05-22. Per-crisis MaxDD +
  2021 unwind on EXT window 1999-03-10+ (so dotcom/GFC are in-window).
- POINT-ESTIMATES ONLY. No bootstrap, no walk-forward (standing scope cut).

Repro:
```
.venv/bin/python research/cpm_blend_ndx_overlay_run.py
```
Artifacts: `research/cpm_blend_ndx_overlay_{harness,run}.py`,
`research/cpm_blend_ndx_overlay_findings.json`.

## PROD blend anchor (reproduced honestly)

My repro of the unmodified prod blend (CLEAN 2008-05-30 -> 2026-05-22):

| metric | my repro | build_dashboard.py header |
|---|---|---|
| Sharpe | 1.495 | 1.4155 |
| CAGR | 17.02% | 16.51% |
| MaxDD | -10.46% | -12.26% |
| Calmar | 1.626 | 1.3467 |

FLAG: my repro is modestly BETTER than the hardcoded header (higher Sharpe/CAGR,
shallower MaxDD, higher Calmar). Likely a data-vintage / window difference
(cached frozen dataset vs the build that produced the header; the header MaxDD
-12.26% vs my -10.46% suggests a slightly different end date or panel refresh).
Direction of the overlay deltas below is robust regardless of which anchor is
"true" because CPM+BULL are held identical -- the comparison is internally
consistent.

## Blend-level results (CLEAN 2008-05-30+)

| cfg | Sharpe | Sortino | CVaR | Calmar | Martin | MaxDD | CAGR | vol | NDX TO |
|---|---|---|---|---|---|---|---|---|---|
| PROD  | 1.495 | 2.216 | 9.943 | **1.626** | **6.715** | -10.46% | **17.02%** | 10.93% | 5.16 |
| m1.00 | 1.499 | 2.216 | 9.973 | 1.502 | 6.430 | -10.46% | 15.72% | 10.09% | 4.93 |
| m1.25 | 1.486 | 2.194 | 9.858 | 1.518 | 6.413 | -10.46% | 15.88% | 10.29% | 5.05 |
| m1.50 | 1.480 | 2.187 | 9.819 | 1.552 | 6.504 | -10.46% | 16.24% | 10.56% | 5.11 |

Decisive structural fact: **blend MaxDD is IDENTICAL (-10.46%) across ALL
configs.** The binding blend drawdown is the **May 2010 flash-crash / Euro debt
selloff (peak 2010-04-26 -> trough 2010-05-20)**, which is a CPM/BULL-era event
the NDX overlay can never touch. Because the denominator of Calmar and (via
Ulcer) Martin is fixed, the overlay can only *lower* CAGR -> it strictly worsens
Calmar and Martin at the blend.

NDX-only turnover barely moves (5.16 -> 4.93..5.11); blend turnover delta is ~0.2x
that, i.e. negligible.

## NDX sleeve standalone (marginal-contribution source, CLEAN)

| cfg | NDX CAGR | NDX MaxDD | NDX Calmar | NDX Sharpe |
|---|---|---|---|---|
| PROD  | 31.43% | -31.39% | 1.001 | 1.279 |
| m1.00 | 25.08% | -22.41% | 1.119 | 1.312 |
| m1.25 | 25.81% | -27.85% | 0.927 | 1.275 |
| m1.50 | 27.51% | -29.57% | 0.930 | 1.254 |

The sleeve-level story reproduces prior runs: m=1.00 trims NDX DD -31% -> -22%
and lifts sleeve Calmar (+12%) and Sharpe, at -6.3pp sleeve CAGR.

## Per-crisis BLEND MaxDD (EXT 1999+)

| cfg | dotcom | GFC | COVID | Y2022 | Y2025 | unwind21 | year21 |
|---|---|---|---|---|---|---|---|
| PROD  | -6.52% | -8.00% | -7.96% | -5.09% | -7.70% | -9.33% | -9.33% |
| m1.00 | -6.52% | -8.00% | -7.96% | -5.09% | -7.70% | **-6.07%** | **-6.07%** |
| m1.25 | -6.52% | -8.00% | -7.96% | -5.09% | -7.70% | -6.69% | -6.69% |
| m1.50 | -6.52% | -8.00% | -7.96% | -5.09% | -7.70% | -8.00% | -8.00% |

Every market-wide crisis (dotcom / GFC / COVID / 2022 / 2025) is **identical**
across configs -- in those episodes the NDX gate is already OFF (rotated to safe),
so EW vs overlay produce the same sleeve. The overlay only bites in the **2021
momentum unwind**, the one episode where the gate stays ON while the
concentrated basket blows up. There, blend 2021 DD improves -9.33% -> -6.07%
(m=1.00), a ~3.3pp shave.

But note: the 2021 blend DD (-9.33% prod) is already SHALLOWER than the binding
blend MaxDD (-10.46%, May 2010). So shaving 2021 does not move the headline
MaxDD / Calmar at all.

## NDX sleeve per-crisis (dilution check)

| cfg | COVID | Y2022 | unwind21 | year21 |
|---|---|---|---|---|
| PROD  | -4.68% | -0.30% | -31.39% | -31.39% |
| m1.00 | -4.68% | -0.30% | -17.41% | -19.14% |
| m1.25 | -4.68% | -0.30% | -19.62% | -19.96% |
| m1.50 | -4.68% | -0.30% | -26.14% | -26.14% |

Dilution math: NDX 2021 DD -31.4% -> -19.1% (m=1.00) is a 12.3pp sleeve
improvement. At 20% weight + diversification with CPM/BULL it survives as only a
~3.3pp blend improvement (-9.33% -> -6.07%), i.e. roughly 27% of the sleeve gain
reaches the book. Confirms the user's intuition: most of the NDX 2021 blowup is
ALREADY diversified away before any overlay.

## Answers to key questions

(a) **Does the overlay materially change blend MaxDD / Calmar / Martin / CVaR /
Sharpe?** No. Blend MaxDD identical (-10.46%, May 2010, NDX-independent). Sharpe
flat (1.495 -> 1.50/1.49/1.48, within noise). Sortino flat-to-down. CVaR flat.
Calmar and Martin **worsen** (CAGR cut with fixed denominator). The only
non-noise effect is the 2021 secondary DD.

(b) **Net CAGR cost at blend?** -1.30pp (m=1.00), -1.14pp (m=1.25), -0.78pp
(m=1.50). Matches ~0.2 x sleeve CAGR cut (-6.3pp x 0.2 = -1.27pp). Real and
persistent.

(c) **Does the blend already diversify away NDX's 2021 -31%?** Largely yes. NDX
-31% sleeve DD is already only -9.33% at the blend (prod, no overlay). The
overlay shaves a further ~3.3pp (to -6.07%), but this is a SECONDARY drawdown
below the binding -10.46% MaxDD, so it does not improve the portfolio's headline
risk. The diversification does the heavy lifting; the overlay polishes an
already-diluted, non-binding episode.

(d) **Calmar / Martin / CVaR at blend -- genuine improvement or frontier slide?**
Worse than a frontier slide: STRICTLY DOMINATED on Calmar and Martin. Because
the binding blend MaxDD (and hence Ulcer's dominant term) is unaffected by NDX,
the overlay only removes CAGR from the numerator. CVaR ratio is flat. There is
no risk-adjusted metric at the blend level that the overlay improves; sleeve-level
Calmar +12% does NOT propagate to the book.

(e) **Recommendation:** KEEP NDX as the top-5 EW pure CAGR engine. Do NOT adopt
the overlay at the production blend. Rationale (explicit CAGR-vs-tail tradeoff at
the portfolio level): the overlay costs ~1pp blend CAGR for a flat Sharpe, worse
Calmar/Martin, and a benefit confined to a single non-binding secondary drawdown
(2021) that diversification already shrinks from -31% to -9%. Portfolio tail
protection is already supplied by the CPM/BULL diversification and the NDX gate
(which catches every market-wide crisis); the discretionary momentum-unwind
overlay adds nothing the book needs. If 2021-style unwind exposure ever becomes a
hard mandate constraint, the lightest dial (m=1.50, -0.78pp CAGR) is the least
costly, but on pure risk-adjusted merit none of the configs justify the CAGR
give-up.

## Caveats / confidence

- Single in-sample, point-estimates only (no bootstrap / WF per scope). NONE of
  the deltas were stress-tested for significance; the 2021 benefit rests on ONE
  episode and the Sharpe deltas are within plausible noise.
- mult is a-priori but the overlay family itself was selected on this same
  history -> HIGH overfit caution; treat the sleeve-level wins as upper bounds.
- Cached frozen dataset; my prod-blend anchor differs modestly from the
  build_dashboard.py header (-10.46% vs -12.26% MaxDD, see FLAG). The overlay
  COMPARISON is internally consistent (CPM+BULL held identical) so the verdict is
  robust to the anchor discrepancy, but the absolute blend numbers should be
  re-confirmed against a fresh prod build before quoting.
- Nothing compelling enough here to warrant a later bootstrap/WF confirm: the
  decision (do not adopt) follows from a structural fact (blend MaxDD is
  NDX-independent), not from a marginal stat that significance testing could
  flip.

## Verdict

Do not adopt the NDX overlay at the production blend. The 20% weight +
diversification already absorbs NDX's sleeve drawdown, the binding blend MaxDD is
a 2010 CPM/BULL event the overlay cannot touch, and the overlay's only real
effect on the book is a ~1pp CAGR give-up. **NDX should stay the pure CAGR
engine.** User hypothesis CONFIRMED.
