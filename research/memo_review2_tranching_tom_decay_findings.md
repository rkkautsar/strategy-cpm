# CPM memo review-2: A4 (tranching mitigation) + C (TOM structural-vs-cyclical)

Analyst, read-only. Reuses production `cpm_live.py` signal/weight fns UNCHANGED
and the `research/cpm_execution_cliff.py` timing harness (`gen_sig_dates`,
`cpm_cc_returns`, `sharpe_of`) UNCHANGED. Does NOT edit memo/prod; not committed.

- Harness: `research/memo_review2_A4_C_harness.py`
- Output: `research/memo_review2_A4_C_findings.json`
- Run: `.venv/bin/python research/memo_review2_A4_C_harness.py`
- Convention: close-to-close (cc), exec_lag handled via tranche offsets, 10 bps/side,
  clean window 2008-05-30..2026-05-22. Same convention as the memo's execution-cliff battery.

## Anchor reproduction (gate)

CPM clean cc EOM Sharpe reproduced = **1.2063** (matches
`research/cpm_tom_decay_findings.json` `anchor_full_clean_sharpe` = 1.2063).
TOM subperiod numbers also reproduce the memo context exactly:
2018-22 day-1 = 19.0 bps vs rest 4.1; 2023-26 = 6.2 vs 7.1 (0.87x, inverted).
Within-harness comparisons are therefore apples-to-apples with the memo.

Offset axis note: in this harness the tranche `offset` shifts the EXECUTION day
only, while the signal is always computed at EOM. So single-scheme `eom+1`
(= execute one day after EOM, signal at EOM) = **1.207**, matching the cc anchor
(1.206). The memo's headline cliff (`eom,k` rule) additionally shifts the SIGNAL
date with k, so it is steeper; this harness isolates pure execution-day slippage,
which is the relevant axis for an execution-timing-robustness argument.

---

## A4. Tranching mitigation (ILLUSTRATIVE -- NOT a production change)

Model: a base offset `o` shifts the whole tranche schedule vs EOM. Each month the
held basket transitions linearly from last month's realised target to this month's
target across the tranche days (`held = (1-cum_frac)*w_old + cum_frac*w_new`).
Total turnover (hence cost) is invariant to tranching; only its placement differs.

- single     = `[(o, 1.0)]`
- 2tr_5050   = `[(o, 0.5), (o+1, 0.5)]`
- 3tr_thirds = `[(o, 1/3), (o+1, 1/3), (o+2, 1/3)]`

Cliff = Sharpe across the execution-offset grid o in {0,1,2,3} (EOM..EOM+3).
Robustness = std/range of Sharpe across that grid (lower = flatter cliff).

### Sharpe across the execution-offset grid

| scheme      | EOM   | EOM+1 | EOM+2 | EOM+3 | peak  | mean  | min   | std    | range  |
|-------------|-------|-------|-------|-------|-------|-------|-------|--------|--------|
| single      | 1.255 | 1.207 | 1.152 | 1.106 | 1.255 | 1.180 | 1.106 | 0.0560 | 0.149  |
| 2tr_5050    | 1.233 | 1.181 | 1.131 | 1.112 | 1.233 | 1.164 | 1.112 | 0.0468 | 0.120  |
| 3tr_thirds  | 1.208 | 1.159 | 1.128 | 1.104 | 1.208 | 1.150 | 1.104 | 0.0389 | 0.104  |

### Cliff-flattening vs single-day

| scheme     | std (vs single) | range (vs single) | peak give-up | mean give-up |
|------------|-----------------|-------------------|--------------|--------------|
| single     | 0.0560 (--)     | 0.149 (--)        | --           | --           |
| 2tr_5050   | 0.0468 (-16%)   | 0.120 (-19%)      | -0.022       | -0.016       |
| 3tr_thirds | 0.0389 (-31%)   | 0.104 (-30%)      | -0.047       | -0.030       |

### A4 verdict

Tranching does what the hypothesis predicts: it trades a little peak Sharpe for
robustness to execution-day timing.

- 3-tranche cuts cliff dispersion ~30% (std 0.056 -> 0.039; range 0.149 -> 0.104)
  for ~0.047 of peak Sharpe and ~0.030 of mean Sharpe.
- 2-tranche is the cheaper middle: ~16-19% flatter cliff for only ~0.02 peak / ~0.016 mean.
- Mechanism: spreading execution means a one-day slip only mis-times a fraction of
  the trade, so the worst-case (EOM+3) Sharpe rises (1.106 -> 1.112 -> ... the floor
  lifts while the EOM peak is shaved), compressing the EOM..EOM+3 spread.

Caveat: illustrative only. Single-sample backtest; the per-day cliff differences
are well inside backtest noise. Cost is modelled as turnover-invariant (real
multi-day execution can add slippage/impact, partially offsetting the benefit).
Not an adoption recommendation -- it is a robustness illustration for the memo's TOM section.

---

## C. TOM structural vs cyclical decomposition

### C1. Decay shape (per calendar year; NOISY -- flag)

~11-12 day-1 observations per year => estimates are very noisy; 95% CIs on the
day-1 mean routinely span +/-40 to +/-90 bps. Read the shape, not the points.

| year | n | day1 bp | rest bp | premium bp | day1 95% CI |
|------|---|---------|---------|------------|-------------|
| 2008 | 7 | 29.4 | 3.3 | 26.1 | [-10, 69] |
| 2009 | 12 | 18.3 | 5.9 | 12.4 | [-80, 116] |
| 2010 | 12 | 56.8 | 4.2 | 52.6 | [8, 106] |
| 2011 | 12 | 14.2 | 3.2 | 11.0 | [-35, 63] |
| 2012 | 12 | -2.4 | 2.7 | -5.2 | [-31, 26] |
| 2013 | 12 | 26.3 | 6.7 | 19.6 | [-14, 67] |
| 2014 | 12 | -35.4 | 8.1 | -43.6 | [-83, 12] |
| 2015 | 12 | 22.0 | -1.6 | 23.5 | [2, 42] |
| 2016 | 12 | 10.1 | 4.2 | 5.9 | [-13, 33] |
| 2017 | 12 | 24.0 | 7.4 | 16.6 | [1, 47] |
| 2018 | 12 | -15.5 | 2.0 | -17.5 | [-50, 19] |
| 2019 | 12 | -10.6 | 5.8 | -16.5 | [-46, 25] |
| 2020 | 12 | 53.9 | 6.2 | 47.7 | [29, 79] |
| 2021 | 12 | 56.7 | 6.9 | 49.9 | [10, 103] |
| 2022 | 12 | 10.6 | -0.2 | 10.9 | [-12, 33] |
| 2023 | 12 | 12.9 | -0.1 | 13.1 | [-14, 40] |
| 2024 | 12 | -5.5 | 6.5 | -12.0 | [-53, 42] |
| 2025 | 12 | 13.5 | 9.8 | 3.6 | [-12, 39] |
| 2026 | 5 | 0.9 | 20.6 | -19.7 | [-91, 93] |

5-year subperiod day-1 bp (from `cpm_tom_decay_findings.json`):
**22.7 (2008-12) -> 9.4 (2013-17) -> 19.0 (2018-22) -> 6.2 (2023-26)**.

Shape read: **NOT a monotone secular decline.** The series dips (2013-17 = 9.4)
then REBOUNDS to 19.0 in 2018-22 (driven by huge 2020-21 spikes, +48/+50 bp),
before collapsing to 6.2 in 2023-26. A pure structural/crowding death would be
monotone; this is regime-lumpy with a mid-sample rebound. The "decay" is really a
recent (2023-26) compression layered on top of high year-to-year volatility.

### C2. Regime correlation (mega-cap-narrow / breadth collapse)

Breadth proxy = annual RSP/SPY relative total return (equal-vs-cap). Negative =
mega-cap-narrow regime.

- 2023 RSP-SPY = -12.9%, 2024 = -12.8%, 2025 = -6.5% -- the most negative
  (narrowest-breadth) cluster in the whole 2004-26 sample, and it coincides
  with the TOM compression (premium 13.1, -12.0, 3.6 bp).
- 2020-21 (post-COVID broadening / strong tape) coincides with the biggest TOM
  spikes (+47.7, +49.9 bp).
- Full-sample correlation (n=19 yrs): corr(TOM premium, RSP-SPY) = **+0.16**;
  corr(day1 bp, RSP-SPY) = **+0.17**. Weak-positive: TOM premium tends to be
  larger when breadth is healthy, but the relationship is loose.

So the 2023-26 compression IS coincident with the breadth-collapse / mega-cap
regime (a cyclical signal), but the cross-year link is weak and swamped by noise.

### C3. Literature check (sourced)

- McLean & Pontiff (2016, J. Finance, "Does Academic Research Destroy Stock
  Return Predictability?"): cross-section of 97 predictors; average anomaly
  long-short return is ~26% lower out-of-sample and ~58% lower post-publication.
  => a generic prior that published anomalies (incl. TOM, published by
  Lakonishok & Smidt 1988) partially crowd/fade after publication.
  Sources: papers.ssrn.com (SSRN abstract), jstor.org, abfer.org.
- McConnell & Xu (2012, "Equity Returns at the Turn of the Month", Purdue/CIBER
  wp 43; FAJ): the TOM effect in U.S. equities has persisted for >100 years
  (Lakonishok-Smidt DJIA 1897-1986, extended through mid-2000s), is robust across
  subperiods, large-caps and small-caps, and is concentrated in the last trading
  day through the third business day -- exactly the day-1 window measured here.
  => TOM is an unusually DURABLE anomaly, not a fast post-publication death.
  Sources: business.purdue.edu (PDF), docs.lib.purdue.edu/ciberwp/43.
- Vidal & Vidal-Garcia (SSRN 4106003): TOM concentrated in last trading day to
  3rd business day; days before last business day and after 3rd have no
  significant effect -- consistent with our day-1-centric attribution.

Net lit read: the academic record says TOM is one of the more persistent
calendar anomalies (100+ yr), which argues AGAINST a clean structural death;
but McLean-Pontiff supplies a real prior that some post-publication crowding fade
exists generically.

### C VERDICT: BOTH, weighted toward cyclical + sampling noise (NOT clean structural decay)

- Against pure STRUCTURAL secular crowding: the decay shape is non-monotone
  (2013-17 dip then 2018-22 rebound to 19 bp), and the literature documents TOM
  as a 100+ year persistent effect rather than a fast-fading post-publication
  anomaly. A clean secular crowding death is not supported.
- For a CYCLICAL component: the 2023-26 compression coincides with the most
  extreme mega-cap-narrow / breadth-collapse cluster on record (RSP-SPY ~-13%
  in 2023 and 2024), and TOM premium is weakly positively correlated with breadth
  (+0.16). This is consistent with TOM being a partial byproduct of broad-tape /
  breadth conditions that mean-revert.
- Dominant caveat -- NOISE: at annual granularity the premium is statistically
  fragile (CIs +/-40-90 bp; single 2023-26 window). Much of the apparent "decay"
  is indistinguishable from sampling variation. This is a single sample.

Weighting (qualitative): ~50% cyclical/regime, ~35% noise, ~15% structural crowding.

### Practical implication for the memo

Treat the forward TOM contribution as **~0; do NOT underwrite it.** This holds
regardless of which mechanism dominates:

- If cyclical, the premium may mean-revert with breadth -- but you cannot time it,
  and underwriting it forward is a bet on a regime turn.
- If structural, it keeps fading.
- If noise, there is nothing to underwrite.

This is also costless to assume: removing TOM (day-1) entirely costs only ~0.001
Sharpe in 2023-26 (`sharpe_drop_from_day1` = 0.0006), and the strong recent CPM
Sharpe (~1.49 in 2023-26) is NOT TOM-driven (day-1 share of P&L = 4.2%). The memo
should keep the headline number while treating TOM as a historical, non-underwritten
tailwind. The A4 tranching illustration further shows the strategy can be made
robust to the execution-timing axis that TOM sensitivity rides on.

---

## Caveats / confidence

- Anchor reproduced; cc/exec_lag convention consistent with the memo battery. (high)
- A4 cliff-flattening direction is robust and mechanically expected; magnitude is a
  single-sample point estimate inside backtest noise; cost modelled turnover-invariant
  (real multi-day slippage could erode part of the benefit). (medium)
- C annual TOM estimates are very noisy (CIs +/-40-90 bp, ~12 obs/yr); breadth
  correlation is weak (+0.16) on n=19 years; single sample. Verdict is directional,
  not a precise decomposition. (medium-low on magnitudes; medium on the
  do-not-underwrite conclusion, which is robust to the mechanism).
- Breadth proxy (RSP/SPY) fetched live via the repo's cached fetch helper; RSP
  inception 2003 limits pre-2003 coverage (not needed: clean window starts 2008).

## Handoff

None required for analysis. If the memo's TOM section is to be edited to add the
A4 illustration or the structural-vs-cyclical verdict, route the prose edit to the
fixer (memo edits are out of analyst scope).
