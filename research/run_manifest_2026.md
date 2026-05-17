# CPM-BULL Run Manifest (current spec, 2026)

Reproducible specification of the strategy as it stands. NOT versioned
(nothing has run live or been published; this is the current research
candidate state).

## Blend

```
CPM sleeve weight:   0.70
BULL sleeve weight:  0.30
```

## Signals

```
mom_12_1(asset):     price[T-1mo] / price[T-13mo] - 1
                     (Antonacci dual momentum, total-return adjusted)

mom_13612U(asset):   (r1 + r3 + r6 + r12) / 4
                     where r_k = price[T] / price[T-k_mo] - 1
                     (canonical HAA per Keller & Keuning 2022, total-return adjusted)
                     Function name in code: sig_13612W (back-compat); alias sig_13612U

faber_score(asset):  (price[T] - SMA_10mo) / SMA_10mo
                     (Faber 2007 SMA-distance, total-return adjusted)
```

## CPM sleeve (70% capital)

```
RISKY universe (11): QQQ, IGM, XLE, VBR, SPHQ, XMHQ, XLV, VEA, VWO, GLD, TLT
CANARY assets:       HYG, TIP, GLD     # 3-asset any-positive 13612U
SAFE pool:           SHV (single-asset, zero duration)

canary_on = mom_13612U(HYG) > 0 or mom_13612U(TIP) > 0 or mom_13612U(GLD) > 0

if not canary_on:
    fcp_weights = {SHV: 1.0}
else:
    ranked = sort_desc(RISKY, by=faber_score)
    candidates = [a for a in ranked[:K=6] if faber_score(a) > 0]

    if len(candidates) == 0:
        fcp_weights = {SHV: 1.0}
    elif len(candidates) == 1:
        fcp_weights = {candidates[0]: 0.5, SHV: 0.5}
    else:
        pair = min_variance_pair(candidates, lookback=756d)
        fcp_weights = {pair[0]: 0.5, pair[1]: 0.5}

        # Hold-buffer (deterministic, leg-level)
        if prev_pair is not None:
            z = zscore(faber_score across positive_candidates)
            new_set = set(pair)
            for prior in prev_pair:
                if prior in new_set:           continue   # already kept
                if prior not in universe:      continue   # delisted
                if faber_score(prior) <= 0:    continue   # stale, must drop
                swap_cands = [a for a in new_set if a not in prev_pair]
                if not swap_cands:             continue
                swap = min(swap_cands, key=lambda a: z[a])
                if z[swap] - z[prior] < 2.5:           # within HOLD_BUFFER
                    new_set.discard(swap)
                    new_set.add(prior)
            fcp_weights = {a: 0.5 for a in list(new_set)[:2]}

# Vol cap (de-risk only, sleeve-level)
realized_vol = std(daily_total_returns[fcp_basket, last 63d]) * sqrt(252)
scale = min(1.0, 0.10 / realized_vol)   # MAX_LEVERAGE = 1.0
fcp_weights = {t: w * scale for t, w in fcp_weights.items()}
fcp_weights[SHV] += 1.0 - sum(fcp_weights.values())   # cash fills remainder
```

## BULL-QQQ sleeve (30% capital)

```
trend_ok = mom_12_1(QQQ) > 0 or mom_13612U(QQQ) > 0
macro_on = (mom_13612U(HYG) > 0
            or mom_13612U(LQD) > 0
            or mom_13612U(TIP) > 0)
late_cycle_inflation = (mom_13612U(HYG) <= 0
                        and mom_13612U(LQD) <= 0
                        and mom_13612U(TIP) > 0)

if trend_ok and macro_on:
    bull_weights = {"XLP" if late_cycle_inflation else "QQQ": 1.0}
else:
    bull_weights = {"SHV": 1.0}
```

## Combined execution

```
portfolio = {}
for t, w in fcp_weights.items():
    portfolio[t] = portfolio.get(t, 0) + 0.70 * w
for t, w in bull_weights.items():
    portfolio[t] = portfolio.get(t, 0) + 0.30 * w
```

## Execution

```
Signal date:      Last trading day of calendar month (T)
Trade date:       T+1 MOC (market-on-close)
Trade list:       (target_weight * NAV) - current_position, per ticker
Cost model:       10 bps/side on changed notional (round-trip 20 bps on flip)
Rebalance:        Monthly only; no intramonth adjustments
```

## Data

```
Source:           yfinance (daily Adj Close)
Adjustment:       auto_adjust=True (dividend-reinvested total return)
Used in:          ALL momentum, SMA, covariance, realized vol calculations
Pre-inception:    Vanguard mutual-fund proxies stitched at splice dates
                  (see Data lineage section in main README; pre-2010 only)
ETF-live window:  All 11 RISKY ETFs definitely tradable post-2008 (no proxy)
```

## Headline metrics (current PROD spec)

```
ETF-live 18y (2008-09-30 to 2026-05-17):
  Sharpe:   1.56
  CAGR:     16.63%
  Vol:       9.93%
  MaxDD:   -12.29%

EXT 32y (1994-01-01 to 2026-05-17):
  Sharpe:   1.31
  CAGR:     13.53%
  MaxDD:   -16.7%

TEST OOS (2017-01-01 to 2026-05-17, unseen by spec selection):
  Sharpe:   1.73
  CAGR:     17.89%
  MaxDD:   -12.3%
```

## Forward expectation (NOT raised from prior versions)

```
Sharpe:  0.90-1.20
CAGR:    8-12%
MaxDD:  -15% to -25%
```

## Selection trail (signals + variants tested this research cycle)

```
13612W weighted vs 13612U canonical:   13612U chosen (+0.08 Sh, matches paper)
Blend weights tested:                   80/20, 70/30, 60/40, 50/50 (70/30 optimal)
SAFE pool tested:                       [BIL,SHV,SHY,IEF] best-of, IEF-only, SHV-only
                                        (SHV-only chosen for unified narrative)
Equity-strength override:               REMOVED (inert, 10/403 months)
Pair lookback grid:                     63/126/252/504/756/1008/1260d (756d, robust)
Pair rule:                              min-variance vs lowest-corr vs inv-vol
                                        (min-variance wins)
XLP alternatives:                       XLP/XLV/XLU/SPY/SHV/baskets/SCHD/NOBL/VIG etc
                                        (XLP-only wins all windows after costs)
Canary rules:                           any-positive vs 2-of-3 vs all vs single-asset
                                        (any-positive wins)
Asymmetric canary (2-mo confirm):       REJECTED (-0.05 Sh)
BULL vol-target:                        REJECTED (hurts Sharpe all caps)
CPM-Core (drop QQQ/IGM):                REJECTED (-0.08 Sh)
Universe drop tests:                    GLD/TLT critical (-0.32 Sh)
```

## Robustness summary (Bailey & Lopez de Prado 2012 framework)

```
ETF-live 18y:    PSR(>1.0) = 97.8%, DSR @ N=1000 = 99.9%
TEST OOS:        PSR(>1.0) = 97.2%, DSR @ N=1000 = 95.9%
EXT 32y:         PSR(>1.0) = 94.2%, DSR @ N=1000 = 100%
```

Interpretation: edge is supportive under assumed N_eff=1000 effective
trials. The 13612U switch counts as +1 selected variant; if true
effective trial count is materially higher, DSR confidence drops.

## Known limitations

```
1. Never run live capital. ETF-live = backtest on real ETF history.
2. Universe selected in-sample (DSR mitigates but doesn't eliminate).
3. GLD/TLT structurally essential (not just diversifier).
4. Structural V-recovery lag (canary slow to re-engage; COVID -1.6%).
5. BULL CAGR = QQQ-era artifact (forward anchor 7-10%).
6. Tax wrapper required (monthly rotation = short-term gains).
7. Pre-2010 EXT data uses Vanguard mutual-fund proxies (stress-test only).
```

## Reproduction

```
Run from repo root:
  uv run python bull_qqq_live.py backtest
  uv run python build_dashboard.py

Required:
  - yfinance (auto_adjust=True for total-return data)
  - pandas, numpy, scipy
  - Pre-stitched panel via cpm_live.load_panel()

Random seed: not needed (deterministic given data)
Time zone:   US/Eastern (NYSE close)
```
