import os
import httpx
from datetime import datetime
from dotenv import load_dotenv
from storage.database import get_connection

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}"

def fetch_telegram_messages():
    """
    Fetches new messages from Telegram using long polling.
    Uses 'offset' so we never re-read the same message twice.
    Returns count of new messages saved.
    """
    conn   = get_connection()
    cursor = conn.cursor()

    # Get the last offset we processed (stored in a simple config table)
    # This tells Telegram: give me only messages AFTER this point
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telegram_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    row    = cursor.execute(
        "SELECT value FROM telegram_state WHERE key = 'last_offset'"
    ).fetchone()
    offset = int(row["value"]) + 1 if row else 0

    # Fetch updates from Telegram
    response = httpx.get(
        f"{BASE_URL}/getUpdates",
        params={"offset": offset, "timeout": 10},
        timeout=15
    )

    data      = response.json()
    updates   = data.get("result", [])
    new_count = 0

    for update in updates:
        update_id = update["update_id"]

        # Only handle text messages
        message = update.get("message", {})
        text    = message.get("text", "")
        if not text:
            continue

        msg_id      = f"telegram_{update_id}"
        sender_info = message.get("from", {})
        sender      = sender_info.get("username") or sender_info.get("first_name", "Unknown")
        received_at = datetime.fromtimestamp(
            message.get("date", 0)
        ).isoformat()

        # Skip if already stored
        exists = cursor.execute(
            "SELECT id FROM raw_messages WHERE id = ?", (msg_id,)
        ).fetchone()
        if not exists:
            cursor.execute("""
                INSERT INTO raw_messages (id, source, sender, subject, body, received_at, processed)
                VALUES (?, 'telegram', ?, NULL, ?, ?, 0)
            """, (msg_id, sender, text, received_at))
            new_count += 1
            print(f"  [Telegram] {text[:60]} — from {sender}")

        # Update offset so we don't re-read this update
        cursor.execute("""
            INSERT INTO telegram_state (key, value)
            VALUES ('last_offset', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (str(update_id),))

    conn.commit()
    conn.close()
    return new_count


def send_telegram_message(text: str, chat_id: str = None):
    """
    Sends a message via Telegram bot.
    We'll use this in Step 11 for notifications.
    """
    target = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    httpx.post(
        f"{BASE_URL}/sendMessage",
        json={"chat_id": target, "text": text, "parse_mode": "HTML"}
    )