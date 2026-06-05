# CPM Memo CI / Bootstrap Regeneration -- Findings (current prod CPM)

Analyst artifact. Read-only re production and re the memo. No production files,
no `cpm_memo.md`, `README`, `build_dashboard.py`, `cpm_live.py` edited. No commit.

Purpose: the factorial ladder and point metrics in `cpm_memo.md` were already
rebaselined to current prod CPM (clean Sharpe 1.255673: equal-weight risky
block, TIP-only canary, min-var 3-of-4 selection at n_pos=4). The bootstrap /
confidence-interval tables were NOT. This regenerates every stale CPM-own
CI/bootstrap table for current prod CPM, with an OLD->NEW replacement map for the
fixer.

- Regen script: `research/cpm_memo_ci_regen.py`
- Regen data:   `research/cpm_memo_ci_regen.json`
- Run:          `.venv/bin/python research/cpm_memo_ci_regen.py`


## (d) Bootstrap parameters used (confirming match to memo)

| Parameter | Value | Source / confirmation |
|---|---|---|
| Method | stationary block bootstrap (circular wrap) | memo 5.3 line 181/190: "stationary block bootstrap" |
| B (iterations) | 2000 | memo 5.3 stated B=2000 |
| Block length | 21 trading days | memo 5.3 stated block=21 |
| Seed | 42 | memo 5.3 stated seed=42 |
| Window | clean 2008-05-30 .. 2026-05-22 | memo 12.3; n=4524 daily obs |
| Convention | mooex (T+1 MOO exact), 10 bps/side, both-252 | memo 0/4; harness anchor |
| CPM series | `cpm_live.compute_target_weights` via `research/cpm_harness.py` | anchor verified 1.255673 (Sharpe/MaxDD/Calmar within 5e-4) |
| Resampling helper | `research/cpm_bootstrap_multimetric.py` (`rng.integers(0,n)` + `%n`) | canonical, byte-identical to `cpm_weighting_corr.paired_block_bootstrap` |

Confirmation: the regen reuses the memo's explicitly stated 5.3 convention
(B=2000, block=21, seed=42) for BOTH the single-series 5.3 CI and the paired
5.5 dSharpe CIs, so all regenerated CIs are methodologically consistent with the
rest of the memo. CPM clean anchor verified through `cpm_harness.verify_anchor`
(Sharpe 1.2556732727, n=4524).

Methodology note / flag (5.5): the OLD 5.5 CI table was produced by
`research/cpm_benchmarks_proper.py`, whose `paired_block_bootstrap` uses
seed=12345 and NON-wrapping block starts (`arange(0, n-block+1)` + `rng.choice`).
The regen instead uses the canonical `cpm_bootstrap_multimetric` (seed=42,
circular wrap), which is what the memo's stated convention describes. This is an
intentional consistency upgrade, not a silent drift -- the regenerated 5.5 CIs
now match the same bootstrap convention the memo declares in 5.3. Benchmark
SERIES construction (AAA / 60-40 / Naive 12m / Buy-hold inv-vol) is reused
unchanged from `cpm_benchmarks_proper.py`; only the CPM leg was swapped to
current prod.


## (a) Inventory of stale CI / bootstrap / significance content in cpm_memo.md

CPM-own (MUST regenerate):

| # | Memo location | What it currently shows | Staleness |
|---|---|---|---|
| 1 | 5.3, lines 179-190 | Single-series clean Sharpe bootstrap CI: point 1.2557, 2.5% 0.7866, 50% 1.1964, 97.5% 1.5969 | POINT already current (1.2557) but the 2.5/50/97.5 quantiles are from the OLD anchor (1.191 split-window run; source `cpm_headline_numbers_findings.json -> bootstrap_clean_sharpe`). Median 1.1964 < point 1.2557 is the tell. |
| 2 | 5.5, lines 213-220 | Paired dSharpe CIs (CPM minus benchmark): AAA +0.22 [-0.113,+0.589] Yes; 60/40 +0.37 [-0.093,+0.791] Yes; Naive 12m +0.52 [+0.166,+0.889] No; Buy-hold +0.51 [+0.090,+0.895] No | Built on OLD CPM (Sharpe 1.1658, inverse-vol) via `cpm_benchmarks_proper.json -> diff_ci` (seed 12345, non-wrap). dSharpe points = 1.1658 - bench. |

CPM-own (FLAGGED -- partially stale, NOT fully regenerated here; see flags):

| # | Memo location | What it currently shows | Staleness / why flagged |
|---|---|---|---|
| 3 | 8.2 DSR appendix, lines 449-470 | SR_hat 0.07910 (ann 1.2557), n 4524, skew -0.3682, excess kurtosis 4.0204, V_trials 2.094e-5; SR0/DSR/z table by N | SR_hat and n already CURRENT. skew/kurtosis are STALE (built on old 1.191 anchor; current CPM series moments are skew -0.4298, excess kurtosis 5.5254). V_trials grid and the SR0/DSR/z table also predate current prod. DSR is selection-deflation, not block bootstrap; regenerating the z-table needs the DSR DoF / V_trials machinery -- out of bootstrap-CI scope. Flagged with corrected moments below. |
| 4 | 9 intro bullet (line 483) + 9.2 (lines 507-515) | "vol-window standardization to both-252 is statistically free in paired bootstrap comparisons ... differences include zero"; 9.2 table both-252 1.2557 / split 1.1910 / both-504 1.2039; "Paired bootstrap (both-252 minus alternatives) includes zero for Sharpe, Calmar, Martin" | both-252 row is current (1.2557). Split-window row (1.1910 / -12.67% / 1.0615) is byte-identical to the OLD `rank252/wt504` prod spec in `cpm_volwindow_standardize_findings.json` -- i.e. the split / both-504 rows and the "includes zero" claim were computed on a non-current CPM spec. Regenerating requires running current CPM under three distinct vol-window configs (separate rank-vol and covariance lookbacks), which is a separate harness task. Flagged, not guessed. |

Benchmark / peer tables that are independent of CPM and were already left UNCHANGED
by the prior rebaseline (do NOT touch):

- 5.5 first per-series table (lines ~203-211): benchmark Sharpe/CAGR/MaxDD/
  Calmar/Martin for AAA / 60-40 / Naive / Buy-hold. These match
  `cpm_benchmarks_proper.json` and are CPM-independent. The CPM row in that table
  was already updated to 1.26. No CI; leave as is.
- 5.6 common-window tables, 5.9 HAA head-to-head and ladder: point metrics only,
  already handled by the factorial regen (`cpm_factorial_regen_findings.md`).
  Not bootstrap CIs.


## (b) Regenerated values for current prod CPM

### Table 1 -- 5.3 single-series clean Sharpe bootstrap CI (current prod CPM)

Stationary block bootstrap, B=2000, block=21 trading days, seed=42, clean window
(n=4524).

| Statistic | Value |
|---|---:|
| point | 1.2557 |
| 2.5% | 0.8633 |
| 50% | 1.2573 |
| 97.5% | 1.6689 |

(boot mean 1.2614.) Note the regenerated median (1.2573) now sits essentially on
the point (1.2557), which is the expected behavior for a correctly-anchored
single-series bootstrap -- the old median (1.1964) being below the point was the
diagnostic that the quantiles were stale.

### Table 2 -- 5.5 paired dSharpe CI CPM(current) minus each benchmark

Paired block bootstrap, B=2000, block=21, seed=42, clean window (n_common=4524
for all four comparators). CPM clean Sharpe 1.2557 vs unchanged benchmark series.

| Comparator | dSharpe | 95% CI | Includes zero? |
|---|---:|---|---|
| AAA-style available-panel benchmark | +0.31 | [-0.066, +0.682] | Yes |
| 60/40 | +0.46 | [-0.019, +0.895] | Yes |
| Naive 12m | +0.61 | [+0.230, +0.987] | No |
| Buy-hold vol-parity | +0.60 | [+0.178, +0.991] | No |

Full-precision points: AAA +0.3122, 60/40 +0.4611, Naive +0.6064, Buy-hold
+0.5952. P(dSharpe > 0): AAA 0.941, 60/40 0.970, Naive 0.9995, Buy-hold 0.998.

Classification UNCHANGED from the old table: AAA-style and 60/40 still include
zero; Naive 12m and Buy-hold vol-parity still exclude zero. So the memo's
interpretive paragraphs after the 5.5 table (lines ~222-224) and the executive-
summary "BENCHMARK INTERPRETATION" line (line ~26) remain valid as written and
need no edit. Only the point estimates and CI bounds move (all shift up by the
~0.09 Sharpe gap between old 1.1658 and current 1.2557; 60/40's lower bound moves
from -0.093 to -0.019 but still includes zero).

### Flag -- 8.2 DSR corrected series moments (current prod CPM)

Provided for the fixer; full DSR z-table NOT regenerated (needs DSR DoF /
V_trials machinery, separate task).

| Input | Memo (stale) | Current prod CPM |
|---|---:|---:|
| Observed SR_hat (per-day) | 0.07910 (ann 1.2557) | 0.07910 (ann 1.2557) -- already current |
| n (daily obs) | 4524 | 4524 -- already current |
| skew | -0.3682 | -0.4298 |
| excess kurtosis | 4.0204 | 5.5254 |
| V_trials (grid SR variance, per-day) | 2.094e-5 | NOT regenerated (DSR grid; flag) |
| SR0/DSR/z table by N | old (anchor 1.191) | NOT regenerated (flag) |

Directional note (not a substitute for a real DSR rerun): more-negative skew and
higher excess kurtosis slightly inflate the non-normality adjustment in the
DSR/PSR z, nudging z marginally lower, but with z already ~3.8-4.2 and DSR
~1.0000 the qualitative DSR conclusion (decisively significant after deflation)
is very unlikely to flip. Recommend a dedicated DSR regen pass to refresh
V_trials, SR0, DSR, and z on the current series.


## (c) OLD -> NEW replacement map for cpm_memo.md (for the fixer)

CPM-scoped only. Apply exactly; do not touch BULL / NDX / blend content.

### 5.3 table (lines 185-188)

| Line | OLD | NEW |
|---|---|---|
| 186 | `| 2.5% | 0.7866 |` | `| 2.5% | 0.8633 |` |
| 187 | `| 50% | 1.1964 |` | `| 50% | 1.2573 |` |
| 188 | `| 97.5% | 1.5969 |` | `| 97.5% | 1.6689 |` |

Line 185 (`| point | 1.2557 |`) is already current -- leave unchanged. Lines 181
and 190 (method statements) already state B=2000/block=21/seed=42 -- leave
unchanged.

### 5.5 table (lines 217-220)

| Line | OLD | NEW |
|---|---|---|
| 217 | `| AAA-style available-panel benchmark | +0.22 | [-0.113, +0.589] | Yes |` | `| AAA-style available-panel benchmark | +0.31 | [-0.066, +0.682] | Yes |` |
| 218 | `| 60/40 | +0.37 | [-0.093, +0.791] | Yes |` | `| 60/40 | +0.46 | [-0.019, +0.895] | Yes |` |
| 219 | `| Naive 12m | +0.52 | [+0.166, +0.889] | No |` | `| Naive 12m | +0.61 | [+0.230, +0.987] | No |` |
| 220 | `| Buy-hold vol-parity | +0.51 | [+0.090, +0.895] | No |` | `| Buy-hold vol-parity | +0.60 | [+0.178, +0.991] | No |` |

Line 213 header ("...paired block bootstrap, 95% CI") -- leave as is. The post-
table read (lines ~222-224) and exec-summary benchmark line (~26) need no change
(classifications unchanged).

### 8.2 (lines 457-459) -- FLAG, partial replacement only

| Line | OLD | NEW |
|---|---|---|
| 457 | `| skew | -0.3682 |` | `| skew | -0.4298 |` |
| 458 | `| excess kurtosis | 4.0204 |` | `| excess kurtosis | 5.5254 |` |

Line 459 (`V_trials ... 2.094e-5`) and the SR0/DSR/z table (lines 467-474) plus
the monthly-frame z band line: DO NOT hand-edit. These require a DSR rerun on the
current series. Flag to a follow-up DSR regen task before changing.

### 9 intro bullet (line 483) + 9.2 (lines 511-515) -- FLAG, do NOT guess

The split-window (1.1910) and both-504 (1.2039) rows and the "includes zero"
paired-bootstrap claim were computed on a non-current CPM spec. Regenerating
needs current CPM run under three vol-window configurations. Out of scope for
this CI regen; recommend a dedicated vol-window-standardization rerun on current
prod before editing. Until then, treat 9.2's non-both-252 rows and the
includes-zero statement as unverified for current prod.


## Caveats and confidence

- Confidence HIGH for Tables 1 and 2 (5.3, 5.5): CPM leg anchored to prod
  (1.2556732727, n=4524, anchor asserted via `cpm_harness.verify_anchor`);
  benchmark series reused unchanged from the memo's own 5.5 source; bootstrap
  uses the canonical helper with the memo's stated B/block/seed.
- Window and end-date: clean 2008-05-30 .. 2026-05-22 (n=4524 daily obs). All CIs
  are in-sample on this single clean window.
- PIT / cached-data caveat: signals use month-end `close.loc[:sig_d]` only;
  vol/cov windows end at sig_d. Execution uses cached yfinance opens
  (`exec_lag_moo_validation_2026_05_30.load_open_close` plus `_macro_cache` OHLC
  for the AAA-only tickers). Numbers are reproducible against the frozen panel /
  open cache as of this run; a data refresh could move the last digits.
- 5.5 methodology change is intentional and documented (canonical seed=42 circular
  bootstrap vs the old seed=12345 non-wrapping helper) -- it makes 5.5 consistent
  with the memo's declared 5.3 convention. If the fixer instead wants byte-for-
  byte continuity with the OLD 5.5 helper, rerun `cpm_benchmarks_proper.py` with
  the CPM leg swapped to `compute_target_weights`; expect CIs within a few
  thousandths of Table 2.
- 8.2 (skew/kurt provided; z-table flagged) and 9.2 (flagged) are NOT fully
  regenerated -- flagged rather than guessed, per discipline. Both need separate,
  non-block-bootstrap reruns (DSR machinery; 3-config vol-window harness).

## Next handoff

- fixer: apply the OLD->NEW replacement map for 5.3 (lines 186-188) and 5.5
  (lines 217-220), and the partial 8.2 skew/kurt swap (lines 457-458).
- analyst (follow-up, separate task): regenerate the 8.2 DSR z-table and the 9.2
  vol-window paired-bootstrap claim on current prod CPM before editing those.
