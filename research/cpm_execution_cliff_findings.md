# CPM Execution Cliff: Month-End-Reversal Attribution

Read-only analyst investigation. Reuses production signal/weight functions from
`cpm_live.py` unchanged; varies only rebalance timing and decomposes where P&L
is earned. No production or memo files were edited; nothing was committed.

- Harness: `research/cpm_execution_cliff.py` (extends `research/cpm_robust_lookahead.py`)
- Data/artifacts: `research/cpm_execution_cliff_findings.json`
- Run: `.venv/bin/python research/cpm_execution_cliff.py`
- Convention: close-to-close accounting, `exec_lag=0` (same convention as the
  prior part2 rebalance-day battery, so the cited cliff is reproduced
  apples-to-apples). Cost 10 bps/side. Clean window 2008-05-30..2026-05-22;
  extended window from 1999-03-10. The realistic T+1 MOO convention yields
  EOM Sharpe 1.191 vs the cc 1.206 used here; the cliff shape is identical.

## Question / hypothesis

Robustness showed a sharp rebalance-day sensitivity (EOM Sharpe 1.21 -> EOM+1
1.01 -> +2 0.97 -> +3 0.91). Losing ~0.30 Sharpe from a 3-day execution slip on
liquid monthly-rebalanced ETFs is suspicious. Hypothesis: the EOM edge partly
captures the turn-of-month / month-end microstructure premium rather than being
purely robust momentum-timing skill.

## 1. Wider rebalance-day battery (Sharpe / Calmar / MaxDD)

Signal and execution shifted to EOM-2, EOM-1, EOM, EOM+1, EOM+2, EOM+3, plus a
mid-month rebalance (11th business day) and the first business day of month.

Clean window (2008-2026):

| Config       | Sharpe | Calmar | MaxDD  | CAGR  |
|--------------|--------|--------|--------|-------|
| eom-2        | 1.012  | 0.699  | -0.163 | 0.114 |
| eom-1        | 1.088  | 0.665  | -0.183 | 0.122 |
| **eom**      | **1.206** | **1.111** | **-0.123** | **0.136** |
| eom+1        | 1.013  | 0.745  | -0.156 | 0.116 |
| eom+2        | 0.975  | 0.563  | -0.198 | 0.111 |
| eom+3        | 0.909  | 0.543  | -0.187 | 0.101 |
| mid_bdom11   | 0.929  | 0.419  | -0.258 | 0.108 |
| first_bdom1  | 1.013  | 0.745  | -0.156 | 0.116 |

Extended window (1999-2026):

| Config       | Sharpe | Calmar | MaxDD  |
|--------------|--------|--------|--------|
| eom-2        | 1.098  | 0.715  | -0.173 |
| eom-1        | 1.097  | 0.619  | -0.197 |
| **eom**      | **1.244** | **0.864** | **-0.163** |
| eom+1        | 1.143  | 0.759  | -0.173 |
| eom+2        | 1.074  | 0.618  | -0.198 |
| eom+3        | 1.051  | 0.633  | -0.187 |
| mid_bdom11   | 0.970  | 0.434  | -0.258 |
| first_bdom1  | 1.143  | 0.759  | -0.173 |

Reading: EOM is a knife-edge **spike**, not a smooth momentum plateau. Both
sides of month-end (EOM-2/-1 before; EOM+1/+2/+3 after) and the mid-month
rebalance all sit in a ~0.91-1.10 band. Only the exact month-end print reaches
1.21 (clean) / 1.24 (ext). The Calmar/MaxDD gap is even starker: EOM MaxDD
-0.123 and Calmar 1.11, versus mid-month MaxDD -0.258 and Calmar 0.42. A signal
that were genuinely insensitive momentum timing would not collapse ~0.2-0.3
Sharpe and double its drawdown from a 1-3 day calendar shift on liquid ETFs.

Mid-month does NOT preserve the edge (0.93 clean). This points to month-end
specific timing, not general momentum timing.

## 2. Reversal attribution: where is the P&L earned?

Decompose each config's daily returns by trading-day-since-rebalance. For the
EOM config, day-1 after rebalance is the first trading day of the month -- the
turn-of-month (TOM) window. For mid-month, day-1 is an ordinary mid-month day.

Mean daily return by day-since-rebalance (clean, basis points):

| Config     | d1   | d2  | d3  | d4  | d5   | d6  | d7  | d8  | d9  | d10  |
|------------|------|-----|-----|-----|------|-----|-----|-----|-----|------|
| eom        | 14.9 | 7.6 | 0.5 | 4.2 | 6.9  | 6.2 | 6.6 | 8.2 | 8.2 | 5.3  |
| mid_bdom11 | 0.9  | 1.2 | 1.1 | 9.5 | -1.3 | 1.5 | 1.6 | 3.2 | 6.3 | 10.4 |

Early-window P&L share and counterfactual Sharpe (clean):

| Config     | day-1 share | first-5 share | Sharpe excl first 5 | day-1 standalone Sharpe |
|------------|-------------|---------------|---------------------|-------------------------|
| eom        | 13.3%       | 30.4%         | 1.122               | 3.14                    |
| mid_bdom11 | 0.9%        | 12.3%         | 1.044               | 0.22                    |
| eom+1      | -0.9%       | 13.6%         | 1.163               | -0.19                   |

Extended window confirms the pattern: EOM first-5 share 33.6% (first-3 22.8%),
mid-month first-5 share 12.8% (first-3 3.2%).

Reading:

- The EOM config earns **14.9 bp on trading-day-1** of the month versus a
  rest-of-month baseline of ~4.9 bp/day -- roughly 3x. That single day has a
  standalone annualized Sharpe of 3.14 and carries 13.3% of total clean P&L
  (one day out of ~21). This is the documented turn-of-month effect, captured
  because the strategy holds a freshly-rebalanced basket through TD1.
- The mid-month config shows **no** such early spike (day-1 = 0.9 bp, standalone
  Sharpe 0.22). Its returns are flat ~5 bp/day across the cycle. Same selection
  engine, same universe -- the only difference is calendar alignment.
- The EOM+1 config actively MISSES the TOM premium: its day-1 (= TD2 of month)
  is -0.9 bp, because the turn-of-month day was earned under the prior basket
  before the slipped rebalance applied.

So a disproportionate share of the EOM edge is earned in the first trading
day(s) after month-end -- consistent with turn-of-month / microstructure
capture, not with rest-of-month momentum.

## 3. Verdict

**(b) Partly month-end microstructure (turn-of-month) capture, layered on top of
a genuine but lower momentum core.**

Two components:

1. Robust momentum core (~1.0-1.1 Sharpe). Excluding the first 5 days of each
   EOM holding period still leaves Sharpe 1.12; any nearby rebalance day
   (EOM-2/-1, EOM+1, mid-month) lands in the ~0.91-1.10 band. The selection
   engine has real edge that survives timing perturbation. This part carries a
   normal execution-discipline cost.

2. Turn-of-month kicker (~0.10-0.20 Sharpe, calendar-dependent). The jump from
   the ~1.0-1.1 base to the 1.21 (clean) / 1.24 (ext) headline comes almost
   entirely from aligning the rebalance so the fresh basket holds through the
   first trading day of the month. Removing TD1 alone drops Sharpe 1.206 ->
   1.103 (~0.10). The full gap to the immediate neighbors' average
   (eom-1 1.088, eom+1 1.013 -> ~1.05) and to mid-month (0.93) is ~0.15-0.28.
   This kicker is turn-of-month microstructure, not momentum-timing skill.

How much of the 1.19/1.21 headline is month-end-timing-dependent:

- Direct removal of trading-day-1: ~0.10 Sharpe (1.206 -> 1.103), i.e. ~8% of
  the headline and ~13% of clean P&L.
- Knife-edge spike vs nearby rebalance days / mid-month: ~0.15-0.28 Sharpe
  (~12-23% of the headline) is contingent on exact month-end alignment.
- Honest range: roughly **0.10-0.20 of the headline Sharpe (~8-17%) is
  turn-of-month microstructure capture**, not robust momentum timing. The
  defensible robust-momentum core is ~1.0-1.1.

OOS / reliability implications:

- The headline 1.19-1.21 assumes you reliably trade at/near month-end and hold
  the new basket through the first trading day. A 1-day execution slip forfeits
  the TOM kicker AND drifts the signal date, costing ~0.19 Sharpe (EOM 1.21 ->
  EOM+1 1.01). That is the execution cliff.
- The turn-of-month effect is well-documented but has weakened over recent
  decades and is execution-sensitive; treating the full 1.19-1.21 as durable OOS
  momentum alpha would over-state the edge. Budget the durable component at
  ~1.0-1.1 and treat the remainder as a calendar premium that requires
  disciplined month-end execution to harvest and may decay.
- Realistic T+1 MOO execution still captures most of the day-1 close-to-close
  TOM premium (EOM moo 1.191 vs cc 1.206), so the kicker is harvestable in
  practice -- but only if execution does not slip past the first trading day.

## Caveats and confidence

- Confidence HIGH on direction: the day-1 spike (14.9 bp, standalone Sharpe 3.1,
  13% of P&L) versus the flat mid-month profile is unambiguous and replicates in
  both windows with the identical selection engine.
- Confidence MEDIUM on the exact magnitude split (0.10 vs 0.20): the headline
  jump mixes two effects -- TOM capture and signal-date freshness (mid-month
  uses a partial-month momentum bar) -- which are not cleanly separable. The
  range brackets both attributions (day-1 removal ~0.10; neighbor/mid-month gap
  ~0.15-0.28).
- This is a single strategy on one universe; not cost-stressed beyond 10 bps,
  not slippage-modeled on month-end close fills (where TOM crowding can widen
  spreads -- a further reason the kicker may under-deliver live).
- Throwaway research artifacts only; no production behavior changed.
