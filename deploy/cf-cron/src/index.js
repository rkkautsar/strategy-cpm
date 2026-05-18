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

export default {
  async scheduled(event, env, ctx) {
    const owner = env.GH_OWNER;
    const repo = env.GH_REPO;
    const token = env.GH_TOKEN;

    if (!owner || !repo || !token) {
      console.error("Missing GH_OWNER / GH_REPO / GH_TOKEN env vars");
      return;
    }

    const url = `https://api.github.com/repos/${owner}/${repo}/dispatches`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${token}`,
        "User-Agent": "cpm-bull-cron-worker",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        event_type: "monthly-signal",
        client_payload: {
          triggered_at: new Date().toISOString(),
          cron: event.cron,
        },
      }),
    });

    if (!res.ok) {
      const body = await res.text();
      console.error(`GH dispatch failed ${res.status}: ${body}`);
      throw new Error(`GH dispatch failed: ${res.status}`);
    }
    console.log(`GH dispatch fired for ${owner}/${repo} at ${event.cron}`);
  },

  // Optional: manual trigger via HTTP for testing
  async fetch(request, env, ctx) {
    if (request.method !== "POST") {
      return new Response("POST to trigger manually", { status: 405 });
    }
    const auth = request.headers.get("X-Trigger-Token");
    if (auth !== env.TRIGGER_TOKEN) {
      return new Response("Unauthorized", { status: 401 });
    }
    // Reuse the scheduled handler logic
    await this.scheduled({ cron: "manual" }, env, ctx);
    return new Response("Dispatched", { status: 200 });
  },
};
