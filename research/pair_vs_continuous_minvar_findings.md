# 50/50 min-var pair vs continuous min-var weighting (CPM sleeve)

**Config:** CPM sleeve, production universe + vol-adjusted ranker + HYG-or-TIP
canary held fixed (U=1, R=1, C=1); the ONLY toggle is the weighting step
(factor P). `P=1` = equal-weight 50/50 minimum-variance **pair** of the two
lowest-variance survivors (production). `P=0` = **continuous** minimum-variance
weighting over all positive-trend survivors (alternative).

**Execution:** realistic T+1 MOO exact (mooex), 10 bps/side headline, real
yfinance OHLC opens. Cov lookback 504d.
**Windows:** CLEAN 18y (2008-05-30..2026-05-22, 17.98y) and EXT 27y
(1999-03-10.., 27.20y).
**Harness:** `research/pair_vs_continuous_minvar.py` (reuses
`factorial_decomposition_2026_05_30.cpm_wf` logic +
`exec_lag_moo_validation_2026_05_30._segment_returns_conv`). JSON:
`research/pair_vs_continuous_minvar.json`.

**Reproduction check (CLEAN, 10 bps) - exact:**

| scheme | Sharpe | Calmar | MaxDD | anchor |
|---|---|---|---|---|
| pair 50/50 (prod) | 1.2424 | 0.8704 | -16.35% | CPM-solo anchor 1.242 OK |
| continuous min-var | 1.2935 | 0.9618 | -15.15% | factorial no-pair 1.294/0.962/-15.15% OK |

---

## Verdict (headline)

The 50/50 pair is net-negative on Sharpe/Calmar/MaxDD in both windows (already
known). Of the three candidate benefits, **only ONE is a clean, real
improvement: holding/signal stability.** Turnover is NOT improved (near
identical). Concentration is improved only in the worst-case cap sense (max
single weight), not in average diversification. Estimation robustness is a
wash.

| candidate metric | does pair improve? | magnitude (CLEAN / EXT) |
|---|---|---|
| **Stability** (frac months any weight change) | **YES, large** | 0.389 vs 0.810 / 0.423 vs 0.868 -> ~2x fewer trade-months |
| **Concentration** (avg risk-on max single weight) | **YES, cap only** | 0.500 vs 0.628 / 0.514 vs 0.605 |
| Concentration (avg effective N, risk-on) | NO (slightly worse) | 2.000 vs 2.057 / 1.973 vs 2.156 |
| **Turnover** (ann. round-trip sum\|dw\|) | negligible (~2% lower) | 6.34 vs 6.45 / 6.77 vs 6.85 |
| Estimation sensitivity (mean L1 to lookback) | NO (wash / lumpier) | see section 5 |

**Cost break-even (net Sharpe, pair overtakes continuous):** ~**78 bps/side**
(EXT); ~**220 bps/side** (CLEAN, extrapolated beyond tested 0-100 bps - pair
never wins within range). Continuous min-var still wins net Sharpe at 50 bps/side
in BOTH windows. The pair's stability/concentration benefits do NOT pay for
themselves on a Sharpe/cost basis at any realistic illiquid-sleeve cost
(<=50 bps/side).

---

## 1. Turnover and cost drag

Round-trip turnover = annualized sum of |delta weight| per rebalance (charges
both sell and buy side; one-way = half). Cost drag = ann. round-trip x bps/10000.

| window | scheme | ann RT turnover | ann one-way | drag @10 | drag @25 | drag @50 |
|---|---|---|---|---|---|---|
| CLEAN | pair 50/50 | 6.342 | 3.171 | 63.4 bps/yr | 158.5 | 317.1 |
| CLEAN | continuous | 6.452 | 3.226 | 64.5 bps/yr | 161.3 | 322.6 |
| EXT | pair 50/50 | 6.765 | 3.382 | 67.6 bps/yr | 169.1 | 338.2 |
| EXT | continuous | 6.849 | 3.424 | 68.5 bps/yr | 171.2 | 342.4 |

**Finding:** turnover is essentially identical (pair only ~1.7% lower notional).
There is NO cost-efficiency offset from the pair. This is the crux: the pair's
gross-return deficit is never recovered through lower trading cost, because the
two schemes trade roughly the same notional per year.

## 2. Pre-cost vs post-cost performance + cost break-even

| window | scheme | Sharpe 0bps (gross) | Sharpe 10bps (net) | CAGR 0bps | CAGR 10bps |
|---|---|---|---|---|---|
| CLEAN | pair | 1.2985 | 1.2424 | 14.95% | 14.23% |
| CLEAN | continuous | 1.3517 | 1.2935 | 15.31% | 14.57% |
| EXT | pair | 1.2202 | 1.1640 | 14.71% | 13.95% |
| EXT | continuous | 1.2719 | 1.2091 | 14.04% | 13.27% |

Continuous min-var's edge is **GROSS** (real selection/sizing edge): +0.0532
Sharpe at 0 bps (CLEAN), +0.0517 (EXT). Because turnover is near-identical, the
gap barely shrinks as costs rise.

Net-Sharpe gap (pair minus continuous) across cost grid:

| bps/side | 0 | 10 | 25 | 50 | 75 | 100 |
|---|---|---|---|---|---|---|
| CLEAN | -0.0532 | -0.0511 | -0.0479 | -0.0423 | -0.0363 | -0.0301 |
| EXT | -0.0517 | -0.0451 | -0.0351 | -0.0182 | -0.0016 | +0.0143 |

**Break-even where pair overtakes continuous on net Sharpe:**
- EXT: ~77.5 bps/side (interpolated between 75 and 100 bps).
- CLEAN: ~220 bps/side (linear extrapolation; pair never wins within 0-100 bps).

At any realistic illiquid-sleeve cost (10-50 bps/side) continuous min-var wins
net Sharpe in both windows.

## 3. Concentration

Per-rebalance: max single-asset weight and effective N = 1/HHI. "risk-on" =
months holding >=1 non-safe asset (188 of 217 CLEAN; 291 of 327 EXT). Safe-only
months are identical across schemes (single asset, effN 1) and only dilute.

| window | scheme | avg max w (risk-on) | avg effN (risk-on) | avg max w (all) | avg effN (all) | max single ever |
|---|---|---|---|---|---|---|
| CLEAN | pair | 0.500 | 2.000 | 0.567 | 1.866 | 1.000 |
| CLEAN | continuous | 0.628 | 2.057 | 0.678 | 1.916 | 1.000 |
| EXT | pair | 0.514 | 1.973 | 0.567 | 1.865 | 1.000 |
| EXT | continuous | 0.605 | 2.156 | 0.648 | 2.028 | 1.000 |

**Finding (honest):** the pair caps single-asset weight at 0.500 by
construction (vs continuous avg 0.61-0.63 risk-on), so it improves WORST-CASE
concentration. But average effective N is slightly HIGHER (more diversified)
for **continuous** (2.057 vs 2.000 CLEAN; 2.156 vs 1.973 EXT) - it spreads
across 3-4 assets in calm regimes, then concentrates when the optimizer prefers
one low-vol asset. The pair's only true concentration win is the hard cap, not
average diversification. (Both schemes hit max single = 1.0 in the degenerate
single-positive-survivor fallback, which is shared logic.)

## 4. Holding / signal stability

| window | scheme | basket-change freq | frac months any weight change | mean month-to-month L1 |
|---|---|---|---|---|
| CLEAN | pair | 0.389 | 0.389 | 0.528 |
| CLEAN | continuous | 0.500 | **0.810** | 0.537 |
| EXT | pair | 0.423 | 0.423 | 0.564 |
| EXT | continuous | 0.534 | **0.868** | 0.571 |

**Finding (the real win):** continuous min-var re-optimizes weights every month,
so 81% (CLEAN) / 87% (EXT) of months carry SOME weight change even when the held
basket is unchanged. The pair only changes weights when the selected pair flips
(weight change <=> basket change), so it touches only 39% (CLEAN) / 42% (EXT) of
months - roughly **half as many trade-months.** Mean L1 move is nearly equal
(0.528 vs 0.537) because continuous's extra changes are individually small.

This explains the turnover paradox (section 1): the pair concentrates the same
annual notional into fewer, larger, lumpier discrete reshuffles (full 50/50
swaps), while continuous makes frequent tiny adjustments. Same total turnover,
very different number of trade events. The pair's advantage is operational
(fewer trade tickets / rebalance events), not cost.

## 5. Estimation sensitivity (cov lookback 504 -> 480 / 528 d)

Mean L1 weight move when the lookback is perturbed +-24 d (EXT rebalances):

| scheme | lookback 480 mean L1 | 480 max L1 | 528 mean L1 | 528 max L1 |
|---|---|---|---|---|
| pair 50/50 | 0.0183 | 2.000 | 0.0214 | 2.000 |
| continuous | 0.0236 | 0.303 | 0.0217 | 0.227 |

**Finding (honest):** roughly a wash on average magnitude (continuous slightly
more sensitive at 480d, near-equal at 528d). The CHARACTER differs: the pair's
sensitivity is fat-tailed and discrete - a small lookback change occasionally
flips the selected pair, producing a full L1=2.0 swap (~3 such flips across 327
months); continuous never moves more than ~0.30 L1 (smooth reweighting). The
common claim "continuous min-var is more estimation-sensitive" is NOT supported
on average here; the pair is just lumpier when it does react. Not a clean pair
win.

---

## Honest read / recommendation

- **What the pair actually improves:** (1) signal/holding stability - ~2x fewer
  months require any rebalancing trade (39% vs 81% CLEAN); (2) worst-case
  single-asset concentration - hard 0.50 cap vs continuous ~0.63 avg risk-on.
- **What it does NOT improve:** turnover/cost drag (near-identical), average
  diversification (effN slightly worse), estimation robustness (wash).
- **What it costs:** a real GROSS edge for continuous min-var of ~+0.05 net
  Sharpe and ~+0.10 Calmar (CLEAN) that persists across all realistic costs;
  the pair only wins net Sharpe above ~78 bps/side (EXT) or ~220 bps/side
  (CLEAN).
- **Bottom line:** even granting that real illiquid-sleeve costs exceed the
  10 bps headline (say 25-50 bps/side), continuous min-var still wins net Sharpe
  in both windows. The pair's benefits are genuine but **operational/governance
  in nature** (fewer trade events, a hard concentration cap, no optimizer corner
  solutions) - they are not a Sharpe/Calmar/cost justification. Choosing the
  pair is a deliberate trade of ~5 bps of net Sharpe for simpler, more stable,
  capped execution; it is defensible only if those operational properties are
  valued explicitly, not on measured net performance.

**Caveats:** single data vintage (yfinance auto_adjust, stitched BIL/AGG not used
by CPM); cost model is linear per-side notional (no market-impact convexity that
would penalize the pair's lumpier full-swap trades more, or the continuous
scheme's many tiny trades via fixed per-ticket costs - both directions plausible);
break-even assumes both schemes face the same per-side rate. Optimizer corner
behavior (continuous going to a single asset) is bounded but real. Confidence:
high on stability and turnover findings (direct weight accounting); high on the
gross/net edge and break-even (reproduces published anchors exactly); medium on
the concentration interpretation and estimation-sensitivity wash (sensitive to
the +-24 d perturbation choice).
