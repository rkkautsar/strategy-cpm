import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "../deploy/cf-cron/src/index.js";

test("dispatches once at 10pm New York in summer and winter", async () => {
  const requests = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    requests.push(JSON.parse(options.body));
    return new Response(null, { status: 204 });
  };
  try {
    const env = { GH_OWNER: "owner", GH_REPO: "repo", GH_TOKEN: "test" };
    for (const date of ["2026-10-31T02:00:00Z", "2026-10-31T03:00:00Z", "2026-12-31T02:00:00Z", "2026-12-31T03:00:00Z"]) {
      await worker.scheduled({ scheduledTime: Date.parse(date), cron: "test" }, env);
    }
    assert.deepEqual(requests.map(request => request.inputs.scheduled_session_date), ["2026-10-30", "2026-12-30"]);
  } finally {
    globalThis.fetch = original;
  }
});

test("reports a GitHub dispatch failure", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response('{"message":"Bad credentials"}', { status: 401 });
  try {
    await assert.rejects(worker.scheduled({ scheduledTime: Date.parse("2026-10-31T02:00:00Z"), cron: "test" }, {
      GH_OWNER: "owner", GH_REPO: "repo", GH_TOKEN: "test",
    }), /401.*Bad credentials/);
  } finally {
    globalThis.fetch = original;
  }
});
