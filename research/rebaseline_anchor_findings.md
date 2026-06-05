# Rebaseline anchor findings: authoritative PROD 60/20/20 + sleeve numbers

Analyst note. Point-estimates only (no bootstrap/WF, per mandate). Research
artifact only; no prod/doc files edited, no commit. cpm_memo.md is out of scope
and was not touched.

## TL;DR

The three disagreeing anchors are NOT a window / end-date / data-vintage
problem. They are three different STRATEGY CODE VINTAGES. `cpm_live.py` was
re-anchored across three commits; `README.md` and `build_dashboard.py` text were
never updated to match. Reproduced each anchor exactly from its source commit:

| Anchor (as written) | PROD Sharpe / CAGR / MaxDD / Calmar | Source commit (strategy vintage) | Worktree repro |
|---|---|---|---|
| README headline | 1.370 / 16.64% / -12.16% / 1.37 | b568013 (2026-05-30) top-4 inverse-vol, HYG-OR-TIP canary | 1.3825 / 16.86% / -12.26% / 1.3746 |
| build_dashboard FORWARD_SHARPE_GUIDANCE | 1.4155 / 16.51% / -12.26% / 1.3467 | 49fb9cd (2026-05-31) same CPM, BULL switched to TIP-only canary | 1.4145 / 16.51% / -12.26% / 1.3461 (EXACT) |
| prior "cached" repro (flagged do-not-trust) | 1.495 / 17.02% / -10.46% | HEAD 24c1207 (2026-06-02) equal-weight risky + min-var 3-of-4 + TIP-only CPM canary | 1.4944 / 17.02% / -10.46% / 1.6261 |

The "cached 1.495" that was flagged "do not trust" is in fact the CURRENT
canonical HEAD output. The cache flag was a misdiagnosis: frozen vs fresh-fetched
data differ by < 0.001 Sharpe (see below). 1.495 is the authoritative number.

The dashboard anchor reproduces to the 3rd decimal from commit 49fb9cd. The
README headline is one strategy generation older still (its CPM-solo anchor
1.1910 traces to an even earlier memo snapshot; the b568013 inverse-vol family
reproduces ~1.38, the same superseded design).

## Code-vs-doc drift (the actual root cause)

Current HEAD `cpm_live.py` CPM sleeve != README spec:

| Aspect | README.md spec (stale) | HEAD code (canonical) |
|---|---|---|
| CPM canary | HYG OR TIP (`mom_13612U > 0`) | TIP-only (`CANARY_ASSETS = ["TIP"]`) |
| Risky weighting | inverse-vol across all surviving positives, top-K=4 | equal-weight; n_pos=4 -> min-var 3-of-4 subset (equal-weight var objective) |
| BULL canary | (README alpha row implies HYG-era) | TIP-only -> BULL is now IDENTICAL to benchmark B3 (HAA-Simple SPY): beta 1.000, corr 1.000 |

The strategy spec block, universe list and method-lineage prose in README still
describe the inverse-vol / HYG-OR-TIP design and must be reconciled by the doc
owner (fixer), not just the metric cells.

## Authoritative numbers (HEAD 24c1207, canonical path)

- Code path: `build_dashboard.build_artifacts()` (dashboard single source of truth).
- Data: frozen in-repo panel, `load_panel(live=False)` -> pinned `EVAL_END = 2026-05-22`.
- Clean window: 2008-05-30 -> 2026-05-22 (17.98y). Stress window: 1999-03-10 -> 2026-05-22 (27.20y).
- Data end-date used: 2026-05-22 (panel last = 2026-05-22 frozen; NDX parquet last 2026-05-28; live fetch reaches 2026-06-01 but is not the canonical clean-window end).
- Reproduction scripts: `research/rebaseline_repro.py` (+ `.json`), `research/rebaseline_extra.py`.

### 1. PROD blend + sleeves (clean window, frozen, post-cost)

| Strategy | Raw Sharpe | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|---:|
| PROD 60/20/20 | 1.4944 | 1.3728 | 17.02% | 10.93% | -10.46% | 1.6261 | 6.7132 |
| CPM | 1.2912 | 1.1617 | 13.55% | 10.27% | -11.57% | 1.1711 | 4.5711 |
| BULL | 0.9836 | 0.8722 | 11.67% | 11.98% | -20.28% | 0.5758 | 2.4973 |
| NDX | 1.2793 | 1.2228 | 31.43% | 23.56% | -31.39% | 1.0012 | 4.2308 |
| CPM-BULL 60/40 (two-sleeve, no NDX) | 1.2912 | 1.1556 | 12.93% | 9.81% | -10.70% | 1.2089 | 4.6761 |

### 2. Headline peer benchmarks (clean window, frozen) -- reproduce UNCHANGED

| Strategy | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| BB4 (best lit blend) | 1.1944 | 1.0609 | 12.03% | 9.94% | -14.55% | 0.8271 |
| BB1 (simplest lit 60/40) | 1.1222 | 0.9851 | 10.90% | 9.65% | -14.80% | 0.7361 |
| SPY buy-hold | 0.6603 | 0.5912 | 11.73% | 19.82% | -50.70% | 0.2313 |
| QQQ buy-hold | 0.8163 | 0.7547 | 16.94% | 22.30% | -49.37% | 0.3432 |

These match README to displayed precision -> the literature-benchmark machinery
is strategy-independent and did NOT move. Only the PROD/sleeve rows change.

### 3. Stress window (1999-03-10 -> 2026-05-22, frozen)

| Strategy | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|---:|
| PROD 60/20/20 | 1.4308 | 1.2060 | 14.90% | 10.06% | -10.46% | 1.4240 | 5.8319 |
| CPM | 1.2913 | 1.0629 | 13.15% | 9.96% | -11.57% | 1.1368 | 4.3945 |
| BULL | 0.9691 | 0.7602 | 10.72% | 11.15% | -20.28% | 0.5287 | 2.5481 |
| NDX | 1.1314 | 1.0148 | 22.90% | 19.99% | -31.39% | 0.7296 | 3.5201 |

### 4. CPM concentration (clean, share of risky-sleeve exposure)

NEW: SPHQ 23.1%, GLD 18.1%, QQQ 13.4%, TLT 12.7%, EFA 12.1%, DBC 9.0%, VNQ 6.8%, EEM 4.9%.
(OLD README: SPHQ 20.9%, QQQ 16.9%, GLD 15.0%, EFA 11.7%, TLT 10.5%, VNQ 9.8%, EEM 8.1%, DBC 7.2%.)
Shift is driven by equal-weight + min-var 3-of-4 selection replacing inverse-vol top-4.

### 5. Alpha / beta / corr (clean, OLS daily)

| Strategy | Benchmark | Alpha %/yr | Beta | Corr |
|---|---|---:|---:|---:|
| PROD 60/20/20 | BB4 | +5.27 | 0.932 | 0.848 |
| PROD 60/20/20 | BB1 | +5.92 | 0.962 | 0.849 |
| CPM | B2 AAA+TIP | +4.96 | 0.813 | 0.838 |
| BULL | B3 HAA-Simple SPY | +0.03 | 1.000 | 1.000 |
| NDX | QQQ buy-hold | +24.16 | 0.329 | 0.311 |

CAUTION: BULL vs B3 is now degenerate (alpha ~0, beta/corr = 1.000) because the
TIP-only BULL gate makes BULL mathematically identical to B3. The README "BULL |
B3 | +4.48 | 0.589 | 0.668" row is no longer meaningful and should be reframed,
not just renumbered.

### 6. Window / end-date / data-vintage sensitivity (all small)

| Change | PROD Sharpe | Delta |
|---|---:|---:|
| Canonical: frozen, clean end 2026-05-22 | 1.4944 | -- |
| Live fetch (fresh yfinance), clean end 2026-05-22 | 1.4951 | +0.0007 |
| Live fetch, end = panel last 2026-06-01 | 1.5061 | +0.012 |

Frozen vs fresh = negligible. End-date extension to today = +0.012. Neither
explains the 1.370 / 1.4155 / 1.495 spread; strategy code does.

NOTE for fixer: `build_dashboard.main()` defaults to `end = today` with
`live=True`, so a plain `python build_dashboard.py` reports ~1.506 (clean window
to today), not the pinned-clean 1.4944. To match the README clean window exactly,
run `python build_dashboard.py --end 2026-05-22`, or pin EVAL_END. The hardcoded
guidance text should quote the pinned-clean number (1.4944).

## OLD -> NEW mapping: README.md

Window label "2008-05-30 -> 2026-05-22 (18.0y)" stays valid. Display precision
mirrors existing README cells.

### Headline performance table (~line 33)

| Cell | OLD | NEW |
|---|---|---|
| PROD Raw Sharpe | 1.370 | 1.494 |
| PROD Excess Sharpe | 1.257 | 1.373 |
| PROD CAGR | 16.64% | 17.02% |
| PROD Vol | 11.78% | 10.93% |
| PROD MaxDD | -12.16% | -10.46% |
| PROD Calmar | 1.37 | 1.63 |
| BB4 row | 1.194 / 1.061 / 12.03% / 9.94% / -14.55% / 0.83 | UNCHANGED |
| BB1 row | 1.122 / 0.985 / 10.90% / 9.65% / -14.80% / 0.74 | UNCHANGED |
| SPY buy-hold row | 0.660 / 0.591 / 11.73% / 19.82% / -50.70% / 0.23 | UNCHANGED |
| QQQ buy-hold row | 0.816 / 0.755 / 16.94% / 22.30% / -49.37% / 0.34 | UNCHANGED |

### Sleeve table (~line 41)

| Cell | OLD | NEW |
|---|---|---|
| CPM | 1.191 / 1.072 / 13.44% / 11.16% / -12.67% / 1.06 | 1.291 / 1.162 / 13.55% / 10.27% / -11.57% / 1.17 |
| BULL | 1.081 / 0.955 / 11.44% / 10.57% / -13.35% / 0.86 | 0.984 / 0.872 / 11.67% / 11.98% / -20.28% / 0.58 |
| NDX | 1.186 / 1.132 / 30.01% / 24.77% / -35.92% / 0.84 | 1.279 / 1.223 / 31.43% / 23.56% / -31.39% / 1.00 |
| PROD 60/20/20 | 1.370 / 1.257 / 16.64% / 11.78% / -12.16% / 1.37 | 1.494 / 1.373 / 17.02% / 10.93% / -10.46% / 1.63 |

### Clean-window anchors (CPM-focused) table (~line 50)

| Cell | OLD | NEW |
|---|---|---|
| CPM (Sharpe/CAGR/Vol/MaxDD/Calmar/Martin) | 1.1910 / 13.44% / 11.16% / -12.67% / 1.0615 / 3.9646 | 1.2912 / 13.55% / 10.27% / -11.57% / 1.1711 / 4.5711 |
| CPM-BULL 60/40 (two-sleeve, no NDX) | 1.2485 / 12.74% / 10.05% / -10.68% / 1.1928 / 4.354 | 1.2912 / 12.93% / 9.81% / -10.70% / 1.2089 / 4.6761 |

### CPM concentration line (~line 55)

OLD: SPHQ 20.9%, QQQ 16.9%, GLD 15.0%, EFA 11.7%, TLT 10.5%, VNQ 9.8%, EEM 8.1%, DBC 7.2%.
NEW: SPHQ 23.1%, GLD 18.1%, QQQ 13.4%, TLT 12.7%, EFA 12.1%, DBC 9.0%, VNQ 6.8%, EEM 4.9%.

### Raw-momentum checkpoints table (~line 61)

| Cell | OLD | NEW |
|---|---|---|
| Clean: NDX Sharpe/CAGR/MaxDD | 1.186 / 30.01% / -35.92% | 1.279 / 31.43% / -31.39% |
| Clean: Blend Sharpe/CAGR/MaxDD | 1.370 / 16.64% / -12.16% | 1.494 / 17.02% / -10.46% |
| Stress: NDX Sharpe/CAGR/MaxDD | 1.014 / 21.48% / -35.92% | 1.131 / 22.90% / -31.39% |
| Stress: Blend Sharpe/CAGR/MaxDD | 1.298 / 14.73% / -12.63% | 1.431 / 14.90% / -10.46% |

### Alpha decomposition table (~line 67)

| Cell | OLD | NEW |
|---|---|---|
| CPM vs B2 | +4.75 / 0.834 / 0.791 | +4.96 / 0.813 / 0.838 |
| BULL vs B3 | +4.48 / 0.589 / 0.668 | +0.03 / 1.000 / 1.000 (DEGENERATE -- reframe, BULL == B3 now) |
| PROD vs BB4 | +4.85 / 0.947 / 0.800 | +5.27 / 0.932 / 0.848 |
| PROD vs BB1 | +6.01 / 0.933 / 0.764 | +5.92 / 0.962 / 0.849 |
| NDX vs QQQ buy-hold | +22.09 / 0.400 / 0.360 | +24.16 / 0.329 / 0.311 |
| prose "+4.85 vs BB4, +6.01 vs BB1" | as is | +5.27 vs BB4, +5.92 vs BB1 |
| prose "vs SPY +13.12%/yr, vs QQQ +11.73%/yr" | as is | NOT recomputed (PROD-vs-SPY/QQQ buy-hold alpha not run this pass; refresh if kept) |

### Literature benchmarks table (~line 196)

| Cell | OLD | NEW |
|---|---|---|
| B1..B5, BB1, BB4 rows | as is | UNCHANGED (strategy-independent; BB4/BB1 reproduce exactly) |
| PROD 60/20/20 row | 1.370 / 16.64% / -12.16% | 1.494 / 17.02% / -10.46% |

### Robustness / caveats prose (~line 205+)

| Cell | OLD | NEW |
|---|---|---|
| Bootstrap CI table (Sharpe 1.370 row etc.) | as is | NOT recomputed (bootstrap excluded by mandate). STALE -- point row should read 1.494; full CI needs a bootstrap refresh job. |
| "Extended-window Sharpe point/CI: 1.298 [...]" | 1.298 point | stress point now 1.431; CI needs bootstrap refresh |
| p-win sections (vs BB4 / PP / SPY / QQQ) | as is | NOT recomputed (paired bootstrap excluded). Flag stale. |
| "realized backtest Sharpe is 1.370" caveat line | 1.370 | 1.494 |
| Strategy spec block / universe / lineage prose (HYG-OR-TIP, inverse-vol) | as is | RECONCILE to code: TIP-only canary, equal-weight + min-var 3-of-4 (doc-owner change, not a metric cell) |

## OLD -> NEW mapping: build_dashboard.py

Most dashboard metrics are computed live at render; only hardcoded text/anchors
need editing. NEW values are the pinned-clean (end 2026-05-22) canonical numbers.

| Location | Cell | OLD | NEW |
|---|---|---|---|
| FORWARD_SHARPE_GUIDANCE (~line 56-58) | Sharpe | 1.4155 | 1.4944 |
| same | CAGR | 16.51% | 17.02% |
| same | MaxDD | -12.26% | -10.46% |
| same | Calmar | 1.3467 | 1.6261 |
| sleeve_rows hardcode (~line 2313-2315) "CPM-BULL 60/40" | sharpe/cagr/vol/maxdd/calmar/martin | 1.2777 / 0.1255 / 0.1005 / -0.1068 / 1.1746 / 4.3538 | 1.2912 / 0.1293 / 0.0981 / -0.1070 / 1.2089 / 4.6761 |
| sleeve_rows hardcode (~line 2317-2319) "CPM clean window" | sharpe/cagr/vol/maxdd/calmar/martin | 1.1910 / 0.1344 / 0.1116 / -0.1267 / 1.0615 / 3.9646 | 1.2912 / 0.1355 / 0.1027 / -0.1157 / 1.1711 / 4.5711 |
| cpm_bull_60_40_clean_anchor (~line 2398-2407) | sharpe/cagr/vol/maxdd/calmar/martin | 1.2777 / 0.1255 / 0.1005 / -0.1068 / 1.1746 / 4.3538 | 1.2912 / 0.1293 / 0.0981 / -0.1070 / 1.2089 / 4.6761 |
| text line ~2521 "clean window: 2008-05-30 -> 2026-05-22" | window label | as is | UNCHANGED |

Behavioral note (not a cell): `main()` runs `live=True, end=today`. Default
output drifts vs the pinned-clean hardcodes. Fixer should either pin EVAL_END for
the headline panel or pass `--end 2026-05-22` when regenerating the guidance.

## Caveats / confidence

- Confidence HIGH on the discrepancy diagnosis: each prior anchor reproduced from
  its source commit (dashboard 1.4155 -> 1.4145 EXACT; README family -> ~1.38;
  HEAD -> 1.4944). Same frozen data across all three (data files predate all
  commits), so the spread is purely strategy code.
- Confidence HIGH on the NEW HEAD numbers: frozen and live agree to < 0.001
  Sharpe; same canonical `build_artifacts` path the dashboard uses.
- README headline 1.370 vs b568013 repro 1.3825 leaves a ~0.012 residual: the
  exact headline (and CPM-solo 1.1910 anchor) traces to an earlier memo snapshot
  in the same inverse-vol/HYG-OR-TIP family; immaterial to the rebaseline since
  that design is superseded.
- Bootstrap CIs, p-win tables, and PROD-vs-SPY/QQQ buy-hold alpha were NOT
  recomputed (bootstrap/extra regressions excluded by mandate). Flagged stale.
- cpm_memo.md deliberately untouched (CPM-only, out of scope).
- No prod/doc files edited; no commit. Worktrees used for vintage repro were
  removed.

## Next handoff

- fixer: apply the OLD -> NEW cell edits to README.md and build_dashboard.py;
  reconcile README strategy spec/universe/lineage prose to the TIP-only +
  equal-weight/min-var-3-of-4 code; reframe the degenerate BULL-vs-B3 alpha row.
- analyst (follow-up, if wanted): refresh bootstrap CIs + p-win tables + buy-hold
  alpha to the new strategy (separate bootstrap job).
