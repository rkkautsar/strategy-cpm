# CPM TAA novel overlay experiments

## Provenance

- Date: 2026-06-07
- Source reports:
  - `/tmp/taa_macro_budget_experiment.md`
  - `/tmp/taa_adaptive_governor_experiment.md`
- Source scripts:
  - `/tmp/taa_macro_budget_run.py`
  - `/tmp/taa_adaptive_governor_run.py`
- Related repo notes:
  - `research/cpm_taa_landscape_synthesis.md`
  - `research/cpm_taa_overlay_validation_current_blend.md`
- Process: consolidated approved experiment outputs into one durable repo note; no reruns.

## 1. Executive verdict comparing Experiment A and Experiment B

- Experiment A (macro-regime sleeve rebudgeting) produced a strong structural result: Sahm-driven R3-half style rebudgeting keeps most CAGR while improving drawdown and Calmar versus both baseline and prior de-risk-to-cash framing. But Sharpe lift stayed inside bootstrap noise, result is episode-driven, and macro vintage caveats remain. Verdict: WATCH.
- Experiment B (adaptive defense overlay) produced the stronger near-term implementation signal: stress-amplified VT (tgt-20% or cap-0.75) improved plain VT hardening, reduced clean MaxDD to -6.50%, and had dMaxDD CI clearing zero, while Sharpe stayed directionally positive but not significant. Verdict: QUALIFIED ADOPT-CANDIDATE.
- Comparison: both improve defense quality versus baseline, but B is stronger for practical next-step deployment because benefit is cleaner on the hardening axis. A remains high-value research insight with open validation gates (vintage unemployment, walk-forward/OOS, real HY OAS).

## 2. Full Experiment A content (macro-regime sleeve risk-budgeting)

# Experiment A: Dynamic Macro-Regime Sleeve Risk-Budgeting on the Current 60/15/15/10 CPM Blend

## Provenance

- Date: 2026-06-07
- Analyst run. Research/analysis only: NO production files edited, NO commit/push,
  NO strategy-config change. All overlays are post-processing on the canonical
  daily sleeve-return series produced by the production engine (`build_artifacts`).
- Repo: `/Users/rkautsar/personal/scripts/strategy_cpm`
- Hypothesis source: `research/cpm_taa_landscape_synthesis.md` flags dynamic
  macro-regime risk budgeting (factor F6 x dimension D) as a genuine unexplored
  gap. Prior overlay validation: `research/cpm_taa_overlay_validation_current_blend.md`.
- This experiment is DISTINCT from that prior work: prior overlays scaled total
  blend exposure in [0,1] with the residual parked in SHV cash (de-risk-to-cash).
  Here we REALLOCATE the four sleeve weights (cpm/ndx/val/rpv) toward a defensive
  budget when a macro stress regime fires (risk-budgeting, fully invested), so the
  shed equity risk rotates into the earning RPV risk-premia sleeve rather than
  dead cash.

## Question

Does a constrained, transparent, publication-lagged macro-regime overlay that
DYNAMICALLY REBUDGETS sleeve weights (toward CPM + RPV in recession/credit stress)
improve the risk-adjusted profile of the current blend versus the static
60/15/15/10, and does rebudgeting beat the prior de-risk-to-cash overlay on the
Sharpe / CAGR / drawdown tradeoff? Constraints: no ML, no multi-parameter
optimization, small transparent grid only, all signals point-in-time through T and
executed t+1.

## Sleeve identities (for interpreting the weight maps)

- CPM (0.60): canary-protected trend/momentum core; the blend's defensive engine.
- NDX (0.15): Nasdaq-100 momentum sleeve; aggressive equity beta.
- VAL (0.15): fundamental value + quality equity sleeve; equity beta.
- RPV (0.10): Risk Premia Value, a multi-asset sleeve over term/IG-credit/HY-credit/
  equity premia; the diversifying ballast that keeps earning carry when de-risked.

The recession budgets cut NDX + VAL (aggressive equity) and add to CPM + RPV
(defensive trend + earning diversifier). This is the structural reason rebudgeting
can beat de-risk-to-cash: the shed equity risk is parked in RPV (still earning),
not SHV (zero real carry).

---

## Baseline (reconstructed from cached sleeve returns, canonical engine)

The blend daily return is an exact linear sum of sleeve daily returns:
reconstruction `0.60*cpm + 0.15*ndx + 0.15*val + 0.10*rpv` vs the stored engine
blend has max abs error 6.94e-18 (floating-point exact). This validates applying a
time-varying weight vector to the cached sleeve returns: it reproduces exactly what
the engine would produce for those weights (each sleeve's own t+1 MOO / 10bps
execution is already baked into its daily returns; the overlay adds only the
cross-sleeve reallocation cost).

| window | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| clean (2008-05-30..2026-06-05) | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% |
| ext (1999-03-10..2026-06-05) | 1.544 | 15.53% | -9.94% | 1.562 | 9.65% |

Matches the published baseline in the prior validation note exactly.

Baseline per-crisis MaxDD (within fixed windows): GFC -7.22%, Euro-2011 -5.19%,
COVID -6.13%, 2022 -3.18%, 2025 tariff -6.28%. Note the binding clean MaxDD
(-9.53%) sits OUTSIDE the GFC calendar window (it spans the continuous 2008-2010
stress stretch), which is why the overlay can move the binding DD even when the
fixed GFC-window DD moves only partly.

---

## Methods

### Conventions (locked, identical across all arms)

- Baseline weights `w0 = (cpm 0.60, ndx 0.15, val 0.15, rpv 0.10)` from `config.py`.
- Monthly signal at month-end trading day T (PIT, info <= T with macro publication
  lag), executed t+1: the weight vector chosen at T applies to every trading day
  strictly after T until the next month-end (same `last sig strictly < day` mapping
  as the prior overlay code).
- Overlay reallocation cost: 10 bps charged on gross `sum_i |dw_i|` at each weight
  change (conservative; charges both buy and sell legs). The sleeves' own internal
  trade costs are already inside their daily returns.
- Fully invested at all times (no leverage, no cash leg): weight maps sum to 1.0.
- Windows: clean 2008-05-30..2026-06-05 (decision window), ext 1999-03-10..2026-06-05.

### Recession / stress weight maps (cpm, ndx, val, rpv; all sum to 1.0)

| map | full target | half-shift target (0.5*w0 + 0.5*target) |
|---|---|---|
| R1 | 70 / 5 / 5 / 20 | 65 / 10 / 10 / 15 |
| R2 | 80 / 0 / 0 / 20 | 70 / 7.5 / 7.5 / 15 |
| R3 | 60 / 0 / 0 / 40 | 60 / 7.5 / 7.5 / 25 |

Half-shift = move only 50% of the way from baseline to the recession target (a
softer, less episode-sensitive variant).

### Stress signals (point-in-time, publication-lagged)

- Sahm stress: 3m-MA of unemployment minus its trailing-12m low >= threshold
  (0.50 canonical, 0.30 looser). Recommended by prior note as the one orthogonal
  early-warning channel CPM lacks.
- Credit stress: Moody's Baa-Aaa IG spread >= threshold (1.2 / 1.5). Used as the
  available credit-level proxy; NO HY OAS (FRED BAMLH0A0HYM2) is available locally.
- Combined stress: Sahm OR credit (recession budget if either fires, else baseline).

When a signal fires at T, weights move to the (full or half) recession target for
the next month; otherwise weights are the baseline w0.

### Data and lookahead labeling (required by guardrails)

- UNRATE = `research/_macro_cache/UNRATE.csv`: the CURRENT REVISED FRED print, NOT
  vintage/ALFRED. Unemployment is low-revision, but real-time point-in-time values
  can differ slightly. I CANNOT claim vintage validity; the Sahm-driven results may
  be modestly optimistic. (Same limitation as the prior note's Experiment 2.)
- IG credit spread = Moody's Baa-Aaa (`data/fred_BAA.csv` - `data/fred_AAA.csv`):
  market-priced monthly yields, effectively non-revised (clean on the revision
  axis), but narrower / milder than a true HY OAS.
- Publication lag: every monthly observation (dated first-of-month) is treated as
  usable only ~1 month + 7 days later, so a month-end T signal uses at most the
  prior month's print. This removes same-month lookahead and blunts fast-crisis
  detection (see COVID below).
- VIX / volatility-state budget: SKIPPED. There is NO VIX, VIX-term-structure, or
  VIX-proxy series available locally (confirmed: no vix file under `data/` or
  `research/_macro_cache/`, and no vix column in the parquet panels). The
  realized-vol regime is in any case already covered by the prior note's
  Experiment 1 (blend-level vol-target overlay). Per scope, this arm is documented
  as missing-data and not run.

### Statistics

- Point estimates over clean + ext windows; per-crisis MaxDD over fixed windows.
- Paired block bootstrap dSharpe vs baseline (B=2000, block=21, seed=42), reusing
  `research.cpm_bootstrap_multimetric.paired_block_bootstrap_mm` (same code the
  prior note used). dMaxDD is reported as path-dependent context (soft CI).

---

## Results

### Signal fire frequency + orthogonality vs CPM price de-risk (clean)

`%fire@CPM-riskON` = of the signal's fire months, share where the CPM sleeve was
still fully risk-ON at T (so the overlay adds NEW, orthogonal action). Higher =
more orthogonal.

| signal | n fire | % of months | %fire@CPM-riskON |
|---|---:|---:|---:|
| Sahm>=0.50 | 38 | 17.4% | 68% |
| Sahm>=0.30 | 51 | 23.4% | 76% |
| IGspread>=1.2 | 42 | 19.3% | 57% |
| IGspread>=1.5 | 13 | 6.0% | 38% |
| combo Sahm.50 OR IG1.5 | 38 | 17.4% | 68% |
| combo Sahm.30 OR IG1.2 | 73 | 33.5% | 74% |

The combined Sahm.50/IG1.5 signal is IDENTICAL to Sahm>=0.50 alone in the clean
window (same 38 fires): the 13 IG>=1.5 fire months are all subsumed inside the
GFC stretch where Sahm already fires. The credit proxy adds no new orthogonal
breadth here. Sahm is genuinely orthogonal (68-76% of fires when CPM price defense
has not engaged).

### Combined stress signal (Sahm>=0.50 OR IGspread>=1.5) -- weight map x shift

clean:

| config | Sharpe | CAGR | MaxDD | Calmar | vol | TO/yr |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% | 0.000 |
| R1 70/5/5/20 full | 1.649 | 16.88% | -7.26% | 2.325 | 9.77% | 0.147 |
| R1 65/10/10/15 half | 1.643 | 17.24% | -8.38% | 2.058 | 10.02% | 0.073 |
| R2 80/0/0/20 full | 1.632 | 16.53% | -7.31% | 2.260 | 9.69% | 0.220 |
| R2 70/7.5/7.5/15 half | 1.640 | 17.07% | -8.07% | 2.117 | 9.94% | 0.110 |
| R3 60/0/0/40 full | 1.675 | 16.41% | -7.51% | 2.184 | 9.36% | 0.220 |
| R3 60/7.5/7.5/25 half | 1.667 | 17.02% | -7.08% | 2.405 | 9.74% | 0.110 |

ext (Sharpe / CAGR / MaxDD): baseline 1.544 / 15.53% / -9.94%; R1 full 1.567 /
15.13% / -9.94%; R3 full 1.589 / 14.84% / -9.94%; R3 half 1.579 / 15.19% / -9.94%.
The ext binding MaxDD is UNCHANGED at -9.94% for every arm: the binding ext tail
lives in the 1999-2008 pre-GFC region where the Sahm/credit signal is silent
(same structural blind spot the prior note flagged).

### Per-crisis MaxDD (combined signal)

| crisis | baseline | R1 full | R1 half | R2 full | R2 half | R3 full | R3 half |
|---|---:|---:|---:|---:|---:|---:|---:|
| GFC 2007-10..2009-06 | -7.22% | -6.43% | -6.83% | -6.88% | -6.65% | -7.51% | -6.69% |
| Euro 2011-04..2012-01 | -5.19% | -5.19% | -5.19% | -5.19% | -5.19% | -5.19% | -5.19% |
| COVID 2020-02..2020-06 | -6.13% | -6.13% | -6.13% | -6.13% | -6.13% | -6.13% | -6.13% |
| 2022 bear | -3.18% | -3.18% | -3.18% | -3.18% | -3.18% | -3.18% | -3.18% |
| 2025 tariff | -6.28% | -6.28% | -6.28% | -6.28% | -6.28% | -6.28% | -6.28% |

Only GFC moves; Euro/COVID/2022/2025 are untouched because the lagged macro signal
is silent in those fast/atypical shocks (confirmed in the sanity table below). Note
R3 FULL slightly WORSENS the GFC-window DD (-7.51% vs -7.22%): a 40% RPV budget
over-concentrates into credit/term premia, which also drew down in 2008; R3 HALF
(25% RPV) avoids this and gives the best clean DD/Calmar overall.

### Paired block bootstrap dSharpe vs baseline (combined signal, clean, B=2000, block=21)

| config | dSharpe | CI95 | P(d>0) | dMaxDD |
|---|---:|---:|---:|---:|
| R1 full | +0.0204 | [-0.0521, +0.1012] | 69.2% | +1.00% |
| R1 half | +0.0148 | [-0.0211, +0.0545] | 77.0% | +0.64% |
| R2 full | +0.0026 | [-0.1036, +0.1167] | 50.9% | +0.99% |
| R2 half | +0.0117 | [-0.0413, +0.0690] | 65.1% | +0.74% |
| R3 full | +0.0457 | [-0.0800, +0.1896] | 74.3% | +1.56% |
| R3 half | +0.0385 | [-0.0248, +0.1079] | 86.7% | +1.13% |

Every arm has a POSITIVE point dSharpe and positive dMaxDD (DD improvement), but
EVERY CI includes zero. The strongest directional case is R3 half (P(d>0)=86.7%,
tightest CI of the positive set). Not statistically significant.

### Signal comparison at fixed weight map R1 (70/5/5/20), full shift (clean)

| signal | Sharpe | CAGR | MaxDD | Calmar | TO/yr | dSharpe (boot) | P(d>0) |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 | 0.000 | - | - |
| Sahm>=0.50 | 1.649 | 16.88% | -7.26% | 2.325 | 0.147 | +0.0204 | 69.2% |
| Sahm>=0.30 | 1.681 | 16.91% | -7.26% | 2.330 | 0.235 | +0.0527 | 87.4% |
| IGspread>=1.2 | 1.604 | 17.09% | -9.53% | 1.792 | 0.206 | -0.0239 | 15.9% |
| IGspread>=1.5 | 1.631 | 17.57% | -9.53% | 1.843 | 0.059 | +0.0040 | 62.0% |
| combo Sahm.50/IG1.5 | 1.649 | 16.88% | -7.26% | 2.325 | 0.147 | +0.0204 | 69.2% |
| combo Sahm.30/IG1.2 | 1.660 | 16.63% | -7.36% | 2.259 | 0.294 | +0.0312 | 74.2% |

The Sahm rule is the entire engine of the result. The IG credit proxy on its own
is Sharpe-neutral-to-NEGATIVE (IG>=1.2 actually drags, P(d>0)=15.9%) and the least
orthogonal; it leaves the binding MaxDD untouched (-9.53%). Combining credit with
Sahm adds nothing over Sahm alone. Sahm>=0.30 has the highest point Sharpe (1.681)
and P(d>0)=87.4%, but it fires more often (51 months) and is looser.

### Macro value sanity (selected month-ends; values as-used after pub lag)

```
2008-09-30: Sahm=1.17  IGspread=1.51  combo_fire=True   (GFC: fires - good)
2008-12-31: Sahm=1.67  IGspread=3.09  combo_fire=True
2009-03-31: Sahm=2.80  IGspread=2.81  combo_fire=True
2011-09-30: Sahm=0.00  IGspread=0.99  combo_fire=False  (Euro: silent)
2020-03-31: Sahm=0.00  IGspread=0.83  combo_fire=False  (COVID crash month: SILENT)
2020-04-30: Sahm=0.27  IGspread=1.27  combo_fire=False  (still silent after the gap)
2022-06-30: Sahm=0.00  IGspread=0.99  combo_fire=False  (2022: silent)
2025-04-30: Sahm=0.23  IGspread=0.64  combo_fire=False  (2025 tariff: silent)
```

The signal fires correctly in the one classic recession in the clean window (GFC,
where it stays on continuously 2008-05..2010-06) and is silent in every fast /
atypical shock. COVID is missed entirely (the publication lag pushes the first
Sahm trip past the V-reversal). This is the same structural fast-shock blind spot
the prior note documented for both price and macro triggers.

### Rebudgeting vs prior de-risk-to-cash overlay (the key structural finding)

Comparing the best risk-budgeting arm to the prior note's best de-risk-to-cash arm
on the SAME Sahm signal:

| approach | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 |
| prior: Sahm>=0.50 de-risk f50 -> SHV | 1.680 | 15.53% | -6.63% | 2.340 |
| this: Sahm/combo R3 half (60/7.5/7.5/25) | 1.667 | 17.02% | -7.08% | 2.405 |
| this: Sahm>=0.30 R1 full (70/5/5/20) | 1.681 | 16.91% | -7.26% | 2.330 |

Risk-budgeting delivers essentially the SAME Sharpe and Calmar as the cash-derisk
overlay while sacrificing far LESS CAGR (17.0% vs 15.5%, a ~1.5pp recovery) for a
comparable drawdown. The mechanism is exactly as hypothesized: rotating shed equity
risk into the RPV risk-premia sleeve (which keeps earning) rather than into dead
SHV cash preserves return at the same defensive benefit. This is the genuine,
novel structural result of the F6 x D gap: on this blend, defensive REBUDGETING
dominates defensive DE-RISK-TO-CASH on the return/risk tradeoff.

---

## Verdict

WATCH (lean qualified-adopt-candidate). Verdict per signal/config:

- Sahm-driven rebudgeting (combo == Sahm in clean), best configs R3-half
  (60/7.5/7.5/25) and Sahm>=0.30 R1-full (70/5/5/20): WATCH, slightly stronger than
  the prior macro gate. It produces a positive point Sharpe (1.65-1.68 vs 1.627),
  material drawdown / Calmar relief (clean MaxDD -9.53% -> -7.08%, Calmar 1.85 ->
  2.40), and the smallest CAGR cost of any defensive overlay tested so far (~0.6pp
  for the half-shift), and it strictly dominates the prior de-risk-to-cash overlay
  on the Sharpe/CAGR tradeoff. BUT it fails the same gates as before: the bootstrap
  dSharpe CI includes zero (not significant), the lift is episode-driven (one
  classic recession, GFC, plus the binding 2008-2010 stretch), it is silent in
  every fast shock (COVID/2022/2025), and it rides REVISED (non-vintage)
  unemployment.

- Credit-stress rebudgeting (IG Baa-Aaa proxy): REJECT as a standalone signal.
  Sharpe-neutral-to-negative, least orthogonal, leaves binding MaxDD untouched,
  adds nothing over Sahm when combined. A true HY OAS (unavailable locally) might
  behave differently, but the available proxy does not clear the bar.

- Volatility-state budget: NOT RUN (no local VIX / proxy; documented missing-data).
  The realized-vol regime is already covered by the prior note's vol-target overlay.

- R3 FULL (60/0/0/40): avoid; the 40% RPV budget over-concentrates into credit/term
  premia and slightly WORSENS the GFC-window DD. Prefer R3 HALF (25% RPV cap) or R1.

Net: the risk-budgeting framing is a genuine improvement over de-risk-to-cash and
the most attractive defensive overlay tested to date on the return/risk tradeoff,
but it does NOT cross the adoption bar (no statistically significant Sharpe edge,
episode-driven, vintage-caveated, fast-shock-blind). Pre-adoption gates that remain
open and MUST be cleared before any production move:
(a) vintage / ALFRED point-in-time unemployment to remove the revision optimism;
(b) walk-forward / out-of-sample stability of the DD relief and the dSharpe sign
across a longer recession sample (the lift currently rides essentially one episode);
(c) a real HY OAS series to fairly test (and likely confirm-or-reject) the credit
channel.

---

## Caveats and confidence

- Point estimates + a single paired block bootstrap (B=2000, block=21); NO
  walk-forward / OOS split. The headline DD relief and the positive dSharpe sign
  are in-sample on the development window and ride a very small number of episodes
  (effectively GFC).
- Macro signal uses REVISED FRED unemployment (not vintage/ALFRED); I cannot claim
  vintage validity. The credit channel uses an IG Baa-Aaa proxy because HY OAS is
  absent locally (narrower / milder than HY OAS).
- No same-day lookahead: all signals are publication-lagged ~1 month + 7 days and
  executed t+1. The lag is conservative and structurally blunts fast-crisis
  detection (COVID is missed).
- Overlay reallocation cost modeled as 10 bps on gross sum|dw| per change
  (conservative, both legs). Overlay turnover is tiny (0.07-0.29/yr) and does not
  change any verdict.
- Crisis windows are fixed calendar windows; the binding full-period MaxDD can sit
  outside them (the binding clean -9.53% spans the 2008-2010 stretch beyond the GFC
  window edges; the binding ext -9.94% sits in the 1999-2008 region the signal
  never touches).
- Confidence: HIGH on the mechanics and the relative finding (rebudgeting beats
  de-risk-to-cash on the tradeoff; the result is Sahm-driven, not credit-driven).
  LOW on any claim of a real risk-adjusted edge: the Sharpe deltas are inside
  bootstrap noise and episode-driven.

---

## Reproduction artifacts

```bash
cd /Users/rkautsar/personal/scripts/strategy_cpm
# 0) cached baseline daily sleeve series already exists at /tmp/taa_baseline_series.parquet
#    (built by /tmp/taa_probe.py from build_dashboard.build_artifacts; ~5 min if rebuilding)
# 1) run Experiment A (fast, ~30s)
.venv/bin/python /tmp/taa_macro_budget_run.py
```

- `/tmp/taa_macro_budget_run.py` - this experiment (weight-rebudgeting overlay +
  signals + metrics + bootstrap); writes `/tmp/taa_macro_budget_raw.md`.
- `/tmp/taa_macro_budget_raw.md` - raw run output.
- `/tmp/taa_macro_budget_experiment.md` - this report.
- `/tmp/taa_baseline_series.parquet` - cached canonical baseline daily series
  (blend + 4 sleeve daily returns + cash); reused from the prior analyst run.
- Repo code reused (read-only): `core.perf_metrics`, `cpm_live.load_panel`,
  `cpm_live.compute_target_weights` (CPM risk-state for orthogonality),
  `research.cpm_bootstrap_multimetric.paired_block_bootstrap_mm`, `config.py`
  weights, `sleeves.py` (sleeve identities).
- Data sources: `/tmp/taa_baseline_series.parquet`, `research/_macro_cache/UNRATE.csv`
  (REVISED, labeled), `data/fred_BAA.csv`, `data/fred_AAA.csv`.

## 3. Full Experiment B content (adaptive defense / stress-amplified VT)

# Experiment B: Adaptive Defense / State-Conditioned Vol Governor (current 60/15/15/10 CPM blend)

Analyst run. Research/analysis only: no production files edited, no commit, no
strategy-config change. Every arm is post-processing on the canonical blend
daily-return series (`build_artifacts`), applied identically, so all deltas are
apples-to-apples.

- Date: 2026-06-07
- Repo: `/Users/rkautsar/personal/scripts/strategy_cpm`
- Question: does CONDITIONING the already-promising VT-6040-expand overlay on a
  state (macro/credit stress, or drawdown-from-high) beat plain VT-6040-expand
  and the unscaled baseline, without standalone macro gates or same-day lookahead?
- Prior context: `research/cpm_taa_overlay_validation_current_blend.md`
  (VT-6040-expand = qualified DD/Calmar hardening, not a Sharpe lift; Sahm gate =
  orthogonal but not significant, watch-item) and
  `research/cpm_taa_landscape_synthesis.md` (state-conditioned defense and
  multi-lookback/fractional hardening are flagged open; multi-asset canary,
  carry/value tilt, PC1 gate are already rejected and were NOT re-run here).

---

## Baseline

Canonical engine output, reproduced and cached by the prior validation run
(`/tmp/taa_baseline_series.parquet`, blend + 4 sleeves + cash daily returns).

| window | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| clean (2008-05-30..2026-06-05) | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% |
| ext (1999-03-10..2026-06-05) | 1.544 | 15.53% | -9.94% | 1.562 | 9.65% |

Baseline per-crisis MaxDD: GFC -7.22%, Euro-2011 -5.19%, COVID -6.13%,
2022 -3.18%, 2025 tariff -6.28%. Binding clean MaxDD (-9.53%) is the 2010-05-20
flash-crash trough, not a textbook bear (matches the synthesis prior).

Plain VT-6040-expand (the overlay this experiment conditions), clean:
Sharpe 1.626, CAGR 15.47%, MaxDD -7.22%, Calmar 2.143, vol 9.13%. It relieves the
slow grinds (2022 -3.18 -> -2.17, Euro -5.19 -> -4.89, 2025 -6.28 -> -5.43) but
does NOT move GFC (-7.22), COVID (-6.13), or the binding ext tail (-9.94).

---

## Methods

Conventions locked across every arm (identical to the prior validation note):

- Blend = `0.60*CPM + 0.15*NDX + 0.15*VAL + 0.10*RPV`; blend daily return is the
  linear sum of sleeve daily returns, so a blend-level exposure scale is exact.
- De-risk ONLY: exposure scale in [0,1], residual to SHV cash; overlays never lever.
- Monthly state/VT signals at month-end T (PIT, info <= T), executed t+1.
- Daily drawdown governor uses prior close only and executes t+1 (one-day lag).
- 10 bps charged on `|delta scale|` at each change (one side).
- Windows: clean 2008-05-30.., ext 1999-03-10.. . Bootstrap = paired block
  (B=2000, block=21, seed=42), reusing `research.cpm_bootstrap_multimetric`.

VT base scale: `scale_base = min(1, target / rv_blend_252d)` with the
parameter-free expanding-60/40 target (mean of completed-month realized vol of
0.6*SPY+0.4*IEF) and trailing-252d realized vol of the non-recursive baseline
blend, lagged to T. This reproduces VT-6040-expand exactly.

Stress state S(T) (monthly, PIT, publication-lagged ~1m+7d):
`S = (Sahm >= 0.50) OR (IG-spread >= 1.5)`, where Sahm = SMA3(UNRATE) minus its
trailing-12m low and IG-spread = Moody's Baa-Aaa. (Sahm dominates; see results.)

Governor arms tested (sparse, transparent):

1. VT-6040-expand (plain) -- comparator.
2. VT + stress-amp (target -20% / -30%): in stress, `scale = min(1, target*(1-x)/rv)`;
   else `scale_base`. De-risk MORE when the economy/credit has cracked.
3. VT + stress-cap (0.75 / 0.50): in stress, `scale = min(scale_base, cap)`;
   else `scale_base`.
4. VT calm-relaxed (gated): ablation/placebo -- apply VT de-risk ONLY in stress,
   full exposure in calm (`scale = scale_base if S else 1.0`). Isolates whether the
   VT benefit/cost lives in calm vs stress states.
5. DD governor (daily, hysteresis): drawdown of the non-recursive baseline blend
   equity through close t-1; de-risk to `cap` when DD <= enter, restore to 1.0 when
   DD >= exit (exit shallower than enter), applied t+1. Tested standalone and
   stacked on VT.

Multi-lookback / fractional shared-gate hardening: SKIPPED, infeasible at overlay
level (see Results, item 4).

---

## Results

### Metrics, clean (2008-05-30..2026-06-05)

| config | Sharpe | CAGR | MaxDD | Calmar | vol | TO/yr | cost bps/yr |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% | - | - |
| VT-6040-expand (plain) | 1.626 | 15.47% | -7.22% | 2.143 | 9.13% | 0.130 | 1.3 |
| VT + stress-amp tgt-20% | 1.646 | 14.84% | -6.50% | 2.284 | 8.65% | 0.165 | 1.7 |
| VT + stress-amp tgt-30% | 1.653 | 14.50% | -6.50% | 2.231 | 8.42% | 0.188 | 1.9 |
| VT + stress-cap 0.75 | 1.641 | 15.05% | -6.50% | 2.317 | 8.80% | 0.166 | 1.7 |
| VT + stress-cap 0.50 | 1.657 | 14.16% | -6.50% | 2.179 | 8.22% | 0.233 | 2.3 |
| VT calm-relaxed (gated) | 1.660 | 16.86% | -7.22% | 2.335 | 9.70% | 0.077 | 0.8 |
| DD-gov (-7.5/-3, cap.5) | 1.605 | 16.99% | -12.43% | 1.367 | 10.13% | 0.220 | 2.2 |
| VT + DD-gov stacked | 1.604 | 15.09% | -8.38% | 1.800 | 9.04% | 0.304 | 3.0 |

### Metrics, ext (1999-03-10..2026-06-05)

| config | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| baseline | 1.544 | 15.53% | -9.94% | 1.562 | 9.65% |
| VT-6040-expand (plain) | 1.542 | 14.10% | -9.94% | 1.419 | 8.81% |
| VT + stress-amp tgt-20% | 1.556 | 13.70% | -9.94% | 1.378 | 8.48% |
| VT + stress-amp tgt-30% | 1.560 | 13.46% | -9.94% | 1.354 | 8.31% |
| VT + stress-cap 0.75 | 1.564 | 13.85% | -9.94% | 1.394 | 8.53% |
| VT + stress-cap 0.50 | 1.584 | 13.29% | -9.94% | 1.337 | 8.09% |
| VT calm-relaxed (gated) | 1.568 | 15.05% | -9.94% | 1.514 | 9.21% |
| DD-gov (-7.5/-3, cap.5) | 1.520 | 14.87% | -12.43% | 1.196 | 9.41% |
| VT + DD-gov stacked | 1.518 | 13.59% | -8.99% | 1.513 | 8.64% |

ext binding MaxDD (-9.94%) is UNCHANGED by every monthly VT/stress arm: it sits
pre-2008 (outside the clean window) and, like the 2010 flash bar, is not movable by
a monthly overlay.

### Per-crisis MaxDD (within fixed calendar windows)

| crisis | baseline | VT plain | amp-20% | amp-30% | cap-0.75 | cap-0.50 | calm-relaxed | DD-gov | VT+DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GFC 2007-10..2009-06 | -7.22% | -7.22% | -6.10% | -5.34% | -5.41% | -3.62% | -7.22% | -7.22% | -7.22% |
| Euro 2011-04..2012-01 | -5.19% | -4.89% | -4.89% | -4.89% | -4.89% | -4.89% | -5.19% | -5.19% | -4.89% |
| COVID 2020-02..2020-06 | -6.13% | -6.13% | -6.13% | -6.13% | -6.13% | -6.13% | -6.13% | -6.13% | -6.13% |
| 2022 bear | -3.18% | -2.17% | -2.17% | -2.17% | -2.17% | -2.17% | -3.18% | -3.18% | -2.17% |
| 2025 tariff | -6.28% | -5.43% | -5.43% | -5.43% | -5.43% | -5.43% | -6.28% | -6.28% | -5.43% |

Key read: stress-amp adds GFC relief (the one crisis plain VT could NOT touch)
ON TOP of plain VT's slow-crisis relief. cap-0.50 takes GFC from -7.22% to -3.62%.
calm-relaxed reverts every slow crisis to baseline (it only de-risks in stress).
No arm helps COVID (macro/monthly signals fire the month after the gap).

### Paired block bootstrap dSharpe (clean, B=2000, block=21)

| config | dS vs baseline | P>0 | dS vs plain VT | P>0 |
|---|---|---:|---|---:|
| VT-6040-expand (plain) | -0.0018 [-0.075,+0.077] | 47% | 0 | - |
| VT + stress-amp tgt-20% | +0.0188 [-0.076,+0.125] | 64% | +0.0206 [-0.018,+0.062] | 86% |
| VT + stress-amp tgt-30% | +0.0260 [-0.082,+0.151] | 67% | +0.0278 [-0.033,+0.091] | 81% |
| VT + stress-cap 0.50 | +0.0296 [-0.093,+0.159] | 68% | +0.0313 [-0.060,+0.119] | 75% |
| VT calm-relaxed (gated) | +0.0320 [-0.029,+0.104] | 81% | +0.0338 [-0.018,+0.086] | 90% |
| DD-gov (-7.5/-3, cap.5) | -0.0235 [-0.071,+0.013] | 11% | -0.0217 [-0.127,+0.064] | 35% |
| VT + DD-gov stacked | -0.0245 [-0.098,+0.047] | 26% | -0.0227 [-0.060,+0.003] | 5% |

dSharpe is directionally POSITIVE for every stress arm vs both baseline and plain
VT (P(better than plain VT) 75-86%), but the 95% CI still includes zero -- not
significant. The DD-gov arms are directionally NEGATIVE.

### Bootstrap dMaxDD vs baseline (soft CI; positive = shallower DD)

| config | dMaxDD | CI95 | P(better) |
|---|---:|---|---:|
| VT-6040-expand (plain) | +1.69% | [-0.00,+4.05]% | 97% |
| VT + stress-amp tgt-20% | +2.31% | [+0.08,+5.54]% | 98% |
| VT + stress-amp tgt-30% | +2.58% | [+0.06,+6.24]% | 98% |
| VT + stress-cap 0.50 | +2.76% | [+0.09,+6.46]% | 98% |
| VT calm-relaxed (gated) | +1.28% | [-0.02,+3.70]% | 88% |
| DD-gov (-7.5/-3, cap.5) | -1.18% | [-4.58,+0.83]% | 25% |
| VT + DD-gov stacked | +1.09% | [-1.04,+3.50]% | 88% |

The stress-amp arms' DD relief CI now CLEARS zero ([+0.08,+5.54] for tgt-20),
strictly stronger than plain VT's ([-0.00,+4.05]). This is the one statistically
meaningful improvement: stress-conditioned amplification HARDENS the drawdown more
robustly than uniform VT, mainly by adding the GFC relief.

### Sensitivity: stress-amp strength (clean)

| variant | Sharpe | CAGR | MaxDD | Calmar | GFCdd | 2025dd |
|---|---:|---:|---:|---:|---:|---:|
| tgt-20% | 1.646 | 14.84% | -6.50% | 2.284 | -6.10% | -5.43% |
| tgt-30% | 1.653 | 14.50% | -6.50% | 2.231 | -5.34% | -5.43% |
| cap-0.75 | 1.641 | 15.05% | -6.50% | 2.317 | -5.41% | -5.43% |
| cap-0.50 | 1.657 | 14.16% | -6.50% | 2.179 | -3.62% | -5.43% |

Monotone and well-behaved: more amplification = more GFC relief, modestly lower
CAGR, Sharpe stable around 1.64-1.66. tgt-20% / cap-0.75 are the conservative
sweet spot (best Calmar 2.28-2.32, smallest CAGR give-up).

### Sensitivity: credit-stress threshold (stress-amp tgt-20%, clean)

| credit thr | nStress | Sharpe | CAGR | MaxDD | Calmar | GFCdd |
|---|---:|---:|---:|---:|---:|---:|
| IG>=1.2 | 60 | 1.642 | 14.67% | -6.50% | 2.258 | -6.10% |
| IG>=1.5 | 38 | 1.646 | 14.84% | -6.50% | 2.284 | -6.10% |
| IG>=2.0 | 38 | 1.646 | 14.84% | -6.50% | 2.284 | -6.10% |

IG>=1.5 and IG>=2.0 are IDENTICAL (nStress 38 both): every credit fire is already a
Sahm fire. The governor is effectively Sahm-driven; the credit channel adds nothing
incremental in this window (consistent with the prior note's weak/non-orthogonal IG
proxy verdict). Robust to threshold = anti-overfit, but "OR credit" is redundant.

### Sensitivity: DD-governor thresholds (clean)

| enter/exit/cap | Sharpe | CAGR | MaxDD | Calmar | TO/yr | GFCdd | COVIDdd |
|---|---:|---:|---:|---:|---:|---:|---:|
| -5.0/-2/0.75 | 1.576 | 16.19% | -9.53% | 1.698 | 0.514 | -6.64% | -6.13% |
| -5.0/-2/0.50 | 1.500 | 14.77% | -9.56% | 1.546 | 1.028 | -6.09% | -6.13% |
| -7.5/-3/0.75 | 1.619 | 17.30% | -10.99% | 1.574 | 0.110 | -7.22% | -6.13% |
| -7.5/-3/0.50 | 1.605 | 16.99% | -12.43% | 1.367 | 0.220 | -7.22% | -6.13% |
| -10.0/-4/0.50 | 1.627 | 17.60% | -9.53% | 1.846 | 0.000 | -7.22% | -6.13% |

EVERY DD-gov config is <= baseline on Calmar. The -7.5%/-3% configs make MaxDD
WORSE than baseline (-10.99% / -12.43%). The only harmless config (-10/-4) never
fires (TO 0.000 = does nothing). Verified path mechanism (not a bug): the binding
clean MaxDD is the 2010-05-20 flash-crash trough; the governor de-risks at -7.5% on
the 2010-05-10 head-fake, whipsaws out at -3%, then re-enters 2010-05-21 just after
the single-bar plunge -- a textbook reactive-stop whipsaw at monthly-relevant
thresholds with a one-day lag. Activation episodes (clean): 2010-05-10..05-13,
2010-05-21..08-19, 2021-03-05..04-09.

### Item 4: multi-lookback / fractional shared-gate hardening -- SKIPPED (infeasible)

The shared NDX/VAL gate is the internal triple AND gate (TIP momentum > 0 AND SPY
momentum > 0 AND SPY RV20 < RV252) applied INSIDE sleeve construction. The cached
artifact carries only post-gate sleeve daily RETURNS; the per-lookback gate
components (1/3/6/12 momentum legs, SPY trend, SPY vol regime) are not recoverable
from a return series. A fractional 1/3/6/12 "25% per failed lookback" hardening
must modify the sleeve gate logic and re-run the engine -- product-code work, out of
this analysis-only overlay scope.
(A blend-level trend overlay is a DIFFERENT idea, not "hardening the shared gate",
and was not substituted in.)

---

## Verdict

| candidate | vs plain VT | clean MaxDD | dMaxDD CI vs base | crisis relief | verdict |
|---|---|---:|---|---|---|
| VT + stress-amp tgt-20% (or cap-0.75) | Sharpe +0.02 (P=86% better), Calmar +0.14 | -6.50% | [+0.08,+5.54]% (clears 0) | adds GFC; keeps slow crises | QUALIFIED ADOPT-CANDIDATE (refines VT) |
| VT + stress-cap 0.50 / tgt-30% | stronger GFC relief, more CAGR give-up | -6.50% | [+0.09,+6.46]% | GFC -3.6%, slow crises | adopt-candidate (aggressive variant) |
| VT calm-relaxed (gated) | highest Sharpe by doing less | -7.22% | [-0.02,+3.70]% | loses slow-crisis relief | REJECT as strategy; informative ablation |
| DD-gov (any threshold) | negative | -10.99..-12.43% | [-4.58,+0.83]% | none; whipsaws | REJECT |
| multi-lookback gate hardening | n/a | n/a | n/a | n/a | SKIP (needs sleeve internals) |

ADOPT-CANDIDATE: stress-amplified VT (tgt-20% or cap-0.75). It STRICTLY DOMINATES
plain VT-6040-expand on the hardening axis -- clean MaxDD -7.22 -> -6.50, Calmar
2.14 -> 2.28-2.32, and it finally relieves GFC (-7.22 -> -5.4..-6.1), the one
crisis plain VT could not move -- while Sharpe is directionally BETTER (not worse)
and the dMaxDD CI now clears zero. Same verdict CLASS as plain VT (drawdown/Calmar
hardening, not a significant Sharpe lift) but a measurably better hardening. The
mechanism is clean: VT base handles slow-vol grinds (2022/Euro/2025), the Sahm
stress amplifier handles the recession grind (GFC); the two relief channels stack
and, because stress fires only ~17% of months, the extra CAGR cost is bounded
(~0.6pp below plain VT).

REJECT: the daily drawdown governor (reactive price-DD stop with lag + hysteresis
whipsaws; worsens the binding tail) and calm-relaxed as a deployable strategy (it
wins Sharpe only by reverting toward baseline and surrendering the DD hardening that
is the entire point of the overlay).

CAVEATS / confidence (MODERATE, in-sample point estimates only):
- The GFC/Sharpe lift rides essentially ONE recession episode (GFC) plus the
  2008-2010 stress cluster; the clean window has few recessions. dSharpe CI still
  includes zero. The robust, CI-clearing claim is the DRAWDOWN relief, not Sharpe.
- The stress gate is effectively Sahm-only; the "OR credit (IG Baa-Aaa)" leg is
  redundant in this window and uses an IG proxy (no HY OAS locally).
- UNRATE is the REVISED FRED print, not vintage/ALFRED -> the Sahm-conditioned
  results may be modestly optimistic. A 2024-09 Sahm false-positive shows up as a
  small calm-period CAGR drag (honest cost of the gate).
- COVID and the binding ext tail (-9.94%) and the 2010 flash bar are unmoved -- no
  monthly overlay catches fast V-reversals or single-bar gaps.
- No walk-forward / OOS split was run; pre-adoption gate = the same WF/OOS
  stability test the prior note already flagged for plain VT, now applied to the
  stress-amplified variant (and ideally re-run on vintage UNRATE + real HY OAS).

---

## Reproduction artifacts

- `/tmp/taa_adaptive_governor_run.py` -- this experiment (reads cached baseline +
  engine `load_panel`, macro CSVs; reuses `core.perf_metrics`,
  `research.cpm_bootstrap_multimetric.paired_block_bootstrap_mm`).
- `/tmp/taa_adaptive_governor_raw.md` -- raw run output.
- `/tmp/taa_baseline_series.parquet` -- cached canonical baseline daily series
  (blend + 4 sleeves + cash), built by the prior validation run `/tmp/taa_probe.py`.
- Repo code reused (read-only): `build_dashboard.build_artifacts` (via cache),
  `cpm_live.load_panel`, `core.perf_metrics`,
  `research.cpm_bootstrap_multimetric`.
- Data: production price panel (`load_panel`, stitched proxies);
  `research/_macro_cache/UNRATE.csv`; `data/fred_BAA.csv`; `data/fred_AAA.csv`.

Commands:

```bash
cd /Users/rkautsar/personal/scripts/strategy_cpm
.venv/bin/python /tmp/taa_adaptive_governor_run.py   # ~1 min (uses cached series)
# if the cache is missing, rebuild it first:
# .venv/bin/python /tmp/taa_probe.py
```
