import os
import requests
import threading
from flask import Flask, request

app = Flask(__name__)

from db import init_db, save_message

# Initialize database at startup
init_db()

# Inside your Telegram message handler:
save_message(user_id, user_message)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def send_message(chat_id, text):
    url = f"{TELEGRAM_URL}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print("Error sending message:", e)

def ask_fireworks(prompt):
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.7
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=20)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Error calling Fireworks:", e)
        return "Sorry, something went wrong."

def handle_update(update):
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        user_message = update["message"]["text"]
        reply = ask_fireworks(user_message)
        send_message(chat_id, reply)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    # Respond immediately to Telegram
    threading.Thread(target=handle_update, args=(update,)).start()
    return {"ok": True}

@app.route("/", methods=["GET"])
def home():
    return "Bot is running."
    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))