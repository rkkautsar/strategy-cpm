# BULL vol-gate variants: IMPLIED vol (VIX) / VVIX / implied-vs-realized hybrids vs symmetric RV gate

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL production BULL improvement; user decides adoption later (OOS-gated). Harness `research/bull_volgate_impliedvol.py`.

**Motivation.** Prior round (`research/bull_volgate_variants_findings.md`) showed downside/EWMA REALIZED-vol gates all UNDERPERFORM the symmetric RV60<RV252, because the symmetric gate's UPSIDE-sensitivity is load-bearing -- it front-runs the lagging trend filter in the 2018-Q4 and 2022 grinds. New idea: IMPLIED vol (VIX) is naturally ASYMMETRIC -- it spikes on fear, stays low in melt-ups -- so a VIX gate might avoid the 'de-risk into strength' whipsaw (the live OFF-at-SPY-highs) WITHOUT losing protection. Also test VVIX (vol-of-vol) and implied-vs-realized hybrids. Replace ONLY the vol-gate layer; canary (TIP 13612U>0) + trend (SPY 13612U>0) unchanged; safe = best{SHV,IEF} by 13612U.

**Already covered elsewhere (NOT repeated):** VIX term-structure VIX vs VIX3M -- `bull_strengthen_macro_findings.md` found REPLACE-rv lowers Sharpe; ADD-to-rv only improves 2020 DD (thin: VIX3M starts 2006-07).

**Variants (small principled set, NOT grid-tuned).**
- **V0 symmetric** (PROD): RV60 < RV252, RV = annualized std of SPY daily returns.
- **V1a VIX 21/252**: risk-on when VIX 21d MA < VIX 252d MA (1m vs 12m implied).
- **V1b VIX 63/252**: risk-on when VIX 63d MA < VIX 252d MA (3m vs 12m; RV60<RV252 analogue).
- **V2a VIX < 20**: risk-on when latest VIX < 20 (classic fixed level; THRESHOLD-TUNED -- flagged).
- **V2b VIX < 252d median**: risk-on when latest VIX < its trailing 252d median (adaptive threshold).
- **V3 VVIX < 252d MA**: risk-on when latest VVIX < its 252d MA (high vol-of-vol = tail risk -> de-risk; VVIX 2007+).
- **V4a VRP-panic**: risk-OFF when VIX > 1.5 * RV20 (annualized) -- blown-out variance-risk-premium / panic sign.
- **V4b CONFIRM (AND)**: risk-on when RV60<RV252 AND VIX < VIX 252d MA (implied confirms realized).

**Convention (canonical).** T+1 MOO exact (`mooex`, real auto_adjust opens), 10 bps/side, monthly month-end signal. Windows: clean 2008-05-30..2026-05-22 (18y, decisive lens); ext 1999-03-10..2026-05-22 (27y, partly proxy-backed pre-2006-08). Metrics from production `perf_metrics`.

**Data.** ^VIX (yfinance, 1990-01-02..2026-05-29); ^VVIX (yfinance/CBOE, 2007-01-03..2026-05-29). VVIX-limited variants (V3_vvix_ma_252) run risk-on pre-2007 -> read CLEAN only; ext is degraded.

## 0. Anchor gate

BULL V0 symmetric-gate clean Sharpe **1.1005** / MaxDD **-13.35%** vs anchor ~1.1005 / -13.35% -> **CONFIRMED**.

## 1. BULL standalone sleeve metrics -- clean 18y

| Variant | CAGR | Vol | Sharpe | Excess Sharpe | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 10.93% | 9.90% | 1.1005 | 0.9661 | -13.35% | 0.8189 | 3.0714 |
| V1a VIX 21d<252d MA | 8.06% | 10.15% | 0.8174 | 0.6862 | -17.31% | 0.4655 | 1.8141 |
| V1b VIX 63d<252d MA | 7.34% | 10.47% | 0.7317 | 0.6044 | -17.31% | 0.4241 | 1.4299 |
| V2a VIX < 20 (fixed) | 7.13% | 9.38% | 0.7844 | 0.6424 | -14.08% | 0.5066 | 1.3311 |
| V2b VIX < 252d median | 5.89% | 8.94% | 0.6872 | 0.5388 | -15.48% | 0.3802 | 1.0941 |
| V3 VVIX < 252d MA | 7.43% | 8.89% | 0.8542 | 0.7051 | -14.79% | 0.5026 | 1.6190 |
| V4a VRP risk-off VIX>1.5*RV20 | 6.62% | 9.14% | 0.7494 | 0.6044 | -23.76% | 0.2785 | 0.8719 |
| V4b CONFIRM RV60<252 AND VIX<MA252 | 7.35% | 9.07% | 0.8302 | 0.6838 | -12.53% | 0.5866 | 1.9426 |

### Ext 27y (partly proxy-backed; VVIX variants degraded pre-2007)

| Variant | CAGR | Vol | Sharpe | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 9.48% | 9.30% | 1.0207 | -13.35% | 0.7101 |
| V1a VIX 21d<252d MA | 8.17% | 9.50% | 0.8738 | -17.31% | 0.4719 |
| V1b VIX 63d<252d MA | 7.73% | 9.73% | 0.8144 | -17.31% | 0.4469 |
| V2a VIX < 20 (fixed) | 7.21% | 9.19% | 0.8040 | -14.08% | 0.5122 |
| V2b VIX < 252d median | 6.33% | 8.61% | 0.7562 | -15.48% | 0.4092 |
| V3 VVIX < 252d MA (VVIX-deg) | 7.98% | 9.05% | 0.8940 | -14.79% | 0.5397 |
| V4a VRP risk-off VIX>1.5*RV20 | 6.59% | 8.99% | 0.7549 | -23.76% | 0.2775 |
| V4b CONFIRM RV60<252 AND VIX<MA252 | 6.93% | 8.65% | 0.8177 | -12.53% | 0.5534 |

### Delta vs V0 (clean): Sharpe / Calmar / MaxDD / CAGR

| Variant | dSharpe | dCalmar | dMaxDD (pp) | dCAGR (pp) |
|---|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | +0.0000 | +0.0000 | +0.00 | +0.00 |
| V1a VIX 21d<252d MA | -0.2832 | -0.3533 | +3.96 | -2.87 |
| V1b VIX 63d<252d MA | -0.3689 | -0.3948 | +3.96 | -3.59 |
| V2a VIX < 20 (fixed) | -0.3161 | -0.3123 | +0.74 | -3.80 |
| V2b VIX < 252d median | -0.4133 | -0.4387 | +2.13 | -5.04 |
| V3 VVIX < 252d MA | -0.2464 | -0.3162 | +1.45 | -3.49 |
| V4a VRP risk-off VIX>1.5*RV20 | -0.3511 | -0.5404 | +10.41 | -4.31 |
| V4b CONFIRM RV60<252 AND VIX<MA252 | -0.2704 | -0.2323 | -0.82 | -3.58 |

*dMaxDD>0 = deeper drawdown (worse). dCAGR>0 = higher return.*

## 2. Whipsaw + upside-vol-de-risk (clean 18y monthly signals)

Vol-gate de-risk month = canary_ok AND trend_ok AND NOT vol_ok (vol gate is the SOLE binding leg). False de-risk = governed next-month SPY return > 0. Upside-vol-de-risk = de-risk while trailing 63d SPY return is POSITIVE (the de-risk-into-strength failure mode).

| Variant | de-risk months | false-pos | false-pos rate | upside-derisk | upside rate | mean SPY next | mean trail63 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 32 | 19 | 59.4% | 22 | 68.8% | +0.50% | +2.38% |
| V1a VIX 21d<252d MA | 35 | 23 | 65.7% | 25 | 71.4% | +1.42% | +3.67% |
| V1b VIX 63d<252d MA | 37 | 26 | 70.3% | 28 | 75.7% | +1.81% | +4.10% |
| V2a VIX < 20 (fixed) | 35 | 25 | 71.4% | 27 | 77.1% | +2.15% | +5.20% |
| V2b VIX < 252d median | 53 | 38 | 71.7% | 40 | 75.5% | +1.67% | +3.95% |
| V3 VVIX < 252d MA | 54 | 36 | 66.7% | 44 | 81.5% | +1.46% | +4.59% |
| V4a VRP risk-off VIX>1.5*RV20 | 74 | 52 | 70.3% | 67 | 90.5% | +0.99% | +6.39% |
| V4b CONFIRM RV60<252 AND VIX<MA252 | 51 | 34 | 66.7% | 37 | 72.5% | +1.35% | +3.83% |

*Lower false-pos rate and FEWER upside-vol-de-risks = the variant punishes upside vol less.*

## 3. Per-crisis protection (BULL sleeve MaxDD / total return in window)

Crash protection (2008, 2020) and grind catches (2018-Q4, 2022) must be KEPT. Each cell = sleeve MaxDD / total return over the window.

| Variant | 2008 GFC DD/Ret | 2018 Q4 DD/Ret | 2020 COVID DD/Ret | 2022 bear DD/Ret |
|---|---|---|---|---|
| V0 symmetric RV60<RV252 (PROD) | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| V1a VIX 21d<252d MA | -12.09% / 6.57% | -2.14% / 10.53% | -13.35% / -3.82% | -0.30% / 1.03% |
| V1b VIX 63d<252d MA | -12.09% / 6.57% | -10.10% / 6.67% | -13.35% / -3.82% | -9.73% / -4.35% |
| V2a VIX < 20 (fixed) | -10.40% / 8.66% | -10.10% / 10.42% | -13.35% / -3.82% | -9.73% / -4.81% |
| V2b VIX < 252d median | -12.09% / 6.57% | -2.17% / -0.87% | -4.68% / 8.03% | -9.73% / -4.81% |
| V3 VVIX < 252d MA | -12.09% / 6.57% | -2.17% / 2.58% | -6.99% / 12.99% | -9.73% / -4.81% |
| V4a VRP risk-off VIX>1.5*RV20 | -12.09% / 6.57% | -4.05% / 0.26% | -6.99% / 20.28% | -10.11% / -0.82% |
| V4b CONFIRM RV60<252 AND VIX<MA252 | -12.09% / 6.57% | -2.14% / 9.91% | -4.68% / 8.03% | -0.30% / 0.94% |

*Windows: 2008 GFC 2008-05-30..2009-06-30; 2018 Q4 2018-01-01..2018-12-31; 2020 COVID 2020-01-01..2020-06-30; 2022 bear 2022-01-01..2022-12-31.*

## 4. Live current state (latest signal month)

Is each variant ON (risk-on, 100% SPY) or OFF (de-risked to safe) right now? Baseline V0 is OFF at SPY highs (RV60 inflated by the recovery rally) -- the de-risk-into-strength concern. vol short/long are the gate's own comparands (VIX MA / threshold / VVIX, all shown /100).

| Variant | signal date | canary | trend | vol_ok | risk-on | gate short | gate long | trail63 |
|---|---|:--:|:--:|:--:|:--:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 2026-05-22 | Y | Y | n | OFF | 14.59 | 12.43 | +6.83% |
| V1a VIX 21d<252d MA | 2026-05-22 | Y | Y | Y | ON | 17.68 | 18.20 | +6.83% |
| V1b VIX 63d<252d MA | 2026-05-22 | Y | Y | n | OFF | 21.21 | 18.20 | +6.83% |
| V2a VIX < 20 (fixed) | 2026-05-22 | Y | Y | Y | ON | 16.70 | 20.00 | +6.83% |
| V2b VIX < 252d median | 2026-05-22 | Y | Y | Y | ON | 16.70 | 17.24 | +6.83% |
| V3 VVIX < 252d MA | 2026-05-22 | Y | Y | Y | ON | 91.16 | 101.05 | +6.83% |
| V4a VRP risk-off VIX>1.5*RV20 | 2026-05-22 | Y | Y | n | OFF | 16.70 | 15.37 | +6.83% |
| V4b CONFIRM RV60<252 AND VIX<MA252 | 2026-05-22 | Y | Y | n | OFF | 16.70 | 18.20 | +6.83% |

*gate short/long are in vol points (VIX-style): e.g. V0 = RV60 vs RV252; V1 = VIX MA fast vs slow; V2 = VIX vs threshold/median; V3 = VVIX vs MA; V4a = VIX vs 1.5*RV20; V4b = VIX vs VIX-MA (AND rv).*

## 5. Annualized turnover (clean 18y, two-way, monthly state flips)

| Variant | Annualized turnover |
|---|---:|
| V0 symmetric RV60<RV252 (PROD) | 378.3% |
| V1a VIX 21d<252d MA | 456.1% |
| V1b VIX 63d<252d MA | 356.0% |
| V2a VIX < 20 (fixed) | 478.4% |
| V2b VIX < 252d median | 634.2% |
| V3 VVIX < 252d MA | 656.4% |
| V4a VRP risk-off VIX>1.5*RV20 | 956.8% |
| V4b CONFIRM RV60<252 AND VIX<MA252 | 578.5% |

## 6. VERDICT

Candidate scorecard (clean 18y). Crash-protection = 2008 & 2020 DD not >2pp deeper than V0; grind-protection = 2018-Q4 & 2022 DD not >3pp deeper than V0 (the slow-bear catches the task warns not to trade away):

| Variant | Sharpe | Calmar | MaxDD | CAGR | false-pos | upside-derisk | keeps crash? | keeps grind? | live now |
|---|---:|---:|---:|---:|---:|---:|:--:|:--:|:--:|
| V0 symmetric RV60<RV252 (PROD) | 1.1005 | 0.8189 | -13.35% | 10.93% | 59.4% | 68.8% | Y | Y | OFF |
| V1a VIX 21d<252d MA | 0.8174 | 0.4655 | -17.31% | 8.06% | 65.7% | 71.4% | Y | Y | ON |
| V1b VIX 63d<252d MA | 0.7317 | 0.4241 | -17.31% | 7.34% | 70.3% | 75.7% | Y | NO | OFF |
| V2a VIX < 20 (fixed) | 0.7844 | 0.5066 | -14.08% | 7.13% | 71.4% | 77.1% | Y | NO | ON |
| V2b VIX < 252d median | 0.6872 | 0.3802 | -15.48% | 5.89% | 71.7% | 75.5% | Y | NO | ON |
| V3 VVIX < 252d MA | 0.8542 | 0.5026 | -14.79% | 7.43% | 66.7% | 81.5% | Y | NO | ON |
| V4a VRP risk-off VIX>1.5*RV20 | 0.7494 | 0.2785 | -23.76% | 6.62% | 70.3% | 90.5% | Y | NO | OFF |
| V4b CONFIRM RV60<252 AND VIX<MA252 | 0.8302 | 0.5866 | -12.53% | 7.35% | 66.7% | 72.5% | Y | Y | OFF |

**NO implied-vol / VVIX / hybrid variant BEATS the symmetric V0** on the full objective (higher Sharpe AND Calmar, keep 2008/2020 crash + 2018-Q4/2022 grind catches, not raise whipsaw). Same conclusion as the prior realized-vol round: V0 (Sharpe 1.1005, Calmar 0.8189) is not beaten.

No variant even cuts the upside-de-risk rate while keeping both crash and grind protection.

**On the live de-risk-into-strength concern.** V0 is **OFF** right now (RV60 14.59 vs RV252 12.43, trailing-63d +6.83%). Variants that would be ON now: V1a VIX 21d<252d MA, V2a VIX < 20 (fixed), V2b VIX < 252d median, V3 VVIX < 252d MA. A live ON flip is necessary but not sufficient -- the 18y backtest decides whether re-risking into rallies pays.

**Overfitting / OOS caveats.** MA windows (21/63/252), the VIX<20 level, the 1.5x VRP ratio and the AND-confirm are a small principled set, NOT grid-tuned -- but ANY gate swap mined on the same 18y sample risks in-sample selection. V2a (VIX<20) is the most threshold-exposed (a round number); V2b (rolling median) is adaptive but still a level call. VVIX history starts 2007 so V3 has ~2 real crashes (2008 partial, 2020) + 2022 in the clean window -- THIN tail evidence; treat VVIX results as suggestive only. This would be a LIVE PRODUCTION CHANGE: requires OOS / walk-forward validation (freeze pre-2015, test 2015+) and a paired bootstrap on the Sharpe/Calmar deltas before adoption.

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.
- Only the vol-gate layer changes; canary (TIP 13612U>0), trend (SPY 13612U>0) and safe (best{SHV,IEF} by 13612U) held at production values, so the vol gate is the single differentiator.
- Sleeves run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side, via exec_lag_moo_validation_2026_05_30._segment_returns_conv.
- VIX/VVIX gates use only data up to the month-end signal date (no lookahead); VIX in pct points, reported /100 as decimal for the live table.
- VIX term-structure (VIX vs VIX3M) NOT re-tested here -- see bull_strengthen_macro_findings.md.
- Whipsaw / upside-de-risk / live state use a monthly month-grain calendar (signal -> following calendar-month SPY close-to-close return); the daily sleeve backtest uses mooex. Trailing 63d return is the rally proxy.
- VVIX (2007+) limits V3 to the clean 18y window; ext pre-2007 runs risk-on (degraded) and is flagged. Clean 18y is the decisive lens.
