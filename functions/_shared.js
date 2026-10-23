export function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

export function html(body, status = 200) {
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

export function randomToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export async function tokenHash(token) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

async function unsubscribeKey(secret) {
  if (!secret) throw new Error("Missing unsubscribe signing secret.");
  return crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

export async function makeUnsubscribeToken(env, subscriptionId) {
  const key = await unsubscribeKey(env.UNSUBSCRIBE_SIGNING_SECRET);
  const data = new TextEncoder().encode(subscriptionId);
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", key, data));
  const encoded = btoa(String.fromCharCode(...signature)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  return `${subscriptionId}.${encoded}`;
}

export async function verifyUnsubscribeToken(env, token) {
  const [subscriptionId, encoded, ...rest] = String(token).split(".");
  if (!subscriptionId || !encoded || rest.length) return null;
  try {
    const signature = Uint8Array.from(atob(encoded.replace(/-/g, "+").replace(/_/g, "/")), char => char.charCodeAt(0));
    const key = await unsubscribeKey(env.UNSUBSCRIBE_SIGNING_SECRET);
    const valid = await crypto.subtle.verify("HMAC", key, signature, new TextEncoder().encode(subscriptionId));
    return valid ? subscriptionId : null;
  } catch { return null; }
}

export async function sendEmail(env, message, idempotencyKey) {
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
      "User-Agent": "taa-dashboard/1.0 (+resend-api)",
    },
    body: JSON.stringify(message),
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`Resend API ${response.status}: ${body}`);
  return JSON.parse(body);
}

export const STRATEGIES = new Set([
  "CPM", "HAA-Simple", "HAA-Balanced", "BAA-G12", "AAA", "VAA-G12", "NDX", "RPV", "VAL",
]);

export function validateBlend(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > STRATEGIES.size) return null;
  const seen = new Set();
  const blend = [];
  for (const leg of value) {
    const name = leg?.name;
    const weight = Number(leg?.weight);
    if (!STRATEGIES.has(name) || seen.has(name) || !Number.isFinite(weight) || weight <= 0 || weight > 1) return null;
    seen.add(name);
    blend.push({ name, weight });
  }
  const total = blend.reduce((sum, leg) => sum + leg.weight, 0);
  return Math.abs(total - 1) < 0.0001 ? blend : null;
}

export function page(title, message) {
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(title)}</title><body style="font:16px/1.5 system-ui,sans-serif;max-width:560px;margin:12vh auto;padding:24px;color:#17263c"><h1>${escapeHtml(title)}</h1><p>${escapeHtml(message)}</p><p><a href="/">Return to the TAA dashboard</a></p></body></html>`;
}
