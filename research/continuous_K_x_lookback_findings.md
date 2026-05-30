# Continuous min-variance: K x covariance-lookback robustness map

Analyst, hypothesis-driven, read-only re production. No production files touched, no commit.
Throwaway artifact in `research/`.

## Config / window / execution (labels)

- Config: CPM sleeve, U=R=C on (production universe / ranker / canary). Weighting =
  CONTINUOUS minimum-variance (SLSQP, long-only, sum-to-1) over the top-K trend-qualified
  candidates -- NOT the 50/50 pair. K = top-K momentum candidate pool size; cov lookback =
  rolling daily-return covariance window (annualized).
- Universe: QQQ SPHQ EFA EEM VNQ GLD TLT DBC; safe pool SHV/IEF; canary HYG-or-TIP any-positive.
- Grid: K in {2,3,4,5,6} x cov lookback in {126,252,504,756,1008,1260} = 30 cells.
- Execution: T+1 MOO exact (mooex), 10 bps/side, net.
- Windows: CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22).
- Harness: `research/continuous_K_x_lookback.py` (reuses pair_vs_continuous_minvar /
  pair_vs_continuous_by_covlookback / cardinality_sweep selection+execution machinery;
  only K and cov lookback parametrized). JSON: `research/continuous_K_x_lookback.json`.

## 5. Anchor (verify before trusting other cells) -- PASS

K=4 / 504d continuous, CLEAN, 10 bps reproduces the production headline EXACTLY:

```
continuous: sharpe=1.2935  maxdd=-15.15%  calmar=0.9618   (expect 1.2935 / -15.15% / 0.9618)
```

All other cells are computed by the same code path; anchor match validates the grid.

## 1. Full K x lookback grid

### CLEAN (18y) -- net Sharpe

```
K\lb       126       252       504       756      1008      1260
K=2     0.7252    0.7532    0.8050    0.8177    0.8164    0.8185
K=3     1.0216    0.9964    1.0115    1.0139    0.9997    0.9975
K=4     1.1757    1.2154   *1.2935*   1.2734    1.2490    1.2494
K=5     1.2040    1.2049    1.2488    1.2485    1.2221    1.2167
K=6     1.1425    1.1492    1.2044    1.2052    1.1912    1.1675
```

### CLEAN (18y) -- Calmar

```
K\lb       126       252       504       756      1008      1260
K=2     0.4102    0.4177    0.4630    0.4737    0.4880    0.4898
K=3     0.7773    0.7608    0.7929    0.7631    0.7684    0.7684
K=4     0.8459    0.8794   *0.9618*   0.9067    0.9133    0.9169
K=5     0.8248    0.8328    0.8825    0.8461    0.8500    0.8473
K=6     0.7548    0.7649    0.8145    0.7829    0.7959    0.7833
```

### CLEAN (18y) -- MaxDD (%)

```
K\lb       126       252       504       756      1008      1260
K=2    -22.11    -22.86    -22.53    -22.50    -21.91    -21.90
K=3    -15.27    -15.37    -15.15    -15.86    -15.63    -15.63
K=4    -15.27    -15.37   *-15.15*   -15.86    -15.63    -15.63
K=5    -15.27    -15.37    -15.15    -15.86    -15.63    -15.63
K=6    -15.27    -15.37    -15.15    -15.86    -15.63    -15.63
```

### EXT (27y) -- net Sharpe

```
K\lb       126       252       504       756      1008      1260
K=2     0.8204    0.8372    0.8640    0.8582    0.8554    0.8565
K=3     1.0517    1.0236    1.0139    1.0034    0.9967    0.9915
K=4     1.1498    1.1696    1.2091    1.1869    1.1779    1.1655
K=5     1.1780    1.1629    1.1752    1.1708    1.1655    1.1582
K=6    [1.2109]   1.1816    1.1942    1.1853    1.1918    1.1725
```
(`[ ]` = EXT global-best Sharpe; K=4/504 = 1.2091 is #2, gap 0.0018 = noise.)

### EXT (27y) -- Calmar

```
K\lb       126       252       504       756      1008      1260
K=2     0.4809    0.4791    0.5097    0.5085    0.5235    0.5292
K=3     0.7892    0.7692    0.7840    0.7459    0.7538    0.7561
K=4     0.8056    0.8221   *0.8760*   0.8260    0.8300    0.8285
K=5     0.7843    0.7775    0.8069    0.7710    0.7885    0.7842
K=6     0.7762    0.7613    0.7904    0.7326    0.7774    0.7663
```

### EXT (27y) -- MaxDD (%)

```
K\lb       126       252       504       756      1008      1260
K=2    -22.11    -22.86    -22.53    -22.50    -21.91    -21.90
K=3    -15.27    -15.37    -15.15    -15.86    -15.74    -15.65
K=4    -15.27    -15.37    -15.15    -15.86    -15.92    -15.82
K=5    -15.27    -15.37    -15.15    -15.86    -15.63    -15.63
K=6    -15.27    -15.37    -15.15    -16.32    -15.63    -15.63
```

## 2. Optimal cells vs production (K=4, 504d)

| Window | Best Sharpe cell | Best Calmar cell | Prod K=4/504 Sharpe (rank) | Prod K=4/504 Calmar (rank) |
|--------|------------------|------------------|----------------------------|----------------------------|
| CLEAN  | K=4/504 (1.2935) | K=4/504 (0.9618) | 1.2935 (#1 / 30)           | 0.9618 (#1 / 30)           |
| EXT    | K=6/126 (1.2109) | K=4/504 (0.8760) | 1.2091 (#2 / 30)           | 0.8760 (#1 / 30)           |

- On CLEAN, the production cell (K=4, 504d) is the GLOBAL optimum on BOTH Sharpe and Calmar.
- On EXT, the production cell is the #1 Calmar cell and the #2 Sharpe cell; the nominal EXT
  Sharpe winner K=6/126 beats it by 0.0018 (1.2109 vs 1.2091) -- inside noise, and that cell
  is materially worse on Calmar (0.7762 vs 0.8760).
- Answer to "does continuous prefer a larger K since it can optimize over more assets?": NO.
  Continuous does not push toward larger K. K=4 is the joint Sharpe+Calmar sweet spot in both
  windows. K=5 and K=6 are slightly lower on risk-adjusted terms (and clearly lower on Calmar),
  because adding 5th/6th momentum candidates dilutes the trend signal faster than the optimizer
  gains diversification. K=4/504 chosen under the pair regime remains right under continuous.

## 3. Robustness / spread across the grid

Min-max spread across all 30 cells:

| Window | Sharpe spread | Calmar spread | MaxDD spread (pp) |
|--------|---------------|---------------|-------------------|
| CLEAN  | 0.5683 (0.7252..1.2935) | 0.5517 (0.4102..0.9618) | 7.72 (-22.86..-15.15) |
| EXT    | 0.3906 (0.8204..1.2109) | 0.3969 (0.4791..0.8760) | 7.72 (-22.86..-15.15) |

Almost all of the spread is the degenerate K=2 row (pool too small to diversify; pair-only
behaviour, ~22% DD). Excluding K=2 (K in {3,4,5,6}):

| Window | Sharpe spread | Calmar spread |
|--------|---------------|---------------|
| CLEAN  | 0.2971        | 0.2071        |
| EXT    | 0.2194        | 0.1433        |

Structure:
- K is the dominant axis, lookback is secondary. Row-mean Sharpe by K: CLEAN {2:0.79, 3:1.01,
  4:1.24, 5:1.22, 6:1.18}; EXT {2:0.85, 3:1.01, 4:1.18, 5:1.17, 6:1.19}. Smooth, single-peaked
  at K=4 (CLEAN) / flat plateau K=4-6 (EXT).
- Lookback axis is FLAT. Within K=4, CLEAN Sharpe over 252..1260 sits in 1.2154..1.2935
  (504 best, 126 the only weak one); EXT 1.1655..1.2091. MaxDD is essentially lookback-driven
  and identical across K for K>=3 (-15.1% to -15.9%).
- No cliffs. The classic overfit-fear corner (short lookback x large K, i.e. K=6/126) is NOT
  fragile: it is EXT's best-Sharpe cell (1.2109) and a healthy CLEAN cell (1.1425). The
  continuous optimizer degrades gracefully everywhere.
- Conclusion: continuous is broadly robust. The whole K>=3 region is a stable plateau within
  ~0.2-0.3 Sharpe; the only weak band is K=2, which is a too-small-pool artifact, not a
  continuous-weighting fragility.

## 4. Concentration check (corner-solution / overfit test)

Avg / max single-asset risk-on weight (%), and avg effective-N = 1/HHI, risk-on months:

CLEAN
```
K\lb        126        252        504        756       1008       1260
K=2  74/100/1.6 74/100/1.6 74/100/1.6 74/100/1.6 74/100/1.6 74/100/1.6
K=3  63/100/2.0 63/100/2.0 67/100/1.9 66/100/1.9 66/100/1.9 66/100/1.9
K=4  58/100/2.2 59/100/2.2 63/100/2.1 63/100/2.1 63/100/2.1 63/100/2.1
K=5  54/100/2.4 54/100/2.4 58/100/2.2 58/100/2.2 58/100/2.2 57/100/2.3
K=6  52/100/2.6 53/100/2.5 56/100/2.4 56/100/2.4 55/100/2.4 55/100/2.4
```
EXT
```
K\lb        126        252        504        756       1008       1260
K=2  74/100/1.6 73/100/1.6 73/100/1.6 73/100/1.6 73/100/1.6 73/100/1.6
K=3  63/100/2.0 63/100/2.0 65/100/1.9 65/100/2.0 65/100/2.0 65/100/2.0
K=4  58/100/2.2 58/100/2.2 60/100/2.2 61/100/2.2 61/100/2.2 61/100/2.2
K=5  54/100/2.4 54/100/2.4 56/100/2.3 57/100/2.3 57/100/2.4 56/100/2.4
K=6  52/100/2.6 53/100/2.5 54/100/2.5 55/100/2.5 54/100/2.5 54/100/2.6
```

- The overfit hypothesis (larger K + short lookback -> corner solutions) is REJECTED.
  Avg risk-on concentration DECREASES monotonically with K (K=2 ~74% -> K=6 ~52-56%) and
  effective-N RISES (1.6 -> 2.6). More candidates means the optimizer spreads risk wider,
  not narrower.
- Short lookback does NOT concentrate more -- if anything slightly less (e.g. K=4: 126d ~58%
  vs 504d ~60-63%). So short-cov-window x large-K is the LEAST concentrated corner, opposite
  of the corner-solution worry.
- The max single weight = 100% in every cell is a low-breadth FALLBACK artifact (months with
  one surviving positive-trend candidate force a single-asset / partial-safe holding),
  identical across the grid -- it is not a continuous-optimizer corner solution and does not
  vary with K or lookback.

## Verdict

- Under continuous weighting the robust choice is STILL K=4 / 504d -- the same as the pair-era
  default. It is the CLEAN global optimum on both Sharpe (1.2935) and Calmar (0.9618), the EXT
  global Calmar optimum (0.8760), and the EXT #2 Sharpe cell (1.2091, behind K=6/126 by 0.0018,
  i.e. tied within noise). No re-tuning needed when moving from pair to continuous weighting.
- Continuous does NOT prefer a larger K despite optimizing weights over more assets: K=4 is the
  joint risk-adjusted peak; K>=5 dilutes momentum faster than diversification helps (clearly so
  on Calmar). K=4 is a principled, not accidental, choice for continuous.
- Continuous is broadly robust across the grid -- a stable K>=3 plateau (excl-K=2 Sharpe spread
  0.22-0.30), a flat lookback axis (252-1260 near-identical, only 126d marginally soft), no
  cliffs, and graceful behaviour even in the short-lookback x large-K corner. Concentration is
  well-behaved and improves (lower, more diversified) as K grows. This supports continuous
  min-variance at K=4/504 as a sound production CPM default.
- Only weak region: K=2 (too-small pool, ~0.72-0.86 Sharpe, ~22% DD). That is a pool-size
  artifact, not a continuous-weighting fragility, and is well clear of the recommended K=4.

## Caveats / confidence

- Confidence: HIGH. Anchor reproduces the production headline exactly (1.2935 / -15.15% /
  0.9618); the K x lookback surface is smooth, single-peaked in K, and flat in lookback -- no
  signs of estimation-error blow-up or corner overfit.
- Single execution convention (T+1 MOO exact, 10 bps/side); not re-tested under other cost/exec
  assumptions (out of this task's scope; pair_vs_continuous_minvar already mapped cost sweeps).
- In-sample over the full 27y/18y windows; this is a parameter-robustness map, not a
  walk-forward OOS test. The flatness of the surface is itself the robustness evidence.
- max-single-weight = 100% reflects low-breadth fallback months, not optimizer corner solutions;
  avg risk-on weight and effective-N are the informative concentration metrics.

## Next handoff

None required for the analysis. If continuous min-var is to be adopted as the production CPM
weighting, route the production-code change (weighting swap, K=4/504 retained) to the fixer and
the release/risk decision to the oracle.
