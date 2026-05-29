# Safe Haven Expansion Backtest & Analysis Findings

Testing whether expanding the `best_safe` pool with a short-duration instrument improves defensive behavior, especially in 2022 stagflation.

## Performance Metrics Table

| Strategy / Variant | Clean Sharpe | Clean CAGR | Clean Vol | Clean MaxDD | 2022 Return | 2022 MaxDD | 2022 Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline [SHV, IEF] | 1.503 | 17.93% | 11.43% | -11.62% | 4.95% | -5.84% | 0.819 |
| Variant A [SHV, IEF, BIL] | 1.502 | 17.93% | 11.43% | -11.82% | 5.34% | -5.83% | 0.878 |
| Variant B [BIL, IEF] | 1.503 | 17.94% | 11.43% | -11.64% | 5.34% | -5.83% | 0.878 |
| Variant C (VTIP) [SHV, IEF, VTIP] | 1.484 | 17.75% | 11.48% | -11.81% | 3.24% | -6.47% | 0.487 |
| Variant C (STIP) [SHV, IEF, STIP] | 1.489 | 17.82% | 11.47% | -11.72% | 3.35% | -6.38% | 0.504 |
| Variant D (VTIP+BIL) [BIL, IEF, VTIP] | 1.484 | 17.75% | 11.48% | -11.85% | 3.37% | -6.42% | 0.504 |

## 2022 Safe Asset Selections Detail

Here are the actual safe assets selected by the 13612U momentum rule across different variants during 2022:

### Baseline [SHV, IEF]

| Signal Date | Safe Asset Choice | Regime State |
| --- | --- | --- |
| 2021-12-31 | **SHV** | RISK_ON |
| 2022-01-31 | **SHV** | DEFENSIVE |
| 2022-02-28 | **SHV** | RISK_ON |
| 2022-03-31 | **SHV** | DEFENSIVE |
| 2022-04-29 | **SHV** | DEFENSIVE |
| 2022-05-31 | **SHV** | DEFENSIVE |
| 2022-06-30 | **SHV** | DEFENSIVE |
| 2022-07-29 | **SHV** | DEFENSIVE |
| 2022-08-31 | **SHV** | DEFENSIVE |
| 2022-09-30 | **SHV** | DEFENSIVE |
| 2022-10-31 | **SHV** | DEFENSIVE |
| 2022-11-30 | **SHV** | DEFENSIVE |
| 2022-12-30 | **SHV** | DEFENSIVE |

### Variant A [SHV, IEF, BIL]

| Signal Date | Safe Asset Choice | Regime State |
| --- | --- | --- |
| 2021-12-31 | **BIL** | RISK_ON |
| 2022-01-31 | **BIL** | DEFENSIVE |
| 2022-02-28 | **BIL** | RISK_ON |
| 2022-03-31 | **BIL** | DEFENSIVE |
| 2022-04-29 | **BIL** | DEFENSIVE |
| 2022-05-31 | **BIL** | DEFENSIVE |
| 2022-06-30 | **BIL** | DEFENSIVE |
| 2022-07-29 | **BIL** | DEFENSIVE |
| 2022-08-31 | **BIL** | DEFENSIVE |
| 2022-09-30 | **BIL** | DEFENSIVE |
| 2022-10-31 | **BIL** | DEFENSIVE |
| 2022-11-30 | **BIL** | DEFENSIVE |
| 2022-12-30 | **BIL** | DEFENSIVE |

### Variant B [BIL, IEF]

| Signal Date | Safe Asset Choice | Regime State |
| --- | --- | --- |
| 2021-12-31 | **BIL** | RISK_ON |
| 2022-01-31 | **BIL** | DEFENSIVE |
| 2022-02-28 | **BIL** | RISK_ON |
| 2022-03-31 | **BIL** | DEFENSIVE |
| 2022-04-29 | **BIL** | DEFENSIVE |
| 2022-05-31 | **BIL** | DEFENSIVE |
| 2022-06-30 | **BIL** | DEFENSIVE |
| 2022-07-29 | **BIL** | DEFENSIVE |
| 2022-08-31 | **BIL** | DEFENSIVE |
| 2022-09-30 | **BIL** | DEFENSIVE |
| 2022-10-31 | **BIL** | DEFENSIVE |
| 2022-11-30 | **BIL** | DEFENSIVE |
| 2022-12-30 | **BIL** | DEFENSIVE |

### Variant C (VTIP) [SHV, IEF, VTIP]

| Signal Date | Safe Asset Choice | Regime State |
| --- | --- | --- |
| 2021-12-31 | **VTIP** | RISK_ON |
| 2022-01-31 | **VTIP** | DEFENSIVE |
| 2022-02-28 | **VTIP** | RISK_ON |
| 2022-03-31 | **VTIP** | DEFENSIVE |
| 2022-04-29 | **VTIP** | DEFENSIVE |
| 2022-05-31 | **VTIP** | DEFENSIVE |
| 2022-06-30 | **SHV** | DEFENSIVE |
| 2022-07-29 | **SHV** | DEFENSIVE |
| 2022-08-31 | **SHV** | DEFENSIVE |
| 2022-09-30 | **SHV** | DEFENSIVE |
| 2022-10-31 | **SHV** | DEFENSIVE |
| 2022-11-30 | **SHV** | DEFENSIVE |
| 2022-12-30 | **SHV** | DEFENSIVE |

### Variant C (STIP) [SHV, IEF, STIP]

| Signal Date | Safe Asset Choice | Regime State |
| --- | --- | --- |
| 2021-12-31 | **STIP** | RISK_ON |
| 2022-01-31 | **STIP** | DEFENSIVE |
| 2022-02-28 | **STIP** | RISK_ON |
| 2022-03-31 | **STIP** | DEFENSIVE |
| 2022-04-29 | **STIP** | DEFENSIVE |
| 2022-05-31 | **STIP** | DEFENSIVE |
| 2022-06-30 | **SHV** | DEFENSIVE |
| 2022-07-29 | **SHV** | DEFENSIVE |
| 2022-08-31 | **SHV** | DEFENSIVE |
| 2022-09-30 | **SHV** | DEFENSIVE |
| 2022-10-31 | **SHV** | DEFENSIVE |
| 2022-11-30 | **SHV** | DEFENSIVE |
| 2022-12-30 | **SHV** | DEFENSIVE |

### Variant D (VTIP+BIL) [BIL, IEF, VTIP]

| Signal Date | Safe Asset Choice | Regime State |
| --- | --- | --- |
| 2021-12-31 | **VTIP** | RISK_ON |
| 2022-01-31 | **VTIP** | DEFENSIVE |
| 2022-02-28 | **VTIP** | RISK_ON |
| 2022-03-31 | **VTIP** | DEFENSIVE |
| 2022-04-29 | **VTIP** | DEFENSIVE |
| 2022-05-31 | **VTIP** | DEFENSIVE |
| 2022-06-30 | **BIL** | DEFENSIVE |
| 2022-07-29 | **BIL** | DEFENSIVE |
| 2022-08-31 | **BIL** | DEFENSIVE |
| 2022-09-30 | **BIL** | DEFENSIVE |
| 2022-10-31 | **BIL** | DEFENSIVE |
| 2022-11-30 | **BIL** | DEFENSIVE |
| 2022-12-30 | **BIL** | DEFENSIVE |

## Analysis and Discussion

### 1. Baseline Performance
The current production `SAFE_POOL` of `[SHV, IEF]` provides a very solid defense. During the clean window (2008-05-30 to 2026-05-22), it achieves a blend Sharpe of **1.503**, CAGR of **17.93%**, and MaxDD of **-11.62%**.
Specifically in 2022, the baseline achieved a positive return of **+4.95%** with a MaxDD of only **-5.84%**.

### 2. Variant Performance Analysis
- **Variant A [SHV, IEF, BIL]**: Adding BIL (1-3mo T-bills) to the existing pool results in a slightly higher 2022 return of **+5.34%** (vs +4.95% baseline) and slightly higher 2022 Sharpe of **0.878** (vs 0.819 baseline). However, its overall Clean Sharpe is **1.502** (slightly lower than baseline's 1.503), and its overall MaxDD degrades slightly to **-11.82%** (vs -11.62% baseline) due to minor changes in selections over other historical market cycles.

- **Variant B [BIL, IEF]**: Replacing SHV with BIL entirely results in a 2022 return of **+5.34%** and a 2022 Sharpe of **0.878**. Its overall Clean Sharpe is **1.503** (identical to baseline) and its overall MaxDD is **-11.64%** (virtually identical to baseline's -11.62%). This shows that replacing SHV with BIL is a completely viable lateral swap, but provides no material overall performance benefit over the entire 18-year period.

- **Variant C (VTIP / STIP)**: Adding short-TIPS (VTIP or STIP) to the defensive pool results in significantly **worse** performance. VTIP drags the overall Clean Sharpe down to **1.484** and 2022 return down to **+3.24%** (with a worse 2022 MaxDD of **-6.47%**). Similarly, STIP drags the overall Clean Sharpe to **1.489** and 2022 return to **+3.35%**.

- **Variant D [BIL, IEF, VTIP]**: Combining BIL and VTIP results in an overall Clean Sharpe of **1.484** and 2022 return of **+3.37%**, failing to outperform the simple cash/bond baseline.

### 3. Why did VTIP/STIP underperform in 2022?
TIPS (inflation-protected securities) are designed to hedge against CPI inflation. However, 2022 was characterized by **historically aggressive interest rate hikes** by the Federal Reserve to combat inflation. This caused real yields to rise dramatically from negative levels to deeply positive levels. Since VTIP/STIP still carry some duration risk (average duration ~2.5 years), the aggressive spike in bond yields caused their prices to decline significantly (VTIP total return in 2022 was about **-3.9%**). Meanwhile, ultra-short T-bills/cash (SHV with duration ~0.3y and BIL with duration ~0.1y) had almost no duration risk and rapidly captured rising risk-free rates, yielding positive returns in 2022.

### 4. Recommendation
**Keep-as-is** (`[SHV, IEF]`) or optionally **replace SHV with BIL** (`[BIL, IEF]`).

The current `[SHV, IEF]` pool is highly adequate because:
1. **Automatic Rotation Works**: The 13612U momentum score successfully rotates the defensive sleeve to SHV (short-duration cash) when IEF (intermediate-duration treasuries) suffers from duration risk in rising-rate environments. In 2022, the baseline rotated exclusively to SHV from January through November, completely avoiding IEF's -15% selloff and delivering a positive **+4.95%** overall return in 2022.
2. **VTIP/STIP add unwanted correlation and yield risk**: TIPS are highly sensitive to real interest rates and failed to defend in 2022's rate-hike regime. Adding them degrades strategy robustness.
3. **BIL is a lateral swap**: While replacing SHV with BIL provides a marginal +0.39% boost in 2022, it does not materially alter the long-term risk-adjusted return (1.503 vs 1.503 Sharpe). Thus, the current production implementation is highly robust and requires no change.
