# RV20 vs RV60 on the EXTENDED / 1970s windows -- whipsaw + crisis-catch test

Role: analyst (read-only re production; writes only research/; no prod/memo edits; no commit). Own harness `research/rv20_ext_whipsaw.py`. Does NOT edit other analysts' files.

**Recollection under test:** "RV20 was a bit overfit to the clean period; on the EXTENDED window it whipsaws." The prior verdict adopted RV20<RV252 for NDX on clean-18y + post-2017 walk-forward, but never tested the EXTENDED/older window, and the in-sample bootstrap CI already INCLUDED 0 (RV20-V0 Calmar P=85%). This study supplies the missing ext / 1970s test.

**V0** = RV60<RV252 (SPY); **candidate** = RV20<RV252 (SPY). The gate underlying is SPY for BOTH the BULL and NDX sleeves, so SPY-gate whipsaw over the extended window IS the NDX-relevant test.

**Anchor reproduced before deltas:** ext-harness CLEAN(2008+) BULL rv60 close-to-close Sharpe 0.9936 / Calmar 0.7305 / MaxDD -13.60% (expect 0.9936/0.7305/-13.60%).


## PART A -- 1970s stagflation OOS (genuine older regime)

Monthly S&P sleeve, vol-gate-ONLY (risk-on iff rv_fast<rv_252 on ^GSPC daily, else 3m T-bill), t+1 monthly lag. Window 1968-01..1985-12. Reuses stagflation_1970s_trend_vol loaders verbatim.

| Variant | CAGR | MaxDD | Sharpe | Calmar | Martin | Flips | FlipsYr | Def% | FP rate | DownCap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| nogate | 8.85% | -39.16% | 0.1347 | 0.2261 | 0.8532 | 0 | 0.0000 | 0.00% | n/a | 0.00% |
| rv60 | 7.64% | -21.21% | 0.0233 | 0.3601 | 1.2685 | 41 | 2.2778 | 38.89% | 60.71% | 37.93% |
| rv20 | 11.67% | -11.66% | 0.4059 | 1.0001 | 2.8479 | 56 | 3.1111 | 30.56% | 51.52% | 36.78% |

Crisis catches (DD / total return within window):

| Variant | 1973-74 bear | 1977-82 stagflation |
|---|---|---|
| nogate | -39.16% / -38.55% | -13.42% / 80.67% |
| rv60 | -21.21% / -14.05% | -13.31% / 35.52% |
| rv20 | -9.72% / 3.56% | -10.12% / 70.55% |

**Whipsaw delta RV20 vs RV60 (1970s):** flips 56 vs 41 (+15); FP rate 51.52% vs 60.71%; defensive 30.56% vs 38.89%.


## PART B1 -- EXTENDED SPY-gate on the BULL daily sleeve (1982/1995-2026)

Reuses bull_10y3m_extended_1982 (production close-to-close T+1, 10 bps/side, gates monkeypatched). Gates: no-gate (HAA-simple), RV60 (prod V0), RV20 (candidate).

### full_1982

| Gate | Sharpe | Calmar | Martin | MaxDD | CAGR | Flips | FlipsYr | Def% | FP rate | DownCap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| nogate | 1.0137 | 0.6211 | 2.6955 | -20.28% | 12.59% | 0 | 0.0000 | 0.00% | n/a | 0.00% |
| rv60 | 1.0638 | 0.5515 | 2.3036 | -19.56% | 10.79% | 94 | 2.1243 | 54.05% | 62.02% | 57.98% |
| rv20 | 1.0392 | 0.6476 | 2.7724 | -16.77% | 10.86% | 132 | 2.9831 | 50.66% | 60.59% | 56.38% |

RV20-RV60 deltas (full_1982): Calmar +0.0962, Martin +0.4689, flips +38 (132 vs 94), FP rate 60.59% vs 62.02%.

### ext_1995

| Gate | Sharpe | Calmar | Martin | MaxDD | CAGR | Flips | FlipsYr | Def% | FP rate | DownCap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| nogate | 0.9752 | 0.6101 | 2.5612 | -20.28% | 12.37% | 0 | 0.0000 | 0.00% | n/a | 0.00% |
| rv60 | 0.9228 | 0.4684 | 1.8306 | -19.56% | 9.16% | 71 | 2.2660 | 54.79% | 61.17% | 62.02% |
| rv20 | 0.9555 | 0.6424 | 2.6093 | -15.41% | 9.90% | 95 | 3.0319 | 52.13% | 58.67% | 62.79% |

RV20-RV60 deltas (ext_1995): Calmar +0.1740, Martin +0.7787, flips +24 (95 vs 71), FP rate 58.67% vs 61.17%.

### clean_2008

| Gate | Sharpe | Calmar | Martin | MaxDD | CAGR | Flips | FlipsYr | Def% | FP rate | DownCap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| nogate | 0.9635 | 0.5735 | 2.4947 | -20.28% | 11.63% | 0 | 0.0000 | 0.00% | n/a | 0.00% |
| rv60 | 0.9936 | 0.7305 | 2.8024 | -13.60% | 9.93% | 40 | 2.2222 | 50.93% | 60.91% | 61.43% |
| rv20 | 1.0546 | 0.7972 | 3.1476 | -13.60% | 10.84% | 50 | 2.7778 | 49.07% | 58.49% | 62.86% |

RV20-RV60 deltas (clean_2008): Calmar +0.0667, Martin +0.3452, flips +10 (50 vs 40), FP rate 58.49% vs 60.91%.

### Per-episode MaxDD (full 1982 window, BULL sleeve)

| Episode | nogate | rv60 | rv20 |
|---|---:|---:|---:|
| 1990 recession | -16.77% | -16.77% | -16.77% |
| 2000-02 dot-com | -13.86% | -13.46% | -12.49% |
| 2008-09 GFC | -10.10% | -10.10% | -10.10% |
| 2011 euro/dgrade | -17.18% | -6.75% | -6.75% |
| 2018-Q4 | -0.02% | -0.02% | -0.02% |
| 2020-COVID | -13.60% | -13.60% | -13.60% |
| 2022 grind | -10.61% | -0.30% | -0.30% |

## PART B2 -- EXTENDED high-beta NDX PROXY (QQQ), vol-gate-only

QQQ monthly returns (repo proxy from 1988-10-03) gated by the SAME SPY-based vol gate (SPY from 1995-01-04), monthly t+1. Window 1995-01-31..2026-05-31. **CAVEAT: QQQ proxy != survivorship-clean NDX-100 sleeve; directional high-beta proxy only.**

| Variant | CAGR | MaxDD | Sharpe | Calmar | Martin | Flips | FlipsYr | Def% | FP rate | DownCap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| nogate | 15.15% | -81.08% | 0.5851 | 0.1868 | 0.3911 | 0 | 0.0000 | 0.00% | n/a | 0.00% |
| rv60 | 12.29% | -70.67% | 0.5992 | 0.1739 | 0.4106 | 61 | 1.9416 | 38.46% | 53.79% | 45.89% |
| rv20 | 12.08% | -66.16% | 0.5779 | 0.1826 | 0.4530 | 106 | 3.3740 | 35.01% | 56.06% | 39.73% |

Crisis catches (DD / total return, QQQ proxy):

| Variant | 2000-02 dotcom | 2008 GFC | 2018-Q4 | 2020 COVID | 2022 bear |
|---|---|---|---|---|---|
| nogate | -81.08% / -77.00% | -49.74% / -28.70% | -8.90% / -16.73% | -7.29% / 13.46% | -26.11% / -32.58% |
| rv60 | -70.67% / -64.36% | -0.12% / 40.16% | 0.00% / -8.24% | -0.03% / -5.65% | -0.11% / 4.81% |
| rv20 | -62.95% / -56.76% | -14.89% / 8.40% | 0.00% / -8.24% | -0.03% / 6.96% | -15.15% / -14.47% |

**RV20-RV60 deltas (QQQ ext proxy):** Calmar +0.0087, Martin +0.0423, flips +45 (106 vs 61), FP rate 56.06% vs 53.79%.


## SYNTHESIS -- does RV20's edge SURVIVE the extended/older window?

Three lenses, one consistent mechanism (a faster window flips ~1.5x more often; whether
that helps or hurts depends on the sleeve's BETA):

| Lens | RV20 vs RV60 Calmar | RV20 vs RV60 Martin | flips RV20/RV60 | FP rate RV20/RV60 | crisis catches |
|---|---:|---:|---:|---:|---|
| 1970s stagflation (S&P) | **+0.640** (1.000 vs 0.360) | **+1.579** | 56 / 41 (+15) | 51.5% / 60.7% (better) | RV20 BEST: 1973-74 -9.7% vs -21.2% |
| ext-1995 BULL daily | **+0.174** (0.642 vs 0.468) | **+0.779** | 95 / 71 (+24) | 58.7% / 61.2% (better) | RV20 keeps 2011/2022; DD -15.4% vs -19.6% |
| full-1982 BULL daily | **+0.096** (0.648 vs 0.552) | **+0.469** | 132 / 94 (+38) | 60.6% / 62.0% (better) | RV20 keeps all; DD -16.8% vs -19.6% |
| **ext-1995 QQQ (NDX proxy)** | **+0.009** (0.183 vs 0.174, NOISE) | **+0.042** (NOISE) | **106 / 61 (+45, ~2x)** | **56.1% / 53.8% (WORSE)** | **RV20 GIVES BACK 2008 (-14.9% vs -0.1%) and 2022 (-15.2% vs -0.1%)** |

### Confirm / refute the "overfit-to-clean / whipsaws on ext" recollection

**PARTIALLY CONFIRMED -- and confirmed precisely where it matters (the high-beta NDX sleeve).**

- **REFUTED on the gate/BULL level and the 1970s.** On the S&P 1970s OOS and the BULL daily
  sleeve (full-1982, ext-1995, clean-2008), RV20 still BEATS RV60 on Calmar/Martin/MaxDD,
  keeps (even improves) crisis catches, and -- despite more raw flips -- has a LOWER
  false-positive rate. The faster window is NOT globally overfit; on low/medium-beta sleeves
  its extra flips are net-accretive (it de-risks earlier and re-risks faster correctly).
- **CONFIRMED on the high-beta QQQ ext proxy (the NDX-relevant lens).** Here the RV20 edge
  over RV60 COLLAPSES TO NOISE (Calmar +0.009, Martin +0.042), whipsaw roughly DOUBLES
  (flips/yr 3.37 vs 1.94), the FP rate gets WORSE (56.1% vs 53.8% -- the only lens where it
  does), and RV20 SURRENDERS the 2008 GFC (-14.9% vs RV60 -0.1%) and 2022 bear (-15.2% vs
  -0.1%) crisis catches that RV60 holds cleanly. RV20 keeps only the COVID-2020 catch (tied
  with RV60). This is exactly the whipsaw the user remembered: a faster window's extra flips
  cost MORE on a high-beta stream, and over the extended window that cost shows up as
  re-entering 2008/2022 too early.

Mechanism: a faster window's whipsaw cost scales with sleeve beta. The prior NDX "adopt"
rested on the post-2017 NDX walk-forward (~9y, COVID-2020-dominated), where the single big
RV20 win (cutting 2020 DD) dominated. The only available LONG high-beta lens (QQQ proxy)
shows that over a full cycle the faster window does not clearly beat RV60 and re-enters
2008/2022 prematurely.

### RE-JUDGED NDX RV20 verdict: DOWNGRADE "adopt" -> **INCONCLUSIVE, lean KEEP-RV60 (V0)**

Weighing all three pieces of evidence now on the table:

1. **In-sample bootstrap CI includes 0** (RV20-V0 Calmar P=85%, never reached exclude-0). [prior]
2. **Clean-18y + post-2017 NDX walk-forward favored RV20** (monotone fast-dominance, plateau,
   episode-robust) -- but on a short, survivorship-biased-pre-2017, COVID-dominated sample. [prior]
3. **Extended high-beta lens (this study): the RV20 edge over RV60 vanishes (Calmar +0.009),
   whipsaw ~doubles, FP rate worsens, and RV20 surrenders the 2008/2022 crisis catches.** [new]

Net: the prior "adopt" was decisive ONLY because the long/older high-beta test was missing.
With it supplied, two of three pillars now point away from a clean adopt (bootstrap includes
0; ext high-beta edge is noise + extra whipsaw + lost crisis catches), and the one pillar
that favored RV20 is the shortest, most-contaminated sample. **The honest call is no longer
a clean adopt.** Recommend **KEEP RV60 (V0) as the NDX default**: over the extended high-beta
proxy it dodges 2008 and 2022 cleanly with HALF the whipsaw of RV20, and the RV20 advantage
never reached statistical significance. If RV20 is to be adopted, it needs a
**survivorship-clean NDX-100 extended return series** (not available here) to confirm the
post-2017 edge generalizes -- until then, RV20 for NDX is **inconclusive-needs-more**, and
the safe default is V0/RV60.

### Caveats / honesty guards

- PART B2 is a **QQQ proxy** for high-beta, NOT a survivorship-clean NDX-100 sleeve (QQQ
  proxy real data from ~1999; repo proxy backfilled to 1988; pre-2017 NDX-sleeve
  survivorship ~28% missing tickers is the original concern -- this proxy sidesteps but does
  not solve it). PART B2 is also **vol-gate-ONLY** (no trend/canary stack); the full NDX
  sleeve's trend filter may recover some of the 2008/2022 catches RV20 surrenders here, so
  B2 likely OVERSTATES standalone-gate fragility. Directional, not definitive.
- PART A uses Shiller monthly-average S&P for the trend leg but TRUE ^GSPC daily close for
  the vol gate (documented price-series mismatch); equity = Shiller monthly TR; defensive =
  3m T-bill. Single 18y sample.
- PART B1 is production close-to-close T+1 (10 bps/side); equity pre-1993 is ^GSPC price-only
  (no dividends); safe/cash/canary synthetic pre-1991/2000 (flagged in the source harness).
- Single historical samples throughout; no bootstrap CI re-run on the ext windows (point
  estimates only). t+1 implementation lag, point-in-time gate, no lookahead.
- Anchor reproduced exactly (CLEAN rv60 0.9936/0.7305/-13.60%) before any delta.
- EXPLORATION ONLY; no production/memo edits; no commit. No adoption without user confirmation.
