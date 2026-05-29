# 60/40 CPM-BULL same-day signal->execution lookahead audit

Date: 2026-05-30
Analyst role (read-only): no production file changed, no spec change, no commit.
Throwaway harness: `research/lookahead_audit_2026_05_30.py`.

## Question

Every headline Sharpe assumes the monthly signal (canary, Faber rank, RV gate,
trend) is computed AND executed on the SAME month-end close T. Does the 60/40
CPM-BULL headline Sharpe survive a realistic 1-trading-day execution lag
(fill at t+1)?

## Engine timing alignment (where the lookahead lives)

Both sleeves share one convention:

- Signal computed at month-end close T from data `loc[:sig_d]` inclusive of T.
  - CPM: `cpm_live.py:339` (`monthly = close_panel.loc[:sig_d]...`), weights
    via `compute_target_weights` (`cpm_live.py:318`).
  - BULL: `bull_qqq_live.py:145` (`monthly = close_panel.loc[:sig_d]...`),
    weights via `compute_bull_qqq_weights` (`bull_qqq_live.py:141`).
- Weights applied from `apply_from = future[0]` = T+1 (first trading day after T):
  - CPM: `cpm_live.py:465-468` (`apply_from = future[0]`).
  - BULL: `bull_qqq_live.py:209` (`apply_from = future[0]`).
- Returns are `close.pct_change()`, so the return indexed at T+1 equals
  `close[T+1]/close[T]-1` (`cpm_live.py:497`, `bull_qqq_live.py:194`).

### The catch

The code LABELS this "T+1 OPEN / next-day MOO" (`cpm_live.py:446-451`,
`bull_qqq_live.py:184-186`), but because the new weights are applied starting at
the T+1 row and the T+1 return is the close[T]->close[T+1] move, the new basket
economically earns from **close[T]**. That requires rebalancing at the same
close T that produced the signal = **same-day-close (MOC) execution**. The "T+1"
label refers to the index row, not the economic fill bar. So the baseline = the
production engine = same-day-close fill.

### Lag convention used here

- `exec_lag=0` (BASELINE = production): apply_from = future[0] = T+1; new
  weights earn close[T]->close[T+1]; effective fill at close[T] (same-day).
- `exec_lag=1` (LAGGED, realistic): apply_from = future[1] = T+2; new weights
  earn close[T+1]->close[T+2]; effective fill at close[T+1] = one full trading
  day after the signal close (realistic next-day / next-close execution).

This is the minimal, defensible 1-trading-day shift of the signal->return
alignment. Signal/weight logic is reused UNCHANGED; only application timing moves.

## Baseline reproduces production (validation)

| sleeve | prod engine Sharpe (clean 18y) | harness exec_lag=0 | max abs daily diff |
|---|---|---|---|
| CPM  | 1.2626 | 1.2626 | 0.000 (exact) |
| BULL | 1.0989 | 1.1005 | 0.002 (one-day cost-timing edge) |

CPM reproduces exactly. BULL differs by a single 20bps cost-day (immaterial,
0.0016 Sharpe). Baseline is trustworthy.

## Baseline vs lagged (Sharpe / CAGR / MaxDD / Calmar), per sleeve

Costs 10bps/side, pure unlevered 60% CPM / 40% BULL, no vol cap.

### CLEAN 18y (2008-05-30 -> 2026-05-22)

| series | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---|---|---|
| CPM base | 1.266 | 14.58% | -15.41% | 0.946 |
| CPM lag  | 1.240 | 14.24% | -15.77% | 0.903 |
| CPM delta | -0.026 | -0.34% | -0.36% | -0.043 |
| BULL base | 1.103 | 11.80% | -12.02% | 0.982 |
| BULL lag  | 0.929 |  9.78% | -15.64% | 0.625 |
| BULL delta | -0.173 | -2.02% | -3.62% | -0.356 |
| BLEND base | 1.351 | 13.60% | -9.82% | 1.385 |
| BLEND lag  | 1.258 | 12.58% | -10.00% | 1.257 |
| BLEND delta | -0.093 | -1.02% | -0.19% | -0.128 |

### EXTENDED ~27y (1999-03-10 -> 2026-05-22, stitched proxies pre-2010)

| series | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---|---|---|
| CPM base | 1.194 | 14.29% | -15.91% | 0.898 |
| CPM lag  | 1.156 | 13.82% | -17.37% | 0.796 |
| CPM delta | -0.037 | -0.48% | -1.45% | -0.103 |
| BULL base | 0.980 | 10.27% | -12.49% | 0.823 |
| BULL lag  | 0.841 |  8.68% | -15.64% | 0.555 |
| BULL delta | -0.139 | -1.59% | -3.16% | -0.268 |
| BLEND base | 1.280 | 12.84% | -11.79% | 1.089 |
| BLEND lag  | 1.195 | 11.91% | -12.06% | 0.988 |
| BLEND delta | -0.085 | -0.93% | -0.26% | -0.101 |

### Stress windows (blend deltas in Sharpe)

| window | CPM dS | BULL dS | BLEND dS | note |
|---|---|---|---|---|
| dot-com (2000-03..2002-10) | -0.099 | -0.039 | -0.088 | mild |
| GFC (2008-05-30..2009-06-30) | -0.125 | **-0.322** | **-0.218** | trend-flip timing |
| COVID (2020-02-01..2020-04-30) | +0.227 | +0.252 | **+0.252** | lag HELPS (avoids whipsaw) |
| 2022 (2022-01-01..2022-12-31) | **-0.331** | 0.000 | **-0.329** | CPM rebalance-timing |

(Stress base/lag absolute values in the harness stdout.)

## Diagnosis: which signal carries the lookahead

Targeted gate-ablation on the BULL sleeve (monkeypatched gates, harness reuse):

1. **RV_20d crossover gate = the steady-state (clean) culprit.**
   BULL clean lag delta -0.173. Disable the RV gate (`_vol_gate_ok`,
   `bull_qqq_live.py:104-112`, fast 20d vs 252d realized-vol crossover using
   daily returns up to close[T]) and the clean lag delta collapses to **+0.001**.
   A 20-day realized-vol gate is fast-moving; same-day execution lets it catch
   vol-regime turns precisely, and that edge evaporates under a 1-day lag.

2. **SPY 13612U monthly TREND flip = the GFC/crash culprit.**
   GFC BULL lag delta -0.322 is unchanged when RV is disabled, and is fully
   reproduced by the trend gate alone (canary+RV off -> -0.322). The monthly SPY
   13612U trend flip (`_spy_trend_ok`, `bull_qqq_live.py:93-101`) lands at a
   month-end boundary adjacent to a large daily move (Oct/Nov 2008); shifting
   the fill one day eats an extra crash day before going defensive. Canary
   (`_macro_gate`/`_canary_state`) contributes similarly (-0.302 canary-only).

3. **CPM sleeve is structurally robust.** Clean lag delta only -0.026; it uses
   slow monthly signals (Faber SMA + 252d vol-adjusted ranker + 13612U canary +
   504d min-var pair). Its stress deltas (2022 -0.331, GFC -0.125) are
   monthly-rebalance-timing luck around sharp moves, not a fast-signal lookahead.

## Verdict: PARTIAL (holds-with-cost at blend level; BULL sleeve carries it)

- Headline 60/40 blend Sharpe **survives** the realistic 1-day lag in the full
  windows: clean 1.351 -> 1.258 (-0.093), extended 1.280 -> 1.195 (-0.085).
  Both stay well above 1.2; CAGR cost ~1%/yr; MaxDD/Calmar barely move. The
  -0.093 clean drop sits right at the ~0.1 "collapse" threshold but does not
  break the strategy.
- The lookahead is **real and concentrated in the BULL sleeve**: BULL standalone
  drops -0.173 clean / -0.139 extended (a sleeve-level near-collapse), driven by
  the fast RV_20d gate. CPM is essentially lag-immune (-0.026).
- **Crisis windows are where same-day fills flatter the most**: GFC blend
  -0.218, 2022 blend -0.329 (the latter via CPM timing). COVID is the exception
  where the lag actually HELPS (+0.252), i.e. same-day execution whipsawed.

### Recommendation (for fixer/oracle, not actioned here)

- The "T+1 OPEN" docstrings (`cpm_live.py:446-451`, `bull_qqq_live.py:184-186`)
  are economically misleading: the engine fills same-day-close. Either (a) move
  apply_from to future[1] for an honest 1-day lag, accepting ~-0.09 blend Sharpe,
  or (b) keep MOC but relabel and justify same-day-close as achievable (place MOC
  order seconds before close on near-final prices). The RV_20d gate is the most
  fragile component if same-day execution is not truly achievable.

## Reproduce

```
.venv/bin/python research/lookahead_audit_2026_05_30.py
```

## Caveats

- Close-to-close accounting (no intraday open prices), consistent with the
  production engine; a strict open-to-open MOO fill would land between baseline
  and lagged.
- Stress sub-window Sharpes are short-sample and noisy; treat directionally.
- Pre-2010 extended window uses stitched mutual-fund proxies (HYG<-VWEHX,
  TIP<-VIPSX, SHV<-VFISX, IEF<-VFITX, TLT<-VUSTX, GLD/QQQ stitches); see
  `cpm_live.py:84-103`.
- BULL cost model micro-diff (0.0016 Sharpe) vs production; immaterial.
```
