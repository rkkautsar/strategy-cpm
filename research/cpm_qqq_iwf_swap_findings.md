# CPM single-asset swap: QQQ -> IWF (purer growth factor vs Nasdaq-tech index)

Analyst, exploratory. CPM production is UNCHANGED regardless of this result.

## Question

Does swapping QQQ -> IWF in the CPM-8 universe change CPM materially? QQQ
(Nasdaq-100) is a tech/sector-concentrated index that merely behaves
growth-like; IWF (iShares Russell 1000 Growth) is a purer, broader growth
factor with less single-sector concentration. One swap, full metrics, vs
current CPM. Not a grid search.

## Method

- Mechanism: FULL CPM, fixed R1 M1 (vol-adj Faber ranker + raw-Faber positive
  screen, min-var 3-of-4 at n_pos=4, TIP-only canary, top-4, equal-weight,
  breadth-scaled partial-safe, best-of {SHV,IEF} safe). Byte-identical
  `cpm_mech_wf` reused from `cpm_mech_2swap_univ_2026_06_02.py`.
- Universe parametric: only QQQ -> IWF differs; SPHQ, EFA, EEM, VNQ, GLD, TLT,
  DBC held constant.
- Convention mooex (T+1 MOO), 10 bps/side, both-252 lookbacks.
- Script: `research/cpm_qqq_iwf_swap_2026_06_02.py`
  (JSON: `research/cpm_qqq_iwf_swap_2026_06_02.json`).
- Command: `.venv/bin/python research/cpm_qqq_iwf_swap_2026_06_02.py`

GATE PASSED: current CPM-8 reproduces 1.255673 (actual 1.2556733).

## Data / IWF availability

- IWF absent from frozen panel. Fetched live via yfinance auto_adjust (same
  adjusted-close convention as the stitched panel) for the close panel, plus
  OHLC into /tmp/cpm_open_cache for exact mooex rebal-day economics.
- IWF inception in panel = 2000-05-26 (iShares Russell 1000 Growth, ~2000).
  CLEAN window (2008-05-30+) fully covered. EXT window (1999-03-10 start) has a
  ~14-month pre-inception gap where IWF is simply unselectable; the mechanism
  handles missing assets (falls to other risky assets / safe). PIT caveat.

## Full-metrics table (point-estimates)

CLEAN (2008-05-30 .. 2026-05-22)

| metric    |   CPM-8 QQQ |  CPM-8 IWF |    delta |
|-----------|------------:|-----------:|---------:|
| Sharpe    |      1.2557 |     1.2123 |  -0.0434 |
| Sortino   |      1.8058 |     1.7430 |  -0.0628 |
| CVaR95rat |      8.2295 |     7.9573 |  -0.2722 |
| Calmar    |      1.0076 |     0.9506 |  -0.0570 |
| Martin    |      4.2571 |     3.7662 |  -0.4909 |
| MaxDD %   |    -13.0317 |   -13.0317 |   0.0000 |
| CAGR %    |     13.1314 |    12.3880 |  -0.7434 |
| Vol %     |     10.2753 |    10.0822 |  -0.1931 |
| Turnover  |      7.0833 |     7.1481 |  +0.0648 |

EXT (1999-03-10 .. 2026-05-22; IWF gap pre-2000-05)

| metric    |   CPM-8 QQQ |  CPM-8 IWF |    delta |
|-----------|------------:|-----------:|---------:|
| Sharpe    |      1.2549 |     1.2387 |  -0.0162 |
| Sortino   |      1.8114 |     1.7895 |  -0.0219 |
| CVaR95rat |      8.2770 |     8.1848 |  -0.0922 |
| Calmar    |      0.9712 |     0.8708 |  -0.1004 |
| Martin    |      4.1168 |     3.8123 |  -0.3045 |
| MaxDD %   |    -13.1414 |   -14.1396 |  -0.9982 |
| CAGR %    |     12.7628 |    12.3125 |  -0.4503 |
| Vol %     |      9.9683 |     9.7591 |  -0.2092 |
| Turnover  |      6.8037 |     6.8650 |  +0.0613 |

## QQQ vs IWF correlation (daily returns)

- CLEAN: Pearson 0.9729 (4524 overlap days)
- EXT:   Pearson 0.9188 (6538 overlap days)

As expected, very high (~0.92-0.97). IWF and QQQ are near-substitutes for the
growth slot.

## Selection divergence (effect size) -- CLEAN, 217 monthly rebals

- Held basket differs (QQQ/IWF treated as same "growth slot"): 20 / 217 = 9.2%
- QQQ held: 63/217 (29.0%); IWF held: 61/217 (28.1%)
- QQQ picked when IWF would NOT be: 10 rebals
- IWF picked when QQQ would NOT be: 8 rebals
- Mean L1 weight distance (growth slot mapped same): 0.063

So the growth slot is selected at a near-identical rate (~28-29%), and the two
universes diverge on the held basket only ~9% of months. When they diverge it
is roughly symmetric (10 vs 8), i.e. neither is systematically more "selectable"
under the vol-adj ranker.

## Verdict

(a) Material change? NO. QQQ -> IWF is a small, consistently NEGATIVE nudge.
    CLEAN Sharpe -0.043 (1.2557 -> 1.2123), CAGR -0.74pp, all risk-adjusted
    ratios (Sortino, CVaR, Calmar, Martin) slightly worse. CLEAN MaxDD
    identical (the worst drawdown comes from a safe/non-growth state). EXT
    direction agrees (Sharpe -0.016) but EXT MaxDD is ~1pp WORSE for IWF and is
    confounded by the pre-2000 inception gap.

(b) Direction. IWF loses some tech-beta return that QQQ carried -- lower CAGR
    in both windows (-0.74pp CLEAN, -0.45pp EXT) at marginally lower vol. There
    is NO diversification/drawdown payoff for the "purer/broader growth": CLEAN
    MaxDD is unchanged and EXT MaxDD is worse. So the cleaner growth factor
    gives up return without buying tail/DD protection here.

(c) Correlation ~0.92-0.97; baskets diverge only ~9% of months and the growth
    slot is held at ~28-29% either way. Effect size is small and the swap is
    near-neutral by construction (high substitute).

CONCLUSION: QQQ's concentrated Nasdaq-tech beta is mildly ACCRETIVE to CPM vs
the purer Russell-1000-Growth factor -- not a problem to "clean up". The swap
is a small net negative with no risk offset. Keep QQQ. Strictly exploratory;
single swap on a single in-sample window -> HIGH overfit caution, the ~0.04
Sharpe gap is well within noise and should not be over-read.

## Caveats / confidence

- Point-estimates only (bootstrap skipped per scope); the ~0.04 CLEAN Sharpe
  gap is small relative to typical CPM bootstrap CIs -> treat as directional,
  not decisive.
- Single swap, single in-sample window: HIGH overfit caution.
- IWF live-fetched (yfinance auto_adjust); inception 2000-05-26 -> EXT
  pre-2000 gap makes EXT IWF a partial/optimistic-survivor compare; trust CLEAN
  more.
- CPM production UNCHANGED. Confidence: MEDIUM that the direction (QQQ slightly
  better) is real; LOW that the magnitude is meaningful.
