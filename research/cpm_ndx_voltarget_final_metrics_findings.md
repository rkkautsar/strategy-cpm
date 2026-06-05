# NDX top-5 slot vol-target: expanding-QQQ synthesis + comprehensive risk-adjusted reframe

Analyst run. Research-only (no prod / voltarget / memo edits, no commit). Scope-reduced
per request: POINT-ESTIMATES only -- paired block bootstrap and walk-forward SKIPPED
for speed; compelling cells flagged for later confirm.

Scripts (new, research only):
- research/cpm_ndx_voltarget_expandqqq_harness.py  (QQQ_EXPAND mode + `_index_expanding_vol`)
- research/cpm_ndx_voltarget_expandqqq_run.py       (comprehensive table runner)
- research/cpm_ndx_voltarget_expandqqq_findings.json (full numeric dump)

Engine: UNMODIFIED ndx_sleeve_live.run_ndx_backtest (gate / safe rotation / T+1 MOO /
10bps / delist / PIT membership). Every de-risk config shares the IDENTICAL top-5 SLOT
discrete drop-lowest-momentum mechanism (n = round(scale*5)); only the TARGET feeding
`scale` differs. Clean window 2008-05-30..end; ext/stress window 1999+.

Data caveat: QQQ from cpm_panel (cached, ETF adj close 1999-03+, NDX index-level proxy
pre-1999). Frozen dataset; absolute levels may differ marginally from a prod refresh.
Apples-to-apples across configs. PIT/delist applied. Single in-sample pass; mult/windows
A-PRIORI {1.0, 1.25, 1.5, 2.0} and short {20, 60}d, NOT optimized. HIGH overfit caution.

## Metric definitions (all annualized unless noted)

- Sharpe  = annualized excess-of-cash Sharpe (perf_metrics).
- Sortino = mean*252 / (downside_dev*sqrt(252)); downside_dev = sqrt(mean(min(r,0)^2)), threshold 0.
- CVaR_ratio = mean*252 / |mean(worst 5% daily returns)|  (annualized Expected-Shortfall ratio).
- Calmar  = CAGR / |MaxDD|.
- Martin  = CAGR / Ulcer; Ulcer = sqrt(mean(drawdown^2)) over the full daily drawdown path.
- MaxDD   = peak-to-trough worst drawdown (path-dependent, single trough).

## Comprehensive risk-adjusted table (CLEAN window 2008+)

QEXP = expanding-window QQQ vol target: target = m * qqq_expand_vol, where qqq_expand_vol
is the mean of completed-month QQQ realized vol from inception to t-1. scale =
min(1, target / basket_RV_short). 2021DD = full-year-2021 MaxDD.

```
config            Sh    Sort  CVaR  Cal   Mar   MaxDD% CAGR% vol%  mExp  TO   slot  2021DD%
NONE(prod)        1.281 1.962 8.40  1.002 4.233 -31.4  31.4  23.6  1.000 5.16 0.00  -31.4
FIXED_t25_w60     1.311 2.019 8.78  1.144 4.270 -22.4  25.6  18.8  0.839 4.98 1.77  -20.0
FIXED_t30_w60     1.262 1.922 8.30  0.948 3.667 -27.8  26.4  20.2  0.901 5.11 1.65  -22.8
ADAPT_w60         1.302 1.998 8.59  0.981 4.352 -31.4  30.8  22.6  0.965 5.10 1.12  -31.4
EXPAND_w60        1.265 1.922 8.25  0.933 3.888 -31.4  29.3  22.3  0.971 5.13 0.53  -31.4
QQQL_m10_w60      1.280 1.987 8.61  0.922 3.576 -26.1  24.1  18.2  0.732 4.52 3.13  -26.1
QQQR_w60          1.263 1.926 8.26  0.968 4.026 -31.4  30.4  23.2  0.978 5.13 0.89  -31.4
QEXP_m100_w60     1.296 1.990 8.62  1.127 4.184 -22.4  25.2  18.7  0.833 5.03 1.83  -20.0
QEXP_m125_w60     1.263 1.921 8.29  0.950 3.637 -27.8  26.5  20.3  0.901 5.09 1.48  -22.8
QEXP_m150_w60     1.294 1.974 8.50  0.981 4.045 -29.6  29.0  21.5  0.943 5.12 0.77  -26.1
QEXP_m200_w60     1.280 1.956 8.40  0.975 4.065 -31.4  30.6  23.0  0.982 5.16 0.47  -31.4
QEXP_m100_w20     1.286 1.980 8.59  1.059 3.847 -24.1  25.5  19.2  0.861 5.22 2.48  -23.5
QEXP_m125_w20     1.279 1.957 8.42  0.940 3.859 -29.3  27.6  20.8  0.921 5.26 1.36  -26.1
QEXP_m150_w20     1.313 2.014 8.65  0.960 4.154 -31.4  30.1  21.9  0.952 5.28 1.42  -31.4
QEXP_m200_w20     1.294 1.983 8.50  0.996 4.212 -31.4  31.3  23.1  0.987 5.21 0.47  -31.4
```

## Per-crisis MaxDD (ext/stress window 1999+)

```
config            dotcom  GFC   COVID  Y2022  Y2025
NONE(prod)        -12.1  -9.1  -4.7   -0.3   -4.8
FIXED_t25_w60     -12.1 -10.5  -4.7   -0.3   -4.4
QEXP_m100_w60     -12.1 -10.5  -4.7   -0.3   -4.4
QEXP_m125_w60     -12.1  -9.5  -4.7   -0.3   -4.4
QQQL_m10_w60      -12.1  -9.5  -4.7   -0.3   -4.4
```

CONFIRMS the settled finding: the gate covers V-shaped crises, so per-crisis MaxDDs are
near-identical across ALL configs. The entire clean-window MaxDD spread (-31.4 vs -22.4)
comes from ONE non-gated episode: the 2021 idiosyncratic growth-unwind.

2021 unwind (2021-02-12..05-13) MaxDD / cum:
```
NONE         -31.4 / -28.2     QEXP_m100_w60 -19.6 / -17.3
FIXED_t25    -19.6 / -17.3     QEXP_m125_w60 -22.4 / -18.6
FIXED_t30    -22.4 / -18.6     QQQL_m10_w60  -26.1 / -21.6
```

## (a) Expanding-QQQ verdict: YES it recovers 2021 protection, parameter-light

The hypothesis is CONFIRMED. Expanding-QQQ at m=1.0 reproduces the fixed-0.25 winner almost
exactly: Sharpe 1.296 vs 1.311, Calmar 1.127 vs 1.144, Martin 4.184 vs 4.270, MaxDD -22.4
vs -22.4, 2021 unwind -19.6 vs -19.6, mean exposure 0.833 vs 0.839.

WHY it works (2021 exposure / target path, QEXP m=1.0 w60):
```
date        rv_short  qexp   tgt   scale  n  exp
2020-09-30   0.558    0.237  0.237 0.425  2  0.40   <- COVID-era basket blowout: cut to n=2
2021-01-29   0.468    0.237  0.237 0.506  3  0.60   <- unwind onset: de-risk to n=3
2021-02-26   0.404    0.237  0.237 0.587  3  0.60
2021-03-31   0.438    0.237  0.237 0.541  3  0.60
2021-05-28   0.406    0.237  0.237 0.584  3  0.60
2021-07-30   0.276    0.236  0.236 0.858  4  0.80   <- calm returns: re-risk to n=4
2021-08-31   0.263    0.236  0.236 0.896  4  0.80
```

KEY MECHANISM: qqq_expand_vol is a quasi-CONSTANT ~0.237 -- a ~20yr expanding mean barely
moves, so a single 2020 crash year does NOT inflate it (contamination-free, unlike the
trailing-252d QQQ_LEVEL which stayed elevated through 2021 and only reached -26.1).
Effectively, the expanding window REDISCOVERS the fixed-0.25 constant from QQQ's own
history -- 0.237 emerges, it is not hand-picked. This is the synthesis: external (below
basket vol) + expanding (contamination-free) + the constant target that was the only thing
that ever worked, now parameter-light.

CONDITIONAL, not chronic-drag: mean exposure 0.833 (essentially identical to fixed-0.25's
0.839, far above QQQL_m10's chronic-drag 0.732). It cuts to n=3 during the 2021 unwind
(basket vol 0.40-0.47) and re-risks to n=4-5 in calm 2021-H2 (basket vol 0.26-0.28). The
feared chronic drag (target 0.237 << basket "structural" 0.45) did NOT materialize, because
basket vol in calm regimes drops to ~0.20-0.26 and scale -> 1; the 0.45 figure is a
stress-inclusive average, not the calm-regime level.

m maps the conditional-vs-drag frontier cleanly (m=1.0 ~ fixed-0.25; m=1.25 ~ fixed-0.30;
m=2.0 ~ prod no-protection). m=1.25 fills the gap: MaxDD -27.8, 2021 -22.8, mExp 0.901 --
identical to fixed-0.30. So the grid is monotone and well-behaved; no m beats m=1.0 on
Calmar.

Does any m match/beat fixed-0.25 on Calmar/Martin while parameter-light? YES: m=1.0 matches
it on both (Calmar 1.127 vs 1.144; Martin 4.184 vs 4.270) and is the parameter-light
equivalent. Higher m monotonically degrades protection toward prod.

## (b) Metrics reframe: does FIXED-0.25 genuinely improve, or is it a 1:1 dial?

FIXED-0.25 vs PROD(NONE), clean window:
```
metric       PROD    FIXED25   delta      pct
Calmar       1.002 -> 1.144    +0.143    +14.3%   <- GENUINE improvement
CVaR_ratio   8.404 -> 8.783    +0.379    +4.5%    <- genuine (worst-day tail)
Sortino      1.962 -> 2.019    +0.057    +2.9%    <- genuine (modest)
Sharpe       1.281 -> 1.311    +0.030    +2.3%    <- genuine (modest)
Martin       4.233 -> 4.270    +0.037    +0.9%    <- FLAT (1:1 dial)
MaxDD       -0.314 -> -0.224   +0.090   +28.7%    (single-trough)
CAGR         0.314 -> 0.256    -0.058   -18.6%    (return given up)
```

ANSWER: it is BOTH, depending on the metric.
- On Calmar it GENUINELY improves: MaxDD is cut 28.7% while CAGR is cut only 18.6%, so the
  DD-adjusted return ratio rises ~14%. NOT a 1:1 risk-for-return trade on this metric.
- On CVaR/Sortino/Sharpe it modestly genuinely improves (+2-5%): the worst-day tail and
  downside-day quality get slightly better, not just rescaled.
- On Martin (Ulcer) it is essentially FLAT (+0.9%) = a 1:1 dial. The integrated drawdown
  PATH quality is unchanged; only the single worst trough (2021) is trimmed.

Reconciliation: Calmar divides by the SINGLE worst trough (the 2021 unwind), which the
overlay specifically cuts -> Calmar jumps. Martin divides by Ulcer, which integrates the
ENTIRE 18yr drawdown path; trimming one episode while paying continuous small de-risk drag
elsewhere leaves Ulcer ~unchanged -> Martin flat. So the benefit is CONCENTRATED in one
episode + the worst-day tail, not spread across the drawdown path.

QEXP_m100 vs PROD is the same story (Calmar +12.6%, CVaR +5.x%, Martin -1.1%).

## (c) Does metric choice flip the ranking? YES.

- MaxDD / Calmar view: FIXED-0.25 and QEXP-m1.0 are the clear winners (Calmar 1.14, MaxDD
  -22.4); prod and ADAPT/EXPAND/QQQR look worst (Calmar ~0.93-1.00, MaxDD -31.4).
- Martin (Ulcer) view: ADAPT_w60 (Martin 4.352) TOPS the entire field -- including
  FIXED-0.25 (4.270) and prod (4.233) -- despite having ZERO 2021 protection (MaxDD -31.4).
  And FIXED-0.30 (Martin 3.667) ranks near-WORST despite cutting MaxDD to -27.8.

So a config that looks BAD on MaxDD (ADAPT, -31.4) looks BEST on Martin, and vice versa.
The MaxDD-led presentation and a Martin/Ulcer-led presentation genuinely disagree. This is
exactly the reporting gap the reframe was meant to expose: leading with MaxDD overstates the
overlay's broad-path benefit.

## (d) Final recommendation

TARGET SPEC: two equivalent best specs -- FIXED-0.25 (incumbent) and QEXP-m1.0 (expanding-QQQ,
NEW). They are numerically near-identical. PREFER QEXP-m1.0 on robustness grounds: its
target (~0.237) EMERGES from QQQ's own 20yr expanding mean rather than a hand-picked
constant, removing one discretionary degree of freedom while delivering the same Calmar,
Martin, CVaR, MaxDD, and 2021 protection. It is the parameter-light winner the search was
looking for. (If a fixed constant is operationally simpler, FIXED-0.25 is interchangeable.)
Avoid m>=1.5 and the trailing-252d QQQ_LEVEL (contaminated, weaker).

IS THE OVERLAY WORTH ADOPTING AT ALL? Qualified yes, with eyes open:
- It is NOT pure frontier-sliding: Calmar (+14%), CVaR (+4.5%), Sortino (+3%), Sharpe (+2%)
  all genuinely improve vs prod. So on single-worst-trough and worst-day-tail risk-adjusted
  return, it is a real improvement.
- BUT the benefit is CONCENTRATED in the one 2021 unwind episode + the worst-day tail; on
  the integrated drawdown path (Martin/Ulcer) it is flat, and it gives up ~19% of CAGR.
- Therefore: adopt if the mandate values protecting the single worst idiosyncratic-unwind
  trough and worst-day tail (Calmar/CVaR/Sortino). Do NOT adopt expecting broad
  drawdown-path improvement (Martin) or higher CAGR -- on those, prod (or ADAPT) is as good
  or better.

## Significance / confirm later (bootstrap + WF SKIPPED this run)

The compelling deltas worth a paired block bootstrap (B=2000, block=21, seed=42) + 3-seg
walk-forward LATER:
1. FIXED-0.25 (or equivalently QEXP-m1.0) vs PROD on Calmar / CVaR / Sortino -- to test
   whether the +14% Calmar and +4.5% CVaR are significant or path/sampling noise. (Prior
   runs showed the Sharpe delta only MARGINAL, so the Calmar/CVaR significance is the open
   question.)
2. QEXP-m1.0 vs FIXED-0.25 is NOT worth bootstrapping -- the configs are near-identical
   (all deltas ~0), so the contrast would be noise by construction; treat them as
   equivalent.

Caveats: single in-sample pass; m/windows a-priori not optimized but still DoF; absolute
levels subject to the cached-QQQ caveat; MaxDD/Calmar CIs are inherently soft/path-dependent
(another reason the Martin-flat finding matters); no out-of-sample confirmation in this run.
