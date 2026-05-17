# Canary state asset rotation research notes

## Background

Systematic state matrix analysis on 3-asset canary (HYG, LQD, TIP) revealed that the canary state predicts not just QQQ-vs-cash but **which equity asset** is best forward-return per state. 8 canary states (2^3) showed dramatic differences in best-performing asset.

## Hypotheses tested

### H1: `+-+` (HYG-, LQD-, TIP+) → defensive cash-flow sector (XLP/XLV/IHF)

**Status: DEPLOYED as XLP rotation in BULL-QQQ sleeve**

**Evidence**: 40 observations combined (19 LIVE + 21 EXT). All defensive cash-flow sectors outperform QQQ:
- QQQ: +1.02% / +0.75% fwd return
- XLP (staples): +1.98% / +1.81% (Sharpe 2.17 / 2.05)
- XLV (broad HC): +1.80% / +1.54%
- IHF (HC providers): +2.55% / +2.55% (highest but UNH-concentrated)
- VHT, XLU, RYH also outperform

**Mechanism**: State `+-+` = late-cycle inflation regime (rising real yields, credit weak). Defensive cash-flow sectors with pricing power lead. Tech (QQQ) underperforms due to long-duration sensitivity. Biotech/pharma sub-sectors are also duration-exposed (XBI Sharpe only 0.38 in this state) — confirms duration story.

**Why XLP over IHF**:
- XLP broader basket (30+ staples like PG/KO/WMT) vs IHF concentration on UNH/managed care
- IHF Sharpe collapses from 1.88 → 0.65 when removing top 5 months (outlier-driven)
- XLP nearly same Sharpe (2.17 vs 1.88) without concentration risk
- Mechanism more durable: consumer staples = textbook defensive across decades

**Caveats**:
- Sample 40 obs total, ~10-15 independent episodes
- Mechanism-family validation passed (XLV, XLP, VHT, IHF, RYH all outperform)
- Multiple-testing concern: 8 states × many assets × thresholds searched

### H2: `--+` (HYG-, LQD-, TIP+) → small value (VBR) or REITs (VNQ)

**Status: PARKED — research only, not deployed**

**Evidence**: 18 observations combined (5 LIVE + 13 EXT). Insufficient sample for deployment.
- VBR: +6.78% / +3.36% fwd return
- VNQ: +11.58% / +6.61% fwd return (likely outlier-driven)
- QQQ: +5.34% / +1.50%

**Hypothesis**: state `--+` = severe stress with only TIP rallying. "Fed pivot incoming" or "stagflation start" regime where real assets (REITs) and small value benefit from rate cut anticipation + inflation hedge demand.

**Reason for parking**:
- N=18 too small for confidence (oracle flagged as research-only)
- VNQ +11.58% LIVE mean likely 1-2 outlier episodes
- Story plausible but not validated by mechanism-family check
- Episode contribution dominates: removing top 1-2 months may flip sign

**Re-evaluate**: after 12+ new live `--+` observations, run mechanism-family check (VBR vs IWN vs IJS vs DFSVX; VNQ vs broad REIT proxy).

### H3: XLE-rotation kill switch (XLE 12m - QQQ 12m > 10%)

**Status: PARKED — pending more out-of-sample evidence**

**Evidence**:
- LIVE 18y standalone Sh boost: 1.05 → 1.08 (+0.03)
- EXT 28y standalone Sh boost: 0.85 → 0.91 (+0.06)
- 80/20 blend Sharpe gain: 1.40 → 1.43

**Validation results**:
- ✅ **Threshold monotonicity passes**: Sharpe rises smoothly 0.98 → 1.10 across thresholds 0%→12.5%, then declines. Not knife-edge fit.
- ❌ **Episode test FAILS**: kill switch firings concentrated in 2022 (12 of 30 firings = 40%). Remove 2022 from sample → Sharpe gain flips from +0.03 to -0.03.

**Mechanism**: When energy structurally leads tech by 10%+ over 12 months, that's a commodity/inflation regime hostile to growth. Historical triggers: 2007-2008 (oil to $147), 2011 (post-QE2 oil rally), 2021-2022 (oil $130 + Fed hikes), 2026 spike.

**Reason for parking**:
- Sample dominated by 2022 (12 firings out of 30 total)
- Signal disappears when removing 2022 from backtest
- Could be regime-specific (works during commodity supercycles only)
- Personal-capital deployment: real but not confidence-deployable

**Re-evaluate**: if another XLE-QQQ rotation regime fires in live deployment, observe whether the predicted growth-underperformance materializes.

## Other states evaluated (not deployed)

| State | n | Best asset | QQQ vs best | Verdict |
|---|---:|---|---|---|
| `+++` (all positive) | 116/152 | IGM/XLK/QQQ tied | QQQ fine | Use QQQ default |
| `++-` | 10/10 | IGM (+2.73%) | QQQ (+2.27%) close | Sample too small for rotation |
| `+--` | 17/29 | IGM live, GLD/VWO ext | Inconsistent | No clear winner |
| `-++` | 12/15 | XLK | QQQ +3.74% close | Tech tied; not worth rotation |
| `-+-` | 5/5 | QQQ wins | already best | Use QQQ |

## Lessons learned

1. **State matrix beats variant testing**: instead of trying canary variants ad-hoc, systematic enumeration of all 2^n states reveals true signal structure.
2. **OR-pattern of credit/inflation signals validated**: lone-positive states for HYG/LQD/TIP all have positive fwd QQQ. Lone-positive states for GLD/BND are NEGATIVE — they're "flight to safety" signals.
3. **Mechanism family critical for deployment**: IHF was tempting (Sharpe 1.88) but mechanism-family check (XLV, XLP, VHT all confirm) is what makes the hypothesis durable, not the highest-Sharpe-single-asset.
4. **Episode test catches signals that look real but cluster on one event**: XLE kill looked great until isolating 2022's contribution.
5. **Sample-size discipline**: any state with n<20 should be research-only, not deployable.

## Sources

- `bull_qqq_live.py` — production design
- `research/canary_state_matrix.log` — full state matrix
- `research/monthly_qqq_signals.md` — earlier signal research
- Oracle review: `Agent 3fb15029` (May 2026) — flagged H2 as low plausibility, recommended XLP/family validation for H1, episode test for H3
