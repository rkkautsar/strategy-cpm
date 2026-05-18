/**
 * CF Workers cron trigger -> fires GH Actions repository_dispatch event.
 *
 * Why this exists: GitHub Actions scheduled workflows are automatically
 * disabled after 60 days of repo inactivity. For a strategy that only
 * commits via its own monthly cron, that breaks after ~2 months.
 *
 * CF Workers cron triggers have no inactivity penalty. This Worker fires
 * monthly and POSTs to GitHub API to wake up the workflow that does the
 * actual Python compute + CF Pages deploy + Telegram notification.
 *
 * The Worker itself does nothing else. It is the durable clock.
 */

async function dispatchToGitHub(env, cronStr) {
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
      event_type: "monthly-signal",
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
  console.log(`GH dispatch fired for ${GH_OWNER}/${GH_REPO} at ${cronStr}`);
}

export default {
  // Scheduled cron handler (fires on schedule defined in wrangler.toml)
  async scheduled(event, env, ctx) {
    try {
      await dispatchToGitHub(env, event.cron);
    } catch (err) {
      console.error(err.message);
      throw err;
    }
  },

  // HTTP handler for manual testing
  async fetch(request, env, ctx) {
    if (request.method !== "POST") {
      return new Response("POST with X-Trigger-Token header to trigger manually", { status: 405 });
    }
    const auth = request.headers.get("X-Trigger-Token");
    if (!env.TRIGGER_TOKEN || auth !== env.TRIGGER_TOKEN) {
      return new Response("Unauthorized", { status: 401 });
    }
    try {
      await dispatchToGitHub(env, "manual");
      return new Response("Dispatched\n", { status: 200 });
    } catch (err) {
      return new Response(`Error: ${err.message}\n`, { status: 500 });
    }
  },
};
