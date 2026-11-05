# CPM monthly scheduler

Cloudflare Worker `cpm-bull-cron` dispatches the GitHub workflow
`monthly-dashboard.yml` with `send_all_notifications=true`. The GitHub workflow
checks the scheduled New York session against the NYSE calendar, then builds
and deploys the dashboard and emails the current blend allocations only when
that date is the month's final trading session.

The Worker cron runs at 02:00 and 03:00 UTC daily. It dispatches only when the
scheduled instant is 10 PM in `America/New_York`, covering daylight saving
time without relying on a fixed UTC offset. It passes that New York date to the
workflow as `scheduled_session_date`; the workflow's NYSE calendar preflight
skips dates that are not the month's final trading session. This schedule does
not depend on repository activity, unlike GitHub's native scheduled workflows
for public repositories.

Deploy from the repository root:

```sh
wrangler deploy --config deploy/cf-cron/wrangler.toml
```

The existing Worker secret `GH_TOKEN` must be a GitHub token with
`Actions: Read and write` access to `rkkautsar/strategy-cpm`. `GH_OWNER` and
`GH_REPO` are configured as non-secret Worker vars. Test the full monthly flow
through the Cloudflare cron run UI only when an email run is intended; ordinary
workflow recovery remains available from the GitHub Actions UI.

The Worker persists structured logs in Cloudflare Workers Observability. Each
cron invocation records its schedule time, New York date/hour, and either a
skip, successful workflow dispatch, or dispatch error. GitHub error response
text is capped at 1,000 characters; credentials are never logged.
