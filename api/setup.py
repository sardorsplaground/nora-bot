"""
Setup endpoint — call once after deployment to register the webhook with Telegram.
GET /api/setup will set the webhook URL automatically.
"""

import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
VERCEL_URL = os.environ.get("VERCEL_URL", "")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Register webhook with Telegram."""
        if not BOT_TOKEN:
            self._respond(500, {"error": "TELEGRAM_BOT_TOKEN not set"})
            return

        # Determine the webhook URL
        webhook_url = f"https://{VERCEL_URL}/api/webhook"

        # Set webhook
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        data = json.dumps({
            "url": webhook_url,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
        }).encode("utf-8")

        req = Request(url, data=data, headers={"Content-Type": "application/json"})

        try:
            with urlopen(req) as resp:
                result = json.loads(resp.read().decode())

            # Also set bot commands
            commands_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands"
            commands_data = json.dumps({
                "commands": [
                    {"command": "start", "description": "Welcome message & intro"},
                    {"command": "help", "description": "Show all commands"},
                    {"command": "tasks", "description": "View current task list"},
                    {"command": "status", "description": "Get a progress report"},
                    {"command": "newcontact", "description": "Log a supplier contact"},
                ]
            }).encode("utf-8")
            commands_req = Request(commands_url, data=commands_data,
                                  headers={"Content-Type": "application/json"})
            urlopen(commands_req)

            self._respond(200, {
                "status": "Webhook registered!",
                "webhook_url": webhook_url,
                "telegram_response": result,
            })

        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def log_message(self, format, *args):
        pass
