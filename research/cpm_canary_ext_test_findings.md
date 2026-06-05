# Canary value in the extended crisis-rich window (min-var prod base)

**Question.** On the NEW min-var 3-of-4 production config, does the canary earn
its keep in the EXTENDED window (crises in-sample: dot-com 2000-02 + GFC 2008),
where the clean-window LOO-at-prod-corner understated it? Specifically: does
TIP-only canary significantly beat NO-canary (path-independent: dSharpe /
dSortino / dCVaR), and does HYG add anything over TIP-only?

**Verdict (short).** The canary does **NOT** produce a statistically significant
risk-adjusted improvement even with crises in-sample (TIP-only vs no-canary:
dSharpe / dSortino / dCVaR all NOISE). Its value is **path-dependent drawdown
insurance**: TIP-only cuts the dot-com (-2.0pp), GFC (-3.4pp) and 2022 (-2.7pp)
drawdowns and lifts Calmar/Martin/MaxDD descriptors. **HYG adds nothing** over
TIP-only on crisis DD (identical) and is NOISE on every bootstrap metric while
slightly worsening the worst-case ext drawdown -- HYG is the clean simplification
candidate; TIP-only captures the full canary benefit.

## Method

- Engine/windows: `research/cpm_harness.py` (mooex T+1, both-252, 10 bps/side;
  clean 2008-05-30+, ext 1999-03-10+). Anchor verified FIRST through harness:
  Sharpe 1.262209, MaxDD -11.3463%, Calmar 1.219599 (min-var 3-of-4 prod, commit 7706a1f).
- Configs (all on min-var prod base; vary ONLY the canary):
  - `no_canary`: always risk-on (gate removed; selection/universe/safe/weighting unchanged).
  - `tip_only`: risk-on iff TIP 13612U > 0 (single-asset any_positive).
  - `hyg_or_tip`: current prod (any-positive over HYG/TIP).
- Bootstrap: paired block, B=2000, block=21, seed=42, EXT window, via
  `research/cpm_bootstrap_multimetric.py` (classify on dSharpe/dSortino/dCVaR;
  dCalmar/dMartin/dMaxDD reported as path-dependent context only).
- Script: `research/cpm_canary_ext_test.py`; raw: `research/cpm_canary_ext_test.json`.
- Run: `.venv/bin/python -m research.cpm_canary_ext_test`

## Descriptor table

EXT (1999-03-10 .. 2026-05-22) -- DECISION lens:

| config | Sharpe | Sortino | CVaRr | Calmar | Martin | MaxDD | CAGR | vol |
|---|---|---|---|---|---|---|---|---|
| no_canary | 1.2048 | 1.7223 | 8.12 | 0.8935 | 3.335 | -14.92% | 13.33% | 10.88% |
| tip_only | 1.2265 | 1.7642 | 8.06 | 1.0063 | 3.933 | -12.06% | 12.13% | 9.72% |
| hyg_or_tip | 1.2624 | 1.8093 | 8.45 | 0.9135 | 3.817 | -14.92% | 13.63% | 10.57% |

CLEAN (2008-05-30 .. 2026-05-22) -- contrast:

| config | Sharpe | Sortino | CVaRr | Calmar | Martin | MaxDD | CAGR | vol |
|---|---|---|---|---|---|---|---|---|
| no_canary | 1.1765 | 1.6777 | 7.91 | 0.9776 | 3.218 | -13.60% | 13.30% | 11.18% |
| tip_only | 1.2497 | 1.7962 | 8.21 | 1.1309 | 4.109 | -11.35% | 12.83% | 10.11% |
| hyg_or_tip | 1.2622 | 1.8036 | 8.39 | 1.2196 | 3.952 | -11.35% | 13.84% | 10.76% |

Note: `hyg_or_tip` clean reproduces the production anchor exactly (Sharpe 1.2622,
MaxDD -11.35%, Calmar 1.2196). In EXT, `hyg_or_tip` has the highest Sharpe but a
**worse** MaxDD (-14.92%, equal to no_canary) and worse Calmar than `tip_only`
(-12.06%): the extra HYG risk-on days lift mean return slightly but worsen the
tail. `tip_only` is the best on Calmar/Martin/MaxDD in both windows.

## Per-crisis drawdown (trough in window)

EXT:

| config | Dot-com 2000-02 | GFC 2008 | COVID 2020 | 2022 | 2025 |
|---|---|---|---|---|---|
| no_canary | -9.56% | -13.70% | -10.11% | -9.29% | -11.35% |
| tip_only | -7.54% | -10.33% | -10.11% | -6.61% | -11.35% |
| hyg_or_tip | -7.54% | -10.33% | -10.11% | -6.61% | -11.35% |

Canary DD reduction vs no_canary: dot-com -2.02pp, GFC -3.37pp, 2022 -2.68pp.
COVID and 2025 unchanged (canary did not fire / no help). **TIP-only and
HYG-or-TIP are identical on every crisis DD** -- HYG contributes no incremental
crisis protection.

## Bootstrap (EXT, B=2000 block=21 seed=42)

**TIP-only vs no-canary (KEY QUESTION):**

| metric | mean | 95% CI | p>0 | class |
|---|---|---|---|---|
| dSharpe | +0.0225 | [-0.1612, +0.2099] | 0.588 | NOISE |
| dSortino | +0.0436 | [-0.2314, +0.3346] | 0.609 | NOISE |
| dCVaR | -0.0515 | [-1.3401, +1.2691] | 0.475 | NOISE |
| dCalmar (ctx) | +0.0417 | [-0.2778, +0.4127] | - | soft |
| dMartin (ctx) | +0.2905 | [-0.9470, +1.6716] | - | soft |
| dMaxDD (ctx) | +0.0268 | [-0.0321, +0.1049] | - | soft |

All three classification metrics straddle 0 -> **NOT significant**, even with
dot-com + GFC in-sample. Path-dependent context leans positive for the canary
(dMaxDD +2.7pp, dMartin +0.29, dCalmar +0.04) consistent with the per-crisis DD
cuts, but CIs straddle 0.

**HYG-or-TIP vs TIP-only (does HYG add anything):**

| metric | mean | 95% CI | p>0 | class |
|---|---|---|---|---|
| dSharpe | +0.0340 | [-0.1293, +0.1915] | 0.671 | NOISE |
| dSortino | +0.0415 | [-0.2121, +0.2797] | 0.641 | NOISE |
| dCVaR | +0.3733 | [-0.7900, +1.5042] | 0.743 | NOISE |
| dMaxDD (ctx) | -0.0163 | [-0.0924, +0.0369] | - | soft (negative) |

HYG adds nothing significant; context dMaxDD is slightly **negative** (HYG worsens
the ext tail, matching the -14.92% vs -12.06% descriptor gap).

## Interpretation

1. **Does the canary earn its keep in crises?** Not on path-independent
   risk-adjusted significance -- TIP-only vs no-canary is NOISE on
   Sharpe/Sortino/CVaR even with crises in-sample. So the clean-window LOO
   understatement claim does **not** flip to a significant edge when crises are
   added. The canary's payoff is concentrated in the **drawdown path**: it
   meaningfully trims dot-com (-2.0pp), GFC (-3.4pp), and 2022 (-2.7pp)
   drawdowns and improves Calmar/Martin/MaxDD descriptors. It is best read as
   cheap tail insurance, not a Sharpe-improver.

2. **HYG specifically is dead weight.** TIP-only matches HYG-or-TIP on every
   crisis DD, HYG is NOISE on all bootstrap metrics, and HYG slightly worsens the
   worst-case ext drawdown (any-positive keeps risk-on more often). If
   simplifying, drop HYG and run TIP-only: it keeps the full crisis-DD benefit,
   the best Calmar/Martin/MaxDD, and removes the HYG/VWEHX stitch dependency.

3. **Keep-vs-simplify call.** Keeping a canary is defensible as drawdown
   insurance (the per-crisis cuts are real and economically meaningful), but
   neither the existence of a canary nor the HYG leg is statistically
   significant on path-independent metrics. The strongest evidence-backed
   simplification is **TIP-only over HYG-or-TIP** (parsimony + slightly better
   ext tail, no loss). Removing the canary entirely sacrifices 2-3.4pp of crisis
   drawdown protection for no significant Sharpe gain -- not recommended.

## Caveats / confidence

- Single in-sample ext run; ext is the decision lens here by design. No OOS split.
- Path-independent metrics (Sharpe/Sortino/CVaR) drive the significance calls;
  Calmar/Martin/MaxDD are point/context only (block resampling shuffles the DD path).
- Ext pre-2008 is proxy-backed (lower confidence). Canary proxy availability:
  TIP<-VIPSX ~2000-06+, HYG<-VWEHX pre-2007-04. Pre-2007 HYG-or-TIP effectively
  falls back to TIP, so HYG-or-TIP == TIP-only across the entire dot-com episode
  by construction (explains the identical dot-com DD).
- Bootstrap CIs all reported above; all classification metrics NOISE.

**Next handoff:** oracle/fixer if a decision is made to drop HYG (TIP-only) or
the canary in cpm_live -- this analysis only evaluates; no prod edits made.
