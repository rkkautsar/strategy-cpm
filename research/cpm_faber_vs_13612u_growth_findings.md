# Why Faber beats 13612U on the CPM universe: is it the high-vol growth names (QQQ/SPHQ)?

Analyst findings. Read-only reproduction; no production files edited; no commit.

## Question

Why does the slower Faber 10-month-SMA trend metric beat the faster 13612U on the
CPM universe (clean Sharpe +0.012 within-noise; ext +0.14 Calmar / ~+3pp shallower
MaxDD), while 13612U beats Faber on the HAA universe?

## Hypothesis (tested)

The high-vol growth/quality names QQQ and SPHQ drive Faber's preference: a slow
10-month SMA rides high-momentum/high-vol names through short-term reversals, while
the fast 13612U whipsaws in and out of them (deeper crisis drawdowns). On
flatter/lower-vol assets the speed penalty disappears. Prediction: replacing QQQ/SPHQ
with SPY should SHRINK or FLIP Faber's advantage.

**Verdict: hypothesis REJECTED.** De-tilting QQQ/SPHQ to SPY does not collapse
Faber's edge -- it preserves and even amplifies it. The discriminator between the CPM
and HAA universes is the broader universe composition, not the growth tilt, and the
proposed "slow = less whipsaw on growth names" mechanism is not present in the data.

## Method

Flip ONLY the coupled trend metric (Faber <-> 13612U; the flip moves both the rank
numerator and the absolute trend screen together). Full CPM stack held fixed
otherwise: vol-adjusted rank denominator (rv_252d), inverse-vol weighting (cov tail
252), HYG-or-TIP any-positive canary, top-4 candidates, partial-safe breadth scaling
(risky_fraction = n_pass/4, remainder to safe), best-of-safe {SHV, IEF} by 13612U.
Both metrics are vol-adjusted in the rank denominator. Engine = cpm_live; execution =
mooex T+1 (real opens, 10 bps/side), identical to `cpm_haa_coupled_factorial.py`.

- Clean window 2008-05-30..2026-05-22 (decision lens). Ext window 1999-03-10..2026-05-22.
- Script: `research/cpm_faber_vs_13612u_growth.py`; raw output: `research/cpm_faber_vs_13612u_growth.json`.

### Gates (all pass)

- `cpm_wf(CPM_as_is, faber)` matches production `compute_target_weights` weight-by-weight (0 mismatches across all monthly signal dates).
- CPM full Faber clean anchor: Sharpe 1.16576 / MaxDD -12.97% / Calmar 1.01369 (target 1.1658 / -12.97 / 1.0137).
- CPM full 13612U clean anchor: Sharpe 1.15399 / MaxDD -13.32% / Calmar 0.98756 (target 1.1540 / -13.32 / 0.9876).

## 1) Universe-variant head-to-head: Faber minus 13612U

The both-to-SPY variant deduplicates to a 7-asset universe (top-4 fixed); the single
swaps keep 8 assets. Delta = Faber minus 13612U (positive = Faber better; for MaxDD
positive = Faber shallower).

| Universe variant | CLEAN dSharpe | CLEAN dCalmar | CLEAN dMaxDD | EXT dSharpe | EXT dCalmar | EXT dMaxDD |
|---|---|---|---|---|---|---|
| CPM_as_is (QQQ+SPHQ) | +0.0118 | +0.0261 | +0.34pp | +0.0196 | +0.1401 | +2.99pp |
| CPM both -> SPY (7 assets) | +0.0475 | +0.1312 | +1.51pp | +0.0394 | +0.1840 | +3.21pp |
| CPM QQQ -> SPY (keep SPHQ) | -0.0019 | -0.0081 | -0.08pp | +0.0093 | +0.1461 | +3.39pp |
| CPM SPHQ -> SPY (keep QQQ) | +0.0320 | +0.0158 | -0.02pp | +0.0237 | +0.1970 | +3.16pp |
| HAA universe | +0.0631 | -0.0602 | -2.72pp | +0.0296 | -0.0596 | -1.90pp |

Reading the decisive test -- does Faber's edge shrink or flip as QQQ/SPHQ are replaced by SPY?

- **It does NOT collapse.** Replacing BOTH growth names with SPY GROWS Faber's edge
  (clean Sharpe +0.012 -> +0.048; ext Calmar +0.140 -> +0.184; MaxDD +3.0pp -> +3.2pp).
- Replacing SPHQ alone (keep QQQ) also GROWS the clean Sharpe edge (+0.012 -> +0.032)
  and the ext Calmar edge (+0.140 -> +0.197).
- Only replacing QQQ alone (keep SPHQ) marginally erases the clean Sharpe edge
  (+0.012 -> -0.002, well within noise), but the ext drawdown/Calmar edge persists
  almost unchanged (Calmar +0.146, MaxDD +3.4pp shallower).
- The edge only FLIPS against Faber when the universe is swapped wholesale to the HAA
  set: ext Calmar -0.060, MaxDD 1.9pp DEEPER. (Note: even there Faber's ext/clean
  Sharpe stays slightly positive; what flips is the drawdown/Calmar dimension.)

So Faber's core advantage -- shallower ext drawdowns and higher ext Calmar -- is a
property of the CPM diversifier frame that SURVIVES removing the high-vol growth names.
The growth tilt is not what drives it.

## 2) Mechanism check: whipsaw / turnover on QQQ/SPHQ vs SPY

Over ~290 monthly signal dates (CPM_as_is universe), hold-state turnover (entries+exits)
and hold-disagreements between metrics:

| Name | months present | held Faber | held 13612U | hold disagreements | turnover Faber | turnover 13612U |
|---|---|---|---|---|---|---|
| QQQ | 291 | 168 | 177 | 27 | 58 | 56 |
| SPHQ | 290 | 158 | 164 | 18 | 61 | 55 |

The "slow metric = less whipsaw on high-vol trending names" mechanism is NOT present:

- Faber's turnover on the growth names is equal-to-slightly-HIGHER than 13612U's
  (QQQ 58 vs 56; SPHQ 61 vs 55), the opposite of the predicted whipsaw reduction.
- Hold-state disagreements are small (18-27 of ~290 months); the two metrics mostly
  agree on QQQ/SPHQ. 13612U actually holds the growth names slightly MORE often than
  Faber (QQQ 177 vs 168; SPHQ 164 vs 158).
- Replacing a growth name with SPY does not materially change either metric's turnover
  (SPY turnover 57-63, same ballpark), so the metrics behave the same on the de-tilted
  name.

### Crisis-window drawdowns (Faber vs 13612U)

| Episode | CPM Faber | CPM 13612U | CPM both->SPY Faber | CPM both->SPY 13612U |
|---|---|---|---|---|
| Dot-com 2000-2002 | -6.03% | -5.87% | -6.03% | -5.87% |
| GFC 2007-2009 | -11.88% | -11.76% | -11.63% | -13.49% |
| COVID 2020 | -10.50% | -10.50% | -9.17% | -9.29% |
| 2022 | -8.32% | -7.96% | -5.69% | -6.68% |

On the QQQ-containing CPM_as_is universe, Faber and 13612U have essentially identical
named-crisis drawdowns (Faber is marginally DEEPER in dot-com, GFC, and 2022). The
"slow Faber cuts/holds high-vol growth at better times in crises" story is not
supported within these episodes. Faber's drawdown advantage shows up only in the
de-tilted (both->SPY) frame during GFC and 2022 -- i.e. it strengthens when the growth
names are removed, again contradicting the hypothesis.

Note: the binding ext MaxDD gap (13612U -18.72% vs Faber -15.73% on CPM_as_is) is
identical for CPM_as_is and CPM QQQ->SPY (both -18.72% for 13612U), confirming 13612U's
worst full-sample drawdown is NOT located in QQQ. It is a universe-wide effect, not a
growth-name effect.

## 3) Per-asset realized vol (grounding the vol-tilt premise)

Annualized realized vol over the clean window: full-sample daily vol and the
time-average of the rolling rv_252d the strategy actually ranks on. Sorted high to low.

CPM universe (mean clean_vol = 21.5%, mean rv_252 = 19.7%):

| Ticker | clean_vol | mean rv_252 |
|---|---|---|
| VNQ | 29.6% | 24.4% |
| EEM | 27.5% | 24.5% |
| QQQ | 22.3% | 21.2% |
| EFA | 21.8% | 19.8% |
| DBC | 19.2% | 18.3% |
| SPHQ | 18.7% | 17.4% |
| GLD | 17.9% | 16.9% |
| TLT | 15.4% | 15.0% |

HAA universe (mean clean_vol = 20.4%, mean rv_252 = 18.6%):

| Ticker | clean_vol | mean rv_252 |
|---|---|---|
| VNQ | 29.6% | 24.4% |
| VWO | 26.0% | 23.5% |
| IWM | 24.9% | 23.3% |
| VEA | 21.5% | 19.6% |
| SPY | 19.8% | 18.1% |
| DBC | 19.2% | 18.3% |
| TLT | 15.4% | 15.0% |
| IEF | 6.9% | 6.8% |

Shared names: VNQ 29.6%, DBC 19.2%, TLT 15.4% (identical in both).

Observations:

- The CPM universe is only MARGINALLY higher-vol on average (21.5% vs 20.4% clean_vol;
  19.7% vs 18.6% rv_252). It is NOT a large structural gap.
- The real composition difference is the tails, not the growth equities: HAA is
  anchored by IEF (6.9% vol intermediate Treasury) sitting IN the risky universe, and
  HAA drops GLD (17.9%); CPM keeps GLD and has no in-universe bond ladder below TLT.
- SPHQ (18.7%) is actually a LOWER-vol name than EFA/SPY, so labelling SPHQ as a
  "high-vol growth" driver is mis-specified; QQQ (22.3%) is mid-pack, below VNQ and EEM.
  The genuinely high-vol CPM names are VNQ and EEM, which are NOT the swapped names.

## Verdict

1. **Is the Faber-over-13612U preference driven by the high-vol growth names QQQ/SPHQ?
   No.** De-tilting both to SPY preserves and amplifies Faber's edge (clean Sharpe
   +0.048, ext Calmar +0.184, ext MaxDD +3.2pp shallower). Removing QQQ alone only
   erases the marginal clean Sharpe edge while leaving the ext drawdown/Calmar edge
   intact; removing SPHQ alone grows the edge. The edge flips against Faber only on the
   full HAA universe.

2. **Is the mechanism "slow metric = less whipsaw on high-vol trending names"? No.**
   Faber's turnover on QQQ/SPHQ is equal-to-slightly-higher than 13612U's, the two
   metrics mostly agree on these names (18-27 disagreements of ~290 months), and their
   named-crisis drawdowns on the QQQ-containing universe are near-identical (Faber
   marginally deeper). 13612U's worst full-sample drawdown is not located in QQQ.

3. **What actually distinguishes CPM from HAA is the whole-universe composition**
   (CPM's diversifier mix with GLD and no in-universe IEF bond, vs HAA's bond-anchored
   set including in-universe IEF). Faber's tail-drawdown/Calmar advantage is a property
   of that CPM diversifier frame and is largely metric-name-agnostic to the growth
   tilt. The mean-asset-vol gap (21.5% vs 20.4%) is small, so "CPM is structurally
   higher-vol therefore a slower trend helps" is at best a weak, second-order
   contributor and is NOT the operative channel demonstrated here.

## Honesty / caveats

- Anchors reproduced exactly (Faber 1.1658/-12.97%/1.0137; 13612U 1.1540/-13.32%/0.9876
  clean) and production weight-parity gate passes.
- Clean window is the decision lens; the Faber-vs-13612U clean Sharpe deltas are all
  small (|0.002| to |0.063|), i.e. within-noise. The more consistent signal is in the
  EXT drawdown/Calmar dimension. Findings are single in-sample.
- The both->SPY variant drops cardinality 8 -> 7 (top-4 fixed), which itself shifts
  risky_fraction dynamics; treat that cell's magnitude with caution. The 8-asset single
  swaps (QQQ->SPY, SPHQ->SPY) bracket the conclusion at constant cardinality and still
  show Faber's ext drawdown edge surviving de-tilt.
- SPY has long history (fine for the swap); HAA-only names IWM/VEA/VWO lack the real
  open/close cache, so the mooex rebal-day override falls back to close-to-close for
  them -- identical treatment to the existing factorial harness, so the HAA comparison
  is internally consistent.

## Handoff

None required. Research-only deliverable complete. Possible follow-up for fixer/oracle
only if the team wants to act: a controlled GLD-in/IEF-in swap test to isolate which
single composition change flips Faber's drawdown edge between the CPM and HAA frames.
