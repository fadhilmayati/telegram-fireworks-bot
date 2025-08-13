import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)

# --- Environment ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Missing TELEGRAM_TOKEN env var")
if not FIREWORKS_API_KEY:
    raise RuntimeError("Missing FIREWORKS_API_KEY env var")

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# --- Helpers ---
def tg_send_message(chat_id, text, reply_to=None):
    """Send a text message to Telegram (chunks if too long)."""
    # Telegram text limit ≈ 4096 chars; keep a safety margin
    MAX_LEN = 3500
    parts = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)] or [""]
    for i, part in enumerate(parts):
        payload = {"chat_id": chat_id, "text": part}
        if reply_to and i == 0:
            payload["reply_to_message_id"] = reply_to
        try:
            requests.post(f"{TELEGRAM_API_BASE}/sendMessage", json=payload, timeout=20)
        except Exception as e:
            print("sendMessage error:", e)

def tg_send_typing(chat_id):
    try:
        requests.post(
            f"{TELEGRAM_API_BASE}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=10,
        )
    except Exception as e:
        print("sendChatAction error:", e)

def ask_fireworks(prompt):
    """Call Fireworks Chat Completions."""
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = {
        "model": "accounts/fireworks/models/gpt-oss-20b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.6,
        "top_p": 1,
        "top_k": 40,
        "presence_penalty": 0,
        "frequency_penalty": 0,
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=45)
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"]
    except Exception as e:
        print("Fireworks error:", e, "Response:", getattr(e, "response", None))
        return "Sorry, I couldn’t reach the AI right now. Please try again."

# --- Health check ---
@app.get("/")
def index():
    return "Bot is running!"

# --- Telegram webhook ---
# IMPORTANT: route path includes the token (matches your current setup)
@app.post(f"/{TELEGRAM_TOKEN}")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    print("Incoming update:", json.dumps(update, ensure_ascii=False))
    msg = update.get("message")

    if not msg:
        return "ok"

    chat_id = msg["chat"]["id"]
    message_id = msg.get("message_id")
    text = msg.get("text")

    if not text:
        tg_send_message(chat_id, "Please send text messages only.")
        return "ok"

    # Simple command handling
    if text.strip().lower() in ("/start", "start"):
        tg_send_message(
            chat_id,
            "Hi! I’m your assistant. Send me a message and I’ll reply with AI ✨"
        )
        return "ok"

    # Show typing while we call the model
    tg_send_typing(chat_id)

    # Ask Fireworks and reply
    ai_reply = ask_fireworks(text)
    tg_send_message(chat_id, ai_reply, reply_to=message_id)

    return "ok"

if __name__ == "__main__":
    # Railway sets $PORT; default to 5000 if local
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))