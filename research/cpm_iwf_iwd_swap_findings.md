# CPM US-equity pair swap: QQQ + SPHQ -> IWF + IWD (growth/value style pair)

Analyst, exploratory. CPM production UNCHANGED regardless of result.
Date: 2026-06-02. ASCII only.

## Question / hypothesis

Replace the CPM-8 US-equity pair QQQ + SPHQ (Nasdaq-tech + S&P quality, both
growth/quality-leaning) with IWF + IWD (Russell 1000 Growth + Russell 1000
Value), a cleaner growth/value STYLE pair that spans the style axis, under the
FULL CPM mechanism (R1 M1). One swap (2 tickers), full metrics, vs current CPM-8.

Hypothesis: IWF + IWD are more orthogonal than QQQ + SPHQ, so the pair spans
US-equity styles better and lets the momentum ranker rotate growth<->value with
the regime -> more diversification / better drawdown. Risk: gives up QQQ
concentrated tech-beta and adds IWD value drag during the 2008-2021 growth era.

## Method

- Harness: research/cpm_iwf_iwd_swap_2026_06_02.py (adapted from the byte-identical
  cpm_mech_wf used in cpm_qqq_iwf_swap; CPM R1 M1, universe-parametric).
- Mechanism: vol-adj Faber ranker + raw-Faber screen, min-var 3-of-4 at n_pos=4,
  TIP-only canary, top-4, equal-weight, best-of{SHV,IEF} safe, breadth-scaled
  partial-safe. Convention mooex / T+1 MOO, both-252, 10 bps/side.
- Universes:
  - CPM-8 current = QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC
  - CPM-8 swap    = IWF, IWD,  EFA, EEM, VNQ, GLD, TLT, DBC
- Windows: CLEAN 2008-05-30..2026-05-22 ; EXT 1999-03-10..2026-05-22.
- Data: IWF/IWD fetched live (yfinance auto_adjust, same convention) + OHLC into
  /tmp/cpm_open_cache for exact mooex. Both inception 2000-05-26.
- Run: `.venv/bin/python -m research.cpm_iwf_iwd_swap_2026_06_02`

## Gate (reproduce current CPM-8)

PASS. CPM-8 current CLEAN Sharpe = 1.2556732727 vs anchor 1.255673 (within 5e-4).

## Full metrics table

| cfg | win | Sharpe | Sortino | CVaR95 | Calmar | Martin | MaxDD | CAGR | Vol | Turn |
|-----|-----|--------|---------|--------|--------|--------|-------|------|-----|------|
| CPM8 current      | CLEAN | 1.2557 | 1.8058 | 8.2295 | 1.0076 | 4.2571 | -13.03% | 13.13% | 10.28% | 7.083 |
| CPM8 IWF+IWD swap | CLEAN | 1.2417 | 1.7845 | 8.1706 | 0.9702 | 3.7895 | -13.03% | 12.64% | 10.02% | 7.407 |
| CPM8 current      | EXT   | 1.2549 | 1.8114 | 8.2770 | 0.9712 | 4.1168 | -13.14% | 12.76% |  9.97% | 6.804 |
| CPM8 IWF+IWD swap | EXT   | 1.2712 | 1.8401 | 8.4500 | 0.8866 | 3.9497 | -14.14% | 12.54% |  9.66% | 6.975 |

Deltas (swap - current), CLEAN: dSharpe -0.0140, dSortino -0.0213,
dCAGR -0.49pp, dMaxDD ~0 (identical -13.03%), dCalmar -0.0374, dMartin -0.468,
turnover +0.32. EXT: dSharpe +0.0163 (EXT is unreliable, see caveat).

## (b) Style spanning: correlation + rotation

Pair correlation (daily returns):

| win | corr(IWF,IWD) | corr(QQQ,SPHQ) |
|-----|---------------|----------------|
| CLEAN | 0.8641 | 0.8809 |
| EXT   | 0.8432 | 0.8187 |

- CLEAN: IWF+IWD marginally MORE orthogonal (0.864 < 0.881) -> hypothesis weakly
  supported on pair corr. EXT reverses (new pair higher). Either way both pairs
  are highly correlated (~0.82-0.88) -> daily-frequency "style spanning" gain is
  small; growth and value still co-move strongly.

Style rotation (CLEAN, 217 monthly rebals):

| pair | slot-A held% | slot-B held% | both | neither | single-style switches |
|------|--------------|--------------|------|---------|-----------------------|
| NEW IWF/IWD | IWF 35.0% | IWD 40.6% | 50 | 103 | 17 |
| OLD QQQ/SPHQ | QQQ 29.0% | SPHQ 49.3% | 39 | 86 | 14 |

- Momentum DOES rotate growth<->value: 17 single-style switches over 217 months,
  with both IWF and IWD each held a meaningful fraction. It is NOT stuck in one
  style. In CLEAN, IWD (value) was held slightly more often than IWF (growth).
- But the NEW US-equity sleeve is held LESS often than the old one: new style
  slot filled 52.5% of months vs old 60.4% (CLEAN). The old SPHQ quality factor
  trended cleaner and got selected more.

## Selection divergence

| win | baskets differ | old style-slot held% | new style-slot held% | mean L1 wt dist (style slot) |
|-----|----------------|----------------------|----------------------|------------------------------|
| CLEAN | 20.3% (44/217) | 60.4% | 52.5% | 0.14 |
| EXT   | 19.9% (65/327) | 47.1% | 45.3% | 0.14 |

Modest effect size: held baskets (collapsing the style sleeve to a common slot)
differ only ~20% of rebals.

## Verdict on (a)-(c)

(a) Material change? NO. Sharpe, CAGR, MaxDD barely move. CLEAN is slightly
WORSE (Sharpe -0.014, CAGR -0.49pp, Calmar -0.037, Martin -0.47); MaxDD is
identical (-13.03%, the binding drawdown comes from a non-style episode, so the
swap cannot improve it). EXT slightly better but is unreliable.

(b) Style spanning? Marginal. corr(IWF,IWD) is a touch lower than corr(QQQ,SPHQ)
in CLEAN (0.864 vs 0.881), and the ranker does rotate growth<->value (17
switches, both styles held). BUT the spanning did NOT buy diversification or DD:
MaxDD unchanged, Calmar and Martin both worse, vol only marginally lower. The
diversification thesis is not realized in the CPM metrics.

(c) Direction? Giving up QQQ tech-beta and SPHQ quality, and adding IWD value,
HURTS slightly in CLEAN (the growth/quality-led era) and helps marginally in EXT
(pre-inception-gap, untrustworthy). The new sleeve is also held less often
(52.5% vs 60.4%), forfeiting accretive US-equity exposure. Net: roughly neutral
to slightly negative on the trustworthy CLEAN window.

DECISION: NO swap. IWF+IWD is a cleaner conceptual style pair and the momentum
ranker does rotate between the styles, but the change is immaterial-to-slightly-
negative on CLEAN with no drawdown benefit. Insufficient evidence to displace
QQQ+SPHQ, especially under HIGH overfit caution (single in-sample swap). CPM
production unchanged.

## Caveats / confidence

- HIGH overfit caution: single 2-ticker swap, single in-sample window. No
  bootstrap (skipped per scope) -> point estimates only; deltas this small
  (|dSharpe| ~0.014) are within noise.
- PIT/data caveat: IWF/IWD fetched live (yfinance auto_adjust), both inception
  2000-05-26. EXT (1999-03-10 start) has a ~14-month pre-inception gap where the
  style assets are unselectable (mechanism falls to other assets/safe) ->
  TRUST CLEAN; treat EXT as directional only.
- Confidence: MODERATE-HIGH that the swap is not an improvement on CLEAN;
  MODERATE on the "style rotation works but spanning gain is small" reading.

## Artifacts

- research/cpm_iwf_iwd_swap_2026_06_02.py (harness)
- research/cpm_iwf_iwd_swap_2026_06_02.json (full results)
- research/cpm_iwf_iwd_swap_findings.md (this file)
