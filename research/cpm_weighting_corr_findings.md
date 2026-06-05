# CPM weighting: does correlation/covariance-aware weighting (ERC / HRP) beat inverse-vol?

Role: analyst (hypothesis-driven, read-only re production). No production files
changed; no commit. Throwaway harness in `research/`.

## Question

Does correlation/covariance-aware WEIGHTING (ERC risk parity, HRP) beat CPM
production inverse-vol weighting, net of cost and walk-forward OOS? Can ERC
replace a min-variance SELECTION step (simpler architecture), or is inverse-vol
confirmed as the robust default?

## Handoff correction (verified in cpm_live.py)

The handoff premise said production uses a min-var subset selection. It does NOT.
Verified in `cpm_live.compute_target_weights` (lines 425-465): production CPM is
single-stage, rank by vol-adjusted Faber (faber / vol_252) -> top-4 -> positive-
faber filter -> `inv_vol_weights` (252d cov DIAGONAL only) -> strict-4 partial-
safe fallback. Correlation enters NOWHERE in production (rank = vol-adjusted,
weighting = cov diagonal only). min-var / min-corr selection were research-only,
never adopted (removed in commit b568013 "single-stage top-4 inverse-vol";
lookback unified 504->252 in 9aac665). So:

- PRODUCTION BASELINE (the number to beat) = rank-select top-4 + inverse-vol.
- The weighting-only A/B (inv-vol vs ERC vs HRP on the SAME prod picks) is the
  clean isolation of the weighting lever -- correlation enters for the FIRST time
  here, so there is no upstream corr to double-count.
- min-var subset is included as a NEW exploratory SELECTION variant, NOT prod,
  to answer "does correlation help more via WEIGHTING or via SELECTION?".

## Method / reproduction

- Harness: `research/cpm_weighting_corr.py` (built on `research/cpm_harness.py`:
  mooex T+1 MOO exact, both-252 baseline, 10 bps/side net). Reuses cpm_live
  selection helpers (faber_sma_xs, best_safe, sig_13612U, inv_vol_weights) so
  the selection/canary/safe/partial-safe blocks are byte-identical to prod;
  ONLY the risky-block weighting is swapped.
- Run: `.venv/bin/python -m research.cpm_weighting_corr`
- Output: `research/cpm_weighting_corr_findings.json` (full grid + per-crisis +
  turnover + bootstrap + walk-forward).
- Weighting: invvol (prod, cov diagonal), ERC (full cov, SLSQP equal-risk-
  contribution), HRP (Lopez de Prado: corr-distance single linkage, quasi-
  diagonalization, recursive bisection).
- Cov estimate for ERC/HRP: Ledoit-Wolf shrinkage (default) and sample
  (robustness). Cov/vol lookback: 252 (prod) and 504.
- Windows: CLEAN 2008-05-30..2026-05-22 (18y); EXT 1999-03-10.. (27y, pre-2008
  leans on stitched proxies). Per-crisis on the EXT curve.
- Turnover: one-way annualized (sum|dw|/2 per monthly rebalance x12); 10 bps/side
  already applied to all returns (the bar is NET).
- Bootstrap: paired stationary block bootstrap, B=2000, block=21, seed=42, same
  block index applied to both legs. Walk-forward: 3 sequential clean segments
  (~6y each), variant vs prod.

### Anchor verification (production through harness)

`H.verify_anchor` reproduces clean both-252 anchor EXACT: Sharpe 1.1658 /
MaxDD -12.97% / Calmar 1.0137. The invvol-sample-252 cell delegates to
`cpm_live.inv_vol_weights`, so the baseline cell IS production.

## 1. Headline grid (net 10 bps/side)

| cell | clean Sharpe | clean Calmar | clean MaxDD | ext Sharpe | ext Calmar | turnover |
|---|---:|---:|---:|---:|---:|---:|
| PROD invvol sample 252 (baseline) | 1.1658 | 1.0137 | -12.97% | 1.2004 | 0.8571 | 258% |
| invvol sample 504 | 1.1910 | 1.0615 | -12.67% | 1.2142 | 0.8608 | 257% |
| ERC LW 252 | 1.1586 | 1.0072 | -12.95% | 1.1974 | 0.8546 | 258% |
| ERC sample 252 | 1.1592 | 1.0049 | -12.97% | 1.1961 | 0.8523 | 259% |
| ERC LW 504 | 1.1938 | 1.0604 | -12.66% | 1.2178 | 0.8621 | 259% |
| ERC sample 504 | 1.1944 | 1.0602 | -12.67% | 1.2165 | 0.8601 | 260% |
| HRP LW 252 | 1.1984 | 1.0448 | -12.68% | 1.1703 | 0.8254 | 291% |
| HRP sample 252 | 1.1975 | 1.0454 | -12.69% | 1.1631 | 0.8208 | 291% |
| HRP LW 504 | 1.2573 | 1.1884 | -11.79% | 1.2016 | 0.8375 | 288% |
| HRP sample 504 | 1.2520 | 1.1843 | -11.77% | 1.1960 | 0.8323 | 290% |

LW vs sample cov makes essentially no difference (deltas < 0.01 Sharpe in every
pair). Drop it as a lever; report LW as default below.

## 2. Isolating the WEIGHTING lever (matched lookback)

This is the clean answer. Hold lookback fixed and swap ONLY the weighting.

At 252 (production lookback):

| weighting | clean Sharpe | clean Calmar | ext Sharpe | ext Calmar |
|---|---:|---:|---:|---:|
| inv-vol (prod) | 1.1658 | 1.0137 | 1.2004 | 0.8571 |
| ERC | 1.1586 | 1.0072 | 1.1974 | 0.8546 |
| HRP | 1.1984 | 1.0448 | 1.1703 | 0.8254 |

At 504:

| weighting | clean Sharpe | clean Calmar | ext Sharpe | ext Calmar |
|---|---:|---:|---:|---:|
| inv-vol | 1.1910 | 1.0615 | 1.2142 | 0.8608 |
| ERC | 1.1938 | 1.0604 | 1.2178 | 0.8621 |
| HRP | 1.2573 | 1.1884 | 1.2016 | 0.8375 |

Reading:

- ERC at matched 252 LOSES to inv-vol on both metrics, both windows
  (clean -0.007 Sharpe / -0.006 Calmar). At 504 ERC ~ inv-vol (clean +0.003
  Sharpe, ext +0.004). Net of estimation noise, ERC adds nothing over inv-vol.
  This is the DeMiguel result: optimized cov-weights do not beat the naive
  diagonal sizing once you isolate them.
- HRP at 252 beats inv-vol on CLEAN (+0.033 Sharpe / +0.031 Calmar) but LOSES on
  EXT on both (-0.030 Sharpe / -0.032 Calmar). A variant that wins one window and
  loses the other is within-noise / window-fragile, not a real edge.

## 3. The 504 "gains" are a LOOKBACK confound, not correlation

Every cell that beats the baseline on both clean Sharpe AND Calmar is either at
504 lookback or uses min-var SELECTION. Lengthening production's OWN inv-vol
lookback 252->504 (invvol_s504) already captures most of the apparent gain:
clean Sharpe 1.1910 (+0.025), Calmar 1.0615 (+0.048), and ERC at 504 only
matches it (1.1938). So the cov-weight "win" at 504 is the lookback, not the
correlation structure. (Lookback was deliberately unified to 252 in prod commit
9aac665; relitigating it is outside the weighting mandate -- flagged, not
recommended here.)

## 4. Correlation helps via SELECTION, not WEIGHTING

| cell | clean Sharpe | clean Calmar | clean MaxDD | ext Sharpe | ext Calmar | turnover |
|---|---:|---:|---:|---:|---:|---:|
| rank-select + inv-vol (PROD) | 1.1658 | 1.0137 | -12.97% | 1.2004 | 0.8571 | 258% |
| rank-select + ERC | 1.1586 | 1.0072 | -12.95% | 1.1974 | 0.8546 | 258% |
| rank-select + HRP | 1.1984 | 1.0448 | -12.68% | 1.1703 | 0.8254 | 291% |
| min-var subset(3) + inv-vol | 1.2622 | 1.2196 | -11.35% | 1.2624 | 0.9135 | 299% |
| min-var subset(3) + ERC | 1.2598 | 1.2191 | -11.31% | 1.2609 | 0.9116 | 299% |

- min-var SELECTION (correlation used to pick the subset) beats prod on BOTH
  windows AND both metrics, and improves EXT (unlike HRP weighting). This is the
  only corr lever that generalizes.
- ERC on top of min-var selection adds nothing (minvar_erc ~ minvar_invvol).
- ERC cannot replace min-var selection: rank-select + ERC ~ prod (no gain). The
  diversification benefit lives in the SELECTION step, not the weighting step.

## 5. Per-crisis (EXT curve; Sharpe / MaxDD / Calmar)

| cell | GFC Sh | GFC DD | COVID Sh | COVID DD | 2022 Sh | 2022 DD | 2025 Sh | 2025 DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PROD invvol 252 | 0.541 | -11.88% | 1.191 | -10.50% | -0.299 | -7.96% | 0.240 | -12.97% |
| ERC 252 | 0.537 | -12.05% | 1.178 | -10.53% | -0.286 | -7.94% | 0.245 | -12.95% |
| HRP 252 | 0.607 | -8.91% | 1.201 | -10.14% | -0.340 | -7.95% | 0.174 | -12.68% |
| invvol 504 | 0.476 | -11.88% | 1.419 | -10.06% | -0.049 | -6.33% | 0.314 | -12.67% |
| HRP 504 | 0.494 | -8.94% | 1.649 | -10.18% | 0.154 | -4.73% | 0.348 | -11.79% |
| min-var inv-vol | 0.744 | -10.33% | 1.246 | -10.11% | -0.114 | -6.19% | 0.243 | -11.35% |

At matched 252, ERC ~ prod in every crisis (noise). HRP-252 trims GFC drawdown
(-8.9% vs -11.9%) but hurts 2022 and 2025. The cross-crisis improvements (COVID,
2022, 2025) track the 504 lookback, not the weighting flavor.

## 6. Bootstrap + walk-forward for cells that beat baseline (clean, Sharpe AND Calmar)

Paired block bootstrap vs prod (B=2000, block=21). 95% CI; P = P(variant > prod).

| cell | dSharpe mean [95% CI] P | dCalmar mean [95% CI] P | dMaxDD |
|---|---|---|---|
| invvol s504 | +0.025 [-0.009,+0.061] 93% | +0.047 [-0.023,+0.155] 90% | +0.6pp |
| ERC LW 504 | +0.028 [-0.017,+0.076] 89% | +0.054 [-0.031,+0.183] 89% | +0.7pp |
| HRP LW 252 | +0.035 [-0.061,+0.133] 75% | +0.042 [-0.157,+0.256] 70% | +0.7pp |
| HRP LW 504 | +0.094 [-0.035,+0.225] 92% | +0.150 [-0.094,+0.451] 90% | +1.7pp |
| min-var inv-vol | +0.097 [-0.005,+0.196] 97% | +0.112 [-0.084,+0.334] 89% | +1.3pp |

Every CI includes 0 (low ceiling, as expected). Strongest signal is min-var
SELECTION (P97 Sharpe), not any weighting variant.

Walk-forward (3 sequential ~6y clean segments, variant minus prod Sharpe):

- ERC 504: +0.037 / +0.038 / +0.005 (all positive, but ~ invvol_s504:
  +0.032 / +0.039 / +0.004 -- the gain is lookback, ERC contributes ~0).
- HRP 252: +0.101 / -0.011 / -0.013 (FAILS OOS -- entirely a 2008-2014 / GFC
  artifact; negative in both later segments).
- HRP 504: +0.195 / +0.065 / -0.005 (front-loaded on GFC era, fades to flat).
- min-var inv-vol: +0.126 / +0.063 / +0.092 (positive in ALL three segments;
  the only corr lever that is consistent OOS).

## 7. Verdict

1. Does corr/cov-aware WEIGHTING beat inv-vol net of cost + OOS? NO.
   - ERC LOSES to inv-vol at matched 252 and only TIES at 504 (the 504 gain is a
     lookback effect inv-vol captures equally). DeMiguel confirmed: optimized
     cov-weights do not beat the naive diagonal once isolated.
   - HRP wins CLEAN at 252 but LOSES EXT and FAILS sequential OOS (gain is a
     2008-2014 / GFC artifact, negative in both post-2014 segments). Higher
     turnover (291% vs 258%) with no durable net payoff.
   - Inverse-vol is confirmed as the robust weighting default.

2. Can ERC replace min-var selection? NO. ERC on rank-select ~ prod (no gain),
   and ERC on top of min-var selection adds nothing. Correlation pays off in
   SELECTION, not WEIGHTING -- ERC cannot substitute for the selection step.

3. Honest flag (outside the weighting lever): two NON-weighting levers do show
   robust in-sample edges that survive both windows + sequential OOS --
   (a) lengthening the inv-vol lookback 252->504, and (b) a min-var subset
   SELECTION step. Both were previously evaluated and deliberately dropped from
   prod for parsimony (single-stage, both-252). They are SELECTION/estimation
   levers, not weighting; relitigating them is outside this mandate. Their
   existence reinforces the core finding: whatever value correlation has is
   upstream (selection), and the WEIGHTING step is correctly left as inverse-vol.

## Caveats / confidence

- Single in-sample full-window evaluation; all bootstrap CIs include 0 (low
  ceiling held strictly). No metric here would justify a weighting change.
- Look-ahead controls: mooex T+1 MOO exact opens, cov windows strictly trailing
  (`tail(lookback)` up to sig_d), monthly resample on `loc[:sig_d]`. 10 bps/side
  applied to all returns; turnover reported (corr methods churn ~12-16% more
  one-way annualized).
- HRP n<=2 falls back to inverse-vol by construction; with top-4 picks HRP only
  differentiates when n_picks in {3,4}.
- EXT pre-2008 leans on stitched proxies (lower confidence on absolute EXT
  levels; directional cross-cell comparison is sound).
- Confidence HIGH that inv-vol is the right weighting default; HIGH that ERC does
  not beat it; MEDIUM-HIGH that HRP's clean edge is a GFC-era artifact (clear OOS
  failure + ext loss).

## Knowledge candidate

Corr/cov-aware WEIGHTING (ERC/HRP) does NOT beat CPM inverse-vol net of cost +
OOS: ERC loses at matched lookback and ties at 504 (lookback confound, not
correlation); HRP wins clean only as a GFC-era artifact and fails ext +
sequential OOS. ERC cannot replace min-var selection (no gain on rank-select; no
add on top of min-var). Correlation's value is upstream in SELECTION, not
WEIGHTING. Inverse-vol confirmed as the robust weighting default.
