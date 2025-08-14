import os
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Function to simulate typing indicator
def send_typing(chat_id):
    requests.post(f"{TELEGRAM_URL}/sendChatAction", data={
        "chat_id": chat_id,
        "action": "typing"
    })

# Function to ask LLM (Fireworks API example)
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
    response = requests.post("https://api.fireworks.ai/inference/v1/chat", headers=headers, json=payload)
    if response.status_code == 200:
        return response.json().get("output_text", "Hmm, I can't think right now 😅")
    else:
        return "Oops, something went wrong 😵"

# Split text into smaller chunks for typing simulation
def split_text(text, chunk_size=20):
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i+chunk_size])
    return chunks

# Send gradually updating single bubble
def stream_typing_message(chat_id, text):
    # Create an initial empty message
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
        send_typing(chat_id)  # Show typing
        time.sleep(min(len(chunk)/10, 0.5))  # small delay per chunk
        # Edit the existing message
        requests.post(f"{TELEGRAM_URL}/editMessageText", data={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": buffer
        })

# Telegram webhook endpoint
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]
        user_text = message.get("text", "")
        
        if user_text:
            # Ask LLM
            response_text = ask_fireworks(user_text, user_id=chat_id)
            # Stream response in a single bubble
            stream_typing_message(chat_id, response_text)
    
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(port=5000)