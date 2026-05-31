# 1970s Stagflation TIP-Canary Efficacy on Equity (Foundational, Multi-Episode)

Status: complete. Read-only re production. Artifacts written to research/ only.
No production/memo edits, no commit.

Harness: `research/stagflation_1970s_tip_canary.py`
JSON: `research/stagflation_1970s_tip_canary_findings.json`
Raw data cache: `research/data_1970s/`

## Question

Does a (synthetic) TIP-momentum canary actually de-risk EQUITY through REAL
1970s stagflation drawdowns (1973-74, 1977-82)? The prior `canary_variant_test.py`
skipped the 1970s -- its panel starts 1995, so 2022 (n=1) was the only real-data
stagflation episode it could test. This is the foundational test the n=1 case
lacked.

Scope note: HYG (high yield) and the production ETF risky universe do not exist
pre-1980, so this is NOT a HYG-OR-TIP vs TIP-only production rerun. It is a
single equity sleeve (S&P 500 total return) gated by canary 13612U momentum,
with a long-history credit analog (Moody's Baa corporate-bond total return)
standing in for HYG, testing four variants:

1. `tip_only`       - risk-on iff synthetic-TIP 13612U > 0
2. `credit_or_tip`  - risk-on iff (Baa > 0 OR TIP > 0)   [HYG-OR-TIP analog]
3. `credit_and_tip` - risk-on iff (Baa > 0 AND TIP > 0)
4. `buyhold`        - always risk-on (= S&P 500 buy & hold)

Defensive months earn the 3-month T-bill.

## Verdict (headline)

The (synthetic) TIP-momentum canary does NOT provide genuine stagflation
drawdown protection on equity. In the 1973-74 stagflation bear it stayed
risk-on EVERY month -- its 13612U signal was positive throughout and even
STRENGTHENED into the crash (TIP signal rose from +0.037 in Dec-1972 to +0.105
by Nov-1974). Over the full 1968-1985 window the TIP-only canary was defensive
exactly ONCE (1980-04), capturing 1.1% of equity down-months. Its CAGR / MaxDD /
Sharpe are statistically indistinguishable from buy-and-hold.

`credit_or_tip` is IDENTICAL to `tip_only` in the 1970s (zero override months):
whenever TIP said de-risk, Baa also said de-risk, so OR never overrode. The
permissive leg that kept equity exposed through the crash was TIP, not credit.

The only variant that protected was `credit_and_tip`, and its protection came
almost entirely from the CREDIT (Baa) leg de-risking as rising rates crushed
corporate-bond total returns -- not from TIP. Even that protection was noisy
(59% false-positive defensive rate) and cheap to run only because T-bills paid
double digits in this era.

Economic reading: TIPS are designed NOT to crash during inflation (CPI accrual
offsets nominal-rate pain), so a TIP-momentum signal will not flag classic
stagflation equity risk. 2022 was the opposite kind of episode -- a
rate-shock / disinflation-scare where TIP fell alongside equities, so the TIP
canary "worked" there by coincidence of regime. The 1970s show the regime where
it fails. This is the multi-episode evidence the n=1 (2022) test lacked.

## Results

### Full period 1968-01 .. 1985-12 (nominal total return)

| Variant | CAGR | MaxDD | Sharpe (excess) | Vol |
|---|---|---|---|---|
| tip_only       |  8.99% | -39.16% | 0.145 | 12.82% |
| credit_or_tip  |  8.99% | -39.16% | 0.145 | 12.82% |
| credit_and_tip |  9.94% | -22.56% | 0.247 |  9.48% |
| buyhold        |  8.85% | -39.16% | 0.135 | 12.83% |

tip_only == credit_or_tip == buyhold to the second decimal (one defensive month
in 18 years). credit_and_tip is the only variant that moves the needle, via the
Baa leg.

### Stagflation window 1973-74 (the ~-48% real S&P bear)

| Variant | Total return | MaxDD | DD avoided vs B&H | Sharpe |
|---|---|---|---|---|
| tip_only       | -38.55% | -39.16% |  0.0 pp | -2.10 |
| credit_or_tip  | -38.55% | -39.16% |  0.0 pp | -2.10 |
| credit_and_tip | -17.60% | -22.56% | +16.6 pp | -1.82 |
| buyhold        | -38.55% | -39.16% |  0.0 pp | -2.10 |

TIP-only / credit-OR-TIP rode the full bear (identical to buy-and-hold).
credit-AND-TIP cut the drawdown by 16.6 pp -- entirely because Baa momentum
turned negative from 1974-04 onward (rates rising), de-risking H2 1974.

### Stagflation window 1977-82

| Variant | Total return | MaxDD | DD avoided vs B&H | Sharpe |
|---|---|---|---|---|
| tip_only       | 84.80% | -13.42% |  0.0 pp | 0.101 |
| credit_or_tip  | 84.80% | -13.42% |  0.0 pp | 0.101 |
| credit_and_tip | 78.96% |  -9.87% | +3.55 pp | 0.046 |
| buyhold        | 80.67% | -13.42% |  0.0 pp | 0.072 |

1977-82 was not a sustained equity bear (equities ground higher in nominal
terms); the canary had little to protect. TIP fired once (1980-04). credit-AND
shaved a little MaxDD but gave up return for a lower Sharpe.

### Real (CPI-deflated) S&P context

- Real S&P buy-and-hold MaxDD, full window: -49.94%
- Real S&P buy-and-hold MaxDD, 1973-74: -49.94%

Confirms the ~-48% real 1973-74 drawdown cited in the brief. The TIP canary
avoided 0 pp of it.

### Defensive-month behaviour (1968-1985, 215 equity months)

| Variant | Defensive months | False-positive (de-risked, equity rose) | FP rate | Down-month capture |
|---|---|---|---|---|
| tip_only       |  1 |  0 |  0.0% |  1.1% |
| credit_or_tip  |  1 |  0 |  0.0% |  1.1% |
| credit_and_tip | 66 | 39 | 59.1% | 31.0% |

The single TIP-only defensive month was 1980-04. credit-AND-TIP de-risked 66
months but with a 59% false-positive rate -- it caught 31% of down-months by
being defensive a third of the time, not by precision.

### Override / signal-disagreement census

- `credit_or_tip` override months (TIP <= 0 AND Baa > 0): 0.
  Credit never kept equity risk-on when TIP wanted out -> OR added nothing and
  cannot have HURT relative to TIP-only in the 1970s.
- Baa <= 0 AND TIP > 0 months: 65.
  The mirror case dominates: credit wanted out 65 times while TIP stayed in.
  This is why AND (which respects the credit veto) protected and OR/TIP did not.

The user's core concern -- "does the credit override keep equity risk-on INTO
stagflation drawdowns" -- resolves as: in the 1970s the override that kept
equity exposed was the TIP leg, not credit. Credit's signal was the more
defensive of the two. So in a true 1970s-style stagflation, credit-OR-TIP fails
because TIP is permissive, and dropping credit (TIP-only) would not have helped.

## Data sources (all public)

| Series | Source | Use |
|---|---|---|
| S&P 500 price + dividend, monthly | Robert Shiller `ie_data` (datahub mirror `datasets/s-and-p-500`) | S&P 500 monthly TOTAL return |
| CPI | FRED `CPIAUCSL` | inflation accrual + real deflation |
| 5y Treasury CMT yield | FRED `GS5` | nominal intermediate-Treasury TR (synthetic-TIP base) |
| 10y Treasury CMT yield | FRED `GS10` | cached for sensitivity (not in headline) |
| Moody's Baa corp yield | FRED `BAA` (1919+) | credit (HYG analog) TR |
| 3m T-bill | FRED `TB3MS` | defensive / cash leg |

Raw CSVs cached under `research/data_1970s/` for reproducibility.

## Constructions (documented)

- S&P 500 monthly total return:
  `TR_t = (P_t - P_{t-1} + D_t/12) / P_{t-1}`
  where P = Shiller monthly S&P price, D = Shiller annualized dividend/share
  (D/12 = month's reinvested dividend). Standard Shiller TR reconstruction.

- Constant-maturity bond total return (Treasury GS5 N=5y, Baa N=20y):
  par coupon bond repriced monthly, coupon rate = prior yield:
  `income_t = y_{t-1}/12`,
  `price_ret_t = -Dmod_{t-1} * (y_t - y_{t-1})`,
  `TR_t = income + price_ret`.
  Dmod = modified duration of a par bond (semiannual coupons). First-order
  (duration-only) approximation; convexity omitted (second order; the canary
  uses only the SIGN of 13612U momentum, so this suffices).

- SYNTHETIC TIP -- SAME construction as `canary_variant_test.py`:
  `syn_TIP TR = nominal intermediate-Treasury TR + realized monthly CPIAUCSL inflation`,
  cumulated to a price index, used ONLY for the 13612U canary signal.

- Signal: `13612U = mean(1m,3m,6m,12m total returns)` of the canary price index
  (matches `cpm_live.sig_13612U`). Computed at end of month t (>=13 months
  history), applied to month t+1 (1-month implementation lag, no lookahead).

## Caveats and confidence

- No real TIPS exist pre-1997; the 1970s TIP signal is a CPI-accrual proxy.
  Sign cannot be validated against real TIPS in the 1970s. The only overlap
  check (`canary_variant_test.py`, 2000-06+) gives 13612U sign agreement = 0.84
  over 300 months vs real TIP (VIPSX stitch).
- Proxy bias direction: adding full realized CPI on top of a nominal yield
  (which already embeds expected inflation) likely OVERSTATES synthetic-TIP
  returns in high-inflation months, making the TIP canary even MORE risk-on
  than real TIPS would be. So if anything the proxy understates how often real
  TIP momentum might de-risk -- but the qualitative verdict is robust because
  TIPS by design hold up in inflation, so real TIP momentum would also have
  stayed largely positive through 1973-74.
- 1970s equity = Shiller monthly S&P (monthly-average price, not daily close);
  drawdown magnitudes are month-end approximations.
- Bond TR is a first-order par-bond duration reconstruction; Baa duration N=20
  is an assumption (long investment-grade corporate). Duration changes the
  MAGNITUDE of credit TR but not the SIGN of its momentum, which is what the
  canary uses.
- Credit analog = Moody's Baa (investment-grade long corporate), NOT high yield.
  HYG did not exist pre-1980; Baa is the longest-history credit-risk series.
  A true high-yield series would carry more equity-correlated default risk and
  might de-risk somewhat differently, but the central finding (TIP leg is the
  permissive one in stagflation) does not depend on the credit proxy.
- Defensive asset = 3m T-bill. Using intermediate Treasuries as the defensive
  leg would change defensive-leg returns (Treasuries lost ground to rising
  rates in the 1970s), generally HURTING the protective variants -- not tested
  in the headline.

Confidence: HIGH on the qualitative verdict (TIP-momentum canary does not flag
1970s stagflation equity risk; protection came from credit). The signal calendar
shows TIP positive in all 24 months of the 1973-74 bear, which is economically
coherent and robust to the proxy caveats. MODERATE on exact magnitudes
(monthly-average prices, duration assumptions, proxy bias).

## Handoff

None required for analysis. If this evidence is to change production canary
logic (e.g. de-emphasize TIP as a stagflation guard, or add a credit/rate-trend
guard), route the production/memo edits to the fixer and a release decision to
the oracle.
