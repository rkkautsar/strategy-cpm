# CPM monthly scheduler

Cloudflare Worker `cpm-bull-cron` dispatches the GitHub workflow
`monthly-dashboard.yml` with `send_all_notifications=true`. The GitHub workflow
builds and deploys the dashboard, then emails the current blend allocations
to subscribers.

The cron is `17 2 4 * *` UTC: 9:17 PM EST / 10:17 PM EDT on the 3rd in New
York. It does not depend on repository activity, unlike GitHub's native
scheduled workflows for public repositories.

Deploy from the repository root:

```sh
wrangler deploy --config deploy/cf-cron/wrangler.toml
```

The existing Worker secret `GH_TOKEN` must be a GitHub token with
`Actions: Read and write` access to `rkkautsar/strategy-cpm`. `GH_OWNER` and
`GH_REPO` are configured as non-secret Worker vars. Test the full monthly flow
through the Cloudflare cron run UI only when an email run is intended; ordinary
workflow recovery remains available from the GitHub Actions UI.
