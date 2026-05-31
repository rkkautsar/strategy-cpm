# Canary Variant Test: HYG-OR-TIP vs TIP-only (CPM and BULL)

Question: Production runs a dual-canary HYG-OR-TIP (any-positive 13612U) on BOTH
sleeves. Should it be dropped to a TIP-only canary? Decide separately for CPM
and BULL, at sleeve and 60/40 blend level.

Method: toggle ONLY the canary input; hold everything else at production. Faithful
execution = mooex framework (`research/exec_lag_moo_validation_2026_05_30.py`),
the same path that produces the production anchor. Three canary modes per sleeve:
TIP-only (TIP 13612U > 0), HYG-OR-TIP (any-positive, production), none (always
risk-on; sleeve still keeps its other gates).

Reproduce: `.venv/bin/python research/canary_variant_test.py`
Artifacts: this file + `research/canary_variant_test_findings.json`.

Windows: clean = 2008-05-30..2026-05-22 (fully REAL TIP[VIPSX 2000-06+] and REAL
HYG[VWEHX 1980+]); ext = 1999-03-10..2026-05-22.

## Anchor confirmation (gate)

Reproduced exactly before any variant was reported:

| Series | Production anchor Sharpe | Reproduced |
|---|---|---|
| CPM clean | 1.1910 | 1.1910 |
| BULL clean | 1.0813 | 1.0813 |
| 60/40 blend clean | 1.2485 | 1.2485 |

Anchor gate PASSED (all within 5e-4). All variant numbers below come from the
same framework.

## TIP proxy reality and the synthetic TIP

- Real TIP (VIPSX stitch) enters the panel at 2000-06; the 13612U signal is
  available from 2001-06. The clean window is therefore 100% real TIP and real
  HYG -- no proxy is involved in the decision-relevant numbers.
- In the ext window before 2001-06, production has NO TIP signal, so a TIP-only
  canary is forced defensive (an artifact, not an economic signal). To de-bias
  the ext window we built a CPI-aware synthetic TIP.

Synthetic TIP construction (canary-only; TIP is not held by either sleeve):
monthly synthetic TIPS total return = IEF nominal intermediate-Treasury total
return + realized monthly CPI inflation (FRED CPIAUCSL), cumulated to a price
index. This restores the inflation-accrual component that a nominal-bond proxy
(plain IEF) is blind to. The series is spliced: synthetic before real-TIP
availability, REAL TIP after (rescaled to match at the splice date), so the
post-2000 era stays on real data.

Validation: over the 300-month real/synthetic overlap, the synthetic and real
TIP 13612U signs agree 84% of the time. Synthetic signal starts ~1994-11.

Pre-1997 proxy labeling: any pre-2000-06 TIP number in the "ext_synTIP" columns
uses the CPI-aware synthetic; pre-2000-06 numbers in the "ext_prodTIP" columns
use the production stitch (no TIP signal => forced defensive). Post-2000 is real
TIP in both.

## 1970s stagflation: infeasible, fallback applied

A 1970s stagflation backtest (1973-74, 1977-82) is structurally infeasible with
the available data: the panel starts 1995-01, the risky ETF universe does not
exist pre-1995, and the HYG credit proxy (VWEHX) starts only in 1980. Even the
canary signal cannot be reconstructed -- the nominal-bond series (IEF stitch)
starts 1993-10, so a CPI-aware synthetic TIP cannot be built before ~1994, and
there is no credit (HYG) series for the 1970s at all.

FALLBACK (as instructed): the verdict rests on the real-TIP era. The decision-
relevant stagflation episode is 2022 (and 2021H2), both inside the clean window
on fully real data. No IEF-proxy 1970s result was computed, and none drives the
decision.

## 1. CPM sleeve

| CPM canary | clean Sharpe | clean Calmar | clean MaxDD | ext Sharpe (prodTIP) | ext Sharpe (synTIP) |
|---|---|---|---|---|---|
| TIP-only | 1.1546 | 0.960 | -12.67% | 1.1575 | 1.1820 |
| HYG-OR-TIP (prod) | 1.1910 | 1.062 | -12.67% | 1.2109 | 1.2018 |
| none | 1.1278 | 0.874 | -15.01% | 1.1693 | n/a |

Read: on CPM, HYG-OR-TIP beats TIP-only on every metric in the clean window
(Sharpe +0.036, Calmar +0.10, identical MaxDD). The synthetic-TIP ext column
narrows the gap (1.2018 vs 1.1820, +0.020) and shows that the production ext
TIP-only number (1.1575) was understated by the pre-2001 forced-defensive
artifact -- the real TIP-only ext Sharpe is closer to 1.182. Dropping the canary
entirely (none) clearly hurts CPM (MaxDD -15.01% vs -12.67%).

## 2. BULL sleeve

| BULL canary | clean Sharpe | clean Calmar | clean MaxDD | ext Sharpe (prodTIP) | ext Sharpe (synTIP) |
|---|---|---|---|---|---|
| TIP-only | 1.1005 | 0.819 | -13.35% | 1.0207 | 0.9319 |
| HYG-OR-TIP (prod) | 1.0813 | 0.857 | -13.35% | 0.9196 | 0.8841 |
| none | 1.0096 | 0.655 | -16.68% | 0.8380 | n/a |

Read: on BULL, TIP-only has the HIGHER Sharpe (1.1005 vs 1.0813 clean; 1.02 vs
0.92 ext-real; 0.93 vs 0.88 ext-syn) at IDENTICAL MaxDD (-13.35%). HYG-OR-TIP is
marginally better on Calmar only (0.857 vs 0.819). Dropping the canary entirely
(none) is clearly worse (MaxDD -16.68%). So for BULL the HYG half adds nothing
to Sharpe or drawdown -- a TIP-only canary is equal-or-better and just as
protective.

## 3. 60/40 blend (decision view)

Joint variation (both sleeves same canary), real TIP:

| Blend canary (both) | clean Sharpe | clean Calmar | clean MaxDD | ext Sharpe |
|---|---|---|---|---|
| TIP-only | 1.2344 | 1.101 | -10.68% | 1.2179 |
| HYG-OR-TIP (prod) | 1.2485 | 1.193 | -10.68% | 1.2183 |
| none | 1.1791 | 0.820 | -15.05% | 1.1587 |

Per-sleeve variation (other sleeve held at production HYG-OR-TIP), clean:

| Config | clean Sharpe | clean Calmar | clean MaxDD |
|---|---|---|---|
| CPM TIP-only + BULL prod | 1.2457 | 1.122 | -10.68% |
| CPM prod + BULL prod (= production) | 1.2485 | 1.193 | -10.68% |
| CPM prod + BULL TIP-only | 1.2777 | 1.175 | -10.68% |
| CPM none + BULL prod | 1.2158 | 1.176 | -10.68% |
| CPM prod + BULL none | 1.2270 | 1.174 | -10.68% |

Read: the production joint HYG-OR-TIP (1.2485) slightly beats joint TIP-only
(1.2344) at the blend level. But the single best config is asymmetric -- keep
HYG-OR-TIP on CPM and drop BULL to TIP-only: Sharpe 1.2777 (+0.029 vs
production), Calmar 1.175 (-0.018, flat), same MaxDD. A full drop to TIP-only on
both costs ~0.014 blend Sharpe and ~0.09 Calmar.

## 4. State analysis: TIP-negative / HYG-positive override months

Override = a month where TIP 13612U <= 0 AND HYG 13612U > 0, i.e. HYG-OR-TIP
stays risk-on but TIP-only would de-risk. The canary signal is identical for both
sleeves, so the override calendar is shared.

Clean window (real TIP): 28 override months out of 216 (~13%). Realized forward
1-month behavior in those months:

- SPY (market proxy) forward mean = +0.775%, vol 3.75%, only 39.3% negative.
- CPM sleeve forward mean = +0.632%; BULL sleeve forward mean = +0.112%.

Ext window with synthetic TIP: 36 overrides; SPY forward mean +0.469%, 41.7%
negative; CPM sleeve forward +0.83%.

Override months cluster in 2013 (taper tantrum), 2014, 2017, 2018, 2023, 2024 --
rising-real-rate but risk-on equity regimes where real bonds (TIP) fall while
credit (HYG) and equities rise. They are NOT concentrated in equity drawdowns:
on average the market rose in override months and fewer than half were negative.
Staying risk-on there HELPED on average (positive forward returns), which is why
HYG-OR-TIP is net positive for CPM and roughly neutral for BULL.

## Stagflation episodes (real data)

| Episode | CPM TIP | CPM HYG-OR-TIP | BULL TIP | BULL HYG-OR-TIP | Blend TIP | Blend HYG-OR-TIP | overrides |
|---|---|---|---|---|---|---|---|
| 2022 full | -0.50% / -6.33% | -0.50% / -6.33% | +0.94% / -0.30% | +0.94% / -0.30% | +0.12% / -3.86% | +0.12% / -3.86% | 0 |
| 2022 H1 | -1.61% / -6.33% | -1.61% / -6.33% | -0.19% / -0.30% | -0.19% / -0.30% | -1.00% / -3.86% | -1.00% / -3.86% | 0 |
| 2021 H2 | +8.33% / -4.70% | +8.33% / -4.70% | +7.98% / -5.11% | +7.98% / -5.11% | +8.22% / -3.97% | +8.22% / -3.97% | 0 |

(format: total return / MaxDD over the episode.)

Key stagflation finding: 2022 had ZERO override months. HYG 13612U was negative
every month of 2022 (Jan -0.011, deepening to -0.108 in June) and actually went
negative ahead of TIP. Because credit collapses alongside real bonds in
stagflation, HYG-OR-TIP and TIP-only produce IDENTICAL behavior and identical
returns through 2022 (CPM -0.50%, BULL +0.94%, blend +0.12%) and through 2021H2.
The OR-HYG extension does NOT keep the strategy risk-on into the stagflation
drawdown -- it is harmless there. Its effect lives entirely in the benign
rising-rate, risk-on regimes of section 4, not in stagflation.

Implication: TIP-only is NOT a meaningfully safer stagflation hedge than
HYG-OR-TIP, because both de-risk together when credit fails. Stagflation does not
change the keep/drop verdict; the verdict rests on benign-regime behavior.

## 5. Net verdict per sleeve

Bootstrap (block=21d, 2000 reps) on the clean daily Sharpe difference
(HYG-OR-TIP minus TIP-only):

| Series | obs diff | 95% CI | within noise? |
|---|---|---|---|
| CPM | +0.0363 | [-0.136, +0.192] | YES |
| BULL | -0.0193 | [-0.201, +0.152] | YES |
| 60/40 blend | +0.0141 | [-0.168, +0.183] | YES |

All three differences are WITHIN bootstrap noise. The point estimates are
directionally informative but not statistically distinguishable.

CPM: HYG-OR-TIP is net POSITIVE vs TIP-only (clean Sharpe +0.036, Calmar +0.10,
same MaxDD; ext positive too). Effect is small and within noise, but the sign is
consistent across clean and ext and it never worsens drawdown. Verdict: KEEP
HYG-OR-TIP on CPM (weak positive, costless on risk).

BULL: HYG-OR-TIP is net NEUTRAL-to-NEGATIVE vs TIP-only -- TIP-only has higher
Sharpe at identical MaxDD (only Calmar marginally favors HYG-OR-TIP), within
noise. Verdict: TIP-only is the better/equal canary for BULL; the HYG half adds
no Sharpe or drawdown benefit and is the cleaner drop.

C x V redundancy cross-check (BULL): all BULL variants keep the SPY trend filter
and the rv_60d vol gate; only the canary is toggled.

- none (canary off): Sharpe 1.0096, MaxDD -16.68% -- materially worse, so the
  canary is NOT fully redundant with the vol gate; some canary is needed for
  drawdown control.
- TIP-only and HYG-OR-TIP both achieve MaxDD -13.35%; TIP-only has the higher
  Sharpe.

So the rv_60d vol gate plus a TIP-only canary already capture the protection;
the HYG half specifically is redundant. This corroborates the previously found
small/negative C x V interaction (Calmar delta -0.018).

## Bottom line

- CPM: keep HYG-OR-TIP (weak net positive, within noise, no drawdown cost).
- BULL: drop to TIP-only (equal-or-better Sharpe, identical MaxDD; HYG half is
  redundant given the rv_60d vol gate). Do not drop the canary entirely.
- Blend: the production joint HYG-OR-TIP is fine, but the asymmetric config
  (CPM HYG-OR-TIP + BULL TIP-only) is the single best blend (Sharpe 1.2777 vs
  1.2485, flat Calmar, same MaxDD). A full drop to TIP-only on both is within
  noise on Sharpe but loses ~0.09 blend Calmar.
- Stagflation: TIP-only and HYG-OR-TIP are equivalent in 2022 (credit fails with
  real bonds; zero override months), so stagflation safety does not motivate the
  drop. The OR-HYG extension is harmless in stagflation and only acts in benign
  rising-rate regimes.

## Caveats

- All sleeve/blend Sharpe differences between HYG-OR-TIP and TIP-only are within
  bootstrap noise (section 5). Treat the recommendation as a low-conviction,
  costless-leaning preference, not a strong signal.
- Pre-2000-06 TIP numbers: ext_prodTIP uses the production stitch (TIP-only
  forced defensive pre-2001 = downward-biased); ext_synTIP uses the CPI-aware
  synthetic (84% sign agreement with real TIP). Post-2000 is real TIP in both.
- The 1970s stagflation test is infeasible with available data and was not run;
  the verdict deliberately rests on the real-TIP era (clean window, 2022).
- Single-cut backtest on one asset universe; no multiple-testing correction
  beyond the bootstrap shown.

Handoff: implementation of any canary change (production config edit) is out of
analyst scope -> route to fixer if the team chooses to act.
