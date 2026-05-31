# CPM universe-substitution robustness

Role: analyst (read-only re production; NO production/memo files changed; NO commit). Throwaway harness `research/cpm_robust_universe.py`; raw output `research/cpm_robust_universe.json` (== `..._findings.json`).

## Question

Does CPM's edge survive risky-universe substitution, or is it dependent on the QQQ/SPHQ quality/tech tilt? Specifically the SPY swap (drop QQQ+SPHQ for plain SPY).

## Method

Full CPM pipeline held FIXED, only the risky universe swapped:
- vol-adjusted Faber rank (m_faber / rv_252d), positive-trend screen, top-4, inverse-vol over surviving positives, strict-4 partial-safe (min(n,4)/4), HYG-OR-TIP canary, SHV/IEF safe selector, covariance lookback 504d.
- Convention: mooex T+1 MOO exact (real auto_adjust opens), 10 bps/side, monthly month-end signal. Clean 2008-05-30..2026-05-22 (18y, decisive lens); ext 1999-03-10..2026-05-22 (proxy-backed pre-2006 tail).
- TOP_K stays 4 for every universe (production pipeline; ceil(N/2)=4 for N=7,8,10 anyway). Universe injected by monkeypatching `cpm_live.RISKY_UNIVERSE` + the imported `V.RISKY_UNIVERSE`. Everything else byte-identical to production builder (`exec_lag_moo_validation_2026_05_30.cpm_sleeve_conv`).

Inputs: in-repo `data/proxy_adjusted_close_daily.csv` + stitched series + OHLC cache `/tmp/cpm_open_cache`. All risky tickers (incl SPY, IEF, LQD, HYG) present in panel.

## Anchor gate (CONFIRMED, exact)

PROD_8 clean reproduced Sharpe **1.1910** / MaxDD **-12.67%** / Calmar **1.0615** -- exact match to the production anchor. ext 1.2142 / -15.93% / 0.8608. All variant numbers trusted on this basis.

## Results -- CLEAN (18y, decisive)

| Universe | N | Sharpe | CAGR | Vol | MaxDD | Calmar | dSharpe | dCalmar | dCAGR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PROD_8 (QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC) | 8 | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | -- | -- | -- |
| SPYswap_7 (SPY,EFA,EEM,VNQ,GLD,TLT,DBC) | 7 | 1.0122 | 10.62% | 10.57% | -11.75% | 0.9035 | -0.179 | -0.158 | -2.83pp |
| AAA_8 (SPY,EFA,EEM,VNQ,IEF,TLT,DBC,GLD) | 8 | 1.0328 | 10.14% | 9.87% | -13.69% | 0.7405 | -0.158 | -0.321 | -3.30pp |
| KellerGTAA10 (SPY,EFA,EEM,IEF,GLD,DBC,VNQ,TLT,LQD,HYG) | 10 | 0.9881 | 8.15% | 8.31% | -12.78% | 0.6374 | -0.203 | -0.424 | -5.30pp |
| FaberGTAA5 (SPY,EFA,IEF,VNQ,DBC) | 5 | 0.8131 | 6.43% | 8.11% | -10.93% | 0.5887 | -0.378 | -0.473 | -7.01pp |

## Results -- EXT (27y, proxy-backed tail)

| Universe | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| PROD_8 | 1.2142 | 13.71% | 11.09% | -15.93% | 0.8608 |
| SPYswap_7 | 1.0993 | 11.53% | 10.42% | -13.45% | 0.8573 |
| AAA_8 | 1.1089 | 10.70% | 9.59% | -13.69% | 0.7817 |
| KellerGTAA10 | 1.1104 | 8.76% | 7.84% | -12.78% | 0.6858 |
| FaberGTAA5 | 0.9829 | 7.71% | 7.87% | -10.93% | 0.7053 |

Passive AAA benchmark reference (memo Sec 5.5): clean Sharpe 0.7869, Calmar 0.3188, MaxDD -23.21%.

## Reading

- SPY swap (the key test): pipeline still strong -- clean Sharpe 1.01, Calmar 0.90, ext Sharpe 1.10. The loss vs PROD is almost ENTIRELY return, not risk: CAGR -2.83pp, but MaxDD is shallower (-11.75% vs -12.67%) and vol lower (10.57% vs 11.16%). So QQQ/SPHQ contribute a return premium (~+2.8pp CAGR, ~+0.18 Sharpe, ~+0.16 Calmar), NOT risk control. Risk-control machinery (canary, partial-safe, inverse-vol) is universe-agnostic.
- Every variant keeps clean Sharpe >= 0.81, ext Sharpe >= 0.98, MaxDD <= -13.7% (all far shallower than the AAA passive benchmark -23.21%), and Calmar >= 0.59. The CPM pipeline beats the passive AAA Sharpe (0.79) in all five universes, both windows.
- AAA_8: Sharpe holds (1.03 clean / 1.11 ext) but Calmar degrades to 0.74 clean (IEF+TLT double-bond + no quality tilt; deeper -13.69% MaxDD).
- FaberGTAA5: weakest (Sharpe 0.81, CAGR 6.4%). Largely a breadth artifact -- with N=5 and top-4, selection barely filters (4 of 5 held), and the universe lacks EEM/GLD/TLT separation. Not a pipeline failure so much as a starved universe.
- KellerGTAA10: Sharpe near 1.0 but lowest CAGR/Calmar (more bonds + LQD/HYG diluting trend leaders). CAVEAT: LQD has no OHLC in cache, so mooex falls back to close-close on rebal days for LQD-holding months (real/fallback 125/201 vs ~250/76 elsewhere); close-close vs mooex difference is immaterial per `cpm_headline_numbers_findings`, but treat this row as slightly lower-fidelity.

## VERDICT

CPM's edge is ROBUST to universe choice in the sense that matters: the pipeline produces clean Sharpe ~1.0+ and ext Sharpe ~1.1, shallow drawdowns (<14%), and beats the passive AAA benchmark (0.79 Sharpe / 0.32 Calmar) in EVERY tested universe including the plain-SPY swap. The risk-control structure (canary, strict-4 partial-safe, inverse-vol) is universe-agnostic -- swapping to SPY actually lowers vol and MaxDD.

HOWEVER, the HEADLINE MAGNITUDE (Sharpe 1.19, Calmar 1.06, CAGR 13.4%) is partly tilt-enhanced: the QQQ/SPHQ quality/tech sleeve adds ~+0.18 clean Sharpe, ~+0.16 Calmar, ~+2.8pp CAGR over plain SPY -- a return premium, not better risk control. Without QQQ/SPHQ, CPM remains a strong strategy (Sharpe ~1.0, Calmar ~0.90) but no longer posts the >1.0 Calmar / >13% CAGR headline.

Materially-degraded flag: FaberGTAA5 (Sharpe 0.81 / CAGR 6.4% / Calmar 0.59) -- but driven by N=5 starved breadth under a fixed top-4, not a structural CPM break. AAA_8 and KellerGTAA10 degrade Calmar (0.74 / 0.64) while holding Sharpe ~1.0.

Confidence: HIGH on clean-window relative ordering and the SPY-swap conclusion (anchor reproduced exactly, identical pipeline, real opens). MEDIUM on KellerGTAA10 absolute level (LQD mooex fallback) and on ext-window levels (proxy-backed pre-2006 tail). Top-4 was held constant across N; a breadth-scaled top-K (ceil(N/2)) was not tested and could change FaberGTAA5/KellerGTAA10 specifically.

## Reproduction

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
.venv/bin/python research/cpm_robust_universe.py
```
Outputs: `research/cpm_robust_universe.json` (== `research/cpm_robust_universe_findings.json`).
