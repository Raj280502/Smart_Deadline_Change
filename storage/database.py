import sqlite3
import os

# Database will be created as a file in the project root
DB_PATH = "smart_deadline.db"

def get_connection():
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Create all tables if they don't exist yet.
    This is safe to run multiple times — it won't
    delete existing data.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Unified table for Gmail + Telegram messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_messages (
            id           TEXT PRIMARY KEY,
            source       TEXT NOT NULL,    -- 'gmail' or 'telegram'
            sender       TEXT,
            subject      TEXT,             -- Gmail only, null for Telegram
            body         TEXT,
            received_at  TEXT,             -- ISO timestamp
            processed    INTEGER DEFAULT 0 -- 0 = not classified yet
        )
    """)


    # Table 2: extracted deadlines (filled in Step 3)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deadlines (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id      TEXT,            -- links back to raw_emails
            event_name    TEXT,
            deadline_date TEXT,            -- ISO date
            deadline_time TEXT,
            venue         TEXT,
            confidence    REAL,            -- 0.0 to 1.0
            risk_score    REAL DEFAULT 0.0,
            created_at    TEXT,
            source        TEXT
        )
    """)
    # Sender statistics for prediction agent
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sender_stats (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            sender           TEXT UNIQUE,
            total_deadlines  INTEGER DEFAULT 0,
            total_changes    INTEGER DEFAULT 0,
            last_change_at   TEXT,
            last_deadline_at TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

# Run init when this file is imported
if __name__ == "__main__":
    init_db()
    