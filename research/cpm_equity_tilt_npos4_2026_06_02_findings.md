# CPM n_pos=4 equity-tilt variants -- findings (2026-06-02)

RESEARCH-ONLY. Prod untouched, not committed. mooex T+1, both-252, 10 bps/side.
Harness: `research/cpm_equity_tilt_npos4_2026_06_02.py` -> raw
`research/cpm_equity_tilt_npos4_2026_06_02_raw.txt`.

Anchor gate reproduced EXACT: A clean Sharpe = 1.255673, MaxDD = -13.0317%,
Calmar = 1.007646. A replica == prod (max weight diff 0). Blend patch verified
(every P* blend differs from A blend).

## Setup

Only the n_pos=4 weighting changes. n_pos<=3 = prod A ramp (25/50/75, hold all
positives equal-split); canary + safe routing unchanged; n_pos=0/canary-off = safe.
SPY/QQQ sourced from the same panel adjusted-close + OHLC open cache used everywhere
else (SPY OHLC from 1993-01, QQQ OHLC from 1999-03), canonical mooex T+1 override.

n_pos histogram (config-invariant): n_pos=4 fires 65.9% of clean months (143/217),
63.0% ext (206/327). So the n=4 rule dominates exposure.

## Config x metrics

SLEEVE clean (2008-05-30..):

| cfg | Sharpe | Sortino | MaxDD | Calmar | Martin | CAGR | vol |
|-----|--------|---------|-------|--------|--------|------|-----|
| A  (prod, MV3@33.3%) | 1.2557 | 1.5163 | -13.03% | 1.0076 | 4.2571 | 13.13% | 10.28% |
| B  (MV3@25%+25% safe) | 1.2426 | 1.5184 | -13.03% | 0.8017 | 3.7761 | 10.45% | 8.30% |
| P1 (MV3@25%+25% SPY) | 1.2424 | 1.4976 | -13.05% | 0.9872 | 4.2386 | 12.88% | 10.20% |
| P2 (MV3@25%+25% QQQ) | 1.2695 | 1.5433 | -13.83% | 0.9960 | 4.4335 | 13.77% | 10.64% |
| P3 (100% SPY)        | 0.9379 | 1.0791 | -20.45% | 0.5722 | 2.1665 | 11.70% | 12.69% |
| P4 (100% QQQ)        | 1.0036 | 1.1862 | -22.77% | 0.6626 | 2.4908 | 15.09% | 15.21% |

SLEEVE ext (1999-03-10..):

| cfg | Sharpe | Sortino | MaxDD | Calmar | CAGR | vol |
|-----|--------|---------|-------|--------|------|-----|
| A  | 1.2549 | 1.5499 | -13.14% | 0.9712 | 12.76% | 9.97% |
| B  | 1.2658 | 1.5849 | -14.11% | 0.7370 | 10.40% | 8.07% |
| P1 | 1.2181 | 1.5074 | -15.79% | 0.7658 | 12.09% | 9.76% |
| P2 | 1.2142 | 1.5215 | -15.07% | 0.8437 | 12.71% | 10.29% |
| P3 | 0.7965 | 0.9328 | -32.10% | 0.2998 |  9.62% | 12.52% |
| P4 | 0.7723 | 0.9231 | -48.10% | 0.2442 | 11.75% | 16.05% |

BLEND 60/20/20 clean (BD.compute_target_weights patched per config; BULL+NDX identical):

| cfg | Sharpe | MaxDD | CAGR |
|-----|--------|-------|------|
| A  | 1.4427 | -10.49% | 16.33% |
| B  | 1.4560 |  -9.18% | 14.68% |
| P1 | 1.4269 |  -9.31% | 14.40% |
| P2 | 1.4067 | -11.03% | 16.68% |
| P3 | 1.2242 |  -8.31% |  8.61% |
| P4 | 1.2091 | -16.41% | 17.49% |

## Per-crisis SLEEVE (ext) -- cum return / MaxDD

| crisis | A | B | P1 | P2 | P3 | P4 |
|--------|---|---|----|----|----|----|
| GFC 2008    | +23.26% / -13.14% | +19.92% / -14.11% | +13.31% / -15.79% | +13.98% / -15.07% | -13.01% / -27.51% | -11.21% / -30.04% |
| Euro 2011   | -0.68% / -7.95% | +1.14% / -7.95% | -3.82% / -7.95% | -2.86% / -7.95% | -13.47% / -17.18% | -10.05% / -16.10% |
| COVID 2020  | +2.11% / -10.20% | +3.00% / -10.20% | +0.21% / -11.50% | +0.99% / -11.21% | -5.48% / -18.09% | -2.71% / -18.05% |
| 2022 bear   | -0.33% / -5.17% | +0.24% / -4.88% | -1.10% / -6.32% | -1.95% / -7.44% | -3.41% / -9.73% | -6.75% / -15.08% |
| 2025 tariff | +2.62% / -10.70% | +2.82% / -7.92% | +1.15% / -12.76% | +1.06% / -13.83% | -3.69% / -18.76% | -4.24% / -22.77% |

## P2 QQQ-case breakdown (n_pos=4 only)

CLEAN (143 mo): QQQ in MV3 (ends 50%) 41.3% | QQQ dropped 4th (=hold-all-4 @25%)
31.5% | QQQ not in top-4 (MV3 + new QQQ@25%) 27.3%.
EXT (206 mo): 33.5% | 27.7% | 38.8%. So P2 is genuinely a QQQ-concentration tilt
~1/3 of n=4 months, a benign hold-all-4 ~1/3, and a 4-name add the rest.

## Key answers

**Q1 -- Equity buffer (P1/P2) vs A / B?**
No clear win over A. P1 (SPY buffer) ~ B in risk-adjusted terms but recovers CAGR:
P1-B is dSharpe -0.0002, dCAGR +2.43pp, same DD -- so SPY-buffer is "B that gives the
return back" but it does NOT beat A (P1-A: dSharpe -0.0133, dCAGR -0.25pp). P2 (QQQ
buffer) is the only equity-tilt that beats A on CLEAN sleeve (dSharpe +0.0139, dCAGR
+0.64pp) but at a -0.80pp DD cost -- and that edge collapses out of sample: ext Sharpe
1.2142 < A 1.2549, ext DD -15.07% vs -13.14%, and blend Sharpe 1.4067 < A 1.4427 with
worse DD. So P2's win is an in-sample clean-window artifact.

**Q2 -- Own-the-market (P3/P4) vs A? (the key test)**
NO. The diversified min-var-3 basket clearly beats just owning the market at full
breadth. P3 (100% SPY) clean Sharpe 0.9379 and P4 (100% QQQ) 1.0036 vs A 1.2557 --
0.25-0.32 Sharpe destroyed, DD blows out to -20%/-23% clean and -32%/-48% ext. P4
buys +1.95pp CAGR (clean) for nearly double the DD; P3 gives up return AND safety.
The min-var basket is worth keeping. Decisive.

**Q3 -- Anything beat F (sleeve 1.288/-10.71%, blend 1.449/-10.49%) or A?**
On SLEEVE Sharpe: nothing beats F (best is P2 clean 1.2695 < 1.288). On BLEND: only
B (drop-to-safe, the de-risk direction, not equity-tilt) beats both -- B blend Sharpe
1.4560 > A 1.4427 > F 1.449-ish, with the best blend DD -9.18%. Among the equity-tilt
configs (P1-P4) none beats A or F on risk-adjusted at blend.

**Q4 -- Equity-crisis DD penalty (quantified).**
Full-equity configs pay the most: GFC P3/P4 DD -27.5%/-30.0% vs A -13.1% (2x); 2022
P4 -15.1% vs A -5.2% (3x); 2025 tariff P3/P4 -18.8%/-22.8% vs A -10.7%. Buffer configs
pay less: P1/P2 GFC DD ~-15-16% (vs -13.1%), 2025 -12.8%/-13.8% (vs -10.7%), 2022
-6.3%/-7.4% (vs -5.2%). GFC return is the starkest: A +23.3% vs P3/P4 -13%/-11%
(min-var basket rotated to safe assets/GLD/TLT while full-equity rode the crash down).

## Verdict per config

- **B (drop-to-safe, reference):** ADOPT-candidate at blend only -- best blend Sharpe
  (1.4560) and DD (-9.18%), but it is de-risking (CAGR -1.65pp vs A), the opposite of
  the requested aggressive direction. Not an equity tilt.
- **P1 (drop-to-SPY):** REJECT vs A. = B with the CAGR handed back, no Sharpe gain,
  no DD improvement; strictly dominated by A on Sharpe and by B on safety.
- **P2 (drop-to-QQQ):** MIXED -> lean REJECT. Beats A only on the clean sleeve;
  fails out of sample (ext) and at the blend, with worse DD. In-sample-only edge.
- **P3 (full-SPY at n=4):** STRONG REJECT. Worst risk-adjusted, gives up return and
  safety. Proves the basket is worth keeping.
- **P4 (full-QQQ at n=4):** STRONG REJECT for risk-adjusted; only attractive if you
  purely chase CAGR and tolerate -48% ext DD. The basket dominates.

## Caveats

Single in-sample point per config; no walk-forward / DSR / bootstrap here. The one
config that beat A (P2 clean sleeve) failed both robustness checks available in-run
(ext window + blend), which is itself the tell. SPY/QQQ buffer adds an asset outside
RISKY_UNIVERSE -- a structural change, not just a reweight. Conclusion is robust in
direction: aggressive equity tilt at full breadth does not improve CPM risk-adjusted
return; the diversified min-var-3 basket is the right call at n=4.
