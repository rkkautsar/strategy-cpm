import { escapeHtml, json, makeUnsubscribeToken, sendEmail, validateBlend } from "../../_shared.js";

function combineBlend(blend, targets, field) {
  const combined = {};
  for (const leg of blend) {
    const state = targets[leg.name];
    if (!state || !state[field] || typeof state[field] !== "object") throw new Error(`Missing ${field} targets for ${leg.name}.`);
    for (const [ticker, weight] of Object.entries(state[field])) {
      const number = Number(weight);
      if (!Number.isFinite(number) || number < 0) throw new Error(`Invalid target for ${ticker}.`);
      combined[ticker] = (combined[ticker] || 0) + leg.weight * number;
    }
  }
  return combined;
}

function percent(value) { return `${(value * 100).toFixed(1)}%`; }
function points(value) { return `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)} pp`; }

function renderMessage(blend, current, previous, currentDate, previousDate, dashboardUrl, unsubscribeUrl) {
  const holdings = Object.entries(current).filter(([, weight]) => weight > 0.0001).sort((a, b) => b[1] - a[1]);
  const action = item => item.before <= 0.001 ? "BUY" : item.after <= 0.001 ? "SELL" : item.delta > 0 ? "ADD" : "TRIM";
  const changes = [...new Set([...Object.keys(current), ...Object.keys(previous)])]
    .map(ticker => ({ ticker, before: previous[ticker] || 0, after: current[ticker] || 0 }))
    .map(item => ({ ...item, delta: item.after - item.before }))
    .filter(item => Math.abs(item.delta) > 0.001)
    .sort((a, b) => {
      const order = { SELL: 0, BUY: 1, TRIM: 2, ADD: 3 };
      return order[action(a)] - order[action(b)] || Math.abs(b.delta) - Math.abs(a.delta) || a.ticker.localeCompare(b.ticker);
    });
  const blendLabel = blend.map(leg => `${leg.name} ${Math.round(leg.weight * 100)}%`).join(" · ");
  const monthLabel = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${currentDate}T00:00:00Z`));
  const previousLabel = previousDate ? `Compared with ${previousDate}` : "First signal in the available history";
  const actionText = item => `${action(item)} ${item.ticker} · ${percent(item.before)} → ${percent(item.after)} · ${points(item.delta)}`;
  const text = [
    `TAA MONTHLY BRIEF  |  ${monthLabel.toUpperCase()}`,
    `Your allocation is ready. Signal date: ${currentDate}.`,
    `YOUR BLEND  ${blendLabel}`,
    "",
    `WHAT TO HOLD THIS MONTH  ·  ${currentDate}`,
    ...(holdings.length ? holdings.map(([ticker, weight]) => `  ${ticker.padEnd(8)} ${percent(weight).padStart(7)}`) : ["  No active holdings"]),
    "",
    `WHAT CHANGED  ·  ${previousLabel}`,
    ...(previousDate && changes.length ? changes.map(item => `  ${actionText(item)}`) : [previousDate ? "  No target changes. Keep last month's targets." : "  No prior signal is available for comparison."]),
    "",
    "Changes are target-weight percentage points, not share counts.",
    "Use your portfolio value and execution prices to calculate order sizes.",
    "",
    `OPEN THE DASHBOARD  ${dashboardUrl}`,
    `UNSUBSCRIBE  ${unsubscribeUrl}`,
  ].join("\n");
  const holdingRows = holdings.length ? holdings.map(([ticker, weight], index) => `<tr style="background:${index % 2 ? "#f7f9fc" : "#ffffff"}"><td style="padding:12px 14px;border-bottom:1px solid #e9eef4;font-weight:700;color:#17263c">${escapeHtml(ticker)}</td><td style="padding:12px 14px;border-bottom:1px solid #e9eef4;text-align:right;font-size:17px;font-weight:750;color:#126d78">${percent(weight)}</td></tr>`).join("") : `<tr><td colspan="2" style="padding:14px;color:#68778b">No active holdings for this signal.</td></tr>`;
  const tradeRows = previousDate && changes.length ? changes.map(item => {
    const kind = action(item);
    const colors = kind === "BUY" || kind === "ADD" ? ["#e7f5f2", "#126d60"] : ["#fbefef", "#a14343"];
    return `<tr><td style="padding:11px 10px;border-bottom:1px solid #e9eef4"><span style="display:inline-block;padding:3px 7px;border-radius:999px;background:${colors[0]};color:${colors[1]};font-size:10px;font-weight:800;letter-spacing:.04em">${kind}</span> <strong style="margin-left:4px">${escapeHtml(item.ticker)}</strong></td><td style="padding:11px 10px;border-bottom:1px solid #e9eef4;text-align:right;white-space:nowrap">${percent(item.before)} <span style="color:#98a5b4">→</span> <strong>${percent(item.after)}</strong><br><span style="font-size:11px;color:${colors[1]};font-weight:700">${points(item.delta)}</span></td></tr>`;
  }).join("") : `<tr><td colspan="2" style="padding:14px;color:#68778b">${previousDate ? "No target changes this month. Keep last month's targets." : "No prior signal is available for comparison."}</td></tr>`;
  const blendPills = blend.map(leg => `<span style="display:inline-block;margin:3px 5px 3px 0;padding:5px 9px;border:1px solid #dce8ed;border-radius:999px;background:#f7fbfc;color:#294556;font-size:12px;font-weight:650">${escapeHtml(leg.name)} ${Math.round(leg.weight * 100)}%</span>`).join("");
  const safeDashboard = escapeHtml(dashboardUrl);
  const safeUnsubscribe = escapeHtml(unsubscribeUrl);
  const htmlBody = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><body style="margin:0;padding:0;background:#f2f5f8;font-family:Arial,Helvetica,sans-serif;color:#17263c"><div style="display:none;max-height:0;overflow:hidden;opacity:0">Your monthly holdings and trades versus the previous allocation.</div><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f2f5f8;padding:24px 10px"><tr><td align="center"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#fff;border:1px solid #e5ebf1;border-radius:16px;overflow:hidden"><tr><td style="padding:26px 26px 22px;background:#173247;color:#fff"><div style="font-size:11px;font-weight:800;letter-spacing:.13em;color:#87d2d1">TACTICAL ASSET ALLOCATION</div><h1 style="margin:9px 0 4px;font-size:25px;line-height:1.2;color:#fff">Your allocation is ready</h1><div style="font-size:14px;color:#d4e0e8">${escapeHtml(monthLabel)} <span style="color:#87d2d1">·</span> Signal date ${escapeHtml(currentDate)}</div></td></tr><tr><td style="padding:20px 26px 4px"><div style="margin-bottom:6px;color:#68778b;font-size:11px;font-weight:800;letter-spacing:.08em">YOUR BLEND</div>${blendPills}<div style="margin-top:11px;color:#68778b;font-size:12px">${escapeHtml(previousLabel)}</div></td></tr><tr><td style="padding:20px 26px 4px"><h2 style="margin:0 0 9px;font-size:17px">What to hold this month</h2><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e9eef4;border-radius:10px;overflow:hidden"><thead><tr style="background:#f4f7fa"><th align="left" style="padding:8px 14px;color:#68778b;font-size:10px;letter-spacing:.08em">ASSET</th><th align="right" style="padding:8px 14px;color:#68778b;font-size:10px;letter-spacing:.08em">TARGET</th></tr></thead><tbody>${holdingRows}</tbody></table></td></tr><tr><td style="padding:21px 26px 3px"><h2 style="margin:0 0 9px;font-size:17px">Trades versus last month</h2><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e9eef4;border-radius:10px;overflow:hidden"><thead><tr style="background:#f4f7fa"><th align="left" style="padding:8px 10px;color:#68778b;font-size:10px;letter-spacing:.08em">ACTION</th><th align="right" style="padding:8px 10px;color:#68778b;font-size:10px;letter-spacing:.08em">PRIOR → TARGET · CHANGE</th></tr></thead><tbody>${tradeRows}</tbody></table></td></tr><tr><td style="padding:19px 26px 2px;color:#68778b;font-size:12px;line-height:1.5">Changes are target-weight percentage points, not share counts. Use your portfolio value and execution prices to calculate order sizes.</td></tr><tr><td align="center" style="padding:20px 26px 23px"><a href="${safeDashboard}" style="display:inline-block;padding:12px 20px;border-radius:9px;background:#147d8b;color:#fff;text-decoration:none;font-size:13px;font-weight:750">View the TAA dashboard</a></td></tr><tr><td style="padding:15px 26px;background:#f7f9fb;border-top:1px solid #e9eef4;color:#68778b;font-size:11px;line-height:1.5">You receive this because you subscribed to monthly allocation emails. <a href="${safeUnsubscribe}" style="color:#506579;text-decoration:underline">Unsubscribe</a>.</td></tr></table><div style="padding:12px;color:#98a5b4;font-size:10px">Monthly target allocations from your saved strategy blend.</div></td></tr></table></body></html>`;
  return { text, html: htmlBody, subject: `Your TAA blend · ${monthLabel} allocation` };
}

export async function onRequestPost({ request, env }) {
  const authorization = request.headers.get("Authorization") || "";
  if (!env.NOTIFICATION_DISPATCH_TOKEN || authorization !== `Bearer ${env.NOTIFICATION_DISPATCH_TOKEN}`) {
    return json({ error: "Unauthorized." }, 401);
  }
  if (!env.DB || !env.RESEND_API_KEY || !env.RESEND_FROM || !env.UNSUBSCRIBE_SIGNING_SECRET) return json({ error: "Notification service is not configured." }, 503);
  let data;
  try { data = await request.json(); } catch { return json({ error: "Invalid notification payload." }, 400); }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(data?.as_of || "") || !data.targets || typeof data.targets !== "object") {
    return json({ error: "Payload must include as_of and targets." }, 400);
  }
  const targetEmail = data.target_email == null ? "" : String(data.target_email).trim().toLowerCase();
  if (data.target_email != null && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(targetEmail)) {
    return json({ error: "target_email must be a valid email address." }, 400);
  }
  const month = data.as_of.slice(0, 7);
  const dashboardUrl = env.DASHBOARD_URL || new URL(request.url).origin;
  const users = targetEmail
    ? await env.DB.prepare("SELECT id, email, blend_json FROM subscriptions WHERE status='active' AND lower(email)=?").bind(targetEmail).all()
    : await env.DB.prepare("SELECT id, email, blend_json FROM subscriptions WHERE status='active'").all();
  let sent = 0;
  let skipped = 0;
  const errors = [];
  for (const subscription of users.results || []) {
    const delivered = await env.DB.prepare("SELECT 1 FROM deliveries WHERE subscription_id=? AND month=?")
      .bind(subscription.id, month).first();
    if (delivered) { skipped += 1; continue; }
    try {
      const blend = validateBlend(JSON.parse(subscription.blend_json));
      if (!blend) throw new Error("Saved blend is invalid.");
      const current = combineBlend(blend, data.targets, "current");
      const previous = combineBlend(blend, data.targets, "previous");
      const dates = blend.map(leg => data.targets[leg.name].current_date).filter(Boolean).sort();
      const previousDates = blend.map(leg => data.targets[leg.name].previous_date).filter(Boolean).sort();
      const currentDate = dates.at(-1) || data.as_of;
      const previousDate = previousDates.at(-1) || null;
      const unsubscribeUrl = new URL("/api/unsubscribe", dashboardUrl);
      unsubscribeUrl.searchParams.set("token", await makeUnsubscribeToken(env, subscription.id));
      const message = renderMessage(blend, current, previous, currentDate, previousDate, dashboardUrl, unsubscribeUrl.toString());
      const result = await sendEmail(env, {
        from: env.RESEND_FROM,
        to: [subscription.email],
        subject: message.subject,
        text: message.text,
        html: message.html,
        headers: {
          "List-Unsubscribe": `<${unsubscribeUrl.toString()}>`,
          "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
      }, `taa-monthly-${subscription.id}-${month}`);
      await env.DB.prepare("INSERT OR IGNORE INTO deliveries (subscription_id, month, sent_at, resend_id) VALUES (?, ?, ?, ?)")
        .bind(subscription.id, month, new Date().toISOString(), result.id || null).run();
      sent += 1;
    } catch (error) {
      console.error(`Monthly notification failed for ${subscription.id}`, error.message?.split(":")[0] || "unknown error");
      errors.push(subscription.id);
    }
  }
  return json({ month, sent, skipped, errors }, errors.length ? 502 : 200);
}
