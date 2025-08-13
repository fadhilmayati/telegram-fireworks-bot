import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)

# --- Environment variables ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

if not TELEGRAM_TOKEN or not FIREWORKS_API_KEY:
    raise RuntimeError("Missing TELEGRAM_TOKEN or FIREWORKS_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
FIREWORKS_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
MODEL = "accounts/fireworks/models/gpt-oss-20b"

# --- Telegram helpers ---
def tg_send(chat_id, text, reply_to=None):
    """Send message to Telegram, split into safe chunks."""
    MAX_LEN = 4000
    chunks = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)] or [""]
    for i, part in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": part}
        if reply_to and i == 0:
            payload["reply_to_message_id"] = reply_to
        try:
            requests.post(f"{TELEGRAM_URL}/sendMessage", json=payload, timeout=20)
        except Exception as e:
            print("tg_send error:", e)

def tg_typing(chat_id):
    """Show typing indicator in Telegram."""
    try:
        requests.post(
            f"{TELEGRAM_URL}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=10
        )
    except Exception as e:
        print("tg_typing error:", e)

# --- Fireworks API ---
def ask_fireworks(prompt):
    """Call Fireworks GPT-OSS-20B model."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.7,
        "top_p": 1,
        "top_k": 40
    }
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        r = requests.post(FIREWORKS_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Fireworks API error:", e)
        if hasattr(e, "response") and e.response is not None:
            print("Status code:", e.response.status_code, "Body:", e.response.text)
        return None

# --- Routes ---
@app.get("/")
def index():
    return "Bot is running!"

@app.post(f"/{TELEGRAM_TOKEN}")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    print("Incoming update:", json.dumps(update, ensure_ascii=False))

    msg = update.get("message")
    if not msg or "text" not in msg:
        return "OK"

    chat_id = msg["chat"]["id"]
    msg_id = msg.get("message_id")
    text = msg["text"].strip()

    if text.lower() in ("/start", "start"):
        tg_send(chat_id, "Hi 👋 I’m your AI assistant. Send me a message!", reply_to=msg_id)
        return "OK"

    tg_typing(chat_id)
    ai_reply = ask_fireworks(text)

    if ai_reply:
        tg_send(chat_id, ai_reply, reply_to=msg_id)
    else:
        tg_send(chat_id, "⚠️ Sorry, I couldn’t reach the AI right now. Please try again.", reply_to=msg_id)

    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))