import time
from datetime import datetime
from integrations.gmail_client import fetch_gmail_messages
from integrations.telegram_client import fetch_telegram_messages

def run_ingestion_once():
    """
    Fetch from all sources once.
    Returns total new messages count.
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Running ingestion...")

    gmail_count    = fetch_gmail_messages(max_results=20)
    telegram_count = fetch_telegram_messages()
    total          = gmail_count + telegram_count

    print(f"  Gmail: {gmail_count} new  |  Telegram: {telegram_count} new  |  Total: {total}")
    return total


def start_polling(interval_minutes=5):
    """
    Continuous polling loop — runs every N minutes.
    In Phase 2 this becomes a LangGraph node.
    """
    print(f"Starting ingestion polling every {interval_minutes} min. Ctrl+C to stop.\n")
    while True:
        run_ingestion_once()
        time.sleep(interval_minutes * 60)