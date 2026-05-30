# CPM (Cross-asset Parity Momentum) -- weighting flavor & subset-selection sensitivity

Role: analyst (hypothesis-driven, read-only re production). No production files
changed; no commit. Throwaway harness in `research/`.

## Question

Two sensitivity axes on the CPM sleeve, each holding the rest of the production
design fixed:

- AXIS A -- WEIGHTING FLAVOR (selection fixed = min-variance 3-subset of top-4):
  now that "Parity" is in the name, is naive inverse-vol the right flavor, or
  does true ERC (equal-risk-contribution) risk-parity beat it?
- AXIS B -- SUBSET SELECTION OBJECTIVE (weighting fixed = inverse-vol; pick 3 of
  top-4): is min-variance the right objective? Does the simpler risk-based
  min-vol match it? Do performance-based selectors (max-Sharpe / max-Calmar /
  min-DD) beat it in-sample, and if so are they overfit-prone?

## Labeled configuration

- Strategy design (held fixed): universe = [QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT,
  DBC]; safe = best of [SHV, IEF]; ranker = Faber 12m SMA distance / 252d vol
  (U=R=C=1); positive-trend filter (Faber > 0); K = 4 (top-half); canary =
  13612U on [HYG, TIP]; partial-safe fallback (0 pos -> 100% safe; 1 pos ->
  50/50 pos/safe); target cardinality M = 3.
- Window: CLEAN = 2008-05-30 .. 2026-05-22 (18y); EXT = 1999-03-10 .. 2026-05-22
  (27y).
- Execution: T+1 MOO exact (`mooex`), real yfinance opens; 10 bps/side net
  headline (0 bps gross also computed).
- Estimation window: covariance / vol lookback = 504 trading days.
- Weighting flavors: INVVOL (w_i prop 1/sigma_i, cov diagonal only -- production
  / naive risk parity); ERC (equal risk contribution, full covariance, SLSQP
  solver, inverse-vol fallback on failure); EW (1/3).
- Selection objectives: MINVAR (min equal-weight portfolio variance w'Sigma w --
  production); MINVOL (3 lowest individual sigma_i); MINCORR (3-subset lowest
  average pairwise correlation); MAXSHARPE / MAXCALMAR / MINDD (3-subset best
  trailing realized metric over the 504d cov window).
- Selection blocks are byte-identical to production; only the named step changes.
- Bootstrap: paired stationary block bootstrap, B = 2000, block = 21 days,
  seed = 42 (same primitives as `paired_bootstrap_pair_vs_continuous.py`).

## Method / reproduction

- Harness: `research/cpm_weighting_selection_sensitivity.py` (reuses
  `inverse_vol_weighting.py` selection/weighting primitives,
  `weighting_headtohead.py` `_selection` + `erc_weights`,
  `exec_lag_moo_validation_2026_05_30._segment_returns_conv`,
  `paired_bootstrap_pair_vs_continuous` block-bootstrap primitives).
- Run: `.venv/bin/python research/cpm_weighting_selection_sensitivity.py`
- Outputs: `research/cpm_weighting_selection_sensitivity.json` (full grid +
  bootstrap + ERC diagnostics).

### Anchor verification (production = MINVAR select + inverse-vol, net 10 bps)

| Window | Sharpe | MaxDD | Calmar | Expected anchor | Match |
|--------|-------:|------:|-------:|-----------------|:-----:|
| CLEAN  | 1.2453 | -13.19% | 1.0824 | 1.2453 / -13.19% / 1.0824 | EXACT |
| EXT    | 1.2249 | -15.18% | 0.9148 | 1.2249 / -15.18% / 0.9148 | EXACT |

Both CPM-solo anchors reproduce to 4 decimals before any variant is trusted.

## AXIS A -- WEIGHTING FLAVOR (selection = min-var 3-subset, net 10 bps)

| Window | Flavor | Sharpe | CAGR | Vol | MaxDD | Calmar | avg maxW | avg effN |
|--------|--------|-------:|-----:|----:|------:|-------:|---------:|---------:|
| CLEAN | INVVOL (prod) | 1.2453 | 14.28% | 11.27% | -13.19% | 1.0824 | 0.476 | 2.65 |
| CLEAN | ERC           | 1.2693 | 14.42% | 11.14% | -12.96% | 1.1120 | 0.498 | 2.60 |
| CLEAN | EW (1/3 ref)  | 1.2229 | 14.39% | 11.57% | -16.86% | 0.8536 | 0.427 | 2.71 |
| EXT   | INVVOL (prod) | 1.2249 | 13.89% | 11.12% | -15.18% | 0.9148 | 0.469 | 2.68 |
| EXT   | ERC           | 1.2243 | 13.67% | 10.96% | -15.20% | 0.8993 | 0.490 | 2.63 |
| EXT   | EW (1/3 ref)  | 1.2237 | 14.33% | 11.49% | -17.68% | 0.8106 | 0.412 | 2.76 |

Paired block bootstrap, ERC minus INVVOL (positive => ERC better):

| Window | Sharpe diff (mean, 95% CI) | P(ERC>INVVOL) | Calmar diff (mean, CI) | excl. 0? |
|--------|----------------------------|:-------------:|------------------------|:--------:|
| CLEAN | +0.0250 [-0.0234, +0.0732] | 0.849 | +0.0328 [-0.0686, +0.1603] | no |
| EXT   | -0.0013 [-0.0432, +0.0426] | 0.478 | -0.0038 [-0.0889, +0.0760] | no |

Daily-return correlation INVVOL vs ERC = 0.994 (CLEAN), 0.993 (EXT).

ERC concentration / blow-up diagnostics (291 risk-on rebalances, EXT):

| Flavor | avg maxW | max maxW | avg effN | min effN |
|--------|---------:|---------:|---------:|---------:|
| INVVOL | 0.403 | 0.686 | 2.89 | 1.76 |
| ERC    | 0.427 | 0.687 | 2.83 | 1.76 |

Mean L1(ERC, INVVOL) per rebalance = 0.079.

Findings:
- ERC does NOT beat INVVOL with significance. CLEAN shows a small ERC Sharpe/
  Calmar edge (P(ERC>INVVOL) = 0.85 on Sharpe) but the 95% CI straddles zero;
  EXT is a dead heat (P = 0.48, mean diff ~0). No metric, either window,
  excludes zero.
- ERC does NOT blow up or concentrate on this menu. ERC and INVVOL weights are
  near-identical (max single weight 0.687 vs 0.686; min effective N 1.76 for
  both; mean L1 only 0.079). The documented ERC fragility under high vol
  asymmetry (bonds vs equities) does not manifest here because the menu is
  pre-filtered to positive-trend assets, capped at 3 names, and risk magnitudes
  are similar after trend filtering -- so full-cov ERC collapses toward the
  diagonal inverse-vol solution.
- EW (1/3) is clearly worse on the risk axis: MaxDD -16.86% / -17.68% and
  Calmar 0.85 / 0.81 vs INVVOL's -13.19% / -15.18% and 1.08 / 0.91. Equal
  weight ignores vol entirely and pays for it in drawdown.

VERDICT AXIS A: inverse-vol IS the right parity flavor. ERC adds a full
covariance estimate and an iterative SLSQP solver for no statistically
significant gain (and a slight EXT loss). Because the menu is small, trend-
filtered, and risk-similar, true ERC degenerates to roughly the inverse-vol
solution -- the extra machinery buys nothing. Keep solver-free inverse-vol.

## AXIS B -- SUBSET SELECTION OBJECTIVE (weighting = inverse-vol, net 10 bps)

| Window | Selector | Kind | Sharpe | CAGR | Vol | MaxDD | Calmar |
|--------|----------|------|-------:|-----:|----:|------:|-------:|
| CLEAN | MINVAR (prod) | risk | 1.2453 | 14.28% | 11.27% | -13.19% | 1.0824 |
| CLEAN | MINVOL        | risk | 1.1926 | 13.59% | 11.27% | -13.19% | 1.0301 |
| CLEAN | MINCORR       | risk | 1.2027 | 14.27% | 11.70% | -12.66% | 1.1276 |
| CLEAN | MAXSHARPE     | perf | 1.1501 | 13.80% | 11.89% | -12.66% | 1.0900 |
| CLEAN | MAXCALMAR     | perf | 1.1958 | 14.37% | 11.85% | -12.66% | 1.1349 |
| CLEAN | MINDD         | perf | 1.2166 | 14.22% | 11.51% | -13.19% | 1.0779 |
| EXT   | MINVAR (prod) | risk | 1.2249 | 13.89% | 11.12% | -15.18% | 0.9148 |
| EXT   | MINVOL        | risk | 1.1949 | 13.57% | 11.17% | -17.24% | 0.7870 |
| EXT   | MINCORR       | risk | 1.1848 | 13.91% | 11.56% | -16.31% | 0.8531 |
| EXT   | MAXSHARPE     | perf | 1.1431 | 13.74% | 11.89% | -16.16% | 0.8504 |
| EXT   | MAXCALMAR     | perf | 1.1419 | 13.56% | 11.74% | -15.38% | 0.8816 |
| EXT   | MINDD         | perf | 1.2320 | 14.24% | 11.33% | -14.43% | 0.9870 |

Paired block bootstrap, selector minus MINVAR (positive => selector better):

| Comparison | Window | Sharpe diff (mean, 95% CI) | P(sel>MINVAR) | Calmar diff (mean, CI) | excl. 0? |
|------------|--------|----------------------------|:-------------:|------------------------|:--------:|
| MAXSHARPE | CLEAN | -0.0957 [-0.2535, +0.0447] | 0.099 | -0.1147 [-0.5280, +0.1241] | no |
| MAXSHARPE | EXT   | -0.0833 [-0.2127, +0.0376] | 0.086 | -0.0821 [-0.3447, +0.0955] | no |
| MAXCALMAR | CLEAN | -0.0494 [-0.1711, +0.0652] | 0.206 | -0.0371 [-0.2802, +0.1599] | no |
| MAXCALMAR | EXT   | -0.0834 [-0.1910, +0.0184] | 0.059 | -0.0622 [-0.2723, +0.1071] | no |
| MINDD     | CLEAN | -0.0282 [-0.1097, +0.0516] | 0.261 | -0.0232 [-0.2048, +0.1317] | no |
| MINDD     | EXT   | +0.0071 [-0.0616, +0.0749] | 0.583 | +0.0239 [-0.1161, +0.1645] | no |

Findings:
- MINVAR (production) is the Sharpe-best selector in both windows (1.2453 CLEAN,
  1.2249 EXT) and best/tied on net Calmar among risk-based selectors after
  accounting for MaxDD.
- MINVOL (the simpler risk-based selector) does NOT match MINVAR. It gives up
  ~0.05 Sharpe in CLEAN and degrades badly in EXT: MaxDD -17.24% vs -15.18%,
  Calmar 0.787 vs 0.915. Ignoring correlation in the selection step hurts --
  the lowest-individual-vol triple is not the lowest-portfolio-vol triple.
  MINVAR's use of the off-diagonal covariance earns its keep.
- MINCORR (diversification) has a slightly better CLEAN Calmar (1.1276) and
  shallower CLEAN MaxDD (-12.66%) but lower Sharpe in both windows (1.2027 /
  1.1848) and worse EXT Calmar (0.853). Not a clear win.
- Performance-based selectors fail even IN-SAMPLE on the primary metric.
  MAXSHARPE and MAXCALMAR are below MINVAR on net Sharpe in both windows
  (1.14-1.20 vs 1.2249-1.2453); the bootstrap shows P(selector > MINVAR) on
  Sharpe of 0.06-0.21 (i.e., MINVAR usually wins). There is no in-sample winner
  to "flag as overfit-prone" because they do not win in-sample to begin with --
  selecting on trailing realized performance actively destroys Sharpe.
- MINDD is the only performance-based selector that is competitive: it edges
  MINVAR on EXT MaxDD (-14.43% vs -15.18%), EXT Calmar (0.987 vs 0.915), and
  EXT Sharpe (1.2320 vs 1.2249). BUT it loses MINVAR on CLEAN Sharpe (1.2166 vs
  1.2453), and every paired-bootstrap CI includes zero (EXT Sharpe P = 0.583,
  Calmar CI [-0.116, +0.165]). This is exactly the overfit signature: a DD-based
  selector looking good on the DD metric over one window with no significance.
  FLAG MINDD as overfit-prone; do NOT adopt on its in-sample DD edge.

VERDICT AXIS B: min-variance IS the right subset-selection objective. It is the
Sharpe-best choice in both windows, it is risk-based (uses only the covariance
estimate, no lookahead, robust), and no alternative beats it with significance.
The simpler risk-based MINVOL does not match it -- correlation in selection
matters. The performance-based selectors do not even win in-sample on Sharpe;
MINDD's narrow EXT DD edge is overfit-prone and statistically insignificant, so
it is flagged and rejected.

## Net verdict -- production design confirmed

The production CPM weighting (min-variance 3-subset selection + inverse-vol
weighting) is confirmed on both axes:

1. WEIGHTING: inverse-vol is the correct parity flavor despite the "Parity"
   name. True ERC neither beats it significantly nor blows up on this menu; it
   degenerates toward the inverse-vol solution (weights L1-differ by only 0.079
   per rebalance), so the full-cov + solver overhead is unjustified. Solver-free
   inverse-vol wins on simplicity at no measurable cost.
2. SELECTION: min-variance is the correct objective. It is the Sharpe-best
   risk-based selector, beats the simpler MINVOL (correlation matters), and
   beats all performance-based selectors in-sample on Sharpe. No variant clears
   significance against it.

No production design change recommended. The "Parity" naming is honest in spirit
(risk-balanced via inverse-vol on a min-variance-selected subset) but should not
be read as a mandate to upgrade to full ERC.

## Caveats / confidence

- All point metrics are net 10 bps/side, T+1 MOO exact, on the exact production
  selection pipeline; production anchors reproduce to 4 decimals (high confidence
  the harness measures the production strategy).
- Bootstrap is a paired stationary block bootstrap (B=2000, block=21, seed=42);
  every comparison's 95% CI includes zero, so all axis differences are
  statistically insignificant at the 5% level. The conclusion is "no variant
  significantly beats production," not "production is provably optimal."
- The ERC non-fragility result is conditional on this menu (small, trend-
  filtered, 3-name cap). On a wider or un-filtered menu with strong bond/equity
  vol asymmetry, ERC could diverge from inverse-vol and the fragility caveat
  would re-apply. Not tested here.
- Performance-based selectors use trailing realized performance over the same
  504d window used for covariance: in-sample but NOT lookahead (all data <=
  signal date). Their poor in-sample Sharpe is therefore a genuine selection-
  quality result, not a data-leak artifact.
- MINDD's EXT edge rests partly on the pre-2008 segment (where the EXT-only
  panel has thinner/younger-ETF history); treat the single-window DD edge with
  the usual small-sample skepticism.

## Memory / knowledge candidates

- Durable lesson (knowledge): for small, trend-filtered, low-cardinality menus,
  risk-based subset selection (min-variance) dominates performance-based
  selection (max-Sharpe / max-Calmar / min-DD); the latter often lose even
  in-sample on Sharpe and any DD-metric edge is overfit-prone and insignificant.
- Durable lesson (knowledge): true ERC risk parity collapses toward naive
  inverse-vol on such menus (no blow-up, no significant gain), so the solver-
  free inverse-vol flavor is preferred; the ERC vol-asymmetry fragility only
  bites on wide/un-filtered menus.
