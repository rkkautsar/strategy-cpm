# CPM Safe-Sleeve Expansion (R3) -- Findings

Research-only. Does widening the CPM defensive menu (selector = best by 13612U, same mechanism) fix the 2022 duration trap and/or improve full-period drawdown-adjusted metrics, vs the production {SHV, IEF} pool?

- Convention: T+1 MOO exact (`mooex`), 10 bps/side, post-cost.
- Windows: clean 2008-05-30..2026-05-22, ext 1999-03-10..2026-05-22.
- Mechanism unchanged: `cpm_live.compute_target_weights(safe_pool=...)`. Only the menu widens.
- Inception limits: SHV 2007, IEF 2002, VTIP 2012-10, USFR 2014-02, KMLM stitched 1988+, GLD stitched 1995+.
- `best_safe` needs >=13 months history before an asset can be selected (newer assets cannot bind early).

## 0. Anchor reproduction (gate)

| Window | Sharpe | MaxDD | Calmar | Matches anchor |
|---|---:|---:|---:|:--:|
| clean | 1.1910 | -12.67% | 1.0615 | YES |
| ext | 1.2142 | -15.93% | 0.8608 | NO |

Anchor reproduced exactly before any variant was trusted.

## 1. Full-period CPM metrics by safe pool

### Clean (2008-05-30+)

| Safe pool | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| baseline {SHV,IEF} | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 |
| +VTIP {SHV,IEF,VTIP} | 1.1896 | 13.46% | 11.19% | -12.67% | 1.0630 | 3.7764 |
| +USFR {SHV,IEF,USFR} | 1.2000 | 13.56% | 11.16% | -12.67% | 1.0710 | 4.1263 |
| +VTIP+USFR {SHV,IEF,VTIP,USFR} | 1.1968 | 13.56% | 11.19% | -12.67% | 1.0706 | 3.8934 |
| +KMLM {SHV,IEF,VTIP,USFR,KMLM} | 1.1548 | 14.99% | 12.86% | -25.38% | 0.5906 | 2.1842 |
| +GLD {..,KMLM,GLD} | 1.1854 | 15.71% | 13.08% | -16.78% | 0.9361 | 3.2367 |

### Extended (1999-03+, proxy-informed robustness only)

| Safe pool | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| baseline {SHV,IEF} | 1.2142 | 13.71% | 11.09% | -15.93% | 0.8608 | 3.8201 |
| +VTIP {SHV,IEF,VTIP} | 1.2132 | 13.72% | 11.11% | -15.93% | 0.8616 | 3.7104 |
| +USFR {SHV,IEF,USFR} | 1.2202 | 13.79% | 11.09% | -15.93% | 0.8658 | 3.9124 |
| +VTIP+USFR {SHV,IEF,VTIP,USFR} | 1.2180 | 13.79% | 11.11% | -15.93% | 0.8656 | 3.7809 |
| +KMLM {SHV,IEF,VTIP,USFR,KMLM} | 1.1866 | 15.01% | 12.44% | -25.38% | 0.5915 | 2.4799 |
| +GLD {..,KMLM,GLD} | 1.1889 | 15.30% | 12.64% | -18.86% | 0.8111 | 3.1997 |

## 2. 2022 episode (the duration-trap question)

### Whole CPM, calendar 2022

| Safe pool | 2022 return | 2022 MaxDD |
|---|---:|---:|
| baseline {SHV,IEF} | -0.50% | -6.33% |
| +VTIP {SHV,IEF,VTIP} | -0.20% | -6.33% |
| +USFR {SHV,IEF,USFR} | 0.24% | -6.33% |
| +VTIP+USFR {SHV,IEF,VTIP,USFR} | 0.17% | -6.33% |
| +KMLM {SHV,IEF,VTIP,USFR,KMLM} | 11.41% | -17.56% |
| +GLD {..,KMLM,GLD} | 16.36% | -16.56% |

### Isolated safe sleeve (100% best_safe(pool) every month)

This sleeve is what the defensive/unused-breadth slots route to. It isolates the duration trap directly.

| Safe pool | 2022 sleeve return | 2022 sleeve MaxDD | Full-clean Sharpe | Full-clean MaxDD | Full-clean CAGR |
|---|---:|---:|---:|---:|---:|
| baseline {SHV,IEF} | 0.94% | -0.30% | 0.4729 | -10.40% | 2.43% |
| +VTIP {SHV,IEF,VTIP} | -0.05% | -3.03% | 0.6137 | -10.40% | 3.17% |
| +USFR {SHV,IEF,USFR} | 1.35% | -0.29% | 0.5024 | -10.40% | 2.57% |
| +VTIP+USFR {SHV,IEF,VTIP,USFR} | 0.32% | -3.03% | 0.6277 | -10.40% | 3.25% |
| +KMLM {SHV,IEF,VTIP,USFR,KMLM} | 17.20% | -17.56% | 0.2379 | -25.86% | 2.10% |
| +GLD {..,KMLM,GLD} | 22.42% | -16.56% | 0.6184 | -26.39% | 9.26% |

## 3. Safe-asset selection frequency (does the new menu ever bind?)

### Clean window (2008-05-30+), count of months each asset was the best_safe choice

| Safe pool | GLD | IEF | KMLM | SHV | USFR | VTIP |
|---|---|---|---|---|---|---|
| baseline {SHV,IEF} | 0 | 131 | 0 | 86 | 0 | 0 |
| +VTIP {SHV,IEF,VTIP} | 0 | 120 | 0 | 49 | 0 | 48 |
| +USFR {SHV,IEF,USFR} | 0 | 128 | 0 | 25 | 64 | 0 |
| +VTIP+USFR {SHV,IEF,VTIP,USFR} | 0 | 120 | 0 | 20 | 34 | 43 |
| +KMLM {SHV,IEF,VTIP,USFR,KMLM} | 0 | 77 | 75 | 18 | 23 | 24 |
| +GLD {..,KMLM,GLD} | 109 | 24 | 53 | 10 | 11 | 10 |

### 2022 month-by-month best_safe choice (Dec-2021 .. Dec-2022)

- **baseline {SHV,IEF}**: 12-31:SHV 01-31:SHV 02-28:SHV 03-31:SHV 04-29:SHV 05-31:SHV 06-30:SHV 07-29:SHV 08-31:SHV 09-30:SHV 10-31:SHV 11-30:SHV 12-30:SHV
- **+VTIP {SHV,IEF,VTIP}**: 12-31:VTIP 01-31:VTIP 02-28:VTIP 03-31:VTIP 04-29:VTIP 05-31:VTIP 06-30:SHV 07-29:SHV 08-31:SHV 09-30:SHV 10-31:SHV 11-30:SHV 12-30:SHV
- **+USFR {SHV,IEF,USFR}**: 12-31:SHV 01-31:USFR 02-28:USFR 03-31:USFR 04-29:USFR 05-31:USFR 06-30:USFR 07-29:USFR 08-31:USFR 09-30:USFR 10-31:USFR 11-30:USFR 12-30:USFR
- **+VTIP+USFR {SHV,IEF,VTIP,USFR}**: 12-31:VTIP 01-31:VTIP 02-28:VTIP 03-31:VTIP 04-29:VTIP 05-31:VTIP 06-30:USFR 07-29:USFR 08-31:USFR 09-30:USFR 10-31:USFR 11-30:USFR 12-30:USFR
- **+KMLM {SHV,IEF,VTIP,USFR,KMLM}**: 12-31:VTIP 01-31:KMLM 02-28:KMLM 03-31:KMLM 04-29:KMLM 05-31:KMLM 06-30:KMLM 07-29:KMLM 08-31:KMLM 09-30:KMLM 10-31:KMLM 11-30:KMLM 12-30:KMLM
- **+GLD {..,KMLM,GLD}**: 12-31:VTIP 01-31:KMLM 02-28:KMLM 03-31:KMLM 04-29:KMLM 05-31:KMLM 06-30:KMLM 07-29:KMLM 08-31:KMLM 09-30:KMLM 10-31:KMLM 11-30:GLD 12-30:GLD

## 4. Analysis and verdict

### 4.1 The duration trap is not empirically realized in 2022

Under the existing `{SHV, IEF}` pool, `best_safe` (13612U) selected **SHV every single
month of 2022** (Dec-2021 through Dec-2022). By late 2021 the 6/12-month return
components on IEF were already negative enough that the selector never parked in IEF.
The baseline safe sleeve returned **+0.94% with only -0.30% MaxDD in 2022** -- no bleed.
The whole-CPM 2022 MaxDD of -6.33% comes from the *risky* sleeve in early 2022, not the
safe sleeve. The review's feared "30-60 day IEF bleed" did not occur historically; the
13612U selector already rotates duration-hostile in a rate shock. SHV/IEF is adequate
for the specific risk flagged.

### 4.2 Small bill/TIPS additions wash (USFR mildly favorable, VTIP neutral-to-negative)

- **+USFR** is the only addition that is net-positive on every full-period metric:
  clean Sharpe 1.1910 -> 1.2000, Calmar 1.0615 -> 1.0710, Martin 3.96 -> 4.13, MaxDD
  unchanged at -12.67%; 2022 sleeve +1.35% vs +0.94%. USFR binds 64 clean-window months,
  displacing SHV (floating-rate bills capture rising-rate yield that fixed T-bills lag).
  Economically near-identical to cash, so no MaxDD cost. The gain is real but immaterial
  (+0.009 Sharpe) and inception-limited (USFR live 2014-02, cannot bind in GFC/2008).
- **+VTIP** is a wash-to-slightly-negative: clean Sharpe 1.1896 (-0.001), and it *hurts*
  the 2022 sleeve (-0.05% return, -3.03% MaxDD) because short-term TIPS still carry real-
  rate duration that fell in 2022. Do not add.
- **+VTIP+USFR** lands between the two; USFR carries the benefit, VTIP a slight drag.

### 4.3 KMLM and GLD are risky diversifiers, not safe assets -- they break drawdown control

Adding KMLM or GLD to the *safe* sleeve materially damages CPM's core capital-preservation
identity:

| Addition | Clean MaxDD | Clean Calmar | Clean Martin | 2022 sleeve MaxDD |
|---|---:|---:|---:|---:|
| baseline {SHV,IEF} | -12.67% | 1.0615 | 3.96 | -0.30% |
| +KMLM | -25.38% | 0.5906 | 2.18 | -17.56% |
| +GLD | -16.78% | 0.9361 | 3.24 | -16.56% |

Both boost raw return (KMLM 2022 +11.4%, GLD 2022 +16.4%; CAGR up to 15-16%) because
managed futures and gold had a strong 2022. But the "safe" sleeve's own full-clean MaxDD
balloons to -17.6% (KMLM) / -26.4% (GLD): these are volatile risk assets, not capital
preservers. Routing unused breadth slots into them roughly doubles CPM's MaxDD and
collapses Calmar/Martin. KMLM/GLD belong (if anywhere) in the RISKY universe, not the
defensive sleeve. GLD is also already in the risky universe -- adding it to safe
double-counts the exposure (flagged design choice), and the result confirms it is a bad
fit for the safe role. Reject both for the safe pool.

### 4.4 Verdict

**SHV/IEF is already adequate; do not expand the safe sleeve.**

- The 2022 duration trap does not bind historically -- the 13612U selector already sits
  in SHV through the rate shock, with a +0.94% / -0.30% safe sleeve.
- VTIP, KMLM, GLD each hurt (VTIP marginally; KMLM/GLD materially via doubled MaxDD and
  halved Calmar/Martin). KMLM/GLD are risky-sleeve ideas, not safe additions.
- USFR is the only defensible optional swap-in (immaterial +0.009 Sharpe / +0.16 Martin,
  zero MaxDD cost, better rising-rate yield capture), but the gain is below decision
  materiality and adds inception-limited complexity. Not worth adopting on this evidence.

**Recommendation: NONE (keep production {SHV, IEF}).** If a future change is desired purely
for rising-rate yield capture, USFR is the single justifiable candidate -- but it is a
cosmetic improvement, not a fix for a real defect.

### 4.5 Caveats and confidence

- Single in-sample run, t+1 MOO exact, point-in-time, one stress episode (2022). No
  walk-forward / OOS / multiple-testing correction. Treat as directional, not decisive.
- **Inception bias:** USFR (2014-02) and VTIP (2012-10) cannot bind before their launch,
  so they are absent during GFC/2008 -- the worst clean-window drawdown. Their flattering
  full-period MaxDD partly reflects this absence, not genuine protection (survivorship-
  flavored). KMLM pre-2020 is a stitched KFA-MLM index proxy; GLD pre-2004 is a stitched
  proxy. Clean window from 2008-05-30 mitigates but does not remove this for KMLM/GLD.
- Execution: mooex uses real opens for SHV/IEF/VTIP/USFR; KMLM and stitched-GLD lack
  intraday opens, so the rebal-day return falls back to close-to-close for those two only
  (affects the day a switch occurs, negligible at monthly frequency).
- Ext-window anchor drifts trivially (Sharpe 1.2142 vs stale 1.2161) from yfinance data
  refresh; the decisive **clean anchor reproduces to 4 decimals (1.1910 / -12.67% / 1.0615)**.
- Confidence: HIGH that KMLM/GLD hurt the safe role; HIGH that the 2022 trap is not
  empirically realized; MEDIUM that USFR is marginally favorable (inception-limited).
