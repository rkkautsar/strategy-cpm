# TIP-proxy robustness: IEF+CPI synthetic (X) vs plain IEF (Y)

Read-only adversarial check mirroring AllocateSmartly's "plain IEF for all
pre-2003 TIPS" robustness test. Does the pre-cutover TIP-proxy construction
matter for HAA-Simple (paper window) and CPM-extended? Both legs stitch to the
SAME real TIP after cutover, so any delta is driven only by the pre-cutover
canary signal.

## Constructions (everything else identical)

- **(X) IEF+CPI synthetic** = nominal intermediate Treasury total return
  (GS10 par-bond TR, N=7, in Part A; panel IEF in Part B) PLUS realized monthly
  CPI inflation (FRED CPIAUCSL). This is our convention's pre-1997 proxy.
- **(Y) plain IEF** = nominal intermediate Treasury total return only,
  inflation-blind (the AllocateSmartly adversarial proxy).

Cutover to real TIP:
- Part A (monthly FRED/Shiller): real TIP = VIPSX monthly TR from 2000-07
  (VIPSX inception 2000-06-29; no tradeable TIPS fund exists in 1997, so the
  synthetic necessarily runs to 2000-06).
- Part B (daily prod panel): real TIP = prod `tip_stitched` (VIPSX, 2000-06+).
  In the prod panel TIP is NaN for 1999-03..2000-05; we inject X or Y over those
  month-ends only. Post-2000-06 both use the identical real series.

Harness: mooex T+1 MOO exact, 10 bps/side, monthly signal. NO prod files
touched, NO commit.

## Part A -- HAA-Simple, paper window 1970-12 .. 2022-12 (625 months)

Faithful HAA-Simple: risk-on iff TIP-13612U > 0 AND SPY-13612U > 0 -> SPY;
else best-of({IEF, T-bill cash}) by 13612U. SPY = Shiller S&P 500 TR;
IEF = GS10 par-bond TR; cash = TB3MS.

| metric | (X) IEF+CPI | (Y) plain IEF | delta X-Y |
|--------|-------------|---------------|-----------|
| Sharpe | 0.8751 | 0.9277 | **-0.0526** |
| Calmar | 0.6636 | 0.6758 | -0.0122 |
| MaxDD  | -18.92% | -18.92% | 0.00 |
| CAGR   | 12.55% | 12.78% | -0.23% |

- Holdings differ in only **25 of 625 months (4.0%)**.
- MaxDD is **identical** -- the divergent months never touch the global
  drawdown path.
- Note the direction: the rigorous IEF+CPI proxy (X) scores marginally LOWER
  Sharpe than plain IEF (Y). In the late-70s/early-80s the CPI accrual pushed
  synthetic TIP-13612U positive, keeping HAA risk-on in equities through the
  1981 equity weakness; the inflation-blind proxy went defensive and did
  slightly better. The effect is small either way.

### Where the difference concentrates (additive monthly-return gap by year)

| year | X-Y gap | note |
|------|---------|------|
| 1981 | -0.1829 | high-inflation stagflation -- dominant |
| 1999 | -0.0723 | secondary |
| 1987 | +0.0434 | crash year blip |
| 1995 | +0.0334 | |
| 1980 | +0.0311 | high inflation |
| 2000 | +0.0290 | |
| 1979 | +0.0230 | high inflation |

Hold-differs months cluster in **1979-11 .. 1981-09** (16 of 25), exactly the
high-inflation period AllocateSmartly flagged, with minor blips in 1987,
1994-96, 1999-2000. No divergence anywhere in the post-2000 real-TIP era.

## Part B -- CPM extended (canary HYG-OR-TIP), daily panel

CPM canary is HYG OR TIP (any-positive). TIP is canary-only (never held), so the
override only affects the canary decision in 1999-03..2000-05.

EXT (1999-03-10 .. 2026-05-22):

| metric | (X) IEF+CPI | (Y) plain IEF | delta X-Y |
|--------|-------------|---------------|-----------|
| Sharpe | 1.2158 | 1.2058 | +0.0100 |
| Calmar | 0.8653 | 0.8564 | +0.0089 |
| MaxDD  | -15.93% | -15.93% | 0.00 |

CLEAN (2008-05-30 .. 2026-05-22):

| metric | (X) IEF+CPI | (Y) plain IEF | delta X-Y |
|--------|-------------|---------------|-----------|
| Sharpe | **1.1910** | **1.1910** | 0.0000 |
| Calmar | 1.0615 | 1.0615 | 0.0000 |
| MaxDD  | -12.67% | -12.67% | 0.0000 |

- **Clean anchor 1.1910 confirmed and UNAFFECTED** -- X and Y are bit-identical
  in the clean window (TIP is real post-2000-06; the clean window starts 2008).
- Series differ on only **23 days, all in 1999-08-02 .. 1999-09-01** -- and only
  because HYG canary was negative there, letting the TIP override matter. CPM
  extended cannot reach the 1970s, so it never sees the high-inflation effect.

## Verdict: MINIMAL (confirms paper / AllocateSmartly robustness)

The IEF+CPI-vs-plain-IEF TIP-proxy choice is **MINIMAL**, not material, for both
HAA and CPM-extended.

- **Max delta: HAA-Simple Sharpe -0.0526 (X worse than Y), concentrated in the
  1979-1981 high-inflation period** (year 1981 dominates, additive gap -0.18).
  MaxDD delta is exactly 0.
- CPM-extended delta is +0.010 Sharpe, confined to 23 days in Aug-Sep 1999;
  CPM clean (the headline 1.1910) is exactly unaffected.

This matches the paper's own adversarial finding and AllocateSmartly's "very
little impact beyond the late-70s/early-80s." Plain IEF would have sufficed for
the headline numbers; our IEF+CPI rigor is defensible but does not change any
material metric -- and in HAA-Simple it marginally LOWERS Sharpe by keeping the
strategy risk-on through 1981. The rigor matters only as a faithfulness choice
in the 1979-1981 window, not as a performance driver.

## Reproduce

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
.venv/bin/python research/cpm_tip_proxy_compare.py
```

Inputs: research/data_1970s/fred_{CPIAUCSL,GS10,TB3MS}.csv,
research/data_1970s/shiller_sp500_monthly.csv,
research/_macro_cache/VIPSX_tr.csv, prod daily panel via cpm_live.load_panel.
Outputs: research/cpm_tip_proxy_compare_findings.{md,json}.

## Caveats

- Part A is a monthly synthetic backtest (Shiller S&P TR, GS10 par-bond TR,
  TB3MS cash); it is HAA-Simple faithful but not the ETF-era daily harness.
  It is the only way to reach the 1970-2022 paper window.
- Part A cutover is 2000-07 (first tradeable TIPS fund), not literally 1997;
  1997-2000 has no tradeable TIPS, so the synthetic legitimately extends there.
  This does not affect the verdict (all divergence is pre-2000 and concentrated
  in 1979-1981).
- Part B injects synthetic TIP only at 1999-2000 month-ends (prod panel has TIP
  NaN there); the prod panel does not actually carry a pre-2000 TIP series, so
  Part B measures X vs Y on the 15-month stub, not vs current prod behavior.
- 13612U / Faber / inverse-vol engine logic is unchanged from prod (cpm_live).
