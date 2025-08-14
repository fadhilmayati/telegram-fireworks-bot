import os
import requests
import threading
from flask import Flask, request
from db import init_db, save_message, get_chat_history

app = Flask(__name__)

# ---- Env vars ----
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ---- Initialize DB ----
init_db()

# ---- Telegram helpers ----
def send_message(chat_id, text):
    try:
        requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print("Error sending message:", e)

# ---- Fireworks AI call ----
def ask_fireworks(user_id, user_message):
    """Call Fireworks API with conversation context."""
    history = get_chat_history(user_id)
    messages = history + [{"role": "user", "content": user_message}]

    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "accounts/fireworks/models/gpt-oss-20b",  # Keep your original model
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.7
    }

    r = requests.post(url, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

# ---- Handle incoming Telegram messages ----
def handle_update(update):
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        user_id = str(chat_id)
        user_message = update["message"]["text"]

        # Save user message
        save_message(user_id, "user", user_message)

        # Get bot reply
        try:
            reply = ask_fireworks(user_id, user_message)
            save_message(user_id, "assistant", reply)
            send_message(chat_id, reply)
        except Exception as e:
            send_message(chat_id, f"Error: {str(e)}")

# ---- Webhook route ----
@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    threading.Thread(target=handle_update, args=(update,)).start()
    return {"ok": True}

@app.route("/", methods=["GET"])
def home():
    return "Bot is running."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)