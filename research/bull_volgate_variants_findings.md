# BULL vol-gate variants: downside-only / EWMA vs symmetric RV gate

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL production BULL improvement; user decides adoption later. Harness `research/bull_volgate_variants.py`.

**Motivation.** Production vol gate is SYMMETRIC: risk-on when RV60 < RV252 (annualized std of SPY daily returns, counting UP and DOWN vol identically). A sharp RALLY inflates RV60 so the gate can DE-RISK INTO STRENGTH (the likely current SPY-at-highs OFF state). It also whipsaws (~59% false-positive de-risks). Test whether a DOWNSIDE-only or EWMA vol gate fixes this WITHOUT losing crash protection. Replace ONLY the vol-gate layer; canary (TIP 13612U>0) + trend (SPY 13612U>0) unchanged; safe = best{SHV,IEF} by 13612U.

**Variants (small principled set, NOT grid-tuned).**
- **V0 symmetric** (PROD): RV60 < RV252, RV = annualized std of daily returns.
- **V1 downside**: dRV = sqrt(mean(min(r,0)^2))*sqrt(252) over 60 vs 252d; ON when dRV60 < dRV252.
- **V2a EWMA 0.94/0.99**: RiskMetrics short lambda=0.94 (HL 11.2d) vs long lambda=0.99 (HL 69.0d); ON when ewma_short < ewma_long.
- **V2b EWMA 0.97/0.99**: short lambda=0.97 (HL 22.8d, ~60d-window com) vs long lambda=0.99 (HL 69.0d); ON when ewma_short < ewma_long.
- **V3 downside-EWMA 0.97/0.99**: EWMA on downside semi-variance (min(r,0)^2), short lambda=0.97 vs long lambda=0.99; ON when short < long.

**Convention (canonical).** T+1 MOO exact (`mooex`, real auto_adjust opens), 10 bps/side, monthly month-end signal. Windows: clean 2008-05-30..2026-05-22 (18y); ext 1999-03-10..2026-05-22 (27y, partly proxy-backed pre-2006-08). Metrics from production `perf_metrics`.

## 0. Anchor gate

BULL V0 symmetric-gate clean Sharpe **1.1005** / MaxDD **-13.35%** vs anchor ~1.1005 / -13.35% -> **CONFIRMED**.

## 1. BULL standalone sleeve metrics -- clean 18y

| Variant | CAGR | Vol | Sharpe | Excess Sharpe | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 10.93% | 9.90% | 1.1005 | 0.9661 | -13.35% | 0.8189 | 3.0714 |
| V1 downside semi-dev 60<252 | 10.01% | 10.05% | 1.0036 | 0.8710 | -13.35% | 0.7503 | 2.4096 |
| V2a EWMA lam 0.94<0.99 | 9.87% | 10.14% | 0.9823 | 0.8511 | -14.54% | 0.6787 | 2.4643 |
| V2b EWMA lam 0.97<0.99 | 10.07% | 10.03% | 1.0101 | 0.8775 | -14.54% | 0.6926 | 2.6488 |
| V3 downside-EWMA 0.97<0.99 | 8.52% | 10.21% | 0.8551 | 0.7247 | -14.54% | 0.5859 | 1.8282 |

### Ext 27y (partly proxy-backed)

| Variant | CAGR | Vol | Sharpe | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 9.48% | 9.30% | 1.0207 | -13.35% | 0.7101 |
| V1 downside semi-dev 60<252 | 8.93% | 9.30% | 0.9668 | -13.35% | 0.6694 |
| V2a EWMA lam 0.94<0.99 | 9.04% | 9.61% | 0.9486 | -14.54% | 0.6216 |
| V2b EWMA lam 0.97<0.99 | 9.29% | 9.43% | 0.9891 | -14.54% | 0.6385 |
| V3 downside-EWMA 0.97<0.99 | 8.20% | 9.53% | 0.8751 | -14.54% | 0.5640 |

### Delta vs V0 (clean): Sharpe / Calmar / MaxDD / CAGR

| Variant | dSharpe | dCalmar | dMaxDD (pp) | dCAGR (pp) |
|---|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | +0.0000 | +0.0000 | +0.00 | +0.00 |
| V1 downside semi-dev 60<252 | -0.0970 | -0.0686 | -0.00 | -0.92 |
| V2a EWMA lam 0.94<0.99 | -0.1183 | -0.1401 | +1.20 | -1.06 |
| V2b EWMA lam 0.97<0.99 | -0.0905 | -0.1262 | +1.20 | -0.85 |
| V3 downside-EWMA 0.97<0.99 | -0.2454 | -0.2330 | +1.20 | -2.41 |

*dMaxDD>0 = deeper drawdown (worse). dCAGR>0 = higher return.*

## 2. Whipsaw + upside-vol-de-risk (clean 18y monthly signals)

Vol-gate de-risk month = canary_ok AND trend_ok AND NOT vol_ok (vol gate is the SOLE binding leg). False de-risk = governed next-month SPY return > 0. Upside-vol-de-risk = de-risk while trailing 63d SPY return is POSITIVE (the de-risk-into-strength failure mode).

| Variant | de-risk months | false-pos | false-pos rate | upside-derisk | upside rate | mean SPY next | mean trail63 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 32 | 19 | 59.4% | 22 | 68.8% | +0.50% | +2.38% |
| V1 downside semi-dev 60<252 | 37 | 23 | 62.2% | 26 | 70.3% | +0.85% | +1.71% |
| V2a EWMA lam 0.94<0.99 | 27 | 17 | 63.0% | 17 | 63.0% | +0.76% | +1.23% |
| V2b EWMA lam 0.97<0.99 | 28 | 17 | 60.7% | 18 | 64.3% | +0.58% | +1.83% |
| V3 downside-EWMA 0.97<0.99 | 28 | 20 | 71.4% | 18 | 64.3% | +1.38% | +1.09% |

*Lower false-pos rate and FEWER upside-vol-de-risks = the variant punishes upside vol less.*

## 3. Per-crisis protection (BULL sleeve MaxDD / total return in window)

Crash protection must be KEPT. Each cell = sleeve MaxDD / total return over the window.

| Variant | 2008 GFC DD/Ret | 2018 Q4 DD/Ret | 2020 COVID DD/Ret | 2022 bear DD/Ret |
|---|---|---|---|---|
| V0 symmetric RV60<RV252 (PROD) | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| V1 downside semi-dev 60<252 | -12.09% / 6.57% | -10.10% / 11.30% | -13.35% / -3.82% | -9.73% / -4.81% |
| V2a EWMA lam 0.94<0.99 | -12.09% / 6.57% | -3.00% / 14.43% | -13.35% / -2.29% | -0.30% / 0.94% |
| V2b EWMA lam 0.97<0.99 | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 1.03% |
| V3 downside-EWMA 0.97<0.99 | -12.09% / 6.57% | -10.10% / 11.30% | -13.35% / -3.82% | -9.73% / -4.81% |

*Windows: 2008 GFC 2008-05-30..2009-06-30; 2018 Q4 2018-01-01..2018-12-31; 2020 COVID 2020-01-01..2020-06-30; 2022 bear 2022-01-01..2022-12-31.*

## 4. Live current state (latest signal month)

Is each variant ON (risk-on, 100% SPY) or OFF (de-risked to safe) right now? Baseline V0 is expected OFF at SPY highs (RV60 inflated by the recovery rally).

| Variant | signal date | canary | trend | vol_ok | risk-on | vol short | vol long | trail63 |
|---|---|:--:|:--:|:--:|:--:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 2026-05-22 | Y | Y | n | OFF | 14.59% | 12.43% | +6.83% |
| V1 downside semi-dev 60<252 | 2026-05-22 | Y | Y | n | OFF | 8.84% | 7.94% | +6.83% |
| V2a EWMA lam 0.94<0.99 | 2026-05-22 | Y | Y | Y | ON | 13.58% | 14.58% | +6.83% |
| V2b EWMA lam 0.97<0.99 | 2026-05-22 | Y | Y | Y | ON | 14.10% | 14.58% | +6.83% |
| V3 downside-EWMA 0.97<0.99 | 2026-05-22 | Y | Y | Y | ON | 7.88% | 9.33% | +6.83% |

## 5. Annualized turnover (clean 18y, two-way, monthly state flips)

| Variant | Annualized turnover |
|---|---:|
| V0 symmetric RV60<RV252 (PROD) | 378.3% |
| V1 downside semi-dev 60<252 | 422.8% |
| V2a EWMA lam 0.94<0.99 | 500.6% |
| V2b EWMA lam 0.97<0.99 | 456.1% |
| V3 downside-EWMA 0.97<0.99 | 522.9% |

## 6. VERDICT

Candidate scorecard (clean 18y). Crash-protection = 2008 & 2020 DD not >2pp deeper than V0; grind-protection = 2018-Q4 & 2022 DD not >3pp deeper than V0 (the slow-bear catches the task warns not to trade away):

| Variant | Sharpe | Calmar | MaxDD | CAGR | false-pos | upside-derisk | keeps crash? | keeps grind? |
|---|---:|---:|---:|---:|---:|---:|:--:|:--:|
| V0 symmetric RV60<RV252 (PROD) | 1.1005 | 0.8189 | -13.35% | 10.93% | 59.4% | 68.8% | Y | Y |
| V1 downside semi-dev 60<252 | 1.0036 | 0.7503 | -13.35% | 10.01% | 62.2% | 70.3% | Y | NO |
| V2a EWMA lam 0.94<0.99 | 0.9823 | 0.6787 | -14.54% | 9.87% | 63.0% | 63.0% | Y | Y |
| V2b EWMA lam 0.97<0.99 | 1.0101 | 0.6926 | -14.54% | 10.07% | 60.7% | 64.3% | Y | Y |
| V3 downside-EWMA 0.97<0.99 | 0.8551 | 0.5859 | -14.54% | 8.52% | 71.4% | 64.3% | Y | NO |

**Key failure mode -- downside gates trade away the 2018/2022 grind catches.** The DOWNSIDE variants (V1, V3) de-risk LESS in slow grinds (they wait for realized DOWN-vol, which lags a steady bleed), so they hold SPY through 2018-Q4 and 2022: BULL 2018-Q4 DD blows out to -10.10% (V0 -2.14%) and 2022 DD to -9.73% (V0 -0.30%). This is exactly the catch the task says not to lose -- so the downside-only premise BACKFIRES here: the symmetric gate's 'upside punishment' is also what front-runs the lagging trend filter in grinds.

**Best non-baseline variant (keeps crash AND grind protection AND reduces upside-vol-de-risk): V2b EWMA lam 0.97<0.99.** Clean Sharpe 1.0101 vs V0 1.1005 (-0.0905); Calmar 0.6926 vs 0.8189; upside-de-risk 64.3% vs V0 68.8%; false-pos 60.7% vs V0 59.4%. NOTE: it still TRAILS V0 on every headline risk-adjusted metric -- it is the 'least bad' alternative, not an improvement.

**On the live de-risk-into-strength concern.** Section 4 confirms V0 is OFF right now (RV60 14.59% > RV252 12.43%, trailing-63d +6.83%) -- a genuine de-risk into a rally. The EWMA variants (V2a/V2b/V3) would be ON; V1 downside would also be OFF. So EWMA *would* fix the specific current OFF state, but the 18y backtest shows that flexibility nets out NEGATIVE (lower Sharpe/Calmar, deeper DD) -- the symmetric gate's 'over-cautious' de-risks are, on net, paid for by the crash/grind protection they buy. Re-risking into every rally is not free.

**Overfitting / OOS caveats.** Windows (60/252) and EWMA lambdas (0.94/0.97/0.99) are a small principled set, NOT grid-tuned, but ANY gate swap mined on the same 18y sample risks in-sample selection. This would be a LIVE PRODUCTION CHANGE: requires OOS / walk-forward validation (e.g. freeze the variant pre-2015, test 2015+) and a paired bootstrap on the Sharpe/Calmar deltas before adoption. The downside/EWMA gates change the LIVE state vs baseline (section 4) -- confirm that flip is desired, not just a sample artifact.

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.
- Only the vol-gate layer changes; canary (TIP 13612U>0), trend (SPY 13612U>0) and safe (best{SHV,IEF} by 13612U) are held at production values, so the vol gate is the single differentiator across variants.
- Sleeves run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side, via the canonical harness exec_lag_moo_validation_2026_05_30._segment_returns_conv.
- Whipsaw / upside-de-risk / live state use a monthly month-grain calendar (signal -> following calendar month SPY close-to-close return); the daily sleeve backtest uses mooex. Trailing 63d return is the rally proxy for upside-vol-de-risk.
- EWMA variance: RiskMetrics recursion var_t = lambda*var_{t-1} + (1-lambda)*r^2 (pandas ewm alpha=1-lambda, adjust=False), seeded from the full daily history up to the signal date; annualized x sqrt(252).
- Ext window pre-2006-08 is proxy-backed; clean 18y has full real-open coverage and is the decisive lens.
