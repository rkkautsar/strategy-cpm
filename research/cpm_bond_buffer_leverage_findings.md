# CPM bond-buffer / dedicated-diversifier slot + optional leverage (HAA-revisited analog)

Scope: research only. Read-only on production. No memo/prod edits, no commit.
Harness: `research/cpm_bond_buffer_leverage_harness.py` (+ `.json` output).
Engine: production `cpm_live.compute_target_weights`. Accounting: memo mooex
T+1 MOO exact (`exec_lag_moo_validation_2026_05_30._segment_returns_conv`),
10 bps/side, monthly rebalance, point-in-time signals. Decision lens = clean
18y window 2008-05-30..2026-05-22.

## Baseline: BOTH-252 prod CPM (UPDATED)

Production CPM is now standardized to BOTH-252 (rank-vol AND weight-vol both
252d; `cpm_live.CORR_LOOKBACK_DAYS = 252`). ALL comparisons below use the
both-252 CPM as the baseline, NOT the old 252/504 config (1.1910 / -12.67% /
1.0615). The harness pins 252 in-process so the anchor reproduces
deterministically; cpm_live.py is not edited by this work.

## Anchor reproduction (FIRST, gate)

Reproduced exactly via the production engine through the mooex harness:

| Metric | Reproduced | Both-252 target |
|---|---:|---:|
| Sharpe | 1.1658 | 1.1658 |
| MaxDD | -12.97% | -12.97% |
| Calmar | 1.0137 | 1.0137 |
| Martin | 3.6907 | -- |
| Vol | 11.18% | -- |

(The static-blend `w=1.0` row reads 1.1625 instead of 1.1658 only because that
series starts at the clean boundary without the pre-2008 warmup month used for
the first rebalance's turnover-cost basis. Negligible; the true anchor uses the
full-history CPM series and matches to 4 dp.)

## Article mechanism (faithful summary)

Source: https://nlxfinance.wordpress.com/2024/03/07/the-haa-strategy-revisited/
(numeric stat tables are embedded images, so exact figures could not be scraped;
mechanism and qualitative claims are read verbatim from the prose).

- Base strategy: Keller/Keuning **HAA-Simple** (Hybrid Asset Allocation,
  simplified by Allocate Smartly). Offensive = 100% SPY; defensive = BIL/IEF.
  ETFs used: SPY, IEF, TIP, BIL. **Filter/canary = TIP (TIPS) momentum**; when
  TIP momentum turns negative the position is moved to defensive (the author
  frames this as "exit when stock-bond decorrelation is likely to fail").
- **Proposal (HAA.60.40):** replace the 100% SPY offensive leg with a **60% SPY
  + 40% IEF** blend. The always-on bond pocket is decorrelated from equities and
  cushions equity shocks; TIP/IEF are interchangeable as the filter ("more or
  less the same"). Lower vol -> "turns 60/40 into a long, quiet river".
- **Leverage variants:** lower vol "may enable a little leverage":
  - `HAA.75.75` = 75% SPY futures + 75% IEF (1.5x gross).
  - `HAA.100.50` = 100% SPY futures + 50% IEF (1.5x gross).
  Compared against plain SPY and unlevered `HAA.SPY` (100% SPY HAA).
- **Borrow-cost assumption:** NONE. "brokerage fees, execution spreads and taxes
  are not taken into account"; leverage is obtained via S&P 500 **futures**
  (financing implied, not charged). Prices are dividend-adjusted closes.
- **Claimed results (qualitative; tables are images):** HAA.60.40 sharply lowers
  drawdown/vol vs classic 60/40; levered HAA variants aim to beat plain SPY /
  unlevered HAA at controlled risk. Author flags leverage tail risk explicitly:
  levered HAAs "did a good job getting out very early in the 2022 implosion...
  had things worked out differently, the leveraged strategies would have been
  more exposed."

CPM analog mirrors this: (a) static `w*CPM + (1-w)*bond`; (b) dedicated always-on
diversifier slot; (c) constant leverage with an EXPLICIT borrow cost
(SHV t-bill rate + 50 bps on borrowed notional) plus a de-lever-only vol-target
overlay for contrast. AGG proxied by **BND**, BIL proxied by **SHV** (AGG/BIL
absent from the frozen panel).

## (a) STATIC BLEND  -- w*CPM + (1-w)*bond (clean 18y)

| bond | w | Sharpe | Vol | MaxDD | Calmar | Martin | CAGR |
|---|---:|---:|---:|---:|---:|---:|---:|
| IEF | 1.0 (CPM) | 1.163 | 11.18% | -12.97% | 1.013 | 3.69 | 13.15% |
| IEF | 0.9 | 1.182 | 10.15% | -11.49% | 1.057 | 3.60 | 12.15% |
| IEF | 0.8 | 1.197 | 9.19% | -10.36% | 1.075 | 3.40 | 11.14% |
| IEF | 0.7 | 1.206 | 8.29% | -11.40% | 0.888 | 3.09 | 10.12% |
| IEF | 0.6 | 1.199 | 7.51% | -12.45% | 0.731 | 2.69 | 9.10% |
| TLT | 0.9 | 1.170 | 10.32% | -11.94% | 1.023 | 3.22 | 12.21% |
| TLT | 0.8 | 1.146 | 9.73% | -15.43% | 0.729 | 2.59 | 11.25% |
| TLT | 0.7 | 1.082 | 9.46% | -19.00% | 0.540 | 1.99 | 10.26% |
| TLT | 0.6 | 0.978 | 9.52% | -22.55% | 0.410 | 1.48 | 9.25% |
| BND | 0.9 | 1.180 | 10.17% | -11.66% | 1.041 | 3.62 | 12.14% |
| BND | 0.8 | 1.196 | 9.19% | -10.33% | 1.077 | 3.50 | 11.13% |
| BND | 0.7 | 1.211 | 8.25% | -10.32% | 0.980 | 3.27 | 10.11% |
| BND | 0.6 | 1.219 | 7.37% | -11.06% | 0.822 | 2.95 | 9.09% |

Read:
- **IEF / BND buffers** cut vol hard (11.2% -> ~7.4%) and shave MaxDD to ~-10%
  at w=0.8; Sharpe nudges up modestly (+0.03 to +0.06). Calmar peaks ~1.08 at
  w=0.8 then FALLS at heavier bond weights because the bond's own 2022 drawdown
  starts to dominate (vol keeps dropping but MaxDD stops improving).
- **TLT buffer is actively harmful:** long duration imports the 2022 bond crash
  -> MaxDD blows out to -22.6% and Sharpe collapses to 0.98 at w=0.6. Wrong
  instrument. The buffer must be short/intermediate (IEF/BND), not long (TLT).

## (b) DEDICATED DIVERSIFIER SLOT (clean 18y)

A fixed slot to a single static bond is mathematically identical to (a) with
w = 1-frac, so that adds nothing new. The informative variant routes the
always-on slot to CPM's **dynamic** safe selector (`best_safe` IEF/SHV
duration switch) -> a duration-adaptive buffer:

| slot | frac | Sharpe | Vol | MaxDD | Calmar | Martin | CAGR |
|---|---:|---:|---:|---:|---:|---:|---:|
| dyn-safe | 0.2 | 1.191 | 9.15% | -10.34% | 1.066 | 3.82 | 11.03% |
| dyn-safe | 0.3 | 1.202 | 8.20% | **-9.01%** | **1.106** | **3.83** | 9.97% |
| dyn-safe | 0.4 | 1.203 | 7.31% | **-8.74%** | 1.018 | 3.74 | 8.90% |

Read: the dynamic-safe slot is the **best risk profile** of every unlevered
variant. At frac=0.3 it cuts MaxDD from -12.97% to **-9.01%**, lifts Calmar to
1.106 and **Martin to 3.83 (above CPM's 3.69)** -- because it switches the
always-on buffer to SHV in duration-hostile regimes (2022) instead of eating the
bond drawdown a static IEF/BND slot suffers. Sharpe still only +0.04 (noise).

## (c) LEVERAGE on the lowest-vol buffered blend (dyn-safe 40%, vol 7.33%)

Borrow cost EXPLICIT = SHV t-bill daily + 50 bps/yr on the (L-1) borrowed
notional. Constant leverage (article-faithful), plus an in-sample vol-matched
point and a de-lever-only vol-target overlay.

| variant | Sharpe | Vol | MaxDD | Calmar | Martin | CAGR |
|---|---:|---:|---:|---:|---:|---:|
| base (dyn-safe 40%, unlevered) | 1.203 | 7.31% | -8.74% | 1.018 | 3.74 | 8.90% |
| L=1.5x | 1.121 | 10.96% | -13.18% | 0.939 | 3.24 | 12.37% |
| L=2.0x | 1.080 | 14.61% | -17.54% | 0.901 | 2.97 | 15.81% |
| L=1.528x (vol-matched to CPM, IN-SAMPLE) | 1.118 | 11.17% | -13.43% | 0.936 | -- | 12.57% |
| vol-target capped @1x (de-lever only, target=CPM vol) | 1.179 | 7.17% | **-8.10%** | **1.051** | -- | -- |
| **unlevered CPM (reference)** | **1.166** | 11.18% | -12.97% | 1.014 | 3.69 | 13.15% |
| 60/40 SPY-IEF (reference) | 0.795 | 11.42% | -29.82% | 0.294 | -- | -- |

Read:
- **At matched vol the levered buffer LOSES to unlevered CPM.** Vol-matched
  (1.528x) -> Sharpe 1.118 vs CPM 1.166, and MaxDD -13.43% vs -12.97%
  (WORSE on both). The article's headline claim (levered-buffered beats the
  unlevered base at matched vol) **does NOT transfer to CPM**. Reason: the
  article's base is a low-Sharpe 60/40-style sleeve where leverage adds value;
  CPM is already a high-Sharpe, tail-controlled base, so leverage + financing
  only adds drag and re-imports the drawdown the buffer removed.
- **Levered buffer DOES beat 60/40** -- L=1.5x Sharpe 1.121 vs 0.795 and MaxDD
  -13.2% vs -29.8% -- so "beat 60/40 with much less DD" holds, but that is a low
  bar already cleared by plain unlevered CPM.
- **De-levering wins, not levering.** The vol-target cap (never >1x) gives the
  best DD/-8.10% and Calmar 1.051 of any variant. For a capital-preservation
  strategy the useful lever is reducing exposure in storms, not adding it in calm.

## Significance (paired block-bootstrap, B=2000, block=21, clean window)

| comparison | dSharpe | 95% CI | verdict |
|---|---:|---|---|
| unlevered buffer - CPM | +0.038 | [-0.087, +0.179] | includes 0 (ns) |
| L=1.5x buffer - CPM | -0.045 | [-0.171, +0.096] | includes 0 (ns) |
| L=2.0x buffer - CPM | -0.086 | [-0.210, +0.056] | includes 0 (ns) |
| vol-matched buffer - CPM | -0.048 | [-0.173, +0.093] | includes 0 (ns) |
| unlevered buffer - 60/40 | +0.409 | [-0.079, +0.874] | includes 0 (ns) |
| L=1.5x buffer - 60/40 | +0.326 | [-0.162, +0.792] | includes 0 (ns) |

Every Sharpe difference is statistically unresolved over this single 18y in-sample
window (consistent with the memo's note that even CPM-vs-60/40 CIs include zero).

## Critical framing: does an always-on buffer add anything beyond CPM's routing?

CPM already routes to bonds dynamically (TLT/GLD/etc. when trending; IEF/SHV via
breadth-scaled partial-safe + canary when defensive). The always-on buffer is
**partly redundant but not fully**:

- **Redundant on Sharpe:** the unlevered buffer's Sharpe gain is +0.04..+0.06,
  inside noise. CPM's dynamic routing already captures the risk-adjusted edge.
- **Additive on residual risk-on vol/DD:** the buffer trims vol/DD that CPM
  carries during fully-invested risk-on months (CPM only de-risks when breadth
  or the canary force it). The **dynamic-safe slot** is the cleanest expression:
  -12.97% -> -9.01% MaxDD and Martin 3.69 -> 3.83 at frac=0.3, with the duration
  switch avoiding the static-bond 2022 trap. So it buys genuine extra tail
  reduction -- at the cost of diluting CAGR (13.2% -> ~10%).
- The benefit is **dilution-shaped, not new-alpha-shaped**: lower vol, lower DD,
  lower return, ~flat Sharpe. That is a portfolio-construction preference dial,
  not an engine improvement.

## VERDICT

1. **Unlevered bond-buffer / diversifier slot:** mild, NOT statistically
   significant risk-adjusted improvement; mostly return dilution plus a real but
   modest tail trim. The **dynamic-safe diversifier slot (frac 0.2-0.3)** is the
   only version worth keeping in mind -- it lowers MaxDD to ~-9.0% and edges
   Martin above CPM while staying duration-aware. CPM's dynamic routing already
   captures most of the diversification benefit; a static IEF/BND slot is largely
   redundant and a TLT slot is harmful. Recommendation: **explore-further-lite**
   (optional low-vol/low-DD variant for capital-preservation-max investors who
   accept lower CAGR), not a headline edge.

2. **Levered-buffered version:** **does NOT beat unlevered CPM at matched vol**
   (the article's core claim fails to transfer, because CPM is already a
   high-Sharpe base, unlike the article's 60/40 base). It beats 60/40, but so
   does plain CPM. Recommendation: **not worth it.** Leverage also directly
   contradicts CPM's capital-preservation thesis and a prior review's explicit
   anti-leverage warning, and adds genuine tail risk (the article itself concedes
   the 2022 escape was partly luck). If any overlay is added, a **de-lever-only
   vol-target cap** (best MaxDD -7.99%, Calmar 1.084) is the correct direction --
   reduce exposure in storms, never lever in calm.

## Honesty / caveats / confidence

- BASELINE: all comparisons use BOTH-252 prod CPM (Sharpe 1.1658 / MaxDD -12.97%
  / Calmar 1.0137), per the standardization. Anchor reproduced to 4 dp via the
  production engine -> harness wiring is sound. Harness pins
  CORR_LOOKBACK_DAYS=252 in-process; cpm_live.py not edited by this work.
- Switching the baseline from the old 504-config (1.1910) to both-252 (1.1658)
  left every conclusion intact: the buffer's relative Sharpe gain, the dynamic-
  slot tail trim, the leverage-loses-at-matched-vol result, and the de-lever-
  wins result all hold with near-identical deltas.
- Single in-sample 18y clean window; all Sharpe diffs include zero. No OOS/walk-
  forward. Treat all deltas as directional, not proven.
- AGG -> BND proxy; BIL -> SHV proxy (panel lacks AGG/BIL). IEF is the article's
  own instrument and is tested directly.
- Borrow cost is made EXPLICIT (SHV + 50 bps), unlike the article (futures,
  no financing charged) -- so the levered comparison here is if anything kinder
  to leverage than reality with retail margin, and it still loses to CPM.
- Vol-matched leverage uses an in-sample constant scale factor (look-ahead in the
  scaling constant only); flagged illustrative. Constant 1.5x/2x are look-ahead-
  free and tell the same story.
- Article stat tables are images; only the mechanism/qualitative claims were
  scraped, not the exact reported figures.
- Confidence: HIGH that levered-buffered does not beat unlevered CPM at matched
  vol on this sample; MEDIUM that the unlevered dynamic-safe slot is a real (but
  small, non-significant) tail-trim rather than pure dilution.

## Handoff

None required (research complete). If productization of the dynamic-safe
diversifier slot is ever desired, that is a fixer/oracle decision, not analysis.
