import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(text: str, chat_id: str = None):
    """
    Sends a formatted message via Telegram bot.
    """
    target = chat_id or CHAT_ID

    if not target or not BOT_TOKEN:
        print("  [Notification] Telegram not configured — skipping.")
        return False

    try:
        response = httpx.post(
            f"{BASE_URL}/sendMessage",
            json={
                "chat_id":    target,
                "text":       text,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        data = response.json()
        if data.get("ok"):
            print(f"  [Notification] ✅ Telegram message sent.")
            return True
        else:
            print(f"  [Notification] ❌ Failed: {data}")
            return False
    except Exception as e:
        print(f"  [Notification] ❌ Error: {e}")
        return False


def format_change_alert(classification: dict, change_details: dict,
                        risk_result: dict, sender: str) -> str:
    """
    Formats a deadline change notification message.
    Uses Telegram HTML formatting.
    """
    event     = classification.get("event_name", "Unknown Event")
    new_date  = classification.get("deadline_date", "Unknown")
    new_time  = classification.get("deadline_time", "")
    risk      = risk_result.get("risk_level", "UNKNOWN")
    changes   = change_details.get("changes", [])

    # Risk emoji
    risk_emoji = {
        "LOW":      "🟢",
        "MEDIUM":   "🟡",
        "HIGH":     "🔴",
        "CRITICAL": "🚨"
    }.get(risk, "⚠️")

    lines = [
        f"⚠️ <b>DEADLINE CHANGED</b>",
        f"",
        f"📌 <b>Event:</b> {event}",
    ]

    # Show what changed
    for change in changes:
        field     = change["field"].replace("_", " ").title()
        old_value = change["old_value"]
        new_value = change["new_value"]
        lines.append(f"🔄 <b>{field}:</b> {old_value} → <b>{new_value}</b>")

    lines += [
        f"",
        f"📅 <b>New Deadline:</b> {new_date}" + (f" at {new_time}" if new_time else ""),
        f"📧 <b>Source:</b> {sender[:50]}",
        f"{risk_emoji} <b>Risk Level:</b> {risk}",
        f"",
        f"🕐 Detected at: {datetime.now().strftime('%d %b %Y %H:%M')}"
    ]

    return "\n".join(lines)



def format_new_deadline_alert(classification: dict,
                               risk_result: dict, sender: str) -> str:
    """
    Formats a new deadline notification message.
    Only sent for HIGH/CRITICAL risk deadlines.
    """
    event    = classification.get("event_name", "Unknown Event")
    date     = classification.get("deadline_date", "Unknown")
    time     = classification.get("deadline_time", "")
    venue    = classification.get("venue", "")
    urgency  = classification.get("urgency", "medium").upper()
    risk     = risk_result.get("risk_level", "UNKNOWN")

    risk_emoji = {
        "LOW":      "🟢",
        "MEDIUM":   "🟡",
        "HIGH":     "🔴",
        "CRITICAL": "🚨"
    }.get(risk, "⚠️")

    urgency_emoji = {
        "HIGH":   "🔥",
        "MEDIUM": "📌",
        "LOW":    "📝"
    }.get(urgency, "📌")

    lines = [
        f"{urgency_emoji} <b>NEW DEADLINE DETECTED</b>",
        f"",
        f"📌 <b>Event:</b> {event}",
        f"📅 <b>Date:</b> {date}" + (f" at {time}" if time else ""),
    ]

    if venue:
        lines.append(f"📍 <b>Venue:</b> {venue}")

    lines += [
        f"📧 <b>Source:</b> {sender[:50]}",
        f"{risk_emoji} <b>Change Risk:</b> {risk}",
        f"",
        f"🕐 Detected at: {datetime.now().strftime('%d %b %Y %H:%M')}"
    ]

    # Add risk reasons if high risk
    if risk in ("HIGH", "CRITICAL"):
        reasons = risk_result.get("reasons", [])
        if reasons:
            lines.append(f"\n⚠️ <b>Why HIGH risk:</b>")
            for r in reasons[:2]:
                lines.append(f"  • {r}")

    return "\n".join(lines)


def format_summary_alert(processed: int, deadlines: int,
                          changes: int) -> str:
    """Daily summary notification."""
    return (
        f"📊 <b>Processing Summary</b>\n"
        f"\n"
        f"✅ Messages processed: {processed}\n"
        f"📌 Deadlines found: {deadlines}\n"
        f"⚠️ Changes detected: {changes}\n"
        f"\n"
        f"🕐 {datetime.now().strftime('%d %b %Y %H:%M')}"
    )


if __name__ == "__main__":
    # Test notification
    print("Sending test notification...")
    send_message(
        "🤖 <b>Smart Deadline & Change</b>\n\n"
        "✅ System is running!\n"
        "Your deadline monitoring is active."
    )