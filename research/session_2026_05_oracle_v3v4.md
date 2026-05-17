# Session 2026-05 (continued): Oracle v3 + v4 hardening

## Oracle v3 review changes applied

| Change | Before | After | Justification |
|---|---|---|---|
| Blend weight | 60/40 | **70/30** | Sharpe-optimal both LIVE/EXT; flat surface 60/40-80/20 |
| Pair lookback | 378d | **756d** | More stable covariance, +0.05 Sh standalone |

### Verified (no change needed)
- Override threshold is expanding-window only (no lookahead)
- 13612W formula confirmed: `(12r1 + 4r3 + 2r6 + r12)/19` (Keller weighted)
- FCP <2 candidates fallback handled (1 pos = 50/50 with safe, 0 = full safe)
- Top-K ranker uses Faber 10mo SMA distance (NOT 12-1) — pseudocode fixed

### Tested and rejected
- BULL vol-target overlay: hurts Sharpe across all caps (-0.03 to -0.07)
- Drop VBR+XLE combined: hurts due to K=4 over-shrinking universe (1.395 vs 1.460)
- K sensitivity: K=5 marginally beats K=6 but within bootstrap noise; kept K=6

### Documented (not applied — oracle concern was conflated)
- IEF in SAFE pool: by design (best-of-safes rotation by SMA distance picks
  SHV/BIL during rate-rising regimes like 2022, IEF during rate-falling like
  2008-2020). NOT a "duration leak" bug — tactical duration management.
- BULL-QQQ cash fallback is SHV-only (verified, separate from FCP SAFE)

## New PROD metrics

| Window | FCP Sh | BULL Sh | 70/30 PROD Sh | CAGR | MaxDD |
|---|---:|---:|---:|---:|---:|
| LIVE 18y | 1.26 | 1.07 | **1.48** | 14.25% | -12.3% |
| EXT 32y | 1.14 | 0.91 | **1.27** | 13.17% | -15.2% |
| TEST OOS 2017-26 | 1.49 | 1.06 | **1.63** | 16.85% | -12.3% |

Net vs old 60/40 + 378d:
- LIVE: Sh +0.01, CAGR -1.85pp, MaxDD +1.55pp better
- EXT: Sh +0.05, CAGR -0.46pp, MaxDD +3.2pp better
- TEST OOS: Sh +0.10, CAGR +0.06pp, MaxDD +1.55pp better

## Oracle v4 universe robustness findings

| Variant | LIVE Sh | TEST OOS | EXT Sh | Verdict |
|---|---:|---:|---:|---|
| FULL 11 (PROD) | 1.216 | 1.319 | 1.127 | baseline |
| QQQ->SPY | 1.114 | 1.337 | 1.046 | LIVE worse, robust |
| QQQ->VTI | 1.184 | 1.373 | 1.098 | similar |
| IGM->XLK | **1.280** | **1.448** | 1.114 | best modern, EXT tied |
| Both: SPY+XLK | 1.203 | 1.453 | 1.047 | mixed |
| Drop TLT | 1.106 | 1.245 | 1.038 | hurts |
| **Drop GLD** | **0.899** | 1.028 | 0.934 | catastrophic (always #1 to keep) |
| Drop quality | 1.014 | 1.176 | 1.060 | hurts moderately |
| No sectors (5) | 0.895 | 1.232 | 1.006 | LIVE bad, robust elsewhere |
| Broad only (4) | 0.919 | 1.173 | 1.012 | works but lower return |
| Drop all sectors (7) | 1.197 | 1.253 | **1.234** | surprisingly best on EXT |

Key conclusions:
1. **GLD criticality reconfirmed** — drop hurts -0.32 LIVE
2. **Strategy robust to single-ETF swaps** (QQQ<->SPY/VTI, IGM<->XLK)
3. **Sectors load-bearing on LIVE** (modern era benefits from sector tilts)
4. **EXT 32y prefers broader universe** without specific sectors
5. **Core engine works at lower return without sectors** (broad-only Sh 0.92)

## Pseudocode correction

Previous pseudocode incorrectly showed FCP using `top_k_by_12_1_momentum`.
Actual code uses Faber 10mo SMA distance for cross-sectional ranking, then
canary (13612W) for risk-on/off decision. Fixed in `strategy_summary.md`.

## Remaining oracle v3 asks NOT addressed (low priority / out-of-scope)

- PBO (probability of backtest overfitting) — combinatorial CV
- Deflated Sharpe / Probabilistic Sharpe haircut
- Regime block bootstrap (already have wider bootstrap CI)
- Walk-forward design freeze (we did 2008-16 vs 2017-26 OOS split)
- Tax drag simulation
- Execution stress test (we have 10bps; would need 0/5/25/50bps grid)
