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
to the stronger of BIL and IEF. With `VALUEIN_API_KEY`, each run checks the
Valuein manifest and skips unchanged snapshots. On a new snapshot it refreshes
the security map and the full fact partitions for current Nasdaq-100 CIKs,
replacing only those company partitions and retaining older bootstrap history.
Each company partition is checkpointed separately, so rate-limited runs resume
without redownloading completed CIKs. An active Pro or Full plan is required;
the updater blocks publication if coverage is incomplete. Historical
`accepted_at` vintages remain intact for point-in-time VAL signals.

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
`uv sync --extra r2`. The runner restores one checksummed snapshot, updates
recent/missing Yahoo prices (35-day overlap), FRED observations (60-day overlap),
and ALFRED first-release CPI (18-month overlap), then writes an immutable new
snapshot and advances the latest pointer only after upload. Shiller has no
small incremental API, so its compact CSV is re-fetched and merged by date.
Never make this bucket public. For an initial seed from a machine that already
has the full private cache and Valuein Parquet files, run
`uv run python -m taa_engine.r2_snapshot publish` with the R2 variables set.

The monthly dashboard pipeline is GitHub Actions → private R2 → Cloudflare Pages.
It is scheduled for 9:17 PM EST / 10:17 PM EDT on the 3rd, after the prior
month's US market close. GitHub Actions replays the full cached history to
preserve vectorbt results; it does not append a single month because the current
engine has no serialized portfolio/VAL state checkpoint. The R2 archive keeps
immutable monthly cache and results snapshots. Failed refreshes also preserve
private cache progress so a retry can resume. VAL still uses its cached
Valuein Parquet bootstrap snapshot and applies manifest-aware per-CIK updates;
the Valuein API has no row-level cursor, so the updater replaces only the
relevant company partitions instead of downloading the full market-wide fact
table.

Configure GitHub repository secrets `CPM_R2_BUCKET`, `CPM_R2_ACCOUNT_ID`,
`CPM_R2_ACCESS_KEY_ID`, `CPM_R2_SECRET_ACCESS_KEY`, `FRED_API_KEY`,
`VALUEIN_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
`NOTIFICATION_DISPATCH_TOKEN`, and `RESEND_API_KEY`; configure `RESEND_FROM` and
`DASHBOARD_URL` as repository variables. Set `UNSUBSCRIBE_SIGNING_SECRET` as a
Cloudflare Pages production secret. No separate cron Worker or GitHub dispatch
token is needed. Blend definitions and selected strategy are already saved in
browser localStorage and remain on that browser/origin.

Yahoo Finance data accessed through `yfinance` is unofficial and intended for
personal/research use. This starter is for private research; confirm data rights
before publishing price history or building a public service on it. The local
cache is ignored by Git and should not be committed or redistributed.
