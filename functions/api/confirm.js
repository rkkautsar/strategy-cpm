import { escapeHtml, html, page, tokenHash } from "../_shared.js";

export async function onRequestGet({ request }) {
  const token = new URL(request.url).searchParams.get("token") || "";
  if (!token) return html(page("Confirmation unavailable", "This confirmation link is invalid or has expired."), 400);
  return html(`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Confirm subscription</title><body style="font:16px/1.5 system-ui,sans-serif;max-width:560px;margin:12vh auto;padding:24px;color:#17263c"><h1>Confirm monthly TAA emails</h1><p>Confirm this address to receive monthly allocation and trade emails.</p><form method="post" action="/api/confirm"><input type="hidden" name="token" value="${escapeHtml(token)}"><button style="padding:10px 16px">Confirm subscription</button></form></body></html>`);
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return html(page("Confirmation unavailable", "Please try again later."), 503);
  let token = new URL(request.url).searchParams.get("token") || "";
  if (!token) {
    try { token = String(new URLSearchParams(await request.text()).get("token") || ""); }
    catch { token = ""; }
  }
  if (!token) return html(page("Confirmation unavailable", "This confirmation link is invalid or has expired."), 400);
  const hash = await tokenHash(token);
  const result = await env.DB.prepare(`UPDATE subscriptions SET status='active', blend_json=pending_blend_json,
    pending_blend_json=NULL, confirm_token_hash=NULL, updated_at=?
    WHERE confirm_token_hash=? AND pending_blend_json IS NOT NULL`).bind(new Date().toISOString(), hash).run();
  if (!result.meta.changes) return html(page("Already confirmed", "This link is invalid, expired, or has already been used."), 200);
  return html(page("Subscription confirmed", "You will receive a monthly email with your blend allocation and trades versus last month."));
}
