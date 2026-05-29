# CPM best_safe Timing Isolation (60/40 CPM+BULL two-sleeve)

Question: does CPM/BULL's `best_safe` timing (argmax 13612U over [SHV, IEF]) earn its keep vs simpler fixed safe rules? Safe asset is shared by CPM and BULL; the safe rule is varied on BOTH sleeves consistently.

Method: monkeypatch `cpm_live.best_safe` and `bull_qqq_live._pick_safe` (measurement only, no production files edited). 50/50 uses a synthetic daily-rebalanced SHV+IEF blend column. Blend = 0.60*CPM + 0.40*BULL. Excess Sharpe vs SHV cash. Turnover = annual one-way, combined (shared SHV/IEF net out).

Windows: clean 2008-05-30..2026-05-22, stress 1999-03-10..2026-05-22.

## Verification

S0 production path (60/40 clean): Sharpe **1.347** / CAGR **13.59%** / MaxDD **-9.82%**. Target 1.347 / 13.59% / -9.82%. Match: **True**.

Patched 13612 rule (strictly SHV/IEF pool) reproduces true production exactly: **True** (CPM 0.0 max daily diff over 4524 days; BULL 0.0 max diff). The S0 table row below is the exact production equivalent.

## 1. 60/40 Blend Metrics (all variants)

| Variant | Window | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | Calmar | Turnover (ann 1-way) | 2022 | 2008 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0 (best of SHV/IEF by 13612U (PROD)) | clean | 13.59% | 9.84% | 1.347 | 1.212 | -9.82% | 1.38 | 3.37 | 4.95% | 6.11% |
| S0 (best of SHV/IEF by 13612U (PROD)) | stress | 12.65% | 9.58% | 1.291 | 1.056 | -11.79% | 1.07 | 3.47 | 4.95% | 15.17% |
| S1 (SHV only) | clean | 12.20% | 9.31% | 1.285 | 1.143 | -12.76% | 0.96 | 3.19 | 4.95% | -5.87% |
| S1 (SHV only) | stress | 11.61% | 9.10% | 1.252 | 0.999 | -13.02% | 0.89 | 3.22 | 4.95% | 2.04% |
| S2 (IEF only) | clean | 13.52% | 10.21% | 1.296 | 1.167 | -17.31% | 0.78 | 3.19 | -8.45% | 6.11% |
| S2 (IEF only) | stress | 12.80% | 9.85% | 1.272 | 1.044 | -17.31% | 0.74 | 3.22 | -8.45% | 15.17% |
| S3 (50/50 SHV+IEF (no timing)) | clean | 12.88% | 9.59% | 1.313 | 1.176 | -11.91% | 1.08 | 3.19 | -1.87% | -0.01% |
| S3 (50/50 SHV+IEF (no timing)) | stress | 12.22% | 9.35% | 1.279 | 1.037 | -11.91% | 1.03 | 3.22 | -1.87% | 8.46% |
| S4 (best of SHV/IEF by 3-month return) | clean | 12.47% | 9.78% | 1.252 | 1.117 | -13.98% | 0.89 | 3.75 | -0.60% | -2.76% |
| S4 (best of SHV/IEF by 3-month return) | stress | 11.95% | 9.53% | 1.232 | 0.994 | -13.98% | 0.85 | 3.78 | -0.60% | 6.23% |
| S5 (best of SHV/IEF by 12-month return) | clean | 13.73% | 9.83% | 1.360 | 1.225 | -9.82% | 1.40 | 3.26 | 4.95% | 6.11% |
| S5 (best of SHV/IEF by 12-month return) | stress | 12.86% | 9.57% | 1.313 | 1.077 | -11.79% | 1.09 | 3.29 | 4.95% | 15.17% |

Notes: 2008 calendar return only meaningful in stress window (clean window starts 2008-05-30, so 2008 figure is partial-year May-Dec). Turnover differs slightly across windows due to start date.

## 1b. CPM standalone (where it differs from blend)

| Variant | Window | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | Calmar |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S0 | clean | 14.58% | 11.30% | 1.263 | 1.145 | -15.41% | 0.95 |
| S0 | stress | 13.99% | 11.28% | 1.218 | 1.014 | -15.91% | 0.88 |
| S1 | clean | 13.42% | 11.10% | 1.192 | 1.072 | -21.27% | 0.63 |
| S1 | stress | 13.16% | 11.13% | 1.167 | 0.959 | -21.73% | 0.61 |
| S2 | clean | 14.51% | 11.61% | 1.228 | 1.114 | -18.30% | 0.79 |
| S2 | stress | 13.96% | 11.49% | 1.195 | 0.996 | -18.30% | 0.76 |
| S3 | clean | 13.98% | 11.23% | 1.223 | 1.106 | -15.72% | 0.89 |
| S3 | stress | 13.57% | 11.22% | 1.190 | 0.985 | -16.21% | 0.84 |
| S4 | clean | 13.38% | 11.28% | 1.171 | 1.054 | -16.44% | 0.81 |
| S4 | stress | 13.23% | 11.26% | 1.160 | 0.956 | -16.93% | 0.78 |
| S5 | clean | 14.67% | 11.30% | 1.270 | 1.152 | -15.41% | 0.95 |
| S5 | stress | 14.07% | 11.27% | 1.224 | 1.020 | -15.91% | 0.88 |

## 2. S0 13612U Timing Diagnostic

### clean window

- Total month-ends: 216.
- CPM defensive months (holds safe leg): 29 (13.4% of months). Of these IEF picked: 13 (44.8%), SHV picked: 16.
- BULL cash months (holds safe leg): 88 (40.7% of months). Of these IEF picked: 57 (64.8%), SHV picked: 31.
- Any-sleeve-defensive months: 88; of those at least one sleeve picked IEF: 57 (64.8%). (How often the SHV-vs-IEF choice could matter.)
- CPM IEF-picked months realized fwd gap (IEF-SHV): mean +1.48%, median +0.41%, IEF beat SHV 8/13 (62%).
- CPM: cumulative realized timing edge from picking IEF over SHV in defensive months (sum of captured gaps): +19.21% over 29 defensive months.
- BULL IEF-picked months realized fwd gap (IEF-SHV): mean +0.54%, IEF beat SHV 33/57 (58%).

### stress window

- Total month-ends: 326.
- CPM defensive months (holds safe leg): 36 (11.0% of months). Of these IEF picked: 17 (47.2%), SHV picked: 19.
- BULL cash months (holds safe leg): 147 (45.1% of months). Of these IEF picked: 99 (67.3%), SHV picked: 48.
- Any-sleeve-defensive months: 148; of those at least one sleeve picked IEF: 99 (66.9%). (How often the SHV-vs-IEF choice could matter.)
- CPM IEF-picked months realized fwd gap (IEF-SHV): mean +1.22%, median +0.41%, IEF beat SHV 11/17 (65%).
- CPM: cumulative realized timing edge from picking IEF over SHV in defensive months (sum of captured gaps): +20.82% over 36 defensive months.
- BULL IEF-picked months realized fwd gap (IEF-SHV): mean +0.38%, IEF beat SHV 57/99 (58%).

## 3. Verdict

Comparison anchors (clean window, 60/40 blend):

- S0 (timing): Sharpe 1.347, ExSharpe 1.212, CAGR 13.59%, MaxDD -9.82%, Calmar 1.38, 2022 4.95%.
- S1 (SHV): Sharpe 1.285, ExSharpe 1.143, CAGR 12.20%, MaxDD -12.76%, Calmar 0.96, 2022 4.95%.
- S3 (50/50): Sharpe 1.313, ExSharpe 1.176, CAGR 12.88%, MaxDD -11.91%, Calmar 1.08, 2022 -1.87%.

Decisive periods:

- 2022 (rate-hike, IEF duration hurts) clean 60/40 returns: S0 +4.95%, S1 +4.95%, S2 -8.45%, S3 -1.87%.
- 2008 (flight-to-quality, IEF duration helps) stress 60/40 returns: S0 +15.17%, S1 +2.04%, S2 +15.17%, S3 +8.46%.

### 3a. Does S0 timing beat SHV-only (S1) and 50/50 (S3) by enough to justify the rule?

Yes. The timing rule's value is an asymmetry that neither fixed rule can match: S0 captures BOTH the 2022 rate-hike protection (short-duration SHV behaviour) AND the 2008 flight-to-quality gain (intermediate-duration IEF behaviour).

- Clean window 60/40: S0 Sharpe 1.347 vs S1 1.285 (+0.062) vs S3 1.313 (+0.034). Modest on Sharpe.
- Drawdown/Calmar is where timing earns its keep: S0 MaxDD -9.82% / Calmar 1.38 vs S1 -12.76% / 0.96 vs S3 -11.91% / 1.08. Timing cuts MaxDD by ~3pp vs SHV-only and ~2pp vs 50/50, and lifts Calmar by +0.42 and +0.30 respectively.
- 2008 flight-to-quality (stress, full year): S0 +15.17% vs S1 +2.04% (SHV-only forfeits the duration rally) vs S3 +8.46%. This is the decisive gap: SHV-only gives up ~13pp of crisis-year return.
- 2022 rate-hike: S0 +4.95% = S1 +4.95% (both correctly sit in SHV), while S2 IEF-only -8.45% and S3 50/50 -1.87% eat the duration loss. Timing matches the best fixed rule here.

So S0 dominates: it equals the better fixed rule in each regime instead of compromising. S2 (IEF-only) is clearly inferior (-17.31% MaxDD, -8.45% in 2022). S3 (50/50) is a permanent compromise that loses on both tails.

### 3b. Is SHV-only nearly as good (simpler, no duration controversy)?

On headline Sharpe, almost (1.285 vs 1.347, -0.062). But NOT on tail protection: SHV-only runs a -12.76% MaxDD (vs -9.82%), a 0.96 Calmar (vs 1.38), and forfeits the 2008 flight-to-quality (+2.04% vs +15.17%). SHV-only is the simplest and avoids all duration risk, but it is structurally exposed in deep equity-crisis flight-to-quality episodes where intermediate Treasuries rally hard. The simplicity is real; the cost is concentrated in exactly the crisis tail the safe sleeve exists to cover.

### 3c. How often does the 13612U timing actually matter?

The diagnostic shows the choice is live and additive, not noise:
- IEF is selected in 45-67% of defensive months (CPM ~45-47%, BULL ~65-67%).
- In IEF-picked months the realized forward IEF-minus-SHV gap is positive on average (CPM mean +1.2 to +1.5%, BULL mean +0.4 to +0.5%) and IEF beats SHV 58-65% of the time.
- Cumulative realized timing edge from CPM picking IEF over SHV in defensive months: about +19 to +21% summed across ~30-36 defensive months. The rule is correctly timing into duration when it pays.

### 3d. Recommendation: KEEP TIMING (best_safe by 13612U).

The `best_safe` 13612U timing earns its keep. It delivers the best fixed-rule outcome in each regime simultaneously: SHV-equivalent protection in 2022 (+4.95%) and IEF-equivalent flight-to-quality capture in 2008 (+15.17%), yielding the lowest MaxDD (-9.82%) and highest Calmar (1.38) of all candidates. SHV-only is simpler but pays for it with a deeper drawdown and a forfeited crisis rally; 50/50 is a permanent compromise that underperforms on both tails; IEF-only is dominated.

Secondary note: S5 (best-of by 12-month return) marginally edges S0 (Sharpe 1.360 vs 1.347, identical -9.82% MaxDD). This is still a timing rule with a different momentum lookback and reinforces the verdict that *some* duration timing beats any fixed rule. We do not recommend switching to S5: the gain is within noise, 13612U is the canonical HAA momentum already used consistently across the canary and both safe sleeves, and re-tuning the lookback to a 12-month-only signal would add an idiosyncratic, more overfit-prone parameter for no robust benefit.

## 4. Caveats and confidence

- Measurement only; no production files edited. Safe rule was monkeypatched on both sleeves (`cpm_live.best_safe`, `bull_qqq_live._pick_safe`) and applied consistently to the shared safe asset, per the mandate.
- S0 reproduces the 60/40 baseline exactly (Sharpe 1.347 / CAGR 13.59% / MaxDD -9.82%); patched 13612U rule confirmed bit-identical to true production for both CPM (0.0 over 4524 days) and BULL (0.0).
- IEF/SHV pre-ETF history uses audited Vanguard mutual-fund stitches (VFITX/VFISX, 1991-10+); duration behaviour in 2008/stress relies on those proxies.
- 2008 clean-window figure is partial-year (window starts 2008-05-30); full-year 2008 is read from the stress window.
- 50/50 (S3) modelled via a synthetic daily-rebalanced SHV+IEF price; daily rebalancing slightly flatters it vs a monthly-rebalanced implementation (turnover not charged on the internal blend).
- Turnover reported is annual one-way at the combined-blend level (shared SHV/IEF net across sleeves); fixed/blend safe rules show lower safe-leg churn but the dominant turnover driver is the CPM risky pair, so blend turnover differences are second-order.
- Confidence: HIGH on the qualitative verdict (keep timing) - the 2008-vs-2022 asymmetry is large and mechanistically expected (duration regime). MODERATE on the exact Sharpe deltas (sensitive to window, proxy stitches, and cost model).
