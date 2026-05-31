# 1970s Stagflation: Do the TREND filter and VOL gate protect equity where the TIP canary did not?

Author: analyst (read-only research). Scope: research/ only. No production/memo edits, no commit.

## Question

The companion test (`stagflation_1970s_tip_canary.py`) showed the synthetic-TIP 13612U
canary does NOT protect a S&P 500 equity sleeve through the real 1973-74 and 1977-82
stagflation drawdowns. This test asks whether the strategies' OTHER defenses do, on the
SAME equity sleeve and SAME harness:

- TREND filter: risk-on iff S&P 500's own 13612U absolute (time-series) momentum > 0.
  This is CPM's positive-trend screen and BULL's SPY trend gate.
- VOL gate: risk-on iff realized-vol(60d) < realized-vol(252d) on S&P 500 daily returns.
- TREND AND VOL: risk-on iff both pass.
- References: buy-and-hold; tip_only (the known failure) for contrast.

All variants: monthly rebalance, signal at end of month t applied to month t+1 (1-month
lag, no lookahead), defensive leg = 3-month T-bill.

## Method

- Script: `research/stagflation_1970s_trend_vol.py` (reuses the companion harness loaders,
  S&P TR reconstruction, 13612U signal, and metrics verbatim via import).
- Run: `python3 research/stagflation_1970s_trend_vol.py`
- Outputs: `research/stagflation_1970s_trend_vol_findings.json` (+ this file).

### Data sources

- S&P 500 monthly TOTAL return: Robert Shiller `ie_data` (datahub mirror), reconstructed
  `TR_t = (P_t - P_{t-1} + D_t/12)/P_{t-1}`. Drives both the equity sleeve return AND the
  TREND 13612U signal. NOTE: Shiller price is a MONTHLY-AVERAGE of daily closes, not a
  month-end close; averaging smooths and can lag turning points.
- S&P 500 DAILY close: Yahoo Finance `^GSPC` daily, 1967-01-03 .. 1985-12-31 (4770 obs),
  cached at `research/data_1970s/gspc_daily.csv`. PRICE-ONLY (no dividends; irrelevant for
  realized vol). Drives ONLY the VOL gate. This is a TRUE daily close, not monthly-average.
- Cash / defensive: FRED TB3MS (3m T-bill), monthly = rate/1200.
- Synthetic TIP (for the known-failure reference only): FRED GS5 par-bond TR + realized
  CPIAUCSL inflation (companion construction).

### Constructions

- TREND signal: `13612U = mean(1,3,6,12-month TR)` of the S&P monthly TR index; computed at
  end of month t, applied to month t+1.
- VOL signal: daily log returns; at each month-end t, `rv_60d = std(last 60)*sqrt(252)` and
  `rv_252d = std(last 252)*sqrt(252)`; `vol_on = rv_60d < rv_252d`; applied to month t+1.
  (annualization cancels in the ratio; kept for readability.)

## Results

### Full period 1968-01 .. 1985-12 (216 months)

| Variant        | CAGR   | MaxDD    | Sharpe | Vol    |
|----------------|--------|----------|--------|--------|
| trend          | 11.54% | -11.90%  | 0.403  | 9.33%  |
| vol            |  7.64% | -21.21%  | 0.023  | 9.23%  |
| trend_and_vol  |  9.09% | -11.90%  | 0.186  | 7.56%  |
| tip_only       |  8.99% | -39.16%  | 0.145  | 12.82% |
| buyhold        |  8.85% | -39.16%  | 0.135  | 12.83% |

The TREND filter cuts full-period MaxDD from -39.16% (buyhold == tip_only) to -11.90% while
RAISING CAGR to 11.54% and nearly tripling Sharpe. The VOL gate alone cuts MaxDD to -21.21%
but at a CAGR cost (7.64%). TIP_only is indistinguishable from buy-and-hold.

### Crash window: 1973-74 bear (1973-01 .. 1974-12)

| Variant        | Total ret | MaxDD    | DD avoided vs buyhold | Sharpe |
|----------------|-----------|----------|-----------------------|--------|
| trend          |  -0.27%   |  -9.22%  | +29.94 pp             | -1.248 |
| vol            | -14.05%   | -21.21%  | +17.95 pp             | -1.326 |
| trend_and_vol  |  +3.27%   |  -6.85%  | +32.31 pp             | -0.988 |
| tip_only       | -38.55%   | -39.16%  |  0.00 pp              | -2.102 |
| buyhold        | -38.55%   | -39.16%  |  0.00 pp              | -2.102 |

This is the decisive episode. Buy-and-hold and TIP_only both lose ~39%. The TREND filter
holds the drawdown to -9.22% (avoids ~30 pp); TREND AND VOL holds it to -6.85% (avoids
~32 pp) and is net POSITIVE through the bear. The VOL gate alone avoids ~18 pp.

### Stagflation window: 1977-82 (1977-01 .. 1982-12)

| Variant        | Total ret | MaxDD    | DD avoided vs buyhold | Sharpe |
|----------------|-----------|----------|-----------------------|--------|
| trend          | +89.18%   | -11.90%  | +1.52 pp              |  0.136 |
| vol            | +35.52%   | -13.31%  | +0.11 pp              | -0.613 |
| trend_and_vol  | +47.24%   | -11.90%  | +1.52 pp              | -0.484 |
| tip_only       | +84.80%   | -13.42%  |  0.00 pp              |  0.101 |
| buyhold        | +80.67%   | -13.42%  |  0.00 pp              |  0.072 |

1977-82 was net a RISING market (buyhold +80.67%); drawdowns were shallow (-13%), so there
was little to protect. TREND still edges buyhold on both return and DD. VOL and TREND AND
VOL underperform on return here (whipsaw cost) while only marginally improving DD. The real
value of the defenses shows up in the deep 1973-74 crash, not the choppy-but-rising 1977-82.

### Timing: did each defense de-risk INTO the declines, or late?

1973-74 bear (equity peak 1973-01, trough 1974-12):

- VOL went defensive at the very peak (applied 1973-01) but WHIPSAWED back risk-on into two
  big down legs: risk-on for 1973-11 (-6.85%), 1974-04/05, and the worst month 1974-07
  (-11.34%). Early but unstable.
- TREND went defensive applied 1973-05 (one quarter after peak) and then stayed defensive
  through almost the entire crash, including the 1973-12 (-6.8%), 1974-07 (-11.34%) and
  1974-09 (-10.01%) legs. Slightly late to flip but stable and correctly positioned.
- TREND AND VOL went defensive applied 1973-01 and held; best-positioned overall.
- TIP_only NEVER went defensive in 1973-74 (0 defensive months in window). It was risk-on
  through the entire 39% drawdown.

1977-82: 1980 mini-crash (1980-03 -8.77%) and 1981-09 (-8.3%) were caught only partially;
both trend and vol whipsawed in this choppy regime (e.g. trend defensive Oct-Dec 1981 then
risk-on for the 1982-01 -4.8% leg). Acceptable because the window had no deep sustained
drawdown to protect.

### Whipsaw / false-positive (defensive months where equity ROSE), full period

| Variant        | Defensive months | Whipsaw FP | FP rate | Down-month capture |
|----------------|------------------|------------|---------|--------------------|
| trend          | 67               | 34         | 50.7%   | 37.9%              |
| vol            | 84               | 51         | 60.7%   | 37.9%              |
| trend_and_vol  | 108              | 63         | 58.3%   | 51.7%              |
| tip_only       | 1                | 0          |  0.0%   |  1.1%              |

All three active defenses carry a high false-positive rate (~50-60% of defensive months the
equity actually rose) -- this is the structural cost of trend/vol overlays and is why they
shave some CAGR in calm/rising regimes. But that cost bought the 1973-74 protection. TIP_only
has ~0 false positives only because it almost never de-risks at all -- it is inert, which is
exactly why it fails to protect.

## Verdict

YES -- the TREND filter (S&P own absolute-momentum 13612U) provides GENUINE 1970s stagflation
equity drawdown protection where the TIP canary did not. In the decisive 1973-74 bear it cut
the drawdown from -39% to -9% (~30 pp avoided) while raising full-period CAGR and Sharpe. The
VOL gate also helps materially (avoids ~18 pp in 1973-74) but is noisier: it whipsaws back
risk-on into several major down legs (including the worst single month, 1974-07 -11.34%) and
costs return in 1977-82. Combining them (TREND AND VOL) gives the best raw drawdown (-6.85%
in 1973-74) at some CAGR cost from extra whipsaw.

The real stagflation defense is the ABSOLUTE-MOMENTUM TREND FILTER on the equity sleeve
itself, with the VOL gate as a useful but secondary, noisier complement. The TIP canary was
inert in the 1970s (0-1 defensive months, ~0% down-capture) and provided no protection. The
protective mechanism that matters is "is the asset I hold actually trending down" -- a direct
trend/vol read on equity -- not an indirect inflation-bond canary.

## Caveats and confidence

- TREND signal uses Shiller MONTHLY-AVERAGE S&P price; averaging smooths and can delay trend
  flips vs a month-end close (likely explains TREND's one-quarter lag to flip in 1973). A
  month-end-close trend signal would plausibly flip slightly earlier.
- VOL gate uses Yahoo `^GSPC` DAILY close (price-only). So the TREND and VOL signals run on
  DIFFERENT price series (monthly-average TR index vs true daily close) -- a documented
  mismatch; results are directionally robust but not perfectly apples-to-apples.
- Equity sleeve return = Shiller monthly TR (consistent with companion harness).
- Defensive asset = 3m T-bill; using intermediate Treasuries as the defensive leg would
  change defensive-leg returns (not tested).
- Two stagflation episodes only (1973-74, 1977-82); n is small, so treat magnitudes as
  indicative. The QUALITATIVE conclusion (trend protects, TIP does not) is strong and
  consistent across full-period and the deep-crash window.
- Warmup months with insufficient signal history default to risk-on (no lookahead).

Confidence: HIGH on the qualitative verdict (trend filter is the real 1970s stagflation
equity defense; TIP canary is not). MEDIUM on exact magnitudes (data-construction smoothing,
n=2 episodes).
