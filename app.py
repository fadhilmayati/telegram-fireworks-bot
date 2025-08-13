import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)

# Environment variables (set in Railway)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

# Telegram API URL
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Send a prompt to Fireworks GPT-OSS-20B
def ask_fireworks(prompt):
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "accounts/fireworks/models/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 200
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            print("Fireworks API Error:", response.status_code, response.text)
            return None
    except Exception as e:
        print("Error calling Fireworks API:", e)
        return None

# Send a message to Telegram
def send_telegram_message(chat_id, text):
    url = f"{TELEGRAM_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Error sending message to Telegram:", e)

# Telegram webhook route
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()

    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"]

        reply = ask_fireworks(text)
        if reply:
            send_telegram_message(chat_id, reply)
        else:
            send_telegram_message(chat_id, "Sorry, I couldn’t reach the AI right now. Please try again.")

    return "OK"

@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))