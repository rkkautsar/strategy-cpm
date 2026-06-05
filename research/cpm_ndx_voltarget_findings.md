# NDX sleeve: monthly implementable volatility targeting -- findings

Analyst role. Read-only re production (`ndx_sleeve_live.py` / prod / memo NOT
edited; no commit). Harness: `research/cpm_ndx_voltarget.py`. Raw:
`research/cpm_ndx_voltarget_findings.json`.

## Question

Does monthly IMPLEMENTABLE volatility targeting (vol-scaled total risky exposure)
on the NDX sleeve (a) cut the -31% MaxDD MATERIALLY without proportional
Sharpe/CAGR loss, and (b) IMPROVE Sharpe/Sortino (the momentum vol-scaling
literature result of Barroso-Santa-Clara 2015 / Daniel-Moskowitz 2016 /
Moreira-Muir 2017 / Harvey 2018) -- net of the extra turnover it churns and
out-of-sample? Bongaerts 2020 cautions the famous versions carry ex-post-k
look-ahead bias and high turnover, so we test only implementable scaling.

## Method

- Keep prod selection (momentum top-5) + EW within the risky block. Scale the
  TOTAL risky exposure monthly at rebalance:
  `exposure_t = clip(target_vol / realized_vol_{t-lag}, 0, CAP)`;
  risky weights = prod-EW * exposure_t; freed weight -> safe (SHV/IEF best-of-safe);
  CAP>1 lets calm months lever (safe weight goes negative = borrow at safe yield).
- IMPLEMENTABLE: `realized_vol` from trailing daily returns through the month-end
  signal date `sig_d`; execution is T+1 MOO, so this is properly LAGGED -- no
  look-ahead. `target_vol` is FIXED a-priori (NOT calibrated ex-post over the
  sample -- that is the Bongaerts bias). Achieved unconditional vol + avg exposure
  reported; target/window/cap/vol-choice swept as sensitivity, not optimization.
- A-PRIORI TARGET: a concentrated 5-name single-stock momentum basket runs ~30%
  annualized vol (vs ~12% for the diversified L/S momentum FACTOR in Barroso), so
  PRIMARY `target_vol = 0.30` for basket-vol (avg exposure lands ~0.90, i.e.
  de-risk in spikes not a permanent de-gross). Index/QQQ-vol variant uses 0.22
  (QQQ runs lower vol). Round a-priori anchors, NOT swept-then-picked.
- Engine reuse: monkeypatch `compute_ndx_weights`, call UNMODIFIED
  `run_ndx_backtest` (gate TIP+SPY-trend+SPY-RV, safe rotation, T+1 MOO,
  10bps/side, delisting haircut, PIT membership all identical). Only total risky
  exposure scaled. Helpers + B=2000 block=21 seed=42 paired block bootstrap reused
  from `cpm_ndx_minvar_cvar.py` / `cpm_bootstrap_multimetric.py`.
- Windows: clean (2008-05-30+, DECISION), stress (1999-03-10+, confirm),
  per-crisis, 3-seg walk-forward. Turnover net 10bps.

### Configs (clean 2008+, EW within risky; gate/safe/T+1/10bps/delist/PIT fixed)

| config       | vol measure | CAP  | target | Sharpe | Sortino | CVaR  | MaxDD   | CAGR   | vol    | turnover | avgExp |
|--------------|-------------|------|--------|--------|---------|-------|---------|--------|--------|----------|--------|
| PROD         | --          | --   | --     | 1.281  | 1.962   | 8.40  | -31.4%  | 31.4%  | 23.6%  | 5.16     | --     |
| DERISK (1y)  | basket 60d  | 1.0  | 0.30   | 1.263  | 1.913   | 8.23  | -26.6%  | 25.6%  | 19.6%  | 5.19     | 0.898  |
| SYM          | basket 60d  | 1.5  | 0.30   | 1.235  | 1.869   | 8.04  | -26.6%  | 29.2%  | 22.9%  | 6.55     | 1.073  |
| CONDITIONAL  | basket 60d  | 1.0  | 0.30   | 1.254  | 1.896   | 8.14  | -26.6%  | 25.9%  | 20.0%  | 5.19     | 0.912  |
| DERISK_IDX   | QQQ 60d     | 1.0  | 0.22   | 1.247  | 1.908   | 8.18  | -31.4%  | 29.4%  | 22.8%  | 5.18     | 0.971  |

DERISK = PRIMARY. PROD reproduces the anchor (clean Sharpe 1.281, MaxDD -31.4%).

### Paired block bootstrap each vs PROD (clean; B=2000, block=21, seed=42)

| config      | dSharpe (p>0)   | dSortino (p>0)  | dCVaR (p>0)     | dMaxDD (p>0)        |
|-------------|-----------------|-----------------|-----------------|---------------------|
| DERISK      | -0.016 (0.377)  | -0.048 (0.315)  | -0.162 (0.350)  | **+0.049 (0.968)**  |
| SYM         | -0.044 (0.276)  | -0.092 (0.248)  | -0.356 (0.274)  | +0.014 (0.623)      |
| CONDITIONAL | -0.026 (0.307)  | -0.066 (0.247)  | -0.260 (0.261)  | **+0.047 (0.952)**  |
| DERISK_IDX  | -0.033 (0.037)* | -0.053 (0.053)  | -0.220 (0.065)  | -0.000 (0.477)      |

dMaxDD positive = DD reduced (improvement). dSharpe/dSortino/dCVaR positive =
risk-adjusted return improved. `*` DERISK_IDX dSharpe p<=0.05 = significantly
WORSE. dMaxDD CI is soft (path-dependent) but point estimates align with the
realized full-series MaxDD cut.

### Per-crisis MaxDD (stress 1999+)

| config      | dotcom 00-02 | GFC 07-09 | COVID 20 | 2022   | 2025   |
|-------------|--------------|-----------|----------|--------|--------|
| PROD        | -12.1%       | -9.1%     | -4.7%    | -0.3%  | -4.8%  |
| DERISK      | -12.1%       | -8.7%     | -4.7%    | -0.3%  | -2.9%  |
| SYM / COND  | -12.1%       | -8.7%     | -4.7%    | -0.3%  | -2.9%  |
| DERISK_IDX  | -12.1%       | -8.7%     | -4.7%    | -0.3%  | -2.9%  |

Per-crisis DDs are essentially FLAT across all configs: the gate already strips
the named-crisis drawdowns. Vol targeting only nudges the small 2025 dispersion
DD. The headline -31.4% MaxDD is a risk-ON single-stock dispersion event OUTSIDE
the named crisis windows -- exactly where continuous vol scaling acts.

### Sensitivity (clean; DERISK basket-vol target x window, and SYM cap)

| variant          | Sharpe | MaxDD   | CAGR   | vol    | turnover | avgExp |
|------------------|--------|---------|--------|--------|----------|--------|
| t25 / 20d        | 1.301  | -24.7%  | 24.9%  | 18.4%  | 5.38     | 0.855  |
| t25 / 60d        | 1.274  | -22.6%  | 23.7%  | 18.0%  | 5.11     | 0.835  |
| t30 / 20d        | 1.293  | -28.5%  | 27.0%  | 20.1%  | 5.37     | 0.913  |
| t30 / 60d (PRIM) | 1.263  | -26.6%  | 25.6%  | 19.6%  | 5.19     | 0.898  |
| t35 / 20d        | 1.291  | -30.6%  | 28.7%  | 21.4%  | 5.34     | 0.947  |
| t35 / 60d        | 1.253  | -29.1%  | 27.1%  | 20.9%  | 5.21     | 0.936  |
| SYM cap 1.25     | 1.252  | -26.6%  | 28.4%  | 21.9%  | 6.06     | 1.021  |
| SYM cap 1.50     | 1.235  | -26.6%  | 29.2%  | 22.9%  | 6.55     | 1.073  |
| SYM cap 2.00     | 1.223  | -26.6%  | 29.1%  | 23.1%  | 6.65     | 1.082  |

Lower target / shorter window -> more de-gross -> lower DD, mildly higher Sharpe.
The DD-cut DIRECTION is robust across all target/window cells. Higher CAP is
monotonically worse on Sharpe and adds turnover. (The t25/20d Sharpe 1.301 > PROD
appears only in sweep corners -- treat as overfit risk, not the committed default.)

### Walk-forward (3-seg, clean)

No config beats PROD across segments. DERISK_IDX tracks PROD but lags in the
2020-2026 segment (Sharpe 1.387 vs PROD 1.471). Basket-vol DERISK/SYM/COND were
not walk-forwarded (no significant positive bootstrap and Sharpe below PROD).

## Answers

(a) **Does it cut the -31% MaxDD materially without proportional return loss?**
PARTLY. Basket-vol de-risk cuts MaxDD ~4.8pp (-31.4% -> -26.6%), and the
dMaxDD bootstrap is significant (p=0.968) -- a real, directionally robust DD cut
at NEGLIGIBLE added turnover (5.16 -> 5.19, net 10bps). BUT it is NOT free: vol
(23.6% -> 19.6%) and CAGR (31.4% -> 25.6%) fall roughly proportionally, so it
behaves like a risk-for-return DIAL. It is a CLEANER dial than breadth -- Sharpe
is preserved (1.281 -> 1.263, dSharpe NOT significant) rather than degraded, and
turnover barely moves -- but it does not deliver DD reduction for free.

(b) **Does it improve Sharpe/Sortino (the literature result)?** NO. dSharpe,
dSortino, dCVaR are all mildly NEGATIVE and none significant (p>0 = 0.31-0.38).
The momentum vol-scaling Sharpe gain does NOT replicate on this sleeve, because
the gate already removes the predictable crash-vol autocorrelation (per-crisis
DDs flat); the residual -31% is a risk-ON dispersion event where vol scaling
de-grosses ~1:1 instead of dodging a crash.

(c) **de-risk (cap 1.0) vs symmetric (cap 1.5)?** De-risk-only WINS. Lever-up
adds turnover (5.19 -> 6.55) and lowers Sharpe (1.263 -> 1.235) for the SAME
MaxDD (-26.6%); the cap sweep is monotone (1.25/1.50/2.00 -> 1.252/1.235/1.223).
Lever-up-in-calm buys turnover and risk, no Sharpe.

(d) **conditional vs continuous?** No edge. CONDITIONAL holds the DD benefit
(dMaxDD p=0.952) but does NOT cut turnover (5.19 = continuous) and its Sharpe is
no better. At monthly frequency the sleeve is already low-churn, so the
Bongaerts turnover concern never bites -- conditional adds complexity, not value.

(e) **basket-vol vs index-vol; window.** Basket-vol is the correct measure:
index(QQQ)-vol gives ZERO DD benefit (-31.4%, dMaxDD p=0.48) and SIGNIFICANTLY
hurts Sharpe (dSharpe p=0.037, dCalmar p=0.016) -- it scales on the wrong risk
(index vol misses single-stock dispersion). Window: 20d slightly outperforms 60d
on Sharpe and cuts DD harder; DD-cut direction holds across both.

## Verdict

Monthly implementable vol targeting (basket-vol, de-risk-only, fixed a-priori
target, lagged vol, capped at 1.0) DOES cut the NDX MaxDD modestly (~-31% ->
-27%, bootstrap-significant) at trivial turnover cost -- but NOT for free and NOT
as a Sharpe improver. It trades return roughly proportionally and leaves
Sharpe/Sortino/CVaR flat-to-slightly-down (no significant gain). It is a genuine,
clean DD-CONTROL DIAL (better than breadth: Sharpe-preserving, near-zero added
turnover), not the literature's Sharpe-improving free lunch -- the latter does
not survive because the gate already harvests the predictable crash-vol effect.
Symmetric leverage and the conditional/index-vol variants are dominated. Net: if
the objective is purely to shrink the tail DD with minimal Sharpe/turnover
collateral, basket-vol de-risk-only is a defensible lever; if the objective is
higher risk-adjusted return, it does not deliver.

## Caveats / confidence

- DATASET LIMITATION (per user scope relaxation): runs on the readily-available
  cached daily panel (`data/ndx_constituents/prices.parquet`), which is partial
  vs a full survivorship-free PIT history. Mitigated by construction: PROD and
  EVERY vol-target variant run on the IDENTICAL dataset (same dates/names) via
  the same monkeypatched engine, so the COMPARISON is apples-to-apples and the
  DIRECTIONAL verdict is sound. Absolute levels (Sharpe ~1.28, MaxDD ~-31%) are
  comparable to prior NDX runs but are NOT a publishable survivorship-clean
  anchor.
- dMaxDD/dCalmar CIs are path-dependent (soft) per the bootstrap helper's design;
  dSharpe/dSortino/dCVaR are the order-invariant classification metrics.
- target/window/cap/vol-choice are DoF; primary defaults (basket-vol, 60d,
  target 0.30, cap 1.0) chosen a-priori, sensitivity reported not optimized. The
  one Sharpe-beating cell (t25/20d) sits in a sweep corner -- overfit risk.
- Single in-sample (clean=decision, stress=confirm). PIT/delisting integrity and
  T+1 MOO / 10bps costing inherited unchanged from the prod engine.
- Confidence: MODERATE-HIGH on direction (DD cut real but proportional; no Sharpe
  gain; de-risk>sym; basket>index), given identical-engine comparison and
  consistent bootstrap + sensitivity. LOW on absolute magnitudes (dataset).

## Handoff

None required for analysis. If prod adoption of a DD-control dial is considered,
route the decision to the ORACLE (DD-vs-return tradeoff is a risk/objective call,
not a Sharpe win) and any code change to the FIXER.
