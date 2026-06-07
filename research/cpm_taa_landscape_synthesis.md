# CPM TAA Landscape Synthesis

Generated: 2026-06-07
Source corpus:
- /tmp/taa_synthesis.md
- Additional /tmp artifact paths cited in source memo: none

---

# TAA Synthesis and Decision Memo: Where CPM Sits, What It Misses, and What to Test Next

Scope: long-only, monthly, ETF/asset-class tactical allocation. Capstone synthesis of the
research corpus (academic survey, practitioner survey, valuation/carry, macro/regime,
risk-weighting/ensemble) mapped against the code-authoritative CPM specification, and
reconciled with the strategy's own prior experiment record under research/.

Evidence-quality key (used throughout):
- EVIDENCED: corroborated by peer-reviewed OOS work or by the repo's own backtests.
- IN-SAMPLE / SINGLE-RUN: one backtest on the development window; not yet OOS-validated.
- HYPOTHESIS: mechanically plausible, not yet tested here.
- BLOG/EMPIRICAL: practitioner claim, lower evidentiary weight (no costs/CI/look-ahead control).

Honesty anchor from the repo: CPM in-sample sleeve Sharpe is 1.2373; the memo's own forward
haircut ladder discounts that to ~0.70 forward planning Sharpe (cpm_memo.md:148-151). Treat
every "lift" below against that discount and against bootstrap-CI width, not against the
in-sample point estimate.

---

## 1. The Family Grid (signal type x mechanism+defense)

Rows are the trigger/signal axis. Columns combine the selection mechanism with the defense
mechanism. CPM occupancy is marked in brackets: [CORE]=CPM core sleeve (60%), [NDX]=Nasdaq-100
momentum (15%), [VAL]=value+quality (15%), [RPV]=risk-premia value (10%).

Columns:
- A: Rank-rotation, NO built-in defense (always fully invested)
- B: Rotation + own absolute/trend gate to cash (dual momentum / per-asset SMA)
- C: Separate canary or breadth-count gate (binary or fractional risk-off)
- D: Risk-based sizing (inverse-vol / min-var / risk-parity / HRP)
- E: Overlay/filter layered on another strategy (macro filter, vol-target, seasonality, tranching, intermarket)

| Signal axis | A: rotation, no defense | B: own absolute/trend gate | C: canary / breadth gate | D: risk-based sizing | E: overlay/filter |
|---|---|---|---|---|---|
| Absolute trend / TSMOM (F1) | (n/a; trend is itself a defense) | Faber GTAA5/13, RAA(Alpha Arch), Hurst/MOP century-trend; **[RPV 200d SMA leg], [VAL trend band], [CORE Faber>0 eligibility]** | - | vol-scaled TSMOM (Moskowitz, Hurst) | Trinity (50% trend overlay) |
| Relative momentum (F2) | Jegadeesh-Titman, sector relative strength, AQR momentum | GEM, Composite Dual Mom, Accel Dual Mom; **[NDX top-5 single-stock selection]** | - | AAA, EAA, FAA; **[CORE vol-adj Faber rank + min-var 3-of-4 subset]** | - |
| Multi-asset breadth / canary (F4) | (incoherent) | - | PAA (fractional), VAA (binary), DAA, BAA, HAA, GPM; **[CORE C1 breadth cliff {3:0.5,4:1.0}]** | - | - |
| Valuation level (F5) | Faber Global Value, StarCapital CAPE, Keppler, AQR value (relative) | Faber Global Value abs-filter, GMO 7yr, RAFI; **[RPV spread-z>0], [VAL value-z selection]** | - | RAFI mean-variance | - |
| Mean-reversion / contrarian (F5) | Late-stage contrarian, time-series reversal | - | - | - | EOM stock-bond reversal, TSR with NBER gate |
| Macro / economic regime (F6) | (pure macro rotation: empty-for-a-reason) | - | (BLEND-LEVEL macro canary: UNEXPLORED-TRANSFERABLE) | All Weather (static risk-parity quadrant); dynamic macro risk-budget UNEXPLORED | GTT / GTT-UE, SPY-COMP, LAA, RAA, Sahm, yield-curve inversion, HY OAS level, NFCI, LEI, Hedgeye quadrant. **CPM: NONE** |
| Volatility / risk state (F7) | - | - | (VIX-TS breadth canary: partly tested) | Moreira-Muir vol-managed, Barroso-Santa-Clara, risk parity, min-var; **[CORE min-var cov]** | vol-target overlay; VIX term-structure gate; **[NDX/VAL SPY RV20<RV252 leg]** |
| Carry / yield (F10) | KMPV cross-asset carry, Keppler dividend-yield | carry + vol/credit gate; **[RPV term/credit spreads ~ bond carry]** | - | - | - |
| Intermarket relative (F6) | - | - | (intermarket majority-vote gate: TRANSFERABLE but price-based) | - | Gayed XLU/SPY, Lumber/Gold, TLT/IEF duration, ATAC credit rotation |
| Seasonality / calendar (F9) | - | - | - | (incoherent) | Sell-in-May, Turn-of-Month |

Empty-cell classification (the actionable part):

GENUINELY UNEXPLORED / TRANSFERABLE
- Macro/economic regime as a BLEND-LEVEL gate (F6 x C). No CPM sleeve carries a non-price
  economic trigger. This is the single clearest structural gap.
- Dynamic macro-regime risk budgeting (F6 x D). CPM blend weights are static; All Weather is
  only the static version of this cell.
- Volatility-state breadth canary at the blend (F7 x C), e.g. VIX term-structure as one vote
  in a majority gate. Partly probed on the prior BULL sleeve; not at the current blend.

EMPTY FOR A REASON / INCOHERENT
- Relative momentum with no defense (F2 x A) used as crash protection: incoherent; it stays
  fully invested in the best-falling asset. This is exactly why dual momentum adds the gate.
- Breadth/canary with no defense (F4 x A): incoherent; the canary IS the defense.
- Pure macro rotation with no price confirmation (F6 x A): empty-for-a-reason. Macro data lags
  and is revised; the Growth-Trend-Timing lesson is to let macro turn the price filter ON/OFF,
  not to trade macro alone.
- Valuation-breadth canary (F5 x C): weak. Valuation moves too slowly to function as a fast
  risk-off canary; "early is indistinguishable from wrong."
- Carry as a long-only single-asset monthly gate (F10): mostly incoherent. Carry is inherently
  cross-sectional long-short; the coherent long-only slice (term/credit carry) is already
  approximated by RPV.
- Seasonality x risk-sizing (F9 x D): incoherent; calendar carries no risk content.

---

## 2. CPM Family Map and Nearest Published Neighbors

The blend itself is a multi-factor ensemble (F8): four sleeves combined by fixed linear
weights (CPM 60 / NDX 15 / VAL 15 / RPV 10), monthly signal at month-end close, executed at
next-open (MOO), 10 bps/side.

Sleeve-by-sleeve placement:

- CPM core (60%): a hybrid of breadth-gated rotation (F4, PAA branch), risk-based sizing (F7),
  and volatility-adjusted relative/absolute momentum (F2/F1). Signal = vol-adjusted Faber rank
  over 8 assets with a positive-Faber eligibility screen. Defense = C1 breadth cliff on n_pos
  ({1,2 -> 0% risky, 3 -> 50%, 4 -> 100%}) plus a best-of-safe SHV/IEF absolute-momentum pick.
  At full breadth, weights come from a min-variance 3-of-4 subset (Adaptive-AA style). The
  external canary is DISABLED; the breadth count replaces it.
- NDX (15%): single-stock relative momentum (F2) on point-in-time Nasdaq-100, top-5 by 13612U,
  defended by a triple AND gate (TIP momentum > 0 AND SPY momentum > 0 AND SPY RV20 < RV252).
  Lineage: Global Equity Momentum applied to single stocks with a localized vol/regime gate.
- VAL (15%): value+quality selection (F5) on point-in-time Nasdaq-100, a stateful high-entry/
  tight-exit trend band (F1), defended by the SAME triple gate as NDX.
- RPV (10%): risk-premia value spreads (F5 with carry flavor F10), 120-month z-score, each leg
  gated by its own 200-day SMA (F1); residual to cash.

Nearest published neighbors and how CPM differs:

- HAA (Hybrid Asset Allocation): closest lineage to CPM core. DIFFERENCE: CPM core disables
  HAA's single TIP canary and replaces it with an own-universe breadth cliff (PAA branch); it
  ranks by volatility-adjusted Faber (EAA) instead of unweighted dual momentum; and it sizes
  via a min-variance subset (AAA). CPM core is essentially "HAA skeleton, de-canaried,
  EAA-ranked, AAA-sized."
- EAA (Elastic Asset Allocation): CPM core's return/volatility ranker is EAA in spirit.
  DIFFERENCE: defense is the breadth cliff, not EAA's correlation-aware crash protection.
- PAA (Protective Asset Allocation): the breadth-count fractional defense IS the PAA idea.
  DIFFERENCE: CPM counts over its own top-of-universe with a discrete cliff curve rather than a
  linear bond fraction over 12 assets, and defends into best-of-safe rather than fixed IEF.
- VAA: shares fast multi-period momentum and rotation-to-defense. DIFFERENCE: VAA is binary
  (any-negative -> 100% single defensive); CPM core is fractional and holds multiple risky names.
- DAA: separate-canary count -> cash fraction. DIFFERENCE: CPM core uses OWN-universe breadth,
  not a separate EM+bond canary.
- BAA-G12: G4 canary any-negative + SMA-ranked offensive + 7-asset defensive. DIFFERENCE: no
  separate canary, smaller universe, EAA ranking, min-var sizing.
- GEM: two-way dual momentum with absolute gate to bonds. DIFFERENCE: CPM core is multi-asset
  (not 2-way); CPM NDX is GEM-shaped but on single stocks with a TIP+SPY+vol gate.
- AAA: relative-momentum top-5 + min-variance. DIFFERENCE: CPM core selects a min-variance
  3-of-4 SUBSET and layers the breadth cliff and best-of-safe; AAA has neither.
- FAA: meta-rank on momentum+volatility+correlation + absolute gate. DIFFERENCE: CPM core uses
  momentum/volatility but no explicit correlation meta-rank; defense is the breadth cliff.
- GTAA13: rank top-N + per-asset 10-month SMA gate. DIFFERENCE: CPM core adds vol-adjustment,
  the breadth cliff, min-var sizing, and best-of-safe.

Implication for later sections: CPM core is already a tuned composite of HAA + EAA + PAA + AAA.
Any "replacement" drawn from that same set is a sibling reshuffle, not an orthogonal challenger.

---

## 3. Key Structural Finding: De-risk-Trigger Concentration Is Total on Price

Trigger map by capital share:
- 60% (CPM core): de-risks on OWN 8-asset price-momentum breadth (n_pos of vol-adjusted Faber).
- 30% (NDX + VAL): de-risks on a SHARED triple gate (TIP momentum, SPY trend, SPY vol regime).
- 10% (RPV): de-risks on per-asset value-spread z PLUS its own 200-day SMA.

The two hard facts:
1. 100% of the book has a PRICE-based component in its defensive trigger. RPV's value-spread z
   is the only non-price ingredient anywhere, and it is still gated by a 200-day SMA, so even
   that 10% cannot de-risk on valuation alone.
2. 0% of the book carries a macro/economic-regime trigger (unemployment, yield curve,
   credit-spread LEVEL, ISM, recession, financial-conditions). CPM is structurally blind to the
   real economy; it only sees price, trend, and realized volatility.

Two concentration sub-risks:
- Shared 30% gate. NDX and VAL de-risk off the SAME TIP+SPY+vol condition, so a single
  non-systemic TIP or SPY momentum wobble flips 30% of the book at once. (Caveat from the repo:
  in the CPM-core canary study, TIP's PIVOTAL share of risk-on months was only ~7%, not the
  60-80% sometimes assumed -- cpm_crossasset_overlay_findings.md section 1c. So the shared-gate
  risk is structural to NDX+VAL by construction, but TIP as a single dominant lever is weaker
  than feared.)
- Bond-dependence of the defense. Best-of-safe and the min-var subset both lean on IEF when it
  ranks well; only the SHV cash leg is truly crash-proof when stocks and bonds fall together.

Known and likely failure modes, weighted by evidence:
- Sharp V-reversal / fast-gap crash (EVIDENCED, and largely IRREDUCIBLE at monthly cadence).
  COVID-2020 and the 2025 tariff shock are the worst non-2010 crisis rows (CPM core ~-10.2% and
  ~-10.7%). The repo confirms this is structural: BOTH the vol-target study and the macro-gate
  study leave the COVID drawdown essentially UNCHANGED, because a monthly, lagged signal fires
  the month AFTER the gap (cpm_voltarget_paramfree_findings.md per-crisis table;
  bull_strengthen_macro_findings.md section 3). No monthly overlay tested has pre-empted COVID.
- Slow-building stress where price grinds down (EVIDENCED as the IMPROVABLE failure). GFC,
  Euro-2011, and 2022 drawdowns DO shrink under a volatility-target overlay (GFC -7.4% -> ~-6.1%,
  2022 -5.1% -> ~-4.0% at the blend; cpm_voltarget_paramfree_findings.md). These are the crises
  where a risk-state overlay has room to work.
- Binding blend tail is a sharp 2010 event, not a textbook bear (EVIDENCED on the prior blend).
  In the 60/20/20-era blend analysis, the binding blend MaxDD was the May-2010 flash-crash /
  Euro-debt episode (~-10.46%) and was NDX-INDEPENDENT (cpm_blend_ndx_overlay_findings.md:68-69).
  Sleeve-level surgery did not move it. This should be re-confirmed on the current 4-sleeve blend.
- 2022-style joint stock/bond selloff (PARTIALLY MITIGATED already; do not overstate). 2022 is
  CPM core's SHALLOWEST crisis (~-5.2%), because best-of-safe defaults to SHV cash when IEF
  momentum is negative. The named "bonds fail as the hedge" risk is real only in the residual
  case where the strategy is holding IEF and bonds gap faster than the monthly rebalance.
- Whipsaw in choppy, trendless regimes (HYPOTHESIS, general trend-family weakness). Not isolated
  in the crisis table; the 1970s stagflation studies in the repo probe this regime.

Net: CPM's protection is reactive and price-conditioned. It handles slow grinds and the
2022 rates shock well, is structurally exposed to fast V-reversals (an exposure shared by every
monthly strategy), and has zero orthogonal early-warning channel.

---

## 4. Cross-Pollination Matrix and What the Repo Already Settled

Transferable techniques vs CPM usage, annotated with the repo's verdict so we do not relitigate
closed questions.

| Technique | CPM already uses? | Repo verdict / status |
|---|---|---|
| Canary / breadth gate | YES (core C1 own-breadth; NDX/VAL TIP+SPY) | Multi-asset canary upgrade TESTED -> REJECT (lowers Sharpe, no crisis gain). cpm_crossasset_overlay_findings.md sec 1 |
| Fractional defense (PAA) | YES (core {3:0.5,4:1.0}) | Core to current design; validated in memo C1-cliff table |
| Vol-target overlay | PARTIAL (vol-adj rank + SPY RV gate; no blend vol-scaling) | TESTED, LEADING candidate. Parameter-free expanding-60/40 anchor matches fixed VT-10; improves GFC/Euro/2022 DD; COVID unchanged. Pending bootstrap/WF. cpm_voltarget_paramfree_findings.md |
| Multi-lookback ensemble | PARTIAL (13612U is one weighted composite; gates single-composite) | Not consolidated into a fractional multi-lookback gate; open |
| Recession / macro filter | NO (the structural gap) | TESTED on prior BULL sleeve (VIX-term, yield curve): marginal, one-event (COVID), within noise; NOT on current blend. bull_strengthen_macro_findings.md |
| Contrarian / mean-reversion entry | PARTIAL (VAL/RPV valuation tilt) | Carry/value tilt on CPM core TESTED -> REJECT. cpm_crossasset_overlay_findings.md sec 2 |
| Risk-parity weighting | PARTIAL (core min-var subset; blend weights STATIC) | Blend-level HRP/risk-parity NOT tested on the current 4-sleeve blend. Genuine gap |
| Confirmation / hysteresis | PARTIAL (VAL high-entry/tight-exit band) | Vol-gate hysteresis explored on BULL; not applied to core breadth cliff |
| Rebalance-timing tranching | NO | Examined (memo_review2_tranching_tom_decay); not adopted |
| Correlation / absorption (PC1) gate | NO | TESTED -> REJECT, documented overfit (single 2010-2012 episode, zero OOS value). cpm_pc1_walkforward_findings.md |

Highest-value cross-pollination ideas, ranked by mechanical plausibility AND whether they repair
a NAMED failure mode (after discounting closed questions):

1. Volatility-target overlay at the blend (repairs slow-stress drawdowns). EVIDENCED-promising.
   Best repaired failure: the GFC/Euro/2022 grind-downs. Does NOT repair COVID (confirmed). The
   parameter-free expanding-60/40 anchor removes the hand-picked target and rediscovers ~10%
   from a balanced portfolio's own long-run vol. Status: needs a bootstrap/walk-forward
   significance pass; that is the repo's own stated next handoff.
2. Orthogonal NON-PRICE economic gate at the blend (fills the one true structural gap).
   HYPOTHESIS at the current blend; partially EVIDENCED-marginal on the old sleeve. Use a level
   signal that is decoupled from price: Sahm rule or HY OAS level (recession/credit channel) and
   Growth-Trend-Timing on unemployment (whipsaw suppressor). It cannot fix fast V-reversals
   (macro lags too), but it is the only candidate that can de-risk when the economy or credit
   has cracked while price has not yet broken.
3. Blend-level risk budgeting (HRP / inverse-vol) instead of static 60/15/15/10 (repairs the
   F7-at-blend gap). HYPOTHESIS at the current blend. Mechanically sound and stable; reins in
   the high-vol single-stock sleeves. Caveat: the binding blend tail was a sharp 2010 event that
   sleeve surgery did not move, so expect a risk-budget/Sharpe improvement, not crash-tail relief.
4. Multi-lookback + fractional hardening of the shared NDX/VAL gate (reduces shared-gate whipsaw).
   HYPOTHESIS. Replace the binary single-composite gate with a 1/3/6/12 ensemble that de-risks
   25% per failed lookback. This HARDENS the existing gate; it does not diversify the trigger.
5. Rebalance-timing tranching and breadth-cliff hysteresis (robustness hygiene). HYPOTHESIS/
   examined. Cheap, removes calendar luck and boundary chatter; not crash protection.

Do NOT re-propose: multi-asset canary, carry/value tilt on the core, or a correlation/PC1 gate.
All three are already tested and rejected in the repo.

---

## 5. Alternatives to CPM (two separate bars)

### 5a. Diversifiers (add a sleeve or replace a fraction)

Bar: low return-correlation to CPM ESPECIALLY in crisis sub-samples, plus a complementary
failure mode. Ranked.

1. Volatility-target overlay (risk-state, F7). Mechanic: scale the blend's risky exposure by
   min(1, target/realized-vol), de-risk-only, shed to SHV; parameter-free expanding-60/40
   target. Orthogonal trigger: portfolio realized volatility level (a magnitude channel, not a
   direction channel). Covers: slow-stress grind-downs where CPM's directional triggers are slow
   (GFC, Euro-2011, 2022). Evidence: IN-SAMPLE strong and parameter-free, matches fixed VT-10 on
   every blend metric; needs significance test. Behavior vs CPM: highly correlated in calm,
   de-correlated in rising-vol regimes; explicitly does NOT help COVID-type gaps. Honest label:
   this is a hardening OVERLAY more than an orthogonal diversifier, but it is the best-evidenced
   single improvement on the table.
2. Orthogonal macro/regime sleeve or gate (F6). Mechanic: a non-price recession/credit level
   signal -- Sahm rule (3m unemployment vs trailing low + 0.50), or HY OAS level > ~600 bps, or
   Growth-Trend-Timing on unemployment vs its 12-month average -- used to scale a fraction of the
   blend to cash, with mandatory t+1 execution on vintage (unrevised) data. Orthogonal trigger:
   the real economy / credit-default premium, fully decoupled from CPM's price complex. Covers:
   macro-led or credit-led selloffs that price has not yet confirmed; suppresses non-recession
   whipsaw. Evidence: GTT and unemployment signals are EVIDENCED and low-revision in the academic
   record; on the repo's prior sleeve a VIX-term or yield-curve ADD gave only a one-event (COVID)
   gain within bootstrap noise. Behavior vs CPM: lowest crisis-correlation of any candidate in
   recessionary grinds; near-useless in fast gaps. This is the structural gap-filler, but the
   honest prior is "modest, regime-specific, must clear significance."
3. Global value / CAPE rotation sleeve (valuation, F5). Mechanic: cheapest-quartile country or
   asset CAPE / multi-metric value, annual valuation signal with a monthly trend overlay.
   Orthogonal trigger: long-horizon valuation level. Covers: the regime where momentum/growth is
   richly valued and mean-reverts (CPM is momentum-heavy and would ride a bubble down). Evidence:
   EVIDENCED (Value-and-Momentum-Everywhere; GMO 25y live), with a strong value-momentum negative
   correlation. CRITICAL HONESTY: value crashes WITH momentum in liquidity crises (both fell in
   2008), so this is a STYLE/regime diversifier, NOT a crisis hedge; it also carries decade-long
   tracking-error risk ("early is indistinguishable from wrong"). Note CPM's VAL sleeve is
   single-stock value, so cross-asset/global CAPE value is genuinely additive in style space.
4. Intermarket majority-vote gate (F6 intermarket). Mechanic: a 2-of-3 vote among XLU/SPY,
   Lumber/Gold, TLT/IEF to scale risk. Orthogonal trigger: cross-asset leadership that leads SPY
   by 2-4 weeks. Covers: earlier onset detection than CPM's own trend. Evidence: BLOG/live but
   whipsaw-prone. Weakness: it is still PRICE-based, so it shares CPM's trigger family and adds
   limited true breadth; use only combined with a non-price signal, never standalone.

Lower tier / cautions:
- All-Weather / risk-parity core (F6/F7): a ballast, not a diversifier; dilutes return and is
  itself 2022-vulnerable on its long bonds.
- End-of-month stock-bond reversal (F5): genuinely orthogonal (calendar liquidity flow) but
  micro-structural, twice-monthly, cost-heavy, blog-grade evidence.
- Cross-asset carry (F10): REJECT as a crisis diversifier. Carry unwinds violently in the same
  liquidity squeezes that hit equities (1998, 2008), so crisis-correlation is HIGH, not low; the
  repo's carry/value tilt also failed on Sharpe and Calmar.

### 5b. Replacements (take CPM's exact risk-on/off rotation slot)

Bar: must DOMINATE CPM on OOS Sharpe AND crisis MaxDD, or match within bootstrap CI while being
simpler/more robust. Reminder: CPM core is already a tuned HAA/EAA/PAA/AAA composite, so these
candidates are same-family reshuffles.

1. AAA (Adaptive Asset Allocation). The only candidate with a hard head-to-head in the repo.
   Result: AAA did not decay post-paper (Sharpe 1.068 in-sample -> 1.228 OOS), CPM beats AAA by
   +0.236 Sharpe over 2016-2026, BUT the paired bootstrap CI is [-0.22, +0.67] (includes zero),
   AND that window is CPM-in-sample versus AAA-OOS, which inflates CPM's edge
   (cpm_vs_aaa_oos_findings.md). Verdict: neither dominates; CPM's edge is within noise and
   in-sample-flattered. Does NOT clear the replacement bar in either direction. KEEP CPM.
2. HAA-variant. Reported ~1.42 Sharpe ~ CPM blend, but CPM core is already a de-canaried HAA;
   re-enabling the TIP canary reverts a tuned choice. At best matches; no domination evidence.
3. BAA-G12. Known 2022 dodge via cash/TIP/DBC defensive, but more universes and parameters =
   larger overfit surface. Match-not-dominate; complexity argues against.
4. DAA / FAA / GTAA13. DAA's separate-canary fractional logic is structurally similar to CPM's
   breadth cliff; FAA adds a correlation axis CPM lacks but at high turnover; GTAA13 is simpler
   and lower-Sharpe. None shows domination evidence.

Replacement verdict: NO candidate clears the bar on available evidence. Every reported edge is
in-sample or blog-grade, sits inside the plausible bootstrap CI of CPM, and the one rigorous test
(AAA) is statistically a tie. The defensible move is to DIVERSIFY/HARDEN, not to REPLACE.

---

## 6. Pre-Registered Pitfalls Applied as Gates

- In-sample / overfit discount. CPM's 1.2373 in-sample sleeve Sharpe is already discounted to
  ~0.70 forward by the memo's own haircut ladder. Any candidate lift smaller than that gap, or
  smaller than the relevant bootstrap-CI width, is not alpha. This single gate kills all
  replacements and demotes the vol-target lift to "needs significance proof."
- Look-ahead / release lag. The macro gate (recommendation 2) is the exposed one: model t+1
  execution on VINTAGE/unrevised series. Prefer low-revision signals (unemployment, Sahm, market-
  priced OAS and yield curve); avoid high-revision composites (LEI, industrial production) or
  discount them heavily. The corpus documents 1-month reporting lags and severe revisions for the
  growth composites.
- Same-trigger / OR-breadth trap. A new gate adds REAL crash protection only if it is orthogonal
  (non-price) and able to force de-risk independently (risk-on requires CPM-positive AND the new
  signal not-stressed). Combining two PRICE signals via "de-risk if either" yields correlated
  flips and whipsaw without added breadth -- this is why the intermarket gate (still price-based)
  ranks below the macro and vol-state gates, and why the multi-asset canary upgrade already failed.
- Regime dependence. Vol-target's lift leans on slow crises (GFC/Euro/2022) and is silent in
  COVID; the macro gate's prior lift was 100% one event (COVID) with a curve-choice degree of
  freedom (10y3m worked, 10y2y did not); global value swings with the value regime (dead
  2013-2020, alive 2021+). Every adoption needs a cross-regime decomposition, not a full-sample
  headline.
- Blog-backtest discount. VIX-term-structure conditional stats, intermarket signals, and the
  EOM reversal are blog/empirical; weight them below the peer-reviewed and repo-reproduced results.
- Multiple testing. The repo has run dozens of overlay variants; the headline winner of any wide
  sweep is the most overfit by construction. The PC1 gate is the cautionary example: a 3-point
  sweep produced a single-cell spike that was a 2010-2012 artifact with zero OOS value. Demand a
  fine parameter surface plus per-episode firing decomposition before believing any new gate.
- Crisis-correlation instability. Score diversifiers on crisis sub-samples, not full-sample
  correlation. This is precisely why carry (crisis-correlated) and global value (crashes with
  momentum) are demoted despite low full-sample correlation.
- Premise verification (done). Before recommending, the repo was checked: macro/vol gates, PC1,
  multi-asset canary, carry tilt, and the AAA comparison are ALREADY tested. The recommendations
  below are scoped to the genuinely open questions and to re-validating the leading overlay on
  the current 4-sleeve blend.

---

## 7. Concrete Next Experiments (hypotheses to test, prioritized)

All on the current 60/15/15/10 blend, monthly signal at month-end, t+1 MOO execution, 10 bps/
side, with crisis-row MaxDD and a paired block bootstrap on dSharpe reported for every cell.

Experiment 1 (HIGH; finish the leading overlay). Volatility-target overlay on the CURRENT blend.
- Signal: scale risky exposure by min(1, target / trailing-252d realized vol), de-risk-only,
  residual to SHV; target = expanding-window 60/40 realized vol (parameter-free), compared
  against fixed VT-10 and VT-12.
- Why now: this is the repo's own pending next handoff, but it was validated on the OLD 60/20/20
  blend; it must be re-confirmed on the current sleeves before any adoption.
- Measure: blend Sharpe delta vs production with bootstrap CI; per-crisis MaxDD (expect GFC/Euro/
  2022 improvement, COVID unchanged); turnover/cost delta; sensitivity across target anchors.
- Decision rule: adopt only if the Sharpe delta clears bootstrap noise OR the slow-crisis DD gain
  is material with neutral Sharpe; reject if it merely re-prices COVID risk it cannot catch.

Experiment 2 (HIGH; fill the structural gap). Orthogonal non-price macro/credit gate at the blend.
- Signal: Sahm rule and/or HY OAS level > ~600 bps and/or unemployment vs 12-month average;
  vintage/unrevised data, evaluated at month-end T-1, executed t+1. De-risk a FRACTION (test 25%/
  50%/100%) of the blend to SHV when the gate fires; require risk-on = CPM-risk-on AND gate-calm.
- Measure: overlap between gate-fire months and CPM's own de-risk months (want LOW overlap =
  orthogonality); crisis-row MaxDD with attention to recessionary grinds (GFC, 2008-09) vs fast
  gaps (COVID); blend Sharpe delta with CI; curve/threshold sensitivity (treat a single working
  threshold as a red flag).
- Honest prior: expect a modest, recession-specific gain that may sit inside bootstrap noise (the
  BULL-sleeve precedent), with no COVID help. Value is structural orthogonality, not headline lift.

Experiment 3 (MEDIUM; close the static-weight gap). Blend-level risk budgeting.
- Signal: rolling covariance of the four sleeve return series; compare HRP (single-linkage,
  recursive bisection) and simple inverse-vol against static 60/15/15/10, with Ledoit-Wolf
  shrinkage; weights from data through T, executed t+1.
- Measure: blend Sharpe, MaxDD, per-sleeve risk contribution (is the single-stock vol dominating?),
  turnover (HRP vs static), and walk-forward stability across lookbacks.
- Honest prior: likely a risk-budget/Sharpe-stability improvement, NOT crash-tail relief, since
  the binding blend tail was a sharp 2010 event that sleeve weighting did not move; re-confirm
  that binding-DD fact on the current blend first.

Experiment 4 (LOWER; style diversification, not crisis hedge). Global/cross-asset CAPE value sleeve.
- Signal: cheapest-quartile country/asset CAPE or multi-metric value (vintage earnings, 1-3 month
  restatement lag), annual valuation with a monthly trend overlay; carve ~5-10% from a momentum
  sleeve.
- Measure: FULL-sample AND crisis-subsample correlation to CPM; blend Sharpe over value-ON
  (2003-2007, 2021+) and value-OFF (2013-2020) sub-periods (cross-regime decomposition mandatory);
  crisis-row MaxDD (verify it does NOT claim crisis protection it cannot provide).
- Decision rule: justify only if it is regime-robust and genuinely lowers crisis-sub-sample
  correlation; otherwise it is a return-source bet, not a defense.

Explicitly out of scope (already settled in the repo): correlation/PC1 absorption gate
(rejected overfit), multi-asset canary upgrade (rejected), carry/value tilt on the core (rejected).

---

## 8. Bottom Line

- CPM is a tuned, four-sleeve momentum-and-trend ensemble whose defense is 100% price-conditioned
  and 0% macro-aware. That is its defining structural signature and its one clean gap.
- It already handles the 2022 rates shock and slow grinds well; it is structurally exposed to fast
  V-reversals (COVID, tariff) -- an exposure the repo confirms NO monthly overlay has overcome.
- The best-evidenced single improvement is a volatility-target overlay (slow-stress DD relief,
  pending significance). The only true orthogonal diversifier is a non-price macro/credit gate
  (structural gap-filler, expected modest and recession-specific). Blend-level risk budgeting
  closes the static-weight gap but is unlikely to move the crash tail.
- No replacement clears the bar; the one rigorous head-to-head (AAA) is a statistical tie that is
  in-sample-flattered toward CPM. KEEP the incumbent; diversify and harden rather than replace.
