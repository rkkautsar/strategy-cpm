#!/usr/bin/env python
"""Send monthly signal via Resend email API.

Reads signal_message.txt and dashboard URL from environment, posts to
Resend with both plain text and HTML body. Supports attaching the
dashboard HTML if SEND_DASHBOARD_ATTACHMENT=1.

Env vars:
    RESEND_API_KEY     - required, from resend.com
    RESEND_FROM        - sender, default "CPM-NDX-VAL-RPV <onboarding@resend.dev>"
    RESEND_TO          - recipient email (required)
    DASHBOARD_URL      - link to put in email body (optional)
    SIGNAL_MESSAGE_FILE - path to formatted message (default signal_message.txt)
    DASHBOARD_FILE     - path to dashboard HTML (default dist/index.html)
    SEND_DASHBOARD_ATTACHMENT - "1" to attach dashboard HTML
"""
from __future__ import annotations
import base64
import json
import os
import sys
import urllib.request

API_URL = "https://api.resend.com/emails"


def markdown_to_html(text: str) -> str:
    """Tiny Markdown -> HTML converter for our specific message format.
    Handles: *bold*, `code`, line breaks. No external deps."""
    import html
    out = html.escape(text)
    # *bold*
    import re
    out = re.sub(r"\*([^*\n]+)\*", r"<strong>\1</strong>", out)
    # `code`
    out = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", out)
    # _italic_
    out = re.sub(r"(?<![A-Za-z0-9])_([^_\n]+)_(?![A-Za-z0-9])", r"<em>\1</em>", out)
    # Line breaks
    out = out.replace("\n", "<br>\n")
    return out


def main() -> int:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("ERR: RESEND_API_KEY not set", file=sys.stderr)
        return 1

    to_addr = os.environ.get("RESEND_TO")
    if not to_addr:
        print("ERR: RESEND_TO not set", file=sys.stderr)
        return 1

    from_addr = os.environ.get("RESEND_FROM", "CPM-NDX-VAL-RPV <onboarding@resend.dev>")
    msg_file = os.environ.get("SIGNAL_MESSAGE_FILE", "signal_message.txt")
    dashboard_url = os.environ.get("DASHBOARD_URL", "")

    if not os.path.exists(msg_file):
        print(f"ERR: message file not found: {msg_file}", file=sys.stderr)
        return 1

    with open(msg_file) as f:
        body_md = f.read()

    if dashboard_url:
        body_md += f"\n\n📊 Dashboard: {dashboard_url}"

    body_html = (
        "<div style='font-family:-apple-system,BlinkMacSystemFont,sans-serif;"
        "max-width:600px;line-height:1.5'>"
        + markdown_to_html(body_md)
        + "</div>"
    )

    # Subject: extract signal date for inbox readability
    subject = "CPM-NDX-VAL-RPV Monthly Signal"
    for line in body_md.splitlines():
        if line.startswith("Signal date:") or "Signal date" in line:
            # Pull the date out
            import re
            m = re.search(r"\d{4}-\d{2}-\d{2}", line)
            if m:
                subject = f"CPM-NDX-VAL-RPV Signal · {m.group(0)}"
            break

    payload = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body_md,
        "html": body_html,
    }

    # Optional: attach dashboard HTML
    if os.environ.get("SEND_DASHBOARD_ATTACHMENT") == "1":
        dashboard_file = os.environ.get("DASHBOARD_FILE", "dist/index.html")
        if os.path.exists(dashboard_file):
            with open(dashboard_file, "rb") as f:
                content_b64 = base64.b64encode(f.read()).decode()
            payload["attachments"] = [{
                "filename": "cpm_dashboard.html",
                "content": content_b64,
            }]
            print(f"Attaching dashboard ({os.path.getsize(dashboard_file)/1024:.1f} KB)")

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Resend is behind Cloudflare; default Python UA gets WAF-blocked (1010).
            "User-Agent": "cpm-bull-signal/1.0 (+resend-api)",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"Email sent: id={result.get('id', '?')}")
            return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERR: Resend API {e.code}: {body}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
