import os
import requests
import threading
import time

from flask import Flask, request
from db import init_db, save_message, get_chat_history, reset

app = Flask(__name__)

# ---- Environment variables ----
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ---- Initialize DB ----
init_db()

# Simple per-user rate limiter: last message timestamp per user
last_message_times = {}

def send_message(chat_id: int, text: str, reply_to_message_id: int | None = None) -> None:
    """Send a message to Telegram with optional reply-to threading."""
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        requests.post(f"{TELEGRAM_URL}/sendMessage", json=payload)
    except Exception as e:
        print("Error sending message:", e)

def send_chat_action(chat_id: int, action: str = "typing") -> None:
    """Tell Telegram clients the bot is typing or performing an action."""
    try:
        requests.post(f"{TELEGRAM_URL}/sendChatAction", json={"chat_id": chat_id, "action": action})
    except Exception as e:
        print("Error sending chat action:", e)

def ask_fireworks(user_id: str, user_message: str) -> str:
    """Call Fireworks AI with conversation context and return its reply."""
    history = get_chat_history(user_id)
    messages = history + [{"role": "user", "content": user_message}]
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "accounts/fireworks/models/gpt-oss-20b",
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.7,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

def handle_update(update: dict) -> None:
    """Process a Telegram update: save message, handle /reset, call the model."""
    if "message" not in update or "text" not in update["message"]:
        return

    chat_id = update["message"]["chat"]["id"]
    user_id = str(chat_id)
    user_message = update["message"]["text"]
    reply_to_id = update["message"].get("message_id")

    # Rate limiting: 1 message per second per user
    now = time.time()
    last_time = last_message_times.get(user_id, 0.0)
    if now - last_time < 1.0:
        send_message(chat_id, "You're sending messages too quickly. Please slow down.", reply_to_id)
        return
    last_message_times[user_id] = now

    # /reset command clears history and returns
    if user_message.strip().lower() == "/reset":
        reset(user_id)
        send_message(chat_id, "Conversation memory reset.", reply_to_id)
        return

    # Persist incoming user message
    save_message(user_id, "user", user_message)

    # Indicate typing
    send_chat_action(chat_id, "typing")

    try:
        reply = ask_fireworks(user_id, user_message)
        save_message(user_id, "assistant", reply)
        # Chunk long replies into smaller messages (300 characters each)
        chunk_size = 300
        for i in range(0, len(reply), chunk_size):
            chunk = reply[i:i + chunk_size]
            send_message(chat_id, chunk, reply_to_id)
            if i + chunk_size < len(reply):
                time.sleep(0.3)
    except Exception as e:
        send_message(chat_id, f"Error: {str(e)}", reply_to_id)

# ---- Flask routes ----
@app.route("/webhook", methods=["POST"])
def webhook() -> dict[str, bool]:
    """Telegram posts updates to this webhook; dispatch processing in a new thread."""
    update = request.get_json(force=True)
    threading.Thread(target=handle_update, args=(update,), daemon=True).start()
    return {"ok": True}

@app.route("/", methods=["GET"])
def home() -> str:
    return "Bot is running."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
