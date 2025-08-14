import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")

def init_db():
    """Create the chat_history table if it doesn't exist."""
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
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
    conn.commit()
    cur.close()
    conn.close()

def save_message(user_id, role, content):
    """Save a message to PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_history (user_id, role, content) VALUES (%s, %s, %s)",
        (user_id, role, content)
    )
    conn.commit()
    cur.close()
    conn.close()

def get_chat_history(user_id, limit=10):
    """Retrieve last N messages for a user."""
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM chat_history WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
        (user_id, limit)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    # Return in chronological order
    return [{"role": r, "content": c} for r, c in reversed(rows)]