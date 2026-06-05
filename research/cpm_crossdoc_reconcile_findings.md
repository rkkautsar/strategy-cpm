# CPM cross-doc number reconciliation: memo vs README vs dashboard

Analyst note. Research artifact only. No memo/README/dashboard/prod files edited;
no commit. All numbers recomputed from frozen in-repo data via
`research/cpm_crossdoc_reconcile_recompute.py` (run with `.venv/bin/python`).

## TL;DR

The CPM sleeve disagreement is NOT a window, end-date, data-vintage, or
strategy-code-vintage problem. Both documents use the same clean window
(2008-05-30 -> 2026-05-22), the same frozen panel (`load_panel(live=False)`,
`EVAL_END = 2026-05-22`), the same both-252 baseline, and the same 10 bps/side
cost. The only difference is the rebalance-day EXECUTION CONVENTION:

- cpm_memo.md uses the `research/cpm_harness.py` path = `mooex` (T+1 MOO exact):
  old basket earns the overnight gap close[T]->open[T+1], new basket earns only
  the intraday open[T+1]->close[T+1]. This is the project's ENFORCED regression
  anchor (`cpm_harness.verify_anchor`, ANCHOR Sharpe 1.255673).
- README.md and build_dashboard.py use the `cpm_live.run_cpm_backtest` path =
  close-to-close T+1: the new basket captures the full overnight+intraday move
  close[T]->close[T+1] on the apply day.

Both numbers were reproduced exactly (to 4+ decimals) from frozen data. Vol is
essentially identical (10.275% mooex vs 10.266% close-to-close) because the
convention only re-attributes the rebalance-day overnight gap; it does not change
the held-position return stream. Sharpe, CAGR, MaxDD, Calmar, and Martin all move
because that gap lands on different weight vectors, and at the clean-window trough
(2025-04 tariff selloff) the attribution swings MaxDD by ~1.46 pp.

## (a) Root cause of the 1.2557-vs-1.291 gap

Both paths, same inputs (verified):

- Window: clean live-ETF 2008-05-30 -> 2026-05-22 (~17.98y). IDENTICAL.
- Data: frozen in-repo panel, `EVAL_END = 2026-05-22`, panel last = 2026-05-22. IDENTICAL.
- Covariance/rank lookback: `CORR_LOOKBACK_DAYS = 252` (both-252). IDENTICAL.
- Costs: 10 bps/side at each rebalance apply day. IDENTICAL.
- Weights: same `cpm_live.compute_target_weights` (TIP-only canary, equal-weight
  risky + min-var 3-of-4 at n_pos=4). IDENTICAL.

Sole difference = rebalance-day return attribution:

| Convention | Source | Rebalance-day return | Overnight gap goes to |
|---|---|---|---|
| mooex (T+1 MOO exact) | `cpm_harness.run_strategy` -> `exec_lag_moo_validation_2026_05_30._segment_returns_conv` | old overnight (close[T]->open[T+1]) compounded with new intraday (open[T+1]->close[T+1]) | OLD basket |
| close-to-close T+1 | `cpm_live.run_cpm_backtest` (close.ffill().pct_change(), new weights applied from T+1) | new basket close[T]->close[T+1] | NEW basket |

Reproduced from frozen data (both clean window 2008-05-30 -> 2026-05-22, n=4524 days):

| Metric | mooex (memo / enforced anchor) | close-to-close (README / dashboard) | gap |
|---|---:|---:|---:|
| Raw Sharpe (rf=0) | 1.2557 (1.255673) | 1.2912 (1.291217) | +0.0355 |
| Excess Sharpe (vs SHV) | 1.1262 (1.126205) | 1.1617 (1.161681) | +0.0355 |
| CAGR | 13.13% (0.131314) | 13.55% (0.135506) | +0.42 pp |
| Vol | 10.28% (0.102753) | 10.27% (0.102663) | -0.009 pp |
| MaxDD | -13.03% (-0.130317) | -11.57% (-0.115711) | +1.46 pp (shallower) |
| Calmar | 1.0076 (1.007646) | 1.1711 (1.171073) | +0.1635 |
| Martin | 4.2571 (4.257078) | 4.5711 (4.571093) | +0.314 |

The memo's headline (Sharpe 1.2557, CAGR 13.13%, Vol 10.28%, MaxDD -13.03%,
Calmar 1.0076, Martin 4.2571) matches the mooex path to displayed precision. The
README/dashboard headline (1.291 / 1.162 / 13.55% / 10.27% / -11.57% / 1.17 /
4.5711) matches the close-to-close path to displayed precision. Both are correct
for their own engine; they are simply two conventions reported under one
unlabeled metric name ("CPM clean window"), which is the contradiction.

Note: the prior `research/rebaseline_anchor_findings.md` pass rebaselined README
and build_dashboard CPM cells to the close-to-close values (1.2912 set) because
it sourced everything through `build_dashboard.build_artifacts()` (which calls
`run_cpm_backtest`). That pass was scoped to STRATEGY-CODE VINTAGE drift and never
compared its CPM row against the mooex enforced anchor, so it did not catch this
convention split. The memo was deliberately left untouched in that pass.

## (b) Recommended canonical CPM sleeve metric set

Pick the mooex / enforced-anchor numbers as canonical, on principled grounds:

1. `cpm_harness.verify_anchor` is a HARD regression guard in the repo
   (ANCHOR Sharpe 1.255673, MaxDD -0.130317, Calmar 1.007646). Publishing a CPM
   sleeve headline the enforced anchor does not reproduce is a latent
   contradiction with the codebase's own test surface.
2. mooex is the more faithful execution model (you trade at the T+1 open, so old
   positions genuinely earn the overnight gap and new positions only get the
   intraday leg). The harness module documents it as the "exact" convention; the
   close-to-close path is the production approximation.
3. The decision document (cpm_memo.md) already uses it consistently.

CANONICAL CPM sleeve (label exactly): "clean live-ETF window 2008-05-30 ->
2026-05-22 (~17.98y), mooex T+1 exact, both-252, 10 bps/side, frozen panel
EVAL_END 2026-05-22":

| Metric | Canonical value (display / full) |
|---|---|
| Raw Sharpe (rf=0) | 1.2557 (1.255673) |
| Excess Sharpe (vs SHV) | 1.1262 (1.126205) |
| CAGR | 13.13% (0.131314) |
| Vol | 10.28% (0.102753) |
| MaxDD | -13.03% (-0.130317) |
| Calmar | 1.0076 (1.007646) |
| Martin | 4.2571 (4.257078) |

IMPORTANT downstream implication (flag for oracle/fixer, do not silently ignore):
README and build_dashboard report the CPM sleeve alongside BULL, NDX, and the
PROD 60/20/20 blend, ALL of which currently come from the same close-to-close
`run_cpm_backtest`/`run_ndx_backtest`/blend path. If only the CPM row is switched
to mooex while BULL/NDX/PROD stay close-to-close, README becomes internally
inconsistent (one sleeve on a different convention from the rest of its own
table). Two coherent resolutions:

- PREFERRED (full consistency): migrate the README/dashboard sleeve table AND
  PROD blend headline to the mooex convention so every published number uses the
  enforced-anchor engine. This is a larger fix (BULL/NDX have their own engines)
  and is out of this CPM-scoped pass; recompute BULL/NDX/PROD under mooex before
  editing those rows. Magnitude is likely similar in direction to CPM (small
  Sharpe/CAGR shift, shallower-to-deeper MaxDD), but was NOT recomputed here.
- MINIMUM (label-only): keep README/dashboard on close-to-close but add an
  explicit convention label to every sleeve table ("execution: close-to-close
  T+1 approximation") and add a one-line note that the enforced research anchor
  (mooex) gives CPM 1.2557 / -13.03% / 1.0076, cross-referencing the memo. Then
  the same metric name never appears with two unlabeled values.

This decision (full migration vs label-only) is a release/scope call -> hand to
oracle/fixer. The analyst recommendation is the mooex set as the canonical
HEADLINE CPM number regardless of which resolution is chosen.

## (c) Full cross-doc number-mismatch inventory

cpm_memo.md is CPM-only; it does not quote PROD/BULL/NDX headline Sharpe/CAGR, so
the shared surface with README is the CPM sleeve plus CPM concentration and CPM
windows. Inventory of every shared-metric mismatch:

### C1. CPM sleeve clean-window stats -- CONVENTION MISMATCH (the main issue)

| Metric | memo (mooex) | README (close-to-close) | dashboard hardcode (close-to-close) |
|---|---:|---:|---:|
| Raw Sharpe | 1.2557 | 1.291 / 1.2912 | 1.2912 |
| Excess Sharpe | (not shown) | 1.162 | n/a |
| CAGR | 13.13% | 13.55% | 0.1355 |
| Vol | 10.28% | 10.27% | 0.1027 |
| MaxDD | -13.03% | -11.57% | -0.1157 |
| Calmar | 1.0076 | 1.17 / 1.1711 | 1.1711 |
| Martin | 4.2571 | 4.5711 | 4.5711 |

memo lines 150, 311 (and 5.5 / 5.6 / 5.9 restatements: 235, 251, 511, 522, 635,
652). README lines 44 (sleeve table), 53 (clean-window anchors table CPM row),
54 (CPM-BULL 60/40 row), 66 (raw-momentum blend rows). build_dashboard.py
sleeve_rows ~2317-2319 ("CPM clean window") and ~2313-2315 + cpm_bull_60_40_clean_anchor
~2398-2407 ("CPM-BULL 60/40").

### C2. CPM-BULL 60/40 (two-sleeve, no NDX) -- CONVENTION + OUT-OF-MEMO

README line 54 and dashboard hardcodes report CPM-BULL 60/40 = 1.2912 / 12.93% /
9.81% / -10.70% / 1.2089 / 4.6761 (close-to-close). The memo does not carry this
row. If the canonical convention is mooex, this row must be recomputed under
mooex (involves the BULL engine) before it can be reconciled; NOT recomputed in
this pass. Flag.

### C3. CPM concentration (clean) -- LIKELY DIFFERENT METRIC, not just convention

| Asset | memo 7.4 "risky contribution share" (clean) | README line 56 "share of risky sleeve exposure" (clean) |
|---|---:|---:|
| QQQ | 21.7% | 13.4% |
| SPHQ | 18.7% | 23.1% |
| GLD | 15.5% | 18.1% |
| EFA | 12.5% | 12.1% |
| EEM | 9.0% | 4.9% |
| VNQ | 8.2% | 6.8% |
| TLT | 7.3% | 12.7% |
| DBC | 7.1% | 9.0% |

The top asset and the ordering differ (QQQ-led in memo vs SPHQ-led in README).
That is too large for a convention/vintage shift and is consistent with two
DIFFERENT definitions: memo = risk-contribution share (weight x risk, so the
high-vol QQQ leads), README = exposure/weight share (so equal-weight-favored
SPHQ leads). This is probably NOT an error -- but both labels are ambiguous and
should be disambiguated so a reader does not treat them as the same series. Flag
for doc-owner confirmation; do not force a single set. CONFIDENCE MEDIUM (metric
definitions inferred from labels + orderings, not re-derived from source).

### C4. CPM extended/stress window -- INTENTIONALLY DIFFERENT WINDOW (label it)

| Series | memo "Extended (proxy-informed)" | README "Stress" / harness "ext" |
|---|---|---|
| Start | 1995-01-31 (proxy-informed, mixed starts) | 1999-03-10 (QQQ inception) |
| Sharpe | 1.2549 (memo 5.1) | 1.431 blend / CPM stress 1.2913 (README 66, 245; rebaseline) |
| MaxDD | -13.14% | -11.57% (CPM) |
| Convention | mooex | close-to-close |

These are genuinely different windows (1995 proxy vs 1999 live-ETF) AND different
conventions. They are NOT a contradiction to be collapsed; they answer different
questions. The fix is labeling, not renumbering (see section (e)). Note README's
"Stress" line 66/245 numbers are the PROD/CPM blend, not the CPM sleeve alone, so
ensure like-for-like before any comparison.

### C5. Turnover / fully-safe -- CONSISTENT (no action)

memo 5.4 (lines 197-198): clean 2.582 one-way/yr, 13.4% fully-safe; extended
~2.58, 10.1%. README does not quote sleeve turnover in a conflicting cell. No
mismatch found.

### C6. PROD / FORWARD_SHARPE_GUIDANCE -- not a CPM mismatch (already aligned)

build_dashboard FORWARD_SHARPE_GUIDANCE (line ~56) = PROD 1.4944 / 17.02% /
-10.46% / 1.6261, matching README PROD headline (close-to-close). This is PROD,
not CPM, and is internally consistent across README+dashboard. Listed only so the
fixer does not mistake it for a CPM cell. (It is still close-to-close; if the
project migrates to mooex per (b)-PREFERRED, PROD would also move.)

## (d) Per-doc OLD -> NEW replacement map (to canonical mooex)

Apply ONLY if the project adopts mooex as the canonical published convention
(recommended). If the project instead chooses label-only (section (b)-MINIMUM),
skip the value swaps in this section and apply section (e) labels only.

### cpm_memo.md -- NO value change (already canonical mooex)

memo already matches the enforced anchor. No CPM stat edits needed. Optional
clarity-only edit: add the convention label "mooex T+1 exact" to the 5.1 headline
window label so a cross-reader knows why it differs from the dashboard. No numeric
OLD->NEW.

### README.md -- swap CPM rows close-to-close -> mooex

Window label "clean live-ETF window 2008-05-30 -> 2026-05-22" stays valid; add
"(mooex T+1 exact)" to the convention note. Display precision mirrors existing
README cells.

| Location | Cell | OLD (close-to-close) | NEW (canonical mooex) |
|---|---|---|---|
| Sleeve table, line 44 | CPM Raw Sharpe / Excess / CAGR / Vol / MaxDD / Calmar | 1.291 / 1.162 / 13.55% / 10.27% / -11.57% / 1.17 | 1.256 / 1.126 / 13.13% / 10.28% / -13.03% / 1.01 |
| Clean-window anchors, line 53 | CPM Sharpe / CAGR / Vol / MaxDD / Calmar / Martin | 1.2912 / 13.55% / 10.27% / -11.57% / 1.1711 / 4.5711 | 1.2557 / 13.13% / 10.28% / -13.03% / 1.0076 / 4.2571 |
| Clean-window anchors, line 54 | CPM-BULL 60/40 row | 1.2912 / 12.93% / 9.81% / -10.70% / 1.2089 / 4.6761 | RECOMPUTE under mooex first (BULL engine); do not blind-swap |
| Concentration, line 56 | per-asset shares | SPHQ 23.1% ... | leave as-is but RELABEL "exposure/weight share"; do NOT replace with memo's risk-contribution shares (different metric, see C3) |

CAVEAT: if README keeps BULL/NDX/PROD on close-to-close, swapping only the CPM
row to mooex makes the sleeve table mixed-convention. Either also migrate
BULL/NDX/PROD (preferred, needs their own recompute) or add a per-row convention
note. Do not ship a half-migrated table unlabeled.

### build_dashboard.py -- swap hardcoded CPM cells close-to-close -> mooex

| Location | Cell | OLD (close-to-close) | NEW (canonical mooex) |
|---|---|---|---|
| sleeve_rows ~2317-2319 "CPM clean window" | sharpe/cagr/vol/maxdd/calmar/martin | 1.2912 / 0.1355 / 0.1027 / -0.1157 / 1.1711 / 4.5711 | 1.2557 / 0.1313 / 0.1028 / -0.1303 / 1.0076 / 4.2571 |
| sleeve_rows ~2313-2315 + cpm_bull_60_40_clean_anchor ~2398-2407 "CPM-BULL 60/40" | sharpe/cagr/vol/maxdd/calmar/martin | 1.2912 / 0.1293 / 0.0981 / -0.1070 / 1.2089 / 4.6761 | RECOMPUTE under mooex first (BULL engine); do not blind-swap |

BEHAVIORAL CAVEAT: the dashboard's LIVE (non-hardcoded) CPM row is computed at
render via `perf_metrics(art.cpm, ...)` where `art.cpm = run_cpm_backtest(...)`
(close-to-close). Editing only the hardcoded strings will make the hardcoded
"CPM clean window" row (mooex) disagree with the live-rendered "CPM" row
(close-to-close) in the SAME table. For true dashboard consistency the
`build_artifacts` CPM computation must be switched to the mooex engine, not just
the hardcoded cells. This is the strongest argument for the (b)-PREFERRED full
migration. Flag to fixer/oracle.

## (e) Where different windows/conventions are intentional + how to label

1. Convention (the core fix). Every published CPM stat should carry an explicit
   execution-convention tag. Recommended canonical tag: "mooex T+1 exact". If any
   doc must retain a close-to-close number, tag it "close-to-close T+1 approx" in
   the same table so the two never appear as one unlabeled "CPM" value. The same
   metric name (e.g. "CPM clean Sharpe") must resolve to ONE number across memo,
   README, and dashboard once the convention is fixed.

2. Window (intentionally plural, keep both, label each):
   - "Clean live-ETF window 2008-05-30 -> 2026-05-22" = canonical headline.
   - memo "Extended (proxy-informed)" from 1995-01-31 and README/harness "Stress"
     from 1999-03-10 are DIFFERENT, deliberate robustness windows. Keep both but
     label start dates and proxy/live status inline every time
     (e.g. "Extended (proxy-informed, from 1995-01-31)" vs "Stress (live-ETF,
     from 1999-03-10)"). Never print an unlabeled "Extended Sharpe" because the
     two docs mean different things by it.

3. Concentration (different metric, keep both, disambiguate labels): memo's
   "risky contribution share" (risk-weighted) and README's "share of risky sleeve
   exposure" (weight-weighted) are different measures. Rename to unambiguous
   labels ("risk-contribution share" vs "exposure/weight share") rather than
   trying to make the numbers match.

## Caveats / confidence

- CONFIDENCE HIGH on the root cause: both doc numbers reproduced to 4+ decimals
  from the same frozen panel; the only varied input is the execution convention
  (mooex vs close-to-close). See `research/cpm_crossdoc_reconcile_recompute.py`.
- CONFIDENCE HIGH on the canonical numbers: they are the enforced
  `cpm_harness.ANCHOR` and reproduce through `verify_anchor` (frozen data).
- CONFIDENCE MEDIUM on the concentration metric-definition diagnosis (C3):
  inferred from labels + orderings, not re-derived from each source script.
- NOT recomputed this pass: BULL/NDX/PROD under mooex (needed if the project
  adopts (b)-PREFERRED full migration), and the CPM-BULL 60/40 mooex row. Flagged
  rather than guessed.
- PIT/data caveat: all numbers use the frozen in-repo panel pinned to
  EVAL_END = 2026-05-22 (`load_panel(live=False)`). A live `python
  build_dashboard.py` defaults to live=True / end=today and will print a slightly
  different (later-window) number; that is a separate behavior the prior
  rebaseline already flagged, not part of this convention gap.
- Out of scope as instructed: memo/README/dashboard/prod NOT edited; no commit.

## Reproduction

    .venv/bin/python research/cpm_crossdoc_reconcile_recompute.py

Outputs both the mooex anchor (verify_anchor) and the close-to-close
run_cpm_backtest CPM metrics over the clean window from frozen data.

## Next handoff

- oracle: decide scope -- full mooex migration of README/dashboard sleeve table +
  PROD blend (preferred, internally consistent) vs label-only retention of
  close-to-close (cheaper, requires explicit convention tags everywhere).
- fixer: apply the chosen path (section (d) value swaps + section (e) labels);
  if full migration, first recompute BULL/NDX/PROD/CPM-BULL under mooex and switch
  `build_artifacts` CPM computation to the mooex engine so the live-rendered row
  matches the hardcoded row.
- analyst (follow-up, if full migration chosen): recompute BULL, NDX, PROD
  60/20/20, and CPM-BULL 60/40 under mooex for a complete canonical set.
