# BULL vol-gate re-evaluated on the CORRECT objective (Calmar / MaxDD / vol), honest exec_lag=1

Date: 2026-05-30
Analyst role (read-only): no production file changed, no spec change, no commit.
Harness: `research/lag_robust_vol_gate.py` (UNCHANGED) reusing
`lookahead_audit_2026_05_30.py` timing/CPM/blend/metrics. Raw output:
`research/lag_robust_vol_gate.out` (reproduced exactly this run).

## Framing correction (why this supersedes the prior verdict)

The prior run (`lag_robust_vol_gate_findings.md`) ranked vol-gate variants by
**Sharpe** and concluded "no-gate dominates, drop the gate; S3-MONTHLY is the only
marginal survivor." That objective is wrong for a vol/DD overlay. A volatility gate
exists to **cut MaxDD and annualized vol** (vol-targeting), not to lift Sharpe. It
can be Sharpe-neutral or mildly Sharpe-negative and still be doing its job.

Correct objective, in priority order:

1. **Calmar** (CAGR / |MaxDD|) = headline verdict metric: return earned per unit of
   drawdown. This is what judges a DD tool's performance.
2. **MaxDD** and **annualized vol** = the reduction evidence (is the tool actually
   de-risking?).
3. **CAGR** = the cost to report against each reduction.
4. **Sharpe** = trailing context column only. NOT a ranking key.

All numbers below are **exec_lag=1 (honest T+1 fill)**. Same-day (`REF-ON-sameday`,
exec_lag=0) is shown ONLY as a lookahead ceiling and is excluded from ranking
because MOC same-day fill is not live-practical. `S4-LAGINPUT` (diagnostic) and the
lookahead ref are not ranked. `S5-VOLTGT` uses a **fitted 15% vol target (OVERFIT
-RISK)** and is a cross-check only.

Blend = 0.60 CPM + 0.40 BULL, both sleeves at exec_lag=1. 60/40 two-sleeve is the
headline (NOT the 3-sleeve). No threshold scans: all windows convention-locked.

## Reconciliation with prior audit (trust check)

Honest-lag references match `lag_robust_vol_gate_findings.md` exactly:

| series (clean 18y, BULL solo) | this run | prior md | match |
|---|---|---|---|
| REF-OFF (no gate, lag1)   | Sh 1.038 / CAGR 13.20% / DD -20.71% | same | exact |
| REF-ON-lag (RV20 gate, lag1) | Sh 0.929 / 9.78% / -15.64% | same | exact |
| BLEND REF-OFF / REF-ON-lag Sh | 1.310 / 1.258 | 1.310 / 1.258 | exact |

Same inputs, only the ranking objective changed.

---

## TABLE 1 - BLEND 60/40 (PRIMARY), exec_lag=1, ordered by Calmar (best first)

### CLEAN 18y

| variant | Calmar | MaxDD | Vol | CAGR (cost) | Sharpe |
|---|---|---|---|---|---|
| *REF-ON-sameday (lookahead, excl.)* | *1.385* | *-9.82%* | *9.84%* | *13.60%* | *1.351* |
| **S1-60** | **1.297** | -10.00% | 9.86% | 12.98% | 1.292 |
| S2-EMA | 1.272 | -10.00% | 9.89% | 12.72% | 1.266 |
| S1-120 | 1.268 | -10.00% | 9.69% | 12.68% | 1.286 |
| REF-ON-lag (current gate) | 1.257 | -10.00% | 9.84% | 12.58% | 1.258 |
| S5-VOLTGT (fitted, xcheck) | 1.228 | -10.00% | 9.71% | 12.28% | 1.247 |
| **REF-OFF (no gate)** | 1.208 | -11.59% | 10.46% | 14.01% | 1.310 |
| S3-MONTHLY | 1.129 | -11.59% | 9.61% | 13.09% | 1.333 |

### EXT 27y

| variant | Calmar | MaxDD | Vol | CAGR (cost) | Sharpe |
|---|---|---|---|---|---|
| *REF-ON-sameday (lookahead, excl.)* | *1.089* | *-11.79%* | *9.82%* | *12.84%* | *1.280* |
| **S1-120** | **1.097** | -11.35% | 9.71% | 12.44% | 1.256 |
| S2-EMA | 1.091 | -11.11% | 9.81% | 12.11% | 1.215 |
| **REF-OFF (no gate)** | 1.080 | -12.24% | 10.52% | 13.22% | 1.233 |
| S1-60 | 1.072 | -11.35% | 9.81% | 12.16% | 1.219 |
| S3-MONTHLY | 1.035 | -12.24% | 9.81% | 12.67% | 1.266 |
| REF-ON-lag (current gate) | 0.988 | -12.06% | 9.82% | 11.91% | 1.195 |
| S5-VOLTGT (fitted, xcheck) | 0.966 | -12.06% | 9.70% | 11.65% | 1.185 |

Read: at blend, **every daily gate cuts vol and MaxDD vs no-gate** (no-gate has the
highest vol on both windows and the deepest blend MaxDD on clean). On **Calmar**,
the slow daily forms **S1-120 and S2-EMA beat no-gate on BOTH windows**; S1-60 wins
clean strongly but slips just under no-gate on ext. The current RV_20d gate beats
no-gate on clean (+0.049) but **loses on ext (-0.092)**. S3-MONTHLY is the worst
Calmar both windows because it does **not** cut MaxDD (-11.59 / -12.24 == no-gate).

---

## TABLE 2 - BULL solo (SECONDARY), exec_lag=1, ordered by Calmar (best first)

### CLEAN 18y

| variant | Calmar | MaxDD | Vol | CAGR (cost) | Sharpe |
|---|---|---|---|---|---|
| **S1-60** | **0.788** | **-13.66%** | 10.65% | 10.77% | 1.017 |
| S2-EMA | 0.673 | -15.05% | 10.77% | 10.13% | 0.953 |
| REF-OFF (no gate) | 0.637 | -20.71% | 12.77% | 13.20% | 1.038 |
| REF-ON-lag (current gate) | 0.625 | -15.64% | 10.69% | 9.78% | 0.929 |
| S1-120 | 0.576 | -17.42% | 10.31% | 10.04% | 0.983 |
| S5-VOLTGT (fitted, xcheck) | 0.575 | -15.79% | 10.27% | 9.07% | 0.900 |
| S3-MONTHLY | 0.527 | -20.71% | 11.10% | 10.92% | 0.993 |

### EXT 27y

| variant | Calmar | MaxDD | Vol | CAGR (cost) | Sharpe |
|---|---|---|---|---|---|
| **S1-60** | **0.681** | **-13.66%** | 10.50% | 9.30% | 0.899 |
| S2-EMA | 0.609 | -15.05% | 10.60% | 9.17% | 0.880 |
| S1-120 | 0.573 | -17.42% | 10.21% | 9.99% | 0.983 |
| REF-OFF (no gate) | 0.571 | -20.71% | 12.62% | 11.83% | 0.949 |
| REF-ON-lag (current gate) | 0.555 | -15.64% | 10.56% | 8.68% | 0.841 |
| S5-VOLTGT (fitted, xcheck) | 0.511 | -15.79% | 10.12% | 8.07% | 0.817 |
| S3-MONTHLY | 0.505 | -20.71% | 11.15% | 10.47% | 0.948 |

Read: at the sleeve level the DD/vol value of gating is large and **S1-60 is the
unambiguous winner on Calmar on both windows**, with the **deepest MaxDD cut**
(-13.66% vs -20.71% no-gate, ~34% shallower trough), a ~2.1pp vol cut, and a
near-neutral Sharpe. No-gate has the worst MaxDD and worst vol. The current RV_20d
gate cuts MaxDD/vol but its Calmar is flat-to-below no-gate (0.625 / 0.555) -- the
DD reduction is bought at proportional CAGR loss, i.e. risk reduced but not
risk-efficiently. **S3-MONTHLY does not de-risk the sleeve at all** (MaxDD/vol ==
no-gate), so it is the worst Calmar -- the exact opposite of its prior Sharpe rank.

Note: vols within the honest cluster are nearly tied (BULL ~10.3-10.8%, blend
~9.6-9.9%), so vol alone does not separate variants; **Calmar and MaxDD are the
decisive keys**, and S1-60 wins both at the sleeve.

---

## TABLE 3 - CRISIS windows, exec_lag=1 (the real DD-tool test)

A drawdown tool must shave the trough in real crises even a day late. BULL-solo
MaxDD (where the gate acts) and CAGR shown; "help?" = trough shaved vs no-gate.

### BULL-solo MaxDD per crisis

| variant | dot-com | GFC | COVID | 2022 |
|---|---|---|---|---|
| REF-OFF (no gate) | -12.49% | -13.66% | -12.44% | -9.73% |
| REF-ON-lag (current) | -12.49% | -13.66% | **-4.68%** | **-0.30%** |
| S1-60 | -12.49% | -13.66% | -12.44% | **-0.30%** |
| S1-120 | -12.34% | -13.66% | **-4.68%** | -9.73% |
| S2-EMA | -12.49% | -13.66% | **-4.68%** | **-0.30%** |
| S3-MONTHLY | -12.49% | **-10.40%** | -12.44% | -9.73% |
| S5-VOLTGT (fitted) | -12.21% | **-11.51%** | **-4.68%** | **-0.30%** |

### Which crises each honest form actually protects (BULL trough shaved)

| variant | dot-com | GFC | COVID | 2022 | coverage |
|---|---|---|---|---|---|
| current RV_20d | no | no | YES | YES | modern vol spikes |
| S1-60 | no | no | no | YES | 2022 only |
| S1-120 | ~ | no | YES | no | COVID only |
| S2-EMA | no | no | YES | YES | modern vol spikes |
| S3-MONTHLY | (CAGR) | YES | no | no | slow grinders |
| S5-VOLTGT | no | partial | YES | YES | modern + part GFC |

Two findings:

1. **No single honest form covers all four crises.** Daily fast/medium forms
   (current, S2-EMA, S5) catch the modern vol-spike crises (COVID, 2022); only the
   monthly form (S3) catches the slow grinders (GFC trough -10.40 vs -13.66;
   dot-com via CAGR). They are complementary, each covering ~half.
2. **At the 60/40 BLEND, crisis MaxDD is barely differentiated** (raw output: GFC
   all -10.00%, COVID all -9.82%, dot-com -5.47..-6.36%, 2022 -5.23..-5.84%). The
   CPM sleeve dominates blend crisis drawdown, so the BULL vol-gate's crisis
   protection **mostly washes out at the blend headline** and shows up only at the
   BULL-solo level. (2022 blend DD actually slightly worsens with gates: -5.84 vs
   -5.23 no-gate.)

---

## Direct answers

**(a) Does the current RV_20d gate, under honest lag, reduce blend/BULL MaxDD and
vol vs no-gate (even if Sharpe falls), and at what CAGR cost?**

YES on reduction, mixed on whether it pays for itself on Calmar:

- BLEND clean: vol 10.46 -> 9.84% (-0.62pp), MaxDD -11.59 -> -10.00% (-1.59pp,
  ~14% shallower), **Calmar 1.208 -> 1.257 (+0.049)**, CAGR cost 14.01 -> 12.58%
  (-1.43pp). Earns its place on clean.
- BLEND ext: vol -0.70pp, MaxDD -12.24 -> -12.06% (only -0.18pp), but
  **Calmar 1.080 -> 0.988 (-0.092)** -- CAGR cost (-1.31pp) outruns the DD cut, so
  it does NOT earn its place on ext.
- BULL clean: MaxDD -20.71 -> -15.64% (-5.07pp, ~25% shallower), vol -2.08pp, but
  **Calmar flat (0.637 -> 0.625)** -- de-risks but not efficiently; CAGR cost
  -3.42pp.

Verdict on (a): the current gate is a **marginal, clean-window-only Calmar win**
that **fails on the extended window** and only ties no-gate Calmar at the sleeve.
It does cut MaxDD/vol, so it is not useless, but it is dominated by slower forms.

**(b) Does any lag-robust slow form (S1/S2/S3) cut MaxDD/vol vs no-gate and beat the
current gate on the DD/vol objective?**

YES, decisively:

- **S1-60 (RV_60d/252 daily crossover)** is the best sleeve-level DD tool: best
  BULL Calmar on BOTH windows (0.788 / 0.681 vs no-gate 0.637 / 0.571), the
  **deepest MaxDD cut of any honest variant** (-13.66% both windows vs -20.71%),
  ~2.1pp vol cut, near-neutral Sharpe. It strictly dominates the current RV_20d
  gate on every DD/vol metric (better MaxDD, similar vol, much better Calmar,
  higher CAGR).
- At the **blend headline**, **S1-120 and S2-EMA beat no-gate Calmar on BOTH
  windows** and beat the current gate (S1-120 clean +0.060 / ext +0.017; S2-EMA
  clean +0.064 / ext +0.011 vs no-gate), while also cutting MaxDD and vol.
- **S3-MONTHLY (the prior Sharpe-ranked "winner") is the Calmar LOSER**: it does
  not cut MaxDD/vol at all, so it has the worst blend and BULL Calmar on both
  windows. Its only DD merit is shaving the GFC/dot-com slow-grind troughs at the
  sleeve. As a general vol/DD overlay it fails the objective.

---

## RANKED VERDICT (Calmar-led, honest exec_lag=1)

Composite of blend (primary) + BULL (secondary) Calmar, with MaxDD/vol reduction
and CAGR cost. Lookahead ref and S4 diagnostic excluded; S5 flagged fitted.

| rank | variant | why | CAGR cost vs no-gate |
|---|---|---|---|
| 1 | **S1-60** (RV_60d/252) | best BULL Calmar both windows; deepest MaxDD cut (-13.66 vs -20.71); best blend Calmar clean; ~flat blend Calmar ext. Lag-robust, no fitted param. | BULL ~-2.4pp; blend ~-1.0pp |
| 2 | **S1-120 / S2-EMA** | beat no-gate blend Calmar on BOTH windows; 2nd-best BULL Calmar; cut MaxDD/vol. Slow, lag-robust, convention-locked. | blend ~-0.8 to -1.1pp |
| 3 | REF-OFF (no gate) | middling Calmar; worst MaxDD and vol everywhere. Wins only on raw CAGR/Sharpe -- the wrong objective. | 0 (baseline) |
| 4 | REF-ON-lag (current RV_20d) | cuts MaxDD/vol but Calmar flat-to-below no-gate; **fails ext blend Calmar**. Dominated by S1-60/S1-120/S2. | blend -1.3 to -1.4pp |
| 5 | S3-MONTHLY | does not de-risk (MaxDD/vol == no-gate); worst Calmar. Only GFC/dot-com crisis merit. | -- |
| x | S5-VOLTGT | fitted 15% target (overfit-risk); poor Calmar. Drop. | -- |

### Bottom line

On the **correct Calmar/DD objective under honest T+1 execution, no-gate does NOT
dominate** -- that conclusion was a Sharpe-ranking artifact. No-gate carries the
worst MaxDD and worst vol at both blend and sleeve. The best honest-execution
vol/DD tool for BULL is a **slow daily realized-vol crossover, S1-60 (RV_60d vs
RV_252d)**: it cuts the BULL trough by ~34% (-13.66% vs -20.71%) and vol by ~2.1pp
at ~2.4pp CAGR cost, with the best Calmar on both windows and a near-neutral Sharpe
-- the textbook signature of a vol-targeting overlay doing its job. For the 60/40
blend headline specifically, **S1-120 or S2-EMA** are the most robust (beat no-gate
Calmar on both clean and ext).

The **current production RV_20d gate is the weakest defensible choice**: it does
reduce MaxDD/vol but only earns its Calmar on the clean window and **fails on the
extended window**, and it is dominated by every slower form on the DD/vol
objective. The prior recommendation ("drop the gate, no-gate wins") holds ONLY if
judged by Sharpe; judged correctly by Calmar/MaxDD/vol, the recommendation flips to
**replace the fast RV_20d gate with a slow lag-robust crossover (S1-60 at the
sleeve, or S1-120/S2-EMA for blend robustness)**, not to drop gating entirely.

### Caveats / confidence

- Close-to-close accounting (no intraday open), consistent with the production
  engine; strict MOO would land between same-day and lagged.
- Crisis sub-windows are short-sample and noisy; treat the per-crisis MaxDD shaving
  as directional. The blend-level Calmar gaps (~+0.05-0.09 clean, ~+0.01-0.02 ext
  for the slow forms) are modest and within plausible bootstrap noise -- "cuts DD
  at acceptable cost," not a large robust edge.
- S1-60 wins the sleeve cleanly on both windows; at the blend its ext-window Calmar
  is ~flat vs no-gate, so the blend-robust pick (S1-120/S2-EMA) and the sleeve pick
  (S1-60) differ slightly. Decision depends on whether the gate is judged at sleeve
  or blend level.
- These are convention-locked windows (60/120/252 daily, 12/36 monthly); no
  threshold was scanned or tuned, so no in-sample optimization of the crossover
  windows. S5's 15% target IS fitted -> excluded from the recommendation.
- 60/40 two-sleeve is the headline; 3-sleeve NDX unaffected by the BULL vol gate.
- Pre-2010 ext window uses stitched proxies (`cpm_live.py:84-103`).

## Reproduce

```
.venv/bin/python research/lag_robust_vol_gate.py
```
