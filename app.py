import os
import requests
import threading
import time
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def send_typing(chat_id):
    """Show 'typing...' in Telegram."""
    try:
        requests.post(f"{TELEGRAM_URL}/sendChatAction", json={
            "chat_id": chat_id,
            "action": "typing"
        })
    except Exception as e:
        print("Error sending typing action:", e)

def split_text(text, chunk_size=20):
    """Split text into small chunks for streaming."""
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def stream_message(chat_id, text):
    """Send text gradually in one editable bubble."""
    # Send initial placeholder message
    resp = requests.post(f"{TELEGRAM_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": "…"
    }).json()

    if not resp.get("ok"):
        return

    message_id = resp["result"]["message_id"]
    buffer = ""

    for chunk in split_text(text):
        buffer += chunk
        send_typing(chat_id)
        time.sleep(min(len(chunk) / 10, 0.5))  # Delay per chunk
        requests.post(f"{TELEGRAM_URL}/editMessageText", json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": buffer
        })

def send_message(chat_id, text):
    """Send message instantly."""
    try:
        requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print("Error sending message:", e)

def ask_fireworks(prompt):
    """Call Fireworks AI API."""
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
    """Process each incoming update."""
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        user_message = update["message"]["text"]

        # Show typing first
        send_typing(chat_id)

        # Get reply from AI
        reply = ask_fireworks(user_message)

        # Stream reply in a single bubble
        stream_message(chat_id, reply)

@app.route("/webhook", methods=["POST"])
def webhook():
    """Telegram webhook endpoint."""
    update = request.get_json()
    threading.Thread(target=handle_update, args=(update,)).start()
    return {"ok": True}

@app.route("/", methods=["GET"])
def home():
    return "Bot is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))