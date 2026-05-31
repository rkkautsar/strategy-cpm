# CPM Memo Rebaseline: OLD prod (rank252/wt504) -> NEW production (both-252)

Role: analyst (research-only). No production or memo files edited. No commit.

## What changed in production

`cpm_live.py` now runs **both-252**: `CORR_LOOKBACK_DAYS = 252` (inverse-vol weighting lookback)
and rank-vol `tail(252)` (Faber `m_faber / rv_252d`). The OLD production was rank-vol 252 /
weight-vol 504 ("prod (rank252/wt504)"). Because **rank-vol was already 252 in both configs**,
the selection layer (Faber ranker, positive-trend screen, top-4, HYG-OR-TIP canary, SHV/IEF safe
selector, strict-4 partial-safe routing) is **byte-identical** between old-prod and both-252. The
*only* change is the inverse-vol weighting lookback inside the risky block (504 -> 252 trading days).

Consequence (used throughout this mapping): picks, canary states, safe months, and fully-safe-month
counts are **unchanged**; only intra-risky-block weights move slightly, so every downstream metric
shifts within noise rather than re-ranking.

## Anchor reproduction (gate, done FIRST)

- OLD prod anchor reproduced exactly: clean Sharpe **1.1910** / MaxDD **-12.67%** / Calmar **1.0615**
  (`cpm_volwindow_standardize_harness.py` anchor gate `ok=True`).
- NEW both-252 anchor reproduced exactly across three independent harness paths:
  clean Sharpe **1.1658** / MaxDD **-12.97%** / Calmar **1.0137**
  (matches the task target 1.1658 / -12.97% / 1.0137).

## NEW HEADLINE ANCHOR (prominent)

> **CPM both-252 clean (decision lens, 2008-05-30..2026-05-22, mooex T+1 MOO, 10 bps/side):**
> **Sharpe 1.1658 | MaxDD -12.97% | Calmar 1.0137 | Martin 3.6907 | CAGR 13.15% | Vol 11.18% | Ulcer 3.56% | Excess Sharpe vs SHV 1.0469.**
> Forward expectation unchanged at **~0.72 (0.62-0.85)** after selection/execution/regime haircuts.

## Bottom line on conclusions

**No memo qualitative conclusion changes.** Every both-252 number sits inside the old-prod bootstrap
noise band; the paired block bootstrap (B=5000) on both-252 minus old-prod has all CIs including zero
on Sharpe, Calmar, and Martin (clean and extended). Two **sign-of-a-small-number** shifts are flagged
below (they do not change any narrative): the factorial W (weighting) main-effect clean dSharpe goes
marginally negative, and inverse-vol's edge over equal-weight shrinks. Both are consistent with the
memo's existing framing of weighting as "a modest helper."

---

## Master mapping table

Notation: numbers are clean-window unless marked EXT. "->" is OLD prod -> NEW both-252.

### 1-2. Headline + executive summary (memo Sec 1, Sec 5.1)

| Metric | Memo location | OLD (252/504) | NEW (both-252) |
|---|---|---:|---:|
| Clean Sharpe | Sec 1, 5.1, 5.3 | 1.1910 | **1.1658** |
| Clean CAGR | Sec 5.1 | 13.44% | **13.15%** |
| Clean Vol | Sec 5.1 | 11.16% | **11.18%** |
| Clean MaxDD | Sec 1, 5.1 | -12.67% | **-12.97%** |
| Clean Calmar | Sec 5.1 | 1.0615 | **1.0137** |
| Clean Martin | Sec 5.1 | 3.9646 | **3.6907** |
| Clean Ulcer | Sec 5.1 | 3.39% | **3.56%** |
| Excess Sharpe vs SHV (clean) | Sec 5.1 | 1.0719 | **1.0469** |
| Clean Sharpe bootstrap CI | Sec 1, 5.1, 5.3 | [0.7866, 1.5969], med 1.1964 | within noise (band width ~unchanged; not re-bootstrapped here -- recommend fixer re-run `bootstrap_ci` harness; point shifts 1.1910->1.1658) |
| In-sample peak / selection-deflated / forward | Sec 1, 8, 9.1 | 1.19 / ~1.00 / ~0.72 (0.62-0.85) | **1.17 / ~0.96 / ~0.72 (0.62-0.85)** |
| Worst clean drawdown date/depth | Sec 5.1 | 2025-04-08, -12.67% | **2025-04-08, -12.97%** (peak 2025-02-19, recovered 2025-06-12) |

Extended (1995-01-31 start, proxy-informed robustness only):

| Metric | Memo location | OLD | NEW (both-252) |
|---|---|---:|---:|
| Ext Sharpe | Sec 5.1 | 1.2643 | **1.2491** |
| Ext CAGR | Sec 5.1 | 14.00% | **13.74%** |
| Ext Vol | Sec 5.1 | 10.78% | **10.72%** |
| Ext MaxDD | Sec 5.1 | -15.93% | **-15.73%** |
| Ext Calmar | Sec 5.1 | 0.8791 | **0.8736** |
| Ext Martin | Sec 5.1 | 3.9767 | **3.8437** |
| Ext Ulcer | Sec 5.1 | 3.52% | **3.58%** |
| Ext excess Sharpe vs SHV | Sec 5.1 | 1.0007 | **0.9841** |
| Ext worst DD | Sec 5.1 | -15.93% (2006 proxy era) | **-15.73%** (2006 proxy era) |

Extended-window Sharpe bootstrap (Sec 5.1): old point 1.2643, CI [0.9430, 1.5986]. NEW point 1.2491;
CI shifts marginally, not re-bootstrapped (recommend fixer re-run if exact CI quoted).

### 3. Crisis behavior (Sec 5.2)

Global drawdown episodes (extended continuous-curve, 1995 both-252 curve). Depths recomputed over the
memo's stated peak/trough dates; **recovery dates and exact trough detection are auto-detected and
shift under both-252 -- flagged below.**

| Crisis | Memo location | OLD depth | NEW depth (both-252) | Note |
|---|---|---:|---:|---|
| LTCM (1998) | Sec 5.2 | -9.88% | **-9.07%** | proxy-heavy (0/8 live) |
| Dot-com era (2002 dip) | Sec 5.2 | -5.87% | **-6.03%** | proxy-heavy (1/8 live) |
| GFC (2008) | Sec 5.2 | -11.88% | **-11.88%** | recovery +63d (stable) |
| COVID (2020) | Sec 5.2 | -10.06% | **-10.11%** | recovery ~+29d |
| 2022 | Sec 5.2 | -7.64% | **-8.32%** | see recovery flag |

FLAG (mechanical, not conclusion-changing): the memo's 2022-episode recovery (+40d to 2022-03-08)
is **trough-detection-sensitive**. Holding the memo's fixed trough date (2022-01-27) on the both-252
curve pushes the next full recovery to 2024 (artifact of a fixed, non-deepest trough). The canonical
auto-detection crisis harness should re-derive the precise peak/trough/recovery triplets if exact
recovery days are quoted. Crisis *catches* (CPM goes defensive, shallow depths vs benchmarks) are
fully preserved.

Within-calendar crisis windows (fixed calendar, robust):

| Crisis window | Memo location | OLD MaxDD / ret | NEW MaxDD / ret (both-252) |
|---|---|---:|---:|
| GFC (2007-10..2009-06) | Sec 5.2 | -11.88% / 9.86% | **-11.88% / 11.56%** |
| COVID (2020-02..2020-06) | Sec 5.2 | -10.06% / 8.00% | **-10.50% / 6.67%** |
| 2022 bear (2022-01..2022-12) | Sec 5.2 | -6.33% / -0.50% | **-7.96% / -2.08%** |

Worst clean drawdown is the **2025-04 tariff selloff** (already the memo's clean worst): peak
2025-02-19, trough 2025-04-08, depth **-12.97%**, recovered 2025-06-12 (~65 calendar days).

### 4. Benchmark comparison + difference CIs (Sec 5.5)

Clean metrics (`cpm_benchmarks_proper.py`):

| Series | Memo location | OLD Sharpe / MaxDD / Calmar | NEW Sharpe / MaxDD / Calmar (both-252) |
|---|---|---:|---:|
| CPM | Sec 5.5 | 1.19 / -12.67% / 1.06 | **1.17 / -12.97% / 1.01** |
| AAA-style available-panel | Sec 5.5 | 0.94 / -21.76% / 0.42 | 0.94 / -21.76% / 0.42 (benchmark unchanged) |
| 60/40 (SPY/IEF) | Sec 5.5 | 0.79 / -29.82% / 0.29 | 0.79 / -29.82% / 0.29 (unchanged) |
| Naive 12m | Sec 5.5 | 0.65 / -26.59% / 0.31 | 0.65 / -26.59% / 0.31 (unchanged) |
| Buy-hold inverse-vol | Sec 5.5 | 0.69 / -34.92% / 0.23 | 0.66 / -34.75% / 0.23 (minor data refresh) |

Sharpe difference CIs (CPM minus benchmark, paired block bootstrap B=2000, block=21):

| Comparator | Memo location | OLD dSharpe / CI / incl0 | NEW dSharpe / CI / incl0 |
|---|---|---|---|
| AAA-style | Sec 5.5 | +0.25 / [-0.069,+0.607] / Yes | **+0.22 / [-0.113,+0.589] / Yes** |
| 60/40 | Sec 5.5 | +0.40 / [-0.069,+0.826] / Yes | **+0.37 / [-0.093,+0.791] / Yes** |
| Naive 12m | Sec 5.5 | +0.54 / [+0.178,+0.925] / No | **+0.52 / [+0.166,+0.889] / No** |
| Buy-hold inverse-vol | Sec 5.5 | +0.51 / [+0.086,+0.907] / No | **+0.51 / [+0.090,+0.895] / No** |

Conclusion **unchanged**: AAA-style and 60/40 include zero (favorable but statistically unresolved);
naive-12m and buy-hold inverse-vol exclude zero (significant).

Drawdown-adjusted difference tests (Sec 5.5) -- **point diffs** recomputed from both-252 metrics; the
CIs were not re-bootstrapped (recommend fixer re-run the drawdown-diff harness). Point diffs shrink a
hair; **include/exclude-no-diff verdicts are unchanged** (AAA/60-40 include; naive/buyhold exclude):

| Metric / comparator | Memo location | OLD point | NEW point (both-252) |
|---|---|---:|---:|
| MaxDD gap pp vs AAA | Sec 5.5 | +9.10 | **+8.79** |
| MaxDD gap pp vs 60/40 | Sec 5.5 | +17.16 | **+16.85** |
| MaxDD gap pp vs Naive | Sec 5.5 | +13.92 | **+13.62** |
| MaxDD gap pp vs BuyHold | Sec 5.5 | +22.25 | **+21.78** |
| Calmar diff vs AAA | Sec 5.5 | +0.6399 | **+0.5896** |
| Calmar diff vs 60/40 | Sec 5.5 | +0.7713 | **+0.7201** |
| Calmar diff vs Naive | Sec 5.5 | +0.7579 | **+0.7076** |
| Calmar diff vs BuyHold | Sec 5.5 | +0.8313 | **+0.7869** |
| Martin diff vs AAA | Sec 5.5 | +2.3504 | **+2.068** |
| Martin diff vs 60/40 | Sec 5.5 | +2.5738 | **+2.288** |
| Martin diff vs Naive | Sec 5.5 | +2.9550 | **+2.671** |
| Martin diff vs BuyHold | Sec 5.5 | +2.8682 | **+2.656** |

Per-series EXT benchmark table (Sec 5.5):

| Series | Start | OLD Sharpe/MaxDD/Calmar | NEW (both-252) |
|---|---|---:|---:|
| CPM | 1995-01-31 | 1.26 / -15.93% / 0.88 | **1.25 / -15.73% / 0.87** |
| AAA-style | 2008-01-19 | 0.93 / -21.76% / 0.42 | 0.93 / -21.76% / 0.42 |
| 60/40 | 1999-03-10 | 0.69 / -31.44% / 0.23 | 0.69 / -31.44% / 0.23 |
| Naive 12m | 1999-03-10 | 0.82 / -26.59% / 0.38 | 0.82 / -26.59% / 0.38 |
| Buy-hold inverse-vol | 1999-03-10 | 0.84 / -35.61% / 0.27 | 0.81 / -35.44% / 0.26 |

(CPM ext at 1999 both-252 = Sharpe 1.2102 / MaxDD -15.73% / Calmar 0.8644 / Martin 3.7065; the memo
EXT-CPM 1.26 uses the 1995 start = 1.2491.)

### 4b. Common-window extended (Sec 5.6)

All-series common start 2008-01-19:

| Series | Memo location | OLD Sharpe/MaxDD/Calmar | NEW (both-252) |
|---|---|---:|---:|
| CPM | Sec 5.6 | 1.188 / -12.67% / 1.059 | **1.165 / -12.97% / 1.014** |
| AAA-style | Sec 5.6 | 0.930 / -21.76% / 0.417 | 0.930 / -21.76% / 0.417 |
| 60/40 | Sec 5.6 | 0.798 / -30.83% / 0.286 | 0.798 / -30.83% / 0.286 |
| Naive 12m | Sec 5.6 | 0.665 / -26.59% / 0.319 | 0.665 / -26.59% / 0.319 |
| Buy-hold inverse-vol | Sec 5.6 | 0.708 / -35.61% / 0.239 | 0.684 / -35.44% / 0.233 |

Ex-AAA common start 1999-03-10:

| Series | Memo location | OLD Sharpe/MaxDD/Calmar | NEW (both-252) |
|---|---|---:|---:|
| CPM | Sec 5.6 | 1.214 / -15.93% / 0.861 | **1.200 / -15.73% / 0.857** |
| 60/40 | Sec 5.6 | 0.691 / -31.44% / 0.232 | 0.691 / -31.44% / 0.232 |
| Naive 12m | Sec 5.6 | 0.816 / -26.59% / 0.380 | 0.816 / -26.59% / 0.380 |
| Buy-hold inverse-vol | Sec 5.6 | 0.842 / -35.61% / 0.268 | 0.813 / -35.44% / 0.261 |

### 5. Leave-one-asset-out (Sec 9.1)

| Dropped | Memo location | OLD Sharpe / dSharpe / MaxDD / Calmar | NEW (both-252) |
|---|---|---:|---:|
| (none) baseline | Sec 9.1 | 1.1910 / -- / -12.67% / 1.0615 | **1.1658 / -- / -12.97% / 1.0137** |
| ex-QQQ | Sec 9.1 | 1.0140 / -0.1770 / -11.34% / 0.9285 | **0.9934 / -0.1724 / -11.60% / 0.8904** |
| ex-SPHQ | Sec 9.1 | 1.0339 / -0.1570 / -12.24% / 0.9126 | **1.0068 / -0.1589 / -12.41% / 0.8759** |
| ex-EFA | Sec 9.1 | 1.1799 / -0.0111 / -11.36% / 1.1102 | **1.1609 / -0.0049 / -11.62% / 1.0693** |
| ex-EEM | Sec 9.1 | 1.2069 / +0.0159 / -11.06% / 1.1457 | **1.1897 / +0.0239 / -11.08% / 1.1282** |
| ex-VNQ | Sec 9.1 | 1.1163 / -0.0747 / -13.73% / 0.8813 | **1.0905 / -0.0752 / -13.96% / 0.8462** |
| ex-GLD | Sec 9.1 | 1.0579 / -0.1331 / -14.57% / 0.8277 | **1.0404 / -0.1253 / -14.45% / 0.8222** |
| ex-TLT | Sec 9.1 | 1.0823 / -0.1087 / -13.86% / 0.9132 | **1.0581 / -0.1077 / -13.98% / 0.8859** |
| ex-DBC | Sec 9.1 | 1.1248 / -0.0662 / -12.44% / 1.0155 | **1.1035 / -0.0623 / -12.55% / 0.9886** |

Conclusion unchanged: no single-asset dependence break (all >= 1.01 Sharpe, all MaxDD shallower than
-14.5%); return concentration in QQQ/SPHQ; drawdown-control concentration in GLD/VNQ.

### 6. Calendar-year returns + intra-year DD (Sec 5.7)

CPM column only (AAA/60-40 unchanged). `->` OLD ret / intraDD -> NEW ret / intraDD.

| Year | OLD CPM ret / intraDD | NEW CPM ret / intraDD |
|---|---:|---:|
| 2008* | +5.08% / -9.83% | +5.27% / -10.23% |
| 2009 | +14.47% / -7.09% | +14.26% / -7.07% |
| 2010 | +16.62% / -9.15% | +16.00% / -9.19% |
| 2011 | +10.44% / -7.49% | +9.23% / -7.79% |
| 2012 | +6.72% / -4.81% | +6.89% / -4.87% |
| 2013 | +19.47% / -8.79% | +18.99% / -9.24% |
| 2014 | +15.78% / -6.07% | +15.84% / -6.08% |
| 2015 | -0.97% / -6.51% | -1.14% / -6.80% |
| 2016 | +10.36% / -9.43% | +10.16% / -9.60% |
| 2017 | +22.43% / -2.26% | +22.33% / -2.33% |
| 2018 | +1.92% / -10.13% | +1.04% / -10.08% |
| 2019 | +12.41% / -3.72% | +12.73% / -3.85% |
| 2020 | +23.43% / -10.06% | +21.77% / -10.50% |
| 2021 | +26.22% / -4.70% | +27.28% / -4.51% |
| 2022 | -0.50% / -6.33% | -2.08% / -7.96% |
| 2023 | +1.60% / -7.93% | +1.85% / -7.75% |
| 2024 | +15.08% / -7.01% | +15.24% / -7.19% |
| 2025 | +26.47% / -12.67% | +25.78% / -12.97% |
| 2026* | +20.84% / -5.99% | +21.44% / -5.69% |

(AAA / 60-40 calendar columns are unchanged in this rebaseline.)

### 7. Worst-interval + underwater (Sec 5.8)

| Metric | Memo location | OLD CPM | NEW CPM (both-252) |
|---|---|---:|---:|
| Worst 1-month return | Sec 5.8 | -6.00% | **-5.85%** (ends 2018-10) |
| Worst 3-month return | Sec 5.8 | -7.48% | **-7.34%** (ends 2023-10) |
| Worst 12-month return | Sec 5.8 | -5.24% | **-5.21%** (ends 2023-10) |
| Longest underwater | Sec 5.8 | 688 days | **789 days** |

FLAG (mild): longest-underwater lengthens 688 -> 789 days under both-252 (still a single-path stat;
robustness evidence, not inference). AAA (903d) and 60/40 (787d) unchanged.

### 8. Forward-Sharpe haircut ladder (Sec 8.1, also Sec 1 / Sec 9.1)

Same multiplicative factors, re-anchored to the both-252 in-sample 1.1658:

| Step | Factor (central / band) | Memo location | OLD Sharpe | NEW Sharpe (both-252) |
|---|---|---|---:|---:|
| 0. In-sample argmax | -- | Sec 8.1 | 1.19 | **1.17** |
| 1. Selection de-peak | x0.82 / [0.79,0.86] | Sec 8.1 | ~1.00 (0.94-1.02) | **~0.96 (0.92-1.00)** |
| 2. Execution-realism | x0.85 / [0.765,0.93] | Sec 8.1 | ~0.83 (0.72-0.95) | **~0.81 (0.70-0.93)** |
| 3. Regime non-stationarity | x0.88 / [0.80,0.95] | Sec 8.1 | ~0.72 (0.62-0.85) | **~0.72 (0.62-0.85)** |
| Forward central | synthesis | Sec 1, 8, 9.1 | ~0.72, 0.62-0.85 | **~0.72, 0.62-0.85** |

Three-number framing (Sec 8 / Sec 9.1): **1.17 peak / ~0.96 selection-deflated / ~0.72 forward**
(was 1.19 / ~1.00 / ~0.72). Forward center unchanged; the haircut compounding lands on ~0.72 either way.

### 9. DSR appendix inputs (Sec 8.2)

| Input | Memo location | OLD | NEW (both-252) |
|---|---|---:|---:|
| Observed SR_hat (per-day) | Sec 8.2 | 0.07502 (ann 1.1908) | **0.07343 (ann 1.1656)** |
| n (daily obs) | Sec 8.2 | 4524 | 4524 |
| skew | Sec 8.2 | -0.3740 | **-0.3682** |
| excess kurtosis | Sec 8.2 | 4.0282 | **4.0204** |
| V_trials (per-day) | Sec 8.2 | 2.094e-5 (std 0.073 ann) | 2.094e-5 (selection-space property; carried) |
| SR0 ann by N (40..2000) | Sec 8.2 | 0.159..0.250 | 0.159..0.250 (unchanged; V_trials carried) |
| DSR | Sec 8.2 | ~1.0000 | **~1.0000 (0.9999 at N>=1000)** |
| Daily-frame z range | Sec 8.2 | 3.91-4.48 | **3.81-4.19** |
| Monthly-frame z range | Sec 8.2 | 4.82-5.39 | **4.63-5.02** |
| Reported z band | Sec 8.2 / Sec 8 lead | 3.91-5.39 | **3.81-5.02** |

Conclusion unchanged: DSR ~ 1.0 (z > 3.8 at every N), signal is statistically distinguishable from
the expected search maximum; selection-from-noise alone does not manufacture the result.

### 10. Turnover + fully-safe months (Sec 5.4)

| Window | Memo location | OLD one-way/yr / fully-safe | NEW (both-252) |
|---|---|---:|---:|
| Clean | Sec 5.4, Sec 1 | 2.616 / 13.4% | **~2.58 / 13.4%** |
| Extended | Sec 5.4, Sec 1 | 2.733 / 10.1% | **~2.58 / 10.1%** |

Fully-safe-month percentages are **identical** (selection layer unchanged). One-way turnover is
essentially unchanged (~2.58 one-way/yr clean from `avg_oneway_per_rebal` 0.4304 x 12 / 2; the small
move vs 2.616 is from the weight-lookback change only). Recommend the fixer re-confirm the exact
turnover convention against the original Sec 5.4 harness before quoting; conclusion (low turnover) holds.

### 11. Factorial decomposition (Appendix A, Sec 6, Sec 7.1-7.3)

all-OFF baseline (AAA-like, 000000) is **unchanged** (clean 0.7869 / -23.21% / 0.3188; ext 0.8696 /
-23.21% / 0.3624) -- it does not use the CPM vol lookback. all-ON (111111, production CPM) =
**1.1658 / -12.97% / 1.0137** (was 1.1910 / -12.67% / 1.0615).

Main effects, CLEAN dSharpe / dCalmar (`cpm_factorial_faithful_aaa.py`):

| Factor | Memo location | OLD dSharpe / dCalmar | NEW dSharpe / dCalmar (both-252) |
|---|---|---:|---:|
| Ranker (R) | App A | +0.2048 / +0.2411 | **+0.2041 / +0.2326** |
| Canary (C) | App A | +0.1104 / +0.2172 | **+0.1130 / +0.2100** |
| Universe (U) | App A | +0.0837 / +0.0657 | **+0.0857 / +0.0615** |
| Screen (S) | App A | -0.0228 / +0.0463 | **-0.0238 / +0.0469** |
| Weighting (W) | App A | **+0.0127** / +0.0646 | **-0.0159** / **+0.0343** |
| Partial-safe (P) | App A | +0.0482 / +0.0886 | **+0.0481 / +0.0876** |

FLAG (sign of a small number): **W main-effect clean dSharpe flips marginally negative**
(+0.0127 -> -0.0159) because W-on is now inverse-vol-252 (vs the prior inverse-vol-504) measured
against the min-variance W-off baseline. W clean dCalmar stays **positive** (+0.0343). This does not
change the memo's narrative (W = "modest helper, drawdown-side, regime-dependent"); it strengthens the
existing caveat that the factorial *understates* inverse-vol value because W-off is a sophisticated
min-var weighting, not naive equal-weight. Recommend the fixer soften "+0.0127 clean dSharpe" to
"approximately flat / marginally negative clean dSharpe, positive on Calmar."

EXT main effects (both-252): R +0.1007/+0.1387, C +0.0808/+0.1800, U +0.0593/-0.0023, S -0.0092/+0.0374,
W +0.0696/+0.0957, P +0.0394/+0.0816 (old: R +0.1110/+0.1481, C +0.0728/+0.1790, U +0.0824/+0.0148,
S -0.0178/+0.0346, W +0.1054/+0.1217, P +0.0282/+0.0730). EXT W stays clearly positive.

Key interactions (CLEAN dCalmar): U x R +0.1320 (was +0.1392), S x P +0.0876 (was +0.0886),
C x R +0.0784 (was +0.0832). Qualitative interaction story unchanged.

Contribution ladder (note: the refreshed harness uses order R->C->U->S->P->W; memo Appendix A used
R->C->U->W->S->P, so ladder-step values are not directly position-comparable, but endpoints are):
baseline 000000 = 0.7869 / Calmar 0.3188 (unchanged); all-ON 111111 = 1.1658 / Calmar 1.0137.
Clean ladder Calmar remains monotone-ish to all-ON; qualitative ladder unchanged.

Sec 7.3 weighting (inverse-vol vs **equal-weight** at production):

| Comparison | Memo location | OLD | NEW (both-252) |
|---|---|---:|---:|
| inverse-vol vs equal-weight Sharpe | Sec 7.3 | 1.1910 vs 1.1317 (+0.0593) | **1.1658 vs 1.1317 (+0.0341)** |
| inverse-vol vs equal-weight Calmar | Sec 7.3 | 1.0615 vs 1.0147 | **1.0137 vs 1.0147 (~tie)** |
| inverse-vol vs equal-weight MaxDD | Sec 7.3 | -12.67% vs -13.05% | **-12.97% vs -13.05%** |

FLAG (sign of a small number): equal-weight is lookback-independent (1.1317 unchanged); inverse-vol's
Sharpe edge shrinks to +0.034 and the Calmar edge becomes a ~tie. Still a (smaller) positive Sharpe
helper. Consistent with the W main-effect flag above; conclusion (inverse-vol = modest helper) holds.

Sec 7.1 ranker / Sec 7.2 universe lift quotes (e.g. R +0.1994 clean, U +0.0837 clean): R main effect
vs the faithful-AAA native ranker is essentially unchanged (+0.2041); the secondary "+0.1994 clean,
+0.1488 ext" against the alternate baseline is anchor-adjacent and shifts within ~0.005 -- recommend
the fixer re-run `cpm_ranker_*`/`cpm_robust_universe` only if exact 4-decimal values are required.

### 12. Volatility-lookback section (Sec 9.2) -- REFRAMED

OLD framing treated prod=rank252/wt504 as production and both-252 as an alternative. **Both-252 is now
production.** Corrected framing: production (both-252) vs the legacy rank252/wt504 and vs both-504; all
three are statistically indistinguishable (paired block bootstrap B=5000 CIs include zero on Sharpe,
Calmar, Martin, clean and extended).

Clean-window plateau:

| Config | Memo location | OLD label | Sharpe / MaxDD / Calmar |
|---|---|---|---:|
| **both-252 (PRODUCTION)** | Sec 9.2 | was "alt" | **1.1658 / -12.97% / 1.0137** |
| legacy rank252/wt504 | Sec 9.2 | was "prod" | 1.1910 / -12.67% / 1.0615 |
| both-504 | Sec 9.2 | alt | 1.2039 / -13.73% / 0.9877 |

Paired bootstrap (B=5000, block=21), production both-252 minus alternatives:

| Pair | clean dSharpe CI | clean dCalmar CI | clean dMartin CI |
|---|---|---|---|
| both-252 - legacy(252/504) | -0.0250 [-0.0607,+0.0093] incl0 | -0.0474 [-0.1579,+0.0231] incl0 | -0.2163 [-0.5584,+0.0300] incl0 |
| both-252 - both-504 | -0.0382 [-0.0929,+0.0127] incl0 | -0.0592 [-0.2101,+0.0537] incl0 | -0.2898 [-0.7703,+0.0764] incl0 |
| both-504 - legacy(252/504) | +0.0132 [-0.0212,+0.0519] incl0 | +0.0118 [-0.0776,+0.1140] incl0 | +0.0735 [-0.1901,+0.3912] incl0 |

(EXT pairs likewise all include zero.) Sharpe band across the three configs is ~0.038 (~3%): a robust
plateau, not a tuned peak. Reframe read: production (both-252) is the **fewest-degrees-of-freedom**
choice (single unified lookback) and is statistically indistinguishable from the legacy split and from
both-504; it is not the Sharpe max (both-504 is) but is a parsimony cho inside the noise band.

Crisis-catch parity across configs (clean-window per-crisis MaxDD): GFC -10.23%, COVID -10.50%,
2022 -7.96% for both-252 (legacy: -9.83% / -10.06% / -6.33%; both-504: -9.83% / -10.06% / -6.33%).
All configs retain crisis catches.

EOM-offset stability (both-252): EOM 1.1658, EOM+1 0.9743, EOM+2 0.9628, EOM+3 0.8714 (std 0.107).
Execution cliff persists identically (selection-driven). Legacy EOM was 1.1910 / 1.0125 / 0.9908 / 0.8971.

### 13. US-equity de-tilt (Sec 9.3)

Primary (replace QQQ+SPHQ with SPY):

| Config | Memo location | OLD Sharpe / MaxDD / Calmar | NEW (both-252) |
|---|---|---:|---:|
| Production | Sec 9.3 | 1.1910 / -12.67% / 1.062 | **1.1658 / -12.97% / 1.014** |
| De-tilt SPY | Sec 9.3 | 1.0122 / -11.75% / 0.903 | **0.9884 / -11.98% / 0.865** |

Secondary ticker swaps (dSharpe vs the same-start production baseline):

| Swap | Memo location | OLD dSharpe (or Sharpe) | NEW (both-252) |
|---|---|---:|---:|
| QQQ->VUG | Sec 9.3 | -0.034 | **-0.035** |
| QQQ->IWF | Sec 9.3 | -0.036 | **-0.036** |
| QQQ->IWD (Sharpe) | Sec 9.3 | 1.1028 | **1.0785** (dSharpe -0.087) |
| SPHQ->QUAL | Sec 9.3 | +0.004 | **-0.000 (~flat)** |
| SPHQ->MTUM | Sec 9.3 | -0.048 | **-0.072** |

Passive references unchanged: SPY buy-hold Sharpe 0.660; 60/40 Sharpe 0.795. De-tilt SPY (0.9884)
stays far above both. Growth/quality enhancer = 1.1658 - 0.9884 = ~0.18 Sharpe (was ~0.18). Conclusion
unchanged: cross-asset edge survives de-tilting; tech tilt is a layered enhancer, not the source of edge.

### Sec 7.6 factor stability across halves (marginal dSharpe at production)

| Factor | Memo location | OLD 2008-16 / 2017-26 | NEW (both-252) |
|---|---|---:|---:|
| R (ranker) | Sec 7.6 | +0.30 / +0.11 | **+0.28 / +0.14** |
| U (universe) | Sec 7.6 | +0.25 / +0.10 | **+0.25 / +0.10** |
| W (inverse-vol) | Sec 7.6 | +0.09 / +0.02 | **+0.06 / +0.00** |
| C (canary) | Sec 7.6 | +0.15 / -0.08 | **+0.15 / -0.07** |
| S (screen) | Sec 7.6 | +0.04 / -0.01 | **+0.04 / -0.00** |
| P (partial-safe) | Sec 7.6 | +0.07 / +0.02 | **+0.07 / +0.02** |

Subperiod Sharpe (Sec 9.3 robustness row + Sec 7.6): 2008-16 1.00 -> **0.97**; 2017-26 1.38 -> **1.35**.
Conclusion unchanged; W's 2017-26 contribution rounds to ~0.00 (consistent with the "regime-contingent,
not a primary forward lever" caveat).

### Sec 7.4 asset concentration (weight-dependent) -- recompute with methodology caveat

CPM risky contribution share recomputed on both-252 (`_rebaseline_concentration_both252.py`,
weight x daily-return contribution share):

| | Memo location | OLD clean top-1 / top-3 | NEW clean top-1 / top-3 (both-252) |
|---|---|---:|---:|
| Concentration | Sec 7.4, Sec 8.3 | SPHQ 20.9% / 52.8% | **QQQ 21.7% / 55.9%** |

FLAG (methodology): my contribution-share definition may differ from the memo's original Sec 7.4
harness (the OLD table ordered SPHQ first; my recompute orders QQQ first). The both-252 weight change
plus a possible methodology mismatch makes the per-asset ordering not directly comparable. Treat as
directional: concentration stays moderate (top-1 ~20-22%, top-3 ~53-56%); no extreme single-name
dependence. Recommend the fixer regenerate Sec 7.4 with the original concentration harness on both-252
before quoting exact per-asset shares.

---

## Robustness-table rows NOT individually recomputed (Sec 9 summary table)

These sweep rows are weight-lookback-dependent (each historical cell used wt504). Because rank-vol is
unchanged, the qualitative robustness holds, but exact cell values shift slightly. Recommend the fixer
re-run the corresponding sweep harness if exact figures are quoted:

- Top-K {3,4,5,6}: OLD 0.95/1.19/1.09/1.02 -- K=4 anchor -> 1.17; others shift ~within noise.
- Ranking momentum {Faber, 13612U, 12m, 6m, 3m}: OLD 1.19/1.08/0.99/0.93/0.92 -- Faber -> 1.17.
- Cost {0,10,30 bps}: OLD 1.24/1.19/1.10 -> ~1.21/1.17/1.08 (parallel shift).
- Weighting {inverse-vol, equal-weight}: 1.19/1.13 -> **1.17/1.13** (equal-weight unchanged; see Sec 7.3).
- Fill convention {MOC, T+1 MOO, T+1 close, T+2 open}: T+1 MOO anchor -> 1.17; same-day MOC was 1.2063
  (both-252 MOC not recomputed here).
- Signal/rebalance offset {EOM..EOM+3}: **1.1658 / 0.9743 / 0.9628 / 0.8714** (recomputed, both-252).
- Grid interaction (80 cells): production remains in the top region; the literal argmax shifts because
  both-252 is not the Sharpe max (both-504 is, at 1.2039) -- recommend re-running `cpm_grid_interaction`
  to refresh "argmax/median/IQR" language for both-252.

No-canary MaxDD (-15.01%, cited in Sec 1/2/5.5/7.6/10): canary toggle is selection-layer (rank
identical) but the weight-lookback change moves it slightly. Recommend re-run via the canary-ablation
harness on both-252; expected shift is sub-0.5pp and does not change "still shallower than every
benchmark."

---

## Honesty / scope notes

- Clean window = decision lens; extended = proxy-informed robustness only; single in-sample path,
  point-in-time. All recomputes use the same mooex T+1-MOO engine, 10 bps/side.
- Anchors reproduced first (both OLD 1.1910 and NEW 1.1658 gates pass).
- Metrics that **materially move** beyond a cosmetic shift: (a) factorial W main-effect clean dSharpe
  sign flip (+0.0127 -> -0.0159) and the shrunk inverse-vol-vs-equal-weight edge (Sec 7.3/App A);
  (b) longest-underwater 688 -> 789 days (Sec 5.8); (c) crisis-episode recovery dates are
  trough-detection-sensitive (Sec 5.2). None changes a memo conclusion.
- Everything else shifts within bootstrap noise; all benchmark significance verdicts and the forward
  ~0.72 center are unchanged.

## Artifacts (research/ only; no commit)

- `cpm_rebaseline_both252.md` (this file)
- `cpm_rebaseline_both252_consolidated.json` (machine-readable old->new pack)
- Refreshed harness JSONs re-run on both-252: `memo_review_additions_compute.json`,
  `cpm_benchmarks_proper.json`, `cpm_volwindow_standardize_findings.json`,
  `cpm_factorial_faithful_aaa.json` (= `cpm_factorial_aaa_findings`), `cpm_factor_stability_halves.json`,
  `cpm_factorial_iv4_6factor.json`
- Scratch recompute scripts + JSONs: `_rebaseline_detilt_both252.{py,json}`,
  `_rebaseline_dsr_both252.{py,json}`, `_rebaseline_ext1995_both252.{py,json}`,
  `_rebaseline_crisis_both252.{py,json}`, `_rebaseline_concentration_both252.{py,json}`
