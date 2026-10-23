# Monthly blend email setup

Email subscriptions use Cloudflare Pages Functions, D1, and the Resend API. Blend definitions and subscriber email addresses stay in D1; the static dashboard does not contain them. A subscriber must confirm ownership of the email address. Each monthly message includes the current target holdings and target-weight changes versus the previous signal.

## One-time Cloudflare setup

1. Create a D1 database named `taa-dashboard-notifications` in the same Cloudflare account as the `taa-dashboard` Pages project.
2. Apply the schema from this repository:

   ```sh
   npx wrangler d1 execute taa-dashboard-notifications --remote --file deploy/cf-pages/migrations/0001_monthly_blend_notifications.sql
   ```

3. In the Pages project settings, add a production D1 binding named `DB` pointing to that database.
4. Add these production variables/secrets to the Pages project:

   | Name | Type | Value |
   |---|---|---|
   | `RESEND_API_KEY` | Secret | Resend API key |
   | `RESEND_FROM` | Variable | Sender on a domain verified with Resend |
   | `UNSUBSCRIBE_SIGNING_SECRET` | Secret | Long random string used to sign unsubscribe links |
   | `NOTIFICATION_DISPATCH_TOKEN` | Secret | Random token shared with GitHub Actions |
   | `DASHBOARD_URL` | Variable | Public dashboard origin, e.g. `https://taa-dashboard.pages.dev` |

5. Add `NOTIFICATION_DISPATCH_TOKEN` as a GitHub Actions repository secret and `DASHBOARD_URL` as a repository variable. Use the same values configured in Pages.
6. Deploy the workflow and Pages project. The workflow posts the generated target-only payload to Pages after the dashboard deploy succeeds; dispatches are idempotent per subscription and month.
7. Redeploy the cron Worker so the 9 PM Eastern schedule takes effect:

   ```sh
   cd deploy/cf-cron
   npx wrangler deploy
   ```

The earlier single-recipient sender used Resend's `onboarding@resend.dev` default. Resend restricts that sender to the account owner's verified address, so a verified sender domain is required for subscriptions from other people.

## Schedule

Cloudflare Cron runs at both possible UTC hours for 9 PM `America/New_York` on the third calendar day of each month. The Worker checks the Eastern date and hour and dispatches GitHub Actions only for the matching run, accounting for daylight saving time. The workflow fetches data, builds and deploys the dashboard, then emails verified subscribers. If the dispatch token is not configured, email delivery is skipped and the dashboard still builds.
