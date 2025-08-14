import os
import time
import requests
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def send_typing(chat_id):
    requests.post(f"{TELEGRAM_URL}/sendChatAction", data={
        "chat_id": chat_id,
        "action": "typing"
    })

def ask_fireworks(prompt, user_id):
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": prompt,
        "user": str(user_id),
        "model": "gpt-oss-20b"
    }
    try:
        response = requests.post("https://api.fireworks.ai/inference/v1/chat", headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            return response.json().get("output_text", "Hmm, I can't think right now 😅")
        else:
            return "Oops, something went wrong 😵"
    except Exception:
        return "Oops, something went wrong 😵"

def split_text(text, chunk_size=20):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def stream_typing_message(chat_id, text):
    # Create initial message
    resp = requests.post(f"{TELEGRAM_URL}/sendMessage", data={
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
        time.sleep(min(len(chunk)/10, 0.5))
        requests.post(f"{TELEGRAM_URL}/editMessageText", data={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": buffer
        })

def process_update(message):
    chat_id = message["chat"]["id"]
    user_text = message.get("text", "")
    if user_text:
        response_text = ask_fireworks(user_text, user_id=chat_id)
        stream_typing_message(chat_id, response_text)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" in data:
        threading.Thread(target=process_update, args=(data["message"],)).start()
    return jsonify({})  # Return immediately to Telegram

if __name__ == "__main__":
    app.run(port=5000)