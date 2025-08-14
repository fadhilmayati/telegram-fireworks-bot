import os
import json
import time
import requests
from flask import Flask, request

app = Flask(__name__)

# Environment variables from Railway (or local .env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ----- Telegram send helpers -----

def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

def send_typing(chat_id):
    requests.post(f"{TELEGRAM_API_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})

# ----- LLM Query -----

def ask_fireworks(prompt):
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.7
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    else:
        return "Sorry, I couldn't process that right now."

# ----- Friend-style reply -----

def send_friend_style(chat_id, text, short_threshold=80, delay_between=1.5):
    """
    Send LLM reply in separate Telegram bubbles like a human friend.
    Short replies go in one bubble. Long replies split into sentences.
    """
    text = text.strip()

    if len(text) <= short_threshold:
        # Just send as one bubble
        send_typing(chat_id)
        time.sleep(min(len(text) / 10, delay_between))
        send_message(chat_id, text)
    else:
        # Split into sentences for multiple bubbles
        sentences = text.replace("\n", " ").split(". ")
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            send_typing(chat_id)
            time.sleep(min(len(sentence) / 10, delay_between))
            send_message(chat_id, sentence)

# ----- Webhook -----

@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        user_message = update["message"]["text"]

        # Ask LLM
        reply = ask_fireworks(user_message)

        # Send in friend style
        send_friend_style(chat_id, reply)

    return "ok", 200

# ----- Health check -----

@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)