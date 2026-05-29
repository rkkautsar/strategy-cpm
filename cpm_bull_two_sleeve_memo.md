# CPM + BULL Two-Sleeve Core - Research Memo

**Status:** Current-state research and defensibility memo for the 60/40 CPM+BULL
artifact. Live runbook remains 3-sleeve 60 CPM / 20 BULL / 20 NDX (see
`README.md`), but this memo tracks the maintained 2-sleeve code path and its
execution/governance conclusions.

Window conventions: clean live-ETF window 2008-05-30 -> 2026-05-22 (18.0y);
stress/deep-history window 1999-03-10 -> 2026-05-22. All numbers post-cost
(10 bps/side). Raw Sharpe is 0 rf.

## Strategy definition

- **CPM C0**: AAA Pair-EW Extension over 8-asset risky universe
  (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC), positive-Faber filter, EAA vol-adj
  ranker, top-half candidate pool (K=4), 50/50 min-variance pair, SHV/IEF
  best-safe.
- **BULL**: HAA-Simple on SPY with monthly 3-layer gate: HYG-OR-TIP canary,
  SPY 13612U trend > 0, and realized-vol crossover
  `rv_60d(SPY) < rv_252d(SPY)`. Else hold best-safe (SHV/IEF).
- Monthly rebalance. Production execution is T+1 MOO. Research engine reports
  T+0 MOC proxy metrics and validated MOO impact.

## Production 60/40 headline (clean 18y, RV_60d gate)

| Variant | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| 60/40 CPM+BULL blend | 1.41 | 14.3% | -10.7% | 1.34 |
| BULL solo | 1.12 | 11.9% | -13.6% | 0.88 |
| CPM solo | 1.27 | 14.6% | -15.4% | 0.95 |

## Execution convention validation (T+0 MOC proxy vs realistic T+1 MOO)

Validated on real open-price data for 13 tickers (yfinance OHLC).

- Engine accounting: signal on month-end close T, fill T+0 MOC, basket earns
  close[T] -> close[T+1].
- This is a valid proxy for realistic T+1 MOO fill.
- Rebalance-day overnight gap is sizable at asset level (about 0.2-0.9% mean
  absolute), but lookahead only acts on turned-over sleeve fraction.
- Basket persistence across month-ends keeps net lookahead near 0.6% per year
  (about 5 bps per rebalance), negligible at portfolio level.
- Realistic execution (T+1 MOO) costs about 0.04-0.06 blend Calmar versus
  same-day engine fill.

Conclusion: strategy behavior is robust to normal execution timing.

## BULL vol-gate choice: RV_60d over RV_20d

Chosen gate: `rv_60d(SPY) < rv_252d(SPY)`.

Rationale:

- **Execution-delay robustness first**: RV_60d blend Calmar is flat across
  MOO/MOC conventions (delay-insensitive by construction).
- Faster RV_20d degrades about -0.067 clean Calmar under full-session execution
  delay.
- Accepted trade-off: RV_60d has slightly lower normal-case clean performance
  than RV_20d (60/40 blend Calmar about 1.34 vs 1.39; MaxDD about -10.7% vs
  -9.8%) in exchange for timing-insensitive behavior.
- Differences are within bootstrap noise; slow gate is the more robust artifact.
- Parameters are convention-locked, not fitted/scanned: 60d vs 252d realized-vol
  crossover.

## Governance conclusions

- **Stop adding gates.** Tested and rejected: CPM breadth canary, binary vol
  gate, universe-avg-correlation (SIG-A), pair-corr-breakout (SIG-B),
  diversifier overbought, equity overbought (RSI textbook), shrinkage/min-corr
  pair re-pick, daily SPY 200d overlay, and KMLM crisis sleeve. Each failed at
  least one core bar: forward predictive power, preservation of profitable
  momentum continuation, or balanced multi-metric improvement.
- **Blend MaxDD is BULL-SPY-driven, not CPM-driven.** CPM-side gates can improve
  CPM standalone metrics, but cannot materially move blend troughs. Governance
  rule: do not add CPM complexity to solve a BULL-originated drawdown.
- **Drawdown floor is structural for this class.** Monthly-gated unlevered ETF
  blends in observed crisis regimes sit near about -10% to -12%. Clean 60/40 is
  -10.7%; extended 27y remains near -12%. Treat residual drawdown as structural
  cost, not defect.
- **Canary policy:** keep HYG-OR-TIP. Apparent HYG-only edge came from 3 GFC
  months and did not hold out-of-sample; holdings attribution showed no true
  correlation-break/co-crash edge.
- **Keep current core design:** CPM C0 structure (Faber/vol ranker,
  positive-Faber filter, K=4 top-half, 50/50 min-var pair, SHV/IEF best-safe)
  plus SPY as BULL risk asset.

## Reproduction pointers

- `research/two_sleeve_cpm_bull.py`
- `research/lookahead_audit_2026_05_30.py`
- `research/vol_gate_calmar_objective_findings.md`
