/**
 * CF Workers cron trigger -> fires GH Actions repository_dispatch event.
 *
 * Two cron schedules (see wrangler.toml):
 *   1. Monthly signal:    0 2 1 * *     (1st of month, 10am SGT) -> event_type: monthly-signal
 *   2. Daily vol-check:   30 22 * * 1-5 (weekdays 22:30 UTC, 6:30am SGT) -> event_type: vol-check
 *
 * Why CF Workers cron: GitHub Actions scheduled workflows auto-disable after
 * 60 days of repo inactivity. CF Workers cron has no inactivity penalty.
 *
 * Daily vol-check: catches latched-binary vol-cap trigger / lift between
 * monthly rebalances. Sends Telegram alert only on state change (~0.9/yr).
 * Fires after US market close (4pm ET = 21:00 UTC summer / 22:00 UTC winter);
 * 22:30 UTC chosen to safely cover both DST regimes with 30min margin.
 */

const EVENT_BY_CRON = {
  "0 2 1 * *":   "monthly-signal",
  "30 22 * * 1-5": "vol-check",
};

async function dispatchToGitHub(env, cronStr, eventType) {
  const { GH_OWNER, GH_REPO, GH_TOKEN } = env;
  if (!GH_OWNER || !GH_REPO || !GH_TOKEN) {
    throw new Error("Missing GH_OWNER / GH_REPO / GH_TOKEN env vars");
  }

  const url = `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${GH_TOKEN}`,
      "User-Agent": "cpm-bull-cron-worker",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      event_type: eventType,
      client_payload: {
        triggered_at: new Date().toISOString(),
        cron: cronStr,
      },
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GH dispatch failed ${res.status}: ${body}`);
  }
  console.log(`GH dispatch fired event=${eventType} for ${GH_OWNER}/${GH_REPO} at ${cronStr}`);
}

export default {
  // Scheduled cron handler (fires on schedule defined in wrangler.toml)
  async scheduled(event, env, ctx) {
    const eventType = EVENT_BY_CRON[event.cron] || "monthly-signal";
    try {
      await dispatchToGitHub(env, event.cron, eventType);
    } catch (err) {
      console.error(err.message);
      throw err;
    }
  },

  // HTTP handler for manual testing.
  // POST / with X-Trigger-Token => monthly-signal (default)
  // POST /?event=vol-check with X-Trigger-Token => vol-check
  async fetch(request, env, ctx) {
    if (request.method !== "POST") {
      return new Response("POST with X-Trigger-Token header to trigger manually\n", { status: 405 });
    }
    const auth = request.headers.get("X-Trigger-Token");
    if (!env.TRIGGER_TOKEN || auth !== env.TRIGGER_TOKEN) {
      return new Response("Unauthorized\n", { status: 401 });
    }
    const url = new URL(request.url);
    const eventType = url.searchParams.get("event") || "monthly-signal";
    if (!["monthly-signal", "vol-check"].includes(eventType)) {
      return new Response(`Unknown event=${eventType}\n`, { status: 400 });
    }
    try {
      await dispatchToGitHub(env, "manual", eventType);
      return new Response(`Dispatched ${eventType}\n`, { status: 200 });
    } catch (err) {
      return new Response(`Error: ${err.message}\n`, { status: 500 });
    }
  },
};
