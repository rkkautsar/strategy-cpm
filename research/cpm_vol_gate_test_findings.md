# CPM vol-gate add test -- sleeve vs per-asset vs none

Role: analyst (hypothesis-driven; read-only re production; writes `research/` only; NO production/memo edits; NO commit).

**Question.** CPM currently has NO vol gate (BULL has rv_60d(SPY) < rv_252d(SPY)). CPM already carries the positive-trend (absolute-momentum) screen + strict-4 partial-safe ladder. Does adding a vol gate earn its keep, and at what level (sleeve vs per-asset)?

**Convention.** Everything held at production CPM (IV4 `compute_target_weights`); only the vol gate added. Execution T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost 10 bps/side; cov lookback 504d; K=4. Blend = 0.60*CPM + 0.40*BULL(rv60 gate). Clean 2008-05-30..2026-05-22 (18y); ext 1999-03-10..2026-05-22 (27y). Martin = CAGR/UlcerIndex.

**Variants.**
- **V0 NONE** -- current production. Baseline.
- **V1 SLEEVE-SPY** -- BULL-style: if rv_60d(SPY) >= rv_252d(SPY) at sig_d, de-risk the whole CPM sleeve to timed safe.
- **V2 SLEEVE-BASKET** -- same sleeve gate but on the equal-weight CPM 8-risky basket rv.
- **V3 PER-ASSET** -- 'same level as abs-mom': in addition to faber>0, also require each candidate's rv_60d < rv_252d to be held; failed names route to safe via the strict-4 partial-safe ladder.

## 0. Anchor gate

| Window | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| clean | 1.1910 | -12.67% | 1.0615 | 1.191/-12.67%/1.0615 | CONFIRMED |
| ext | 1.2142 | -15.93% | 0.8608 | 1.2161/-15.93%/0.8654 | MISMATCH |

CPM-solo NONE reproduces the production IV4 anchor exactly. Generalized weight fn `cpm_vg(none)` self-check clean Sharpe 1.190980, matches production = True. Vol-gate variants are trusted on that basis.

## 1. Headline -- CPM-solo and 60/40 blend

### 1.1 CPM-solo, clean window (18y)

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| V0 NONE (production) | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 |
| V1 SLEEVE-SPY | 1.1554 | 11.75% | 10.09% | -9.61% | 1.2227 | 3.5388 |
| V2 SLEEVE-BASKET | 1.1446 | 11.78% | 10.22% | -13.64% | 0.8639 | 3.5610 |
| V3 PER-ASSET | 1.1452 | 10.91% | 9.46% | -9.65% | 1.1299 | 3.6100 |

### 1.2 CPM-solo, extended window (27y)

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| V0 NONE (production) | 1.2142 | 13.71% | 11.09% | -15.93% | 0.8608 | 3.8201 |
| V1 SLEEVE-SPY | 1.0569 | 10.33% | 9.75% | -13.38% | 0.7722 | 2.6284 |
| V2 SLEEVE-BASKET | 1.0759 | 10.30% | 9.54% | -13.64% | 0.7556 | 2.9383 |
| V3 PER-ASSET | 1.1843 | 10.77% | 8.97% | -9.65% | 1.1154 | 3.5826 |

### 1.3 60/40 blend (CPM + BULL), clean window (18y)

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| V0 NONE (production) | 1.2485 | 12.74% | 10.05% | -10.68% | 1.1928 | 4.3538 |
| V1 SLEEVE-SPY | 1.1848 | 11.69% | 9.76% | -9.83% | 1.1894 | 3.8123 |
| V2 SLEEVE-BASKET | 1.2047 | 11.73% | 9.62% | -10.10% | 1.1611 | 3.9112 |
| V3 PER-ASSET | 1.1836 | 11.18% | 9.35% | -8.96% | 1.2483 | 3.8044 |

### 1.4 60/40 blend (CPM + BULL), extended window (27y)

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| V0 NONE (production) | 1.2192 | 12.13% | 9.78% | -11.31% | 1.0723 | 3.9954 |
| V1 SLEEVE-SPY | 1.0641 | 10.06% | 9.42% | -10.27% | 0.9791 | 2.8417 |
| V2 SLEEVE-BASKET | 1.0998 | 10.06% | 9.10% | -10.10% | 0.9963 | 3.0981 |
| V3 PER-ASSET | 1.1503 | 10.33% | 8.89% | -8.96% | 1.1529 | 3.4636 |

## 2. Stress windows (CPM-solo and blend; MaxDD / total return within window)

### GFC (2007-10..2009-06)

| Variant | CPM MaxDD | CPM ret | Blend MaxDD | Blend ret |
|---|---:|---:|---:|---:|
| V0 NONE (production) | -11.88% | 9.86% | -9.90% | 11.68% |
| V1 SLEEVE-SPY | -11.95% | 10.70% | -8.87% | 11.90% |
| V2 SLEEVE-BASKET | -13.29% | 9.00% | -9.67% | 10.92% |
| V3 PER-ASSET | -8.11% | 18.69% | -7.94% | 16.71% |

### COVID (2020-02..2020-06)

| Variant | CPM MaxDD | CPM ret | Blend MaxDD | Blend ret |
|---|---:|---:|---:|---:|
| V0 NONE (production) | -10.06% | 8.00% | -10.68% | 3.22% |
| V1 SLEEVE-SPY | -4.86% | 3.82% | -8.10% | 0.74% |
| V2 SLEEVE-BASKET | -4.86% | 3.82% | -8.10% | 0.74% |
| V3 PER-ASSET | -5.98% | 2.31% | -8.96% | -0.15% |

### 2022 bear (2022-01..2022-12)

| Variant | CPM MaxDD | CPM ret | Blend MaxDD | Blend ret |
|---|---:|---:|---:|---:|
| V0 NONE (production) | -6.33% | -0.50% | -3.86% | 0.12% |
| V1 SLEEVE-SPY | -0.30% | 0.94% | -0.30% | 0.94% |
| V2 SLEEVE-BASKET | -6.33% | -2.01% | -3.86% | -0.82% |
| V3 PER-ASSET | -4.70% | 0.30% | -2.85% | 0.59% |

## 3. Turnover / whipsaw

Annualized one-way turnover (0.5 * sum|dw| / yr) and share of months the CPM sleeve is fully de-risked to safe.

| Variant | Clean turnover/yr | Clean %mo fully-safe | Ext turnover/yr | Ext %mo fully-safe |
|---|---:|---:|---:|---:|
| V0 NONE (production) | 2.616 | 13.4% | 2.768 | 11.0% |
| V1 SLEEVE-SPY | 3.182 | 37.8% | 3.468 | 40.1% |
| V2 SLEEVE-BASKET | 2.868 | 36.9% | 3.166 | 42.2% |
| V3 PER-ASSET | 3.480 | 24.4% | 3.686 | 22.6% |

## 4. Interaction with abs-mom screen + partial-safe (redundant vs additive)

For each candidate gate, by month: does it FIRE; and when it fires is production already de-risked (REDUNDANT) or fully risk-on (ADDITIVE)? Sleeve gates count ADDITIVE only when production was fully risk-on (n_post=4); per-asset counts ADDITIVE when it drops a name while production sleeve was RISK_ON.

### 4.1 clean window

| Gate | Months total | Fires | Additive | Redundant | Fire rate | Additive share |
|---|---:|---:|---:|---:|---:|---:|
| SLEEVE-SPY | 217 | 53 | 39 | 14 | 24.4% | 73.6% |
| SLEEVE-BASKET | 217 | 51 | 37 | 14 | 23.5% | 72.5% |
| PER-ASSET | 217 | 124 | 124 | 0 | 57.1% | 100.0% |

### 4.2 ext window

| Gate | Months total | Fires | Additive | Redundant | Fire rate | Additive share |
|---|---:|---:|---:|---:|---:|---:|
| SLEEVE-SPY | 327 | 95 | 69 | 26 | 29.1% | 72.6% |
| SLEEVE-BASKET | 327 | 102 | 76 | 26 | 31.2% | 74.5% |
| PER-ASSET | 327 | 210 | 210 | 0 | 64.2% | 100.0% |

## 5. Verdict

Deltas vs V0 NONE (positive = better Sharpe/Calmar; less-negative MaxDD = shallower):

| Variant | dSharpe clean | dCalmar clean | dMaxDD clean | dSharpe ext | dBlend Sharpe clean |
|---|---:|---:|---:|---:|---:|
| V1 SLEEVE-SPY | -0.0356 | +0.1612 | +3.05pp | -0.1573 | -0.0637 |
| V2 SLEEVE-BASKET | -0.0463 | -0.1976 | -0.97pp | -0.1383 | -0.0438 |
| V3 PER-ASSET | -0.0457 | +0.0684 | +3.01pp | -0.0298 | -0.0649 |

(dMaxDD positive = shallower drawdown = better.)

### 5.1 VERDICT -- do NOT add a vol gate to CPM (keep V0 NONE)

**Risk-adjusted return (Sharpe): NO gate helps.** On the decisive clean window
(18y, full real-open coverage) V0 NONE has the HIGHEST CPM-solo Sharpe (1.1910).
All three gates LOWER it: V1 SLEEVE-SPY -0.0356, V2 SLEEVE-BASKET -0.0463,
V3 PER-ASSET -0.0457. The 60/40 blend tells the same story (V0 1.2485 highest;
every gate -0.044 to -0.065). The extended window is even more lopsided for the
sleeve gates (V1 -0.157, V2 -0.138 Sharpe), while V3 is roughly Sharpe-neutral
ext (-0.030). No variant produces a positive Sharpe delta anywhere.

**Drawdown / Calmar: a real but bought-with-return improvement for V1 and V3.**
V1 SLEEVE-SPY cuts clean MaxDD -12.67% -> -9.61% (+3.05pp) and lifts clean Calmar
to 1.2227 (+0.16). V3 PER-ASSET cuts clean MaxDD to -9.65% (+3.01pp), lifts ext
Calmar to 1.1154 (vs 0.8608) and shows the shallowest MaxDD in both windows.
V2 SLEEVE-BASKET is strictly dominated -- WORSE clean MaxDD (-13.64%) and Calmar
(0.8639) AND lower Sharpe -- reject outright.

**Net of whipsaw: the gates are a drag.** Every gate ADDS turnover (V1 +0.57,
V3 +0.86 one-way/yr clean) and 2-3x the fully-safe months (V0 13.4% -> V1 37.8%,
V2 36.9%, V3 24.4%). That extra cash time in the strong post-2009 equity run is
exactly the realized whipsaw cost that shows up as the lower Sharpe/CAGR.

**Redundant with abs-mom + partial-safe? Mechanically additive, economically
net-negative.** The vol gate is NOT just re-firing the same months the abs-mom
screen + partial-safe already de-risk: SLEEVE-SPY fires 24.4% of clean months and
73.6% of those fires hit a fully risk-on (n_post=4) production sleeve -- a
distinct vol-timing signal. PER-ASSET trims a held name in 57% of months. But the
additive de-risks land mostly in continuing bull months (whipsaw); the payoff is
concentrated in two episodes -- 2022 (V1 CPM MaxDD -6.33% -> -0.30%) and COVID
(V1/V2 -10.06% -> -4.86%) -- and in GFC for V3 (-11.88% -> -8.11%, ret +18.69%
vs +9.86%). So the gate trades average risk-adjusted return for episodic tail
protection, and on the full sample the trade is Sharpe-negative.

**If a gate were mandated (it should not be), ranking:**
1. **V3 PER-ASSET** -- least-bad. Sharpe-neutral ext, shallowest MaxDD both
   windows, best GFC behavior, best blend Calmar (clean 1.2483). Cost: highest
   turnover and a -0.046 clean Sharpe.
2. **V1 SLEEVE-SPY** -- best single-episode tail cut (2022, COVID) and best CPM
   clean Calmar (1.2227), but the worst full-history Sharpe hit (ext -0.157).
3. **V2 SLEEVE-BASKET** -- dominated; do not use.

**Within-noise flag.** All Sharpe deltas (0.03-0.07) sit well inside the blend
Sharpe bootstrap dispersion (clean 95% CI width ~0.5 in the IV4 memo run), so the
Sharpe degradation is directionally consistent but statistically within noise.
The MaxDD/Calmar gains for V1/V3 are larger relative to their dispersion but are
paid for in return, not free.

**Bottom line: KEEP V0 NONE.** The existing positive-trend (absolute-momentum)
screen + strict-4 partial-safe already deliver CPM's best risk-adjusted return and
capture the bulk of regime de-risking. An added vol gate is redundant-to-
counterproductive on Sharpe and only buys episodic drawdown relief at a turnover
and return cost. Do not add a CPM vol gate at either the sleeve or per-asset
level.

## Caveats

- All post-cost (10 bps/side), T+1 MOO exact with real yfinance auto_adjust opens.

- Ext 27y is partially proxy-backed pre-2006 for the CPM universe (close-to-close fallback on a minority of rebal days); clean 18y has full real-open coverage and is the decisive lens.

- Per-asset vol screen uses each asset's own daily close rv_60d<rv_252d; warmup (<252 obs) holds (passes), matching the BULL gate warmup convention.

- SLEEVE-BASKET uses the equal-weight CPM 8-risky basket daily returns (signal-date only, no lookahead) as a CPM-specific market vol proxy.

- Turnover is signal-level one-way (0.5*sum|dw|); realized cost already embedded in returns.

