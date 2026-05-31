# CPM extended-window recompute: move the ext floor 1999-03 -> engine floor 1995-01

Role: analyst (read-only re production; writes research/ only; NO prod/memo
edits; NO commit). Throwaway harness `research/cpm_ext_1995_recompute.py` ->
`research/cpm_ext_1995_recompute.json`.

## Mandate

Move the official CPM extended ("ext") window from the old QQQ-inception
presentation convention floor 1999-03-10 (27y) to the engine's TRUE
reduced-universe data floor and recompute the FULL ext number set there. Keep
the clean window (2008+) anchor bit-exact.

## New ext window (state exactly)

- New ext start / first valid curve date: **1995-01-31** (month-end signal; first
  daily return 1995-01-31).
- Window length: **1995-01-31 .. 2026-05-22 = ~31.3 years** (was 27.2y from
  1999-03-10).
- Panel: production `cpm_live.load_panel(start=1995-01-01)`, proxy floor
  1995-01-04 with QQQ/TLT stitched back to 1993, so the engine has a full ~2y
  warmup before the first 1995 signal.
- Execution: mooex (T+1 MOO exact, real auto_adjust opens where they exist,
  close-to-close fallback pre-ETF), 10 bps/side post-cost, monthly month-end.
- mooex real-open coverage over the full 1995 window: **245 real / 131 fallback**
  rebal days (fallbacks concentrated pre-2006, when most universe ETFs had no
  live opens). CPM sleeve has NO vol gate.
- Engine: `compute_target_weights` already ranks reduced-universe (the `avail`
  filter drops missing/NaN assets), so the curve runs from 1995-01-31 with NO
  change to engine code or convention. VNQ (proxy 1996-05) never bound the start;
  it is just absent from the candidate set in 1995-96 and ranked normally
  thereafter. Proxy availability ladder (first valid in panel): QQQ/TLT 1993-11,
  GLD 1995-01-02, SPHQ/EEM/DBC 1995-01-04, EFA 1996-04-30, VNQ 1996-05-14.

## Anchor gate (all pass)

| Check | Sharpe | MaxDD | Calmar | Status |
|---|---:|---:|---:|---|
| Clean 2008-05-30.. (1995 panel) | 1.1910 | -12.67% | 1.0615 | CONFIRMED (bit-exact) |
| ext-1999 engine check (1999 panel, old warmup) | 1.2142 | -15.93% | 0.8608 | CONFIRMED (bit-exact) |
| Factorial all-ON (111111) clean | 1.1910 | -12.67% | 1.0615 | CONFIRMED |
| Ranker base (vol-Faber) clean Sharpe vs production | 1.190980 | - | - | matches production exactly |

The clean window is unaffected by the ext-floor change (2008+ is fully warmed and
fully live in both panels) -- **clean Sharpe 1.1910 / -12.67% / 1.0615 is
UNCHANGED and must stay exact.** The engine reproduces the old ext-1999 1.2142
exactly on its original (1999-loaded) panel, proving the engine is unchanged;
only the window floor moves.

Warmup note (for the fixer): the old memo ext figure 1.2142 was computed on a
panel loaded from 1999-03-10, i.e. only ~1.25y of pre-signal history (truncated
covariance warmup). On the properly-warmed 1995 panel the SAME ext-1999 window
re-slices to Sharpe 1.2207 / Calmar 0.8634. The new ext-1995 number below
naturally supersedes both; do not re-slice the 1999 window.

## 1. HEADLINE -- new ext (1995-01-31 .. 2026-05-22) + old->new delta map

| Metric | OLD ext (1999-03, 27y) | NEW ext (1995-01, 31y) | Delta |
|---|---:|---:|---:|
| Sharpe | 1.2142 | **1.2643** | +0.0501 |
| CAGR | 13.71% | **14.00%** | +0.29 pp |
| Vol | 11.09% | **10.78%** | -0.31 pp |
| MaxDD | -15.93% | **-15.93%** | ~0 (-15.9286%) |
| Calmar | 0.8608 | **0.8791** | +0.0183 |
| Martin (CAGR/Ulcer) | 3.8201 | **3.9767** | +0.1566 |
| Ulcer | 3.59% | **3.52%** | -0.07 pp |
| Excess-Sharpe (vs SHV) | 1.0062 | **1.0007** | -0.0055 |

The extra 1995-1999 years are net mildly accretive (more risk-on capture in
1995-99 with low incremental drawdown). MaxDD is unchanged because the deepest
running-high drawdown over the ext window is a **2006 proxy-era episode (peak
2006-05-09, trough 2006-06-13, -15.93%)**, which sits inside both the old and new
windows; it is deeper than any live-era drawdown (clean MaxDD -12.67%).

## 2. Crisis table -- continuous ext curve from 1995-01-31

Deepest continuous-curve drawdown episode (running-high based, same basis as the
memo's GFC -11.88%) troughing inside each crisis window, with recovery and live
risky ETF/8 coverage at the window midpoint.

| Crisis | Peak | Trough | Depth | Recovery | Trough->recovery | Live risky/8 |
|---|---|---|---:|---|---:|---|
| LTCM | 1998-07-20 | 1998-09-02 | -9.88% | 1999-03-11 | +190d | 0/8 (all proxy) |
| Dot-com era (2002 dip) | 2002-05-29 | 2002-07-24 | -5.87% | 2002-08-29 | +36d | 1/8 (QQQ only) |
| GFC | 2008-03-14 | 2008-10-14 | -11.88% | 2008-12-16 | +63d | 8/8 (all live) |
| COVID | 2020-03-06 | 2020-03-18 | -10.06% | 2020-04-15 | +28d | 8/8 (all live) |
| 2022 | 2021-11-24 | 2022-01-27 | -7.64% | 2022-03-08 | +40d | 8/8 (all live) |

Notes:
- **Dot-com labelling:** CPM SIDESTEPPED the 2000 Nasdaq crash (the defensive
  momentum + canary stack rotated out of equities through 2000-2002). The -5.87%
  is the deepest in-window dip and it peaks/troughs in mid-2002, NOT the
  2000 bubble-burst peak-to-trough. Present as "deepest 2000-2002 in-window
  drawdown / capital-preservation win", not "dot-com crash drawdown".
- **Proxy caveat (LTCM, dot-com):** these episodes are 0/8 and 1/8 live; they
  characterize the proxy panel construction, not live ETF execution. GFC and
  later are essentially live. LTCM is reliably measurable (running peak 1998-07-20
  sits ~3.5y after the 1995-01-31 curve start, fully observed, not lead-in
  truncated).

## 3. Factorial 2^6 decomposition -- new ext column (memo Section 6)

Harness: `cpm_factorial_faithful_aaa` cell fn (faithful AAA all-OFF baseline; the
exact memo Section-6 source). all-OFF (000000) = faithful AAA; all-ON (111111) =
production CPM. Factor order C,U,R,S,W,P. CLEAN ladder reproduces the memo
exactly (baseline 0.7869 -> all-ON 1.1910); the EXT column below is recomputed
over 1995-01.

Baseline 000000 and all-ON 111111, new ext (1995-01):

| Cell | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | Ulcer | Excess-Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline (AAA) 000000 | 0.9040 | 8.41% | 9.38% | -23.21% | 0.3626 | 1.4654 | 5.74% | 0.5955 |
| all-ON (production CPM) 111111 | 1.2643 | 14.00% | 10.78% | -15.93% | 0.8791 | 3.9767 | 3.52% | 1.0007 |

Main effects (background-averaged, on-minus-off):

| Factor | CLEAN dSharpe | CLEAN dCalmar | NEW EXT dSharpe | NEW EXT dCalmar |
|---|---:|---:|---:|---:|
| Ranker (R) | +0.2048 | +0.2411 | +0.1110 | +0.1481 |
| Canary (C) | +0.1104 | +0.2172 | +0.0728 | +0.1790 |
| Universe (U) | +0.0837 | +0.0657 | +0.0824 | +0.0148 |
| Screen (S) | -0.0228 | +0.0463 | -0.0178 | +0.0346 |
| Weighting (W) | +0.0127 | +0.0646 | +0.1054 | +0.1217 |
| Partial-safe (P) | +0.0482 | +0.0886 | +0.0282 | +0.0730 |

Key two-way interactions (Calmar):

| Interaction | CLEAN dCalmar | NEW EXT dCalmar |
|---|---:|---:|
| U x R | +0.1392 | +0.1012 |
| S x P | +0.0886 | +0.0752 |
| C x R | +0.0832 | +0.0497 |
| R x S | +0.0570 | +0.0367 |
| R x W | -0.0134 | -0.0045 |
| S x W | -0.0165 | +0.0033 |

Contribution ladder (dependency order R -> C -> U -> W -> S -> P), new ext:

| Step | Config (C,U,R,S,W,P) | EXT Sharpe | EXT Calmar | EXT MaxDD |
|---|---|---:|---:|---:|
| Baseline (AAA) | 000000 | 0.9040 | 0.3626 | -23.21% |
| +R | 001000 | 0.9645 | 0.3591 | -23.54% |
| +C | 101000 | 1.0479 | 0.6347 | -13.90% |
| +U | 111000 | 1.1707 | 0.6929 | -17.52% |
| +W | 111010 | 1.2405 | 0.8887 | -15.93% |
| +S | 111110 | 1.2533 | 0.9069 | -15.93% |
| +P (all-ON production CPM) | 111111 | 1.2643 | 0.8791 | -15.93% |

Ladder is non-monotone in Calmar (+R dips 0.3626 -> 0.3591; +P dips 0.9069 ->
0.8791), same qualitative pattern as the old ext column. W is a notably stronger
driver over the longer 1995 window (EXT dSharpe +0.1054 vs clean +0.0127),
reflecting more low-correlation diversification value in the pre-2008 proxy era.

## 4. Ranker ext lift + paired CI (over 1995)

Vol-adjusted Faber minus plain 12-month momentum (all else at production spec;
base reproduces production clean Sharpe exactly). Paired stationary block
bootstrap, B=2000, block=21, seed=42.

| Window | vol-Faber Sharpe | plain-12m Sharpe | Lift | P(base beats) | 95% CI |
|---|---:|---:|---:|---:|---|
| Clean (memo cross-check) | 1.1910 | 0.9916 | +0.1994 | 95.3% | [-0.0275, +0.4480] |
| ext-1999 (old) | (re-slice) | - | +0.1545 | 95.0% | [-0.0319, +0.3407] |
| **NEW ext-1995** | - | - | **+0.1488** | **94.7%** | **[-0.0270, +0.3275]** |

The clean lift +0.1994 with CI [-0.0275, +0.4480] reproduces the memo exactly.
The NEW ext lift is +0.1488 (CI [-0.0270, +0.3275]), slightly below the old ext
+0.1542/+0.1545; the directional signal (P~95%) is unchanged and the CI still
spans zero (consistent with the memo's "directional, not significant" read).

## 5. Turnover and fully-safe months

| Window | One-way turnover / yr | Fully-safe months |
|---|---:|---:|
| Clean | 2.616 | 13.4% (29/217) |
| ext-1999 (old) | 2.769 | 11.0% (36/327) |
| **NEW ext-1995** | **2.733** | **10.1% (38/377)** |

Convention: one-way = 0.5 * sum|dw| per rebal, annualized (matches
`cpm_vol_gate_test`). Fully-safe = months with zero risky weight. The 1995 window
adds 50 risk-on-heavy 1995-99 months, so fully-safe % ticks down from 11.0% to
10.1% and turnover eases slightly from 2.769 to 2.733.

## 6. Concentration -- per-asset share of risky weight (new ext)

| Asset | NEW ext-1995 share | ext-1999 share | Clean share |
|---|---:|---:|---:|
| SPHQ | 16.4% | 15.6% | 20.9% |
| TLT | 15.5% | 13.9% | 10.5% |
| QQQ | 13.7% | 13.4% | 16.9% |
| VNQ | 12.6% | 12.6% | 9.8% |
| GLD | 12.3% | 13.9% | 15.0% |
| EFA | 11.6% | 12.4% | 11.7% |
| EEM | 9.5% | 9.5% | 8.1% |
| DBC | 8.5% | 8.7% | 7.2% |

- **Top holding (new ext): SPHQ 16.4%.**
- **Top-3 share (new ext): 45.5%** (SPHQ + TLT + QQQ).

The new ext is less concentrated than clean (top-3 45.5% vs 52.8% clean) -- the
longer proxy era spreads weight more evenly, with TLT rising (more bond-heavy
risk-on baskets in 1995-2007).

## 7. Bootstrap 95% CI on ext Sharpe (paired block, B=2000, block=21, seed=42)

| Window | Point | 2.5% | Median | 97.5% |
|---|---:|---:|---:|---:|
| Clean (memo anchor) | 1.1910 | 0.7866 | 1.1964 | 1.5969 |
| **NEW ext-1995** | **1.2643** | **0.9430** | **1.2619** | **1.5986** |

The longer ext sample tightens the lower bound (0.9430 vs clean 0.7866) and keeps
the CI comfortably above zero.

## 8. Proxy coverage summary (for the ext caveat)

Live risky ETF / 8 over time (inception <= year-end):

| Era | Live risky/8 | Notes |
|---|---:|---|
| 1995-1998 | 0/8 | fully proxy (QQQ<-^NDX, treasuries<-Vanguard funds, GLD<-World Bank gold, SPHQ/EEM/DBC proxy) |
| 1999-2000 | 1/8 | QQQ ETF (1999-03) |
| 2001 | 2/8 | + EFA (2001-08) |
| 2002 | 3/8 | + TLT (2002-07) |
| 2003 | 4/8 | + EEM (2003-04) |
| 2004 | 6/8 | + VNQ (2004-09), GLD (2004-11) |
| 2005 | 7/8 | + SPHQ (2005-12) |
| 2006-2026 | 8/8 | + DBC (2006-02); fully live |

Canary/safe: HYG<-VWEHX pre-2007-04, TIP live 2003-12 (panel TIP from 2000-06),
SHV/IEF<-Vanguard funds pre-live. The pre-1999 ext history (1995-98) is fully
proxy-backed; the clean window (2008+) is fully live. The 1995-2007 segment of
the ext window mixes proxy and partial-live coverage; treat the ext headline as a
proxy-informed robustness lens, with the clean window as the decisive live lens.

## Old -> new swap map (for the fixer; memo numbers to replace)

Section 5.1 ext headline row (Window=Extended):

- Sharpe 1.2142 -> 1.2643
- CAGR 13.71% -> 14.00%
- Vol 11.09% -> 10.78%
- MaxDD -15.93% -> -15.93% (unchanged)
- Calmar 0.8608 -> 0.8791
- Martin 3.8201 -> 3.9767
- Ulcer 3.59% -> 3.52%
- Excess-Sharpe 1.0062 -> 1.0007
- Window label "1999-03-10" -> "1995-01-31"; "27y" -> "~31y".

Section 5.2 crisis table: prepend LTCM (-9.88%, +190d, 0/8) and dot-com-era 2002
dip (-5.87%, +36d, 1/8) above GFC; keep GFC/COVID/2022 as-is. Add the proxy
caveat and the dot-com-sidestep note.

Section 5.4 turnover: ext 2.768 -> 2.733; fully-safe ext 11.0% -> 10.1%.

Section 6 factorial EXT columns: replace with the new ext column above (baseline
0.9040/0.3626/-23.21%; all-ON 1.2643/0.8791/-15.93%; main effects, interactions,
and ladder per Section 3). Clean columns UNCHANGED.

Section 7.1 ranker: ext lift +0.1542 -> +0.1488 (CI [-0.0270, +0.3275]); clean
+0.1994 unchanged. Update Section 5.5 ext start "1999-03-10" -> "1995-01-31"
where CPM is cited; benchmark series starts are benchmark-bound and unchanged.

Section 7.4 concentration ext shares: replace with the new ext column (top
holding SPHQ 16.4%, top-3 45.5%); clean column unchanged.

## Caveats / confidence

- **High confidence on anchors:** clean 1.1910/-12.67%/1.0615 bit-exact; engine
  reproduces old ext-1999 1.2142 bit-exact on its original panel; factorial CLEAN
  ladder and ranker clean lift reproduce the memo exactly. The recompute is the
  same production engine, only the window floor moved.
- **Reduced-universe is engine-native** (verified in the `avail` filter); the
  1995-01-31 floor is real, not a convention. VNQ never bound the start.
- **Proxy caveat:** the 1995-2007 ext segment is proxy / partial-live (0/8 live in
  1995-98). The ext headline gain (+0.05 Sharpe) is real but proxy-informed; the
  clean window remains the decisive live lens.
- **Warmup subtlety:** old ext 1.2142 was on a ~1.25y-warmup (1999-loaded) panel;
  re-slicing ext-1999 on the full-warmup 1995 panel gives 1.2207. The new
  ext-1995 (1.2643) is the correct production-faithful number and supersedes both.
- **mooex pre-ETF fallback:** 131/376 rebal days fall back to close-to-close
  (no real opens pre-ETF), concentrated pre-2006.
- All metrics post-cost (10 bps/side), T+1 MOO exact, no CPM vol gate.

## Handoff

- fixer (owns memo/prod): apply the old->new swap map above. Analyst does not
  edit the memo or production.
