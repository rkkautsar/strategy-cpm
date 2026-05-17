# CPM-BULL Strategy — Concise Summary

## What it is

Two-sleeve monthly-rebalanced tactical asset allocation, blended 60% CPM + 40% BULL-QQQ.

## Performance

| Window | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| LIVE 18y (2008-2026) | 1.48 | 14.25% | -12.3% |
| EXT 32y (1994-2026) | 1.27 | 13.17% | -15.2% |
| TEST OOS 2017-2026 | 1.63 | 16.85% | -12.3% |
| **Forward expectation** | **0.90-1.20** | **8-12%** | **-15% to -25%** |

vs SPY buy-hold LIVE: Sharpe 0.73, CAGR 13%, MaxDD -41%.

## CPM sleeve (70% capital)

Defensive engine: cross-sectional Faber SMA ranker + min-variance pair selection + canary regime gating.

```python
# Monthly at signal date T (last trading day)
RISKY = [QQQ, IGM, XLE, VBR, SPHQ, XMHQ, XLV, VEA, VWO, GLD, TLT]  # 11
SAFE  = SHV   # single-asset cash mode, ultra-short Treasury (~0.3y duration)
              # unified with BULL-QQQ cash fallback
CANARY = [HYG, TIP, GLD]   # 3-asset any-positive (GLD added 2026 review,
                            # captures real-asset/tail regimes -- see cpm_live.py)
K = 5  # half-of-universe rule

# 1. Faber SMA-distance ranker (NOT 12-1 momentum)
faber_score(asset) = (price[T] - SMA_10mo(asset)[T]) / SMA_10mo(asset)[T]

# 2. Keller HAA weighted momentum for canary
mom_13612U(asset) = (r1 + r3 + r6 + r12) / 4    # canonical unweighted (U = Unweighted)
                    # r_k = total return over past k months

# 3. Canary regime check (HAA-style any-positive)
canary_on = (mom_13612U(HYG) > 0) or (mom_13612U(TIP) > 0) or (mom_13612U(GLD) > 0)

if not canary_on:
    # Defensive: hold 100% SHV cash (ultra-short Treasury, ~0.3y effective duration)
    weights = {SHV: 1.0}
else:
    # Risk-on: rank by Faber SMA distance, take top-K positive
    ranked = sort_descending(RISKY, key=faber_score)
    candidates = [a for a in ranked[:K] if faber_score(a) > 0]
    
    # Fallback for sparse positive momentum
    if len(candidates) == 0:
        weights = {SHV: 1.0}
    elif len(candidates) == 1:
        weights = {candidates[0]: 0.5, SHV: 0.5}
    else:
        pair = min_variance_pair(candidates, lookback_days=756)
        weights = {pair[0]: 0.5, pair[1]: 0.5}
        
        # Hold-buffer (z-score of Faber distance): swap only if
        # new pair member beats prior by HOLD_BUFFER z-units
        z = zscore(faber_score across all candidates)
        for prior in prev_pair:
            if prior in candidates and z(prior) > 0:
                swap_cand = lowest_z_in(new_pair - prev_pair)
                if z(swap_cand) - z(prior) < 2.5:
                    keep prior instead of swap_cand

# 4. Vol target (de-risk only, no leverage)
realized_vol_63d = sqrt(252) * std(daily_returns_of_chosen_basket[-63:])
scale = min(1.0, 0.10 / realized_vol_63d)
weights = {t: w * scale for t, w in weights.items()}

# 5. Unallocated weight goes to default cash (SHV)
weights[SHV] += 1.0 - sum(weights.values())
```

**Note**: Earlier spec used 4-asset best-of-safes rotation
[BIL/SHV/SHY/IEF]. Oracle-v4 review flagged duration ambiguity; ablation
showed rotation captures only ~0.03 Sh (bootstrap noise). Simplified to
SHV-only for unified cash narrative and ultra-short Treasury defensive.

## BULL-QQQ sleeve (30% capital)

Bull-tilt overlay: QQQ when trend + credit canary risk-on, defensive switch in late-cycle inflation, cash otherwise.

```python
# Momentum signals (all at signal date T)
def mom_12_1(asset):  # Antonacci dual momentum
    return price[T-1mo] / price[T-13mo] - 1

def mom_13612U(asset):  # Canonical HAA (13612U per Keller & Keuning 2022)
    r1, r3, r6, r12 = returns over [1, 3, 6, 12] months
    return (r1 + r3 + r6 + r12) / 4    # function name kept for back-compat

# 1. Composite trend filter (12-1 OR 13612U)
trend_ok = (mom_12_1(QQQ) > 0) or (mom_13612U(QQQ) > 0)

# 2. Multi-canary credit/inflation gate (3-asset any-positive)
macro_on = (
    mom_13612U(HYG) > 0
    or mom_13612U(LQD) > 0
    or mom_13612U(TIP) > 0
)

# 3. Late-cycle inflation state (HYG-/LQD-/TIP+)
late_cycle_inflation = (
    mom_13612U(HYG) <= 0
    and mom_13612U(LQD) <= 0
    and mom_13612U(TIP) > 0
)

# 4. Decision
if trend_ok and macro_on:
    target = "XLP" if late_cycle_inflation else "QQQ"
else:
    target = "SHV"

# Equity-strength override REMOVED in oracle-v4 cleanup.
# Was: mom_12_1(QQQ) > expanding_67th_pctile bypass for canary-off+strong-equity
# (Asness tercile). Fired only 10/403 months over 32y; neutral on LIVE
# (-0.013 Sh), marginal EXT help (+0.01 Sh). Removed for spec simplicity
# and to reduce data-mining surface (pre-2005 threshold was unstable).
```

## Combined execution

```python
FCP_WEIGHT  = 0.70  # oracle-v3 Sharpe-optimal; flat surface 60-80% acceptable
BULL_WEIGHT = 0.30

fcp_weights  = run_fcp_sleeve(T)           # dict of {ticker: weight}
bull_weights = run_bull_qqq_sleeve(T)      # dict of {ticker: weight}

portfolio = {}
for t, w in fcp_weights.items():
    portfolio[t] = portfolio.get(t, 0) + FCP_WEIGHT * w
for t, w in bull_weights.items():
    portfolio[t] = portfolio.get(t, 0) + BULL_WEIGHT * w

# Execute at T+1 MOC: sell anything dropping out, buy anything entering
# Cost: 10 bps/side on changed positions
```

## Spec definitions

- **Signal date T**: last trading day of month
- **Trade date**: T+1 MOC (market-on-close next day)
- **12-1 momentum**: total return T-13mo → T-1mo (excludes most recent month)
- **13612U (canonical HAA)**: simple unweighted average = (r1 + r3 + r6 + r12) / 4. Per Keller & Keuning 2022 HAA paper. Function name `sig_13612W` kept for back-compat; alias `sig_13612U` available in cpm_live.
- **Returns**: dividend-adjusted (yfinance Adj Close)
- **Costs**: 10 bps/side on any state change (20 bps round-trip)
- **Rebalance**: monthly only, no intramonth updates
- **Canary state notation**: HYG/LQD/TIP signs in order, e.g. `-/-/+`

## Why each component

| Component | Source | Why |
|---|---|---|
| 12-1 momentum | Antonacci 2014 | Slow trend anchor, anti-whipsaw |
| 13612U canonical | Keller HAA 2022 | Fast re-entry signal |
| Composite OR trend | This spec | Captures both slow-anchor + fast-rescue |
| HYG canary | Keller VAA/DAA | High-yield credit stress proxy |
| LQD canary | This spec extension | Investment-grade credit / duration stress |
| TIP canary | Keller HAA 2022 | Inflation/real-rate regime |
| 3-asset any-positive | This spec extension | Avoids HAA's TIP-only false alarms |
| ~~67th-pct override~~ | REMOVED (oracle-v4 cleanup) | Inert in practice, fired 10/403 months |
| XLP in HYG-/LQD-/TIP+ | Neuberger Berman 2024 + data | Late-cycle inflation defensive |
| SHV cash mode | Standard | Zero duration risk on cash sleeve |

## Headline risk

- **MaxDD bounded** by canary-cash regime + CPM defensive bias
- **COVID 2020 weakness**: blend -1.6% (vs SPY -9.2%) due to CPM absorbing BULL whip
- **Structural lag** on V-shaped recoveries (canary slow to re-engage)
- **BULL CAGR (20% LIVE)** is QQQ-era artifact, not forward expectation
- **Tail risk** in 2022-style rate-rise regimes (BULL drew -16.8% intramonth)

## What this strategy is NOT

- Not a tax-optimized vehicle (frequent rotation = short-term gains)
- Not for taxable accounts unless tax-deferred wrapper available
- Not leveraged (MAX_LEVERAGE=1.0 by design)
- Not optimized for absolute return (designed for risk-adjusted + DD control)
- Not live-tested (paper-trading only; forward live performance unknown)
