import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)

# Ensure environment vars are set
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
if not TELEGRAM_TOKEN or not FIREWORKS_API_KEY:
    raise RuntimeError("Missing TELEGRAM_TOKEN or FIREWORKS_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def tg_send(chat_id, text, reply_to=None):
    """Send message to Telegram (splits if too long)."""
    MAX_LEN = 3500
    for i in range(0, len(text), MAX_LEN):
        part = text[i:i+MAX_LEN]
        payload = {"chat_id": chat_id, "text": part}
        if reply_to and i == 0:
            payload["reply_to_message_id"] = reply_to
        try:
            requests.post(f"{TELEGRAM_URL}/sendMessage", json=payload, timeout=20)
        except Exception as e:
            print("tg_send error:", e)

def ask_fireworks(prompt):
    """Call Fireworks GPT-OSS-20B model."""
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": "accounts/fireworks/models/gpt-oss-20b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.6,
        "top_p": 1,
        "top_k": 40,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        print("Fireworks request error:", e, getattr(e, "response", None))
        if e.response is not None:
            print("Status code:", e.response.status_code, "; body:", e.response.text)
        return None
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print("Fireworks JSON parse error:", e, getattr(r, "text", None))
        return None

@app.get("/")
def index():
    return "Bot is running!"

@app.post(f"/{TELEGRAM_TOKEN}")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    print("Incoming update:", update)
    msg = update.get("message")
    if not msg or not msg.get("text"):
        return "OK"

    chat_id = msg["chat"]["id"]
    msg_id = msg.get("message_id")
    text = msg["text"].strip()

    if text.lower() in ("/start", "start"):
        tg_send(chat_id, "Hi! Send me something and I'll reply using AI.", reply_to=msg_id)
        return "OK"

    tg_send(chat_id, "Thinking...", reply_to=msg_id)
    ai = ask_fireworks(text)

    if ai:
        tg_send(chat_id, ai, reply_to=msg_id)
    else:
        tg_send(chat_id, "Sorry, I couldn’t reach the AI right now. Please try again.", reply_to=msg_id)

    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))