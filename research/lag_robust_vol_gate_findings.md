# Lag-robust BULL vol-gate: can a slower vol regime survive honest T+1 execution?

Date: 2026-05-30
Analyst role (read-only): no production file changed, no spec change, no commit.
Harness: `research/lag_robust_vol_gate.py` (reuses `lookahead_audit_2026_05_30.py`
timing/CPM/blend/metrics UNCHANGED; only swaps `bull_qqq_live._vol_gate_ok`).
Raw output: `research/lag_robust_vol_gate.out`.

## Question / hypothesis

The fast RV_20d-vs-RV_252d crossover gate (`bull_qqq_live.py:104-112`) carries the
same-day-close lookahead (audit: BULL clean lag delta -0.173). User view: the
vol-targeting IDEA is sound, only the fast-daily-crossover IMPLEMENTATION needs
same-day fill. Hypothesis: a slower / lower-cadence vol regime estimator recovers
most of the benefit while surviving a 1-day execution lag.

Lag convention identical to the prior audit. exec_lag=0 = production same-day-close
ceiling; exec_lag=1 = honest 1-trading-day fill. All variants at exec_lag=1 except
the same-day reference. Blend = 0.60 CPM + 0.40 BULL, both sleeves at the same lag.
No threshold scans: every window/span/target is convention-locked.

## Validation (reproduces prior audit before trusting deltas)

| series (clean 18y, BULL solo) | this harness | prior audit | match |
|---|---|---|---|
| REF-ON-sameday (orig gate, lag0) | 1.103 / 11.80% / -12.02% | 1.103 / 11.80% / -12.02% | exact |
| REF-ON-lag (orig gate, lag1)     | 0.929 / 9.78% / -15.64%  | 0.929 / 9.78% / -15.64%  | exact |
| BLEND base / lag                 | 1.351 / 1.258            | 1.351 / 1.258            | exact |
| EXT BULL base / lag              | 0.980 / 0.841            | 0.980 / 0.841            | exact |

Trustworthy.

## Reference points (clean 18y)

- REF-OFF (vol gate disabled, honest lag) = the floor everything is judged against:
  BLEND Sharpe **1.310**, BULL **1.038**, BULL MaxDD -20.71%.
- REF-ON-sameday (orig gate, lookahead ceiling): BLEND 1.351, BULL 1.103.
- REF-ON-lag (orig gate, honest) = current honest reality: BLEND 1.258, BULL 0.929.

Key framing fact: the current gate's "+0.174 BULL Sharpe" premium is mostly the
gate DESTROYING value under lag (1.103 -> 0.929), not the gate adding value over
no-gate. At same-day the gate beats no-gate by only +0.065 BULL (1.103 vs 1.038);
under honest lag it is -0.109 BELOW no-gate (0.929 vs 1.038). The honest floor is
NO-GATE, and no-gate already beats the current gate at honest execution.

## Ranked results (clean 18y, honest lag; refs italic)

Rank by BLEND Sharpe, then MaxDD, then parsimony.

| variant | cadence / window | BLEND Sh | BLEND DD | BULL Sh | BULL DD | vs FLOOR (blend) |
|---|---|---|---|---|---|---|
| *REF-ON-sameday* | daily RV20/252 lag0 | *1.351* | *-9.82%* | *1.103* | *-12.02%* | *+0.041 (lookahead)* |
| **S3-MONTHLY** | monthly RV 12m/36m | **1.333** | -11.59% | 0.993 | -20.71% | **+0.023** |
| REF-OFF (floor) | none | 1.310 | -11.59% | 1.038 | -20.71% | +0.000 |
| S1-60 | daily RV60/252 | 1.292 | -10.00% | 1.017 | -13.66% | -0.018 |
| S1-120 | daily RV120/252 | 1.286 | -10.00% | 0.983 | -17.42% | -0.024 |
| S2-EMA | daily EMA20/252 | 1.266 | -10.00% | 0.953 | -15.05% | -0.044 |
| *REF-ON-lag* | daily RV20/252 lag1 | *1.258* | *-10.00%* | *0.929* | *-15.64%* | *-0.052 (current)* |
| S5-VOLTGT | continuous 15% tgt | 1.247 | -10.00% | 0.900 | -15.79% | -0.063 |
| S4-LAGINPUT | RV20/252 on close[T-1] | 1.240 | -10.00% | 0.890 | -13.66% | -0.070 |

EXT 27y blend Sharpe (floor REF-OFF 1.233): S3-MONTHLY 1.266 (+0.033), S1-120
1.256 (+0.023), S1-60 1.219 (-0.014), S2-EMA 1.215, REF-ON-lag 1.195, S4 1.187,
S5 1.185. S3-MONTHLY is the only variant that beats the floor on BOTH windows.

### Crisis-window blend Sharpe

| window | REF-OFF | REF-ON-sameday | REF-ON-lag | S3-MONTHLY | S1-120 |
|---|---|---|---|---|---|
| dot-com | 0.926 | 0.932 | 0.844 | **1.075** | 0.974 |
| GFC | 0.050 | 0.268 | 0.050 | 0.172 | 0.050 |
| COVID | **1.011** | 1.515 | 1.767 | 0.931 | 1.712 |
| 2022 | 0.502 | 0.819 | 0.489 | 0.502 | 0.150 |

S3-MONTHLY's edge is crisis-concentrated (dot-com +0.149, GFC +0.122 over floor),
neutral in 2022, slight drag in COVID (lag already helps no-gate there). The daily
crisis "wins" of REF-ON (COVID 1.767, 2022 0.819) are lookahead artifacts: they
need same-day or near-same-day fill and shrink/vanish under honest lag for the
fast forms.

## Diagnosis

1. **The fast signal is inherently dead under lag (S4 confirms).** Merely lagging
   the RV_20d input one more day (S4-LAGINPUT, BULL 0.890) does NOT recover value;
   it is ~= the current honest gate (0.929) and below no-gate (1.038). The value
   of a 20-day realized-vol crossover comes from precisely-timed vol-regime turns;
   shifting the fill off the signal bar makes the turn stale. Confirmed dead.
2. **Slower windows help only partially and only at blend level.** S1-60/S1-120/
   S2-EMA all sit BELOW the no-gate floor at BULL-solo level (1.017/0.983/0.953 <
   1.038). They recover roughly half the gap vs the broken current gate but never
   beat simply turning the gate off.
3. **Only the MONTHLY-cadence vol regime (S3) clears the floor on both windows,**
   and it does so marginally (+0.023 clean / +0.033 ext blend) and only via
   crisis episodes (dot-com, GFC). At BULL-solo level S3 (0.993) is still BELOW
   no-gate (1.038); its blend benefit is a timing-diversification interaction with
   CPM, not a sleeve-level vol edge. Its blend MaxDD (-11.59%) equals no-gate
   (it rarely de-risks), so it does not improve drawdown.
4. **Continuous vol-targeting (S5) is the worst non-diagnostic variant** (blend
   1.247, below current honest gate), consistent with the prior `rv_gate_variants`
   rejection. It also requires a fitted 15% target -> OVERFIT-RISK, drop.

## Verdict

The vol-gate idea is **largely NOT salvageable at the BULL-sleeve level under
honest T+1 execution.** Under honest lag, no-gate (REF-OFF) beats every vol-gate
variant at the sleeve (BULL-solo) level. The fast daily crossover is confirmed
inherently lag-fragile, not merely mis-lagged (S4).

The single defensible lag-robust form is **S3-MONTHLY** (monthly-return realized
vol, 12m vs 36m, evaluated once at month-end on lagged closes, held for the month):

- It is the only variant beating the no-gate floor on BOTH clean (+0.023) and
  extended (+0.033) blend Sharpe, with NO scanned/fitted parameter (12/36 monthly
  is convention-locked), zero daily monitoring, and full alignment with the BULL
  monthly-simple philosophy.
- BUT the margin is small (~+0.02-0.03 blend Sharpe), the benefit is
  crisis-concentrated, it does NOT improve drawdown, and it underperforms no-gate
  at the BULL-solo level. This is a weak, marginal win, not a recovery of the
  ~+0.17 BULL / ~+0.09 blend the lookahead manufactured.

### Recommendation (for fixer/oracle, not actioned here)

If same-day-close (MOC) execution is NOT genuinely achievable, **drop the fast
RV_20d vol gate** rather than try to repair it: under honest lag it actively hurts
(blend -0.052, BULL -0.109 vs no-gate). The canary + 13612U trend gates already
provide the crisis protection. If a vol filter is still desired for governance/
crisis comfort, the ONLY lag-robust candidate is the monthly 12m/36m vol regime
(S3) -- accept it only as a marginal, crisis-tilted overlay, not as a Sharpe
driver. Do NOT adopt slower daily crossovers (S1/S2) or continuous vol-targeting
(S5): all sit below no-gate under honest execution.

## Reproduce

```
.venv/bin/python research/lag_robust_vol_gate.py
```

## Caveats

- Close-to-close accounting (no intraday open), consistent with the production
  engine. Strict open-to-open MOO would land between same-day and lagged.
- Crisis sub-window Sharpes are short-sample and noisy; treat directionally. The
  S3 blend edge (+0.02-0.03) is small relative to bootstrap CI on Sharpe -- it is
  "does not hurt and mildly helps in crises", not a robust alpha.
- Blend is the 60/40 two-sleeve CPM-BULL diagnostic (production headline), not the
  60/20/20 three-sleeve; NDX sleeve unaffected by this BULL vol-gate change.
- S5 uses a fitted 15% vol target (overfit-risk); included only as cross-check.
- Pre-2010 extended window uses stitched proxies (see `cpm_live.py:84-103`).
