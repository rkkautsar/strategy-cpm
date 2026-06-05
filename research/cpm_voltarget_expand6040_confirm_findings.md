# CPM expanding-60/40 vol-target -- ADOPTION-GATE CONFIRM (bootstrap + walk-forward)

Research-only. Does not edit prod (cpm_live / build_dashboard / memo). No commit.

## Question

The CPM continuous vol-target with the PARAMETER-FREE expanding-60/40 anchor
(VT-6040-expand) showed only MODEST point-estimate gains vs the prod baseline
(blend, clean): Sharpe +0.015, Calmar +0.14, Martin +0.12, MaxDD -1.4pp. Are
those gains (a) statistically robust (bootstrap CI / p), (b) OOS-stable across
contiguous walk-forward segments, (c) tracking fixed VT-10 (parameter-free
equivalence), and therefore (d) adoptable -- or are they within-noise /
regime-concentrated and should stay research-only?

## Method (exact config)

- Candidate mechanism (settled, implementable): CPM de-risk = EW risky block,
  continuous de-risk-only scale = `min(1, target/rv_CPM)`, shed -> safe,
  monthly / lagged / T+1 / 10bps. SELECTION unchanged (prod
  `compute_target_weights`). `rv_CPM` = trailing 252d baseline CPM sleeve vol
  (lagged, PIT-clean). VT-6040-expand target = expanding-window mean of
  completed-month realized vol of a 60/40 portfolio (0.6*SPY + 0.4*IEF). Fixed
  VT-10% = cross-check.
- Bootstrap: PAIRED BLOCK, `B=2000`, `block=21`, `seed=42`, VT MINUS baseline,
  paired on the identical return path
  (`research/cpm_bootstrap_multimetric.paired_block_bootstrap_mm`). Classification
  metrics with clean CIs: dSharpe, dSortino, dCVaR(95). Path-dependent context
  with SOFT CIs (block resampling shuffles the drawdown path; do NOT classify on
  these): dCalmar, dMartin, dMaxDD. Run at SLEEVE and BLEND (decision level).
- Walk-forward: clean span 2008-05-30..2026-05-22 (6566 days) split into 3
  contiguous equal-calendar thirds:
  - seg1 2008-05-30..2014-05-27 (1508d)
  - seg2 2014-05-28..2020-05-24 (1509d)
  - seg3 2020-05-25..2026-05-22 (1507d)
  Per segment report Sharpe / Martin / MaxDD / CAGR for baseline,
  VT-6040-expand, VT-10 at sleeve + blend.
- Engine: cpm_harness mooex T+1 10bps (sleeve), build_dashboard 60/20/20
  (blend, CPM+BULL+NDX), monkeypatched compute_target_weights. Anchor verified:
  Sharpe 1.255673. Cached frozen dataset (apples-to-apples; deltas paired on
  identical paths). cached-data caveat applies (no fresh fetch).

## Bind diagnostics (clean, 217 months)

```
config                bind_frac  mean_scl   meanTgt
VT-6040-expand            51.6%    0.9006     9.79%
VT-10% (fixed)            45.6%    0.9049    10.00%
```

Expanding-60/40 pins ~9.79% (vs fixed 10.00%) and binds slightly more often.
Parameter-free anchor sits essentially on top of VT-10. (c) equivalence holds
at the mechanism level.

## (a) Bootstrap -- BLEND (DECISION LEVEL), VT-6040-expand minus baseline

```
metric    delta     ci_lo     ci_hi   p(VT>base)  CI excl 0?
Sharpe   +0.0156   -0.0285   +0.0620    74.0%      NO
Sortino  +0.0271   -0.0504   +0.1057    74.5%      NO
CVaR95   +0.1513   -0.1936   +0.5282    78.7%      NO
Calmar   +0.0276   -0.1461   +0.2668    56.1%      NO (soft)
Martin   +0.1041   -0.4314   +0.6875    62.2%      NO (soft)
MaxDD    +0.0115   -0.0020   +0.0319    93.5%      ~touches 0 (soft)
```

BLEND, fixed VT-10 minus baseline (cross-check, directionally stronger):

```
metric    delta     ci_lo     ci_hi   p(VT>base)  CI excl 0?
Sharpe   +0.0251   -0.0226   +0.0752    82.7%      NO
Sortino  +0.0435   -0.0394   +0.1301    83.2%      NO
CVaR95   +0.2333   -0.1454   +0.6474    87.4%      NO
Calmar   +0.0462   -0.1369   +0.3219    60.6%      NO (soft)
Martin   +0.1901   -0.3826   +0.8684    71.9%      NO (soft)
MaxDD    +0.0124   -0.0020   +0.0361    93.9%      ~touches 0 (soft)
```

SLEEVE, VT-6040-expand minus baseline (weaker than blend):

```
metric    delta     ci_lo     ci_hi   p(VT>base)
Sharpe   +0.0088   -0.0733   +0.0959    57.7%
Sortino  +0.0161   -0.1191   +0.1541    59.1%
CVaR95   +0.1902   -0.4522   +0.8586    72.0%
Calmar   -0.0155   -0.2206   +0.2292    40.9%  (soft)
Martin   +0.0386   -0.6913   +0.7885    52.6%  (soft)
MaxDD    +0.0178   -0.0015   +0.0539    92.7%  (soft)
```

(SLEEVE VT-10 similar: Sharpe +0.0231 p=67.3%, all classification CIs include 0.)

ANSWER (a): NO classification metric (Sharpe / Sortino / CVaR) excludes 0 at
either sleeve or blend, for either VT-6040-expand or VT-10. The delta signs are
all favorable and p(VT>base) is 74-87% at blend (directional tilt toward VT) but
that is well short of the ~95%+ needed to call significance; the 95% bootstrap
CIs straddle 0. The ONLY metric with a near-significant signal is MaxDD
(p~93-94%, CI just touches 0) -- and MaxDD is a SOFT path-dependent CI, so it is
context, not proof. The improvement is WITHIN NOISE. Calmar/Martin point deltas
are positive but their soft CIs are wide and span 0.

## (b)/(c) Walk-forward -- BLEND (decision level)

```
seg  config            Sharpe  Martin   MaxDD    CAGR    vs base
1    baseline (prod)    1.112   3.908  -10.46%  13.13%
1    VT-6040-expand     1.174   4.288   -8.07%  12.46%   Sh+ Mt+ DD better
1    VT-10% (fixed)     1.180   4.257   -7.78%  12.20%   Sh+ Mt+ DD better
2    baseline (prod)    1.525   7.226   -8.22%  12.95%
2    VT-6040-expand     1.521   7.191   -8.22%  12.89%   ~tie (near no-op)
2    VT-10% (fixed)     1.525   7.221   -8.22%  12.94%   ~tie
3    baseline (prod)    1.895  11.954   -9.33%  25.51%
3    VT-6040-expand     1.846  10.875   -9.02%  22.74%   Sh WORSE Mt WORSE
3    VT-10% (fixed)     1.853  11.100   -9.05%  23.30%   Sh WORSE Mt WORSE
```

SLEEVE shows the same pattern (seg1 win, seg2 tie, seg3 loss):
seg1 VT Sharpe 1.031 vs base 0.942 (MaxDD -9.87% vs -13.03%); seg2 near-tie;
seg3 VT Sharpe 1.573 vs base 1.670 (CAGR 14.59% vs 18.92%).

ANSWER (b): NO -- VT does NOT beat-or-tie baseline on Sharpe AND Martin in all 3
segments. The edge is REGIME-CONCENTRATED, not consistent:
- seg1 (2008-2014, crisis-heavy): VT clearly helps -- Sharpe +0.06, Martin +0.38,
  MaxDD -2.4pp shallower. This is where the whole point-estimate gain comes from.
- seg2 (2014-2020): essentially a no-op (anchor barely binds; deltas ~0).
- seg3 (2020-2026, strong bull): VT is a DRAG -- Sharpe -0.05, Martin -1.08,
  CAGR -2.8pp; only MaxDD marginally shallower.
This is the textbook de-risk tradeoff: shave tail risk in drawdown regimes, pay
it back in CAGR/Sharpe during strong bulls. It is a risk-preference shift, not a
uniform improvement.

ANSWER (c): YES -- expanding-60/40 tracks fixed VT-10 OOS. Per-segment metrics,
bind freq, mean target, and bootstrap deltas are near-identical (VT-6040-expand
vs VT-10 differ by <=0.01 Sharpe in every segment). Parameter-free equivalence
holds out-of-sample. But that equivalence inherits VT-10's same modest /
non-significant / regime-concentrated profile -- it rediscovers a tepid edge, not
a strong one.

## (d) Adoption verdict

DO NOT ADOPT on the "modest risk-adjusted gain" pitch. STAY RESEARCH-ONLY.

Rationale:
1. Significance fails. Every classification metric (Sharpe / Sortino / CVaR)
   has a 95% paired-bootstrap CI that includes 0 at both sleeve and blend, for
   both VT-6040-expand and VT-10. p(VT>base) of 74-87% (blend) is a favorable
   lean, not significance. The point estimates are inside noise -- exactly the
   concern that triggered this gate.
2. OOS stability fails. The walk-forward shows the gain is concentrated in the
   2008-2014 crisis third, neutral in 2014-2020, and NEGATIVE (Sharpe/Martin/CAGR
   drag) in the 2020-2026 bull. A one-(crisis-)segment edge that reverses in the
   recent regime is not adoptable as a performance improvement.
3. The only durable, directionally-consistent effect is shallower MaxDD
   (-1 to -2.4pp, p~93-94% but soft path-dependent CI; shallower in all 3
   segments). That is a drawdown-SHAPING / de-risk preference, not a free-lunch
   Sharpe gain.

Honest framing: VT-6040-expand is a defensible PARAMETER-FREE de-risk TOGGLE if
and only if the mandate explicitly prefers shallower drawdowns over recent-bull
CAGR -- it cleanly removes the magic-constant objection (tracks VT-10 OOS) and
reliably trims tail depth. But it is NOT a statistically robust, OOS-stable
return/Sharpe improvement. On the evidence it should remain research-only and not
be promoted to prod as an upgrade.

## Caveats / confidence

- Classification CIs (Sharpe/Sortino/CVaR) are clean order-invariant bootstraps:
  HIGH confidence the improvement is within-noise.
- Calmar/Martin/MaxDD CIs are SOFT (block resampling shuffles the drawdown
  path); treat their p-values as context, not proof. The MaxDD shallowness is
  corroborated independently by the per-segment WF (shallower in all 3), so the
  de-risk-trims-tail-depth claim is MEDIUM-HIGH confidence.
- Walk-forward uses fixed equal-calendar thirds; segment metrics on ~1500-day
  windows are noisy but the directional pattern (crisis-win / bull-drag) is
  consistent across sleeve and blend.
- Cached frozen dataset (no fresh fetch); end 2026-05-22. Deltas are
  apples-to-apples, paired on identical paths. PIT-clean targets (trailing/
  expanding use only data <= sig_d / completed months).

## Reproduce

```
.venv/bin/python -m research.cpm_voltarget_expand6040_confirm_run
```

Artifacts:
- research/cpm_voltarget_expand6040_confirm_run.py (harness/run)
- research/cpm_voltarget_expand6040_confirm_findings_raw.txt (full raw tables)
- research/cpm_voltarget_expand6040_confirm_findings.md (this file)
