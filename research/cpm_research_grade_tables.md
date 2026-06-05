# CPM research-grade tables (oracle review compute pack)

Role: analyst (research-only). No memo / README / dashboard / production edits; no commit.

All numbers below are CANONICAL convention: mooex (T+1 MOO exact), both-252
(CORR_LOOKBACK_DAYS=252), clean window 2008-05-30..2026-05-22 (+ext 1999-03-10
where shown), 10 bps/side baseline, memo bootstrap params B=2000 / block=21 / seed=42.

Gate checks (all pass): CPM clean mooex Sharpe = 1.2557 (== cpm_harness.ANCHOR);
PROD 60/20/20 clean mooex Sharpe = 1.4424 (== README headline); factorial 8-cell
all-OFF = 0.8670 (HAA) and all-ON = 1.2557 (CPM).

Scripts (this work):
- research/cpm_research_grade_compute.py        -> .json  (items 1, 4)
- research/cpm_research_grade_offset_cliff.py   -> .json  (item 2)
- research/cpm_research_grade_rung_ci.py        -> .json  (item 3)
Reused: cpm_harness, exec_lag_moo_validation_2026_05_30 (mooex engine),
cpm_haa_coupled_factorial_v2 (param_wf), build_dashboard (canonical sleeve build),
cpm_execution_cliff.gen_sig_dates, bootstrap_ci_2026_05_28 (resampler).

PIT / cached-data caveat (applies to every table): numbers reflect the frozen
retail panel + cached macro/NDX-constituent opens used by the canonical harness,
not a live-trading reconstruction. yfinance re-adjustment drift is +/-0.05 Sharpe.

---

## (1) Cost sensitivity -- ready-to-insert

CPM sleeve and PROD 60/20/20 blend, clean window, mooex, at 10 / 25 / 50 bps per
side (cost applied per side on every sleeve at each rebalance). CPM one-way
turnover is ~2.58/yr, so each +1 bp/side is ~ -0.0052/yr drag before compounding.

```
Cost sensitivity (clean 2008-05-30..2026-05-22, mooex, both-252)

                CPM sleeve                          PROD 60/20/20 blend
Cost/side   Sharpe  Calmar    CAGR   MaxDD      Sharpe  Calmar    CAGR   MaxDD
10 bps      1.2557  1.0076   13.13%  -13.03%    1.4424  1.5566   16.33%  -10.49%
25 bps      1.1504  0.8978   11.93%  -13.29%    1.3397  1.4259   15.05%  -10.55%
50 bps      0.9712  0.7257    9.96%  -13.73%    1.1648  1.1690   12.94%  -11.07%

Extended-window Sharpe (1999-03-10..): CPM 1.2549 / 1.1518 / 0.9760;
                                       PROD 1.3888 / 1.2854 / 1.1091.
```

Reading: doubling cost to 25 bps/side costs CPM ~0.11 Sharpe and PROD ~0.10
Sharpe; 5x cost to 50 bps/side costs CPM ~0.28 and PROD ~0.28. PROD stays above
Sharpe 1.16 and Calmar 1.17 even at a punitive 50 bps/side. MaxDD is nearly
cost-invariant (the drag is in return/Sharpe, not tail). The 10 bps headline is
not knife-edge: the blend clears Sharpe 1.0 at every plausible retail cost.

---

## (2) Peer offset-cliff -- ready-to-insert

Signal/rebalance offset (EOM, EOM+1, EOM+2, EOM+3 business days) Sharpe for CPM,
AAA, and HAA, recomputed on ONE internally consistent basis. AAA and HAA
implementations were found and are runnable (see notes), so the memo's
"CPM least-affected" claim has comparator data and is SUPPORTED (not refuted).

AAA = canonical 10-asset Adaptive Asset Allocation (Butler-Philbrick 2012 style):
top-half by 6m momentum, SLSQP min-variance weights, no canary; universe
[SPY,EZU,EWJ,EEM,IYR,RWX,IEF,TLT,DBC,GLD], SHV/IEF fallback
(research/cpm_benchmarks_proper.make_canonical_aaa_wf, inlined).
HAA = Keller-Keuning Hybrid simple: TIP 13612U canary + SPY 13612U trend +
best-of-safe{SHV,IEF} (sleeve_vs_benchmark make_haa_simple_wf, inlined).

```
Offset cliff, mooex (T+1 MOO exact), CLEAN 18y, 10 bps/side -- PRIMARY
(EOM matches canonical CPM anchor 1.2557)

Strategy   EOM     EOM+1   EOM+2   EOM+3   abs deg   % deg
CPM        1.2557  1.1867  1.0826  1.0028  -0.2528   -20.1%   (shallowest)
AAA        0.9542  0.5476  0.6287  0.6702  -0.2840   -29.8%   (steepest)
HAA        0.9821  0.7398  0.7489  0.7397  -0.2425   -24.7%

Corroboration, close-to-close exec_lag=0 (T+0 MOC economics), CLEAN 18y
(research/cpm_execution_cliff_peer_sanity_2026_06_01.json)

Strategy   EOM     EOM+1   EOM+2   EOM+3   % deg
CPM        1.2063  1.0127  0.9747  0.9090  -24.6%   (shallowest)
AAA-style  0.9961  0.5462  0.6675  0.6991  -29.8%   (steepest)
HAA-Simple 0.9839  0.7420  0.7613  0.7215  -26.7%
```

Verdict: CPM has the SHALLOWEST cliff of the three peers in BOTH conventions
(% degradation -20.1% / -24.6% vs AAA -29.8% and HAA -24.7% / -26.7%). The
month-end execution cliff is a GENERIC monthly-TAA / turn-of-month property, and
CPM is the least, not the most, affected. The memo's "CPM least-affected vs
AAA/HAA cliff" claim is supported.

FLAGS for the fixer (do not assert without addressing):
- The memo's CURRENT stated CPM cliff (lines 31, 60-62): 1.2557 -> 0.9743 ->
  0.9628 -> 0.8714 (-30.6%) is INTERNALLY INCONSISTENT. The EOM value (1.2557) is
  the canonical mooex anchor, but the three offsets (0.9743 / 0.9628 / 0.8714) were
  carried over from the both-252 inverse-vol REBASELINE run whose own EOM was 1.1658
  (research/cpm_rebaseline_both252.md L377), a different weighting config. Replace
  with the consistent canonical mooex set 1.2557 -> 1.1867 -> 1.0826 -> 1.0028, OR
  adopt the cc peer-sanity set; either way be consistent across EOM and offsets.
- AAA under mooex falls back to close-to-close on 100% of rebalance days (the 4
  extra tickers EWJ/RWX/EZU/IYR lack open-cache OHLC), so AAA's "mooex" row is
  effectively cc economics. The OFFSET-degradation shape is convention-robust
  (driven by held-period returns, not the single rebalance-day attribution), and
  the cc corroboration row confirms the same ranking, so the ranking conclusion
  holds. But do not present AAA's absolute mooex EOM (0.9542) as a true mooex
  number without this caveat. CPM and HAA have full mooex coverage (217/217).

---

## (3) Min-var / decomposition rung CIs -- ready-to-insert

Paired block bootstrap (B=2000, block=21, seed=42; common block indices across
all 8 factorial cells per draw) on the HAA->CPM 2^3 decomposition. Effects are
the same factor model as research/cpm_haa_coupled_factorial_v2.py. Sharpe per draw
is order-invariant (mean*252)/(std*sqrt252), matching cpm_live.perf_metrics.

Level reference: the PROD clean Sharpe block-bootstrap 95% CI half-width is ~0.43
(README [0.954, 1.823]); a single-sleeve Sharpe CI half-width is similar (~0.40).

```
HAA->CPM rung-delta CIs (clean, mooex, both-252, 10 bps/side; B=2000 block=21 seed=42)

Effect                         Point    95% CI            p(>0)   Verdict
Universe (U main effect)      +0.2215  [+0.029, +0.402]   0.985   SIGNIFICANT (clears 0)
Ranker   (R main effect)      +0.0647  [-0.048, +0.176]   0.875   WITHIN NOISE (CI spans 0)
Min-var  (M main effect)      +0.0902  [-0.008, +0.189]   0.966   WITHIN NOISE (CI spans 0)
Min-var  (M at corner U1R1)   +0.1682  [+0.043, +0.291]   0.999   SIGNIFICANT (clears 0)

Sequential ladder rungs (point): +U 0.8670->1.0189 (+0.1519);
  +R 1.0189->1.0874 (+0.0685); +M 1.0874->1.2557 (+0.1682).
```

One-line significance verdict per rung:
- Universe: SIGNIFICANT -- only rung whose main-effect 95% CI clears zero; the
  dominant, robust contributor.
- Ranker: WITHIN NOISE -- main-effect CI spans zero (p>0 = 0.875); positive in
  expectation but not statistically distinguishable from zero at this sample.
- Min-var: WITHIN NOISE on the symmetric main effect (CI spans zero, p>0 = 0.966),
  but SIGNIFICANT at the production corner (U1R1: +0.1682, CI [+0.043, +0.291],
  p>0 = 0.999). Honest statement: min-var is universe-conditional -- it earns its
  keep only on the CPM cross-asset universe, where it is significant; averaged
  across HAA-8 corners it washes into noise.

Honest framing for the memo: of the three HAA->CPM factors, only the Universe
switch is unambiguously significant. Ranker and the symmetric Min-var main effect
are within bootstrap noise; Min-var is significant only at the realized production
corner. None of the individual rung point deltas exceed the ~0.40 level CI
half-width, so each is small relative to the absolute Sharpe estimation error.

---

## (4) Corrected README PROD bootstrap -- ready-to-insert

The README bootstrap (research/bootstrap_ci_2026_05_28.py) resampled SIMPLE
close-to-close daily returns from run_cpm_backtest / run_bull_spy_backtest /
run_ndx_backtest (a T+0 MOC construction). Its realized Point (CAGR 16.69% / Vol
11.78% / MaxDD -12.16% / Calmar 1.372) does NOT match the mooex-accounted headline
(16.33% / 10.93% / -10.49% / 1.56), and its p97.5 MaxDD -10.85% is shallower than
the headline -10.49% because the two are different series. (Sharpe 1.442 matched
only by coincidence.)

Recompute on the SAME mooex blend used for the headline (canonical build_dashboard
sleeve construction: CPM/BULL engine mooex + NDX prod-cc + constituent-opens mooex
delta), same stationary block bootstrap (B=2000, block=21, seed=42). Point now
matches the headline exactly.

```
PROD 60/20/20 bootstrap CI -- mooex-accounted (matches headline)
Stationary block bootstrap, B=2000, block=21d, seed=42, n=4524 (clean 18y)

Metric    Point     p2.5      p25       p50       p75       p97.5
Sharpe    1.4424    1.0315    1.2939    1.4448    1.5932    1.8764
CAGR      16.33%    11.31%    14.50%    16.35%    18.25%    21.84%
Vol       10.93%    10.12%    10.66%    10.94%    11.22%    11.80%
MaxDD    -10.49%   -20.59%   -15.22%   -13.14%   -11.64%    -9.47%
Calmar    1.5566    0.6423    0.9877    1.2339    1.4818    2.0900

95% CI: Sharpe [1.03, 1.88], CAGR [11.31%, 21.84%], MaxDD [-20.59%, -9.47%],
Calmar [0.64, 2.09].
```

Methodology note (one line, for the fixer): the prior README bootstrap resampled
simple close-to-close sleeve returns (T+0 MOC), giving a Point that diverged from
the mooex headline; this version resamples the identical mooex-accounted PROD blend
that produces the 1.4424 headline, so Point == headline and the p97.5 MaxDD
(-9.47%, naturally shallower than the realized -10.49% under block reshuffling) is
no longer paradoxical.

---

## (5) Execution-lag table -- assembled (no new compute)

Source: research/cpm_t1moc_canonical_findings.md sec (b) (engine
exec_lag_moo_validation_2026_05_30; mooex = canonical T+1 MOO with true opens for
NDX/PROD). Assembled for the memo robustness section.

```
Execution-lag sensitivity, CLEAN 2008-05-30..2026-05-22 (both-252, 10 bps/side)

CPM sleeve            T+0 MOC   T+1 MOO   T+1 MOC
  Sharpe              1.2926    1.2557    1.2230
  CAGR                13.55%    13.13%    12.76%
  MaxDD              -11.57%   -13.03%   -13.61%
  Calmar              1.1709    1.0076    0.9371

PROD 60/20/20         T+0 MOC   T+1 MOO   T+1 MOC
  Sharpe              1.4960    1.4424    1.3911
  CAGR                17.02%    16.33%    15.69%
  MaxDD              -10.46%   -10.49%   -10.34%
  Calmar              1.6263    1.5566    1.5179

Extended-window Sharpe: CPM 1.2913 / 1.2549 / 1.2307; PROD 1.4308 / 1.3888 / 1.3479.
```

Framing sentence (ready to insert): "T+1 MOO is the realistic executable
convention (signal at month-end close, fill at the next session's open); T+0 MOC
is the unattainable same-close ideal (it trades on the very close used to compute
the signal); each session of execution lag costs PROD ~0.05 Sharpe (CPM
~0.03-0.04), so the realistic-vs-ideal gap is ~0.05 PROD Sharpe, while the tail is
invariant -- PROD MaxDD holds at -10.3% to -10.5% across all three conventions."

---

## Computability summary

| Item | Status |
|---|---|
| (1) Cost sensitivity 10/25/50 bps | COMPUTED, clean (gate: 10bps = 1.2557 / 1.4424) |
| (2) Peer offset cliff CPM/AAA/HAA | COMPUTED, mooex + cc corroboration; AAA mooex = cc-fallback (flagged) |
| (3) Rung-delta CIs (U/R/M/corner) | COMPUTED, paired block bootstrap (gates: 0.8670 / 1.2557) |
| (4) README PROD bootstrap reconcile | COMPUTED, Point matches headline exactly |
| (5) Execution-lag table | ASSEMBLED from cpm_t1moc_canonical_findings (no new compute) |

Open flags handed to the fixer: memo CPM offset numbers (L31/L60-62) are
internally inconsistent and should be replaced with one consistent set; AAA mooex
coverage caveat must accompany any AAA mooex absolute number.
