# CPM sleeve: L (TOP_K=5 drop-1 min-var) + B (clean drop-to-safe) -- findings

RESEARCH-ONLY. Prod untouched, no commit. mooex T+1, both-252, 10 bps/side.
Script: `research/cpm_LB_topk5_droptosafe_2026_06_02.py`
Raw: `research/cpm_LB_topk5_droptosafe_2026_06_02_raw.txt`

## Anchor + gates (all passed)

- Anchor reproduced EXACT: sleeve Sharpe=1.255673, MaxDD=-13.0317%, Calmar=1.007646.
- A replica == prod (max weight diff 0.00e+00 across ext window).
- B == A at n_pos in {0,1,2,3} & defensive (diff 0); differs ONLY at n_pos=4 (diff 0.25, the dropped slot routed to safe). As designed.
- Blend patch verified: `build_dashboard.compute_target_weights` patched per config. B blend != A blend (max |dret| 7.5e-3), L blend != A blend (max |dret| 1.4e-2). The patch worked this time -- the prior 1.509 for B was a monkeypatch bug measuring prod-A on both blend rows.

## Configs

- **A** (prod baseline): TOP_K=4, curve 25/50/75/100, min-var 3-of-4 @ 33.3% at n_pos=4.
- **L** (TOP_K=5 generalized drop-1): rank all 8 risky by vol-adj faber, take top-5; n_pos = #positive (0..5). Exposure ramp HAD to become **n/5** (not 25/50/75/100) since breadth now reaches 5. Consistent drop-1 min-var: n=5->4of5, n=4->3of4, n=3->2of3, hold-all for n<=2. Held names split risky_fraction equally; remainder -> best_safe. Canary unchanged.
- **B** (drop-to-safe): = A except at n_pos=4 hold min-var 3-of-4 @ 25% each (75% risky) + 25% best_safe. Per-name weight stays 25% at every breadth; dropped 4th slot's 25% goes to safe (the 3 are NOT renormalized to 33.3%). Curve: 25/50/75/(75 risky+25 safe).

## Config x metrics

### SLEEVE clean (2008-05-30..2026-05-22)

| cfg | Sharpe | Sortino | MaxDD | Calmar | Martin | CAGR | vol |
|-----|--------|---------|-------|--------|--------|------|-----|
| A | 1.2557 | 1.5163 | -13.03% | 1.0076 | 4.2571 | 13.13% | 10.28% |
| L | 1.1142 | 1.3770 | -11.32% | 0.9637 | 3.2447 | 10.91% | 9.76% |
| B | 1.2426 | 1.5184 | -13.03% | 0.8017 | 3.7761 | 10.45% | 8.30% |

### SLEEVE ext (1999-03-10..2026-05-22)

| cfg | Sharpe | Sortino | MaxDD | Calmar | Martin | CAGR | vol |
|-----|--------|---------|-------|--------|--------|------|-----|
| A | 1.2549 | 1.5499 | -13.14% | 0.9712 | 4.1168 | 12.76% | 9.97% |
| L | 1.1346 | 1.4301 | -12.93% | 0.8336 | 3.3433 | 10.78% | 9.42% |
| B | 1.2658 | 1.5849 | -14.11% | 0.7370 | 3.7728 | 10.40% | 8.07% |

### BLEND 60/20/20 clean (CPM 60 / BULL 20 / NDX 20; BD.compute_target_weights patched)

| cfg | Sharpe | MaxDD | CAGR |
|-----|--------|-------|------|
| A | 1.4427 | -10.49% | 16.33% |
| L | 1.3482 | -11.19% | 14.94% |
| B | **1.4560** | **-9.18%** | 14.68% |

NOTE: B clean blend Sharpe = **1.4560** (NOT the contaminated 1.509). MaxDD -9.18% (1.31pp better than A). CAGR 14.68% (-1.65pp vs A).

### Per-crisis sleeve (ext) cum return / maxDD

| crisis | A ret | L ret | B ret | A DD | L DD | B DD |
|--------|-------|-------|-------|------|------|------|
| GFC 2008 | 23.26% | 21.06% | 19.92% | -13.14% | -12.93% | -14.11% |
| Euro 2011 | -0.68% | -0.64% | 1.14% | -7.95% | -7.10% | -7.95% |
| COVID 2020 | 2.11% | 1.35% | 3.00% | -10.20% | -10.99% | -10.20% |
| 2022 bear | -0.33% | -0.79% | 0.24% | -5.17% | -3.99% | -4.88% |
| 2025 tariff | 2.62% | 1.69% | 2.82% | -10.70% | -8.70% | -7.92% |

B helps the milder modern crises (Euro 2011, 2022, 2025 tariff turn positive/less-deep) but costs the most in GFC 2008 (deepest DD -14.11%, lowest return). L is uniformly a touch worse on return.

## L breadth (n_pos histogram, clean window, 217 months)

- defensive/0-pos: 57 (26.3%)
- n=1: 1 (0.5%) | n=2: 5 (2.3%) | n=3: 11 (5.1%) | n=4: 15 (6.9%) | **n=5: 128 (59.0%)**
- n_pos=5 fires 128 months vs n_pos=4 just 15 (ratio ~8.5:1). The 5th slot is almost always active, so the n/5 ramp keeps exposure structurally near full while min-var keeps tossing the 5th name -- effectively "hold 4, sized to 5" = persistent ~80-100% exposure with a diluting 5th candidate.
- ext window (327 months): n=5 184 (56.3%), n=4 22 (6.7%).

### L selection at n_pos=5 -- which asset min-var 4-of-5 drops (ext, 184 months)

Dropped ticker counts: **EEM:84, QQQ:61, VNQ:27, EFA:6, DBC:3, GLD:2, SPHQ:1**. min-var consistently sheds the high-variance equity/EM names (EEM, QQQ). Examples:

```
2002-03  VNQ,EEM,GLD,DBC,SPHQ -> held VNQ,GLD,DBC,SPHQ   drop EEM
2003-05  EEM,TLT,VNQ,GLD,QQQ  -> held EEM,TLT,VNQ,GLD     drop QQQ
2003-07  VNQ,EEM,QQQ,EFA,SPHQ -> held VNQ,EEM,EFA,SPHQ    drop QQQ
```

## Key questions answered

1. **Does TOP_K=5 + consistent drop-1 (L) beat A?** No. L LOSES on sleeve (Sharpe 1.1142 vs 1.2557, -0.14; CAGR -2.22pp) AND blend (Sharpe 1.3482 vs 1.4427, -0.095; CAGR -1.39pp; DD 0.70pp worse). The wider/looser 5th name dilutes returns: it fires n=5 ~59% of months, so the n/5 ramp permanently admits a marginal candidate that min-var then mostly drops anyway (EEM/QQQ), leaving you over-diversified into lower-momentum diversifiers. Only modest DD relief (-11.32% vs -13.03% sleeve) -- not enough to offset.

2. **Clean drop-to-safe (B) REAL blend numbers (not contaminated 1.509):** blend **Sharpe 1.4560 / MaxDD -9.18% / CAGR 14.68%**. vs A (1.4427 / -10.49% / 16.33%): blend Sharpe +0.013 (within noise), blend MaxDD 1.31pp better, blend CAGR -1.65pp. Sleeve cost: CAGR 10.45% vs 13.13% = **-2.68pp** (matches the prior ~-2.7pp estimate). So B is marginally better risk-adjusted at the blend with a meaningfully softer drawdown, but pays real return.

3. **Which removes the n_pos=3->4 cliff while staying competitive?** **B does, cleanly.** A jumps exposure 75%->100% AND concentrates from per-name 25% to 33.3% at the 3->4 transition (the cliff). B holds per-name 25% and exposure 75% across n=3 and n=4 (only the min-var-3 selection differs), so the cliff is gone and the curve is monotone 25/50/75/75. B stays competitive (blend Sharpe slightly up, blend DD down). L "smooths" the ramp to n/5 but loses on returns, so it removes the cliff at an unacceptable cost.

## Verdict

- **L (TOP_K=5): REJECT.** Loses on both sleeve and blend Sharpe and CAGR; only buys minor DD relief. It is a structural universe change (high overfit surface) that underperforms the incumbent -- no reason to adopt.
- **B (drop-to-safe): MIXED, lean keep-as-defensive-variant.** Real clean blend Sharpe 1.4560 (> A 1.4427, but +0.013 is within noise) with a genuinely softer blend MaxDD (-9.18% vs -10.49%) and it removes the 3->4 cliff. Cost: blend CAGR -1.65pp, sleeve CAGR -2.68pp. Adopt only if the mandate prioritizes drawdown/risk-adjusted smoothness over compounding. Not a free win.
- **vs F (sleeve 1.288 / -10.71%):** F still dominates both new configs on the sleeve -- F has higher Sharpe (1.288) AND shallower MaxDD (-10.71%) than A (1.2557/-13.03%), L (1.1142/-11.32%), and B (1.2426/-13.03%). Neither L nor B reaches F on the sleeve. F remains the better defensive lever.

## Caveats / confidence

- Single in-sample point per config; no walk-forward / DSR / bootstrap here. Sharpe deltas of +/-0.01-0.02 (e.g. B blend +0.013) are within typical noise -- do NOT over-read.
- L is a STRUCTURAL universe change (TOP_K 4->5 + ramp redefinition): large overfit surface, treat any "win" with extra suspicion. It lost anyway, which is a clean negative.
- B's benefit is concentrated in milder modern crises; it is WORSE in GFC 2008 (deepest DD, lowest return) -- the tail it most needs to protect.
- All numbers mooex T+1, both-252 cov, 10 bps/side, SHV cash. Crisis windows fixed-date.
