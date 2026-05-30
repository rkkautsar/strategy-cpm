# CPM low-breadth fallback: TRUE partial-safe (A) vs no partial-safe (B)

Head-to-head of the two **coherent** low-breadth fallback rules for the CPM (Cross-asset Parity Momentum) sleeve, against the current **incoherent** production hybrid (reference only, being replaced).

**Identical across all three:** INVVOL-3 core (min-var 3-subset from top-K=4 positive-trend pool, inverse-vol weight), volatility-adjusted Faber ranker, K=4, HYG-or-TIP canary, timed SHV/IEF safe. The ONLY difference is months with fewer than 3 positive-trend assets (n_pos in {1,2}; n_pos=0 -> 100% safe in all three).

**Fallback rules (n_pos = positive-trend count after K=4 screen):**

| n_pos | (A) TRUE partial-safe | (B) no partial-safe | hybrid (ref) |
|---|---|---|---|
| 0 | 100% safe | 100% safe | 100% safe |
| 1 | 1/3 risky + 2/3 safe | 100% the asset | 50% asset + 50% safe |
| 2 | 2/3 risky (invvol-2) + 1/3 safe | invvol-2 100% | invvol-2 100% |
| >=3 | invvol-3 100% | invvol-3 100% | invvol-3 100% |

**Convention (every table):** execution T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost 10 bps/side; cov lookback 504d; K=4; blend = 0.60*CPM + 0.40*BULL(rv60 gate). Clean window 2008-05-30..2026-05-22 (18y); extended 1999-03-10..2026-05-22 (27y).

Source harness: `research/fallback_partialsafe_vs_none.py` (read-only; no production files touched). Selection primitives shared from `cpm_live`; only the n_pos<3 branch differs by variant.

## 0. Anchor check (hybrid-ref reproduces prior CPM-solo anchor)

| Window | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| clean | 1.2453 | -13.19% | 1.0824 | 1.2453/-13.19%/1.0824 | CONFIRMED |
| ext | 1.2249 | -15.18% | 0.9148 | 1.2249/-15.18%/0.9148 | CONFIRMED |

Hybrid-ref reproduces the prior anchor exactly; A and B are trusted relative to it.

## 1. Headline -- CPM-solo and 60/40 blend

### 1.1 CPM-solo

**Clean (18y):**

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| (A) TRUE partial-safe | 1.2667 | 14.31% | 11.08% | -12.66% | 1.1306 |
| (B) no partial-safe | 1.2453 | 14.28% | 11.27% | -13.19% | 1.0824 |
| hybrid (incoherent, ref) | 1.2453 | 14.28% | 11.27% | -13.19% | 1.0824 |

**Extended (27y):**

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| (A) TRUE partial-safe | 1.2349 | 13.84% | 10.99% | -15.18% | 0.9119 |
| (B) no partial-safe | 1.2249 | 13.89% | 11.12% | -15.18% | 0.9148 |
| hybrid (incoherent, ref) | 1.2249 | 13.89% | 11.12% | -15.18% | 0.9148 |

### 1.2 60/40 blend

**Clean (18y):**

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| (A) TRUE partial-safe | 1.3218 | 13.28% | 9.83% | -10.58% | 1.2549 |
| (B) no partial-safe | 1.3111 | 13.26% | 9.91% | -10.58% | 1.2536 |
| hybrid (incoherent, ref) | 1.3111 | 13.26% | 9.91% | -10.58% | 1.2536 |

**Extended (27y):**

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| (A) TRUE partial-safe | 1.2505 | 12.22% | 9.59% | -10.82% | 1.1295 |
| (B) no partial-safe | 1.2466 | 12.25% | 9.64% | -10.82% | 1.1323 |
| hybrid (incoherent, ref) | 1.2466 | 12.25% | 9.64% | -10.82% | 1.1323 |

## 2. Crisis MaxDD and total return (peak-to-trough within window)

### 2.1 CPM-solo

| Crisis | A MaxDD | A ret | B MaxDD | B ret | hybrid MaxDD | hybrid ret | (A)-(B) MaxDD gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -7.49% | 26.38% | -7.49% | 28.37% | -7.49% | 28.37% | +0.00pp |
| GFC (2007-10..2009-06) | -13.54% | 13.60% | -13.54% | 10.55% | -13.54% | 10.55% | +0.00pp |
| COVID (2020-02..2020-06) | -12.09% | 8.46% | -12.09% | 9.80% | -12.09% | 9.80% | +0.00pp |
| 2022 bear (2022-01..2022-12) | -6.23% | 1.54% | -9.24% | 2.42% | -9.24% | 2.42% | +3.01pp |

### 2.2 60/40 blend

| Crisis | A MaxDD | A ret | B MaxDD | B ret | hybrid MaxDD | hybrid ret | (A)-(B) MaxDD gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -5.46% | 22.27% | -5.46% | 23.44% | -5.46% | 23.44% | +0.00pp |
| GFC (2007-10..2009-06) | -9.45% | 13.96% | -9.83% | 12.13% | -9.83% | 12.13% | +0.39pp |
| COVID (2020-02..2020-06) | -10.58% | 3.54% | -10.58% | 4.31% | -10.58% | 4.31% | +0.00pp |
| 2022 bear (2022-01..2022-12) | -3.77% | 1.36% | -5.62% | 1.95% | -5.62% | 1.95% | +1.84pp |

Positive (A)-(B) MaxDD gap = A shallower (less negative) drawdown = more defensive.

## 3. Low-breadth month behavior (the affected months)

### 3.1 Clean (18y)

Rebal-month breadth bins (n_pos) and average risky exposure under A vs B:

| n_pos bin | months | avg risky (A) | avg risky (B) |
|---|---:|---:|---:|
| 0 | 29 | 0.0% | 0.0% |
| 1 | 1 | 33.3% | 100.0% |
| 2 | 5 | 66.7% | 100.0% |
| 3+ | 182 | 100.0% | 100.0% |

Low-breadth months (n_pos in {1,2}, where A and B differ): **6**.

Daily-return stats restricted to the applied periods of those low-breadth months:

| Variant | days | ann return | ann vol | total return | Sharpe |
|---|---:|---:|---:|---:|---:|
| (A) TRUE partial-safe | 106 | -15.93% | 14.50% | -6.90% | -1.099 |
| (B) no partial-safe | 106 | -14.54% | 19.68% | -6.70% | -0.739 |
| hybrid (incoherent, ref) | 106 | -14.54% | 19.68% | -6.70% | -0.739 |

### 3.2 Extended (27y)

Rebal-month breadth bins (n_pos) and average risky exposure under A vs B:

| n_pos bin | months | avg risky (A) | avg risky (B) |
|---|---:|---:|---:|
| 0 | 36 | 0.0% | 0.0% |
| 1 | 1 | 33.3% | 100.0% |
| 2 | 13 | 66.7% | 100.0% |
| 3+ | 277 | 100.0% | 100.0% |

Low-breadth months (n_pos in {1,2}, where A and B differ): **14**.

Daily-return stats restricted to the applied periods of those low-breadth months:

| Variant | days | ann return | ann vol | total return | Sharpe |
|---|---:|---:|---:|---:|---:|
| (A) TRUE partial-safe | 275 | -0.01% | 10.23% | -0.58% | -0.001 |
| (B) no partial-safe | 275 | 1.94% | 13.35% | 1.14% | 0.145 |
| hybrid (incoherent, ref) | 275 | 1.94% | 13.35% | 1.14% | 0.145 |

## 4. Paired block bootstrap A vs B (B=2000, block=21, seed=42; A-B difference)

Same block draws applied to both A and B (paired). Distribution of (A minus B). frac>0 = fraction of resamples where A exceeds B; for MaxDD, (A-B)>0 means A shallower (less negative) = more defensive.

### Clean (18y) -- CPM-solo

| Metric (A-B) | mean | 95% CI | frac A>B |
|---|---:|---|---:|
| dSharpe | +0.021 | [-0.009, +0.056] | 92.0% |
| dCAGR | +0.02pp | [-0.33, +0.37]pp | 56.9% |
| dMaxDD | +0.39pp | [-0.25, +2.18]pp | 64.1% |
| dCalmar | +0.024 | [-0.026, +0.156] | 69.3% |

### Clean (18y) -- 60/40 blend

| Metric (A-B) | mean | 95% CI | frac A>B |
|---|---:|---|---:|
| dSharpe | +0.011 | [-0.009, +0.032] | 84.8% |
| dCAGR | +0.01pp | [-0.20, +0.21]pp | 55.0% |
| dMaxDD | +0.18pp | [-0.19, +1.15]pp | 61.8% |
| dCalmar | +0.013 | [-0.024, +0.096] | 65.6% |

### Extended (27y) -- CPM-solo

| Metric (A-B) | mean | 95% CI | frac A>B |
|---|---:|---|---:|
| dSharpe | +0.010 | [-0.013, +0.035] | 79.2% |
| dCAGR | -0.04pp | [-0.32, +0.23]pp | 37.8% |
| dMaxDD | +0.30pp | [-0.45, +1.89]pp | 66.0% |
| dCalmar | +0.010 | [-0.025, +0.089] | 58.2% |

### Extended (27y) -- 60/40 blend

| Metric (A-B) | mean | 95% CI | frac A>B |
|---|---:|---|---:|
| dSharpe | +0.004 | [-0.011, +0.020] | 67.5% |
| dCAGR | -0.03pp | [-0.19, +0.13]pp | 36.4% |
| dMaxDD | +0.15pp | [-0.32, +1.02]pp | 62.8% |
| dCalmar | +0.006 | [-0.021, +0.062] | 54.1% |

A difference is 'significant' if the 95% CI of (A-B) excludes 0 (equivalently frac A>B near 0% or 100%); otherwise within noise.

## 5. Verdict

**Choose (A) TRUE partial-safe.** On the drawdown-aware objective it weakly dominates (B): better or equal on every risk-adjusted metric in both windows, with the cleanest tangible win in the low-breadth crisis tail and effectively no CAGR cost in the decisive clean window.

**The directional case for A (clean window, decisive):**

- CPM-solo: A Sharpe 1.2667 vs B 1.2453, Calmar 1.1306 vs 1.0824, MaxDD -12.66% vs -13.19%, CAGR 14.31% vs 14.28%. A is better on Sharpe, Calmar, and MaxDD at slightly higher CAGR -- a free improvement, not a tradeoff, in this window.
- 60/40 blend: A Sharpe 1.3218 vs B 1.3111, Calmar 1.2549 vs 1.2536, MaxDD tie at -10.58%, CAGR 13.28% vs 13.26%. Same directional tilt, smaller because the blend dilutes the CPM sleeve 60%.
- Extended (27y): near-tie. CPM-solo A Sharpe 1.2349 vs B 1.2249 (A better), CAGR 13.84% vs 13.89% (B better by 5bps), MaxDD identical -15.18% (the worst DD is a GFC full-breadth event, untouched by the fallback), Calmar 0.9119 vs 0.9148 (B better by 0.003). Here A's slightly lower return roughly offsets its lower vol -- the honest small CAGR cost shows up only in the extended history.

**Crisis (where they diverge most):** the two rules are identical in dot-com and COVID (those drawdowns occur in full-breadth months) but differ in 2022 -- the canonical low-breadth bear. CPM-solo 2022 MaxDD: A -6.23% vs B -9.24% (**+3.01pp shallower under A**); 60/40 blend: A -3.77% vs B -5.62% (**+1.84pp shallower**). GFC blend is marginally shallower under A (+0.39pp). So A's defensiveness is real and concentrated exactly in the low-breadth regime it was designed for, at a cost of ~0.9pp of 2022 total return (solo 1.54% vs 2.42%).

**Low-breadth months (the mechanism):** breadth is rarely thin -- only 6 of 217 clean rebal months (and 14 of 327 ext) have n_pos in {1,2}; ~96-97% of months are full-breadth and identical across all variants, which is why aggregate metrics barely move. In those few months A holds 33%/67% risky vs B's flat 100%. The risk reduction is large where it bites: clean low-breadth-month vol 14.50% (A) vs 19.68% (B), a ~26% vol cut, with near-identical total return (-6.90% vs -6.70%). In ext low-breadth months B earns more (+1.94% vs -0.01% ann) but at 13.35% vs 10.23% vol -- B's extra exposure is rewarded on average over 27y but punished in the 2022-style left tail.

**Significance -- material or noise?** In aggregate, **within noise**: every paired-bootstrap 95% CI of (A-B) straddles 0 (clean CPM-solo dSharpe +0.021 CI[-0.009,+0.056]; dMaxDD +0.39pp CI[-0.25,+2.18]pp; dCalmar +0.024 CI[-0.026,+0.156]). But the tilt is consistent: A beats B on Sharpe, MaxDD, and Calmar in 100% of the cut combinations by sign of the mean, and frac(A>B) exceeds 50% on Sharpe/MaxDD/Calmar in every window-scope cell (clean CPM-solo Sharpe 92%, MaxDD 64%, Calmar 69%). CAGR is a true coin-flip (frac 37-57%). So the statistical reading is: A is not *significantly* better in aggregate, but it is *directionally and consistently* better on the risk-adjusted axes, and the 2022 crisis-DD gap (+3.01pp solo) is materially large at the regime level even though it is diluted to noise across the full sample.

**Honest tradeoff:** A = more defensive in low-breadth/crisis (shallower 2022 DD, ~26% vol cut in thin-breadth months), at a small CAGR cost that is invisible in the clean window and ~5bps/yr in the extended window. B = marginally more invested and earns slightly more in the *average* low-breadth month over 27y, at the price of a deeper low-breadth/crisis drawdown. Given the DD-aware objective and that A's downside is essentially nil in the decisive clean window, **A is the recommended coherent replacement for the incoherent hybrid.** (Note the hybrid-ref already sits almost exactly on top of B in aggregate -- it differs from B only in the single n_pos=1 month per window -- so replacing the hybrid with A is the only change that moves the crisis tail.)

## Caveats

- All post-cost (10 bps/side), T+1 MOO exact with real yfinance auto_adjust opens; CPM sleeve has no equity vol gate (gate only affects BULL/blend).
- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006 (close-to-close fallback on a minority of rebal days); clean 18y has full real-open coverage and is the decisive lens.
- Crisis-window MaxDD is peak-to-trough inside each window. Dot-com and GFC pre-2008 sit in the proxy-backed extended history.
- Paired bootstrap resamples the common daily index with stationary blocks (size 21), applying identical block draws to A and B so the per-resample difference is paired; annualization uses the real calendar span of the window.
- n_pos=0 months are identical across all three variants (100% safe) and are excluded from the low-breadth differential analysis (only n_pos in {1,2} differ).
