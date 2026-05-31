# Benchmark fidelity audit: AAA + HAA-Simple vs published specs

Role: analyst (read-only re production; no production/memo files changed; no commit).
Scope: audit whether our AAA and HAA-Simple benchmark implementations match the
verified papers, whether the factorial baseline is a faithful AAA, compute the
TRUE faithful-AAA and TRUE HAA-Simple numbers, and map every component
difference between faithful AAA and production CPM (for the orchestrator to
design the factor set). Does NOT design or run a factorial.

Verified specs used as ground truth (from task brief):
- AAA (Butler/Philbrick/Gordillo/Varadi, SSRN 2328254): 10 assets
  [SPY, EZU/EFA, EWJ, EEM, VNQ/IYR, RWX, IEF, TLT, DBC, GLD]; 6-month (~126d)
  total-return momentum; select top 5 (top half), NO absolute screen;
  MINIMUM-VARIANCE weighting on a weighted covariance (126d correlation, 20d
  volatility); monthly; NO canary; NO cash/safe overlay.
- HAA-Simple (Keller & Keuning, SSRN 4346906): momentum = unweighted avg of
  1/3/6/12-month returns (13612U); if BOTH TIP and SPY momentum > 0 -> 100% SPY;
  else compare IEF and BIL momentum, hold the higher (BIL = cash); monthly,
  dividend-adjusted close.

---

## 1. AAA deviation table (verified spec vs each implementation)

Implementations audited:
- DASH: `build_dashboard.py:351` `bench_aaa_tip` ("B2 AAA standard with TIP canary"),
  universe `build_dashboard.py:313`.
- F6: `research/cpm_factorial_iv4_6factor.py` all-OFF cell (C=U=R=S=W=P=0),
  universe :76, canary :93, momentum :121, weighting :148, partial-safe :154.
  This is the baseline the MEMO factorial decomposition (Sections 5.4, 12.5.1,
  12.6.1) is anchored on; the harness labels it "AAA baseline" and "all-OFF (AAA
  baseline)".
- CANON: `research/cpm_factorial_canonical_aaa.py` all-OFF cell (U=R=P=C=0),
  universe :44, momentum :86, weighting :103. This is the source of the MEMO
  Section 5.3 "Canonical AAA benchmark" numbers (clean Sharpe 0.9695, Calmar
  0.5558, MaxDD -20.65%).

| Attribute | Verified AAA | DASH bench_aaa_tip | F6 all-OFF | CANON all-OFF |
|---|---|---|---|---|
| Universe size | 10 | 7 | 7 | 7 |
| Universe members | SPY,EZU/EFA,EWJ,EEM,VNQ,RWX,IEF,TLT,DBC,GLD | SPY,EFA,EEM,VNQ,GLD,TLT,DBC | SPY,EFA,EEM,VNQ,GLD,TLT,DBC | SPY,EFA,EEM,VNQ,GLD,TLT,DBC |
| IEF in risk universe? | YES (selectable) | NO (moved to safe pool) | NO (safe pool) | NO (safe pool) |
| Momentum metric | 6-month total return | 13612U (1/3/6/12 avg) | plain 12-month return | 13612U |
| Momentum lookback | ~126d (6m) | blended 1-12m | 12m | blended 1-12m |
| Selection | top 5 of 10 (top half) | top 4 (ceil(7/2)) | top 4 | top 4 |
| Absolute/positive screen | NONE | YES (s>0 filter) | NO (holds top-K) | YES (positive-trend) |
| Weighting | min-variance, WEIGHTED cov (126d corr / 20d vol) | min-variance, plain 504d cov | EQUAL weight | min-variance, plain 504d cov |
| Canary | NONE | TIP 13612U>0 gate | TIP 13612U>0 gate | NONE |
| Safe/cash overlay | NONE | best-of SHV/IEF (timed) | best-of SHV/IEF (timed) | best-of SHV/IEF (timed, only via screen) |
| Rebalance | monthly | monthly | monthly | monthly |

Universal deviations (ALL three impls): 7-asset (not 10; missing EWJ, RWX, and
one of EZU/IYR pair), top-4 (not top-5), IEF pulled out of the risk universe.
NONE uses the AAA 6-month momentum. DASH and F6 additionally add a TIP canary
that AAA does not have. DASH adds a positive screen AAA does not have. F6 also
replaces min-variance with equal weight.

Most faithful of the three: CANON (no canary, min-variance) but it still uses
13612U not 6m, is 7-asset not 10, top-4 not top-5, and adds a positive screen.

---

## 2. HAA-Simple deviation table (verified spec vs each implementation)

Implementations audited:
- DASH: `build_dashboard.py:391` `bench_haa_simple` (asset=SPY).
- BULLF: `research/factorial_decomposition_2026_05_30.py:141` `bull_wf` all-OFF
  (K=V=S=0); safe pool :44; this is the MEMO Section 12.5.2 row "0,0,0 (BULL
  factorial baseline)" claimed "reproduces HAA-Simple within 0.029 Sharpe".
- MEMO53: the MEMO Section 5.3 "HAA-Simple benchmark {BIL,AGG}" row (same
  bull_wf path, safe pool {BIL,AGG}).

| Attribute | Verified HAA-Simple | DASH | BULLF all-OFF | MEMO53 {BIL,AGG} |
|---|---|---|---|---|
| Offensive asset | SPY | SPY | SPY | SPY |
| Momentum | 13612U | 13612U | 13612U | 13612U |
| Risk-on gate | TIP>0 AND SPY>0 | TIP>0 AND SPY>0 | TIP>0 AND SPY>0 | TIP>0 AND SPY>0 |
| Defensive choice | best of IEF vs BIL | best of SHV vs IEF | best of BIL vs AGG | best of BIL vs AGG |
| Defensive pool match | IEF, BIL | IEF, SHV (BIL->SHV) | BIL, AGG (IEF->AGG) | BIL, AGG (IEF->AGG) |
| Rebalance | monthly | monthly | monthly | monthly |

HAA-Simple verdict: all three are FAITHFUL on the core logic (single SPY,
13612U, TIP+SPY dual gate). The only deviation is the defensive pool: the paper
uses {IEF, BIL}; DASH uses {SHV, IEF} (BIL proxied by SHV, IEF retained -> very
close), while BULLF/MEMO53 use {BIL, AGG} (BIL retained, IEF swapped for AGG ->
adds duration/credit). "best-of by momentum" over a 2-asset pool exactly
reproduces the paper's "if IEF > BIL hold IEF else BIL" rule, so the only real
gap is which two bonds are in the pool. The "{BIL,AGG}" label is therefore
HAA-Simple with AGG substituted for IEF, not a different strategy. It is a fair
HAA-Simple proxy, but calling it canonical HAA-Simple is slightly off because
the paper's defensive set is {IEF, BIL}.

"~HAA-Simple within 0.029 Sharpe" claim (MEMO Section 12.5.2): arithmetically
the memo compares BULLF clean Sharpe 0.989 vs MEMO53 {BIL,AGG} clean 0.960 =
0.029. That internal delta is real. Versus the TRUE faithful HAA-Simple computed
below (clean 0.9840), the BULLF baseline (0.989) is within 0.005 Sharpe -- so
the BULL factorial baseline is actually a CLOSER match to true HAA-Simple than
the {BIL,AGG} row it is compared against. The claim is directionally true and
conservative; the residual is the safe-pool substitution as the memo states.

---

## 3. TRUE faithful-AAA and TRUE HAA-Simple numbers

Computed with the verified specs via the same shared harness as the memo
(T+1 MOO-exact `mooex`, 10 bps/side, month-end signal), so numbers are
apples-to-apples with the memo tables. Script: `/tmp/true_aaa_haa.py`.
Windows: CLEAN 2008-05-30..2026-05-22, EXT 1999-03-10..2026-05-22.

Faithful AAA built as: 6-month total-return momentum, top-half selection, NO
sign screen, minimum-variance on WEIGHTED covariance (126d correlation, 20d
volatility), monthly, NO canary, NO safe overlay.

DATA CAVEAT: the panel lacks EWJ and RWX (and EZU/IYR), so the faithful AAA was
built on the 8 available members [SPY, EFA, EEM, VNQ, IEF, TLT, DBC, GLD] with
IEF correctly RETAINED in the risk universe. top-half = ceil(8/2) = 4 (vs the
paper's 5 of 10). This is the closest faithful AAA buildable from this panel;
the two missing assets (Japan equity, intl REIT) would change the numbers
somewhat but not the structural conclusions.

| Series | Window | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| TRUE AAA (8-of-10, 6m, top-4, wcov-minvar) | CLEAN | 0.7869 | 7.40% | 9.71% | -23.21% | 0.3188 |
| TRUE AAA | EXT | 0.8696 | 8.41% | 9.84% | -23.21% | 0.3624 |
| TRUE HAA-Simple (TIP+SPY 13612 -> SPY else best IEF/BIL) | CLEAN | 0.9840 | 11.60% | 11.92% | -20.41% | 0.5685 |
| TRUE HAA-Simple | EXT | 0.9735 | 10.73% | 11.11% | -20.41% | 0.5259 |

(BIL absent -> proxied by SHV in the HAA defensive pool; IEF retained, matching
the paper's {IEF, BIL} defensive set up to the BIL->SHV cash proxy.)

How these compare to what the memo currently calls AAA / HAA-Simple (clean):
- TRUE AAA clean Sharpe 0.7869 / Calmar 0.3188 vs MEMO "Canonical AAA"
  0.9695 / 0.5558. The memo's "canonical AAA" is ~0.18 Sharpe HIGHER than a real
  AAA -- because it adds a positive-trend screen and uses 13612U (both lift
  risk-adjusted returns) and drops the worst sleeves via the screen. The memo
  benchmark FLATTERS itself relative to a true AAA, but it also makes CPM's win
  over "AAA" look SMALLER than it is versus a real AAA.
- TRUE HAA-Simple clean Sharpe 0.9840 / Calmar 0.5685 vs MEMO {BIL,AGG}
  0.960 / 0.561 -- very close; the memo HAA-Simple is a faithful proxy.

---

## 4. Component-by-component map: faithful AAA -> production CPM

Production CPM = `cpm_live.compute_target_weights` (:384). Each row lists the AAA
value, the CPM value, and whether moving AAA->CPM is a single clean toggle or
bundles multiple independent sub-changes. This is the raw material for factor
design; it is NOT a proposed factor set.

| # | Component | Faithful AAA value | Production CPM value | Clean toggle or bundled? |
|---|---|---|---|---|
| 1 | Universe | 10 assets [SPY,EZU/EFA,EWJ,EEM,VNQ,RWX,IEF,TLT,DBC,GLD] | 8 assets [QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC] (`cpm_live.py:46-51`) | BUNDLED: (a) count 10->8; (b) US-equity swap SPY -> QQQ+SPHQ (broad beta -> Nasdaq + quality factor, two-name substitution); (c) IEF (and TLT-paired bonds, EWJ, RWX) REMOVED from the selectable risk set -- IEF reclassified as a safe-only asset. Three distinct sub-changes. |
| 2 | Momentum / ranker | 6-month total return (single lookback) | vol-adjusted Faber = (price - 10mo SMA)/SMA divided by 252d realized vol (`cpm_live.py:261,440-447`) | BUNDLED (three sub-changes): (a) metric form total-return -> SMA-distance trend; (b) lookback 6-month -> 10-month SMA; (c) divide by 252d vol (vol-adjustment). Going AAA-6m -> CPM-ranker is NOT a single change. |
| 3 | Selection count | top 5 of 10 (top half) | top 4 of 8 (top half, `TOP_K_CANDIDATES=4`, :62) | NOT an independent axis: both are the same RULE (top-half = ceil(N/2)); the absolute count differs only because the universe size differs (component #1). If the top-half rule is held fixed, there is no separate selection-count toggle; 5->4 is a derived consequence of U. Could be split out only by deliberately overriding the top-half rule. |
| 4 | Weighting | minimum-variance on WEIGHTED covariance (126d correlation, 20d volatility) | inverse-vol over held set, sigma from 504d cov diagonal (`cpm_live.py:320,470`) | BUNDLED (two sub-changes): (a) method min-variance optimizer -> inverse-vol heuristic (DROPS the correlation matrix entirely); (b) covariance window 126d-corr/20d-vol -> single 504d window. Method change and estimation-window change are conflated. |
| 5 | Positive-trend screen | NONE (hold full top-half regardless of sign) | YES: keep only names with positive raw faber score (`cpm_live.py:448-449`) | CLEAN single toggle (add/remove the sign filter). Caveat: the screen is applied to the faber score, so a sign-able trend metric must exist; it is conceptually independent of R but mechanically reads R's metric. |
| 6 | Partial-safe | NONE (always fully invested in the basket) | strict-4: risky_fraction = min(n_picks,4)/4, remainder to safe (`cpm_live.py:457-466`) | CLEAN toggle, but DEPENDENT: it only bites when the screen (#5) empties slots (n<4), and it needs a safe destination (#8). Inert unless S is on. |
| 7 | Canary | NONE | HYG-OR-TIP any-positive 13612U gate; if all <=0 go 100% safe (`cpm_live.py:55-57,404-419`) | CLEAN baseline-vs-prod toggle (off = no gate). The ON definition itself bundles internal choices: (a) which canary assets {HYG,TIP}; (b) 13612U metric; (c) any-positive rule. As an on/off axis it is clean; as a "design" it has sub-parameters. |
| 8 | Safe routing / asset | NONE | timed best-of {SHV, IEF} by 13612U (`cpm_live.py:52,355,400`) | NOT an independent axis: it is the DESTINATION activated by canary-off (#7), partial-safe routing (#6), or an empty screen (#5). No separate toggle; it only exists when C/S/P send weight to safe. |
| 9 | Rebalance / execution | monthly, month-end close signal | monthly, month-end close signal | NO DIFFERENCE. Held constant. The audit harness applies the same T+1 MOO-exact fill + 10 bps/side to both, so execution is not a faithful-AAA-vs-CPM axis. (AAA paper assumes monthly close; dividend-adjusted close is used for both.) |

Summary of which components are genuinely independent toggles vs bundled:
- Genuinely independent single toggles: #5 screen, #6 partial-safe (dependent on
  #5), #7 canary (on/off).
- Bundled multi-change axes: #1 universe (count + US-equity swap + IEF
  reclassification), #2 ranker (metric + lookback + vol-adjustment), #4 weighting
  (method + estimation window).
- Not independent axes at all: #3 selection count (bound to #1 via top-half
  rule), #8 safe routing (a destination for #5/#6/#7), #9 execution (held
  constant).

Implication for factor design: a 6-factor cube that uses one toggle each for
universe, ranker, weighting will silently bundle 3+3+2 = 8 sub-changes into 3
factors. Main effects for U, R, W will therefore be COMPOSITE (e.g. R mixes
metric-form + lookback + vol-adjust), and a clean "AAA 6-month momentum effect"
or "AAA min-variance effect" cannot be read from such a cube without splitting
those bundles. The orchestrator should decide which sub-changes to expose.

---

## 5. Verdict on the existing factorial baseline + memo labels

- The MEMO factorial decomposition (Sections 5.4 / 12.5.1 / 12.6.1) is anchored
  on the F6 all-OFF cell, which the harness labels "AAA baseline". That cell is
  NOT a faithful AAA: it adds a TIP canary (AAA has none), uses plain 12-month
  momentum (AAA = 6-month), EQUAL-weights (AAA = min-variance), is 7-asset (AAA =
  10), top-4 (AAA = 5), pulls IEF out of the risk universe, and overlays a timed
  SHV/IEF safe. Its clean Sharpe is 0.8561 (`cpm_factorial_iv4_6factor.json`
  cell 000000), not the 0.9695 the memo Section 5.3 cites for "Canonical AAA".
- The MEMO Section 5.3 "Canonical AAA benchmark" (Sharpe 0.9695) comes from a
  DIFFERENT cell (CANON all-OFF), which is closer to AAA (no canary,
  min-variance) but still uses 13612U not 6m, is 7-asset, top-4, and adds a
  positive screen. So the memo uses TWO different "AAA" baselines: one for the
  headline comparison (5.3) and a less-faithful one for the factor decomposition.
- Neither equals a real AAA (true clean Sharpe 0.7869). Calling either
  "canonical AAA" overstates fidelity. The factor labels "U = AAA-universe
  effect" and "R = AAA-momentum effect" are MISLABELED: the F6 baseline never
  uses AAA's 6m momentum or min-variance, so those main effects do not measure
  the AAA->CPM steps the labels imply.
- The HAA-Simple labels are largely defensible: the BULL factorial baseline and
  the Section 5.3 {BIL,AGG} row are faithful HAA-Simple up to the defensive-pool
  substitution, and the "within 0.029 Sharpe" claim is true (and conservative
  vs the true 0.9840).

IMPACT: the factorial decomposition can still be INTERNALLY valid (the cube is a
consistent A/B grid from its own baseline to production), but the LABELS and the
"reproduces canonical AAA" framing are wrong, because the all-OFF reference is
not a real AAA and the U/R/W toggles bundle multiple sub-changes (Section 4).
Main-effect MAGNITUDES are attributable to the bundled toggle as defined, not to
the named AAA design choice.

---

## 6. Caveats / confidence

- True-AAA numbers use 8 of the 10 AAA assets (EWJ, RWX, EZU/IYR unavailable in
  this panel) and top-4 (top-half of 8) rather than top-5 of 10. Structural
  conclusions (true AAA Sharpe well below the memo's "canonical AAA") are robust;
  exact decimals would shift with the two missing sleeves. Confidence: high on
  direction, medium on exact decimals.
- BIL absent -> SHV cash proxy in HAA defensive pool; IEF retained, so the
  faithful-HAA defensive logic matches the paper up to the cash-instrument proxy.
  HAA numbers confidence: high.
- All numbers use the shared mooex / T+1 MOO-exact / 10 bps-side harness, so they
  are directly comparable to the memo's tables.
- No production or memo files were modified. Throwaway script: `/tmp/true_aaa_haa.py`.

Next handoff: oracle/orchestrator to decide the factor set and whether to
relabel the memo's "canonical AAA" claims or re-anchor the factorial on a
faithful AAA. Re-running the factorial is a separate fixer/analyst task once the
factor design is chosen.
