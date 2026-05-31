# CPM vs AAA over AAA's Post-Paper Out-of-Sample Window (2016-2026)

Analyst research. Read-only re production/memo. Writes research/ only. No prod or
memo edits. No commit.

Scripts:
- `research/cpm_vs_aaa_oos.py` (this run; primary mooex comparison + degradation pull)
- reuses `research/cpm_benchmarks_proper.py` (mooex engine, CPM + Canonical_AAA)
- pulls AAA paper-window metrics from `research/cpm_class_significance_sanity.json`

Data: `research/cpm_vs_aaa_oos.json`

## Question

How does an AAA-style benchmark fare versus CPM in AAA's genuine post-paper
out-of-sample period? AAA (Adaptive Asset Allocation; Butler, Philbrick,
Gordillo, Varadi; ReSolve, SSRN 2328254) has a paper in-sample window of
1995-2015. So 2016-01 .. 2026-05 (~10 years) is AAA's real OOS. Compute CPM vs
Canonical-AAA over that window on the same engine, apples-to-apples; assess
whether AAA decayed after publication; and frame the in-sample/OOS asymmetry
honestly.

## Verdict (up front)

1. AAA did NOT decay after publication. On its own monthly-close engine and its
   own paper windows, AAA's Sharpe went from 1.068 (in-sample 1995-2015) to 1.228
   (OOS 2016-2026), delta +0.160; Calmar 0.741 -> 0.836, delta +0.095. AAA held
   up -- if anything its point estimates improved post-paper (the 2016-2025 risk
   regime was kind to defensive global momentum). So AAA is a strong, non-decayed
   benchmark over its OOS.

2. CPM still beats AAA over 2016-2026, by about the same margin as over the full
   clean window. Same mooex T+1 MOO engine: CPM Sharpe 1.3610 vs AAA 1.1248,
   dSharpe +0.236 (full-clean edge is +0.248 -- essentially identical). CPM also
   leads on Calmar (+0.68) and Martin (+3.0), driven by a shallower MaxDD
   (-12.7% vs -21.8%). BUT the paired daily block bootstrap dSharpe 95% CI is
   [-0.220, +0.671], which includes zero -- within-noise, same class-level
   sub-significance seen everywhere in this family.

3. CRITICAL ASYMMETRY: 2016-2026 is AAA's OOS but largely CPM's IN-SAMPLE. CPM
   was developed and selected on the 2008+ clean window, which fully contains
   2016-2026. So CPM's +0.24 edge in this slice is a CPM-in-sample vs AAA-OOS
   comparison, not a fair OOS-vs-OOS test. The edge is in-sample-flattered for
   CPM and should NOT be read as clean OOS evidence for CPM.

## Engine and convention (stated explicitly)

Two engines are used; each comparison is internally consistent on ONE engine.

PRIMARY (CPM vs AAA; full-clean and AAA-OOS rows): mooex T+1 MOO exact, 10
bps/side, monthly month-end signal. Byte-identical harness across CPM and
Canonical_AAA via `cpm_benchmarks_proper.py`. Canonical AAA = 10-asset
[SPY, EZU, EWJ, EEM, IYR, RWX, IEF, TLT, DBC, GLD], top-half by 6m total-return
momentum, SLSQP min-variance weights (504d cov), no canary. In mooex, AAA can
only start ~2008-01 (RWX inception 2006-12 + warmup, and real intraday opens do
not exist earlier), so the 2016-2026 OOS slice is fully covered but the 1995-2015
in-sample is NOT reachable in this engine.

DEGRADATION (AAA in-sample 1995-2015 vs OOS 2016-2026): monthly-close TR engine,
month-end signal, hold next month, 10 bps/side, dynamic AAA universe with
documented proxy splices back to 1995 (from the prior class-significance run,
`cpm_class_significance_sanity.json`). Both AAA windows come from this one engine,
so the in-sample-vs-OOS delta is internally consistent.

Cross-engine note: the mooex AAA-OOS Sharpe (1.1248) and the monthly-close
AAA-OOS Sharpe (1.2278) differ because the engines differ (mooex T+1 MOO with
real opens vs monthly close, and mooex AAA = strict canonical 10-asset vs the
monthly-close dynamic-universe AAA). Both are legitimate; they are used only
within their own comparison, never mixed in a single delta.

Anchor sanity (PASS): CPM clean (2008-05-30 .. 2026-05-22) Sharpe = 1.1910,
MaxDD -12.67%, Calmar 1.0615 -- matches the headline full-clean number exactly.

## Results -- CPM vs AAA (mooex T+1 MOO, same engine for both)

| window                       | series        | Sharpe | CAGR   | Vol    | MaxDD   | Calmar | Martin | n_days |
|------------------------------|---------------|--------|--------|--------|---------|--------|--------|--------|
| FULL CLEAN 2008-05 .. 2026-05| CPM           | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 | 4524   |
|                              | Canonical_AAA | 0.9435 |  9.23% |  9.92% | -21.76% | 0.4241 | 1.6230 | 4524   |
|                              | 60/40         | 0.7946 |  8.75% | 11.42% | -29.82% | 0.2936 | 1.4023 | 4524   |
| AAA OOS 2016-01 .. 2026-05   | CPM           | 1.3610 | 15.01% | 10.75% | -12.67% | 1.1852 | 4.6650 | 2612   |
|                              | Canonical_AAA | 1.1248 | 10.94% |  9.66% | -21.76% | 0.5027 | 1.6511 | 2612   |
|                              | 60/40         | 0.9291 |  9.86% | 10.68% | -21.02% | 0.4689 | 1.7397 | 2612   |

CPM-minus-AAA differences:

| window     | dSharpe | dCAGR   | dCalmar | dMartin | bootstrap dSharpe 95% CI        | significant? |
|------------|---------|---------|---------|---------|----------------------------------|--------------|
| FULL CLEAN | +0.2475 | +4.22%  | +0.6375 | +2.3415 | (prior run: incl. zero)          | NO           |
| AAA OOS    | +0.2363 | +4.07%  | +0.6825 | +3.0139 | [-0.2203, +0.6715] (B=3000, blk21)| NO           |

The OOS-slice CPM edge (+0.236 Sharpe) is essentially the same magnitude as the
full-clean edge (+0.248). The bootstrap CI over the OOS window straddles zero, so
the edge is within sampling noise -- consistent with the class-wide
sub-significance result.

## Results -- AAA degradation (monthly-close engine, AAA's own paper windows)

| window                | range                    | Sharpe | Calmar | MaxDD   | CAGR   | n_mo |
|-----------------------|--------------------------|--------|--------|---------|--------|------|
| IN-SAMPLE (paper)     | 1995-01-31 .. 2015-12-31 | 1.0679 | 0.7408 | -13.00% |  9.63% | 251  |
| POST-PAPER OOS        | 2016-01-31 .. 2026-05-22 | 1.2278 | 0.8356 | -13.19% | 11.02% | 124  |
| (context) COMMON 18y  | 2008-05-31 .. 2026-05-22 | 1.0687 | 0.7429 | -13.19% |  9.80% | 216  |

DELTA (OOS minus in-sample): dSharpe +0.160, dCalmar +0.095. AAA's out-of-sample
risk-adjusted performance HELD UP and slightly improved on point estimates -- no
post-publication decay over this window. (MaxDD essentially unchanged ~-13%.)

## Asymmetry quantification and honest framing

- The window 2016-2026 is AAA's true OOS (paper ended 2015) but is inside CPM's
  development/selection sample (CPM was tuned on the 2008+ clean window, which
  contains 2016-2026). The CPM-vs-AAA OOS comparison is therefore
  CPM-in-sample vs AAA-OOS -- an unfair, CPM-favoring asymmetry.

- Direction of the asymmetry: it inflates CPM's apparent edge. A strategy
  evaluated on its own selection window carries optimistic bias (parameters,
  universe, and rule choices were retained partly because they performed well in
  exactly that data). The honest expectation is that CPM's true OOS edge over AAA
  is SMALLER than the +0.236 measured here.

- Magnitude context: AAA itself moved +0.160 Sharpe from in-sample to OOS (i.e.
  no decay; even improved). If CPM degraded out-of-sample by even a modest amount
  typical of selected TAA strategies (a few tenths of Sharpe), CPM's entire
  +0.236 edge over AAA could be erased. The bootstrap CI already includes zero,
  so the edge is statistically indistinguishable from no-difference even before
  applying the selection-bias haircut.

- Bottom line for fairness: there is NO clean OOS-vs-OOS slice available with
  this data (AAA cannot be run pre-1995 reproducibly, and CPM's clean history is
  its own in-sample). The 2016-2026 CPM win is suggestive but selection-flattered;
  it is not clean out-of-sample evidence that CPM beats AAA.

## Caveats and confidence

- Two engines: primary CPM-vs-AAA on mooex; degradation on monthly-close. Each
  delta stays within one engine. Cross-engine AAA-OOS Sharpe differs (1.12 mooex
  vs 1.23 monthly-close) due to execution convention and AAA universe handling
  (strict canonical 10-asset vs dynamic-universe); this does not affect either
  internal comparison.
- mooex AAA cannot reach 1995, so AAA's in-sample number is only available on the
  monthly-close engine. The CPM-vs-AAA OOS comparison and the AAA degradation
  comparison are thus on different engines by necessity; they are reported
  separately and never mixed.
- Bootstrap CI over the ~10y OOS window uses daily returns, block=21, B=3000;
  n=2612 daily units. It includes zero -> within-noise, the class norm.
- AAA OOS holding up may reflect a benign regime for defensive global momentum
  (2016-2025), not a structural property; 124 months is still a single-regime-
  heavy sample.
- Confidence HIGH that (a) AAA did not decay post-paper and (b) the 2016-2026 CPM
  edge is in-sample-flattered and not statistically significant. Confidence
  MODERATE on the exact point magnitudes given the cross-engine necessity.

## Knowledge candidate

Over AAA's genuine post-paper OOS (2016-01 .. 2026-05), Canonical-AAA did NOT
decay -- its Sharpe rose from 1.068 (in-sample 1995-2015) to 1.228 OOS
(monthly-close engine), delta +0.16; Calmar 0.741 -> 0.836. On the same mooex
T+1 MOO engine over that OOS window, CPM (1.361) beats Canonical-AAA (1.125) by
dSharpe +0.236 (Calmar +0.68, Martin +3.0), about the same as the full-clean
edge (+0.248), but the bootstrap dSharpe CI [-0.22, +0.67] includes zero (not
significant). CRITICAL: 2016-2026 is AAA's OOS but CPM's in-sample (CPM selected
on the 2008+ window), so this is a CPM-in-sample vs AAA-OOS asymmetry that
inflates CPM's apparent edge; it is NOT clean OOS-vs-OOS evidence for CPM. A
truly fair OOS-vs-OOS slice is unavailable with reproducible data.
