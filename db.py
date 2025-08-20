# db.py
import os
import math
import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL")

def _conn():
    return psycopg2.connect(DATABASE_URL)

def _rough_tokens(s: str) -> int:
    return math.ceil(len(s or "") / 4)

# ---- 1. Initialize schema ----
def init_db():
    """Create table and indexes if they don't exist."""
    ddl = """
    CREATE TABLE IF NOT EXISTS messages (
        id BIGSERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        text TEXT NOT NULL,
        tokens INTEGER,
        archived BOOLEAN DEFAULT FALSE,
        ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_messages_user_ts
        ON messages (user_id, ts DESC);
    """
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(ddl)
        conn.commit()

# ---- 2. Save a message ----
def save_message(user_id: str, role: str, text: str):
    """Insert a message row with a rough token estimate."""
    tks = _rough_tokens(text)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (user_id, role, text, tokens) VALUES (%s, %s, %s, %s)",
            (user_id, role, text, tks),
        )
        conn.commit()

# ---- 3. Retrieve chat history ----
DEFAULT_TOKEN_BUDGET = 1500

def get_chat_history(user_id: str, token_budget: int = DEFAULT_TOKEN_BUDGET):
    """
    Return last messages up to token_budget.
    Output: list of {role, content}
    """
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT role, text, COALESCE(tokens, CEIL(char_length(text)/4.0)) AS tokens
            FROM messages
            WHERE user_id = %s AND archived = FALSE
            ORDER BY ts DESC
            LIMIT 200
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    running = 0
    chosen = []
    for row in rows:
        toks = int(row["tokens"]) if row["tokens"] else _rough_tokens(row["text"])
        if running + toks > token_budget:
            break
        chosen.append({"role": row["role"], "content": row["text"]})
        running += toks

    return list(reversed(chosen))

# ---- 4. Reset conversation ----
def reset(user_id: str, soft: bool = False):
    """Hard delete or soft archive a user's conversation."""
    with _conn() as conn, conn.cursor() as cur:
        if soft:
            cur.execute("UPDATE messages SET archived = TRUE WHERE user_id = %s", (user_id,))
        else:
            cur.execute("DELETE FROM messages WHERE user_id = %s", (user_id,))
        conn.commit()
