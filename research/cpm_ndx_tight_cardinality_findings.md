# NDX tight-cardinality: does N=K+1 min-var / drop-1 or +/-1 breadth beat prod top-5 EW?

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / memo NOT edited,
no commit). Harness: `research/cpm_ndx_tight_cardinality.py`. Results JSON:
`research/cpm_ndx_tight_cardinality_findings.json`.

## Question

Prior NDX experiment (`research/cpm_ndx_minvar_cvar.py`) found min-var / CVaR / CDaR
on a top-15 momentum prune significantly HURT, because pruning to 15 then selecting 5
reaches deep down the momentum ranking and min-var picks low-variance momentum
laggards, killing the momentum premium. Refinement tested here: a TIGHT N=K+1 prune
so the candidate pool stays high-momentum and min-var only drops the single
most-redundant / most-volatile name. Does that rescue the drop-1 idea, and does a
+/-1 breadth change beat prod?

## Method

Engine reuse only. The unmodified `ndx_sleeve_live.run_ndx_backtest` runs each config
(gating TIP + SPY-trend + SPY-vol, safe rotation, T+1 MOO close-to-close, 10bps/side,
delisting haircut, PIT membership all identical). `compute_ndx_weights` is monkeypatched
per config; only the held-names selection / cardinality varies. EW sizing throughout via
the prior harness `_partial_safe_pack` so partial-fill / cash semantics match prod
exactly. Helpers (gate prefix, LW min-var subset, metrics, turnover, walk-forward,
crisis windows) and the B=2000 / block=21 / seed=42 paired block bootstrap are imported
from the prior harness for byte-faithful reuse.

Configs (EW throughout):

- PROD: momentum top-5 EW (baseline)
- MINVAR_6to5: momentum top-6 -> min-var subset of 5 -> EW (drop worst-by-variance)
- DROP1CORR_6to5: momentum top-6 -> drop highest-avg-pairwise-corr -> 5 -> EW
- MINVAR_5to4: momentum top-5 -> min-var subset of 4 -> EW (tighter, hold 4)
- TOP6_EW: momentum top-6 EW (+1 breadth control)
- TOP4_EW: momentum top-4 EW (-1 concentration control)

Anchor check: PROD reproduces clean Sharpe 1.281, MaxDD -31.39% (matches the ~1.281 /
-31.4% target), confirming the engine wiring is intact.

## Results

### Clean (2008+, DECISION window)

| cfg | Sharpe | Sortino | CVaR | Calmar | Martin | MaxDD | CAGR | vol | TO |
|---|---|---|---|---|---|---|---|---|---|
| PROD | 1.281 | 1.962 | 8.40 | 1.002 | 4.233 | -0.314 | 0.314 | 0.236 | 5.16 |
| MINVAR_6to5 | 1.130 | 1.695 | 7.27 | 0.776 | 2.983 | -0.320 | 0.249 | 0.218 | 5.35 |
| DROP1CORR_6to5 | 1.239 | 1.892 | 8.16 | 0.926 | 3.797 | -0.314 | 0.290 | 0.227 | 5.29 |
| MINVAR_5to4 | 1.167 | 1.769 | 7.62 | 0.814 | 3.391 | -0.338 | 0.275 | 0.231 | 5.56 |
| TOP6_EW | 1.231 | 1.856 | 7.98 | 0.928 | 3.942 | -0.304 | 0.282 | 0.222 | 5.04 |
| TOP4_EW | 1.324 | 2.074 | 8.90 | 1.087 | 4.257 | -0.318 | 0.346 | 0.248 | 5.03 |

### Stress (1999+, CONFIRM window)

| cfg | Sharpe | Sortino | CVaR | MaxDD | CAGR |
|---|---|---|---|---|---|
| PROD | 1.131 | 1.721 | 7.39 | -0.314 | 0.229 |
| MINVAR_6to5 | 1.002 | 1.493 | 6.47 | -0.320 | 0.184 |
| DROP1CORR_6to5 | 1.092 | 1.654 | 7.14 | -0.314 | 0.211 |
| MINVAR_5to4 | 1.021 | 1.535 | 6.65 | -0.338 | 0.199 |
| TOP6_EW | 1.098 | 1.646 | 7.12 | -0.304 | 0.209 |
| TOP4_EW | 1.159 | 1.800 | 7.74 | -0.318 | 0.249 |

Stress ranks the configs identically to clean. No config flips sign between windows.

### Paired block bootstrap vs PROD (clean; mean diff, p_gt0 = P(config > prod))

| cfg | dSharpe | dSortino | dCVaR |
|---|---|---|---|
| MINVAR_6to5 | -0.148 (p=0.024) | -0.263 (p=0.021) | -1.113 (p=0.023) |
| DROP1CORR_6to5 | -0.040 (p=0.189) | -0.068 (p=0.194) | -0.241 (p=0.238) |
| MINVAR_5to4 | -0.113 (p=0.049) | -0.192 (p=0.047) | -0.777 (p=0.057) |
| TOP6_EW | -0.049 (p=0.089) | -0.106 (p=0.052) | -0.424 (p=0.064) |
| TOP4_EW | +0.043 (p=0.827) | +0.113 (p=0.905) | +0.499 (p=0.913) |

Classification (significant = p_gt0 <= 0.05 or >= 0.95):

- MINVAR_6to5: SIGNIFICANTLY WORSE on all three metrics.
- MINVAR_5to4: WORSE (Sharpe/Sortino significant, CVaR marginal).
- TOP6_EW: marginally worse (Sortino borderline, CVaR borderline) -- a wash/slight loss.
- DROP1CORR_6to5: wash (no metric significant).
- TOP4_EW: LEANS better on all three (Sortino 0.905, CVaR 0.913) but none crosses 0.95.

### 6->5 min-var vs 6->5 drop1-corr (positive = min-var better)

| metric | mean | p_gt0 | 95% CI |
|---|---|---|---|
| dSharpe | -0.107 | 0.050 | [-0.234, +0.019] |
| dSortino | -0.195 | 0.040 | [-0.413, +0.016] |
| dCVaR | -0.871 | 0.034 | [-1.796, +0.060] |

corr-only BEATS vol+corr min-var at tight cardinality (min-var significantly worse).
This is the OPPOSITE of the CPM weighting finding: adding the variance objective on a
high-momentum pool actively hurts because it drops a high-momentum name to chase low
variance.

### dMaxDD vs PROD (context only; positive = shallower DD)

| cfg | dMaxDD | p_gt0 |
|---|---|---|
| MINVAR_6to5 | +0.005 | 0.631 |
| DROP1CORR_6to5 | +0.003 | 0.594 |
| MINVAR_5to4 | -0.014 | 0.259 |
| TOP6_EW | +0.012 | 0.823 |
| TOP4_EW | -0.016 | 0.178 |

TOP6_EW is the only config that shallows MaxDD with any conviction (-30.4% vs -31.4%,
82% of bootstrap paths shallower) -- but it pays a small Sharpe/Sortino cost, so it is
a mild risk-for-return trade, not free breadth.

### Per-crisis Sharpe (ext series)

| cfg | dotcom | GFC | COVID | 2022 | 2025 |
|---|---|---|---|---|---|
| PROD | 0.946 | 0.960 | 2.707 | 2.985 | 0.895 |
| MINVAR_6to5 | 0.946 | 0.985 | 2.707 | 2.985 | 2.184 |
| DROP1CORR_6to5 | 0.946 | 1.034 | 2.707 | 2.985 | 1.413 |
| MINVAR_5to4 | 0.946 | 1.060 | 2.707 | 2.985 | 1.742 |
| TOP6_EW | 0.946 | 0.919 | 2.707 | 2.985 | 1.273 |
| TOP4_EW | 0.946 | 1.060 | 2.707 | 2.985 | 0.640 |

dot-com / COVID / 2022 are IDENTICAL across configs: the sleeve was gated defensive
(safe / SPY proxy) in those windows, so held-name selection is irrelevant there.
Differences appear only in GFC (small) and the noisy half-year 2025 window. Note TOP4_EW
is the WORST in 2025 (0.640) despite the best clean point estimate -- its edge is not a
crisis effect.

### Walk-forward (3 segments, clean Sharpe)

| cfg | seg1 2008-2014 | seg2 2014-2020 | seg3 2020-2026 |
|---|---|---|---|
| PROD | 1.179 | 1.252 | 1.471 |
| MINVAR_6to5 | 1.241 | 1.088 | 1.167 |
| MINVAR_5to4 | 1.255 | 1.107 | 1.251 |
| TOP4_EW | 1.175 | 1.198 | 1.596 |

TOP4_EW (the only point-estimate winner) BEATS prod in seg1 (barely) and seg3 but LOSES
seg2 (1.198 vs 1.252). Its overall edge is driven entirely by seg3 (2020-2026). It is
NOT a consistent walk-forward winner. No config beats prod in all 3 segments.

## Answers

(a) Does 6->5 min-var (drop worst-by-variance from a tight high-momentum +1 pool) beat
prod top-5 EW? NO -- it is SIGNIFICANTLY WORSE (dSharpe -0.148, p=0.024; dSortino p=0.021;
dCVaR p=0.023). Keeping the pool high-momentum did NOT rescue the drop-1 idea. The damage
is the variance objective itself: even from a tight pool, min-var drops the single most
volatile name, which is usually a high-momentum winner, sacrificing momentum premium.
MINVAR_5to4 is likewise worse. So the prior top-15 result was not just deep-prune
contamination; the min-var objective is structurally anti-momentum here.

(b) 6->5 min-var vs 6->5 drop1-corr? corr-only WINS (min-var significantly worse:
dSharpe p=0.050, dSortino p=0.040, dCVaR p=0.034). Vol+corr does NOT beat corr-only at
tight cardinality -- the OPPOSITE of the CPM finding. Adding the variance term on a small
high-momentum pool hurts; the pure corr drop is the gentler, near-prod rule.

(c) Cardinality. TOP6_EW (+1 breadth): cuts MaxDD modestly (-30.4% vs -31.4%, ~82% of
paths shallower) but at a small Sharpe/Sortino cost (Sortino borderline worse) -- a mild
risk-for-return trade, NOT cheap free breadth. TOP4_EW (-1 concentration): does NOT hurt;
it LEANS better on Sharpe/Sortino/CVaR point estimates (p ~ 0.83-0.91) but fails to reach
significance, fails walk-forward (loses seg2), worsens MaxDD slightly, and is the worst in
the 2025 window -- edge is seg3-concentrated, consistent with noise / overfit rather than
a robust concentration premium.

(d) Distinguishable from prod? Min-var configs are significantly WORSE. drop1-corr and
top-6 are washes / slight losses. top-4 leans better but is not significant and is
walk-forward-inconsistent. Nothing robustly beats prod top-5 EW.

## Verdict

Tight-cardinality (N=K+1) min-var / drop-1 selection does NOT beat NDX prod top-5 EW.
Keeping the candidate pool high-momentum does NOT rescue the drop-1 idea: min-var is
significantly worse even at 6->5 and 5->4, confirming the mechanism is the variance
objective sacrificing the momentum premium (it, higher-variance
winner), not merely deep-prune contamination from the prior top-15 test. Corr-only drop
beats vol+corr at tight cardinality (opposite of CPM). +1 breadth (top-6 EW) buys a small
MaxDD reduction at a small Sharpe cost, not a free lunch. The only point-estimate winner
(top-4 EW) is not statistically distinguishable from prod and fails walk-forward, so it
reads as noise / overfit, not a durable concentration edge. Recommendation: keep prod
top-5 EW; do not adopt any tight min-var / drop-1 / breadth variant.

## Caveats / confidence

- Single in-sample design (one decision window); no nested OOS parameter search, but the
  bootstrap + 3-seg walk-forward guard against single-point luck.
- Bootstrap classifies dSharpe / dSortino / dCVaR (order-invariant). dCalmar / dMartin /
  dMaxDD are path-dependent context only, not classified.
- Per-crisis windows dot-com / COVID / 2022 are gate-off for all configs (selection
  irrelevant there); 2025 is a noisy half-year. Selection differences live almost entirely
  in the post-2014 / 2020-2026 active regime.
- Turnover is nearly flat across configs (5.0-5.6x/yr); the drop-rules add negligible churn,
  so cost is not the differentiator -- the selection signal itself is the loser.
- PIT membership, delisting haircut, T+1 MOO execution, and the gate are identical across
  configs (engine untouched), so differences are pure held-name selection / cardinality.
- Confidence: HIGH that min-var hurts (significant, consistent clean+stress+WF, matches
  prior NDX direction). HIGH that nothing robustly beats prod. MODERATE that top-4's lean
  is noise (strong point estimate but WF-inconsistent and significance not reached).
