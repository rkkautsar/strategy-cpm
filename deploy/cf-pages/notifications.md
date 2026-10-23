# Monthly blend email setup

Email subscriptions use Cloudflare Pages Functions, D1, and the Resend API. Blend definitions and subscriber email addresses stay in D1; the static dashboard does not contain them. A subscriber must confirm ownership of the email address. Each monthly message includes the current target holdings and target-weight changes versus the previous signal.

## One-time setup

The existing `cpm-bull-dashboard` Pages project serves `https://cpm.rakha.dev`. The root `wrangler.toml` binds the notification D1 database to that project. Apply the schema from this repository:

   ```sh
   npx wrangler d1 execute taa-dashboard-notifications --remote --file deploy/cf-pages/migrations/0001_monthly_blend_notifications.sql
   ```

Configure these GitHub repository secrets and variables:

| Name | Type | Value |
|---|---|---|
| `RESEND_API_KEY` | Secret | Resend API key |
| `RESEND_FROM` | Variable | Sender on a domain verified with Resend |
| `NOTIFICATION_DISPATCH_TOKEN` | Secret | Random token shared with Pages Functions |
| `DASHBOARD_URL` | Variable | `https://cpm.rakha.dev` |

The workflow copies the Resend credentials into Pages during deployment. Configure `UNSUBSCRIBE_SIGNING_SECRET` as a Pages production secret. The Pages `DASHBOARD_URL` variable comes from `wrangler.toml`; the workflow reads the GitHub `DASHBOARD_URL` variable when dispatching email.

After setup, the workflow posts the generated target-only payload to Pages after the dashboard deploy succeeds. Delivery is idempotent per subscription and signal month, so rerunning a failed workflow retries only subscribers who were not recorded as delivered.

The earlier single-recipient sender used Resend's `onboarding@resend.dev` default. Resend restricts that sender to the account owner's verified address, so a verified sender domain is required for subscriptions from other people.

## Schedule

GitHub Actions schedules the monthly workflow for 02:17 UTC on the 4th, which is 9:17 PM EST or 10:17 PM EDT on the 3rd in New York. This is after the prior month has closed and leaves time for Yahoo Finance to settle before the next market session. Scheduled runs fail if the notification dispatch token is missing. If GitHub delays or misses a scheduled run, use the Actions tab to start the workflow manually and select “Send this month's allocation to every eligible subscriber”; D1 delivery records prevent duplicate sends.
