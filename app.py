import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)

# Get environment variables from Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

# Function to send a prompt to Fireworks GPT-OSS-20B
def ask_fireworks(prompt):
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    payload = {
        "model": "accounts/fireworks/models/gpt-oss-20b",
        "max_tokens": 300,
        "top_p": 1,
        "top_k": 40,
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "temperature": 0.6,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FIREWORKS_API_KEY}"
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    data = response.json()
    return data["choices"][0]["message"]["content"]

# Root route just to confirm bot is alive
@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"

# Telegram webhook route
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()

    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        user_text = update["message"]["text"]

        try:
            bot_reply = ask_fireworks(user_text)
        except Exception as e:
            bot_reply = f"Error: {str(e)}"

        send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": bot_reply}
        requests.post(send_url, json=payload)

    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))