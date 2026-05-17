# Session 2026-05: BULL-QQQ sleeve hardening + spec lockdown

## Starting state
- 80/20 CPM-BULL blend
- BULL-QQQ: 12-1 trend filter, HYG+TIP 2-asset canary, no override
- +-+ rule: XLP substitution (oracle-locked previous session)

## Session goal
Address oracle critique (data-mining concerns, sample-size, era-specificity),
add academic backing, lock final spec.

## Final locked spec

```
CPM sleeve (60% capital):
  Universe: 11 risky ETFs (QQQ/IGM/XLE/VBR/SPHQ/XMHQ/XLV/VEA/VWO/GLD/TLT)
            + 4 safe pool (BIL/SHV/SHY/IEF)
  Canary: HYG+TIP any-positive 13612W
  Selection: top-K=6 momentum + min-variance pair, hold buffer 2.5z
  Vol target: 10% (de-risk only, no leverage)
  Defensive: best-safe rotation when canary off

BULL-QQQ sleeve (40% capital):
  trend_ok = (QQQ 12-1 > 0) OR (QQQ 13612W > 0)
  macro_on = (HYG OR LQD OR TIP 13612W > 0)
  override = QQQ 12-1 > expanding 67th-pctile (Asness-style)
  if trend_ok AND (macro_on OR override):
    if state == HYG-/LQD-/TIP+: XLP
    else: QQQ
  else: SHV
```

## Headline metrics

**LIVE 18y (2008-2026):**
- 60/40 PROD: Sharpe 1.47, CAGR 16.10%, MaxDD -13.85%
- BULL-QQQ standalone: Sh 1.12, CAGR 19.95%, MaxDD -28.56%
- CPM standalone: Sh 1.29, CAGR 12.94%, MaxDD -10.59%

**EXT 32y (1994-2026, incl. dot-com):**
- 60/40 PROD: Sh 1.22, CAGR 13.63%, MaxDD -18.4%
- BULL-QQQ standalone: Sh 0.91, CAGR 17.71%, MaxDD -41.1%
- CPM standalone: Sh 1.09, CAGR 10.24%, MaxDD -14.2%

**Forward expectations (heavily discounted):**
- CAGR 8-12% (NOT backtest 16%)
- Sharpe 0.90-1.20 (NOT backtest 1.47)
- MaxDD -15% to -25% (closer to EXT than LIVE)

## Major changes this session

1. **80/20 -> 60/40 blend** (user-requested for higher bull-tilt at tied Sharpe)
2. **Canary upgraded to 3-asset** (HYG+LQD+TIP, +0.04 Sh over HYG+TIP)
3. **Composite trend filter** (12-1 OR 13612W; refutes "OR over-permissive" concern)
4. **Top-tercile override** (67th pct expanding, OOS-defensible, oracle-locked)
5. **README updated** with validation tables, research backing, exact pseudocode
6. **Validation log expanded** (research/oracle_v2_validation_2026.log)

## Critical findings from validation

### What we tested and KEPT
- **XLP-only in +-+**: best across LIVE/TEST OOS/EXT, ties XLU on TEST
- **3-asset OR canary**: best vs 2-of-3, all-positive, single-asset rules
- **SHV cash mode**: most consistent, no era-specificity
- **QQQ as default bull asset**: wins every momentum quintile in +++
- **40% sleeve weight**: oracle-validated, max-Sharpe between 60-80% blend range

### What we tested and REJECTED
- XLP/XLV basket: -0.007 Sh after cost (cost > marginal benefit)
- XLP/XLU 50/50 / XLP/XLV/XLU 1/3: all within bootstrap noise
- Broader defensive ETFs (SCHD/NOBL/VIG/DGRO/SPLV/HDV/DVY/USMV/RSP):
  no material edge over XLP, shorter histories
- IEF in cash mode: 3-of-4 windows favor, but TEST OOS tied; 2022 rate-rise drag
- TLT-when-both-off: era-specific (TRAIN big win, OOS loss)
- XLU-when-canary-off-trend-on: 2008-16 win, 2017-26 collapse, era-specific
- XLP-when-trend-off-canary-on: modern win, EXT loss, regime-dependent
- GLD overlay: DD blows up
- Best-of-safes rotation (BIL/SHV/SHY/IEF): no edge, more complexity
- VIX-conditional defensive: no edge across quintiles
- Yield curve inversion gate: no edge
- HY-IG credit spread proxy: no edge
- SMH-default-in-+++: TEST OOS +0.047 Sh but EXT -0.057, era-dependent (AI rally)
- XLE/XLF/XLV in +-+: raw-mean dramatic but production backtest worse than XLP

## Validation rigor applied

### Bootstrap CI on XLP edge (n=16 +-+ firings across 32y)
- Mean: +1.04%/month
- 95% CI: [-0.48%, +2.55%] (includes zero)
- P(edge > 0): 90.9%
- t-stat: 1.28, p=0.22 (not stat-sig at 5%)
- BUT consistent across windows: LIVE +0.91%, TRAIN +0.91%, TEST OOS +0.90%

### OOS train/test split (2008-16 vs 2017-26)
- XLP/XLV basket: TRAIN win didn't generalize OOS
- XLP-only: ranks top-3 across both halves
- TRAIN winner (XLV @ 1.316) was 4th in TEST -- classic overfit
- Mechanism family (defensive sectors) validated OOS

### Multi-canary disagreement zone (vs HAA single-TIP)
- 34 of 220 LIVE months: HAA defensive, we risk-on
- Aggregate: QQQ +1.49% vs SHV +0.11% in those months
- Annual sleeve impact: ~+2.56%/yr from being risk-on when HAA wrong
- Mechanism: "rising rates on healthy growth" != risk-off (HAA conflates)

### Regime-conditional correlation (refutes diversification skepticism)
| Regime | n | CPM-BULL corr |
|---|---:|---:|
| Overall | 221 | 0.23 |
| Risk-on (SPY 12-1 > 0) | 182 | 0.25 |
| Risk-off (SPY 12-1 < 0) | 39 | 0.09 |
| **SPY bear (DD < -20%)** | 17 | **-0.13** |

Diversification gets STRONGER in bears (not weaker as oracle worried).

### Dot-com 1999-2003 stress test
- 60/40 negative only in 2000 (-2.2%)
- Positive in 2001/2002/2003 while SPY/QQQ bled
- Trend filter held through worst Nasdaq stress in modern history

## Academic backing established

Documented in README "Credit-stress regime sector rotation" subsection:
- Neuberger Berman (2024): credit spread widening -> defensive sector outperformance
- Hartford Funds (2025): staples-vs-tech cash-flow duration thesis
- Fidelity Business Cycle: late-cycle defensive leadership framework
- S&P Dow Jones (2024): quality factor in falling-growth regimes
- Collin-Dufresne et al.: HY credit spreads driven by equity factors
- **Keller HAA (2022)**: TIP canary + 13612W -- direct ancestor of our spec
- Our spec = HAA mechanism + multi-canary stress detection +
  state-conditional sector rotation + composite trend filter

## Honest caveats (in README)

1. In-sample selection bias on hyperparameters/universe
2. Universe risk (factor leadership pre-2015 different)
3. Stitched proxies degrade pre-2010
4. Structural lag on V-shaped recoveries
5. Bull-rally underperformance (MAX_LEVERAGE=1.0)
6. BULL-QQQ adds tail risk (COVID -16.8% sleeve, blend -1.6%)
7. BULL-QQQ CAGR is QQQ-era driven (forward anchor ~7-10%, not 18-20%)

## Files modified this session
- `bull_qqq_live.py`: docstring rewrite, BULL_BY_STATE ablation comment with OOS evidence
- `README.md`: 60/40 blend updates, Validation vs critique section,
  Credit-stress regime references, exact pseudocode, forward expectations discount,
  COVID-whip caveat, BULL tail-risk caveat, QQQ-era CAGR caveat
- `build_dashboard.py`: BULL_BLEND = 0.40, header text fixes
- `cpm_dashboard.html`: regenerated, 807KB

## Research artifacts added
- `research/oracle_v2_validation_2026.log` (641 lines): all validation outputs
- `research/session_2026_05_summary.md` (this file)

## Session lessons learned

1. **My ablation re-implementations had subtle bugs** vs production module --
   always A/B test via real module, not standalone re-implementation
2. **Raw forward-return means lie**: XLE +5.10% in +-+ raw mean, but production
   backtest with switching costs has XLE worst (vol/DD kills Sharpe)
3. **Era-specificity is real**: many "promising" alternatives (XLU/SMH/TLT)
   showed big TRAIN edge that collapsed OOS. Always split-test.
4. **Mechanism family validates direction, not specific asset**: defensive
   sectors as a family beat QQQ in +-+, but XLP-vs-XLV-vs-XLU is noise
5. **Bootstrap CIs prevent over-confidence**: XLP edge p=0.22 means we should
   keep the small-sample caveat prominent even though OOS-consistent
