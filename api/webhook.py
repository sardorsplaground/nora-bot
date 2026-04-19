"""
Nora — VitaFirst's Digital Supplier Sourcing Agent
Telegram Bot webhook handler for Vercel serverless deployment.
Now with AI brain (Claude) and web search (Tavily).
"""

import os
import json
import re
import datetime
import smtplib
import imaplib
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import URLError

# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "nora_vitafirst_bot")
ADMIN_CHAT_IDS = os.environ.get("ADMIN_CHAT_IDS", "").split(",")

# ── AI Config ───────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# ── Email Config ────────────────────────────────────────────────────────────
NORA_EMAIL = os.environ.get("NORA_EMAIL", "nora@vitafirst.co")
NORA_EMAIL_PASSWORD = os.environ.get("NORA_EMAIL_PASSWORD", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── Nora's system prompt ────────────────────────────────────────────────────
NORA_SYSTEM_PROMPT = """You are Nora, VitaFirst's digital supplier sourcing assistant.
You work for VitaFirst (vitafirst.co), a health & wellness brand.
Your email is nora@vitafirst.co.

Your personality:
- Professional but warm and approachable
- Concise and action-oriented
- Knowledgeable about supplements, vitamins, health products, and supply chains
- You speak in first person as a team member of VitaFirst

Your capabilities:
- Research suppliers, manufacturers, and brands using web search
- Draft professional outreach emails to suppliers
- Provide market intelligence on ingredients, pricing, and trends
- Answer questions about the supplement/health product industry
- Track tasks and provide status updates

When researching suppliers:
- Look for company names, websites, contact info, MOQs, certifications
- Prioritize GMP-certified, FDA-registered manufacturers
- Note pricing ranges when available
- Suggest outreach strategies

Format your responses for Telegram (use *bold*, _italic_, and simple formatting).
Keep responses concise — max 3-4 short paragraphs. Use bullet points for lists.
Do NOT use markdown headers (# or ##). Use *bold text* for section titles instead."""

NORA_INTRO = """👋 Hi! I'm *Nora*, VitaFirst's AI-powered supplier sourcing assistant.

Here's what I can do:
• 🔍 *Research suppliers* — I search the web and give you real results
• 🧠 *Answer questions* — ask me anything about supplements, sourcing, or market trends
• 📧 *Send & receive emails* — I have my own inbox at nora@vitafirst.co
• 📋 *Track tasks* — I keep a to-do list and report on progress

*How to use me in group chats:*
Tag me like `@{bot_username} find suppliers for vitamin D3 capsules` and I'll research it!

*Quick commands:*
/start — This welcome message
/help — Show all commands
/tasks — View current task list
/status — Get a progress report
/inbox — Check my email inbox
/sendemail — Send an email
/newcontact — Log a new supplier contact
"""


# ── Telegram API helpers ────────────────────────────────────────────────────

def tg_request(method: str, data: dict = None):
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


def send_message(chat_id: int, text: str, parse_mode: str = "Markdown", reply_to: int = None):
    if len(text) > 4000:
        text = text[:3950] + "\n\n_(message trimmed)_"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    result = tg_request("sendMessage", data)
    if not result or (result and not result.get("ok", True)):
        data["parse_mode"] = None
        result = tg_request("sendMessage", data)
    return result


def send_typing(chat_id: int):
    tg_request("sendChatAction", {"chat_id": chat_id, "action": "typing"})


# ── Web Search (Tavily) ────────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5) -> list:
    if not TAVILY_API_KEY:
        return []
    try:
        url = "https://api.tavily.com/search"
        payload = json.dumps({"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results, "include_answer": True, "search_depth": "basic"}).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        results = []
        answer = data.get("answer", "")
        if answer:
            results.append({"title": "Summary", "url": "", "content": answer})
        for r in data.get("results", [])[:max_results]:
            results.append({"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")[:500]})
        return results
    except Exception as e:
        print(f"Tavily search error: {e}")
        return []


# ── AI Brain (Claude) ──────────────────────────────────────────────────────

def ask_claude(user_message: str, search_context: str = "", user_name: str = "User") -> str:
    if not ANTHROPIC_API_KEY:
        return "🧠 AI is not configured yet. Please add an ANTHROPIC_API_KEY."
    full_message = ""
    if search_context:
        full_message += f"<search_results>\n{search_context}\n</search_results>\n\n"
    full_message += f"Message from {user_name} in the VitaFirst team Telegram:\n{user_message}"
    try:
        url = "https://api.anthropic.com/v1/messages"
        payload = json.dumps({"model": "claude-sonnet-4-6", "max_tokens": 1024, "system": NORA_SYSTEM_PROMPT, "messages": [{"role": "user", "content": full_message}]}).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"})
        with urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode())
        content = data.get("content", [])
        if content and len(content) > 0:
            return content[0].get("text", "I couldn't generate a response.")
        return "I couldn't generate a response."
    except URLError as e:
        print(f"Claude API error: {e}")
        return "⚠️ I'm having trouble connecting to my AI brain right now. Please try again."
    except Exception as e:
        print(f"Claude API error: {e}")
        return f"⚠️ AI error: {str(e)[:100]}"


def nora_think(user_message: str, user_name: str = "User", needs_search: bool = False) -> str:
    search_context = ""
    if needs_search:
        search_results = web_search(user_message, max_results=5)
        if search_results:
            parts = []
            for i, r in enumerate(search_results, 1):
                entry = f"[{i}] {r['title']}"
                if r['url']:
                    entry += f"\n    URL: {r['url']}"
                entry += f"\n    {r['content']}"
                parts.append(entry)
            search_context = "\n\n".join(parts)
    return ask_claude(user_message, search_context, user_name)


# ── Email Functions ────────────────────────────────────────────────────────

def send_email(to_addr: str, subject: str, body: str) -> dict:
    if not NORA_EMAIL_PASSWORD:
        return {"ok": False, "error": "Email not configured (missing password)"}
    try:
        msg = MIMEMultipart()
        msg["From"] = f"Nora — VitaFirst <{NORA_EMAIL}>"
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(NORA_EMAIL, NORA_EMAIL_PASSWORD)
            server.send_message(msg)
        return {"ok": True, "to": to_addr, "subject": subject}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_inbox(limit: int = 5) -> list:
    if not NORA_EMAIL_PASSWORD:
        return []
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(NORA_EMAIL, NORA_EMAIL_PASSWORD)
        mail.select("INBOX")
        _, data = mail.search(None, "ALL")
        email_ids = data[0].split()
        recent_ids = email_ids[-limit:] if len(email_ids) >= limit else email_ids
        recent_ids = list(reversed(recent_ids))
        emails = []
        for eid in recent_ids:
            _, msg_data = mail.fetch(eid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)
            subj_parts = decode_header(msg["Subject"] or "")
            subject = ""
            for part, enc in subj_parts:
                if isinstance(part, bytes):
                    subject += part.decode(enc or "utf-8", errors="replace")
                else:
                    subject += part
            from_parts = decode_header(msg["From"] or "")
            from_addr = ""
            for part, enc in from_parts:
                if isinstance(part, bytes):
                    from_addr += part.decode(enc or "utf-8", errors="replace")
                else:
                    from_addr += part
            date_str = msg["Date"] or ""
            body_preview = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_preview = payload.decode("utf-8", errors="replace")[:200]
                        break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body_preview = payload.decode("utf-8", errors="replace")[:200]
            emails.append({"from": from_addr, "subject": subject, "date": date_str, "preview": body_preview.strip()})
        mail.logout()
        return emails
    except Exception as e:
        print(f"IMAP error: {e}")
        return []


# ── Task Management ────────────────────────────────────────────────────────

class TaskStore:
    def __init__(self):
        self._tasks = {}
        self._counter = 0

    def add(self, chat_id, description, assigned_by):
        self._counter += 1
        task = {"id": self._counter, "chat_id": chat_id, "description": description, "assigned_by": assigned_by, "status": "🆕 New", "created_at": datetime.datetime.utcnow().isoformat(), "updated_at": datetime.datetime.utcnow().isoformat(), "notes": []}
        self._tasks[self._counter] = task
        return task

    def update_status(self, task_id, status, note=None):
        if task_id not in self._tasks:
            return None
        self._tasks[task_id]["status"] = status
        self._tasks[task_id]["updated_at"] = datetime.datetime.utcnow().isoformat()
        if note:
            self._tasks[task_id]["notes"].append(note)
        return self._tasks[task_id]

    def get_tasks(self, chat_id=None):
        tasks = list(self._tasks.values())
        if chat_id:
            tasks = [t for t in tasks if t["chat_id"] == chat_id]
        return tasks

    def format_tasks(self, chat_id=None):
        tasks = self.get_tasks(chat_id)
        if not tasks:
            return "📭 No tasks yet! Tag me with a task to get started."
        lines = ["📋 *Nora's Task Board*\n"]
        for t in tasks:
            lines.append(f"{t['status']} *#{t['id']}* — {t['description']}\n   _Assigned by {t['assigned_by']} • {t['created_at'][:10]}_")
        return "\n\n".join(lines)

store = TaskStore()


# ── Intent Detection ───────────────────────────────────────────────────────

def detect_intent(text):
    lower = text.lower()
    if any(kw in lower for kw in ["find", "search", "look for", "source", "supplier", "vendor", "manufacturer", "who sells", "where to buy"]):
        return "search_supplier"
    if any(kw in lower for kw in ["market", "trend", "industry", "compare", "what is the price", "how much does", "what are the best", "top ", "latest", "news about", "research"]):
        return "research"
    if any(kw in lower for kw in ["draft", "write", "compose", "outreach", "reach out", "template"]):
        return "draft"
    if any(kw in lower for kw in ["price", "quote", "cost", "negotiate", "moq"]):
        return "pricing"
    return "general"


# ── Message Handling ────────────────────────────────────────────────────────

def extract_task_from_mention(text, bot_username):
    pattern = rf"@{re.escape(bot_username)}\s*(.*)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def handle_command(command, message):
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
        new_t = sum(1 for t in tasks if "New" in t["status"])
        in_prog = sum(1 for t in tasks if "Progress" in t["status"])
        done = sum(1 for t in tasks if "Done" in t["status"])
        return f"📊 *Nora's Status Report*\n\n📌 Total: *{total}*\n🆕 New: *{new_t}*\n🔄 In Progress: *{in_prog}*\n✅ Done: *{done}*"
    elif command == "/inbox":
        send_typing(chat_id)
        emails = check_inbox(5)
        if not emails:
            return "📭 *Nora's Inbox*\n\nNo emails yet, or inbox is not configured."
        lines = ["📬 *Nora's Inbox* (latest 5)\n"]
        for i, em in enumerate(emails, 1):
            lines.append(f"*{i}.* {em['subject'][:50]}\n   _From:_ {em['from'][:40]}\n   _{em['preview'][:80]}_\n")
        return "\n".join(lines)
    elif command.startswith("/sendemail"):
        parts = command.replace("/sendemail", "").strip()
        if not parts or " — " not in parts:
            return "📧 *Send an Email as Nora*\n\nUsage:\n`/sendemail to@email.com — Subject — Body`"
        segments = parts.split(" — ", 2)
        if len(segments) < 3:
            return "❌ Use format: `/sendemail to@email.com — Subject — Body`"
        to_addr, subject, body = segments[0].strip(), segments[1].strip(), segments[2].strip()
        if "@" not in to_addr:
            return f"❌ `{to_addr}` is not a valid email."
        send_typing(chat_id)
        result = send_email(to_addr, subject, body)
        if result["ok"]:
            task = store.add(chat_id, f"📧 Sent to {to_addr}: {subject}", user_name)
            return f"✅ *Email Sent!*\n\n*To:* {to_addr}\n*Subject:* {subject}\n*From:* nora@vitafirst.co\n\n_Task #{task['id']}_"
        return f"❌ *Failed*\n\n_{result['error']}_"
    elif command.startswith("/newcontact"):
        parts = command.replace("/newcontact", "").strip()
        if not parts:
            return "📇 *Log a Contact*\n\nUsage: `/newcontact Company — email — notes`"
        task = store.add(chat_id, f"📇 New contact: {parts}", user_name)
        return f"✅ Contact logged as task *#{task['id']}*!\n\n_{parts}_"
    return None


def handle_mention(task_text, message):
    chat_id = message["chat"]["id"]
    user = message.get("from", {})
    user_name = user.get("first_name", "there")
    if not task_text:
        return f"Hi {user_name}! 👋 I'm Nora, VitaFirst's AI assistant.\n\nAsk me anything or give me a task, like:\n`@{BOT_USERNAME} find suppliers for collagen powder`\n`@{BOT_USERNAME} what's the market price for vitamin D3?`"
    intent = detect_intent(task_text)
    if intent in ("search_supplier", "research", "pricing"):
        send_typing(chat_id)
        response = nora_think(task_text, user_name, needs_search=True)
        task = store.add(chat_id, f"🔍 {task_text}", user_name)
        return f"{response}\n\n_Logged as task #{task['id']} • /tasks to view all_"
    elif intent == "draft":
        send_typing(chat_id)
        response = nora_think(task_text, user_name, needs_search=False)
        task = store.add(chat_id, f"📧 {task_text}", user_name)
        return f"{response}\n\n_Logged as task #{task['id']}_"
    else:
        send_typing(chat_id)
        lower = task_text.lower()
        needs_web = any(kw in lower for kw in ["how", "what", "when", "where", "who", "why", "which", "tell me", "explain", "?"])
        response = nora_think(task_text, user_name, needs_search=needs_web)
        return response


def process_update(update):
    message = update.get("message")
    if not message:
        return
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    chat_type = message.get("chat", {}).get("type", "private")
    if not text:
        return
    if text.startswith("/"):
        command = text.split()[0].split("@")[0]
        if command == "/sendemail":
            command = text.split("@")[0] if "@" in text.split()[0] else text
        response = handle_command(command, message)
        if response:
            send_message(chat_id, response, reply_to=message.get("message_id"))
        return
    bot_mentioned = f"@{BOT_USERNAME}".lower() in text.lower()
    if bot_mentioned:
        task_text = extract_task_from_mention(text, BOT_USERNAME)
        response = handle_mention(task_text, message)
        send_message(chat_id, response, reply_to=message.get("message_id"))
        return
    if chat_type == "private":
        response = handle_mention(text, message)
        send_message(chat_id, response)
        return


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
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
            print(f"Error: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        r = {"status": "✅ Nora is online", "bot": BOT_USERNAME, "version": "2.0.0", "ai": "Claude" if ANTHROPIC_API_KEY else "not configured", "search": "Tavily" if TAVILY_API_KEY else "not configured"}
        self.wfile.write(json.dumps(r).encode())

    def log_message(self, format, *args):
        pass
