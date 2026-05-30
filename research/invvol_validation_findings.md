# Inverse-vol weighting validation gauntlet: INVVOL-2 / INVVOL-3 vs production EW-2

Hypothesis under test: the inverse-vol drawdown/Calmar advantage over the
production EW 50/50 min-var pair (EW-2) is a genuine, statistically-robust AND
persistent upgrade, NOT an in-sample / single-episode artifact.

Verdict (up front): NOT robust and NOT persistent. No paired-bootstrap
confidence interval excludes zero on any metric, in either window, for either
challenger. The headline clean MaxDD improvement (EW-2 -16.35% -> INVVOL-2
-13.14%) is almost entirely one episode (GFC). Recommendation: keep EW-2
pending true out-of-sample evidence. This is the same "directional-but-
within-noise" character that sank continuous-vs-pair.

## Config / window / execution / method

- Sleeve: CPM, U=R=C=1, cov lookback 504d, K=4 top-half, mooex (T+1 MOO exact),
  10 bps/side. Universe QQQ/SPHQ/EFA/EEM/VNQ/GLD/TLT/DBC; safe SHV/IEF; canary HYG/TIP.
- Schemes (selection IDENTICAL; weighting differs only):
  - EW2  = production 50/50 min-var pair.
  - IV2  = INVVOL-2: 2 lowest-variance names, w_i proportional to 1/sigma_i.
  - IV3  = INVVOL-3: 3 lowest-variance names, inverse-vol.
  - CONT = continuous min-var (reference).
- Windows: CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22).
- Part 1 method: PAIRED stationary block bootstrap, B=2000, block=21d, seed=42.
  Same resampled block index applied to BOTH series each iteration (variants of
  the same selection, daily corr 0.91-0.99, so paired is mandatory). Diff =
  challenger - baseline; >0 => challenger wins. For MaxDD, less-negative = better,
  so positive diff = shallower drawdown. Naive independent bootstrap reported
  only as contrast.
- Part 2 method: trailing 12m (252d) and 36m (756d) rolling windows, monthly
  step; per-regime MaxDD over fixed episode dates. Win fraction = share of
  windows with diff > 0.
- Scripts: research/invvol_validation.py -> research/invvol_validation.json
  (built on research/inverse_vol_weighting.py returns_for + cpm_live perf_metrics).
- Reproduce: `.venv/bin/python research/invvol_validation.py`

## Anchor verification (full-sample point metrics, 10 bps) -- ALL OK

CLEAN: EW2 1.2424 / -16.35% / 0.8704 ; IV2 1.2630 / -13.14% / 1.0945 ;
IV3 1.2453 / -13.19% / 1.0824 ; CONT 1.2935 / -15.15% / 0.9618.
EXT: EW2 1.2159 / -16.76% / 0.8396 ; IV2 1.2011 / -15.44% / 0.8874 ;
IV3 1.2249 / -15.18% / 0.9148 ; CONT 1.2091 / -15.15% / 0.8760.
(format = Sharpe / MaxDD / Calmar). All four scheme anchors reproduced exactly
before bootstrapping.

## PART 1 -- Paired block bootstrap (B=2000, block=21, seed=42)

P = P(challenger beats baseline). CI = 95% paired diff interval. "excl0" = CI
excludes zero (statistically robust). Diff = challenger - baseline.

### CLEAN 18y

| Pair | metric | P | diff mean | 95% CI (paired) | excl0 |
|------|--------|------|-----------|------------------|-------|
| INVVOL-2 vs EW-2 | Sharpe | 0.714 | +0.0208 | [-0.0492, +0.0994] | NO |
| INVVOL-2 vs EW-2 | MaxDD  | 0.586 | +0.0045 | [-0.0239, +0.0367] | NO |
| INVVOL-2 vs EW-2 | Calmar | 0.638 | +0.0326 | [-0.1405, +0.2330] | NO |
| INVVOL-3 vs EW-2 | Sharpe | 0.501 | +0.0013 | [-0.1819, +0.1834] | NO |
| INVVOL-3 vs EW-2 | MaxDD  | 0.562 | +0.0023 | [-0.0489, +0.0510] | NO |
| INVVOL-3 vs EW-2 | Calmar | 0.553 | +0.0182 | [-0.3047, +0.3585] | NO |
| INVVOL-2 vs continuous | Sharpe | 0.288 | -0.0300 | [-0.1460, +0.0775] | NO |
| INVVOL-2 vs continuous | MaxDD  | 0.432 | -0.0016 | [-0.0380, +0.0344] | NO |
| INVVOL-2 vs continuous | Calmar | 0.409 | -0.0258 | [-0.2882, +0.2204] | NO |
| INVVOL-3 vs continuous | Sharpe | 0.292 | -0.0495 | [-0.2192, +0.1159] | NO |
| INVVOL-3 vs continuous | MaxDD  | 0.456 | -0.0038 | [-0.0551, +0.0434] | NO |
| INVVOL-3 vs continuous | Calmar | 0.406 | -0.0402 | [-0.3955, +0.2979] | NO |

### EXT 27y

| Pair | metric | P | diff mean | 95% CI (paired) | excl0 |
|------|--------|------|-----------|------------------|-------|
| INVVOL-2 vs EW-2 | Sharpe | 0.298 | -0.0142 | [-0.0672, +0.0441] | NO |
| INVVOL-2 vs EW-2 | MaxDD  | 0.554 | +0.0023 | [-0.0252, +0.0317] | NO |
| INVVOL-2 vs EW-2 | Calmar | 0.414 | -0.0115 | [-0.1352, +0.1174] | NO |
| INVVOL-3 vs EW-2 | Sharpe | 0.567 | +0.0108 | [-0.1299, +0.1476] | NO |
| INVVOL-3 vs EW-2 | MaxDD  | 0.555 | +0.0032 | [-0.0518, +0.0604] | NO |
| INVVOL-3 vs EW-2 | Calmar | 0.509 | +0.0044 | [-0.2561, +0.2706] | NO |
| INVVOL-2 vs continuous | Sharpe | 0.445 | -0.0083 | [-0.1161, +0.1034] | NO |
| INVVOL-2 vs continuous | MaxDD  | 0.427 | -0.0036 | [-0.0457, +0.0384] | NO |
| INVVOL-2 vs continuous | Calmar | 0.543 | +0.0079 | [-0.1822, +0.2191] | NO |
| INVVOL-3 vs continuous | Sharpe | 0.586 | +0.0167 | [-0.1223, +0.1545] | NO |
| INVVOL-3 vs continuous | MaxDD  | 0.460 | -0.0027 | [-0.0578, +0.0472] | NO |
| INVVOL-3 vs continuous | Calmar | 0.585 | +0.0239 | [-0.2193, +0.2844] | NO |

Key reading:
- Drawdown/Calmar edge over EW-2 is NOT statistically robust. Best case is
  CLEAN INVVOL-2: MaxDD P=0.586, Calmar P=0.638 -- directional but far below the
  0.95 robustness bar, and both CIs straddle zero. EXT is even weaker (Calmar
  P=0.414 for IV2, i.e. it loses more often than wins over the full 27y).
- This is exactly the "directional-but-within-noise" pattern seen in
  continuous-vs-pair (paired_bootstrap_pair_vs_continuous): point estimate
  favours the challenger, paired CI cannot reject zero.
- Pairing matters and was applied correctly: paired CIs are ~7-10x tighter than
  naive (e.g. CLEAN IV2 Calmar paired [-0.14,+0.23] vs naive [-0.76,+0.80]),
  and STILL fail to exclude zero. Naive would have been even less conclusive.
- Inverse-vol does NOT beat continuous either; on CLEAN it is generally behind
  continuous on Sharpe (P=0.288/0.292), consistent with continuous being the
  point-estimate Sharpe leader.

## PART 2 -- Rolling / sub-period persistence

Win fraction = share of monthly-stepped rolling windows where challenger beats
EW-2 (diff > 0). Coin-flip = 0.50.

| window | scheme | n | win MaxDD | win Calmar | mean dMaxDD (pp) | median dMaxDD (pp) |
|--------|--------|---|-----------|------------|------------------|--------------------|
| CLEAN 12m | IV2 | 205 | 0.54 | 0.45 | +0.04 | +0.02 |
| CLEAN 36m | IV2 | 181 | 0.38 | 0.39 | +0.10 | -0.01 |
| CLEAN 12m | IV3 | 205 | 0.55 | 0.50 | +0.04 | +0.22 |
| CLEAN 36m | IV3 | 181 | 0.54 | 0.56 | -0.04 | +0.22 |
| EXT 12m | IV2 | 316 | 0.56 | 0.41 | +0.20 | +0.02 |
| EXT 36m | IV2 | 292 | 0.51 | 0.39 | +0.44 | +0.02 |
| EXT 12m | IV3 | 316 | 0.59 | 0.49 | +0.26 | +0.32 |
| EXT 36m | IV3 | 292 | 0.65 | 0.60 | +0.35 | +0.44 |

(pp = percentage points of MaxDD; positive = inverse-vol shallower.)

Reading:
- MaxDD win fractions hover near coin-flip (0.38-0.65). IV2 36m CLEAN is
  actually 0.38 (loses more rolling windows than it wins). Median dMaxDD is
  ~0.00-0.02pp for IV2 -- i.e. in a typical window the two are indistinguishable;
  the positive MEAN is dragged up by a few large-shave windows (mean >> median).
- Calmar persistence is weak: IV2 wins Calmar in only 0.39-0.45 of windows on
  EXT and CLEAN-36m. Inverse-vol's higher full-sample Calmar is a point-estimate
  effect (lower denominator from one episode), not a per-window habit.
- IV3 36m EXT is the single best persistence cell (win MaxDD 0.65, win Calmar
  0.60) -- because IV3's drawdown benefit shows up in >1 episode (see below).
  But it is still nowhere near a dominant, all-regime edge.

### Episodes driving the MaxDD improvement

The clean-window MaxDD of EW-2 (-16.35% / -16.76% EXT) IS the GFC drawdown. The
headline improvement is that single episode:

- 36m windows whose trailing period contains GFC show dMaxDD = +4.02pp for IV2
  (chal -12.74% vs base -16.76%) and +4.10pp for IV3 (-12.66% vs -16.76%). The
  improvement is constant across every window-asof from 2009-06 through ~2010-10,
  because the same GFC trough sits inside the trailing 36m -- it is ONE episode,
  re-counted, not many independent wins.
- IV3 has a SECOND, smaller episode: 2015-2016 selloff, base -11.05% -> chal
  -7.63% (+3.42pp). This is why IV3 persistence beats IV2.
- Counter-episodes exist where EW-2 wins: ~2011 (IV2 dMaxDD -2.78pp) and
  2014-2016 (IV3 dMaxDD -2.81pp) -- inverse-vol DEEPENED the drawdown there.

### Per-regime MaxDD (EW-2 vs INVVOL-2 vs INVVOL-3 vs continuous)

| regime | EW-2 | INVVOL-2 | INVVOL-3 | continuous |
|--------|------|----------|----------|------------|
| dot-com (2000-2002) | -8.44% | -7.56% | -7.49% | -6.42% |
| GFC (2007-2009) | -16.76% | -12.74% | -13.54% | -15.15% |
| COVID (2020) | -13.12% | -13.14% | -12.09% | -12.31% |
| 2022 bear | -9.60% | -9.24% | -9.24% | -8.75% |

Reading:
- GFC is the whole story: ~4pp shave for both inverse-vol variants. Every other
  regime is a wash (<=1pp) or, for COVID/IV2, marginally WORSE (-13.14% vs
  -13.12%). Continuous actually beats inverse-vol in 3 of 4 regimes (dot-com,
  COVID, 2022) but loses badly in GFC.
- The inverse-vol drawdown benefit is concentrated, regime-specific (a 2008-style
  bond/credit-led crash where down-weighting the higher-vol equity leg paid off),
  not a broad-based, all-weather improvement.

## VERDICT

1. Is the INVVOL-2 / INVVOL-3 MaxDD/Calmar edge over EW-2 statistically robust
   AND persistent? NO on both counts.
   - Robust: no paired CI excludes zero; best P is 0.638 (CLEAN IV2 Calmar), far
     below 0.95. Within-noise, same as continuous-vs-pair.
   - Persistent: rolling MaxDD win fractions 0.38-0.65 (coin-flip), median
     per-window dMaxDD ~0; Calmar win fractions often < 0.50. The full-sample
     improvement is one episode (GFC), re-counted across overlapping windows.

2. INVVOL-2 vs INVVOL-3 -- better upgrade candidate?
   - INVVOL-2: minimal change (same 2 names as production), best CLEAN
     point-estimate (Sharpe 1.2630, Calmar 1.0945), best single-stat
     significance (CLEAN Calmar P=0.638). BUT its edge is purely GFC-driven, it
     is slightly worse in COVID, its EXT Calmar P drops to 0.414 (loses over
     27y), and its rolling Calmar win is only ~0.40.
   - INVVOL-3: best EXT metrics (Sharpe 1.2249, Calmar 0.9148), best persistence
     (36m EXT win MaxDD 0.65 / Calmar 0.60), and a 2nd drawdown episode
     (2015-16). BUT more complex (3 names), worse CLEAN point estimate than IV2,
     and still no significance anywhere.
   - On significance + persistence + OOS-confidence, INVVOL-3 is the marginally
     stronger evidence case (broader drawdown benefit, better EXT). On
     simplicity + minimal-change, INVVOL-2 wins. Neither clears the decision bar,
     so the tie-break is moot.

3. Honest call: KEEP EW-2 pending true out-of-sample evidence. Neither
   inverse-vol variant is a defensible production upgrade on the drawdown
   objective. The apparent win is an in-sample point estimate driven by a single
   regime (GFC); the paired bootstrap cannot distinguish it from noise and
   rolling persistence is coin-flip. Switching weighting now would be selecting
   on the one episode that happened to favour inverse-vol. If a future genuine
   OOS bear (bond/credit-led, GFC-like) materializes, INVVOL-3 is the variant to
   re-evaluate first, because its drawdown benefit is the least episode-concentrated.

## Caveats and confidence

- High confidence in the negative result: anchors reproduce exactly; paired
  bootstrap is the correct, conservative test for these highly-correlated
  variants (corr 0.91-0.99); result is unambiguous (no CI near excluding zero).
- Overlapping rolling windows inflate apparent persistence of the GFC shave;
  treated qualitatively (episode attribution), not as independent samples.
- Regime windows are fixed calendar boxes; CLEAN MaxDD captures GFC from its
  2008-05-30 start, so CLEAN headline and GFC regime numbers are the same event.
- Single data vintage / single execution convention (mooex, 10 bps). Not a
  walk-forward re-selection test: selection (lowest-variance subset) is held
  fixed; this validates the WEIGHTING choice given selection, not joint search.
- Read-only re production; no production files changed, no commit.

Durable lesson: validate a weighting-scheme "upgrade" with a PAIRED bootstrap on
the correlated variant series plus rolling/per-regime persistence -- not an
aggregate point estimate. A full-sample MaxDD/Calmar gap that collapses to a
within-noise paired CI and a coin-flip rolling win rate is an in-sample,
episode-driven artifact, not an edge.
