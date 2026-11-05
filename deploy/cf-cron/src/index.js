const WORKFLOW_FILE = "monthly-dashboard.yml";
const NEW_YORK_ZONE = "America/New_York";

function newYorkSchedule(scheduledTime) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: NEW_YORK_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(scheduledTime));
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return {
    date: `${values.year}-${values.month}-${values.day}`,
    hour: Number(values.hour),
  };
}

function log(level, event, details) {
  const record = JSON.stringify({ service: "cpm-bull-cron", event, ...details });
  console[level](record);
}

async function dispatchMonthlyWorkflow(env, cron, sessionDate) {
  const { GH_OWNER, GH_REPO, GH_TOKEN } = env;
  if (!GH_OWNER || !GH_REPO || !GH_TOKEN) {
    const missing = ["GH_OWNER", "GH_REPO", "GH_TOKEN"].filter(name => !env[name]);
    throw new Error(`Missing Worker bindings: ${missing.join(", ")}`);
  }

  const response = await fetch(
    `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${GH_TOKEN}`,
        "User-Agent": "cpm-bull-cron-worker",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: {
          send_all_notifications: "true",
          scheduled_session_date: sessionDate,
        },
      }),
    },
  );

  if (!response.ok) {
    const body = (await response.text()).replaceAll(GH_TOKEN, "[redacted]").slice(0, 1000);
    throw new Error(`GitHub workflow dispatch failed (${response.status}): ${body || "empty response"}`);
  }

  return { owner: GH_OWNER, repo: GH_REPO, workflow: WORKFLOW_FILE, cron };
}

export default {
  async scheduled(event, env) {
    const scheduledAt = new Date(event.scheduledTime).toISOString();
    const newYork = newYorkSchedule(event.scheduledTime);
    log("info", "cron_started", {
      cron: event.cron,
      scheduled_at: scheduledAt,
      new_york_date: newYork.date,
      new_york_hour: newYork.hour,
    });
    if (newYork.hour !== 22) {
      log("info", "cron_skipped", {
        cron: event.cron,
        scheduled_at: scheduledAt,
        new_york_date: newYork.date,
        reason: "not_10pm_new_york",
      });
      return;
    }
    try {
      const result = await dispatchMonthlyWorkflow(env, event.cron, newYork.date);
      log("info", "workflow_dispatched", {
        ...result,
        scheduled_at: scheduledAt,
        new_york_date: newYork.date,
      });
    } catch (error) {
      log("error", "workflow_dispatch_failed", {
        cron: event.cron,
        scheduled_at: scheduledAt,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  },

  async fetch(request) {
    return new Response("Monthly CPM scheduler is active.\n", {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  },
};
