# TAA Validation Experiments on the Current 60/15/15/10 CPM Blend

## Provenance

- Persisted: 2026-06-07
- Source tmp file: `/tmp/taa_experiment_results.md`
- Temp scripts: `/tmp/taa_probe.py`, `/tmp/taa_exp_run.py`

Analyst run. Research/analysis only: no production files edited, no commit, no
strategy-config change. All overlays are post-processing on the canonical blend
daily-return series produced by the production engine (`build_artifacts`).

- Date: 2026-06-07
- Repo: `/Users/rkautsar/personal/scripts/strategy_cpm`
- Corpus driving the design: `/tmp/cpm_spec.md` (authoritative current blend),
  `/tmp/taa_synthesis.md` section 7 (experiment definitions).
- Scope executed: Experiment 1 (blend-level vol-target overlay) and Experiment 2
  (orthogonal macro/credit gate). Experiments 3 (risk budgeting) and 4 (global
  value sleeve) were out of the requested scope.

## Commands / Files

```bash
cd /Users/rkautsar/personal/scripts/strategy_cpm
# 1) build + cache the canonical baseline blend daily series (slow part, ~5 min)
.venv/bin/python /tmp/taa_probe.py
# 2) run both experiments on the cached series (fast)
.venv/bin/python /tmp/taa_exp_run.py
```

- Temp scripts (created under /tmp only, per scope):
  - `/tmp/taa_probe.py` - builds the 4-sleeve blend via `build_dashboard.build_artifacts`,
    reproduces baseline metrics, caches daily series to `/tmp/taa_baseline_series.parquet`.
  - `/tmp/taa_exp_run.py` - applies both overlays as post-processing; writes raw
    output `/tmp/taa_exp_raw.md`.
- Repo code reused (read-only): `build_dashboard.build_artifacts` /
  `dashboard_engine.build_artifacts` (blend construction), `cpm_live.load_panel`,
  `cpm_live.compute_target_weights` (CPM risk-state for orthogonality),
  `core.perf_metrics`, `research.cpm_bootstrap_multimetric.paired_block_bootstrap_mm`.
- Data sources: production price panel (`load_panel`, stitched proxies),
  `research/_macro_cache/UNRATE.csv`, `data/fred_BAA.csv`, `data/fred_AAA.csv`.

## Conventions (locked, identical across all arms)

- Blend = `0.60*CPM + 0.15*NDX + 0.15*VAL + 0.10*RPV` (from `config.py`), built by
  the production engine. The blend daily return is a linear sum of sleeve daily
  returns, so a blend-level exposure scale is exact (no re-running the engine).
- Monthly signal at month-end T (PIT, info <= T), executed t+1; sleeve legs are
  the canonical mooex T+1 MOO, 10 bps/side. Overlay turnover is charged 10 bps on
  `|delta scale|` at each rebalance.
- Windows: clean 2008-05-30..2026-06-05 (decision window), ext 1999-03-10.. (confirm).
- De-risk-ONLY overlays: exposure scale in [0,1], residual to SHV cash. Overlays
  never add leverage; they only shed risk on top of the sleeves' own defense.

---

## BASELINE (reproduced, canonical engine)

| window | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| clean (2008-05-30..2026-06-05) | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% |
| ext (1999-03-10..2026-06-05) | 1.544 | 15.53% | -9.94% | 1.562 | 9.65% |

Baseline per-crisis MaxDD (blend, within-window): GFC -7.22%, Euro-2011 -5.19%,
COVID -6.13%, 2022 -3.18%, 2025 tariff -6.28%.

Note: the corpus does not tabulate a Sharpe for the current 4-sleeve blend (only
the CPM core sleeve and the older 60/20/20 blend). This baseline is the canonical
`build_artifacts` output - the same series the dashboard uses - and is applied
identically across every experiment arm, so the reported deltas are
apples-to-apples even though there is no published 4-sleeve headline to anchor to.
The current blend's higher Sharpe vs the old 60/20/20 (1.41) is expected: it adds
the VAL and RPV diversifiers and runs through 2026-06-05.

---

## EXPERIMENT 1: Blend-level vol-target overlay (de-risk-only -> SHV)

Mechanic: `scale = min(1, target / rv_blend_252d)`, where `rv_blend_252d` is the
trailing-252-trading-day realized vol of the BASELINE (unscaled, non-recursive)
blend, lagged to T. Targets: fixed VT-10, fixed VT-12, parameter-free
expanding-60/40 vol (mean of completed-month realized vol of 0.6*SPY+0.4*IEF),
and trailing-60/40 (contamination reference).

### Bind / target diagnostics (clean)

| config | bind% | mean scale | min scale | mean target | target range | overlay TO/yr |
|---|---:|---:|---:|---:|---:|---:|
| VT-10 fixed | 36.2% | 0.927 | 0.572 | 10.00% | [10.0,10.0]% | 0.117 |
| VT-12 fixed | 20.2% | 0.968 | 0.687 | 12.00% | [12.0,12.0]% | 0.054 |
| VT-6040-expand | 39.0% | 0.919 | 0.561 | 9.64% | [9.1,10.5]% | 0.130 |
| VT-6040-trail | 54.1% | 0.865 | 0.500 | 10.39% | [3.8,26.0]% | 0.268 |

### Metrics

clean:

| config | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% |
| VT-10 fixed | 1.626 | 15.66% | -7.12% | 2.200 | 9.24% |
| VT-12 fixed | 1.623 | 16.68% | -7.92% | 2.105 | 9.83% |
| VT-6040-expand | 1.626 | 15.47% | -7.22% | 2.143 | 9.13% |
| VT-6040-trail | 1.600 | 15.24% | -9.30% | 1.638 | 9.15% |

ext:

| config | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| baseline | 1.544 | 15.53% | -9.94% | 1.562 | 9.65% |
| VT-10 fixed | 1.543 | 14.24% | -9.94% | 1.432 | 8.89% |
| VT-6040-expand | 1.542 | 14.10% | -9.94% | 1.419 | 8.81% |
| VT-6040-trail | 1.544 | 13.61% | -9.30% | 1.463 | 8.50% |

### Per-crisis MaxDD

| crisis | baseline | VT-10 | VT-12 | 6040-expand | 6040-trail |
|---|---:|---:|---:|---:|---:|
| GFC 2007-10..2009-06 | -7.22% | -7.12% | -7.22% | -7.22% | -7.22% |
| Euro 2011-04..2012-01 | -5.19% | -4.77% | -5.14% | -4.89% | -4.18% |
| COVID 2020-02..2020-06 | -6.13% | -6.13% | -6.13% | -6.13% | -5.23% |
| 2022 bear | -3.18% | -2.35% | -2.81% | -2.17% | -1.87% |
| 2025 tariff | -6.28% | -5.86% | -6.28% | -5.43% | -5.03% |

### Paired block bootstrap dSharpe vs baseline (clean, B=2000, block=21)

| config | dSharpe | CI95 | P(d>0) |
|---|---:|---:|---:|
| VT-10 fixed | -0.0015 | [-0.0715, +0.0757] | 48.0% |
| VT-12 fixed | -0.0045 | [-0.0465, +0.0435] | 40.7% |
| VT-6040-expand | -0.0018 | [-0.0752, +0.0773] | 47.1% |
| VT-6040-trail | -0.0275 | [-0.1102, +0.0574] | 24.9% |

### Experiment 1 reading

- Sharpe is NEUTRAL. Every reasonable VT config lands on top of the baseline
  (1.626 vs 1.627); the bootstrap dSharpe is ~0 with a CI symmetric around zero
  and P(d>0) ~47-48%. There is no risk-adjusted edge, in either direction.
- Drawdown / Calmar relief is MATERIAL and one-directional. Clean MaxDD shrinks
  -9.53% -> -7.12% (VT-10) / -7.22% (expand), about a 24% reduction, and Calmar
  rises 1.846 -> 2.20 / 2.14 (~+16-19%). The relief concentrates in the slow
  crises (2022 -3.18 -> -2.17, Euro -5.19 -> -4.89, 2025 tariff -6.28 -> -5.43).
- COVID is unchanged (-6.13% across all VT configs): the monthly, lagged scale
  fires the month AFTER the gap. This exactly reproduces the synthesis prediction
  that no monthly overlay catches the fast V-reversal.
- The ext-window binding MaxDD is UNCHANGED (-9.94%): the overlay does not move
  the sharp, single-bar tail (the 2010-flash-crash class event the synthesis
  flagged). The DD relief is real but only on the grind-down crises.
- The parameter-free expanding-60/40 anchor rediscovers VT-10: mean target 9.64%
  in a tight [9.1,10.5]% band, and it matches fixed VT-10 on every metric. This
  confirms on the CURRENT 4-sleeve blend the prior finding (validated only on the
  old 60/20/20). It removes the hand-picked 10% constant.
- VT-6040-trailing is the weakest (Sharpe 1.600) and has a wildly swinging target
  [3.8, 26.0]% - regime-dependent, not recommended.
- Overlay turnover is negligible (~0.12/yr for VT-10/expand).

VERDICT (Experiment 1): QUALIFIED ADOPT CANDIDATE - as a drawdown/Calmar
HARDENING overlay, not a Sharpe lift. It clears the synthesis decision rule via
the "material slow-crisis DD gain with neutral Sharpe" branch (NOT the Sharpe-
delta branch, which is squarely inside bootstrap noise). Use the parameter-free
VT-6040-expand anchor to avoid a magic constant. Honest caveat: it cannot help
COVID-type gaps and does not move the binding ext tail; the entire case is
slow-crisis tail relief at the cost of ~2pp CAGR. Pre-adoption gate still open:
walk-forward / out-of-sample stability of the DD relief (point estimates only here).

---

## EXPERIMENT 2: Orthogonal macro/credit gate (de-risk fraction -> SHV)

Gates tested (all monthly, publication-lagged, executed t+1, de-risk fraction to
SHV when fired):
- Sahm rule: 3m-MA unemployment minus its trailing-12m low >= threshold.
- GTT-UE: unemployment > its trailing-12m mean (Growth-Trend-Timing on UE).
- IG credit spread level: Moody's Baa-Aaa >= threshold (HY-OAS proxy, see data note).

### DATA / LOOKAHEAD LABELING (required by guardrails)

- UNRATE = `research/_macro_cache/UNRATE.csv`. This is the CURRENT REVISED FRED
  print, NOT vintage/ALFRED. Unemployment is low-revision, but real-time
  (point-in-time) values can differ slightly. I cannot claim vintage validity;
  results may be modestly optimistic on the macro side.
- IG credit spread = Moody's Baa-Aaa (`data/fred_BAA.csv` - `data/fred_AAA.csv`),
  market-priced monthly yields, effectively non-revised (clean on the lookahead
  axis). NO HY OAS (FRED `BAMLH0A0HYM2`) is available locally - this is the exact
  missing input; the Baa-Aaa investment-grade spread is used as the available
  credit-level proxy (it is narrower and milder than HY OAS).
- Publication lag: every monthly observation (dated first-of-month) is treated as
  usable only ~1 month + 7 days later, so a month-end T signal uses the prior
  month's print at most. This removes same-month lookahead. (Conservative for
  credit, which is observable faster; it blunts fast-crisis detection - see COVID.)

### Gate fire frequency + orthogonality vs CPM price de-risk (clean)

CPM "risk-off" = the CPM sleeve's risky weight < 1.0 at T (from
`compute_target_weights`). "%fire@CPM-risk-ON" = of the gate's fire months, the
share where CPM was still fully risk-ON (i.e., the gate adds NEW, orthogonal
de-risk). Higher = more orthogonal.

| gate | n fire | % of months | %fire@CPM-risk-ON |
|---|---:|---:|---:|
| Sahm>=0.50 | 38 | 17.4% | 68% |
| Sahm>=0.30 | 51 | 23.4% | 76% |
| GTT-UE | 72 | 33.0% | 81% |
| IGspread>=1.2 | 42 | 19.3% | 57% |
| IGspread>=1.5 | 13 | 6.0% | 38% |
| IGspread>=2.0 | 8 | 3.7% | 25% |

The non-price gates ARE structurally orthogonal: Sahm and GTT-UE fire mostly when
CPM's own price defense has NOT engaged (68-81% of fires). The credit spread is
LESS orthogonal (25-57%) - credit stress tends to coincide with CPM's price
de-risk, so it adds less independent breadth.

### Metrics x de-risk fraction (clean)

Sahm>=0.50:

| config | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% |
| f25% | 1.668 | 16.57% | -7.17% | 2.313 | 9.49% |
| f50% | 1.680 | 15.53% | -6.63% | 2.340 | 8.84% |
| f100% | 1.557 | 13.38% | -6.63% | 2.017 | 8.30% |

- Sahm crisis MaxDD (f50/f100): GFC -7.22 -> -3.73, big relief; Euro/COVID/2022/
  2025 unchanged (Sahm did not fire pre-emptively in those).
- bootstrap dSharpe (f50 vs base): +0.0533, CI [-0.0679, +0.1875], P(d>0)=77.8%.

GTT-UE:

| config | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% |
| f25% | 1.646 | 15.57% | -9.30% | 1.674 | 9.07% |
| f50% | 1.621 | 13.55% | -9.30% | 1.456 | 8.06% |
| f100% | 1.304 | 9.48% | -9.30% | 1.019 | 7.15% |

- Fires too often (33% of months); drags CAGR hard (f100 -> 9.48%); Sharpe flat
  at f25 and falling beyond. GFC dd improves (-7.22 -> -0.36 at f100) but the
  whipsaw drag dominates. bootstrap dSharpe (f50): -0.0042, CI [-0.144, +0.137].

IGspread>=1.5:

| config | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% |
| f25% | 1.624 | 17.18% | -9.53% | 1.802 | 10.10% |
| f50% | 1.611 | 16.76% | -9.53% | 1.758 | 9.95% |
| f100% | 1.554 | 15.89% | -9.53% | 1.667 | 9.83% |

- Sharpe-neutral-to-negative; binding MaxDD unchanged. GFC dd improves
  (-7.22 -> -4.85) but COVID/2022/2025 unchanged. bootstrap dSharpe (f50):
  -0.0161, CI [-0.081, +0.043].

### Credit IG-spread threshold sensitivity (frac=50%, clean)

| threshold | n fire | Sharpe | MaxDD | CAGR | GFC dd | COVID dd |
|---|---:|---:|---:|---:|---:|---:|
| IG>=0.8 | 146 | 1.651 | -7.00% | 12.59% | -3.61% | -3.06% |
| IG>=1.0 | 92 | 1.623 | -9.30% | 14.20% | -3.73% | -6.13% |
| IG>=1.2 | 42 | 1.601 | -9.53% | 15.86% | -3.73% | -6.13% |
| IG>=1.5 | 13 | 1.611 | -9.53% | 16.76% | -4.85% | -6.13% |
| IG>=2.0 | 8 | 1.636 | -9.53% | 17.38% | -6.03% | -6.13% |
| IG>=2.5 | 8 | 1.636 | -9.53% | 17.38% | -6.03% | -6.13% |

Robust NULL: no threshold produces a Sharpe spike (range 1.60-1.65, all inside
baseline noise). This is the anti-overfit check PASSING (no single magic
threshold), but it also means there is no edge. The very low threshold (0.8)
de-risks 146/218 months - a near-permanent ballast that smooths COVID only by
being de-risked nearly all the time (CAGR collapses to 12.59%).

### Macro value sanity (values as-used after pub lag)

```
2008-09-30: Sahm=1.17  IGspread=1.51  GTT-UE=True     (GFC: all gates fire - good)
2008-12-31: Sahm=1.67  IGspread=3.09  GTT-UE=True
2009-03-31: Sahm=2.80  IGspread=2.81  GTT-UE=True
2011-09-30: Sahm=0.00  IGspread=0.99  GTT-UE=False    (Euro: gates silent)
2020-03-31: Sahm=0.00  IGspread=0.83  GTT-UE=False    (COVID crash month: SILENT)
2020-04-30: Sahm=0.27  IGspread=1.27  GTT-UE=True     (fires AFTER the gap)
2022-06-30: Sahm=0.00  IGspread=0.99  GTT-UE=False    (2022: gates silent)
2025-04-30: Sahm=0.23  IGspread=0.64  GTT-UE=True
```

The sanity table is the clearest read: the macro gates fire correctly in the one
true recession in the clean window (GFC) and are silent in the fast/atypical
shocks (COVID crash month, Euro, 2022). COVID specifically fires only the month
AFTER the gap (2020-03 silent, 2020-04 on) - same fast-reversal failure mode as
the price triggers, made slightly worse by the publication lag.

### Experiment 2 reading

- The Sahm rule is the best of the macro candidates: genuinely orthogonal (68% of
  fires when CPM is still risk-ON), positive directional Sharpe (+0.053 at f50)
  and a large GFC drawdown reduction (-7.22 -> -3.73). But it is NOT statistically
  significant (bootstrap CI [-0.068, +0.188] includes zero; P(d>0)=78%), and it is
  episode-driven: the clean window contains essentially one classic recession
  (GFC) plus COVID, so the lift rides a very small number of episodes.
- GTT-UE over-fires (33% of months) and bleeds CAGR; reject.
- The IG credit-spread proxy is Sharpe-neutral-to-negative, the least orthogonal,
  and misses COVID due to the lag; reject as a standalone gate. (A true HY OAS
  series, unavailable locally, might behave better, but the IG proxy does not
  clear the bar.)
- Every macro gate is silent in COVID/2022/2025 fast shocks - structural, expected,
  and consistent with the synthesis "no monthly overlay catches the fast gap."

VERDICT (Experiment 2): DO NOT ADOPT on current evidence; KEEP AS A STRUCTURAL
WATCH-ITEM. The Sahm gate is the only candidate with both orthogonality and a
directional improvement, exactly matching the synthesis honest prior ("modest,
recession-specific, may sit inside bootstrap noise, no COVID help"). Its value is
structural (the one non-price early-warning channel CPM lacks) and recession-
specific, not a headline lift. Reject GTT-UE (whipsaw drag) and the IG credit
proxy (no edge, low orthogonality). Any future adoption MUST (a) use vintage/
ALFRED unemployment, (b) test on a longer recession sample / walk-forward, and
(c) source a real HY OAS for the credit channel.

---

## Cross-experiment summary

| candidate | Sharpe vs base | clean MaxDD | dSharpe CI (clean) | crisis relief | verdict |
|---|---|---|---|---|---|
| VT-6040-expand (vol-target) | ~flat (1.626) | -9.53 -> -7.22 | [-0.075,+0.077] | slow crises; not COVID | qualified adopt (DD/Calmar hardening; WF pending) |
| Sahm>=0.50 f50 (macro) | +0.053 (1.680) | -9.53 -> -6.63 | [-0.068,+0.188] | GFC only | watch-item; orthogonal but not significant |
| GTT-UE f50 | -0.006 | -9.30 | [-0.144,+0.137] | GFC; heavy drag | reject |
| IG credit f50 | -0.016 | -9.53 | [-0.081,+0.043] | GFC partial | reject (no edge, lookahead-blunted) |

## Limitations / caveats

- Point estimates + a single paired block bootstrap (B=2000, block=21) only; NO
  walk-forward / OOS split was run. Both experiments' headline DD relief is
  in-sample on the development window.
- Baseline 4-sleeve blend Sharpe has no published corpus anchor; it is the
  canonical engine output, applied identically across arms (deltas are valid).
- Macro gate uses REVISED FRED unemployment (not vintage); credit channel uses an
  IG Baa-Aaa proxy because HY OAS is absent locally. Both are clearly labeled; the
  unemployment result may be modestly optimistic, the credit result is clean on
  revision but a weaker (narrower) signal than HY OAS.
- Overlay transaction cost is modeled as 10 bps on `|delta exposure|` per
  rebalance (one side); it does not separately charge the SHV leg. Effect is tiny
  (overlay turnover ~0.1-0.3/yr) and does not change any verdict.
- Crisis windows are fixed calendar windows; the binding full-period MaxDD can sit
  outside them (e.g., the 2010 flash-crash class event), which is why ext MaxDD is
  unmoved by the vol-target overlay.

## Reproduction artifacts

- `/tmp/taa_probe.py`, `/tmp/taa_exp_run.py` (scripts)
- `/tmp/taa_baseline_series.parquet` (cached baseline daily series: blend + 4
  sleeves + cash)
- `/tmp/taa_exp_raw.md` (raw run output)
- `/tmp/taa_experiment_results.md` (this file)
