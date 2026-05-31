# Canary variant test -- STRICTER HYG-AND-TIP extension

Question: should the production canary (HYG-OR-TIP, any positive 13612U) be
replaced by a stricter HYG-AND-TIP canary (de-risk if EITHER credit OR real-rate
breadth fails)? Does the added strictness cut drawdown (esp. 2022 / rising-rate
stress) or just sacrifice return via whipsaw? Focus: BULL sleeve.

- Script: `research/canary_and_variant_test.py` (reuses `research/canary_variant_test.py` helpers).
- Run: `.venv/bin/python research/canary_and_variant_test.py`
- Data: `research/canary_and_variant_findings.json`
- Framework: mooex (faithful; reproduces the production anchor exactly).
- Variants: only the canary toggled; trend gate, vol gate (BULL rv_60d), ranker,
  weighting, safe pool all held at production.

## Anchor confirmation (gate-first)

Production HYG-OR-TIP, clean window 2008-05-30..2026-05-22:

| metric | computed | expected | match |
|--------|----------|----------|-------|
| CPM Sharpe   | 1.1910 | 1.1910 | yes |
| BULL Sharpe  | 1.0813 | 1.0813 | yes |
| 60/40 Sharpe | 1.2485 | 1.2485 | yes |

Anchor OK. All variant numbers below are on the same faithful framework.

## Variant definitions

- tip: TIP 13612U > 0
- hygortip: HYG OR TIP positive (PRODUCTION)
- hygandtip: HYG AND TIP both positive (NEW, stricter; de-risk if either fails)
- none: no canary gate (always risk-on)

## 1. CPM sleeve, clean window

| variant | Sharpe | Calmar | MaxDD % | CAGR % |
|---------|--------|--------|---------|--------|
| tip        | 1.1546 | 0.960 | -12.67 | 12.16 |
| hygortip   | 1.1910 | 1.062 | -12.67 | 13.44 |
| hygandtip  | 1.1742 | 0.965 | -12.67 | 12.22 |
| none       | 1.1278 | 0.874 | -15.01 | 13.11 |

HYG-AND-TIP sits between TIP-only and HYG-OR-TIP on Sharpe, but matches TIP-only
on Calmar (0.965 vs 0.960) and loses to production OR on both Sharpe and Calmar.
MaxDD identical to OR/TIP (-12.67): the stricter gate does NOT reduce CPM drawdown.

## 2. BULL sleeve, clean window (focus)

| variant | Sharpe | Calmar | MaxDD % | CAGR % |
|---------|--------|--------|---------|--------|
| tip        | 1.1005 | 0.819 | -13.35 | 10.93 |
| hygortip   | 1.0813 | 0.857 | -13.35 | 11.44 |
| hygandtip  | 1.1005 | 0.819 | -13.35 | 10.93 |
| none       | 1.0096 | 0.655 | -16.68 | 10.92 |

Key result: for BULL, HYG-AND-TIP is OPERATIONALLY IDENTICAL to TIP-only
(Sharpe 1.1005, Calmar 0.819, MaxDD -13.35, CAGR 10.93 -- byte-for-byte).
Bootstrap diff bull_AND_vs_TIP obs = 0.0000, CI = [0.0000, 0.0000]. The reason:
BULL's SPY trend + rv_60d vol gate already capture the months where HYG is
positive but TIP is negative, so demanding BOTH adds nothing beyond TIP-only.
MaxDD identical across tip/or/and (-13.35) -- the stricter canary does NOT cut
BULL drawdown. HYG-AND-TIP/TIP-only give up CAGR (10.93 vs 11.44) and Calmar
(0.819 vs 0.857) relative to production OR.

## 3. 60/40 blend

Joint (both sleeves same canary), clean window:

| variant | Sharpe | Calmar | MaxDD % | CAGR % |
|---------|--------|--------|---------|--------|
| tip        | 1.2344 | 1.101 | -10.68 | 11.76 |
| hygortip   | 1.2485 | 1.193 | -10.68 | 12.74 |
| hygandtip  | 1.2392 | 1.103 | -10.68 | 11.79 |
| none       | 1.1791 | 0.820 | -15.05 | 12.35 |

Same pattern: AND mirrors TIP, both below production OR on Sharpe/Calmar/CAGR;
MaxDD unchanged.

Best asymmetric combo across sleeves (clean):
- by Sharpe: cpm_hygortip x bull_tip -> Sharpe 1.2777, Calmar 1.175, MaxDD -10.68
- by Calmar: cpm_hygortip x bull_hygortip (PRODUCTION) -> Sharpe 1.2485, Calmar 1.193
HYG-AND-TIP does not appear in either best-asymmetric leg.

## 4. HYG-AND-TIP extra defensive months and whipsaw vs protection

Canary-forced defensive months (trend/vol gates common across variants),
clean window n=216:

| variant | defensive months |
|---------|------------------|
| tip        | 57 |
| hygortip   | 29 |
| hygandtip  | 70 |

- HYG-AND-TIP de-risks in 41 EXTRA months vs HYG-OR-TIP (exactly-one-positive months).
- HYG-AND-TIP de-risks in 13 EXTRA months vs TIP-only (TIP positive but HYG fails).

Were those extra defensive months protection or whipsaw? SPY forward
(next ~21 trading days) realized return in the AND-extra months, clean window:

| comparison | n | mean % | median % | pct negative |
|------------|---|--------|----------|--------------|
| AND sits out vs OR risk-on  | 41 | +1.39 | +1.55 | 34.1 |
| AND sits out vs TIP risk-on | 13 | +2.72 | +1.55 | 23.1 |

Both sets show POSITIVE mean/median forward returns and only ~24-34% negative
months. The added strictness mostly sits out of UP months -> WHIPSAW (foregone
return), not protection. This is why AND loses CAGR/Calmar with unchanged MaxDD.

Stagflation / rising-rate stress detail:

| episode | sleeve | OR ret/maxdd % | AND ret/maxdd % | TIP ret/maxdd % |
|---------|--------|----------------|-----------------|-----------------|
| 2022_full      | CPM   | -0.50 / -6.33 | -2.01 / -6.33 | -0.50 / -6.33 |
| 2022_full      | BULL  | +0.94 / -0.30 | +0.94 / -0.30 | +0.94 / -0.30 |
| 2022H1_worst   | CPM   | -1.61 / -6.33 | -3.11 / -6.33 | -1.61 / -6.33 |
| 2022-2023 rate | CPM   | -6.39 / -8.51 | +2.27 / -6.33 | +3.85 / -6.33 |
| 2022-2023 rate | BULL  | -4.34 / -9.97 | +6.19 / -2.60 | +6.19 / -2.60 |
| 2022-2023 rate | blend | -5.49 / -8.63 | +3.85 / -3.86 | +4.84 / -3.86 |

- In 2022 itself, AND does not help (BULL identical; CPM AND slightly worse -- whipsaw).
- In the EXTENDED 2022-2023 rate-stress window, AND (and TIP-only) DID protect:
  HYG-OR-TIP stayed risk-on because credit (HYG) held up while real-rate (TIP)
  rolled over, walking into a 2023 credit-trap drawdown (BULL OR -9.97, CPM OR
  -8.51) that AND/TIP avoided (BULL AND -2.60, CPM AND -6.33). This is the one
  regime where strictness pays.
- BUT this 2023 tail does NOT drive the full-window MaxDD (identical -13.35 BULL /
  -12.67 CPM across all variants), so it does not improve headline Calmar.

## 5. Bootstrap noise (clean window, 21-day block, 2000 reps)

Sharpe difference (variant A - B), 95% CI:

| comparison | obs diff | 95% CI | within noise |
|------------|----------|--------|--------------|
| cpm  AND vs OR  | -0.0168 | [-0.199, +0.184] | yes |
| cpm  AND vs TIP | +0.0195 | [-0.072, +0.124] | yes |
| bull AND vs OR  | +0.0193 | [-0.152, +0.201] | yes |
| bull AND vs TIP | +0.0000 | [ 0.000,  0.000] | yes (identical series) |
| blend AND vs OR | -0.0093 | [-0.187, +0.188] | yes |
| blend AND vs TIP| +0.0048 | [-0.057, +0.073] | yes |

Every AND-vs-OR and AND-vs-TIP difference straddles zero -> within bootstrap
noise. No variant is statistically distinguishable on full-window Sharpe.

## Extended-window context (synthetic-TIP de-bias; less decision-relevant)

ext window 1999..2026, CPI-aware synthetic TIP (84% 13612U sign-agreement with
real TIP over 300-month overlap):

| sleeve | variant | Sharpe | Calmar | MaxDD % |
|--------|---------|--------|--------|---------|
| CPM  | tip       | 1.182 | 0.926 | -13.38 |
| CPM  | hygortip  | 1.202 | 0.851 | -15.93 |
| CPM  | hygandtip | 1.241 | 0.958 | -13.38 |
| BULL | tip       | 0.932 | 0.681 | -13.35 |
| BULL | hygortip  | 0.884 | 0.626 | -14.59 |
| BULL | hygandtip | 0.971 | 0.707 | -13.35 |

In the longer ext window HYG-AND-TIP has the best Sharpe AND Calmar for both
sleeves, and a lower MaxDD than OR -- because the early-2000s and 2023 rate-stress
episodes (where credit and real-rate diverge) reward strictness. This favors AND,
but rests on synthetic TIP pre-2001 and is within noise; the clean-window
real-data verdict governs.

## Net verdict per sleeve (HYG-AND-TIP)

BULL (primary):
- HYG-AND-TIP collapses to TIP-only exactly in the clean window (Sharpe 1.1005,
  Calmar 0.819, MaxDD -13.35) -- the vol+trend gate makes the extra HYG-AND
  requirement redundant.
- It does NOT beat production HYG-OR-TIP: lower CAGR (10.93 vs 11.44) and Calmar
  (0.819 vs 0.857), IDENTICAL MaxDD. No drawdown benefit at headline level.
- The only edge is in the 2022-2023 rising-rate tail (avoids the 2023 credit-trap
  DD that OR suffered), but this does not move full-window MaxDD/Calmar.
- Difference is WITHIN bootstrap noise (obs 0.0000 / +0.0193, CIs straddle 0).
- Recommendation: do not adopt HYG-AND-TIP for BULL; keep production HYG-OR-TIP.

CPM (completeness):
- HYG-AND-TIP Sharpe 1.1742 (< OR 1.1910), Calmar 0.965 (~ TIP 0.960, < OR 1.062),
  MaxDD identical (-12.67). Slightly better than TIP-only on Sharpe, worse than OR
  on everything; the 41 extra defensive months are mostly whipsaw (SPY fwd +1.39%).
- Within bootstrap noise vs both OR and TIP.
- Recommendation: do not adopt HYG-AND-TIP for CPM; keep production HYG-OR-TIP.

Bottom line: HYG-AND-TIP's stricter de-risking does NOT cut drawdown at the
headline (full-clean-window MaxDD identical across all canary variants); it
mainly sacrifices return via whipsaw (sitting out predominantly up months). Its
one genuine protective regime is the 2022-2023 rising-rate / credit-real-rate
divergence tail, but that gain is not large enough to beat production HYG-OR-TIP
on full-window Sharpe/Calmar and the difference is within bootstrap noise.

## Caveats

- Decision rests on clean window (2008+, 100% real TIP). Ext window uses synthetic
  TIP pre-2001 (84% sign agreement) and is supportive-only.
- 1970s stagflation is infeasible (panel starts 1995; HYG/risky-ETF/TIP proxies do
  not extend). The 2022 and 2022-2023 episodes are the in-sample rate-stress tests.
- All AND-vs-OR and AND-vs-TIP Sharpe differences are within block-bootstrap noise;
  treat magnitude rankings as directional, not significant.
- MaxDD is identical across canary variants because the worst drawdowns are driven
  by within-month moves / trend+vol gating, not by the monthly canary sign.
