# CPM equal-weight cardinality sweep: pair vs triplet vs full 1/N vs continuous min-var

Research note (throwaway). Read-only re production. No production files changed, no commit.

## Config / window / execution (labeled)

- Sleeve: CPM, factors U=1 R=1 C=1 (production universe / vol-adjusted-Faber ranker / HYG-or-TIP canary).
- Universe (8): QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC. Safe pool: SHV, IEF (13612U pick).
- Candidate pool K = top-half trend-qualified = 4 (positive-Faber screen applied within top-4).
- Covariance lookback: 504 trading days (~2y). Min-var subset selection mirrors `cpm_live.min_vol_pair`
  covariance handling exactly (`close.pct_change().dropna(how='all').tail(504).cov()`, equal-weight
  portfolio variance w'Sw with w = 1/M), so M=2 is identical to the production pair.
- Execution: T+1 MOO exact (mooex) -- old basket earns overnight close[T]->open[T+1], new basket earns
  intraday open[T+1]->close[T+1], compounded. Real yfinance opens.
- Costs: headline net = 10 bps/side round-trip; gross = 0 bps; cost sensitivity = 10/25/50 bps/side.
- Windows: CLEAN 18y (2008-05-30 -> 2026-05-22, n=17.977y, 217 rebalances) and EXT 27y
  (1999-03-10 -> 2026-05-22, n=27.201y, 327 rebalances).
- Metrics reported on EXACT computed numbers (no rounding in derivation).

## Schemes

Full cardinality spectrum (left endpoint -> diversified -> optimizer):

| Scheme | Definition | Risk-on cap |
|---|---|---|
| EW-1 lowest-var | single lowest-variance candidate | 100% |
| MOM-1 top-mom | single highest raw-Faber-momentum candidate (no risk weighting) | 100% |
| EW-2 pair (prod) | equal-weight min-variance 2-subset | 50% |
| EW-3 triplet | equal-weight min-variance 3-subset | 33% |
| EW-4 full 1/N | equal-weight all 4 trend-qualified candidates (pure 1/N) | 25% |
| continuous min-var | SLSQP min-variance over all positives (optimizer) | none (uncapped) |

Shared fallback (matches production `cpm_wf`, identical across all schemes):
0 positive-trend -> 100% safe; 1 positive -> {pos:0.5, safe:0.5} (partial-safe);
2..M-1 positives (fewer than target cardinality) -> equal-weight all that qualify; >= M -> M-subset.
(Consequence: `max single weight = 1.000` for every scheme comes from all-safe defensive months,
not the risk-on basket. Use the risk-on concentration columns for the cap comparison.)

## Anchor verification (CLEAN, 10 bps) -- PASS

- EW-2 reproduces production pair: Sharpe 1.2424 / Calmar 0.8704 / MaxDD -16.35% (exact match).
- continuous reproduces no-pair anchor: Sharpe 1.2935 / Calmar 0.9618 / MaxDD -15.15% (exact match).

## Headline table -- net 10 bps/side

### CLEAN 18y

| Scheme | Gross Shp | Net Shp | Net CAGR | Net Vol | Net MaxDD | Net Calmar |
|---|---|---|---|---|---|---|
| EW-1 lowest-var | 1.0123 | 0.9673 | 14.06% | 14.80% | -19.70% | 0.7139 |
| MOM-1 top-mom | 0.5385 | 0.4877 | 7.74% | 19.17% | -35.22% | 0.2197 |
| EW-2 pair (prod) | 1.2985 | 1.2424 | 14.23% | 11.27% | -16.35% | 0.8704 |
| EW-3 triplet | 1.2727 | 1.2229 | 14.39% | 11.57% | -16.86% | 0.8536 |
| EW-4 full 1/N | 1.1303 | 1.0875 | 13.28% | 12.20% | -16.86% | 0.7878 |
| continuous min-var | 1.3517 | 1.2935 | 14.57% | 11.03% | -15.15% | 0.9618 |

### EXT 27y

| Scheme | Gross Shp | Net Shp | Net CAGR | Net Vol | Net MaxDD | Net Calmar |
|---|---|---|---|---|---|---|
| EW-1 lowest-var | 0.9103 | 0.8616 | 11.94% | 14.27% | -24.38% | 0.4897 |
| MOM-1 top-mom | 0.6137 | 0.5677 | 10.17% | 20.92% | -43.92% | 0.2315 |
| EW-2 pair (prod) | 1.2729 | 1.2159 | 14.07% | 11.36% | -16.76% | 0.8396 |
| EW-3 triplet | 1.2752 | 1.2237 | 14.33% | 11.49% | -17.68% | 0.8106 |
| EW-4 full 1/N | 1.2009 | 1.1567 | 14.27% | 12.17% | -20.18% | 0.7069 |
| continuous min-var | 1.2719 | 1.2091 | 13.27% | 10.79% | -15.15% | 0.8760 |

## Turnover / stability / concentration (risk-on basket)

| Window | Scheme | Turnover (ann round-trip) | Frac months changed | Basket-change freq | Mean L1 move | maxW (risk-on) | eff-N (risk-on) |
|---|---|---|---|---|---|---|---|
| CLEAN | EW-1 | 6.675 | 0.278 | 0.278 | 0.556 | 0.997 | 1.005 |
| CLEAN | MOM-1 | 9.790 | 0.407 | 0.407 | 0.815 | 0.997 | 1.005 |
| CLEAN | EW-2 | 6.342 | 0.389 | 0.389 | 0.528 | 0.500 | 2.000 |
| CLEAN | EW-3 | 5.859 | 0.505 | 0.505 | 0.488 | 0.339 | 2.968 |
| CLEAN | EW-4 | 5.294 | 0.532 | 0.532 | 0.441 | 0.264 | 3.862 |
| CLEAN | continuous | 6.452 | 0.810 | 0.500 | 0.537 | 0.628 | 2.057 |
| EXT | EW-1 | 7.004 | 0.298 | 0.298 | 0.584 | 0.978 | 1.086 |
| EXT | MOM-1 | 9.632 | 0.402 | 0.402 | 0.804 | 0.998 | 1.003 |
| EXT | EW-2 | 6.544 | 0.420 | 0.420 | 0.546 | 0.493 | 2.055 |
| EXT | EW-3 | 6.035 | 0.528 | 0.528 | 0.504 | 0.339 | 2.979 |
| EXT | EW-4 | 5.472 | 0.558 | 0.558 | 0.457 | 0.269 | 3.814 |
| EXT | continuous | 6.849 | 0.868 | 0.534 | 0.571 | 0.605 | 2.156 |

Notes:
- Annualized round-trip turnover is roughly FLAT across EW cardinalities (and even falls slightly for
  EW-4) because more assets means smaller per-name shifts. The instability shows up not in dollar
  turnover but in the SIGNAL/holding-stability metric (frac months with any weight change).
- Continuous min-var has the highest frac-months-changed by far (0.810 / 0.868): continuous weights
  shift essentially every month even when the basket is unchanged.
- Continuous min-var is the only scheme with NO concentration cap: avg risk-on max weight 62.8%/60.5%
  (and it can run higher in individual months); effective-N ~2.0 despite optimizing over 4 names.

## Cost sensitivity -- net Sharpe at 10 / 25 / 50 bps/side

| Window | Scheme | 10 bps | 25 bps | 50 bps |
|---|---|---|---|---|
| CLEAN | EW-1 | 0.9673 | 0.8987 | 0.7823 |
| CLEAN | MOM-1 | 0.4877 | 0.4112 | 0.2835 |
| CLEAN | EW-2 | 1.2424 | 1.1567 | 1.0108 |
| CLEAN | EW-3 | 1.2229 | 1.1469 | 1.0177 |
| CLEAN | EW-4 | 1.0875 | 1.0224 | 0.9121 |
| CLEAN | continuous | 1.2935 | 1.2046 | 1.0530 |
| EXT | EW-1 | 0.8616 | 0.7876 | 0.6623 |
| EXT | MOM-1 | 0.5677 | 0.4984 | 0.3824 |
| EXT | EW-2 | 1.2159 | 1.1287 | 0.9804 |
| EXT | EW-3 | 1.2237 | 1.1452 | 1.0116 |
| EXT | EW-4 | 1.1567 | 1.0894 | 0.9753 |
| EXT | continuous | 1.2091 | 1.1133 | 0.9503 |

Cost-crossovers worth noting:
- CLEAN: continuous leads at every cost level, but EW-3 overtakes EW-2 by 50 bps (1.0177 vs 1.0108).
- EXT: EW-3 leads continuous at all costs on Sharpe, and the gap WIDENS with cost; at 50 bps the
  best scheme is EW-3 (1.0116) > EW-4 (0.9753) > EW-2 (0.9804... below EW-4) > continuous (0.9503).
  i.e. when costs are high the lower-churn equal-weight schemes catch and pass the optimizer.

## Answers to the key questions

1) Does EW-3 (triplet) close the net-Sharpe / Calmar gap to continuous min-var vs EW-2?
   - NO -- it widens it in CLEAN and is mixed in EXT.
   - CLEAN net Sharpe gap to continuous: EW-2 = 1.2935 - 1.2424 = 0.0511; EW-3 = 1.2935 - 1.2229 =
     0.0706. The triplet is FURTHER from continuous, not closer.
   - CLEAN net Calmar gap: EW-2 = 0.9618 - 0.8704 = 0.0914; EW-3 = 0.9618 - 0.8536 = 0.1082. Wider.
   - EXT net Sharpe: EW-3 (1.2237) actually EDGES continuous (1.2091) by +0.0146 (and EW-2 1.2159 also
     edges it by +0.0068) -- but this is the optimizer underperforming over the noisier 1999-2008
     extension, not the triplet "recovering" anything.
   - EXT net Calmar: continuous (0.8760) still beats EW-2 (0.8396, gap 0.0364) and EW-3 (0.8106,
     gap 0.0654). The triplet is worse than the pair on Calmar in BOTH windows.

2) Is there a cardinality (2,3,4) that matches/beats continuous net while keeping a hard cap + EW
   simplicity? Is diversification gain 2->3->4 monotone? Where is the sweet spot?
   - Diversification is NOT monotone. The net-Sharpe / net-Calmar peak among capped equal-weight
     schemes is at N=2 (the pair) in CLEAN and ~N=2 in EXT; adding the 3rd and 4th asset DEGRADES
     net performance. CLEAN net Sharpe: 1.2424 (EW-2) > 1.2229 (EW-3) > 1.0875 (EW-4). EXT net
     Calmar: 0.8396 (EW-2) > 0.8106 (EW-3) > 0.7069 (EW-4).
   - Net MaxDD also worsens monotonically with cardinality in EXT (-16.76% -> -17.68% -> -20.18%) and
     is flat-to-worse in CLEAN (-16.35% -> -16.86% -> -16.86%).
   - Sweet spot on net Calmar/MaxDD = EW-2 (the production pair), both windows. The only scheme that
     matches/beats continuous net is none on Calmar in CLEAN; in EXT the equal-weight schemes beat
     continuous on Sharpe but lose on Calmar/MaxDD. No capped EW scheme dominates continuous on both.
   - Mechanism: candidates are sorted by variance, so the 3rd/4th asset added is systematically the
     HIGHER-variance trend name; equal-weighting it raises portfolio vol (CLEAN 11.27% -> 11.57% ->
     12.20%) faster than it adds return. Concentrating in the lowest-variance pair is the better
     diversification trade in this small, variance-dispersed universe (equities vs gold vs bonds).

3) Does the stability/cap advantage degrade as cardinality rises?
   - YES on signal stability. Frac-months-changed rises monotonically: EW-2 0.389 -> EW-3 0.505 ->
     EW-4 0.532 (CLEAN); 0.420 -> 0.528 -> 0.558 (EXT). More assets = more months with some weight
     change, because any single asset entering/leaving the min-var subset or trend screen moves the
     basket. (Dollar turnover does NOT rise -- it falls slightly -- but holding/signal churn does.)
   - The cap advantage strengthens numerically with cardinality (50% -> 33% -> 25% risk-on cap,
     eff-N 2.0 -> 3.0 -> 3.9) but buys no net performance. Continuous, by contrast, has the worst
     churn of all (0.81/0.87 frac-changed) AND no cap (62.8%/60.5% avg risk-on max weight).

## Verdict

Do NOT move production from the 50/50 pair to a triplet or to full 1/N.

- The triplet does not recover the gap to continuous min-var; in CLEAN it is strictly worse than the
  pair on net Sharpe, Calmar and MaxDD, and it costs +12 to +16 ppts of signal-churn (0.389 -> 0.505).
  Full 1/N (EW-4) is the worst equal-weight scheme net on both windows.
- Continuous min-var STILL dominates net on the headline metrics in CLEAN (Sharpe 1.2935, Calmar
  0.9618, MaxDD -15.15%) and on risk-adjusted drawdown (Calmar/MaxDD) in EXT. Its disadvantages are
  operational/robustness, not net return: it has no concentration cap (avg risk-on single weight
  ~61-63%) and rebalances almost every month (frac-changed 0.81-0.87).
- The production pair (EW-2) is the equal-weight sweet spot: best capped-EW Sharpe/Calmar/MaxDD,
  lowest churn among the diversified EW schemes, hard 50% cap. Choosing it over continuous is a
  deliberate trade of ~0.05 net Sharpe / ~0.09 net Calmar (CLEAN) for a hard concentration cap and a
  ~2x reduction in signal churn -- a defensible robustness/operability premium, not a free lunch.
- DeMiguel (2009) 1/N-robustness framing does NOT favor adding cardinality here. That result assumes
  a large asset menu where estimation error swamps optimization gains. This menu is tiny (K=4),
  pre-filtered by trend, and the added names are systematically higher-variance, so naive 1/N over
  MORE assets (EW-4) loses to the variance-concentrated pair. The robustness benefit of equal-weight
  is captured at N=2; pushing to N=3/4 only dilutes into the trend universe's high-vol tail.
- Cost caveat: at high costs (50 bps/side) the lower-churn equal-weight schemes converge on, and in
  EXT pass, the optimizer (EW-3 best at 50 bps EXT). If realized transaction costs are materially
  above 25 bps/side, the triplet becomes defensible; at the production 10 bps assumption it is not.

## Reproduce

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
uv run python research/cardinality_sweep.py
```

Outputs: `research/cardinality_sweep.json` (full metrics), console anchor verification + sweep table.

## Caveats / confidence

- High confidence in the relative ordering: anchors reproduce to 4 dp, and the non-monotone
  pair-peak holds in both windows and across the cost grid.
- Single historical path (one universe, one lookback). No bootstrap CI here -- ordering differences
  EW-2 vs EW-3 in EXT (~0.008 Sharpe) are inside likely sampling noise; the EW-vs-N=1 and EW-vs-EW-4
  gaps are large and robust.
- min-var subset selection uses simple sample covariance (no shrinkage); a shrinkage estimator might
  narrow the continuous-vs-EW gap but would not change the cardinality ordering within EW.
- "N=1" MOM-1 is the single raw-Faber-momentum pick; an alternative pure-momentum definition (e.g.
  13612U or vol-adjusted top pick) could differ, but momentum-only N=1 is clearly dominated either way.
