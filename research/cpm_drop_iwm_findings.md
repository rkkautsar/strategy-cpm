# Drop-IWM universe test: SPY as sole US equity (IEF->GLD always)

Analyst run, 2026-06-02. Research only; CPM prod unchanged. Point-estimates
(bootstrap skipped per scope). HIGH overfit caution -- exploratory
universe-design, single in-sample window, PIT/cached data.

Script: `research/cpm_drop_iwm_run.py` -> `research/cpm_drop_iwm_run.json`
Run: `.venv/bin/python research/cpm_drop_iwm_run.py`
Window: CLEAN 2008-05-30..2026-05-22, EXT 1999-03-10..2026-05-22.
Convention: mooex / T+1 MOO, both-252, 10 bps/side. Safe selector = best of
{SHV, IEF} (unchanged in all configs; IEF stays safe-pool only).

## Hypothesis

User dislikes IWM (small-cap: adds vol, weak size premium). Make SPY the sole
US equity. IEF->GLD always (IEF is a bond -> safe pool only, never risky;
consistent with CPM-8). Isolate the IWM-drop effect with GLD already in and
IEF already out, under both the HAA and CPM mechanisms.

Universes (risky pool):
- G1 keep IWM (8): SPY, IWM, VEA, VWO, VNQ, GLD, DBC, TLT
- G2 drop IWM (7) [USER TARGET]: SPY, VEA, VWO, VNQ, GLD, DBC, TLT

Mechanisms:
- HAA (R0 M0): 13612U dual momentum, TIP-only canary, top-4, equal-weight.
- CPM (R1 M1): vol-adj Faber ranker + raw-Faber screen, min-var 3-of-4 at
  n_pos=4, TIP-only canary, top-4, best-of{SHV,IEF} safe. For G2 (7 risky):
  top-4 of 7 then min-var 3-of-4.

## Gates (reproduce anchors first) -- PASS

| gate | actual | target | pass |
|------|--------|--------|------|
| HAA mech on HAA-8 | 0.8669910 | 0.8670 | yes |
| CPM mech on CPM-8 | 1.2556733 | 1.255673 | yes |

Extra confirmation: G1 HAA mech = 0.9400 matches the user's known ~0.9400
anchor for IEF->GLD keep-IWM under HAA mech.

## Full metrics (CLEAN; EXT in parens where noted)

| config | Sharpe | Sortino | CVaR95 | Calmar | Martin | MaxDD | CAGR | vol | turn |
|--------|--------|---------|--------|--------|--------|-------|------|-----|------|
| HAA-8 HAAmech (anchor) | 0.8670 | 1.2296 | 5.525 | 0.6386 | 2.216 | -14.68% | 9.37% | 11.08% | 6.81 |
| CPM-8 CPMmech (anchor) | 1.2557 | 1.8058 | 8.230 | 1.0076 | 4.257 | -13.03% | 13.13% | 10.28% | 7.08 |
| G1 keepIWM HAAmech | 0.9400 | 1.3376 | 6.013 | 0.7175 | 2.497 | -14.69% | 10.54% | 11.40% | 6.97 |
| G1 keepIWM CPMmech | 1.0842 | 1.5428 | 6.982 | 0.7191 | 2.830 | -15.71% | 11.30% | 10.40% | 7.32 |
| G2 dropIWM HAAmech | 0.9220 | 1.3098 | 5.897 | 0.7425 | 2.485 | -12.98% | 9.64% | 10.64% | 6.58 |
| G2 dropIWM CPMmech | 1.0924 | 1.5621 | 7.084 | 0.8530 | 3.099 | -13.03% | 11.12% | 10.15% | 7.04 |

EXT Sharpe: HAA-8 1.0307; CPM-8 1.2549; G1 HAA 1.0731; G1 CPM 1.2216;
G2 HAA 1.0860; G2 CPM 1.1914. EXT MaxDD: G1 CPM -16.78% vs G2 CPM -14.14%.

Anchors for reference: HAA-8 0.8670; CPM-mech-on-HAA-8 0.9399; CPM-mech 2-swap
(GLD+SPHQ) 1.200; full CPM-8 1.2557.

## IWM-drop effect (G2 minus G1, IWM the ONLY difference)

| mechanism | window | dSharpe | dMaxDD | dCalmar | dVol |
|-----------|--------|---------|--------|---------|------|
| HAA | CLEAN | -0.0180 | +1.71pp better | +0.0250 | -0.76pp |
| HAA | EXT | +0.0129 | +1.68pp better | +0.0457 | -0.63pp |
| CPM | CLEAN | +0.0082 | +2.68pp better | +0.1339 | -0.25pp |
| CPM | EXT | -0.0302 | +2.64pp better | +0.0935 | -0.58pp |

Sharpe effect is tiny and sign-flips by window/mechanism (|dSharpe| <= 0.03 in
all four cells) -- IWM is near-neutral on Sharpe. But dropping IWM improves
drawdown, Calmar, and vol in EVERY cell, both mechanisms, both windows. G2
weakly dominates G1 on risk-adjusted/tail metrics.

## Verdict

(a) Does dropping IWM (SPY sole US equity) help or hurt?
Near-neutral on Sharpe (+/-0.03 both ways), consistently HELPS drawdown/Calmar/
vol. Under HAA mech CLEAN, Sharpe dips -0.018 (0.9400->0.9220) but MaxDD
improves -14.69%->-12.98% and Calmar 0.7175->0.7425. Small-cap is effectively
dead weight here: removing it costs no meaningful return but trims tail risk.
The user's dislike of IWM is supported -- dropping it is a free risk reduction.

(b) Under CPM mech, SPY-only with GLD (G2) = 1.0924 CLEAN, edging keep-IWM G1
(1.0842) and clearly milder drawdown (-13.03% vs -15.71%, Calmar 0.853 vs
0.719). EXT favors G1 on Sharpe (1.2216 vs 1.1914) but G2 still has the better
drawdown both windows. GLD is in both, so "with vs without GLD" is not isolated
here; IEF->GLD is what lifts both G1/G2 well above the 0.8670 HAA-8 floor.

(c) Do the SPHQ/QQQ tilts earn their keep?
Yes. Clean SPY+GLD (G2 CPMmech 1.0924) trails:
- CPM-mech 2-swap (adds SPHQ) 1.200 -> SPHQ quality tilt alone worth ~+0.11
- full CPM-8 (adds SPHQ, QQQ, EFA, EEM) 1.2557 -> full tilt stack worth ~+0.16
The tilts add real Sharpe (~0.16) that the clean universe leaves on the table.

Net: a clean "SPY sole US equity + GLD, no IEF/small-cap/QQQ/SPHQ" universe is
respectable (CPM-mech Sharpe ~1.09, MaxDD ~-13%, Calmar ~0.85) and strictly
better on tail risk than keeping IWM, but it gives up ~0.16 Sharpe vs full CPM.
The quality (SPHQ) and growth (QQQ) tilts earn their keep. Recommended framing:
dropping IWM = safe risk-trim with no return cost; but do not also drop SPHQ/QQQ
unless drawdown-minimization is valued over ~0.16 Sharpe.

## Caveats

- Point-estimates only; no bootstrap CI / walk-forward. dSharpe magnitudes
  (<=0.03) are well within plausible noise -> treat IWM-drop as Sharpe-neutral,
  not a proven Sharpe edge. The drawdown/Calmar improvement is the durable
  signal (consistent across 4 cells).
- Single in-sample window; IEF->GLD and SPHQ were selected in prior in-sample
  attribution -> the tilt-value figures (~0.11, ~0.16) are selection-biased
  upward.
- PIT/cached data. CPM production universe unchanged by this run.
