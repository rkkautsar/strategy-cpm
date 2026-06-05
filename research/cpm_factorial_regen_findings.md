# CPM Factorial Regeneration -- Findings (HAA -> current prod CPM)

Analyst artifact. Read-only re production. No production files edited. No commit.

## Summary

The existing coupled factorial (`research/cpm_haa_coupled_factorial.py`, all-ON
endpoint Sharpe 1.1658) decomposes an OLD CPM: inverse-vol weighting,
HYG-or-TIP canary, and no min-var selection. Current prod CPM (`cpm_live.py` @
commit 24c1207) is equal-weight, TIP-only canary, with min-var 3-of-4 selection
at n_pos=4. The factor set was therefore stale.

This regeneration rebuilds the HAA -> CPM factorial against current prod with the
corrected factor set:

- DROP canary (both ends TIP-only -> no longer a difference).
- DROP weighting (both ends equal-weight -> no longer a difference).
- ADD min-var 3-of-4 selection at n_pos=4 (CPM-only -> new difference).
- KEEP universe and ranker (still genuinely differ; verified).
- SAFE selector and breadth/partial-safe confirmed identical between HAA and
  CPM -> not factors (verified empirically).

Result: a 2^3 factorial over factors {U universe, R ranker, M min-var}. The
all-ON endpoint reproduces current prod CPM exactly.

- Artifact: `research/cpm_haa_coupled_factorial_v2.py`
- Data: `research/cpm_haa_coupled_factorial_v2.json`
- Run: `.venv/bin/python research/cpm_haa_coupled_factorial_v2.py`

## Method and conventions

- Engine: `research/exec_lag_moo_validation_2026_05_30._segment_returns_conv`,
  convention `mooex` (T+1 month-end signal, next-session-open execution).
- Costs: 10 bps per side at each rebalance.
- Lookbacks: both-252 (ranking vol and covariance both 252 trading days);
  `cpm_live.CORR_LOOKBACK_DAYS == 252`.
- Windows: CLEAN 2008-05-30..2026-05-22 ; EXT 1999-03-10..2026-05-22.
- PIT: monthly signals use `close.loc[:sig_d]` only; vol/cov windows end at sig_d.
- Point estimates only (decomposition; no bootstrap).

## HAA baseline definition (all-OFF, config 000)

Canonical Keller HAA, identical to the prior factorial's all-OFF:

- Universe HAA-8: SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT.
- Canary: TIP 13612U > 0 (risk-off to safe otherwise).
- Rank and screen: 13612U momentum; top-4; screen 13612U > 0.
- Weighting: equal-weight (0.25 per top-4 slot).
- Safe: best-of {SHV, IEF} by 13612U.
- Breadth: partial-safe strict-4 (each negative/missing slot -> safe).

## Gate results (both pass)

- all-OFF (000) == canonical HAA, weight-by-weight: 0 mismatches over 327 months.
  CLEAN Sharpe 0.8670, MaxDD -14.68%, Calmar 0.6386 (matches HAA anchor).
- all-ON (111) == prod `compute_target_weights`, weight-by-weight: 0 mismatches
  over 327 months. CLEAN Sharpe 1.255673, MaxDD -13.0317%, Calmar 1.007646.
- Endpoint reproduction is EXACT: parametric all-ON CLEAN Sharpe
  1.2556732727 vs prod-direct 1.2556732727 vs `cpm_harness` anchor 1.255673.

## (a) Corrected MAIN sequential ladder (HAA -> +U -> +R -> +M = CPM)

CLEAN window:

| Step | Config | Sharpe | MaxDD | Calmar | CAGR | Vol |
|---|---|---:|---:|---:|---:|---:|
| HAA baseline (all-OFF) | 000 | 0.8670 | -14.68% | 0.6386 | 9.37% | 11.08% |
| +U universe (HAA-8 -> CPM-8) | 100 | 1.0189 | -14.96% | 0.7693 | 11.51% | 11.38% |
| +R ranker (13612U -> vol-adj Faber) | 110 | 1.0874 | -13.05% | 0.9118 | 11.90% | 10.93% |
| +M min-var 3-of-4 = CPM (all-ON) | 111 | 1.2557 | -13.03% | 1.0076 | 13.13% | 10.28% |

Per-rung Sharpe gain: +U +0.1519, +R +0.0685, +M +0.1683. Total +0.3887.

EXT window (same order):

| Step | Config | Sharpe | MaxDD | Calmar |
|---|---|---:|---:|---:|
| HAA baseline | 000 | 1.0307 | -14.68% | 0.7527 |
| +U | 100 | 1.1141 | -15.35% | 0.8156 |
| +R | 110 | 1.1331 | -15.73% | 0.7738 |
| +M = CPM | 111 | 1.2549 | -13.14% | 0.9712 |

Order robustness (CLEAN Sharpe, alternate insertion orders, same 000 and 111
endpoints):

- U,R,M: 0.8670 -> 1.0189 -> 1.0874 -> 1.2557
- R,U,M: 0.8670 -> 0.8980 -> 1.0874 -> 1.2557
- M,R,U: 0.8670 -> 0.9038 -> 0.9399 -> 1.2557

## (b) Per-factor MAIN EFFECTS (full 2^3 cube, ON minus OFF average)

CLEAN:

| Factor | dSharpe | dCalmar | dMaxDD | Sign-flip? |
|---|---:|---:|---:|---|
| U universe (HAA-8 -> CPM-8) | +0.2215 | +0.2542 | +1.10pp | no |
| R ranker (13612U -> vol-adj Faber) | +0.0647 | +0.0425 | -0.03pp | yes (Calmar) |
| M min-var 3-of-4 at n_pos=4 | +0.0902 | +0.0327 | -0.07pp | yes (Calmar) |

(dMaxDD positive = shallower drawdown / improvement.)

Selected interactions (CLEAN Sharpe): UxR +0.0311, UxM +0.0508, RxM +0.0149,
UxRxM +0.0124. The UxM and UxR positives mean both R and M deliver more on the
CPM universe than on the HAA universe (consistent with the ladder, where +M's
marginal is largest at the U1R1 corner).

Universe (U) is the dominant single contributor by every metric. R and M are
second-tier and synergize with the CPM universe.

## (c) Min-var selection (M) marginal contribution

M acts only when exactly 4 assets pass the positive screen (n_pos=4): instead of
holding all 4 equal-weight, it picks the equal-weight min-variance 3-of-4 subset
(`_min_var_subset(..., m=3)`), still fully invested (risky_fraction = min(4,4)/4
= 1.0, so 1/3 each).

Marginal effect of turning M on at each (U,R) corner, CLEAN:

| Corner | Sharpe off -> on | dSharpe | dMaxDD | dCalmar |
|---|---|---:|---:|---:|
| U0 R0 (HAA univ, 13612U) | 0.8670 -> 0.9038 | +0.0369 | +1.14pp | +0.0487 |
| U0 R1 (HAA univ, Faber) | 0.8980 -> 0.9399 | +0.0419 | -0.17pp | -0.0099 |
| U1 R0 (CPM univ, 13612U) | 1.0189 -> 1.1326 | +0.1137 | -1.27pp | -0.0038 |
| U1 R1 (CPM univ, Faber) = prod rung | 1.0874 -> 1.2557 | +0.1683 | +0.01pp | +0.0959 |

At the production corner (U1 R1) the min-var rung adds +0.1683 Sharpe and +0.096
Calmar with essentially flat MaxDD -- the single largest Sharpe rung in the
corrected ladder. It is strongly universe-dependent (much weaker on HAA-8).

## (d) Canary and weighting are now no-ops (drop justified)

Current prod CPM and the HAA baseline BOTH use TIP-only canary and equal-weight
risky block. Along HAA -> CPM these never change, so they are constants, not
factors. Empirical confirmation, starting from the all-ON prod config and
flipping each toward its OLD-CPM value:

| Flip from prod (all-ON) | CLEAN Sharpe | Monthly weight changes vs prod |
|---|---:|---:|
| prod CPM (TIP-only, equal-weight) | 1.2557 | 0 / 327 |
| canary -> HYG-or-TIP (old CPM) | 1.2711 | 54 / 327 |
| weighting -> inverse-vol (old CPM) | 1.2497 | 236 / 327 |

Reading: both are still live levers in general (flipping them changes weights and
Sharpe), but current prod selected the HAA value for each. Because the HAA
baseline already sits at TIP-only + equal-weight, these dimensions are identical
at both ends of HAA -> CPM and contribute exactly zero to the decomposition.
They were factors in the prior factorial only because the OLD CPM used the
non-HAA values. (Note the old factorial's reported per-factor effects for these
were small: weighting +0.024 Sharpe, canary +0.024 Sharpe.)

## (e) Kept factors that genuinely still differ; and structural no-ops

Genuinely differ HAA -> CPM (kept as factors):

- U universe: HAA-8 -> CPM cross-asset-8 (QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC).
- R ranker: 13612U rank + 13612U>0 screen -> vol-adjusted Faber rank
  (faber/rv_252) + raw-Faber>0 screen. One coupled factor; bundles the metric
  switch and the vol-adjust (prod's vol-adjust exists only in the Faber path).
- M min-var: hold-all-4 -> min-var 3-of-4 at n_pos=4.

Confirmed identical (NOT factors):

- SAFE selector: both use best-of {SHV, IEF} by 13612U. Universe-independent;
  0 / 327 monthly mismatches between HAA-context and CPM-context selection.
- BREADTH / partial-safe: both use risky_fraction = min(n_pos,4)/4 with
  remainder -> safe (strict-4). Identical mechanism. The only n_pos=4 breadth
  difference is min-var, isolated as factor M.
- Canary and weighting: see (d).

## (f) Memo replacement map (cpm_memo.md -- NOT edited here)

The memo's HAA->CPM decomposition tables and scope line are stale (built on the
OLD CPM: 1.1658, inverse-vol, HYG-or-TIP). Replacements (apply when memo is
revised; numbers below are CLEAN unless noted):

### Scope line (cpm_memo.md line ~5)

Old: "CPM (cross-asset top-4 Faber vol-adjusted momentum, HYG-or-TIP canary,
breadth-scaled partial-safe routing, SHV/IEF safe selector)".

New: "CPM (cross-asset top-4 Faber vol-adjusted momentum, TIP-only canary,
equal-weight risky block, min-var 3-of-4 selection at full breadth,
breadth-scaled partial-safe routing, SHV/IEF safe selector)".

### Coupled main-effects table (cpm_memo.md ~332-338)

Replace the 5-row table (Trend / Vol-adjustment / Weighting / Canary / Universe)
with the corrected 3-factor table:

| Factor | dSharpe | dCalmar | dMaxDD | Sign-flip? |
|---|---:|---:|---:|---|
| Universe (HAA-8 -> CPM-8) | +0.2215 | +0.2542 | +1.10pp | no |
| Ranker (13612U -> vol-adj Faber, coupled rank+screen) | +0.0647 | +0.0425 | -0.03pp | yes (Calmar) |
| Min-var 3-of-4 selection at n_pos=4 | +0.0902 | +0.0327 | -0.07pp | yes (Calmar) |

Add a note: canary and weighting are no longer factors (prod reverted both to
the HAA value: TIP-only, equal-weight).

### Sequential ladder table (cpm_memo.md ~340-349)

Replace header "(trend metric -> vol-adjustment -> weighting -> canary ->
universe)" and the 6-row ladder with order (universe -> ranker -> min-var):

| Step | Sharpe | Calmar | MaxDD |
|---|---:|---:|---:|
| HAA baseline | 0.8670 | 0.6386 | -14.68% |
| +Universe (HAA-8 -> CPM-8) | 1.0189 | 0.7693 | -14.96% |
| +Ranker (vol-adj Faber, coupled rank+screen) | 1.0874 | 0.9118 | -13.05% |
| +Min-var 3-of-4 = CPM (all-ON, both-252) | 1.2557 | 1.0076 | -13.03% |

### Appendix A (cpm_memo.md ~660-696)

This whole "2^6 decomposition" appendix is built on the OLD all-ON endpoint
(111111 -> 1.1658) and the old factor set {R,C,U,S,P,W}. Replace its endpoints
and tables:

- Baseline all-OFF (000): CLEAN Sharpe 0.8670, MaxDD -14.68%, Calmar 0.6386;
  EXT Sharpe 1.0307, Calmar 0.7527.
- All-ON prod CPM (111): CLEAN Sharpe 1.255673, MaxDD -13.0317%, Calmar 1.007646;
  EXT Sharpe 1.2549, MaxDD -13.14%, Calmar 0.9712.

Main effects table (replace; ON minus OFF):

| Factor | Clean dSharpe | Clean dCalmar | Ext dSharpe | Ext dCalmar |
|---|---:|---:|---:|---:|
| Universe (U) | +0.2215 | +0.2542 | +0.1450 | +0.1596 |
| Ranker (R) | +0.0647 | +0.0425 | +0.0228 | -0.0442 |
| Min-var (M) | +0.0902 | +0.0327 | +0.0600 | +0.0413 |

Contribution ladder (replace 6-step R->C->U->S->P->W with U->R->M):

| Step | Config | Clean Sharpe | Clean Calmar | Clean MaxDD | Ext Sharpe | Ext Calmar | Ext MaxDD |
|---|---|---:|---:|---:|---:|---:|---:|
| Baseline (all-OFF) | 000 | 0.8670 | 0.6386 | -14.68% | 1.0307 | 0.7527 | -14.68% |
| +U | 100 | 1.0189 | 0.7693 | -14.96% | 1.1141 | 0.8156 | -15.35% |
| +R | 110 | 1.0874 | 0.9118 | -13.05% | 1.1331 | 0.7738 | -15.73% |
| +M (all-ON prod) | 111 | 1.2557 | 1.0076 | -13.03% | 1.2549 | 0.9712 | -13.14% |

### Other stale 1.1658 / inverse-vol / HYG-or-TIP references

Beyond the sections above, `cpm_memo.md` repeats the OLD anchor and mechanics in
many places (grep for 1.1658, "inverse-vol", "HYG-or-TIP"): lines ~3, 25, 27,
31, 33, 44, 46, 48, 59, 94, 119, 121, 144, 148, 183, 309, 318, 355, 389-398,
422, 439, 525, 540, 551, 584, 588, 630. These are out of scope for this
factorial regen but are flagged as stale (anchor should be 1.255673; weighting
is equal-weight; canary is TIP-only). Hand to fixer/oracle for a full memo pass.

## Caveats and confidence

- Confidence: high. Both gates pass with 0 weight mismatches over 327 months;
  the all-ON endpoint reproduces prod-direct and the `cpm_harness` anchor to
  ~1e-9 (1.2556732727).
- The "ranker" factor R is deliberately coupled (metric + screen + vol-adjust)
  because prod's vol-adjustment exists only on the Faber path; splitting it
  would create configs neither HAA nor CPM uses (the artifact the prior
  factorial's off-diagonal suffered).
- Effects are point estimates; no CIs. Adequate for a deterministic
  decomposition, but factor-effect magnitudes should not be read as
  statistically separable without bootstrap.
- Interaction terms are non-trivial (UxM +0.05 Sharpe), so single main effects
  understate the universe-conditional value of R and M; the ladder at the prod
  corner is the decision-relevant view.
- EXT-window per-factor cube effects are included in the Appendix A table above
  and in the JSON (`effects.EXT_*`).
```
