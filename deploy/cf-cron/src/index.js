const EVENT_TYPE = "monthly-dashboard";

function isEasternNinePmOnThird(eventTime) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    day: "numeric",
    hour: "numeric",
    hourCycle: "h23",
  }).formatToParts(eventTime);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return Number(values.day) === 3 && Number(values.hour) === 21;
}

async function dispatch(env, trigger) {
  const { GH_OWNER, GH_REPO, GH_TOKEN } = env;
  if (!GH_OWNER || !GH_REPO || !GH_TOKEN) throw new Error("Missing GitHub dispatch configuration.");
  const response = await fetch(`https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/dispatches`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${GH_TOKEN}`,
      "User-Agent": "taa-dashboard-cron",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      event_type: EVENT_TYPE,
      client_payload: { trigger, triggered_at: new Date().toISOString() },
    }),
  });
  if (!response.ok) throw new Error(`GitHub dispatch failed (${response.status}): ${await response.text()}`);
}

export default {
  async scheduled(event, env) {
    if (!isEasternNinePmOnThird(new Date(event.scheduledTime))) return;
    await dispatch(env, event.cron);
  },
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("POST to trigger the monthly dashboard.\n", { status: 405 });
    if (!env.TRIGGER_TOKEN || request.headers.get("X-Trigger-Token") !== env.TRIGGER_TOKEN) {
      return new Response("Unauthorized\n", { status: 401 });
    }
    try {
      await dispatch(env, "manual");
      return new Response("Dashboard build dispatched.\n");
    } catch (error) {
      return new Response(`Dispatch failed: ${error.message}\n`, { status: 502 });
    }
  },
};
