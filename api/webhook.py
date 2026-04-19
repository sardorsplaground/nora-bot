"""
Nora â VitaFirst's Digital Supplier Sourcing Agent
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

# ââ Config ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "nora_vitafirst_bot")
ADMIN_CHAT_IDS = os.environ.get("ADMIN_CHAT_IDS", "").split(",")

# ââ AI Config âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# ââ Email Config ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
NORA_EMAIL = os.environ.get("NORA_EMAIL", "nora@vitafirst.co")
NORA_EMAIL_PASSWORD = os.environ.get("NORA_EMAIL_PASSWORD", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ââ Nora's system prompt ââââââââââââââââââââââââââââââââââââââââââââââââââââ
NORA_SYSTEM_PROMPT = """You are Nora, VitaFirst's digital supplier sourcing assistant.
You work for VitaFirst (vitafirst.co).

About VitaFirst:
- The largest distributor of sports nutrition and supplements in Uzbekistan
- Operating since 2014 (10+ years in the market)
- Partners with major international brands including Ultimate Nutrition and others
- Strong distribution network across Uzbekistan with proven track record
- Always looking to expand our portfolio with quality suppliers

Your email is nora@vitafirst.co.

Your personality:
- Professional, confident, and concise
- Action-oriented â get to the point fast
- Knowledgeable about supplements, vitamins, health products, and supply chains
- You speak in first person as a team member of VitaFirst

Your capabilities:
- Research suppliers, manufacturers, and brands using web search
- Draft professional outreach emails to suppliers
- Provide market intelligence on ingredients, pricing, and trends
- Answer questions about the supplement/health product industry
- Track tasks and provide status updates

When drafting outreach emails:
- Keep emails SHORT: 4-6 sentences max, no fluff
- Always mention VitaFirst is the largest sports nutrition distributor in Uzbekistan (since 2014)
- Mention we work with brands like Ultimate Nutrition to build credibility
- Make the supplier WANT to work with us â we bring volume and market access
- End with a clear call to action (schedule a call, send catalog, share pricing)
- Professional but not overly formal â be direct and business-like

When researching suppliers:
- Look for company names, websites, contact info, MOQs, certifications
- Prioritize GMP-certified, FDA-registered manufacturers
- Note pricing ranges when available
- Suggest outreach strategies

Format your responses for Telegram (use *bold*, _italic_, and simple formatting).
Keep responses concise â max 3-4 short paragraphs. Use bullet points for lists.
Do NOT use markdown headers (# or ##). Use *bold text* for section titles instead."""

NORA_INTRO = """ð Hi! I'm *Nora*, VitaFirst's AI-powered supplier sourcing assistant.

Here's what I can do:
â¢ ð *Research suppliers* â I search the web and give you real results
â¢ ð§  *Answer questions* â ask me anything about supplements, sourcing, or market trends
â¢ ð§ *Send & receive emails* â I have my own inbox at nora@vitafirst.co
â¢ ð *Track tasks* â I keep a to-do list and report on progress

*How to use me in group chats:*
Tag me like `@{bot_username} find suppliers for vitamin D3 capsules` and I'll research it!

*Quick commands:*
/start â This welcome message
/help â Show all commands
/tasks â View current task list
/status â Get a progress report
/inbox â Check my email inbox
/sendemail â Send an email
/newcontact â Log a new supplier contact
"""


# ââ Telegram API helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââ

def tg_request(method: str, data: dict = None):
    """Make a request to the Telegram Bot API."""
    url = f"{API_BASE}/{method}"
    if data:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
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
                 reply_to: int = None, reply_markup: dict = None):
    """Send a message to a chat, optionally with inline keyboard buttons."""
    # Telegram has a 4096 char limit â split if needed
    if len(text) > 4000:
        text = text[:3950] + "\n\n_(message trimmed)_"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_to:
        data["reply_to_message_id"] = reply_to
    if reply_markup:
        data["reply_markup"] = reply_markup
    result = tg_request("sendMessage", data)
    # If Markdown fails, retry without parse_mode
    if not result or (result and not result.get("ok", True)):
        data["parse_mode"] = None
        result = tg_request("sendMessage", data)
    return result


def answer_callback(callback_query_id: str, text: str = ""):
    """Answer a callback query (acknowledge button press)."""
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
    return tg_request("answerCallbackQuery", data)


def edit_message(chat_id: int, message_id: int, text: str,
                 parse_mode: str = "Markdown", reply_markup: dict = None):
    """Edit an existing message."""
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    result = tg_request("editMessageText", data)
    if not result or (result and not result.get("ok", True)):
        data["parse_mode"] = None
        result = tg_request("editMessageText", data)
    return result


def send_typing(chat_id: int):
    """Show typing indicator."""
    tg_request("sendChatAction", {"chat_id": chat_id, "action": "typing"})


# ââ Web Search (Tavily) ââââââââââââââââââââââââââââââââââââââââââââââââââââ

def web_search(query: str, max_results: int = 5) -> list:
    """Search the web using Tavily API. Returns list of {title, url, content}."""
    if not TAVILY_API_KEY:
        print("Tavily API key not configured")
        return []
    try:
        url = "https://api.tavily.com/search"
        payload = json.dumps({
            "api_key": TAVILY_API_KEY,
            "query": query,
            "max_results": max_results,
            "include_answer": True,
            "search_depth": "basic",
        }).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        results = []
        # Include the AI-generated answer if available
        answer = data.get("answer", "")
        if answer:
            results.append({"title": "Summary", "url": "", "content": answer})
        # Include individual results
        for r in data.get("results", [])[:max_results]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:500],
            })
        return results
    except Exception as e:
        print(f"Tavily search error: {e}")
        return []


# ââ AI Brain (Claude) ââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def ask_claude(user_message: str, search_context: str = "",
               user_name: str = "User") -> str:
    """Send a message to Claude API and get a response."""
    if not ANTHROPIC_API_KEY:
        return "ð§  AI is not configured yet. Please add an ANTHROPIC_API_KEY."

    # Build the message with search context if available
    full_message = ""
    if search_context:
        full_message += f"<search_results>\n{search_context}\n</search_results>\n\n"
    full_message += f"Message from {user_name} in the VitaFirst team Telegram:\n{user_message}"

    try:
        url = "https://api.anthropic.com/v1/messages"
        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 1024,
            "system": NORA_SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": full_message}
            ],
        }).encode("utf-8")
        req = Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        })
        with urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode())

        # Extract text from response
        content = data.get("content", [])
        if content and len(content) > 0:
            return content[0].get("text", "I couldn't generate a response.")
        return "I couldn't generate a response."
    except URLError as e:
        err_body = ""
        if hasattr(e, 'read'):
            try:
                err_body = e.read().decode()
            except Exception:
                pass
        print(f"Claude API error: {e} | Body: {err_body}")
        return "â ï¸ I'm having trouble connecting to my AI brain right now. Please try again in a moment."
    except Exception as e:
        err_body = ""
        if hasattr(e, 'read'):
            try:
                err_body = e.read().decode()
            except Exception:
                pass
        print(f"Claude API error: {e} | Body: {err_body}")
        return f"â ï¸ AI error: {str(e)[:100]}"


def nora_think(user_message: str, user_name: str = "User",
               needs_search: bool = False) -> str:
    """
    Nora's main thinking function.
    Optionally searches the web first, then asks Claude to synthesize.
    """
    search_context = ""

    if needs_search:
        # Build a good search query
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


# ââ Email Functions ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def send_email(to_addr: str, subject: str, body: str) -> dict:
    """Send an email from Nora's inbox via SMTP."""
    if not NORA_EMAIL_PASSWORD:
        return {"ok": False, "error": "Email not configured (missing password)"}
    try:
        msg = MIMEMultipart()
        msg["From"] = f"Nora â VitaFirst <{NORA_EMAIL}>"
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
    """Check Nora's inbox for recent emails via IMAP."""
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

            emails.append({
                "from": from_addr,
                "subject": subject,
                "date": date_str,
                "preview": body_preview.strip(),
            })

        mail.logout()
        return emails
    except Exception as e:
        print(f"IMAP error: {e}")
        return []


# ââ Task Management ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class TaskStore:
    """Lightweight task manager (stateless in serverless â use DB in prod)."""

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
            "status": "ð New",
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
            return "ð­ No tasks yet! Tag me with a task to get started."
        lines = ["ð *Nora's Task Board*\n"]
        for t in tasks:
            lines.append(
                f"{t['status']} *#{t['id']}* â {t['description']}\n"
                f"   _Assigned by {t['assigned_by']} â¢ {t['created_at'][:10]}_"
            )
        return "\n\n".join(lines)


store = TaskStore()

# ââ Pending Email Drafts (in-memory, keyed by chat_id) ââââââââââââââââââââ
# In serverless this resets per cold start, but survives within a warm instance.
# Structure: { chat_id: { "to": str, "subject": str, "body": str, "msg_id": int } }
_pending_drafts = {}


def _parse_draft_from_message(text: str) -> dict:
    """Parse TO, SUBJECT, and BODY from a draft preview message.
    Used as fallback when _pending_drafts is lost after a cold start."""
    if not text:
        return None
    to_addr = ""
    subject = ""
    body = ""
    for line in text.split("\n"):
        stripped = line.strip()
        # Handle both Markdown (*To:*) and plain (To:) formats
        clean = stripped.replace("*", "")
        if clean.lower().startswith("to:"):
            to_addr = clean.split(":", 1)[1].strip()
        elif clean.lower().startswith("subject:"):
            subject = clean.split(":", 1)[1].strip()
    # Extract body between --- markers
    parts = text.split("---")
    if len(parts) >= 3:
        body = parts[1].strip()
    elif len(parts) >= 2:
        body = parts[1].strip()
    if not body:
        return None
    return {"to": to_addr, "subject": subject, "body": body, "msg_id": None}


# ââ Intent Detection âââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def detect_intent(text: str) -> str:
    """Detect what the user wants Nora to do."""
    lower = text.lower()

    # Supplier/product search â needs web search
    if any(kw in lower for kw in ["find", "search", "look for", "source",
                                   "supplier", "vendor", "manufacturer",
                                   "who sells", "where to buy", "where can i"]):
        return "search_supplier"

    # Market research / general questions needing web
    if any(kw in lower for kw in ["market", "trend", "industry", "compare",
                                   "what is the price", "how much does",
                                   "what are the best", "top ", "latest",
                                   "news about", "research"]):
        return "research"

    # Draft outreach
    if any(kw in lower for kw in ["draft", "write", "compose", "outreach",
                                   "reach out", "template"]):
        return "draft"

    # Price/quote
    if any(kw in lower for kw in ["price", "quote", "cost", "negotiate", "moq"]):
        return "pricing"

    # General question â use AI but no search needed
    return "general"


# ââ Message Handling ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

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
            return "ð *Status Report*\n\nNo active tasks. I'm ready for new assignments!"
        total = len(tasks)
        new = sum(1 for t in tasks if "New" in t["status"])
        in_progress = sum(1 for t in tasks if "Progress" in t["status"])
        done = sum(1 for t in tasks if "Done" in t["status"])
        return (
            f"ð *Nora's Status Report*\n\n"
            f"ð Total tasks: *{total}*\n"
            f"ð New: *{new}*\n"
            f"ð In Progress: *{in_progress}*\n"
            f"â Completed: *{done}*\n\n"
            f"_Last updated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_"
        )

    elif command == "/inbox":
        send_typing(chat_id)
        emails = check_inbox(5)
        if not emails:
            return "ð­ *Nora's Inbox*\n\nNo emails yet, or inbox is not configured."
        lines = ["ð¬ *Nora's Inbox* (latest 5)\n"]
        for i, em in enumerate(emails, 1):
            subj = em["subject"][:50] or "(no subject)"
            sender = em["from"][:40]
            preview = em["preview"][:80]
            lines.append(
                f"*{i}.* {subj}\n"
                f"   _From:_ {sender}\n"
                f"   _{preview}{'...' if len(em['preview']) > 80 else ''}_\n"
            )
        return "\n".join(lines)

    elif command.startswith("/sendemail"):
        parts = command.replace("/sendemail", "").strip()
        if not parts or " â " not in parts:
            return (
                "ð§ *Send an Email as Nora*\n\n"
                "Usage:\n`/sendemail to@email.com â Subject line â Email body text`\n\n"
                "Example:\n"
                "`/sendemail hello@nutravit.com â VitaFirst Partnership Inquiry â "
                "Hi, I'm reaching out from VitaFirst regarding a potential partnership "
                "for vitamin D3 supply. Could we schedule a call?`"
            )
        segments = parts.split(" â ", 2)
        if len(segments) < 3:
            return "â Please use the format: `/sendemail to@email.com â Subject â Body`"
        to_addr = segments[0].strip()
        subject = segments[1].strip()
        body = segments[2].strip()

        if "@" not in to_addr or "." not in to_addr:
            return f"â `{to_addr}` doesn't look like a valid email address."

        send_typing(chat_id)
        result = send_email(to_addr, subject, body)
        if result["ok"]:
            task = store.add(chat_id, f"ð§ Sent email to {to_addr}: {subject}", user_name)
            return (
                f"â *Email Sent!*\n\n"
                f"*To:* {to_addr}\n"
                f"*Subject:* {subject}\n"
                f"*From:* nora@vitafirst.co\n\n"
                f"_Logged as task #{task['id']}_"
            )
        else:
            return f"â *Failed to send email*\n\n_{result['error']}_"

    elif command.startswith("/newcontact"):
        parts = command.replace("/newcontact", "").strip()
        if not parts:
            return (
                "ð *Log a New Supplier Contact*\n\n"
                "Usage: `/newcontact Company Name â contact@email.com â notes`\n\n"
                "Example:\n"
                "`/newcontact NutraVit Labs â hello@nutravit.com â Vitamin D3 supplier, MOQ 1000 units`"
            )
        task = store.add(chat_id, f"ð New contact: {parts}", user_name)
        return f"â Contact logged as task *#{task['id']}*!\n\n_{parts}_"

    return None


def handle_mention(task_text: str, message: dict) -> str:
    """Handle when someone @mentions Nora with a task or question."""
    chat_id = message["chat"]["id"]
    user = message.get("from", {})
    user_name = user.get("first_name", "there")

    if not task_text:
        return (f"Hi {user_name}! ð I'm Nora, VitaFirst's AI assistant.\n\n"
                f"Ask me anything or give me a task, like:\n"
                f"`@{BOT_USERNAME} find suppliers for collagen powder`\n"
                f"`@{BOT_USERNAME} what's the market price for vitamin D3?`")

    intent = detect_intent(task_text)

    # For search/research intents, search the web first then use AI
    if intent in ("search_supplier", "research", "pricing"):
        send_typing(chat_id)
        response = nora_think(task_text, user_name, needs_search=True)
        task = store.add(chat_id, f"ð {task_text}", user_name)
        return f"{response}\n\n_Logged as task #{task['id']} â¢ /tasks to view all_"

    # For drafting / outreach â parallel: search for contact email + draft email
    elif intent == "draft":
        send_typing(chat_id)

        # 1) Search for contact email in parallel with drafting
        contact_results = web_search(f"{task_text} contact email address", max_results=3)
        contact_context = ""
        if contact_results:
            parts = []
            for i, r in enumerate(contact_results, 1):
                entry = f"[{i}] {r['title']}"
                if r['url']:
                    entry += f"\n    URL: {r['url']}"
                entry += f"\n    {r['content']}"
                parts.append(entry)
            contact_context = "\n\n".join(parts)

        # 2) Ask Claude to draft the email AND extract the best contact email
        draft_prompt = (
            f"{task_text}\n\n"
            f"Based on the above request, please:\n"
            f"1. Identify the best email address to send this to from the search results.\n"
            f"2. Draft a SHORT outreach email (4-6 sentences MAX) from Nora at VitaFirst.\n\n"
            f"IMPORTANT EMAIL GUIDELINES:\n"
            f"- VitaFirst is the LARGEST sports nutrition distributor in Uzbekistan (since 2014)\n"
            f"- We partner with brands like Ultimate Nutrition â mention this for credibility\n"
            f"- Keep it SHORT and punchy â no long intros or filler paragraphs\n"
            f"- Make the supplier want to work with us (volume, market access, proven track record)\n"
            f"- End with a clear CTA: schedule a call, send catalog, or share pricing\n"
            f"- Sign off as: Nora, Supplier Relations, VitaFirst\n\n"
            f"Format your response EXACTLY like this:\n"
            f"TO: recipient@example.com\n"
            f"SUBJECT: Your subject line here\n"
            f"---\n"
            f"The email body here.\n"
            f"---\n"
            f"NOTES: Any brief notes about why you chose this contact."
        )
        draft_response = ask_claude(draft_prompt, contact_context, user_name)

        # 3) Parse the draft
        to_addr = ""
        subject = ""
        body = ""
        notes = ""

        for line in draft_response.split("\n"):
            if line.strip().upper().startswith("TO:"):
                to_addr = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("SUBJECT:"):
                subject = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("NOTES:"):
                notes = line.split(":", 1)[1].strip()

        # Extract body between --- markers
        parts = draft_response.split("---")
        if len(parts) >= 3:
            body = parts[1].strip()
        elif len(parts) >= 2:
            body = parts[1].strip()

        if not body:
            # Fallback: just use the whole response as the draft
            return f"{draft_response}\n\n_I couldn't parse this into a sendable email. Could you try again with more specific instructions?_"

        # 4) Store the pending draft and present with buttons
        preview = (
            f"ð§ *Email Draft*\n\n"
            f"*To:* {to_addr or '(no email found â please reply with the address)'}\n"
            f"*Subject:* {subject}\n\n"
            f"---\n{body}\n---"
        )
        if notes:
            preview += f"\n\nð¡ _{notes}_"

        buttons = {
            "inline_keyboard": [
                [
                    {"text": "â Send", "callback_data": "email_send"},
                    {"text": "âï¸ Edit", "callback_data": "email_edit"},
                    {"text": "â Cancel", "callback_data": "email_cancel"},
                ]
            ]
        }

        result = send_message(chat_id, preview, reply_markup=buttons)
        # Store draft for when the user clicks a button
        sent_msg_id = None
        if result and result.get("ok"):
            sent_msg_id = result["result"]["message_id"]
        _pending_drafts[chat_id] = {
            "to": to_addr,
            "subject": subject,
            "body": body,
            "msg_id": sent_msg_id,
            "user_name": user_name,
        }
        task = store.add(chat_id, f"ð§ {task_text}", user_name)
        return None  # Already sent the message with buttons

    # General questions â use AI, maybe search if it seems fact-based
    else:
        send_typing(chat_id)
        # Decide if this needs a web search
        lower = task_text.lower()
        needs_web = any(kw in lower for kw in [
            "how", "what", "when", "where", "who", "why", "which",
            "tell me", "explain", "?",
        ])
        response = nora_think(task_text, user_name, needs_search=needs_web)
        return response


def handle_callback_query(callback_query: dict) -> None:
    """Handle button clicks (inline keyboard callbacks)."""
    cb_id = callback_query["id"]
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    msg_id = message.get("message_id")
    user = callback_query.get("from", {})
    user_name = user.get("first_name", "there")

    if not chat_id:
        answer_callback(cb_id, "Error: no chat context")
        return

    # ââ Email draft buttons ââ
    if data == "email_send":
        draft = _pending_drafts.get(chat_id)
        if not draft:
            # Cold start fallback: parse draft from the message text
            draft = _parse_draft_from_message(message.get("text", ""))
            if draft:
                draft["user_name"] = user_name
            else:
                answer_callback(cb_id, "Draft expired (bot restarted)")
                edit_message(chat_id, msg_id,
                             message.get("text", "") + "\n\nDraft expired. Please create a new one.")
                return

        if not draft["to"] or "@" not in draft["to"]:
            answer_callback(cb_id, "No valid email address found")
            edit_message(chat_id, msg_id,
                         message.get("text", "") +
                         "\n\n_â No valid recipient email found. Reply with the email address and I'll update the draft._")
            return

        # Send the email
        send_typing(chat_id)
        result = send_email(draft["to"], draft["subject"], draft["body"])
        if result["ok"]:
            answer_callback(cb_id, "â Email sent!")
            edit_message(chat_id, msg_id,
                         message.get("text", "") +
                         f"\n\nâ *Sent successfully* to {draft['to']}")
            task = store.add(chat_id,
                             f"ð§ Sent email to {draft['to']}: {draft['subject']}",
                             draft.get("user_name", user_name))
        else:
            answer_callback(cb_id, "â Failed to send")
            edit_message(chat_id, msg_id,
                         message.get("text", "") +
                         f"\n\nâ *Failed:* _{result['error']}_")
        _pending_drafts.pop(chat_id, None)

    elif data == "email_edit":
        # Ensure draft exists (cold start fallback)
        if chat_id not in _pending_drafts:
            draft = _parse_draft_from_message(message.get("text", ""))
            if draft:
                draft["user_name"] = user_name
                _pending_drafts[chat_id] = draft
        answer_callback(cb_id, "Reply with your changes")
        edit_message(chat_id, msg_id,
                     message.get("text", "") +
                     "\n\nReply to this message with what you'd like to change.")

    elif data == "email_cancel":
        answer_callback(cb_id, "Draft cancelled")
        edit_message(chat_id, msg_id,
                     message.get("text", "") + "\n\nâ _Draft cancelled._")
        _pending_drafts.pop(chat_id, None)

    else:
        answer_callback(cb_id, "Unknown action")


def process_update(update: dict) -> None:
    """Process an incoming Telegram update."""

    # ââ Handle button callbacks ââ
    callback_query = update.get("callback_query")
    if callback_query:
        handle_callback_query(callback_query)
        return

    message = update.get("message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    chat_type = message.get("chat", {}).get("type", "private")

    if not text:
        return

    # ââ Reply context: if user replies to Nora, treat as a follow-up ââ
    reply_to_msg = message.get("reply_to_message")
    if reply_to_msg:
        reply_from = reply_to_msg.get("from", {})
        reply_username = reply_from.get("username", "")
        if reply_username.lower() == BOT_USERNAME.lower():
            # User is replying to Nora â check if editing a draft
            draft = _pending_drafts.get(chat_id)
            if draft:
                # User is providing edits or a recipient email
                send_typing(chat_id)
                user_name = message.get("from", {}).get("first_name", "User")

                # Check if user is providing an email address
                email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
                if email_match and (not draft["to"] or "@" not in draft["to"]):
                    # User is providing the missing recipient email
                    draft["to"] = email_match.group(0)
                    _pending_drafts[chat_id] = draft
                    buttons = {
                        "inline_keyboard": [[
                            {"text": "â Send", "callback_data": "email_send"},
                            {"text": "âï¸ Edit", "callback_data": "email_edit"},
                            {"text": "â Cancel", "callback_data": "email_cancel"},
                        ]]
                    }
                    send_message(chat_id,
                                 f"ð§ Updated recipient to *{draft['to']}*. Ready to send?\n\n"
                                 f"*Subject:* {draft['subject']}\n---\n{draft['body']}\n---",
                                 reply_markup=buttons)
                    return

                # User wants to edit the draft â ask Claude to revise
                edit_prompt = (
                    f"Here is the current email draft:\n"
                    f"TO: {draft['to']}\nSUBJECT: {draft['subject']}\n---\n{draft['body']}\n---\n\n"
                    f"The user says: {text}\n\n"
                    f"Please revise the draft based on their feedback. "
                    f"Use the same format:\nTO: ...\nSUBJECT: ...\n---\nbody\n---"
                )
                revised = ask_claude(edit_prompt, "", user_name)

                # Parse revised draft
                new_to = draft["to"]
                new_subject = draft["subject"]
                new_body = draft["body"]
                for line in revised.split("\n"):
                    if line.strip().upper().startswith("TO:"):
                        new_to = line.split(":", 1)[1].strip()
                    elif line.strip().upper().startswith("SUBJECT:"):
                        new_subject = line.split(":", 1)[1].strip()
                parts = revised.split("---")
                if len(parts) >= 2:
                    new_body = parts[1].strip()

                draft["to"] = new_to
                draft["subject"] = new_subject
                draft["body"] = new_body
                _pending_drafts[chat_id] = draft

                buttons = {
                    "inline_keyboard": [[
                        {"text": "â Send", "callback_data": "email_send"},
                        {"text": "âï¸ Edit", "callback_data": "email_edit"},
                        {"text": "â Cancel", "callback_data": "email_cancel"},
                    ]]
                }
                send_message(chat_id,
                             f"ð§ *Revised Draft*\n\n"
                             f"*To:* {new_to}\n*Subject:* {new_subject}\n\n"
                             f"---\n{new_body}\n---",
                             reply_markup=buttons)
                return

            # Otherwise, it's a follow-up reply to Nora (multi-turn context)
            original_text = reply_to_msg.get("text", "")
            user_name = message.get("from", {}).get("first_name", "User")
            send_typing(chat_id)
            context_msg = (
                f"[Previous message from Nora that the user is replying to:]\n"
                f"{original_text[:1000]}\n\n"
                f"[User's follow-up reply:]\n{text}"
            )
            intent = detect_intent(text)
            needs_search = intent in ("search_supplier", "research", "pricing")
            response = nora_think(context_msg, user_name, needs_search=needs_search)
            send_message(chat_id, response, reply_to=message.get("message_id"))
            return

    # Handle /commands
    if text.startswith("/"):
        command = text.split()[0].split("@")[0]
        # For /sendemail, pass the full text after the command
        if command == "/sendemail":
            command = text.split("@")[0] if "@" in text.split()[0] else text
        response = handle_command(command, message)
        if response:
            send_message(chat_id, response, reply_to=message.get("message_id"))
        return

    # Handle @mentions in group chats
    bot_mentioned = f"@{BOT_USERNAME}".lower() in text.lower()

    if bot_mentioned:
        task_text = extract_task_from_mention(text, BOT_USERNAME)
        response = handle_mention(task_text, message)
        if response:  # None means already sent (e.g., draft with buttons)
            send_message(chat_id, response, reply_to=message.get("message_id"))
        return

    # In private chats, respond to all messages
    if chat_type == "private":
        response = handle_mention(text, message)
        if response:
            send_message(chat_id, response)
        return


# ââ Vercel Serverless Handler âââââââââââââââââââââââââââââââââââââââââââââââ

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
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {
            "status": "â Nora is online",
            "bot": BOT_USERNAME,
            "version": "2.2.0",
            "ai": "Claude" if ANTHROPIC_API_KEY else "not configured",
            "search": "Tavily" if TAVILY_API_KEY else "not configured",
        }
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
