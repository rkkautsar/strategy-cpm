# CPM Extended-Window Crisis Drawdowns (LTCM / Dot-com / GFC) + Proxy Coverage

Analyst research. Read-only re production. Writes research/ only. No prod/memo
edits. No commit. Feeds an honest extended crisis table + proxy caveat for the
memo (section 5.2).

Convention: mooex (T+1 MOO exact), 10 bps/side, monthly. Production CPM engine
(`cpm_live.compute_target_weights`) via the mooex harness
(`research/exec_lag_moo_validation_2026_05_30.py`,
`research/cpm_benchmarks_proper.py`). Reproduce: `.venv/bin/python
research/cpm_ext_crises.py` -> `research/cpm_ext_crises.json`.

Anchors held: production GFC continuous-curve drawdown -11.88% (peak 2008-03-14,
trough 2008-10-14, recovery 2008-12-16, +63d) reproduced exactly.

## Verdict (up front)

1. **Extended crisis table (production-proxy continuous curve, running-high
   based, same basis as the memo's GFC -11.88%):**

   | Crisis  | Peak       | Trough     | Depth   | Recovery   | Trough->recovery | Proxy (risky live/8) |
   |---------|------------|------------|--------:|------------|-----------------:|----------------------|
   | LTCM    | 1998-07-20 | 1998-09-02 |  -9.88% | 1999-03-11 |            +190d | 0/8 (all proxy)      |
   | Dot-com | 2002-05-29 | 2002-07-24 |  -5.87% | 2002-08-29 |             +36d | 1/8 (QQQ only)       |
   | GFC     | 2008-03-14 | 2008-10-14 | -11.88% | 2008-12-16 |             +63d | 8/8 (all live)       |

   (COVID -10.06% and 2022 -7.64% already in the memo; unchanged.)

2. **VNQ is NOT a legitimate floor-binder.** The production engine already
   operates reduced-universe: `compute_target_weights` ranks only assets that
   pass the faber + price-presence `avail` filter, so missing assets are simply
   excluded -- exactly the Adaptive-AA "drop N->N-1" behavior. VNQ binds only the
   artificial "all-8-present" convention (1996-05-14); dropping VNQ moves that to
   EFA 1996-04-30 (two weeks), and dropping VNQ+EFA moves it to the proxy-file
   floor 1995-01-04. The CURVE's real data floor is 1995-01 regardless of VNQ.
   VNQ is, however, an OFTEN-held asset (in the top-4 in 47.8% of risk-on
   months), so it stays in the strategy -- it just never bound the start.

3. **LTCM is reliably measurable -- the ~1998 truncation fear was based on a
   wrong premise.** The premise that the curve starts ~1998-05 assumed VNQ's
   504d covariance warmup binds the start. It does not: the reduced-universe
   engine produces real ranked baskets from ~1995-10 (>=4 risky assets) on the
   production proxy panel. LTCM's running peak (1998-07-20) sits **1266 days
   (~3.5y) after the curve start (1995-01-31)** -- fully observed, not lead-in
   truncated. Depth -9.88% is robust.

4. **The pragmatic SPY/VEIEX extension to 1994 changes NOTHING in the crisis
   table.** Pushing the floor to 1994-01 (US-equity sleeve <- ^GSPC, EEM <-
   VEIEX real EM fund 1994-05, SPHQ <- ^GSPC crude quality) lengthens LTCM
   lead-in 1266d -> 1631d but yields IDENTICAL depths/dates/recovery for all
   three crises (LTCM -9.88%, dot-com -5.87%, GFC -11.88%). The running peak
   entering each crisis is local (within ~1y), so it is already captured by the
   production-proxy curve. The extension is a robustness confirmation, not a
   requirement -- recommend NOT adopting it (it imports synthetic EM/quality and
   an off-universe SPY substitution for zero crisis-table benefit).

## 1. Crisis drawdowns -- continuous ext curve

Measured running-high based (equity peak carried from curve start), matching the
memo's "Global drawdown episodes" basis where GFC = -11.88%.

Production-proxy reduced-universe curve (from 1995-01-31):

| Crisis  | Peak       | Trough     | Depth   | Recovery   | Peak->trough | Trough->recovery | Lead-in (start->peak) |
|---------|------------|------------|--------:|------------|-------------:|-----------------:|----------------------:|
| LTCM    | 1998-07-20 | 1998-09-02 |  -9.88% | 1999-03-11 |         +44d |            +190d |                 1266d |
| Dot-com | 2002-05-29 | 2002-07-24 |  -5.87% | 2002-08-29 |         +56d |             +36d |                 2675d |
| GFC     | 2008-03-14 | 2008-10-14 | -11.88% | 2008-12-16 |        +214d |             +63d |                 4791d |

Pragmatic SPY/VEIEX extension curve (CPM-LIKE, from 1994-01-31) -- identical
depths/dates, longer lead-in only:

| Crisis  | Peak       | Trough     | Depth   | Recovery   | Lead-in |
|---------|------------|------------|--------:|------------|--------:|
| LTCM    | 1998-07-20 | 1998-09-02 |  -9.88% | 1999-03-11 |   1631d |
| Dot-com | 2002-05-29 | 2002-07-24 |  -5.87% | 2002-08-29 |   3040d |
| GFC     | 2008-03-14 | 2008-10-14 | -11.88% | 2008-12-16 |   5156d |

**Dot-com note (important for honest labelling):** CPM's worst dip in the
2000-03..2002-12 window is a shallow -5.87% episode that peaks/troughs in
mid-2002, NOT the 2000 Nasdaq crash. The defensive-momentum + canary stack
rotated out of equities through 2000-2002, so CPM largely sidestepped the dot-com
collapse; the -5.87% is a mid-2002 wobble inside the calendar window. The figure
is a capital-preservation win, but the "dot-com" label is calendar-window, not a
peak-of-bubble-to-trough measure.

## 2. Proxy coverage per crisis

Risky-8 = QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC. Live = ETF inception <= crisis
window midpoint; else proxy-backed. Inceptions from
`research/cpm_ext_extension_feasibility_findings.md`.

| Crisis  | Window mid | Risky live/8 | Live tickers | Canary/safe live |
|---------|------------|-------------:|--------------|------------------|
| LTCM    | 1998-10-16 |          0/8 | (none)       | none (all proxy) |
| Dot-com | 2001-07-31 |          1/8 | QQQ          | none (all proxy) |
| GFC     | 2008-08-15 |          8/8 | all          | all (HYG/TIP/SHV/IEF) |

- **LTCM (1998): fully proxy-backed.** 0/8 risky ETFs existed (earliest is QQQ,
  1999-03). All risky exposure is proxy (QQQ<-^NDX, treasuries<-Vanguard funds,
  GLD<-World Bank gold, SPHQ/EEM/DBC<-proxy-file synthetics). Canary HYG<-VWEHX,
  safe SHV/IEF<-Vanguard funds. **Describes a proxy-panel strategy, not live
  ETF trading.**
- **Dot-com (2000-02): heavily proxy-backed.** Only QQQ live (from 1999-03);
  7/8 risky + all canary/safe are proxy. Same strong caveat.
- **GFC (2008): essentially live.** 8/8 risky ETFs and all canary/safe ETFs
  trading by 2008. This is why the memo's GFC figure is the credible extended
  anchor and LTCM/dot-com need a proxy caveat.

Asset availability ladder in the production proxy panel (first valid date):

```
QQQ  1993-10-01 (^NDX index proxy; QQQ ETF 1999-03)
TLT  1993-10-01 (VUSTX proxy; TLT ETF 2002-07)   [panel pulls start-2y]
GLD  1995-01-02 (World Bank gold proxy)
SPHQ 1995-01-04 (proxy-file floor)
EEM  1995-01-04 (proxy-file floor)
DBC  1995-01-04 (proxy-file floor)
EFA  1996-04-30 (EAFE-type fund proxy)
VNQ  1996-05-14 (VGSIX proxy)  <- binds ONLY the all-8-present convention
```

Reduced-universe availability (production proxy): >=4 risky assets from
1995-10-31, >=6 from 1995-10-31, >=7 from 1997-01-31, all 8 from 1997-02-28.

## 3. VNQ selection frequency (ext window, 1995-01..2026-05, 377 months)

Share of months each risky asset is in the top-4 risk-on basket (339 risk-on
months):

| Asset | Months in top-4 | % of risk-on | % of all months |
|-------|----------------:|-------------:|----------------:|
| QQQ   |             209 |        61.7% |           55.4% |
| SPHQ  |             196 |        57.8% |           52.0% |
| VNQ   |             162 |        47.8% |           43.0% |
| TLT   |             153 |        45.1% |           40.6% |
| EFA   |             147 |        43.4% |           39.0% |
| EEM   |             147 |        43.4% |           39.0% |
| GLD   |             147 |        43.4% |           39.0% |
| DBC   |             116 |        34.2% |           30.8% |

VNQ is the 3rd most-selected risky asset (held ~48% of risk-on months) -- not a
rarely-held asset. So VNQ cannot be dropped from the strategy. But because the
engine ranks reduced-universe, VNQ's late data (1996-05) never constrains the
curve start: in 1995-1996 VNQ is simply absent from the candidate set, and the
ranker selects among the available assets exactly as it would later in any
VNQ-not-picked month.

## 4. Reduced-universe binding floor

- **All-8-present convention:** binds at VNQ 1996-05-14 (next EFA 1996-04-30).
  This is the only sense in which VNQ "binds" and it is an artificial
  requirement, not engine behavior.
- **Engine-native reduced-universe (what production actually does):** the curve
  data floor is the proxy-file floor 1995-01-04 (GLD/SPHQ/EEM/DBC), with
  QQQ/TLT reaching back further. Robust multi-asset ranking from ~1995-10
  (>=4-6 risky). VNQ/EFA do not bind.
- **Pragmatic extension floor (CPM-LIKE):** ~1994-01 curve start, bound by EEM
  via VEIEX (real Vanguard EM fund, 1994-05) plus 13-month faber warmup; SPHQ
  and the US-equity sleeve extended via ^GSPC. The next binder below that is the
  EM wall (no investable EM fund before VEIEX 1994-05; MSCI EM index 1987-12 is
  non-investable). Adds lead-in only; no crisis-depth change.

## Caveats / confidence

- **High confidence:** GFC -11.88% reproduced exactly; reduced-universe is the
  engine's native behavior (verified in `compute_target_weights` `avail`
  filter); LTCM/dot-com/GFC depths identical across the production-proxy and the
  1994 extension curves; VNQ selection frequency 47.8% of risk-on.
- **Strong proxy caveat (LTCM, dot-com):** these episodes are 0/8 and 1/8 live;
  they characterize the proxy-panel construction, not live ETF execution. The
  mooex convention also has no real opens pre-ETF, so rebal-day returns fall
  back to close-to-close on those dates (production-proxy: 245 real / 131
  fallback rebal days over the full window; fallbacks concentrated pre-2006).
- **Dot-com labelling caveat:** the -5.87% is a mid-2002 in-window dip, not the
  2000 bubble-burst peak-to-trough; CPM went defensive and sidestepped the
  crash. Present as "deepest in-window drawdown", not "dot-com crash drawdown".
- **Extension is CPM-LIKE, not production:** Part B substitutes ^GSPC for the
  US-equity sleeve and uses crude EM/quality proxies pre-1996; it is a
  robustness/context curve only and should not be presented as CPM. Production
  clean (Sharpe 1.1910) and ext (1.2142) headlines are unchanged by this work.
- LTCM depth is running-high based with a 1266d (prod-proxy) / 1631d (extension)
  observed lead-in to the 1998-07-20 peak, so it is NOT lead-in truncated
  (contrast the clean-window GFC -9.83% artifact, which started after the GFC
  peak).

## Recommendation for the memo (analyst input; memo edits owned by the writer)

1. Extend section 5.2's "Global drawdown episodes" table with LTCM (-9.88%) and
   dot-com (-5.87%) ABOVE GFC, on the same continuous-curve basis, with a
   "risky live/8" column or footnote.
2. Add a one-line proxy caveat: "LTCM (0/8) and dot-com (1/8) are proxy-backed
   and describe the extended proxy panel, not live ETF execution; GFC (8/8) and
   later are live." Plus the dot-com mid-2002 labelling note.
3. LTCM is reliable enough to PRESENT (3.5y observed lead-in) provided the proxy
   caveat is attached. Do NOT omit it; do NOT present it without the caveat.
4. Do not adopt the 1994 SPY/VEIEX extension; it adds no crisis-table value and
   imports synthetic history.

## Next handoff

- writer/fixer (owns memo): apply the extended 5.2 crisis table + proxy caveat
  above. Analyst does not edit the memo.
