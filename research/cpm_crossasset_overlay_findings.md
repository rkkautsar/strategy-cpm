# CPM cross-asset overlay study -- multi-asset canary / carry-value / PC1 gate

Role: analyst (hypothesis-driven, READ-ONLY re production; no prod/memo edits; no commit). Throwaway harness `research/cpm_crossasset_overlay.py`.

**Convention:** IV4 production spec; execution T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost 10 bps/side; cov lookback 504d; K=4. Clean 2008-05-30..2026-05-22 (decisive); ext 1999-03-10..2026-05-22. All signals point-in-time (<= month-end decision date), executed T+1. VWO fetched 2005-03-10..2026-05-21.

Crisis columns (MaxDD within window): GFC / COVID / 2022 / Dot-com.

## 0. Anchor gate

| Window | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| clean | 1.1910 | -12.67% | 1.0615 | 1.191/-12.67%/1.0615 | CONFIRMED |
| ext | 1.2142 | -15.93% | 0.8608 | 1.2142/-15.93%/0.8608 | CONFIRMED |

Generalized weight-fn base self-check: clean Sharpe 1.190980, matches production = True. Candidate deltas below are trusted on this basis.

## Production CPM reference

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| CPM-solo clean | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 |
| CPM-solo ext | 1.2142 | 13.71% | 11.09% | -15.93% | 0.8608 | 3.8201 |

Production crisis MaxDD -- GFC -11.88%, COVID -10.06%, 2022 -6.33%, Dot-com -5.87%.

## 1. Multi-asset canary upgrade

Clean window, CPM-solo. Crisis = MaxDD within window.

| Canary variant | Sharpe | CAGR | MaxDD | Calmar | Martin | GFC | COVID | 2022 | Dot-com |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PROD HYG-OR-TIP (1of2) | 1.1910 | 13.44% | -12.67% | 1.0615 | 3.9646 | -11.88% | -10.06% | -6.33% | -5.87% |
| TIP+DBC (1of2) | 1.0821 | 11.81% | -13.64% | 0.8662 | 2.8053 | -11.88% | -10.06% | -8.74% | -10.26% |
| TIP+VWO (1of2) | 1.1699 | 12.96% | -12.67% | 1.0229 | 3.7983 | -11.88% | -10.06% | -6.33% | -5.87% |
| {HYG,TIP,DBC,VWO} 1of4 | 1.1733 | 13.35% | -12.67% | 1.0542 | 3.5076 | -11.88% | -10.06% | -8.74% | -10.26% |
| {HYG,TIP,DBC,VWO} 2of4 | 1.1149 | 12.30% | -12.67% | 0.9712 | 3.5413 | -11.88% | -10.06% | -6.33% | -7.02% |
| {HYG,TIP,DBC,VWO} 3of4 | 1.0676 | 11.08% | -12.67% | 0.8752 | 2.8650 | -7.04% | -4.86% | -6.33% | -6.21% |

### 1b. Extended window (CPM-solo)

| Canary variant | Sharpe | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|
| PROD HYG-OR-TIP (1of2) | 1.2142 | -15.93% | 0.8608 | 3.8201 |
| TIP+DBC (1of2) | 1.1304 | -15.93% | 0.7855 | 3.0189 |
| TIP+VWO (1of2) | 1.1531 | -15.93% | 0.7815 | 3.5676 |
| {HYG,TIP,DBC,VWO} 1of4 | 1.2033 | -15.93% | 0.8606 | 3.5389 |
| {HYG,TIP,DBC,VWO} 2of4 | 1.1540 | -15.93% | 0.8049 | 3.5037 |
| {HYG,TIP,DBC,VWO} 3of4 | 1.0620 | -15.93% | 0.6866 | 2.8907 |

### 1c. Gate-dominance (TIP single-signal dominance)

Sole-gate share = fraction of risk-on months where that asset is PIVOTAL (removing it flips the decision to risk-off given the N-of-M threshold). Clean window.

| Canary config | Risk-on months | DBC | HYG | TIP | VWO |
|---|---:|---:|---:|---:|---:|
| PROD {HYG,TIP} 1of2 | 188 | - | 15% | 7% | - |
| {HYG,TIP,DBC,VWO} 1of4 | 198 | 5% | 3% | 5% | 0% |
| {HYG,TIP,DBC,VWO} 2of4 | 174 | 3% | 17% | 12% | 6% |

## 2. Carry / value complement

Bond carry = FRED term spread T10Y3M; equity carry/value = Shiller CAPE earnings yield; commodity roll-yield OMITTED (no futures curve in cache) -> GLD/DBC neutral. FILTER drops the single lowest-carry positive when term spread is inverted (<0, late cycle); TILT blends 70% inverse-vol + 30% carry-rank weight. Clean window, CPM-solo.

| Carry variant | Sharpe | CAGR | MaxDD | Calmar | Martin | GFC | COVID | 2022 | Dot-com |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PROD (no carry) | 1.1910 | 13.44% | -12.67% | 1.0615 | 3.9646 | -11.88% | -10.06% | -6.33% | -5.87% |
| carry FILTER (drop low-carry at term inversion) | 1.1363 | 12.43% | -13.32% | 0.9332 | 3.6890 | -11.88% | -9.68% | -6.33% | -5.87% |
| carry TILT (70% invvol + 30% carry rank) | 1.1633 | 13.37% | -13.39% | 0.9986 | 3.9136 | -13.23% | -10.84% | -7.41% | -7.20% |
| carry FILTER + TILT | 1.1188 | 12.49% | -13.42% | 0.9305 | 3.6608 | -13.23% | -10.54% | -7.41% | -7.20% |

### 2b. Extended window

| Carry variant | Sharpe | MaxDD | Calmar |
|---|---:|---:|---:|
| PROD | 1.2142 | -15.93% | 0.8608 |
| carry FILTER (drop low-carry at term inversion) | 1.1863 | -15.93% | 0.8214 |
| carry TILT (70% invvol + 30% carry rank) | 1.2033 | -15.87% | 0.8764 |
| carry FILTER + TILT | 1.1807 | -15.87% | 0.8390 |

## 3. PC1 / absorption-ratio gate

Rolling 60d correlation matrix of the 8 risky assets; PC1 eigenvalue share. De-risk (scale risky exposure, remainder to safe) when PC1 > threshold. Point-in-time, T+1. Clean window, CPM-solo.

| PC1 gate | Sharpe | CAGR | MaxDD | Calmar | Martin | GFC | COVID | 2022 | Dot-com |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PROD (no gate) | 1.1910 | 13.44% | -12.67% | 1.0615 | 3.9646 | -11.88% | -10.06% | -6.33% | -5.87% |
| PC1>65% -> risky*0.5 | 1.1506 | 12.57% | -12.67% | 0.9927 | 3.8237 | -11.88% | -10.06% | -6.33% | -5.87% |
| PC1>65% -> risky*0 | 1.0787 | 11.67% | -17.81% | 0.6552 | 2.8054 | -11.88% | -10.06% | -6.33% | -5.87% |
| PC1>70% -> risky*0.5 | 1.2144 | 13.64% | -12.67% | 1.0766 | 4.1211 | -11.88% | -10.06% | -6.33% | -5.87% |
| PC1>70% -> risky*0 | 1.2276 | 13.81% | -12.67% | 1.0907 | 4.2057 | -11.88% | -10.06% | -6.33% | -5.87% |
| PC1>75% -> risky*0.5 | 1.1896 | 13.42% | -12.67% | 1.0594 | 3.9657 | -11.88% | -10.06% | -6.33% | -5.87% |
| PC1>75% -> risky*0 | 1.1866 | 13.39% | -12.67% | 1.0570 | 3.9627 | -11.88% | -10.06% | -6.33% | -5.87% |

PC1 firing frequency:

| Threshold/window | Fires | Decisions | Share |
|---|---:|---:|---:|
| 65%_clean | 27 | 217 | 12.4% |
| 65%_ext | 27 | 327 | 8.3% |
| 70%_clean | 9 | 217 | 4.1% |
| 70%_ext | 9 | 327 | 2.8% |
| 75%_clean | 3 | 217 | 1.4% |
| 75%_ext | 3 | 327 | 0.9% |

## 4. Execution-lag robustness (clean Sharpe)

mooex = T+1 MOO exact (production). moc = same-day close (exec_lag=0 close economics). An edge that survives BOTH is not a lag/lookahead artifact.

| Config | mooex Sharpe | moc Sharpe | delta |
|---|---:|---:|---:|
| PROD | 1.1910 | 1.2063 | +0.0153 |
| {HYG,TIP,DBC,VWO} 2of4 | 1.1149 | 1.1144 | -0.0005 |
| carry FILTER | 1.1363 | 1.1568 | +0.0205 |
| PC1>70% risky*0.5 | 1.2144 | 1.2344 | +0.0200 |

## 5. Per-candidate verdict

### Candidate 1 -- multi-asset canary upgrade: REJECT

Every generalized canary variant LOWERS clean CPM-solo Sharpe vs production 1.1910 (best alt 1.1733; TIP+DBC worst 1.0821). NONE improves the 2022 catch -- production already holds 2022 at -6.33% MaxDD; TIP+DBC and the 1of4 set make 2022 WORSE (-8.74%) because adding DBC (a commodity that rose in 2022 stagflation) keeps the engine risk-on through the duration selloff. Crisis catches otherwise unchanged.

**Gate-dominance finding (answers the TIP question):** under the precise pivotal/sole-gate measure (a canary is pivotal in a month only if removing it flips risk-on->off), TIP is sole-pivotal in just 7% of risk-on months and HYG in 15% (~78% of risk-on months have BOTH positive = redundant confirmation). The prior 'TIP gates ~60-80%' framing reflected a looser 'TIP is positive' count, not pivotality. **Single-signal dominance is already LOW**; the multi-asset upgrade solves a non-problem and costs Sharpe. The wider {HYG,TIP,DBC,VWO} 2of4 set does spread pivotality (HYG 17/TIP 12/DBC 3/VWO 6 %) but at clean Sharpe 1.1149.

### Candidate 2 -- carry / value complement: REJECT

Both the carry FILTER (1.1363) and the carry TILT (1.1633) sit BELOW production on BOTH Sharpe (1.1910) and Calmar (1.0615 vs 0.9986 tilt / 0.9332 filter). Combined worse still. The judged axis (Sharpe AND Calmar) fails. Caveat: the commodity roll-yield leg is OMITTED (no futures curve) so GLD/DBC carry is neutral -- a genuine data gap that weakens the test of the carry hypothesis, but the equity-EY + bond-term-spread tilt alone shows no edge.

### Candidate 3 -- PC1 / absorption-ratio gate: PROMISING (Sharpe/Calmar) but threshold-fragile; NOT crisis-protective

PC1>70% -> risky*0.5 beats production on Sharpe (1.2144 vs 1.1910, +0.0234) AND Calmar (1.0766 vs 1.0615); full de-risk (risky*0) is marginally better (1.2276/1.0907). The edge SURVIVES execution lag (mooex 1.2144 vs moc 1.2344; production moc 1.2063 -- the ~+0.02-0.03 edge holds in both conventions, so it is not a lookahead artifact).

**BUT three load-bearing caveats:** (1) **Threshold-fragile** -- 70% is a sweet spot; 65% HURTS (1.1506, fires 12% of months = over-gating) and 75% fades (1.1896, fires only 1.4%). A 3-point sweep with one winner is a classic single-fit risk. (2) **Not crisis-protective** -- every crisis MaxDD is IDENTICAL to production (GFC -11.88%, COVID -10.06%, 2022 -6.33%, Dot-com -5.87%): the 70% gate fires only 9 times in 18y (4.1%) and never touches the crisis troughs. It KEEPS the catches trivially (does not alter them) and earns its lift purely by de-risking a handful of high-correlation, low-forward-return NORMAL months -- a return-quality overlay, not a tail-risk control. (3) Single in-sample; needs walk-forward / sub-period / OOS before any adoption.

### Bottom line

No candidate is adoption-ready. C1 and C2 are clear REJECTs (underperform on the judged axis, no crisis gain). C3 (PC1>70% half-de-risk) is the only candidate that beats production on its judged axis (Calmar/Martin + Sharpe) net of lag while keeping crisis catches, but it is threshold-fragile and adds zero crisis protection -- it is a modest normal-regime Sharpe/Calmar overlay, not the stagflation/diversification-collapse tail fix the hypothesis hoped for. Recommend walk-forward validation of C3 PC1>70% before considering it; do NOT adopt on this single in-sample run.

## Caveats

- Single in-sample backtest. Any apparent winner needs walk-forward / sub-period / OOS validation before adoption (per prior swap-vs-document discipline). No adoption here.
- All post-cost (10 bps/side), T+1 MOO exact with real opens; CPM-solo (no BULL blend).
- Canary signals point-in-time 13612U on monthly closes <= decision date. VWO is signal-only (not traded); see VWO note above for proxy status.
- Carry: commodity roll-yield omitted (no futures curve) -> GLD/DBC carry neutral, a real gap. Equity carry uses Shiller CAPE monthly (lagged); term spread is daily FRED.
- PC1 gate uses 60d daily-return correlation eigen-share; binary de-risk floor variants shown (0.5 partial, 0.0 full to safe). Threshold sweep 65/70/75% only.
- Ext 27y is partially proxy-backed pre-2006 for the CPM trend universe.
