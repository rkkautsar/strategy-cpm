const EVENT_TYPE = "monthly-signal";

async function dispatchMonthlyWorkflow(env, cron) {
  const { GH_OWNER, GH_REPO, GH_TOKEN } = env;
  if (!GH_OWNER || !GH_REPO || !GH_TOKEN) {
    throw new Error("Missing GH_OWNER, GH_REPO, or GH_TOKEN Worker binding");
  }

  const response = await fetch(
    `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${GH_TOKEN}`,
        "User-Agent": "cpm-bull-cron-worker",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        event_type: EVENT_TYPE,
        client_payload: { triggered_at: new Date().toISOString(), cron },
      }),
    },
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub repository_dispatch failed (${response.status}): ${body}`);
  }

  console.log(`Dispatched ${EVENT_TYPE} for ${GH_OWNER}/${GH_REPO}; cron=${cron}`);
}

export default {
  async scheduled(event, env) {
    await dispatchMonthlyWorkflow(env, event.cron);
  },

  async fetch(request) {
    return new Response("Monthly CPM scheduler is active.\n", {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  },
};
