"""
Resend Inbound Email Webhook Handler
Receives email.received events from Resend and forwards them to Sardor via Telegram.
"""

import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen


# Config
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_IDS = os.environ.get("ADMIN_CHAT_IDS", "").split(",")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


def tg_send(chat_id, text, parse_mode="Markdown"):
    """Send a Telegram message."""
    if len(text) > 4000:
        text = text[:3950] + "\n\n_(message trimmed)_"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = Request(f"{API_BASE}/sendMessage", data=payload,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        # Retry without Markdown if it fails
        data["parse_mode"] = None
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = Request(f"{API_BASE}/sendMessage", data=payload,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode())
        except:
            print(f"Telegram send error: {e}")
            return None


def fetch_received_email(email_id):
    """Fetch full email content from Resend's Received Emails API."""
    req = Request(
        f"https://api.resend.com/emails/{email_id}",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "User-Agent": "NoraBot/2.3"
        }
    )
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Resend fetch error: {e}")
        return None


def format_email_notification(email_data):
    """Format received email as a Telegram message."""
    sender = email_data.get("from", "Unknown sender")
    to = email_data.get("to", [])
    to_str = ", ".join(to) if isinstance(to, list) else str(to)
    subject = email_data.get("subject", "(no subject)")
    text_body = email_data.get("text", "")
    html_body = email_data.get("html", "")
    date = email_data.get("created_at", "")

    # Prefer text body, fall back to a note about HTML
    body = text_body if text_body else "(HTML email — check Resend dashboard for full content)"

    # Truncate long bodies
    if len(body) > 2000:
        body = body[:2000] + "\n\n... (truncated)"

    # Check for attachments
    attachments = email_data.get("attachments", [])
    attachment_info = ""
    if attachments:
        att_names = [a.get("filename", "unnamed") for a in attachments]
        attachment_info = f"\n📎 *Attachments:* {", ".join(att_names)}"

    msg = (
        f"📨 *New Reply Received*\n"
        f"────────────────────\n"
        f"👤 *From:* {sender}\n"
        f"📩 *To:* {to_str}\n"
        f"📌 *Subject:* {subject}\n"
        f"📅 *Date:* {date}"
        f"{attachment_info}\n"
        f"────────────────────\n\n"
        f"{body}"
    )
    return msg


class handler(BaseHTTPRequestHandler):
    """Vercel serverless handler for Resend inbound webhooks."""

    def do_POST(self):
        """Handle incoming webhook POST from Resend."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)
            event = json.loads(raw_body.decode("utf-8"))

            event_type = event.get("type", "")
            print(f"Resend webhook event: {event_type}")

            if event_type == "email.received":
                email_data = event.get("data", {})
                email_id = email_data.get("id", "")

                # Fetch full email content from Resend API
                full_email = None
                if email_id and RESEND_API_KEY:
                    full_email = fetch_received_email(email_id)

                # Use full email if available, otherwise use webhook data
                source = full_email if full_email else email_data
                notification = format_email_notification(source)

                # Send to all admin chat IDs
                for chat_id in ADMIN_CHAT_IDS:
                    chat_id = chat_id.strip()
                    if chat_id:
                        tg_send(int(chat_id), notification)

            # Respond 200 to acknowledge webhook
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

        except Exception as e:
            print(f"Inbound webhook error: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "error": str(e)}).encode())

    def do_GET(self):
        """Health check."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "Nora inbound email handler active",
            "version": "1.0"
        }).encode())

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
