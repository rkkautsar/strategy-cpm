# CPM headline number set -- definitive

Role: analyst (hypothesis-driven, read-only re production; NO production/memo files changed; NO commit). Throwaway harness `research/cpm_headline_gaps_compute.py`; remaining numbers pulled from existing `research/*.json` / findings as cited.

CPM = production `cpm_live.compute_target_weights` (IV4 single-stage: vol-Faber rank / top-K=4 / positive-trend screen / inverse-vol-weight-all-positives / strict-4 partial-safe; canary HYG-OR-TIP, unchanged; timed SHV/IEF safe; cov lookback 504d).

**Convention (every number):** mooex T+1 MOO exact (real yfinance auto_adjust opens), 10 bps/side, monthly month-end signal. Clean window 2008-05-30..2026-05 (18y, full real-open coverage, decisive lens); extended 1999-03-10..2026-05 (27y, partially proxy-backed pre-2006). Martin = CAGR / Ulcer index; Ulcer = sqrt(mean(dd_pct^2)) over the daily equity curve.

## 0. Anchor gate (CONFIRMED)

| Window | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| clean | 1.19098 | -12.67% | 1.0615 | 1.1910 / -12.67% / 1.0615 | CONFIRMED (exact) |
| ext | 1.2142 | -15.93% | 0.8608 | (see note) | reproduced |

Fresh mooex rebuild reproduces the CPM clean anchor **exactly** (Sharpe 1.19098 -> 1.1910, MaxDD -12.665% -> -12.67%, Calmar 1.0615310). Everything below is trusted on that basis. MOO real-open coverage: 245 real rebalance days / 81 proxy fallback (proxy all in the pre-2006 ext tail).

> **Ext note (within-noise harness split):** the validated mooex builder gives ext **1.2142 / -15.93% / 0.8608** (this also equals the EXT anchor cited across all `cpm_factorial_iv4*` gate files). The `cpm_iv4_final_numbers` harness reports ext **1.2161 / -15.93% / 0.8654** (CAGR 13.78%). The two differ ONLY in the proxy-backed pre-2006 tail; clean is byte-identical. Lead with the validated-build ext (1.2142) and treat the gap as a within-noise proxy-tail harness difference. Clean is the decisive lens and is unambiguous.

## 1. Headline

### 1.1 Clean (18y) -- decisive, fully real-open

| Metric | Value |
|---|---:|
| Sharpe | 1.1910 |
| CAGR | 13.44% |
| Vol | 11.16% |
| MaxDD | -12.67% |
| Calmar | 1.0615 |
| Martin (CAGR / Ulcer) | 3.9646 |
| Ulcer index | 3.39% |
| Excess-Sharpe vs SHV | 1.0719 |

### 1.2 Extended (27y) -- partially proxy-backed

| Metric | Value (validated build) | cpm_iv4_final variant |
|---|---:|---:|
| Sharpe | 1.2142 | 1.2161 |
| CAGR | 13.71% | 13.78% |
| Vol | 11.09% | 11.13% |
| MaxDD | -15.93% | -15.93% |
| Calmar | 0.8608 | 0.8654 |
| Martin (CAGR / Ulcer) | 3.8201 | 3.8409 |
| Ulcer index | 3.59% | 3.59% |
| Excess-Sharpe vs SHV | 1.0062 | 1.0062 |

Sources: clean Sharpe/MaxDD/Calmar/CAGR/Vol = fresh mooex rebuild (anchor-confirmed) == `cpm_iv4_final_numbers_findings.md` Sec 1.1. Martin/Ulcer clean (3.9646 / 3.39%) == `four_scheme_metrics_martin_findings.md`. Excess-Sharpe vs SHV: clean 1.0719 (`memo_fix_numbers.json`), ext 1.0062 (`memo_na_fills_findings.json`).

## 2. Crisis drawdowns (CPM equity curve, NOT a blend)

### 2.1 Global drawdown episodes (peak-to-trough + recovery), fresh compute

| Crisis | Peak | Trough | Depth | Peak->trough | Recovery | Trough->recovery |
|---|---|---|---:|---:|---|---:|
| GFC | 2008-03-14 | 2008-10-14 | -11.88% | 214d | 2008-12-16 | +63d |
| COVID | 2020-03-06 | 2020-03-18 | -10.06% | 12d | 2020-04-15 | +28d |
| 2022 | 2021-11-24 | 2022-01-27 | -7.64% | 64d | 2022-03-08 | +40d |

Global episodes = deepest CPM drawdown whose trough falls in the crisis window, detected on the continuous ext equity curve (depth >= 4%). All three fully recovered within ~1-9 weeks of the trough -- CPM's defensive rotation makes its crisis drawdowns shallow and fast-healing.

### 2.2 Within-calendar-window MaxDD (complementary framing, re-cited)

From `cpm_iv4_final_numbers_findings.md` Sec 2 (MaxDD measured inside each calendar window):

| Crisis window | CPM MaxDD | CPM return |
|---|---:|---:|
| GFC (2007-10..2009-06) | -11.88% | 9.86% |
| COVID (2020-02..2020-06) | -10.06% | 8.00% |
| 2022 bear (2022-01..2022-12) | -6.33% | -0.50% |

GFC and COVID match the global-episode depth exactly. The 2022 figure differs by framing: the global episode troughs early (Jan-2022, -7.64%) and recovers by Mar-2022, while the within-calendar-2022 MaxDD is the shallower -6.33% -- both confirm CPM was notably resilient through 2022. (Dot-com, for reference: CPM within-window MaxDD -6.03%, return 28.44%.)

## 3. Bootstrap 95% CI -- CPM clean Sharpe

Stationary block bootstrap, B=2000, block=21, seed=42 (fresh compute).

| Statistic | Value |
|---|---:|
| point | 1.1910 |
| 2.5% (low) | 0.7866 |
| 50% (median) | 1.1964 |
| 97.5% (high) | 1.5969 |

CI = **[0.7866, 1.1964, 1.5969]** (low / median / high). Low and high reproduce `cpm_iv4_final_numbers_findings.md` Sec 3 [0.7866, 1.5969] exactly; the median (1.1964) is the newly filled value. Note: a "paired" block bootstrap applies only to a difference of two series; for a single-series Sharpe CI this is the standard (un-paired) stationary block bootstrap with the same block/seed protocol used across the research set.

## 4. Turnover and fully-safe months

Re-cited from `cpm_vol_gate_test_findings.md` Sec 3 (V0 NONE = production CPM, no vol gate). One-way turnover = 0.5 * sum|dw| / yr (signal-level; realized 10 bps/side cost already embedded in returns).

| Window | One-way turnover / yr | % months fully de-risked to safe | approx fully-safe month count |
|---|---:|---:|---:|
| clean (217 mo) | 2.616 | 13.4% | ~29 |
| ext (327 mo) | 2.768 | 11.0% | ~36 |

Low-turnover monthly strategy; CPM fully parks in the safe sleeve in ~1 of 8 months.

## 5. Concentration / top-holding (re-cited, unchanged)

From `cpm_iv4_final_numbers_findings.md` Sec 7 -- per-asset contribution share of the 8 risky assets (applied daily weight / total risky daily weight). Re-cited verbatim, NOT recomputed.

| Asset | Clean share | Ext share |
|---|---:|---:|
| SPHQ | 20.9% | 15.6% |
| QQQ | 16.9% | 13.6% |
| GLD | 15.0% | 13.8% |
| EFA | 11.7% | 12.3% |
| TLT | 10.5% | 13.9% |
| VNQ | 9.8% | 12.6% |
| EEM | 8.1% | 9.6% |
| DBC | 7.2% | 8.5% |
| **Total** | 100.0% | 100.0% |

Top holding = SPHQ at 20.9% (clean) / 15.6% (ext); top-3 (SPHQ+QQQ+GLD) = 52.8% clean / 43.0% ext. Diversified, no single-name dominance; concentration figures unchanged from the memo.

## Caveats / confidence

- **High confidence (clean, decisive):** clean headline, Martin/Ulcer, crisis depths, bootstrap CI, turnover, concentration. Clean window has full real-open coverage and the anchor reproduces exactly (1.19098 -> 1.1910).
- **Medium confidence (ext tail):** the ext Sharpe/Calmar/Martin carry a small within-noise harness split (1.2142/0.8608/3.8201 validated-build vs 1.2161/0.8654/3.8409 cpm_iv4_final) confined to the proxy-backed pre-2006 segment (81 of 326 rebal days are close-to-close proxy fallback). MaxDD (-15.93%), Vol (~11.1%), Ulcer (3.59%), and ext excess-Sharpe (1.0062) agree across harnesses.
- Crisis "2022" depends on framing: global episode -7.64% (peak Nov-2021) vs within-calendar-2022 MaxDD -6.33%; both reported.
- All post-cost (10 bps/side), mooex T+1 MOO exact with real auto_adjust opens; CPM has no equity vol gate (gate only affects BULL/blend, out of scope here).
- No BULL/blend numbers computed -- CPM only, per scope.

## Provenance map (each number -> source)

| Number | Source |
|---|---|
| clean Sharpe/MaxDD/Calmar/CAGR/Vol | fresh `cpm_headline_gaps_compute.py` (anchor-confirmed); == cpm_iv4_final Sec 1.1 |
| clean Martin/Ulcer (3.9646 / 3.39%) | four_scheme_metrics_martin; reproduced fresh (3.9646 / 3.39%) |
| ext headline (1.2142 / 13.71% / 11.09% / -15.93% / 0.8608) | fresh mooex rebuild == cpm_factorial_iv4* EXT anchor |
| ext Martin/Ulcer (3.8201 / 3.59%) | fresh; cpm_iv4_final variant 3.8409 / 3.59% noted |
| excess-Sharpe clean 1.0719 / ext 1.0062 | memo_fix_numbers.json / memo_na_fills_findings.json |
| crisis episodes (peak/trough/recovery) | fresh `cpm_headline_gaps_compute.py` |
| crisis within-window MaxDD | cpm_iv4_final_numbers_findings Sec 2 |
| bootstrap CI low/high | cpm_iv4_final Sec 3; median fresh |
| turnover + fully-safe months | cpm_vol_gate_test_findings Sec 3 (V0 NONE) |
| concentration shares | cpm_iv4_final_numbers_findings Sec 7 (re-cited) |
