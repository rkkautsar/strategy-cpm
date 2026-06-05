# NDX Sleeve: Monthly-Set, Intramonth-Triggered Vol Stop-Loss

Research-only. No prod/memo edits, no commit. Single in-sample, high overfit
caution (path-dependent design, k/z/level/window DoF).

## Question / Hypothesis

Does a MONTHLY-SET, INTRAMONTH-TRIGGERED per-stock vol stop-loss -- the
intramonth complement to monthly vol-targeting -- cut the NDX sleeve's ~-31%
MaxDD by catching mid-month single-stock crashes that monthly exposure-scaling
cannot see, WITHOUT proportional return loss or excessive whipsaw drag?

Literature framing:
- Han-Zhou-Zhu ("Taming Momentum Crashes"): stops on momentum names can cut
  crashes and raise Sharpe.
- Kaminski-Lo (2014): stops help only when returns have momentum/serial
  structure; they hurt under random-walk paths once cost + whipsaw are charged.

## Method

- Engine: prod `ndx_sleeve_live` selection unchanged (13612U momentum top-5 EW,
  TIP/SPY/RV gate, best-of-safe, T+1 MOO, 10bps/side, delisting haircut, PIT
  constituents). Reproduced PROD: clean Sharpe 1.273, MaxDD -31.39% (target
  ~1.281 / -31.4%), stress Sharpe 0.794.
- New daily-path-aware overlay (`research/cpm_ndx_stoploss_harness.py`):
  at each rebalance set a per-stock stop on CUMULATIVE intramonth return from
  the rebalance reference close; walk daily; on breach, rotate that stock's
  slot to the period's best-of-safe for the rest of the month (no re-entry).
- Stop level set from LAGGED daily stats (window W=63d, up to sig_d, no
  look-ahead): sigma_monthly = std*sqrt(21), mu_monthly = mean*21.
  - Vol-multiple: exit if cum_ret < -k * sigma_monthly  (k in 1.5, 2, 3)
  - Expected-band: exit if cum_ret < (mu_monthly - z*sigma)  (z in 1, 2)
- Fill: CONSERVATIVE. Breach detected at close t (no intraday/look-ahead);
  liquidation at t+1 close-to-close (prod T+1 MOO convention). The breach-day
  move + next-day gap are borne by the stock; we do NOT assume a clean
  fill-at-stop-level. A fill-at-stop model would be strictly more favourable.
- Metrics: Sharpe, Sortino, CVaR-ratio, CAGR, vol, MaxDD, Calmar, Martin,
  annualized turnover, stops/yr, whipsaw% (= % of stops where the stock's price
  at the next rebalance exceeded its exit price -> sold low, rebounded).
- Paired block bootstrap vs PROD (B=2000, block=21, seed=42) on clean window.
- 3-segment walk-forward across the clean window.
- Run scripts: `research/cpm_ndx_stoploss_run.py`; JSON in
  `research/cpm_ndx_stoploss_results.json`.

### Inputs / data + caveats
- `data/ndx_constituents/prices.parquet` (auto-adjusted Close, ~190 names by
  2024, from 1995). Daily Close only -> no true intraday stop fills; T+1 close
  is the conservative proxy. PIT membership via index_constitution (>=2006);
  pre-2006 the sleeve uses SPY proxy, so dot-com is CONTEXT only.
- PROD and EVERY stop variant run on the IDENTICAL dataset (apples-to-apples).
- Scope-relaxed: goal is the comparable DIRECTIONAL verdict, not a publishable
  absolute number.

## Results

### Config table -- CLEAN (2008-04 -> 2026-05)

| Variant        | Sharpe | Sortino | CVaR | CAGR%  | Vol%  | MaxDD%  | Calmar | Martin | Turn | Stp/yr | Whip% |
|----------------|--------|---------|------|--------|-------|---------|--------|--------|------|--------|-------|
| PROD (no stop) | 1.273  | 1.950   | 8.35 | 31.15  | 23.52 | -31.39  | 0.99   | 4.20   | 9.38 | 0.00   | --    |
| VolMult k=1.5  | 1.267  | 1.932   | 8.26 | 30.56  | 23.22 | -31.39  | 0.97   | 4.46   | 9.70 | 1.02   | 61    |
| VolMult k=2.0  | 1.278  | 1.961   | 8.40 | 31.18  | 23.43 | -31.39  | 0.99   | 4.42   | 9.44 | 0.22   | 33    |
| VolMult k=3.0  | 1.271  | 1.946   | 8.34 | 31.07  | 23.50 | -31.39  | 0.99   | 4.18   | 9.39 | 0.07   | 50    |
| ExpBand z=1    | 1.246  | 1.991   | 8.71 | 19.97  | 15.62 | -22.26  | 0.90   | 2.71   | 15.54| 13.29  | 57    |
| ExpBand z=2    | 1.309  | 2.004   | 8.56 | 30.29  | 22.14 | -30.84  | 0.98   | 4.36   | 10.38| 2.70   | 57    |

### Config table -- STRESS (1999-01 -> 2026-05)

| Variant        | Sharpe | Sortino | MaxDD%  | CAGR% | Calmar | Stp/yr | Whip% |
|----------------|--------|---------|---------|-------|--------|--------|-------|
| PROD (no stop) | 0.794  | 1.122   | -75.94  | 16.18 | 0.21   | 0.00   | --    |
| VolMult k=1.5  | 0.779  | 1.096   | -75.94  | 15.65 | 0.21   | 1.02   | 61    |
| VolMult k=2.0  | 0.796  | 1.127   | -75.94  | 16.20 | 0.21   | 0.22   | 33    |
| VolMult k=3.0  | 0.792  | 1.120   | -75.94  | 16.13 | 0.21   | 0.07   | 50    |
| ExpBand z=1    | 0.607  | 0.826   | -75.94  | 8.98  | 0.12   | 13.29  | 57    |
| ExpBand z=2    | 0.800  | 1.123   | -75.94  | 15.60 | 0.21   | 2.70   | 57    |

(Stress MaxDD -75.94% is a pre-2006 SPY-proxy-era episode unaffected by any
single-stock stop; gate, not stops, drives crisis behaviour there.)

### Per-crisis MaxDD% (context, path-dependent)

| Crisis        | PROD | k=1.5 | k=2  | k=3  | z=1  | z=2  |
|---------------|------|-------|------|------|------|------|
| dotcom(00-02) | -32.0| -32.0 | -32.0| -32.0| -32.0| -32.0|
| GFC(07-09)    | -6.2 | -6.2  | -6.2 | -6.2 | -6.2 | -6.2 |
| COVID(20)     | -4.7 | -4.7  | -4.7 | -4.7 | -4.7 | -4.7 |
| 2022          | -0.3 | -0.3  | -0.3 | -0.3 | -0.3 | -0.3 |
| 2025          | -2.9 | -2.9  | -2.9 | -2.9 | -2.9 | -2.9 |

In every macro crisis the gate has already rotated the sleeve to safe, so
single-stock intramonth stops do not bind -> identical MaxDD. The gate, not a
stop, handles macro drawdowns.

### Paired block bootstrap vs PROD (clean, B=2000)

| Variant      | dSharpe (95% CI)          | p>0  | dSortino p>0 | dCVaR p>0 | dMaxDD (pp) p>0 |
|--------------|---------------------------|------|--------------|-----------|-----------------|
| VolMult k=1.5| -0.006 [-0.045, +0.034]   | 0.37 | 0.31         | 0.28      | +0.7  0.54      |
| VolMult k=2.0| +0.005 [-0.018, +0.028]   | 0.67 | 0.70         | 0.68      | +0.4  0.56      |
| VolMult k=3.0| -0.002 [-0.007, +0.002]   | 0.25 | 0.26         | 0.26      | -0.1  0.26      |
| ExpBand z=1  | -0.024 [-0.321, +0.261]   | 0.44 | 0.59         | 0.63      | +8.0  0.93      |
| ExpBand z=2  | +0.036 [-0.032, +0.110]   | 0.83 | 0.80         | 0.79      | +1.6  0.81      |

No variant clears significance on Sharpe / Sortino / CVaR -- every CI crosses 0
(all p<0.85). Only ExpBand z=1 shows a robust MaxDD reduction in the bootstrap
(+8.0pp, p=0.93, soft path-dependent CI), but see walk-forward + return cost.

### Walk-forward (3 clean segments)

| Seg / window            | PROD Sh / DD     | k=2 Sh / DD     | z=1 Sh / DD     | z=2 Sh / DD     |
|-------------------------|------------------|-----------------|-----------------|-----------------|
| 1: 2008-04 .. 2014-05   | 1.160 / -17.3    | 1.175 / -15.4   | 1.327 / -11.8   | 1.211 / -14.4   |
| 2: 2014-05 .. 2020-05   | 1.249 / -17.0    | 1.248 / -17.0   | 0.878 / -15.9   | 1.290 / -16.9   |
| 3: 2020-05 .. 2026-05   | 1.468 / -31.4    | 1.470 / -31.4   | 1.491 / -22.3   | 1.489 / -30.8   |

ExpBand z=1 is UNSTABLE: best-in-class in Seg1/Seg3 but Sharpe 0.878 (vs PROD
1.249) in the 2014-2020 grind -- whipsaw drag torches a quiet regime. Classic
overfit signature. VolMult k=2 == PROD in all 3 segments. ExpBand z=2 is the
only "active" variant that is marginally >= PROD in all 3 (but within noise).

## Answers

(a) Does it cut the -31% MaxDD without proportional return loss / whipsaw?
   NO for the headline drawdown. The PROD worst clean DD is the Feb 12 -> Mar 29
   2021 momentum unwind; the vol-multiple stops made ZERO difference there
   (sum |ret diff| = 0.0 in the DD window). That drawdown is a SLEEVE-WIDE,
   multi-week move that STRADDLES a monthly rebalance, so a per-stock intramonth
   cumulative stop (reference reset each month) structurally cannot catch it.
   The only variant that cuts MaxDD (ExpBand z=1: -31.4 -> -22.3) does so by
   hair-trigger de-risking (13.3 stops/yr) that also slashes CAGR 31% -> 20%
   and worsens BOTH Calmar (0.99->0.90) and Martin (4.20->2.71) -- it cuts the
   DD by being out of the market, not by smart crash-catching.

(b) Sharpe/Sortino net of turnover + whipsaw?
   No significant improvement. Best Sharpe is ExpBand z=2 (1.309 vs 1.273),
   bootstrap dSharpe +0.036 with CI crossing 0 (p=0.83) -- noise. Tight stops
   (z=1) destroy risk-adjusted return net of cost+whipsaw, matching Kaminski-Lo:
   at this horizon the intramonth path lacks exploitable downside serial
   structure once 57% whipsaw + turnover are charged.

(c) Best stop level (sensitivity, not optimization)?
   - VolMult k>=2: near no-op. Breaches are RARE among momentum-selected NDX
     names (k=2: 0.22 stops/yr) -> indistinguishable from PROD.
   - VolMult k=1.5: more firing (1.02/yr) but 61% whipsaw -> slight drag.
   - ExpBand z=1: only DD-cutter, but return-destroying + walk-forward-unstable.
   - ExpBand z=2: most benign active variant; marginal Sharpe/Sortino uplift,
     walk-forward-consistent, trivial DD effect -- but within noise.
   No level is a robust winner. Sensitivity is monotone and unremarkable: looser
   = no-op, tighter = whipsaw drag.

(d) Whipsaw cost?
   High where stops bind: 33-61% of stops are sold-low-then-rebound. Tight
   variants (z=1, z=2, k=1.5) all ~57-61% whipsaw -> roughly half of all stop
   trades are round-trip losses paid in spread + adverse selection.

## Verdict

A monthly-set intramonth per-stock vol stop-loss does NOT cut the NDX sleeve
MaxDD net of cost, whipsaw, and OOS. Two structural reasons:
1. The headline -31% drawdown is a SLEEVE-WIDE, multi-week, cross-rebalance
   momentum unwind -- not an idiosyncratic single-name intramonth crash. A
   per-stock stop whose reference resets each month is aimed at the wrong
   failure mode.
2. The events the stop IS designed for (risk-ON single-name intramonth blowups)
   are rare among 13612U-momentum-selected leaders and already capped at ~4% of
   portfolio (20% slot x 20% sleeve), so even when caught the benefit is tiny
   and ~half are whipsaws.

Net: loose stops are no-ops; tight stops trade return + Calmar/Martin for a DD
reduction and are walk-forward-unstable. No variant is bootstrap-significant on
Sharpe/Sortino/CVaR.

Conceptual comparison to vol-targeting: vol-targeting scales WHOLE-SLEEVE
exposure on realized/forecast vol and therefore directly attacks the sleeve-wide
multi-week drawdowns that actually drive the -31% MaxDD. The intramonth
single-name stop addresses a different, rarer, already-capped risk. They are NOT
substitutes; the stop is at best a minor complement for idiosyncratic single-name
crashes, and on this NDX sleeve that complement does not pay for itself.
Recommendation: do NOT adopt an intramonth per-stock vol stop; if drawdown
control is the goal, pursue sleeve-level vol-targeting / exposure-scaling
(the existing DD circuit family) instead.

Confidence: MEDIUM-HIGH on direction (consistent across clean/stress/bootstrap/
walk-forward; PROD reproduced). Absolute numbers are dataset-limited (adjusted
Close only, no intraday fills, partial PIT pre-2006) per scope relaxation.
