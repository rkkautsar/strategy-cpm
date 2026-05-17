# Leveraged ETF Practitioner Research (Retail + Quant-Style Usage, 2024-2026)

## Scope and caveat

This review focuses on **how practitioners actually run leveraged ETF systems**, not on static buy-and-hold narratives. Most cited evidence is from: (a) primary strategy authors, (b) long-running community implementation threads, and (c) quant research shops publishing methodology. Community sources are useful for live behavior and operational lessons, but are not audited fund records.

---

## 1) HFEA (Hedgefundie’s Excellent Adventure)

### Canonical rules

HFEA originates from the Bogleheads “Part I / Part II” threads: initially risk-parity-leaning, then commonly implemented as **55/45 UPRO/TMF** with **quarterly rebalance**.[1][2][3]

Core mechanics in practitioner usage:
- 55% 3x US equity beta (UPRO)
- 45% 3x long duration Treasuries (TMF)
- Rebalance each quarter (or around quarter-end bands in some variants)[3]

### How it evolved

Post-2022, serious practitioners split into camps:

1. **Keep vanilla HFEA** (55/45, no regime filter), arguing 2022 was a known failure mode and horizon must be multi-cycle.[6]
2. **Duration redesign** (replace LTT with ITT/STT + futures leverage): e.g., Bogleheads/Reddit variants using intermediate/short Treasuries and futures to reduce rate-shock sensitivity.[7][8]
3. **Canary/risk-off overlays** (BAA/HAA-style filters, managed futures sleeves): avoid staying fully exposed when stock/bond correlation flips positive.[9][20][21]

### Post-2022 reality check

Documented pain was severe:
- Community-reported drawdown framing of **~67% YTD** at 2022 lows became a reference point.[5]
- A Bogleheads subreddit follow-up reported **~51% over two years** and emphasized regime fragility of stock+duration leverage when rates and equities fall together.[4]
- Even supporters called it “fun-money” sizing in many threads, not core retirement capital.[4][6]

### Backtest vs live gap

Backtests (especially pre-2022) looked excellent; live adoption got hit by the exact tail risk critics flagged: **simultaneous equity drawdown + duration shock**.[4][5][6]

### Current practitioner consensus (2024-2025)

- Consensus is **not dead, not dominant**.
- Conviction shifted from “all-in thesis” to “small aggressive sleeve,” often combined with managed futures, gold, or lower leverage alternatives (SSO/ZROZ/GLD discussions show this migration).[6][26][27]

### Failure modes

- Stock/bond positive-correlation shock
- Rebalance into falling knife when both legs fail
- Behavioral capitulation at -50% to -70%+
- Tax drag if implemented in taxable and rebalanced tightly

### Deployability verdict

**Live-deployable only with explicit sizing discipline and expected severe drawdowns.** For many, now treated as a tactical sleeve, not full-portfolio core.[4][6]

---

## 2) 9SIG (Jason Kelly’s quarterly target-growth system)

### Exact rules (practitioner version)

From Kelly materials and user-guide excerpts discussed on his strategy page:
- Base/reset allocation around **60% stock / 40% bond** for 9Sig implementations (commonly TQQQ/AGG)
- Quarterly signal-line growth target (9% for 9Sig)
- Sell surplus vs target / buy shortfall vs target at scheduled quarter marks
- “Spike reset” and “buying power throttle” style safety rules (community cites: reset trigger near very large quarter gain and cap buy using bond sleeve fraction)[10][11][12]

### Real-world outcomes and critiques

Evidence is polarized:
- Some long-time users report very large absolute gains in favorable sequences.[13][14]
- Critics highlight **bond depletion** and **path dependency** in prolonged drawdowns: when dry powder is exhausted, system can degrade into near buy-and-hold leveraged exposure.[13][18]

### Backtest vs live gap

Important nuance from modern reconstructions:
- One high-effort reimplementation notes earlier online critiques were partly due to incorrect rule implementation, but still reports very deep drawdowns in realistic variants.[13]
- Community backtests show attractive CAGR but extreme tail drawdowns (e.g., very high negative DD in long synthetic windows).[18]

Live/OOS signal from an ongoing real-money tracker:
- 9Sig showed strong recoveries in certain V-shaped regimes and in some updates led the compared leveraged strategies.[14]
- It also experienced deep interim drawdowns (tracker discussions describe large swings consistent with system design).[14]

### Consensus on sizing/conviction

- True believers run high concentration.
- Broader experienced community treats 9Sig as **high-conviction/high-path-risk**, often recommending account-type constraints (tax-advantaged preferred) and modest sizing.[13][18][27]

### Failure modes

- Extended bear + repeated buy signals -> dry powder exhaustion
- Tax friction from quarterly rebalance in taxable
- Rule drift (many users run partial 9Sig, then call it 9Sig)

### Deployability verdict

**Deployable for disciplined operators who accept catastrophic historical drawdown risk and strict process adherence.** Not robust to casual execution.

---

## 3) “TQQQ for the long run” family (TFTLR / TQQQ-TLT style variants)

### What practitioners actually run

In community practice, “TFTLR” is less a single strategy and more a cluster:
1. **Static mix variants** (often equity LETF + duration hedge, ratios discussed as 50/50, 70/30, 60/40-like forms depending on risk appetite)
2. **Trend-gated leverage** (e.g., 200-day regime filter)
3. **Hybrid risk-off parking** (cash/SGOV/BIL/QQQ accumulation sleeve)

A modern example uses:
- SPY-based 200-day regime with hysteresis (+4% / -3%)
- TQQQ in risk-on, de-lever/risk-off handling in weak regimes
- additional overextension safeguards near extreme distance above moving average.[16][17][19]

### Relation to “Leverage for the Long Run” concept

Practitioner threads repeatedly reference the 200-day moving-average leverage-rotation idea from the Leverage for the Long Run paper lineage.[15][14]

### Backtest vs live observations

- Backtests often show strong DD reduction vs naked TQQQ and can improve geometric survival.
- Live/OOS examples show **insurance cost** in whipsaw periods (missed rebounds) but better capital retention in sustained breakdowns.[14][17]

### Consensus

- Static TQQQ+bond mix alone is increasingly seen as insufficient after 2022 unless paired with trend/risk-off logic.
- Trend filters are now mainstream in practitioner discussion; exact threshold tuning remains contested.[15][16][18]

### Failure modes

- Whipsaw around MA boundary
- Re-entry slippage after fast V rebound
- Overfit threshold tuning (+/- bands, SMA length, re-entry cadence)

### Deployability verdict

**More deployable than static leveraged mixes for many practitioners**, provided one accepts whipsaw tax and follows rules mechanically.

---

## 4) SMA-filtered leveraged trend and broader risk-on/risk-off frameworks

### Common rules in the field

A highly recurrent rule-set:
- Use broad index (often SPY) vs 200-day SMA as regime proxy
- Risk-on: hold leveraged equity (TQQQ/UPRO/QLD/SSO)
- Risk-off: rotate to cash/bills/bonds/defensive sleeve
- Add hysteresis bands to reduce churn (e.g., +4/-3, +1/-1.25).[15][16][17]

### HFEA + canary modifications (BAA/HAA influence)

BAA/HAA framework logic, often adapted into LETF circles:
- Use **canary assets** to decide offensive vs defensive universe
- Offensive when broad internals are positive, defensive otherwise
- Monthly rebalance and momentum-ranked selection in selected universe.[20][21]

This moved many practitioners from pure “always on leverage” to conditional leverage.

### Evidence snapshot

One community backtest series combining 9Sig with a 200-day filter reported materially improved DD/Sharpe profile versus unfiltered 9Sig (while still not risk-free).[18]

### Deployability verdict

**Live-deployable with moderate complexity.** Main risk is parameter overfitting and execution drift.

---

## 5) Vol-targeted leveraged approaches (Carver / ReSolve style)

### Carver-style practitioner framing

Carver-oriented systematic practice emphasizes:
- set explicit portfolio risk target,
- size positions from volatility and diversification,
- scale exposure dynamically instead of static notional leverage.

In open implementation examples (pysystemtrade), risk targeting and position scaling are explicit workflow steps (e.g., configurable percentage volatility target before portfolio construction).[25]

### ReSolve-style practitioner framing

ReSolve’s DAA research stack adds:
- risk-adjusted momentum ranking,
- momentum weighting,
- robust risk-parity methods (ERC/cluster/DRP variants),
- explicit deployment in products with stated volatility targets (e.g., 8% and 12% frameworks referenced in their practitioner series).[22][23][24]

### What this means for TQQQ users

Instead of fixed 100% TQQQ or fixed ratio with hedge:
- target portfolio vol (example bands often 10-15% in practitioner literature),
- scale LETF weight inversely with realized vol and correlation context,
- cap gross leverage and require trend confirmation.

### Backtest vs live gap

- Institutional-style vol targeting generally improves risk-adjusted metrics in research publications.
- Retail live adoption is lower due to complexity and data/process demands.

### Deployability verdict

**High potential, high process burden.** Better suited for quantitatively disciplined users than discretionary retail traders.

---

## 6) Best LETF risk-management practices (practitioner synthesis)

Across communities, durable practices repeat:

1. **Position sizing first**: keep LETFs as sleeve capital unless strategy has strict regime exits.[4][6][27]
2. **Pre-commit regime rules**: avoid discretionary panic exits during crashes.[15][16][17]
3. **Diversify risk-off engine**: not just long duration; include alternatives/managed futures when possible.[6][8][21][27]
4. **Control whipsaw expectations**: insurance is costly but can preserve survival.[14][17]
5. **Tax-aware implementation**: quarterly/high-turnover systems are materially different in taxable vs sheltered accounts.[13][27]
6. **Avoid look-ahead and proxy sloppiness**: several community “too-good” variants later failed on implementation rigor.[9]

---

## 7) Critical lessons from the 2022 LETF disaster window

### What failed hardest

- Static leveraged stock+long-duration bond stacks under rising-rate inflation shock.
- Overconfident extrapolation from falling-rate backtests.
- High-concentration deployments without explicit drawdown budget.[4][5][6]

### What survived better

- Systems with **explicit risk-off rotation** (even when imperfect due to whipsaw).
- Investors who maintained process discipline (rebalance/DCA by plan) rather than discretionary capitulation.[5][14]
- Portfolios that added non-equity/non-duration crisis diversifiers (managed futures, canary-conditioned defense).[6][8][21][27]

### Practical takeaway

Most “experienced survivor” narratives are not about finding magical tickers. They are about:
- smaller sizing,
- cleaner rules,
- less leverage at wrong times,
- and avoiding full dependence on one hedge regime.

---

## 8) Comparison snapshot (backtest and live/OOS where available)

| Strategy | Typical rules | Backtest profile (reported) | Live/OOS observations (reported) | Practitioner verdict |
|---|---|---|---|---|
| HFEA (55/45 UPRO/TMF) | Quarterly rebalance | Strong long-run historical backtests pre-2022 in many studies[3] | Severe 2022 pain (community references near -67% YTD); later mixed recovery; still contentious in 2024-2025[4][5][6][14] | Deployable only for high DD tolerance + strict sizing |
| 9Sig (TQQQ/AGG target-growth) | Quarterly target line, buy shortfall/sell surplus, special reset/throttle rules[10][11][12] | Can show high CAGR but extreme drawdown sensitivity; corrected implementations still very deep in stress windows[13][18] | Tracker threads show both strong recoveries and violent swings; leadership can flip with regime[14] | Process-heavy, path-risky, not casual |
| 9Sig + 200d filter variant | 9Sig only in risk-on; de-risk below 200d | Community example: materially better DD/Sharpe than unfiltered 9Sig in that test set[18] | Still limited true long live history; improving survivability logic | Promising adaptation, still needs robust OOS validation |
| 200d rotation (SSO/QLD/TQQQ variants) | Leveraged on-state, cash/bills/bonds off-state, often with bands[15][16][17] | Generally lower DD than naked LETF; return depends on whipsaw regime[15][26] | Real-money tracker shows protection benefit in some windows, insurance drag in V rebounds[14][17] | Most practical “middle path” in current community |
| Vol-targeted leveraged | Dynamic sizing to target risk, often with momentum + risk parity layers[22][23][24][25] | Risk-adjusted improvements in practitioner research | Sparse transparent retail live logs | Strong framework if ops discipline exists |

---

## Bottom line

If question is “what sophisticated practitioners actually do now,” answer is clear:

- Pure static LETF allocation is no longer consensus default.
- **Regime-aware leverage (SMA/canary/risk-off)** is mainstream.
- **Risk budgeting and vol targeting** are gaining mindshare among serious quants.
- Survivors from 2022 were generally those with **smaller sizing, explicit rules, and diversified defense**, not those with the prettiest pre-2022 equity curves.

---

## References

[1] Bogleheads Part I (HFEA origin): https://www.bogleheads.org/forum/viewtopic.php?t=272007  
[2] Bogleheads Part II: https://www.bogleheads.org/forum/viewtopic.php?t=288192  
[3] Optimized Portfolio - HFEA summary: https://www.optimizedportfolio.com/hedgefundie-adventure/  
[4] r/Bogleheads (2024 update, -51% over 2 years): https://www.reddit.com/r/Bogleheads/comments/1b0vu96/update_2_years_later_hedgefundies_excellent/  
[5] r/LETFs (2022 drawdown discussion, “down 67% YTD”): https://www.reddit.com/r/LETFs/comments/yaac20/hfea_down_67_ytd_and_no_signs_of_slowing_down/  
[6] r/LETFs (HFEA in 2025 consensus thread): https://www.reddit.com/r/LETFs/comments/1jjr0jm/hfea_in_2025/  
[7] r/LETFs (enhanced HFEA via futures/shorter duration): https://www.reddit.com/r/LETFs/comments/ql3ck7/an_enhanced_version_of_riskparity_portfolio_hfea/  
[8] r/HFEA (modified HFEA with ITT/futures/gold/VIX): https://www.reddit.com/r/HFEA/comments/zea7iz/modified_hfea_with_itt_futures_gold_and_vix/  
[9] r/LETFs (inverse-vol canary HFEA variant + look-ahead correction): https://www.reddit.com/r/LETFs/comments/yc67ep/inverse_volatility_canary_hfea_enhancedivchfea/  
[10] Jason Kelly strategy page: https://jasonkelly.com/resources/strategies/  
[11] Jason Kelly “9Sig at 9”: https://jasonkelly.com/9sig-at-9/  
[12] 9Sig simulator (rule controls and synthetic history tooling): https://9sig.networthcast.com/  
[13] BestFolio - 9Sig revisited analysis: https://bestfolio.app/blog/kelly-signal-danger-v2  
[14] r/LETFs real-money longitudinal tracker (original + updates): https://www.reddit.com/r/LETFs/comments/1bivl9k/gehrmans_bumpy_ride_starting_my_realmoney_test_of/  
[15] r/LETFs 200-day MA discussion (Leverage for the Long Run references): https://www.reddit.com/r/LETFs/comments/mfugvt/trading_letfs_upro_tqqq_etc_using_sp_200day/  
[16] r/LETFs SPY200SMA (+4/-3) TQQQ/QQQ strategy: https://www.reddit.com/r/LETFs/comments/1nhye66/spy_200sma_43_tqqqqqq_long_term_investment/  
[17] r/LETFs SPY200SMA strategy update: https://www.reddit.com/r/LETFs/comments/1s5h2js/spy_200sma_43_tqqqqqq_long_term_investment/  
[18] r/LETFs combined 9Sig + 200-day SMA backtest: https://www.reddit.com/r/LETFs/comments/1s9d9v0/combined_9sig_200_day_sma_backtesting/  
[19] r/LETFs “TQQQ for the Long Run” variant discussion: https://www.reddit.com/r/LETFs/comments/1q7j5qv/tqqq_for_the_long_run/  
[20] Allocate Smartly - Bold Asset Allocation: https://allocatesmartly.com/bold-asset-allocation/  
[21] Allocate Smartly - Hybrid Asset Allocation: https://allocatesmartly.com/hybrid-asset-allocation/  
[22] ReSolve DAA Part 3 (risk-adjusted momentum): https://investresolve.com/dynamic-asset-allocation-for-practitioners-part-3-risk-adjusted-momentum/  
[23] ReSolve DAA Part 4 (momentum weighting): https://investresolve.com/dynamic-asset-allocation-for-practitioners-part-4-momentum-weighting/  
[24] ReSolve DAA Part 5 (robust risk parity): https://investresolve.com/dynamic-asset-allocation-for-practitioners-part-5-robust-risk-parity/  
[25] Rob Carver pysystemtrade intro (risk target + position sizing workflow): https://raw.githubusercontent.com/robcarver17/pysystemtrade/master/docs/introduction.md  
[26] r/LETFs 40-year LETF rotation study: https://www.reddit.com/r/LETFs/comments/1t7q8or/40year_letf_rotation_backtest_5_strategy_families/  
[27] r/LETFs risk-management discussion: https://www.reddit.com/r/LETFs/comments/1dww3sy/best_passive_simple_risk_management_strategies/
