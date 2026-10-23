import { escapeHtml, html, page, verifyUnsubscribeToken } from "../_shared.js";

export async function onRequestGet({ request }) {
  const token = new URL(request.url).searchParams.get("token") || "";
  if (!token) return html(page("Unsubscribe unavailable", "This unsubscribe link is invalid."), 400);
  const safeToken = escapeHtml(token);
  return html(`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Unsubscribe</title><body style="font:16px/1.5 system-ui,sans-serif;max-width:560px;margin:12vh auto;padding:24px;color:#17263c"><h1>Unsubscribe from monthly TAA emails?</h1><p>Confirm to stop monthly allocation emails for this address.</p><form method="post" action="/api/unsubscribe"><input type="hidden" name="token" value="${safeToken}"><button style="padding:10px 16px">Unsubscribe</button></form></body></html>`);
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return html(page("Unsubscribe unavailable", "Please try again later."), 503);
  let token = new URL(request.url).searchParams.get("token") || "";
  if (!token) {
    const contentType = request.headers.get("Content-Type") || "";
    try {
      if (contentType.includes("application/json")) token = String((await request.json()).token || "");
      else token = String(new URLSearchParams(await request.text()).get("token") || "");
    } catch { token = ""; }
  }
  if (!token) return html(page("Unsubscribe unavailable", "This unsubscribe link is invalid."), 400);
  const subscriptionId = await verifyUnsubscribeToken(env, token);
  if (!subscriptionId) return html(page("Unsubscribe unavailable", "This unsubscribe link is invalid or expired."), 400);
  await env.DB.prepare(`UPDATE subscriptions SET status='unsubscribed', confirm_token_hash=NULL, updated_at=?
    WHERE id=?`).bind(new Date().toISOString(), subscriptionId).run();
  return html(page("Unsubscribed", "This address will no longer receive monthly TAA allocation emails."));
}
