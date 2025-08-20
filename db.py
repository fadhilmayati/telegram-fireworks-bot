import os, psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")

def reset(user_id: str):
    """Delete all stored messages for a given user_id."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM messages WHERE user_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
