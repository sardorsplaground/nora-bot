"""
Nora — VitaFirst's Digital Supplier Sourcing Agent
Telegram Bot webhook handler for Vercel serverless deployment.
"""

import os
import json
import re
import datetime
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlencode

# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "nora_vitafirst_bot")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")  # Optional: for AI replies
ADMIN_CHAT_IDS = os.environ.get("ADMIN_CHAT_IDS", "").split(",")  # Comma-separated

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── In-memory task store (use a DB like Supabase/Redis for production) ──────
# For Vercel serverless, tasks persist only within the function invocation.
# In production, replace with a database (Supabase, Neon, PlanetScale, etc.)
# For now, we use a KV-like approach via Vercel KV or a JSON file.

NORA_INTRO = """👋 Hi! I'm *Nora*, VitaFirst's digital supplier sourcing assistant.

Here's what I can do:
• 🔍 *Find suppliers* — tag me with a product/brand and I'll research options
• 📧 *Draft outreach messages* — I'll compose professional supplier emails
• 📋 *Track tasks* — I keep a to-do list and report on progress
• 📊 *Status updates* — ask me for a progress report anytime

*How to use me in group chats:*
Tag me like `@{bot_username} find suppliers for vitamin D3 capsules` and I'll get to work!

*Quick commands:*
/start — This welcome message
/help — Show all commands
/tasks — View current task list
/status — Get a progress report
/newcontact — Log a new supplier contact
"""


# ── Telegram API helpers ────────────────────────────────────────────────────

def tg_request(method: str, data: dict = None):
    """Make a request to the Telegram Bot API."""
    url = f"{API_BASE}/{method}"
    if data:
        payload = json.dumps(data).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    else:
        req = Request(url)
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Telegram API error: {e}")
        return None


def send_message(chat_id: int, text: str, parse_mode: str = "Markdown",
                 reply_to: int = None):
    """Send a message to a chat."""
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_to:
        data["reply_to_message_id"] = reply_to
    return tg_request("sendMessage", data)


def send_typing(chat_id: int):
    """Show typing indicator."""
    tg_request("sendChatAction", {"chat_id": chat_id, "action": "typing"})


# ── Task Management ────────────────────────────────────────────────────────
# Simple task structure. In production, back this with a real database.

class TaskStore:
    """
    Lightweight task manager.
    NOTE: In Vercel serverless, each invocation is stateless.
    For persistence, integrate with Vercel KV, Supabase, or similar.
    This class shows the interface — swap the storage backend for production.
    """

    def __init__(self):
        self._tasks = {}
        self._counter = 0

    def add(self, chat_id: int, description: str, assigned_by: str) -> dict:
        self._counter += 1
        task = {
            "id": self._counter,
            "chat_id": chat_id,
            "description": description,
            "assigned_by": assigned_by,
            "status": "🆕 New",
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "notes": [],
        }
        self._tasks[self._counter] = task
        return task

    def update_status(self, task_id: int, status: str, note: str = None) -> dict:
        if task_id not in self._tasks:
            return None
        self._tasks[task_id]["status"] = status
        self._tasks[task_id]["updated_at"] = datetime.datetime.utcnow().isoformat()
        if note:
            self._tasks[task_id]["notes"].append(note)
        return self._tasks[task_id]

    def get_tasks(self, chat_id: int = None) -> list:
        tasks = list(self._tasks.values())
        if chat_id:
            tasks = [t for t in tasks if t["chat_id"] == chat_id]
        return tasks

    def format_tasks(self, chat_id: int = None) -> str:
        tasks = self.get_tasks(chat_id)
        if not tasks:
            return "📭 No tasks yet! Tag me with a task to get started."
        lines = ["📋 *Nora's Task Board*\n"]
        for t in tasks:
            lines.append(
                f"{t['status']} *#{t['id']}* — {t['description']}\n"
                f"   _Assigned by {t['assigned_by']} • {t['created_at'][:10]}_"
            )
        return "\n\n".join(lines)


# Global store instance (resets per invocation in serverless — use DB in prod)
store = TaskStore()


# ── Message Handling ────────────────────────────────────────────────────────

def extract_task_from_mention(text: str, bot_username: str) -> str:
    """Extract the task/command after @bot_username mention."""
    pattern = rf"@{re.escape(bot_username)}\s*(.*)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def handle_command(command: str, message: dict) -> str:
    """Handle /commands."""
    chat_id = message["chat"]["id"]
    user = message.get("from", {})
    user_name = user.get("first_name", "there")

    if command == "/start" or command == "/help":
        return NORA_INTRO.replace("{bot_username}", BOT_USERNAME)

    elif command == "/tasks":
        return store.format_tasks(chat_id)

    elif command == "/status":
        tasks = store.get_tasks(chat_id)
        if not tasks:
            return "📊 *Status Report*\n\nNo active tasks. I'm ready for new assignments!"

        total = len(tasks)
        new = sum(1 for t in tasks if "New" in t["status"])
        in_progress = sum(1 for t in tasks if "Progress" in t["status"])
        done = sum(1 for t in tasks if "Done" in t["status"])

        return (
            f"📊 *Nora's Status Report*\n\n"
            f"📌 Total tasks: *{total}*\n"
            f"🆕 New: *{new}*\n"
            f"🔄 In Progress: *{in_progress}*\n"
            f"✅ Completed: *{done}*\n\n"
            f"_Last updated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_"
        )

    elif command.startswith("/newcontact"):
        parts = command.replace("/newcontact", "").strip()
        if not parts:
            return (
                "📇 *Log a New Supplier Contact*\n\n"
                "Usage: `/newcontact Company Name — contact@email.com — notes`\n\n"
                "Example:\n"
                "`/newcontact NutraVit Labs — hello@nutravit.com — Vitamin D3 supplier, MOQ 1000 units`"
            )
        task = store.add(chat_id, f"📇 New contact: {parts}", user_name)
        return f"✅ Contact logged as task *#{task['id']}*!\n\n_{parts}_"

    return None


def handle_mention(task_text: str, message: dict) -> str:
    """Handle when someone @mentions Nora with a task."""
    chat_id = message["chat"]["id"]
    user = message.get("from", {})
    user_name = user.get("first_name", "there")

    if not task_text:
        return f"Hi {user_name}! 👋 Tag me with a task, like:\n`@{BOT_USERNAME} find suppliers for collagen powder`"

    # Detect intent from the task text
    task_lower = task_text.lower()

    # Supplier search request
    if any(kw in task_lower for kw in ["find", "search", "look for", "source", "supplier", "vendor"]):
        task = store.add(chat_id, f"🔍 {task_text}", user_name)
        return (
            f"🔍 *Supplier Search Task Created!*\n\n"
            f"*Task #{task['id']}:* {task_text}\n"
            f"*Assigned by:* {user_name}\n"
            f"*Status:* 🆕 New\n\n"
            f"I'll research this and report back. Here's my plan:\n"
            f"1️⃣ Search for matching suppliers/brands\n"
            f"2️⃣ Compile contact info and MOQ details\n"
            f"3️⃣ Draft outreach messages for top matches\n"
            f"4️⃣ Report findings here\n\n"
            f"_Use /tasks to check progress_"
        )

    # Draft outreach message
    elif any(kw in task_lower for kw in ["draft", "write", "compose", "email", "message", "outreach", "reach out"]):
        task = store.add(chat_id, f"📧 {task_text}", user_name)
        return (
            f"📧 *Outreach Draft Task Created!*\n\n"
            f"*Task #{task['id']}:* {task_text}\n"
            f"*Assigned by:* {user_name}\n\n"
            f"I'll draft a professional outreach message. "
            f"Need any specific tone? (formal/friendly/brief)\n\n"
            f"_Use /tasks to check progress_"
        )

    # Price/quote request
    elif any(kw in task_lower for kw in ["price", "quote", "cost", "negotiate", "moq"]):
        task = store.add(chat_id, f"💰 {task_text}", user_name)
        return (
            f"💰 *Pricing Task Created!*\n\n"
            f"*Task #{task['id']}:* {task_text}\n"
            f"*Assigned by:* {user_name}\n\n"
            f"I'll gather pricing info and prepare a comparison.\n\n"
            f"_Use /tasks to check progress_"
        )

    # General task
    else:
        task = store.add(chat_id, f"📌 {task_text}", user_name)
        return (
            f"📌 *New Task Created!*\n\n"
            f"*Task #{task['id']}:* {task_text}\n"
            f"*Assigned by:* {user_name}\n"
            f"*Status:* 🆕 New\n\n"
            f"I'm on it! I'll update you when I have progress.\n\n"
            f"_Use /tasks to check progress_"
        )


def process_update(update: dict) -> None:
    """Process an incoming Telegram update."""
    message = update.get("message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    chat_type = message.get("chat", {}).get("type", "private")

    if not text:
        return

    # Handle /commands
    if text.startswith("/"):
        # Strip @botname from commands in group chats
        command = text.split()[0].split("@")[0]
        response = handle_command(command, message)
        if response:
            send_message(chat_id, response, reply_to=message.get("message_id"))
        return

    # Handle @mentions in group chats
    bot_mentioned = f"@{BOT_USERNAME}".lower() in text.lower()

    if bot_mentioned:
        task_text = extract_task_from_mention(text, BOT_USERNAME)
        send_typing(chat_id)
        response = handle_mention(task_text, message)
        send_message(chat_id, response, reply_to=message.get("message_id"))
        return

    # In private chats, respond to all messages
    if chat_type == "private":
        send_typing(chat_id)
        # Treat private messages as tasks or questions
        if any(kw in text.lower() for kw in ["find", "search", "source", "supplier",
                                               "draft", "write", "email", "price",
                                               "quote", "help", "status", "task"]):
            response = handle_mention(text, message)
        else:
            response = (
                f"👋 Hi! I'm Nora, your supplier sourcing assistant.\n\n"
                f"Try telling me what you need, like:\n"
                f"• _Find suppliers for organic protein powder_\n"
                f"• _Draft an outreach email to NutraVit Labs_\n"
                f"• _Get price quotes for vitamin C bulk_\n\n"
                f"Or use /help for all commands!"
            )
        send_message(chat_id, response)
        return


# ── Vercel Serverless Handler ───────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler."""

    def do_POST(self):
        """Handle incoming webhook POST from Telegram."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            update = json.loads(body.decode("utf-8"))

            process_update(update)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

        except Exception as e:
            print(f"Error processing update: {e}")
            self.send_response(200)  # Always return 200 to Telegram
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {
            "status": "✅ Nora is online",
            "bot": BOT_USERNAME,
            "version": "1.0.0",
        }
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
