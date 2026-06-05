# Min-var 3-of-4 subset: EW vs inverse-vol, turnover headline

Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.

Anchor verified first through research/cpm_harness.py: Sharpe 1.2622, MaxDD -11.35%, Calmar 1.2196 (matches prod min-var anchor exactly).

## Question

On the CURRENT prod selection (ewobj min-var 3-of-4 subset), give the exact equal-weight (EW) vs inverse-vol (IV) comparison with annualized turnover. SAME selection in both cells; they differ ONLY in risky-block sizing. User is weighing EW for simplicity + stability and wants the turnover number nailed.

- MINVAR_IV   = ewobj min-var subset + inverse-vol sizing = current prod.
- COHERENT_EW = ewobj min-var subset + equal-weight sizing.

## Method

- Engine: research/cpm_harness.py (mooex T+1, both-252, 10 bps/side net in returns). Anchor asserted before any cell.
- Cells via research/cpm_minvar_coherence.py `make_weight_fn(selection="minvar_ewobj", sizing=...)`. Identical universe/canary/trend/safe/subset search; full-risk-on-drop renormalize over the kept trio.
- Metrics: clean (DECISION window) + ext, full panel. Annualized one-way turnover = mean per-rebalance sum|dw|/2 * 12 (research.cpm_weighting_corr.annualized_turnover).
- Significance: paired block bootstrap, positive = EW minus IV, B=2000 block=21 seed=42 (research/cpm_bootstrap_multimetric.py). Classification metrics = path-independent dSharpe/dSortino/dCVaR; dCalmar/dMartin/dMaxDD context only.
- Driver: research/cpm_minvar_ew_vs_iv_turnover.py. Outputs: research/cpm_minvar_ew_vs_iv_turnover_findings.json.

## HEADLINE: annualized turnover

| cell | turnover/yr (one-way) |
|---|---|
| MINVAR_IV (prod, inverse-vol) | 2.988 |
| COHERENT_EW (equal-weight) | 2.958 |

EW minus IV = -0.0294/yr. EW is only ~0.98% lower turnover than inverse-vol.

The stability/simplicity case for EW is NOT supported by turnover. Sizing choice barely moves turnover because annual turnover is dominated by SELECTION and REGIME switching (safe rotation, risky-fraction drop, monthly trio churn), not by the within-trio sizing weights. Both sit at ~2.96-2.99 turns/yr.

## Full metric table (clean = DECISION window)

| cell | win | Sharpe | Sortino | CVaR ratio | Calmar | Martin | MaxDD | CAGR | vol |
|---|---|---|---|---|---|---|---|---|---|
| MINVAR_IV | clean | 1.2622 | 1.8036 | 8.3908 | 1.2196 | 3.9522 | -0.1135 | 0.1384 | 0.1076 |
| MINVAR_IV | ext | 1.2624 | 1.8093 | 8.4523 | 0.9135 | 3.8170 | -0.1492 | 0.1363 | 0.1057 |
| COHERENT_EW | clean | 1.2711 | 1.8179 | 8.4444 | 1.0883 | 4.1685 | -0.1303 | 0.1418 | 0.1093 |
| COHERENT_EW | ext | 1.2969 | 1.8648 | 8.7294 | 0.9458 | 4.0211 | -0.1522 | 0.1439 | 0.1082 |

EW posts marginally higher Sharpe/Sortino/CVaR/CAGR but worse clean Calmar/MaxDD (deeper clean drawdown -13.0% vs -11.4%). Differences are tiny.

## Per-crisis MaxDD (ext curve)

| cell | GFC 2007-09 | COVID 2020 | 2022 full | 2025 tariff |
|---|---|---|---|---|
| MINVAR_IV | -0.1033 | -0.1011 | -0.0619 | -0.1135 |
| COHERENT_EW | -0.1314 | -0.1020 | -0.0517 | -0.1070 |

Mixed and small. EW is notably WORSE in GFC (-13.1% vs -10.3%), roughly tied in COVID, slightly BETTER in 2022 (-5.2% vs -6.2%) and 2025 (-10.7% vs -11.4%). No consistent drawdown advantage for either.

## IV-vs-EW significance (clean, B=2000 block=21 seed=42; positive = EW - IV)

| metric | mean | 95% CI | p(EW>IV) | class |
|---|---|---|---|---|
| dSharpe | 0.0088 | [-0.0469, 0.0651] | 0.628 | spans 0 |
| dSortino | 0.0143 | [-0.0714, 0.1009] | 0.635 | spans 0 |
| dCVaR | 0.0541 | [-0.3601, 0.4603] | 0.608 | spans 0 |
| dCalmar (context) | 0.0217 | [-0.1318, 0.1677] | 0.667 | spans 0 |
| dMartin (context) | 0.1175 | [-0.3434, 0.6020] | 0.722 | spans 0 |
| dMaxDD (context) | -0.0002 | [-0.0205, 0.0192] | 0.495 | spans 0 |

All path-independent contrasts (dSharpe/dSortino/dCVaR) span 0 with p ~0.61-0.64. Performance WASH confirmed. Path-dependent context metrics also span 0.

## Bottom line

1. Turnover: EW is only ~0.98% lower than inverse-vol (2.958 vs 2.988 turns/yr) -> turnover gives essentially NO stability edge to EW. Turnover is driven by selection/regime, not sizing.
2. Performance: full wash. Every classification CI spans 0.
3. Per-crisis MaxDD: mixed, small, no consistent winner (EW worse in GFC, slightly better in 2022/2025).

So the EW-for-stability argument does not hold on the turnover axis. If EW is adopted, justify it on operational simplicity / sizing transparency alone, NOT on lower turnover or better risk -- both are statistically and practically indistinguishable from current prod inverse-vol.

## Caveats / confidence

- Single in-sample evaluation (no OOS split here by design; significance via path-independent paired block bootstrap).
- Turnover is from monthly target weights (sum|dw|/2 * 12), one-way, gross of the 10 bps already netted in return series; it measures trading intensity, not extra cost beyond what is already in returns.
- Confidence HIGH on the turnover near-equality and the performance wash (both robust to the requested resampling protocol). Per-crisis MaxDD windows are short, so single-crisis numbers are noisy.
