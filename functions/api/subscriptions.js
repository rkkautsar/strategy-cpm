import { escapeHtml, html, json, randomToken, sendEmail, tokenHash, validateBlend } from "../_shared.js";

export async function onRequestPost({ request, env }) {
  if (!env.DB || !env.RESEND_API_KEY || !env.RESEND_FROM) {
    return json({ error: "Email subscriptions are not configured yet." }, 503);
  }
  let input;
  try { input = await request.json(); } catch { return json({ error: "Invalid request." }, 400); }
  const email = String(input?.email || "").trim().toLowerCase();
  const blend = validateBlend(input?.blend);
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || !blend) {
    return json({ error: "Enter a valid email and a blend totaling 100%." }, 400);
  }

  const now = new Date().toISOString();
  const existing = await env.DB.prepare("SELECT id, confirmation_sent_at FROM subscriptions WHERE email = ?")
    .bind(email).first();
  if (existing && Date.now() - Date.parse(existing.confirmation_sent_at) < 10 * 60 * 1000) {
    return json({ message: "If this address can receive mail, a confirmation email is on its way." }, 202);
  }

  const id = existing?.id || crypto.randomUUID();
  const confirmToken = randomToken();
  const confirmHash = await tokenHash(confirmToken);
  await env.DB.prepare(`INSERT INTO subscriptions
    (id, email, blend_json, pending_blend_json, status, confirm_token_hash, confirmation_sent_at, created_at, updated_at)
    VALUES (?, ?, NULL, ?, 'pending', ?, ?, ?, ?)
    ON CONFLICT(email) DO UPDATE SET pending_blend_json=excluded.pending_blend_json,
      status=CASE WHEN subscriptions.status='active' THEN 'active' ELSE 'pending' END,
      confirm_token_hash=excluded.confirm_token_hash,
      confirmation_sent_at=excluded.confirmation_sent_at, updated_at=excluded.updated_at`)
    .bind(id, email, JSON.stringify(blend), confirmHash, now, now, now).run();

  const confirmUrl = new URL("/api/confirm", new URL(request.url).origin);
  confirmUrl.searchParams.set("token", confirmToken);
  const safeUrl = escapeHtml(confirmUrl.toString());
  try {
    await sendEmail(env, {
      from: env.RESEND_FROM,
      to: [email],
      subject: "Confirm your monthly TAA allocation emails",
      text: `Confirm your email to receive monthly allocations for ${blend.map(leg => `${leg.name} ${Math.round(leg.weight * 100)}%`).join(" / ")}:\n\n${confirmUrl}\n\nIf you did not request this, ignore this email.`,
      html: `<div style="font:16px/1.5 system-ui,sans-serif;max-width:560px"><h1>Confirm monthly TAA emails</h1><p>Confirm this address to receive monthly allocation and trade emails for your blend:</p><p>${blend.map(leg => `${escapeHtml(leg.name)} ${Math.round(leg.weight * 100)}%`).join(" · ")}</p><p><a href="${safeUrl}">Confirm subscription</a></p><p>If you did not request this, ignore this email.</p></div>`,
    }, `taa-confirm-${id}-${confirmHash.slice(0, 24)}`);
  } catch (error) {
    console.error("Confirmation email failed", error.message?.split(":")[0] || "unknown error");
    return json({ error: "Could not send the confirmation email. Please try again later." }, 502);
  }
  return json({ message: "Check your inbox and confirm the subscription." }, 202);
}

export async function onRequestGet() {
  return html("<!doctype html>" + `<meta charset="utf-8"><title>Method not allowed</title><p>Submit your email and blend from the dashboard.</p>`, 405);
}
