# TAA backtest engine

A small Python backtest for CPM and seven monthly TAA strategies,
compared with SPY buy-and-hold and an annually rebalanced 60/40 SPY/AGG portfolio.

## Rules

- Risky universe: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
- Rank the top four by 10-month Faber trend distance divided by trailing
  252-trading-day annualized volatility.
- Count positive-trend assets among those four. Risky exposure is 0% for
  breadth one or two, 50% for breadth three, and 100% for breadth four.
- At breadth four, hold the equal-weight minimum-variance trio from the four
  candidates. At breadth one through three, hold all positive candidates equally.
- Put the remaining exposure in the higher 1/3/6/12-month momentum asset from
  BIL and IEF.
- Calculate at month-end and apply target weights at the next trading day's
  close. The default cost is 10 bps per side.

The SPY benchmark buys and holds SPY. The 60/40 benchmark buys 60% SPY and 40%
AGG at the start, then restores those weights on the first trading day of each
calendar year. QQQ remains part of CPM's risky universe.

## Strategy comparisons

- **HAA-Simple:** Hold SPY only when both TIP and SPY have positive
  1/3/6/12-month average momentum; otherwise hold the stronger of BIL and IEF
  by that same momentum score.
- **HAA-Balanced:** Same canary and HAA-8 universe, with four equal 25% slots;
  each selected slot with nonpositive momentum goes to the stronger of BIL and
  IEF.
- **BAA-G12:** Balanced Keller BAA with SPY/VEA/VWO/BND canaries using 13612W;
  all four must be positive to hold the six strongest offensive assets by
  13-month SMA ratio. Otherwise hold the three strongest defensive assets,
  replacing any below BIL's SMA ratio with BIL.
- **VAA-G12:** Rank SPY/IWM/QQQ/VGK/EWJ/EEM/VNQ/GSG/GLD/TLT/HYG/LQD by 13612W momentum; hold the top two equally when at most one asset has nonpositive momentum, the top asset and strongest of SHY/IEF/LQD at 50% each when two or three are nonpositive, and only that defensive asset when four or more are nonpositive.
- **AAA:** ReSolve's 10-asset universe (SPY/EZU/EWJ/EEM/IYR/RWX/IEF/TLT/
  DBC/GLD); select the top five by six-month return and assign long-only
  minimum-variance weights using 126-day correlation and 20-day volatility.
  There is no canary, positive-momentum screen, or cash sleeve.

The comparison strategies share the same adjusted daily price panel, monthly
signal dates, next-trading-day-close execution, initial cash, and transaction
cost assumption as CPM. Strategy-specific ETF histories limit the common data
window; the backtest does not synthesize pre-inception prices.

**NDX** is a separate stock-selection strategy. It uses historical
point-in-time Nasdaq-100 membership, the TIP/SPY/realized-volatility gate,
positive 1/3/6/12-month momentum, five equal stock slots, and BIL/IEF for the
defensive position and any unfilled slots; a held name that stops quoting gets
a one-time 10% liquidation haircut. Constituent closes are stored in a
separate local cache; newly added symbols are backfilled from the selected start
date. The dashboard lets NDX be inspected and included in a strategy blend.

**RPV** uses the old five-premium model: term, investment-grade credit, equity,
high-yield credit, and real yield. Each monthly premium is standardized against
its trailing 120 months; after a 36-observation burn-in, positive scores are
eligible only when their ETF is above its 200-day SMA. Eligible sleeves are
weighted by positive z-score, with BIL held when none qualify. Macro inputs are
refreshed from FRED and the Shiller S&P 500 dataset on each run, with local
snapshots as fallback; `--no-refresh-macro` skips the requests. CPI uses first
release values when available, shifted by one month. The Shiller earnings
history is revised and therefore gives the equity-premium leg lookahead bias.
RPV is available in the strategy picker and blend editor.

**VAL** selects five Nasdaq-100 stocks using point-in-time Valuein fundamentals,
quality/value ranking, a stateful 10-month trend band, and a TIP/SPY/volatility
risk gate. It uses the local Parquet snapshot in `.cache/valuein` (or
`--valuein-cache` / `VALUEIN_CACHE_DIR`) and routes defensive or unused weight
to the stronger of BIL and IEF. The local snapshot is not refreshed by the
engine; keep its `accepted_at` data current before relying on the live signal.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
taa-backtest --start 2007-01-01
```

The first run downloads split- and dividend-adjusted daily closes from Yahoo
Finance and caches the complete panel at `.cache/cpm_daily_prices.csv.gz` with a
small metadata sidecar. Later runs refresh a 35-day overlap and fetch only missing
prices; pass `--refresh` to rebuild the full adjusted history. Historical adjusted
prices can be revised, so the overlap is replaced on each update.

The first NDX-enabled run also downloads the historical constituent universe in
30-symbol batches. Later runs refresh the recent overlap for cached symbols and
download full history for new members.

Each run writes `performance.csv`, `equity.csv`, `target_weights.csv`, and a
mobile-friendly `dashboard.html` under `results/`. The dashboard includes
synchronized timeframe selectors for the charts and performance summary, a
rolling three-month maximum drawdown chart, CPM target holdings, and changes
from the prior month's target. Trade changes are shown as target-weight
percentage points; share quantities require portfolio size and current
holdings. The strategy-blend editor lets you choose TAA strategies and target
weights that sum to 100%; it rebalances the strategy sleeves monthly and adds
the blend to both charts and the performance table. The static dashboard
already embeds each strategy's daily net equity curve, so it needs no extra
price or monthly-return store. Component strategy fees are included; the blend
does not add a cost for transfers between sleeves.

For a persistent private cache across ephemeral monthly build runners, configure
a private Cloudflare R2 bucket and set `CPM_R2_BUCKET`, `CPM_R2_ACCOUNT_ID`,
`CPM_R2_ACCESS_KEY_ID`, and `CPM_R2_SECRET_ACCESS_KEY`. Install R2 support with
`uv sync --extra r2`; each run restores the cache, updates only recent/missing
prices, and writes it back. Never make this bucket public.

Yahoo Finance data accessed through `yfinance` is unofficial and intended for
personal/research use. This starter is for private research; confirm data rights
before publishing price history or building a public service on it. The local
cache is ignored by Git and should not be committed or redistributed.
