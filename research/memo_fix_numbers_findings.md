# Memo EXTENDED-window reconciliation -- single post-tidy harness

Role: analyst (read-only re production; research/ artifacts only; NO production edit, NO commit). Throwaway harness `research/memo_fix_numbers.py`. Reconciles the EXTENDED numbers in `cpm_bull_two_sleeve_memo.md` (mixed pre-tidy 1.2161 / post-tidy 1.2142) onto a SINGLE canonical post-tidy harness so a fixer can correct the memo. The CLEAN column is unaffected and already correct.

**Canonical spec (post-tidy):** post-tidy IV4 single-stage top-4 inverse-vol strict-4 partial-safe = current production `cpm_live.compute_target_weights`. All rows: CPM & BULL on T+1 MOO exact (`mooex`, real auto_adjust opens), 10 bps/side post-cost, BULL slow vol gate rv_60d<rv_252d. Windows: clean 2008-05-30..2026-05-22; ext 1999-03-10..2026-05-22. cov/sigma lookback 504d, top-K=4.

**Replication self-check:** the variant CPM weight fn reproduces production `compute_target_weights` byte-for-byte (max|dw| = 0.0e+00) at every signal date; only the single swapped step (weighting flavor or ranker) differs.

## Anchor gate (abort-on-mismatch)

| Window | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| clean | 1.1910 | -12.67% | 1.0615 | 1.1910 / -12.67% / 1.0615 | CONFIRMED |
| ext | 1.2142 | -15.93% | 0.8608 | 1.2142 / -15.93% / 0.8608 | CONFIRMED |

Both anchors reproduce exactly; everything below is on this harness.

## Item 1 -- Section 8.4 CPM weighting sensitivity (consistent post-tidy)

CPM-solo; weighting flavor varies, selection/ranker/canary/safe held at production. CLEAN is the memo's existing (correct) column; EXT is regenerated on the same harness so the comparison is internally consistent.

| Weighting (CPM) | Clean Sharpe | Clean Calmar | Clean Martin | Clean MaxDD | Ext Sharpe | Ext Calmar | Ext MaxDD |
|---|---:|---:|---:|---:|---:|---:|---:|
| inverse-vol (base) | 1.1910 | 1.0615 | 3.9646 | -12.67% | 1.2142 | 0.8608 | -15.93% |
| ERC | 1.1944 | 1.0602 | 3.9896 | -12.67% | 1.2177 | 0.8611 | -15.93% |
| equal-weight | 1.1317 | 1.0147 | 3.7413 | -13.05% | 1.1868 | 0.8718 | -16.21% |

_Note: the memo lists only inverse-vol / ERC / equal-weight under 8.4 (no continuous weighting row); continuous is N/A here._

- EXT Sharpe ranking: ERC 1.2177 vs inverse-vol 1.2142 vs equal-weight 1.1868.
- EXT Calmar ranking: inverse-vol 0.8608 vs ERC 0.8611 vs equal-weight 0.8718.

**Relative-ranking answer (the reconciliation point).** The memo's pre-tidy 8.4 row showed ERC ext Calmar 0.8647 vs inverse-vol 0.8608 (a 0.0039 ERC edge) and EW 0.8718, making inverse-vol look strictly worst on ext Calmar. Once ERC and EW are recomputed on the SAME post-tidy harness, the spurious ERC edge collapses: ERC ext Calmar falls 0.8647 -> 0.8611, now a dead heat with inverse-vol 0.8608 (delta +0.0003) at IDENTICAL ext MaxDD (-15.93%). Equal-weight keeps the nominally highest ext Calmar (0.8718) but only by carrying a deeper ext MaxDD (-16.21% vs -15.93%) and clearly lower ext Sharpe (1.1868 vs 1.2142). So the ORDER on the Calmar column does not flip (EW > ERC ~ inverse-vol), but the misleading 'ERC beats inverse-vol on ext Calmar' impression is removed -- inverse-vol and ERC are statistically tied on every ext metric, and inverse-vol is tied-best (with ERC) on ext Sharpe, both ahead of EW. Inverse-vol no longer 'looks worst': it is co-best on Sharpe and tied with ERC on Calmar/MaxDD, with EW's Calmar lead bought via worse drawdown and Sharpe.

## Item 2 -- Section 8.3 / 7 ranker lift (vol-Faber minus plain-12m momentum)

CPM-solo Sharpe, post-tidy harness. Lift = base vol-adjusted Faber minus plain 12-month momentum ranker (all else fixed).

| Ranker | Clean Sharpe | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|
| vol-adjusted Faber (base) | 1.1910 | -12.67% | 1.0615 | 1.2142 | -15.93% | 0.8608 |
| plain 12-month momentum | 0.9916 | -16.37% | 0.6983 | 1.0600 | -17.98% | 0.6994 |

- **Clean Sharpe lift = +0.1994** (cross-check vs memo +0.1994).
- **Ext Sharpe lift = +0.1542** (memo currently shows +0.1553 from pre-tidy base; this is the post-tidy replacement).

## Item 3 -- 60/40 CPM-BULL blend, single correct post-tidy values

| Window | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| clean | 1.2485 | 12.74% | 10.05% | -10.68% | 1.1928 |
| ext | 1.2192 | 12.13% | 9.78% | -11.31% | 1.0723 |

- The memo shows both 1.219 and 1.2199 (Calmar 1.07 vs 1.0761) for the EXT blend. Single correct post-tidy EXT value: **Sharpe 1.2192, Calmar 1.0723, MaxDD -11.31%, CAGR 12.13%, Vol 9.78%**.

## Item 4 -- Section 8.8 conservative execution-stress lower bound

All on the post-tidy spec. Headline = T+1 MOO exact (`mooex`). Conservative lower bounds: (a) `moo` conservative MOO (new basket earns intraday only; the favorable overnight close[T]->open[T+1] gap is dropped), (b) `moc1` harsh T+1 MOC (a full extra trading session of lag), and (c) penalized slippage (`mooex` at 25 bps/side, 2.5x the headline cost). Haircut = metric minus the exact-open headline.

### 60/40 blend

| Execution | Window | Sharpe | CAGR | MaxDD | Calmar | Sharpe haircut | Calmar haircut |
|---|---|---:|---:|---:|---:|---:|---:|
| headline | clean | 1.2485 | 12.74% | -10.68% | 1.1928 | +0.0000 | +0.0000 |
| headline | ext | 1.2192 | 12.13% | -11.31% | 1.0723 | +0.0000 | +0.0000 |
| T+1 MOO conservative (intraday only, overnight gap dropped) | clean | 1.0824 | 10.72% | -11.34% | 0.9456 | -0.1661 | -0.2472 |
| T+1 MOO conservative (intraday only, overnight gap dropped) | ext | 1.0825 | 10.49% | -11.34% | 0.9254 | -0.1367 | -0.1469 |
| T+1 MOC harsh (full extra session) | clean | 1.1958 | 12.18% | -10.95% | 1.1128 | -0.0527 | -0.0800 |
| T+1 MOC harsh (full extra session) | ext | 1.1857 | 11.79% | -10.95% | 1.0764 | -0.0335 | +0.0041 |
| mooex headline, 25 bps/side (2.5x slippage penalty) | clean | 1.1714 | 11.88% | -10.83% | 1.0967 | -0.0771 | -0.0961 |
| mooex headline, 25 bps/side (2.5x slippage penalty) | ext | 1.1341 | 11.20% | -11.49% | 0.9745 | -0.0851 | -0.0977 |

### CPM solo

| Execution | Window | Sharpe | CAGR | MaxDD | Calmar | Sharpe haircut | Calmar haircut |
|---|---|---:|---:|---:|---:|---:|---:|
| headline | clean | 1.1910 | 13.44% | -12.67% | 1.0615 | +0.0000 | +0.0000 |
| headline | ext | 1.2142 | 13.71% | -15.93% | 0.8608 | +0.0000 | +0.0000 |
| T+1 MOO conservative (intraday only, overnight gap dropped) | clean | 1.0280 | 11.26% | -13.02% | 0.8646 | -0.1629 | -0.1970 |
| T+1 MOO conservative (intraday only, overnight gap dropped) | ext | 1.0840 | 11.92% | -15.25% | 0.7818 | -0.1302 | -0.0790 |
| T+1 MOC harsh (full extra session) | clean | 1.1515 | 12.96% | -13.26% | 0.9775 | -0.0395 | -0.0840 |
| T+1 MOC harsh (full extra session) | ext | 1.1772 | 13.27% | -15.71% | 0.8448 | -0.0370 | -0.0160 |
| mooex headline, 25 bps/side (2.5x slippage penalty) | clean | 1.1214 | 12.57% | -12.91% | 0.9735 | -0.0696 | -0.0881 |
| mooex headline, 25 bps/side (2.5x slippage penalty) | ext | 1.1401 | 12.78% | -16.05% | 0.7964 | -0.0740 | -0.0644 |

**Conservative lower bound (60/40 blend):** the worst Sharpe across the three stress treatments per window:
- clean: Sharpe 1.0824, CAGR 10.72%, MaxDD -11.34%, Calmar 0.9456 (via `moo`; Sharpe haircut -0.1661 vs exact-open headline 1.2485).
- ext: Sharpe 1.0825, CAGR 10.49%, MaxDD -11.34%, Calmar 0.9254 (via `moo`; Sharpe haircut -0.1367 vs exact-open headline 1.2192).

_The stale 1.165 figure was min-var-3 era and is NOT reused; these are regenerated post-tidy._

## Caveats

- All metrics post-cost 10 bps/side (except the explicit 25 bps penalized-slippage row), T+1 MOO exact unless the execution column states otherwise; production anchors reproduce to 4 decimals and the variant weight fn matches production to 1e-9.
- EXT/stress window (1999-03-10..) is partially proxy-backed pre-2006-2008 for the CPM trend universe; the clean 18y window has full real-open coverage and is the decisive lens.
- Bull leg slippage penalty (25 bps) is applied via bull_qqq_live.COST_BPS_PER_SIDE for the penalized-slippage row only; conventions moo/moc1 keep the 10 bps headline cost and stress ONLY the fill timing.
## Item 5 -- BULL vol-gate cohort + BULL factorial vol-gate effect

### 5a. rv-gate cohort forward-vol confirmation

Source: `research/rv_gate_cohort_calibration_findings.md`. A blocked month = canary_ok AND spy_trend_ok TRUE but vol_ok FALSE. FALSE-POSITIVE (FP) cohort = forward SPY return > 0 (the gains the gate forfeited).

| Window | FP cohort fwd vol (mean) | FP cohort fwd vol (median) | Unconditional fwd vol (mean) | Unconditional fwd vol (median) | TP cohort fwd vol (mean) |
|---|---:|---:|---:|---:|---:|
| Clean (2008-05-30..2026-05-22) | 11.77% | 10.08% | 16.13% | 12.92% | 21.10% |
| Stress (1999-03-10..2026-05-22) | 12.10% | 10.23% | 16.30% | 13.96% | 20.46% |

- **Confirmed exact.** Gemini's cited ~11.8-12.1% vs 16.13% = FP-cohort MEAN forward vol (clean 11.77%, stress 12.10%) vs the CLEAN unconditional MEAN forward vol 16.13%. The FP cohort (66% of blocked months) realizes ~11.8-12.1% forward vol; the TP cohort (34%) realizes ~20.5-21.1% (nearly double), confirming the gate as an asymmetric variance filter.
- **FLAG (convention caveat):** this cohort study defines vol_ok via **RV_20d** >= RV_252d (pre-swap gate). Production now uses the **RV_60d** slow gate (commit 8ff3e22). The forward-vol cohort split has NOT been re-run under RV_60d; the 11.77%/12.10% vs 16.13%/16.30% figures are the RV_20d cohort numbers. Cite them as the rv-gate cohort evidence with this explicit RV_20d-vs-production-RV_60d caveat, or commission a RV_60d re-run if an exact RV_60d cohort split is required.

### 5b. BULL factorial vol-gate main effect and V x S interaction

Source: `research/factorial_decomposition_findings.md` (BULL benchmark->sleeve 2^3 K,V,S factorial; mooex, 10 bps/side, production slow gate RV_60d when V=ON). Re-cited in memo section 12.6.2.

| Effect | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar |
|---|---:|---:|---:|---:|
| Vol gate (V) main effect | +0.081 | +0.089 [FLIP] | +0.006 [FLIP] | +0.027 [FLIP] |
| V x S interaction (Calmar) | n/a | +0.143 | n/a | +0.115 |

- V main-effect heuristic average across listed deltas = +0.051. V x S = **+0.143 CLEAN Calmar, +0.115 EXT Calmar** -- dwarfs every BULL main effect (K x V = -0.036). Reading: BULL is interaction-dominated; the vol gate's value is realized jointly with the {SHV,IEF} safe pool (V sends the sleeve to safe; S decides which safe), so cite V and V x S together, not V as an independent main effect.

