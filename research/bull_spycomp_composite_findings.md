# BULL SPY-COMP composite recession-gate override

Role: analyst (read-only re production; writes only to research/; no prod/memo files changed; no commit). Harness `research/cpm_harness.py` + `research/bull_spycomp_composite.py`.

**Question:** does a SPY-COMP-style COMPOSITE recession-nowcast OVERRIDE (`risk_on = (n_warnings < k) OR spy_trend_up`) beat the BULL sleeve's current AND gate (`canary_ok AND spy_trend_ok`) on the decision lens WITHOUT blowing out COVID / fast-crash drawdown, and survive walk-forward?

**Conventions:** mooex T+1 MOO exact, 10 bps/side, both-252. Clean (decision lens) 2008-05-30..2026-05-22. Ext 1999-03-10..2026-05-22. BULL sleeve = asset SPY, safe best-of(SHV/IEF) by 13612U.

**Six recession indicators (binary warn):**

| # | Indicator | Warn rule |
|---|---|---|
| 1 | VIX backwardation | VIX >= VIX3M |
| 2 | Yield curve | T10Y3M < 0 |
| 3 | Unemployment (Sahm-lite) | UNRATE > 12mo MA (lag 1mo) |
| 4 | Faber breadth | n_positive < 4 of 8 |
| 5 | Equity risk premium | ERP < expanding-mean(ERP) |
| 6 | TIP canary | TIP 13612U <= 0 |

**Look-ahead controls:**

- UNRATE lagged 1 month (FRED publication lag)
- ERP from Shiller CAPE; PE10 valid through 2023-09-01, price-scaled beyond (overstates CAPE -> more 'expensive' warns)
- ERP expanding-mean threshold is point-in-time (past only)
- market data (VIX/VIX3M/T10Y3M/breadth/TIP) at sig_d month-end (known)
- mooex T+1 MOO execution, 10bps/side

## 1. Sleeve comparison -- clean decision lens (2008-05-30..)

| Variant | Sharpe | Calmar | Martin | MaxDD | CAGR | Vol |
|---|---:|---:|---:|---:|---:|---:|
| prod_AND (baseline) | 0.984 | 0.569 | 2.382 | -20.41% | 11.60% | 11.92% |
| OR-TIP | 0.816 | 0.385 | 1.857 | -33.72% | 12.97% | 16.71% |
| composite_k1 | 0.928 | 0.620 | 1.872 | -19.86% | 12.32% | 13.54% |
| composite_k2 | 0.916 | 0.582 | 1.890 | -21.39% | 12.44% | 13.90% |
| composite_k3 | 0.920 | 0.528 | 1.662 | -26.34% | 13.90% | 15.49% |

## 2. Per-crisis drawdown (BULL sleeve, from ext series)

GFC 2007-10..2009-06; COVID 2020-02..2020-06 (CRITICAL: override stays long through head-fakes; 1mo-lag fast-crash 'long into the void' risk); 2022 full year; 2025 tariff 2025-02..2025-06.

| Variant | GFC_2008 | COVID_2020 | Y2022 | Tariff_2025 |
|---|---:|---:|---:|---:|
| prod_AND (baseline) | -12.09% | -13.35% | -10.11% | -10.04% |
| OR-TIP | -27.31% | -33.72% | -13.76% | -18.76% |
| composite_k1 | -12.09% | -13.35% | -13.76% | -10.04% |
| composite_k2 | -19.89% | -13.35% | -13.76% | -10.04% |
| composite_k3 | -25.00% | -13.35% | -25.16% | -10.04% |

## 3. Leave-one-out signal attribution (composite k=1, clean)

Drop each indicator from the composite at k=1; SPY-COMP predicts removing weak signals barely matters (any single warn already pushes to trend).

| Dropped | Sharpe | d Sharpe | Calmar | d Calmar | MaxDD |
|---|---:|---:|---:|---:|---:|
| VIX backwardation | 0.928 | +0.000 | 0.620 | +0.000 | -19.86% |
| Yield curve | 0.957 | +0.029 | 0.643 | +0.023 | -19.86% |
| Unemployment (Sahm-lite) | 0.906 | -0.022 | 0.610 | -0.010 | -19.86% |
| Faber breadth | 0.909 | -0.020 | 0.570 | -0.050 | -21.39% |
| Equity risk premium | 0.928 | +0.000 | 0.620 | +0.000 | -19.86% |
| TIP canary | 0.928 | +0.000 | 0.620 | +0.000 | -19.86% |

## 4. Ext-reduced composite confirmation (drop VIX-backwardation; 1999-03-10..)

Reduced composite = yield/unemp/ERP/breadth/TIP (drops VIX-term, VIX3M only from 2006). Confirms the macro-override is not a 2008+ artifact.

| Config | Sharpe | Calmar | Martin | MaxDD | CAGR |
|---|---:|---:|---:|---:|---:|
| prod_AND (baseline) ext | 0.974 | 0.526 | 2.475 | -20.41% | 10.73% |
| reduced_k1 ext | 0.842 | 0.550 | 1.791 | -19.86% | 10.92% |
| reduced_k2 ext | 0.800 | 0.388 | 1.474 | -28.22% | 10.96% |
| reduced_k3 ext | 0.690 | 0.317 | 1.168 | -33.72% | 10.68% |

## 5. Bootstrap (configs beating prod on Sharpe AND Calmar, clean)

No config beat prod on BOTH Sharpe AND Calmar in the clean window; bootstrap skipped.

## 6. Walk-forward (sequential OOS k-selection)

Each year (after 2012-01-01 warmup) pick the config with best trailing in-sample Sharpe from {{prod, OR-TIP, k1, k2, k3}}, apply OOS next year, chain.

| Series | Sharpe | Calmar | Martin | MaxDD | CAGR |
|---|---:|---:|---:|---:|---:|
| walkforward_oos_only | 0.998 | 0.525 | 1.504 | -25.16% | 13.20% |
| prod_oos_only | 1.218 | 0.983 | 4.090 | -13.35% | 13.11% |
| k1_oos_only | 1.051 | 0.691 | 2.063 | -19.35% | 13.37% |

Yearly picks: 2008:prod_AND, 2009:prod_AND, 2010:prod_AND, 2011:prod_AND, 2012:OR-TIP, 2013:composite_k1, 2014:composite_k1, 2015:composite_k1, 2016:composite_k3, 2017:composite_k3, 2018:composite_k1, 2019:composite_k3, 2020:composite_k3, 2021:composite_k3, 2022:composite_k3, 2023:prod_AND, 2024:prod_AND, 2025:prod_AND, 2026:prod_AND

Split-half (k1 vs prod): prod H1 Sharpe 0.706 / H2 1.286; k1 H1 0.848 / H2 1.017 (split 2017-06).

## 7. Verdict -- DOCUMENT, do NOT adopt

The SPY-COMP-style OVERRIDE (OR structure; OR-TIP or composite) does NOT beat the production AND gate on the decision lens. The AND gate wins.

**Evidence:**

- **OR structure alone is strictly worse.** OR-TIP (`TIP OR trend`) drops Sharpe 0.984 -> 0.816 and deepens MaxDD -20.41% -> -33.72% (GFC -27.3%, COVID -33.7%). The permissive OR keeps the sleeve long into drawdowns -- the wrong direction for a crash-defense sleeve.
- **Composite k=1 trades Sharpe for a marginal Calmar bump.** Sharpe 0.984 -> 0.928 (WORSE), Calmar 0.569 -> 0.620 (better), MaxDD -20.41% -> -19.86% (0.5pp, noise). No config beat prod on BOTH Sharpe AND Calmar, so the bootstrap significance gate never even triggered.
- **Higher k blows out tails.** k=2/k=3 deepen GFC (-19.9%/-25.0%) and 2022 (-13.8%/-25.2%): more permissive override = more 'long into the void'.
- **COVID fast-crash:** composite holds COVID at -13.35% (same as prod) ONLY because the SPY trend leg still fires; the macro-override itself adds no COVID protection and the 1mo-lag fast-crash risk shows up instead in 2022 (-10.1% -> -13.8% at k=1).
- **Leave-one-out exposes the overfit narrative.** At k=1, dropping VIX, ERP, or TIP changes Sharpe by +0.000 (inert -- they never bind), dropping the yield curve IMPROVES Sharpe +0.029 (it actively hurts), and only unemployment/breadth carry mild positive weight. The 'composite' is not composite: 2 signals carry it, 1 drags it, 3 are dead weight. Consistent with SPY-COMP's own logic (any warn just defers to trend) -- which means it adds nothing over a plain trend rule.
- **Ext-reduced confirms it is not a 2008 artifact (in the wrong direction).** Over 1999-03-10.. the reduced composite is also WORSE: reduced_k1 Sharpe 0.842 vs prod ext 0.974.
- **Walk-forward is decisive.** Yearly adaptive selection of the best config OOS yields Sharpe 0.998 / Calmar 0.525 / MaxDD -25.16% -- WORSE than simply holding prod OOS (Sharpe 1.218, Calmar 0.983, MaxDD -13.35%). Even an oracle-ish adaptive override loses to the static AND gate out-of-sample.

**Why the AND gate wins (structural):** the AND gate requires BOTH macro canary and SPY trend to agree before risking on -- conservative, good crash protection. The SPY-COMP OR override only requires macro-healthy OR trend-up -- permissive, stays invested through deteriorating tape. For a sleeve whose mandate includes tail defense, permissiveness is value-destructive.

**Portfolio context:** BULL is ~20% of the 60/20/20 book. Adopting composite_k1 costs ~0.056 sleeve Sharpe with no MaxDD win that survives scrutiny; at 20% weight the full-portfolio impact is small but negative, with a deeper 2022 tail. No upside justifies the change; full-CPM re-run not warranted.

**Recommendation:** DOCUMENT (negative result). Keep the production AND gate. The SPY-COMP recession-override paradigm does not transfer to this sleeve; the override's permissiveness is the dominant failure mode and it is the AND gate's conservatism that is doing the work. The biggest threat anticipated (overfit DoF across 6 signals x k) is confirmed by leave-one-out and walk-forward: the apparent Calmar edge at k=1 is carried by 2 signals, does not beat prod on Sharpe, and reverses out-of-sample.

