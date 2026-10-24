# TAA Strategy Lab

A research dashboard and monthly backtest engine for tactical asset allocation
(TAA) strategies. Compare individual strategies, inspect their current target
allocations, and build a monthly rebalanced blend in the browser. Subscribers to
a saved blend can receive its monthly holdings and trades by email.

The dashboard is published at [cpm.rakha.dev](https://cpm.rakha.dev). This is a
personal research project, not investment advice or a broker-connected trading
system.

## What the dashboard does

- Shows each strategy as a selectable card with CAGR, maximum drawdown, and
  Sharpe ratio. A shared range selector controls the cards, summary, and charts.
- Shows strategy target holdings and the weight changes from the previous
  month. These are target weights, not share quantities.
- Lets you create **My blend** from selected strategies. Set weights in 5%
  steps, or ask Auto-optimize to search the available weight combinations for
  the highest historical Sharpe ratio. A blend rebalances its strategy sleeves
  monthly and appears alongside the individual strategies in the charts and
  performance table. Component strategy costs are reflected in their returns;
  the blend does not add a separate cost when it changes sleeve weights.
- Saves the selected view and blend definition in that browser's local storage.
- Lets you subscribe to monthly allocation emails for your blend. The email
  shows the current allocation and changes from the prior month's targets; it
  includes an unsubscribe link.

Auto-optimize evaluates the full shared historical window shown by the
dashboard. It is an **in-sample** historical fit, not an out-of-sample test or
evidence that the suggested weights will perform well in the future. The
dashboard does not currently provide a walk-forward or holdout optimizer.

The dashboard is a static HTML page plus a separately cached JSON data asset.
It includes calculated returns and target allocations, not the underlying price
history. A shared comparison window is calculated from the strategies enabled
by default; optional strategies do not shorten that default window. No prices
are synthesized before an ETF or constituent begins trading.

## Strategies and benchmarks

The strategy picker and blend editor include:

- **CPM:** Ranks QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, and DBC by 10-month trend
  distance divided by trailing 252-trading-day annualized volatility. Risky
  exposure is 0/0/50/100% for breadth one through four among the top four
  (breadth zero also gets 0%). At breadth four, it holds the equal-weight
  minimum-variance trio; at breadth three, it equally weights the positive-trend
  candidates. Remaining weight goes to the stronger 1/3/6/12-month momentum
  asset between BIL and IEF.
- **HAA-Simple:** Holds SPY when both SPY and the TIP canary pass the
  1/3/6/12-month average-momentum test; otherwise it holds the stronger of BIL
  and IEF.
- **HAA-Balanced:** Applies a TIP canary and momentum ranking to a diversified
  ETF universe with four equal slots; failed slots go to the stronger of BIL
  and IEF.
- **BAA-G12:** Uses four 1/3/6/12-month momentum canaries to select between an
  offensive ETF universe and a defensive sleeve.
- **VAA-G12:** Uses 1/3/6/12-month momentum breadth to shift between a global
  offensive universe and defensive bonds.
- **AAA:** Selects the five strongest assets by six-month return and assigns
  long-only minimum-variance weights.
- **NDX:** Selects Nasdaq-100 stocks using point-in-time membership, momentum,
  and a TIP/SPY/realized-volatility risk gate. BIL and IEF hold defensive or
  unfilled weight.
- **RPV:** Allocates among five macro risk-premium sleeves using rolling
  standardized signals, trend eligibility, FRED data, and Shiller data.
- **VAL:** Ranks Valuein-covered Nasdaq-100 companies using point-in-time value
  and quality fundamentals, trend, and a TIP/SPY/volatility risk gate.

BAA-G12, VAA-G12, and AAA are available but disabled by default in the picker;
you can enable them when you want to compare or blend them. The benchmarks are
SPY buy-and-hold and an annually rebalanced 60/40 SPY/AGG portfolio. QQQ is an
input to CPM, not a standalone benchmark.

All strategies calculate signals monthly and apply target weights at the next
trading day's close. The default transaction cost is 10 basis points per side.
The comparison uses the same execution and fee assumptions, but strategy
definitions and data availability differ. The RPV equity-premium signal uses
revised Shiller earnings history, which introduces lookahead bias; interpret
those results with that limitation in mind. VAL's available universe is limited
by the configured Valuein plan and data coverage.

## Run locally

Requirements: Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked
cp .env.example .env
# Add FRED_API_KEY for every run and VALUEIN_API_KEY to refresh VAL fundamentals.
uv run taa-backtest --output results
```

The default requested start date is 2007-01-01. The first valid date for each
strategy depends on its signal warm-up and the available histories; the
dashboard then aligns its comparison to the default-enabled strategies. To
bound the downloaded data, pass `--start YYYY-MM-DD` or `--end YYYY-MM-DD`.
Other useful options:

```bash
uv run taa-backtest --refresh                 # rebuild local Yahoo price cache
uv run taa-backtest --no-refresh-valuein       # use the existing Valuein cache
uv run taa-backtest --fee-bps 10 --cash 100000
```

The FRED key is required for every run because RPV fetches first-release CPI
live. The Valuein cache is private and ignored by Git. A first local VAL run
needs a valid Valuein API key and an eligible plan/cache; Valuein coverage is not
necessarily available for every Nasdaq-100 constituent. FRED and Valuein keys
are read from `.env`; do not commit `.env` or private data. See
`.env.example` for the supported settings.

Each run writes `dashboard.html`, a versioned `dashboard-data-*.json` asset,
`performance.csv`, `equity.csv`, `target_weights.csv`, and
`comparison_targets.csv` under `results/`. Generated output and local caches are
ignored by Git.

## Data and refresh pipeline

- Yahoo Finance daily adjusted prices are fetched through `yfinance` and cached
  locally at `.cache/`. Later runs update a recent overlap and fetch missing
  dates; `--refresh` rebuilds the full local cache. Adjusted history can be
  revised by the source.
- Nasdaq-100 constituent prices and point-in-time membership are cached
  separately for NDX and VAL. New members are backfilled from the selected
  start date.
- RPV fetches the full current FRED series, ALFRED first-release CPI history,
  and Shiller-derived CSV on every build. These raw macro responses are used in
  memory and are not committed, kept in `.cache`, or included in R2 snapshots.
  CPI uses first-release values, shifted by one month. A failed source fetch
  fails the build instead of silently using an older macro snapshot.
- VAL stores Valuein facts as local per-company Parquet partitions under
  `.cache/valuein` (or `VALUEIN_CACHE_DIR`). On a changed Valuein manifest it
  refreshes the Nasdaq-100 security map and relevant company partitions, with
  per-company checkpoints so a rate-limited refresh can resume. Historical
  `accepted_at` vintages are retained for point-in-time signals. The bulk API
  has no row-level cursor, so refresh is scoped by company rather than by row.

The monthly pipeline is a Cloudflare Cron Worker that dispatches the GitHub
Actions workflow. The workflow restores private state from Cloudflare R2,
refreshes the data, rebuilds the full backtest and dashboard, deploys to
Cloudflare Pages, and then sends allocation emails when the dispatch requests
them. It runs at 02:17 UTC on the 4th (9:17 PM EST / 10:17 PM EDT on the 3rd in
New York). A full history replay is used because the engine does not yet store a
serialized portfolio-state checkpoint for appending one month of results.

R2 is private persistent storage for permitted source caches and monthly
snapshots; it is not the public dashboard data source. RPV macro source files
are excluded from R2 snapshots. The pipeline commits a new snapshot and
advances its latest pointer only after upload. Failed runs preserve other cache
progress for retry.

## Deployment configuration

The monthly workflow expects these GitHub repository secrets:

`CPM_R2_BUCKET`, `CPM_R2_ACCOUNT_ID`, `CPM_R2_ACCESS_KEY_ID`,
`CPM_R2_SECRET_ACCESS_KEY`, `FRED_API_KEY`, `VALUEIN_API_KEY`,
`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
`NOTIFICATION_DISPATCH_TOKEN`, and `RESEND_API_KEY`.

Set `RESEND_FROM` and `DASHBOARD_URL` as GitHub repository variables, and
`UNSUBSCRIBE_SIGNING_SECRET` as a Cloudflare Pages production secret. Monthly
email subscriptions use Pages Functions, D1, and Resend; blend definitions and
subscriber addresses are stored in D1, not in the static dashboard. For D1
schema and email setup, see [deploy/cf-pages/notifications.md](deploy/cf-pages/notifications.md).
For the scheduled workflow dispatcher, see [deploy/cf-cron/README.md](deploy/cf-cron/README.md).

## Data-use note

Yahoo Finance data accessed through `yfinance` is unofficial and intended for
personal/research use. Confirm data rights before publishing price history or
building a public service on it. The dashboard publishes calculated results,
not source price bars. Keep `.env`, local caches, and Valuein source data private
and out of commits.
