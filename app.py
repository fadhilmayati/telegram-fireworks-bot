import os
import requests
import psycopg2
from flask import Flask, request

app = Flask(__name__)

# Environment variables from Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Telegram API base
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# PostgreSQL connection
def get_db_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# Save conversation history to PostgreSQL
def save_message(user_id, role, content):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute(
        "INSERT INTO chat_history (user_id, role, content) VALUES (%s, %s, %s)",
        (user_id, role, content)
    )
    conn.commit()
    cur.close()
    conn.close()

# Retrieve chat history for context
def get_chat_history(user_id, limit=10):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM chat_history WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
        (user_id, limit)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    messages = [{"role": r, "content": c} for r, c in reversed(rows)]
    return messages

# Call Fireworks AI
def ask_fireworks(user_id, user_message):
    history = get_chat_history(user_id)
    messages = history + [{"role": "user", "content": user_message}]

    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "accounts/fireworks/models/llama-v2-13b-chat",
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7
    }

    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

# Send messages to Telegram in chunks
def send_chunked_message(chat_id, text, chunk_size=300):
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": chunk})

# Flask webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_id = str(chat_id)
        user_message = data["message"]["text"]

        # Save user message
        save_message(user_id, "user", user_message)

        try:
            bot_reply = ask_fireworks(user_id, user_message)
            save_message(user_id, "assistant", bot_reply)
            send_chunked_message(chat_id, bot_reply)
        except Exception as e:
            send_chunked_message(chat_id, f"Error: {str(e)}")

    return {"ok": True}

# Set webhook when starting
if __name__ == "__main__":
    # Optional: Set webhook automatically on start
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        requests.get(f"{TELEGRAM_URL}/setWebhook?url={webhook_url}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))