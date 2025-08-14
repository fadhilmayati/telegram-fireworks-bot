import os
import time
import threading
import requests
from flask import Flask, request

# ---- LangChain imports ----
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from langchain_community.chat_message_histories import SQLChatMessageHistory

# ---- Flask app ----
app = Flask(__name__)

# ---- Env vars ----
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")  # Postgres URL
FIREWORKS_BASE_URL = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Missing TELEGRAM_TOKEN")
if not FIREWORKS_API_KEY:
    raise RuntimeError("Missing FIREWORKS_API_KEY")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL (e.g., Railway Postgres)")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ---- Simple persona store (table user_persona) ----
# We'll use plain SQL via SQLAlchemy engine under the hood of SQLChatMessageHistory.
# We create the persona table once at startup.
from sqlalchemy import create_engine, text
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_persona (
            chat_id TEXT PRIMARY KEY,
            persona TEXT NOT NULL
        );
    """))

DEFAULT_PERSONA = (
    "Be a friendly, concise buddy. Keep replies short, conversational, "
    "use light warmth and only occasional casual slang if the user does it first. "
    "Ask short follow-up questions when helpful. Avoid info-dumps."
)

def set_persona(chat_id: str, persona: str):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO user_persona (chat_id, persona)
                VALUES (:chat_id, :persona)
                ON CONFLICT (chat_id) DO UPDATE SET persona = EXCLUDED.persona;
            """),
            {"chat_id": chat_id, "persona": persona.strip()}
        )

def get_persona(chat_id: str) -> str:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT persona FROM user_persona WHERE chat_id = :chat_id"),
            {"chat_id": chat_id}
        ).fetchone()
    return row[0] if row and row[0] else DEFAULT_PERSONA

# ---- Telegram helpers ----
def tg_send_message(chat_id: int, text: str):
    try:
        requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print("tg_send_message error:", e, flush=True)

def tg_send_typing(chat_id: int):
    try:
        requests.post(f"{TELEGRAM_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception as e:
        print("tg_send_typing error:", e, flush=True)

# ---- LangChain LLM + Memory ----
# Use Fireworks through OpenAI-compatible ChatOpenAI with a custom base_url.
llm = ChatOpenAI(
    api_key=FIREWORKS_API_KEY,
    base_url=FIREWORKS_BASE_URL,           # LangChain will call <base_url>/chat/completions
    model="accounts/fireworks/models/llama-v3p1-8b-instruct",
    temperature=0.7,
    max_tokens=300,
    timeout=20,
)

# Prompt: persona + history + user input
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an assistant having a natural, succinct conversation. "
     "Persona: {persona}. Keep each reply brief, friendly, and engaging. "
     "Prefer 1–3 short sentences. Ask a tiny follow-up only if it helps."),
    MessagesPlaceholder("history"),
    ("human", "{input}")
])

# History factory: stores messages in Postgres keyed by chat_id
def history_factory(session_id: str):
    # table will be created by SQLChatMessageHistory if missing (table_name = 'lc_chat_history')
    return SQLChatMessageHistory(
        connection_string=DATABASE_URL,
        table_name="lc_chat_history",
        session_id=session_id
    )

chain = prompt | llm

# Wrap with memory
conversational_chain = RunnableWithMessageHistory(
    chain,
    history_factory,
    input_messages_key="input",
    history_messages_key="history",
)

# ---- Friend-style delivery (multi-bubble with natural pauses) ----
def send_friend_style(chat_id: int, full_text: str, short_threshold: int = 90):
    """
    Sends short replies in one bubble. Longer replies are split into bite-size bubbles.
    Uses typing indicators and small delays. This runs in a background thread.
    """
    text = (full_text or "").strip()
    if not text:
        tg_send_message(chat_id, "Hmm, I’ve got nothing to add just yet.")
        return

    def _natural_delay(s: str):
        # Delay ~ proportional to length, capped; adds tiny randomness
        base = min(max(len(s) / 25.0, 0.6), 2.0)
        return base

    # If short, just one bubble
    if len(text) <= short_threshold and "\n" not in text:
        tg_send_typing(chat_id)
        time.sleep(_natural_delay(text))
        tg_send_message(chat_id, text)
        return

    # Otherwise split into small bubbles (by sentence-ish boundaries)
    # First normalize line breaks to sentence boundaries
    normalized = text.replace("\r", " ").replace("\n", " ").strip()
    # Split on sentence enders conservatively
    parts = []
    buf = []
    enders = {'.', '!', '?'}
    for ch in normalized:
        buf.append(ch)
        if ch in enders and len(buf) > 3:
            parts.append("".join(buf).strip())
            buf = []
    if buf:
        parts.append("".join(buf).strip())

    # Fallback if split failed
    if not parts:
        parts = [text]

    for part in parts:
        if not part:
            continue
        tg_send_typing(chat_id)
        time.sleep(_natural_delay(part))
        tg_send_message(chat_id, part)

# ---- Update processing ----
def process_update(update: dict):
    try:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return

        text = msg.get("text", "").strip()

        # Commands
        if text.startswith("/setpersona"):
            # Usage: /setpersona your persona here...
            persona_text = text[len("/setpersona"):].strip()
            if not persona_text:
                tg_send_message(chat_id, "Usage: /setpersona <how you want me to talk>")
                return
            set_persona(str(chat_id), persona_text)
            tg_send_typing(chat_id)
            time.sleep(0.5)
            tg_send_message(chat_id, "Got it. I’ll use that vibe going forward 👍")
            return

        if text.startswith("/start"):
            tg_send_message(chat_id, "Hey! I’m alive. Talk to me 🙂\nYou can also do /setpersona to tune my vibe.")
            return

        if not text:
            tg_send_message(chat_id, "I can only read text for now. Try typing something!")
            return

        # Build inputs for chain
        persona = get_persona(str(chat_id))
        inputs = {"input": text, "persona": persona}

        # Run chain with memory (Postgres-backed)
        result = conversational_chain.invoke(
            inputs,
            config={"configurable": {"session_id": str(chat_id)}}
        )
        reply_text = getattr(result, "content", None) or str(result)

        # Deliver in friend-style bubbles (this function itself handles pauses)
        send_friend_style(chat_id, reply_text)

    except Exception as e:
        print("process_update error:", e, flush=True)
        try:
            tg_send_message(update["message"]["chat"]["id"], "Oops—something went off. Try again?")
        except Exception:
            pass

# ---- Flask routes ----
@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True) or {}
    # Return to Telegram immediately to avoid 502 timeouts
    threading.Thread(target=process_update, args=(update,), daemon=True).start()
    return {"ok": True}, 200

@app.route("/", methods=["GET"])
def health():
    return "ok", 200

# ---- Entrypoint ----
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)