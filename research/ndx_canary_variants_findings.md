# NDX-sleeve canary variants: does a credit-confirming AND-canary beat TIP-only?

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL NDX-sleeve change; user decides adoption later. Harness `research/ndx_canary_variants.py` (SEPARATE from `ndx_gate_underlying.py` / `ndx_volgate_variants.py` / the rv20_ext harness to avoid write races).

**Question.** The NDX sleeve fires its top-K Nasdaq-100 momentum basket only when BULL is risk-on = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252 on SPY). The canary is TIP-only. Does adding a STRICTER credit confirmation (HYG / LQD / HY-vs-Treasury ratio) on top of TIP cut drawdown and whipsaw, or does the stricter AND just over-de-risk and bleed return (the multi-signal failure mode)?

**Design.** Hold trend = SPY 13612U>0 and vol = SPY RV60<RV252 at production. Vary ONLY the canary. bull_active = canary_variant AND trend_spy AND vol_spy. Variants: TIP only (V0); TIP AND HYG; TIP AND LQD; TIP AND HYG/IEF ratio; TIP OR HYG (CPM-style contrast); HYG alone; HYG/IEF alone. Each leg = 13612U momentum > 0. Selection (top-K=5 raw 13612U, partial-fill to best-of-safe), delisting haircut, T+1 MOO execution held at production. Judged on Calmar AND Martin, keeping crisis catches; whipsaw = monthly on/off flips.

**Convention.** T+1 MOO (next-day open), 10 bps/side, monthly month-end signal. Window 2007-02-28..2026-05-22 (231 monthly signals). NDX STANDALONE sleeve (the lens where the canary matters most; at 20% blend weight effects scale ~1/5).

**Data/EXT honesty.** Repo panel uses AUDITED stitches: HYG<-VWEHX (Vanguard HY mutual fund) pre 2007-04, TIP<-VIPSX, IEF<-VFITX; LQD is raw ETF (2002-07+). So canary signals are computable before ETF inception -- but the NDX sleeve is bounded at 2007-02-28 by the constituent panel, so NO ext beyond 2007 is possible for this sleeve. Window limit = the NDX sleeve's own 2007+ window. Robustness via the 2007-2016 (dirty survivorship) vs 2017+ (clean PIT) split below, not an ext view.

**Caveat up front:** pre-2017 NDX backtest has ~28% survivorship bias (missing delisted tickers); post-2020 PIT coverage is clean. Single ~19y in-sample run; any winner needs paired bootstrap-CI / walk-forward before adoption.

## 0. Anchor (reproduced before deltas)

NDX V0 (TIP-only canary, trend SPY, vol SPY RV60<RV252) standalone: Sharpe **1.1812** / MaxDD **-35.92%** / Calmar **0.7602** / Martin **2.9753** vs expected {'sharpe': 1.1812, 'maxdd': -0.3592, 'calmar': 0.7602, 'martin': 2.9753} -> **CONFIRMED**.

## 1. Canary variants (full-window standalone metrics)

| Canary | CAGR | Vol | Sharpe | MaxDD | Calmar | Martin | Ulcer | active mo | flips |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TIP only (V0) | 27.31% | 22.64% | 1.1812 | -35.92% | 0.7602 | 2.9753 | 9.18% | 110/231 | 40 |
| TIP AND HYG | 27.31% | 22.64% | 1.1812 | -35.92% | 0.7602 | 2.9753 | 9.18% | 110/231 | 40 |
| TIP AND LQD | 26.22% | 21.72% | 1.1826 | -35.92% | 0.7299 | 2.9207 | 8.98% | 103/231 | 44 |
| TIP AND HYG/IEF | 23.09% | 20.16% | 1.1328 | -35.92% | 0.6428 | 2.6307 | 8.78% | 91/231 | 48 |
| TIP OR HYG | 28.46% | 24.04% | 1.1638 | -35.92% | 0.7922 | 2.6798 | 10.62% | 129/231 | 40 |
| HYG alone | 28.46% | 24.04% | 1.1638 | -35.92% | 0.7922 | 2.6798 | 10.62% | 129/231 | 40 |
| HYG/IEF alone | 24.57% | 21.58% | 1.1275 | -35.92% | 0.6840 | 2.3887 | 10.29% | 108/231 | 48 |

## 2. Delta vs V0 (Calmar + Martin are the judged objectives)

| Canary | dSharpe | dCalmar | dMartin | dMaxDD (pp) | dCAGR (pp) | dActiveMo | dFlips |
|---|---:|---:|---:|---:|---:|---:|---:|
| TIP only (V0) | +0.0000 | +0.0000 | +0.0000 | +0.00 | +0.00 | +0 | +0 |
| TIP AND HYG | +0.0000 | +0.0000 | +0.0000 | +0.00 | +0.00 | +0 | +0 |
| TIP AND LQD | +0.0014 | -0.0303 | -0.0546 | -0.00 | -1.09 | -7 | +4 |
| TIP AND HYG/IEF | -0.0484 | -0.1174 | -0.3446 | +0.00 | -4.22 | -19 | +8 |
| TIP OR HYG | -0.0174 | +0.0320 | -0.2954 | +0.00 | +1.15 | +19 | +0 |
| HYG alone | -0.0174 | +0.0320 | -0.2954 | +0.00 | +1.15 | +19 | +0 |
| HYG/IEF alone | -0.0537 | -0.0762 | -0.5866 | -0.00 | -2.74 | -2 | +8 |

*dMaxDD>0 = deeper drawdown (worse). dCalmar/dMartin>0 = better. dActiveMo<0 = more de-risked. dFlips<0 = less whipsaw.*

## 3. AND-variant decomposition: real protection vs return bleed

For each TIP AND X variant: the months where V0 was active but the variant went safe ('newly defensive'). `avg active fwd` = mean forward 1-month return of the NDX-active basket on those skipped months (what V0 earned). Positive => the AND skipped UP months (return BLEED); negative => the AND dodged DOWN months (real PROTECTION). `avg skipped excess` = active minus safe forward return on those months (net give-up by de-risking).

| Canary | newly-def mo | up/down split | avg active fwd | avg skipped excess | read |
|---|---:|---:|---:|---:|---|
| TIP AND HYG | 0 | - | - | - | identical to V0 (never newly-defensive) |
| TIP AND LQD | 7 | 6up/1down | 2.34% | 2.27% | BLEED (skipped mostly UP) |
| TIP AND HYG/IEF | 19 | 14up/5down | 2.66% | 2.15% | BLEED (skipped mostly UP) |

*If newly-defensive months are mostly UP and avg active fwd is positive, the stricter AND is de-risking into strength = return bleed, not crisis protection.*

## 4. Per-crisis protection (NDX sleeve MaxDD / total return in window)

| Canary | 2008 GFC DD/Ret | 2018 Q4 DD/Ret | 2020 COVID DD/Ret | 2022 bear DD/Ret |
|---|---|---|---|---|
| TIP only (V0) | -9.11% / 18.01% | -7.43% / 27.57% | -20.46% / 8.57% | -0.30% / 0.94% |
| TIP AND HYG | -9.11% / 18.01% | -7.43% / 27.57% | -20.46% / 8.57% | -0.30% / 0.94% |
| TIP AND LQD | -9.11% / 18.01% | -2.22% / 15.80% | -20.46% / 8.57% | -0.30% / 0.94% |
| TIP AND HYG/IEF | -9.11% / 18.01% | -7.43% / 27.57% | -5.05% / 18.28% | -0.30% / 0.94% |
| TIP OR HYG | -9.11% / 18.01% | -24.07% / -0.05% | -20.46% / 8.57% | -0.30% / 0.94% |
| HYG alone | -9.11% / 18.01% | -24.07% / -0.05% | -20.46% / 8.57% | -0.30% / 0.94% |
| HYG/IEF alone | -9.11% / 18.01% | -24.07% / -0.05% | -5.05% / 18.28% | -0.30% / 0.94% |

*Windows: 2008 GFC 2008-01-01..2009-06-30; 2018 Q4 2018-01-01..2018-12-31; 2020 COVID 2020-01-01..2020-06-30; 2022 bear 2022-01-01..2022-12-31.*

## 5. Sub-period robustness (don't headline only the full-sample Calmar)

| Canary | 2007-2016 (dirty surv.) Calmar/Martin/MaxDD | 2017-2026 (clean PIT) Calmar/Martin/MaxDD |
|---|---|---|
| TIP only (V0) | 1.437/6.819/-17.28% | 0.837/2.386/-35.92% |
| TIP AND HYG | 1.437/6.819/-17.28% | 0.837/2.386/-35.92% |
| TIP AND LQD | 1.400/6.650/-17.28% | 0.793/2.317/-35.92% |
| TIP AND HYG/IEF | 1.249/6.299/-17.28% | 0.690/2.054/-35.92% |
| TIP OR HYG | 1.703/7.191/-17.28% | 0.767/1.885/-35.92% |
| HYG alone | 1.703/7.191/-17.28% | 0.767/1.885/-35.92% |
| HYG/IEF alone | 1.551/7.184/-17.28% | 0.623/1.573/-35.92% |

## 6. VERDICT scorecard

Beats-V0 = Calmar AND Martin both strictly higher than V0. Keeps crash = 2008 & 2020 DD not >3pp deeper than V0; keeps grind = 2018-Q4 & 2022 DD not >4pp deeper than V0.

| Canary | Calmar | Martin | Sharpe | MaxDD | beats V0? | keeps crash? | keeps grind? |
|---|---:|---:|---:|---:|:--:|:--:|:--:|
| TIP only (V0) | 0.7602 | 2.9753 | 1.1812 | -35.92% | no | Y | Y |
| TIP AND HYG | 0.7602 | 2.9753 | 1.1812 | -35.92% | no | Y | Y |
| TIP AND LQD | 0.7299 | 2.9207 | 1.1826 | -35.92% | no | Y | Y |
| TIP AND HYG/IEF | 0.6428 | 2.6307 | 1.1328 | -35.92% | no | Y | Y |
| TIP OR HYG | 0.7922 | 2.6798 | 1.1638 | -35.92% | no | Y | NO |
| HYG alone | 0.7922 | 2.6798 | 1.1638 | -35.92% | no | Y | NO |
| HYG/IEF alone | 0.6840 | 2.3887 | 1.1275 | -35.92% | no | Y | NO |

**No credit-confirming canary beats V0 on Calmar AND Martin while keeping crash + grind catches.** On this sample, requiring a credit confirmation on top of TIP does NOT net-improve over TIP-only.

## 7. Skepticism on the apparent winner

No variant cleared the beats-V0 + keeps-catches bar, so there is no winner to stress. The AND-decomposition (section 3) already shows whether the stricter canaries protect or bleed.

## 8. Bottom line: does a credit-confirming canary beat TIP-only on NDX?

**Short answer: NO.** No credit-confirming AND-canary (TIP AND HYG / LQD / HYG-IEF) beats TIP-only on the NDX sleeve on Calmar AND Martin while keeping catches. The decomposition (section 3) shows the stricter AND mostly de-risks into strength (skipped months are predominantly UP), i.e. return bleed rather than crisis protection -- the same failure mode as the multi-asset-canary rejection on CPM.

- TIP AND HYG: Calmar 0.7602 (V0 0.7602), Martin 2.9753 (V0 2.9753). Newly-defensive 0 mo, 0up/0down, avg active fwd n/a.

- TIP AND HYG/IEF: Calmar 0.6428, Martin 2.6307. Newly-defensive 19 mo, 14up/5down, avg active fwd 2.66%.

- TIP AND LQD: Calmar 0.7299, Martin 2.9207.

**Net of lag: the stricter AND just over-de-risks.** Recommendation: KEEP TIP-only on the NDX sleeve; do NOT add a credit-confirming AND-canary.

**Adoption status: RESEARCH ONLY, not adopted.** Single in-sample run; 2007+ ETF/proxy window; pre-2017 NDX survivorship bias; T+1 MOO / PIT honesty caveats. User decides.

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.
- Only the canary leg changes; trend(SPY 13612U)/vol(SPY RV60<RV252)/selection/delisting/execution held at prod.
- NDX standalone sleeve lens; at 20% blend weight effects scale ~1/5 (dilute further vs CPM+BULL co-movement).
- Canary legs use AUDITED stitches (HYG<-VWEHX, TIP<-VIPSX, IEF<-VFITX); LQD raw ETF 2002+. NDX sleeve bounded at 2007 by constituent panel => no ext beyond 2007.
- 13612U = simple average of 1/3/6/12-month total returns on monthly resampled closes.
- HYG/IEF ratio leg = sig_13612U on the monthly resampled HYG/IEF price ratio.
- Pre-2017 NDX segment has ~28% survivorship bias; post-2020 is clean PIT coverage.
- Single sample + ETF-inception window limit; any winner needs paired bootstrap-CI + walk-forward before adoption.
