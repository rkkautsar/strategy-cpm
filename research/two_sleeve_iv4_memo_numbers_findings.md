# Two-Sleeve CPM + BULL memo numbers -- regenerated under IV4

Role: analyst (hypothesis-driven, read-only re production; no production files changed; no commit). Throwaway harness `research/two_sleeve_iv4_memo_numbers.py`. This file supplies the FRESH number set to rewrite `research/two_sleeve_cpm_bull_findings.md` (whose existing pair / min-var-3-era blend numbers are STALE). Memo prose/rewrite is a separate fixer step; this file is numbers only.

**Production CPM spec = IV4** (`cpm_live.compute_target_weights`): single-stage cross-asset momentum -> vol-Faber ranker (faber_score/rv_252d) -> positive-trend screen -> top-4 -> INVERSE-VOL WEIGHT ALL surviving positives (NO min-var sub-selection) -> strict-4 partial-safe -> HYG-OR-TIP canary -> timed safe.

**Conventions (memo metric set):** CAGR, Vol, raw Sharpe (rf=0), Excess Sharpe vs SHV, MaxDD, Calmar (=CAGR/|MaxDD|), 2022 calendar return. CPM & BULL on T+1 MOO exact (`mooex`, real auto_adjust opens), post-cost 10 bps/side, BULL slow vol gate rv_60d<rv_252d. Windows: clean 2008-05-30..2026-05-22 (18y); stress/ext 1999-03-10..2026-05-22 (27y).

**NDX leg caveat (PROD 60/20/20 only):** the NDX sleeve runs on the production path under T+1 MOO offset=1 close-to-close (T+1 MOO offset=1 (close-to-close; exact-open engine unsupported for per-stock NDX universe + delisting)). The exact-open (`mooex`) engine cannot run the per-stock PIT NDX universe with delisting haircuts, so the NDX 20% leg uses close-to-close T+1 MOO while the CPM 60% and BULL 20% legs use exact-open T+1 MOO. CPM and BULL legs are byte-identical between the two-sleeve and PROD rows; only the NDX leg carries this minor convention nuance.

## 0. Anchor gate

| Gate | Sharpe | MaxDD | Calmar | Martin | Expected | Match |
|---|---:|---:|---:|---:|---|---|
| CPM-solo IV4 (clean) | 1.1910 | -12.67% | 1.0615 | 3.9646 | 1.1910 / -12.67% / 1.0615 | CONFIRMED |
| 60/40 blend (clean) | 1.2485 | -10.68% | 1.1928 | 4.3538 | 1.2485 / -10.68% / 1.1928 / 4.354 | CONFIRMED |

Both anchors reproduce exactly; the rest of this file is trusted on that basis.

## 1. Two-sleeve blend performance (60/40 vs 50/50)

Memo metric conventions; clean (18y) + stress (27y); 2022 calendar return on the clean series. PROD 60/20/20 (3-sleeve, incl. live NDX) re-cited for reference.

| Portfolio / Split | Window | CAGR | Vol | Raw Sharpe | Excess Sharpe vs SHV | MaxDD | Calmar | 2022 Return |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **CPM/BULL 60/40** | Clean | 12.74% | 10.05% | 1.248 | 1.116 | -10.68% | 1.19 | **0.12%** |
| | Stress | 12.13% | 9.78% | 1.219 | 0.986 | -11.31% | 1.07 | |
| **CPM/BULL 50/50** | Clean | 12.55% | 9.95% | 1.243 | 1.109 | -11.12% | 1.13 | **0.27%** |
| | Stress | 11.71% | 9.66% | 1.194 | 0.958 | -11.12% | 1.05 | |
| *PROD 60/20/20* | Clean | 16.64% | 11.78% | 1.370 | 1.257 | -12.16% | 1.37 | **0.12%** |
| | Stress | 14.73% | 11.06% | 1.298 | 1.091 | -12.63% | 1.17 | |

## 2. Weight-insensitivity sweep (80/20 -> 30/70)

| CPM Weight | BULL Weight | Clean Sharpe | Clean MaxDD | Stress Sharpe | Stress MaxDD |
| --- | --- | --- | --- | --- | --- |
| 80% | 20% | 1.233 | -10.09% | 1.235 | -13.63% |
| 70% | 30% | 1.245 | -10.25% | 1.232 | -12.47% |
| 60% | 40% | 1.248 | -10.68% | 1.219 | -11.31% |
| 50% | 50% | 1.243 | -11.12% | 1.194 | -11.12% |
| 40% | 60% | 1.227 | -11.56% | 1.157 | -11.56% |
| 30% | 70% | 1.202 | -12.01% | 1.109 | -12.01% |

- **Clean Sharpe band:** 0.046 (low 1.202 at 30/70, high 1.248 at 60/40).
- **Stress Sharpe band:** 0.126 (low 1.109 at 30/70, high 1.235 at 80/20).
- **Verdict on fit:** PEAKED -- the entire 80/20..30/70 sweep spans a max Sharpe range of 0.126. The split is not a fitted parameter.

## 3. Correlation & diversification

- **CPM-BULL correlation (clean):** 0.6760
- **CPM-BULL correlation (stress):** 0.6091

### Side-by-side vs PROD 60/20/20 (clean window)

| Metric | CPM Standalone | BULL Standalone | NDX Standalone | 2-Sleeve 60/40 | 2-Sleeve 50/50 | 3-Sleeve PROD |
| --- | --- | --- | --- | --- | --- | --- |
| **CAGR** | 13.44% | 11.44% | 30.01% | 12.74% | 12.55% | 16.64% |
| **Vol** | 11.16% | 10.57% | 24.77% | 10.05% | 9.95% | 11.78% |
| **Raw Sharpe** | 1.191 | 1.081 | 1.186 | 1.248 | 1.243 | 1.370 |
| **Excess Sharpe** | 1.072 | 0.955 | 1.132 | 1.116 | 1.109 | 1.257 |
| **MaxDD** | -12.67% | -13.35% | -35.92% | -10.68% | -11.12% | -12.16% |
| **Calmar** | 1.06 | 0.86 | 0.84 | 1.19 | 1.13 | 1.37 |
| **2022 Return** | -0.50% | 0.94% | 0.94% | 0.12% | 0.27% | 0.12% |

### 60/40 two-sleeve vs PROD 60/20/20 -- what is given up / gained (clean)

Given up by dropping NDX (two-sleeve 60/40 minus PROD):
- **CAGR:** give up 3.89pp (16.64% PROD -> 12.74% 60/40).
- **Raw Sharpe:** give up 0.121 (1.370 -> 1.248).
- **Excess Sharpe:** give up 0.141 (1.257 -> 1.116).

Gained by dropping NDX:
- **Vol:** lower by 1.73pp (11.78% PROD -> 10.05% 60/40).
- **MaxDD:** shallower by 1.48pp (-12.16% PROD -> -10.68% 60/40).
- **Calmar:** -0.17 (1.37 PROD -> 1.19 60/40).
- **Operational:** zero individual stocks (broad-index ETFs only) vs monthly NDX-constituent rebalancing.

## Caveats

- CPM & BULL legs: production IV4 `cpm_live.compute_target_weights` + production BULL slow gate, run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side post-cost; anchor-gated to the FINAL IV4 set.
- NDX leg (PROD 60/20/20 + NDX standalone only): production NDX sleeve under T+1 MOO offset=1 close-to-close (exact-open engine unsupported for per-stock PIT universe + delisting). The NDX 20% leg therefore carries a minor convention difference vs the exact-open CPM/BULL legs; CPM and BULL contributions are identical across the two-sleeve and PROD rows.
- Stress/ext window (1999-03-10..) is partially proxy-backed pre-2006-2008 for the CPM trend universe; clean 18y has full real-open coverage and is the decisive lens. NDX constituent data does not extend across the full stress window, so PROD stress-row NDX leg is near-cash pre-data.
- Martin = CAGR / UlcerIndex, UlcerIndex = sqrt(mean(dd_pct^2)); from production perf_metrics. (Memo tables report Calmar; Martin shown only in the anchor gate.)
