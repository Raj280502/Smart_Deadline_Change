import os
import base64
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from storage.database import get_connection

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/calendar"]


def get_gmail_service():
    """
    Handles OAuth 2.0 — opens browser on first run,
    uses saved token.json on all future runs.
    """
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def extract_body(payload):
    """Decode Gmail's base64 encoded email body."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    break
    else:
        data = payload["body"].get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body.strip()


def fetch_gmail_messages(max_results=5):
    """
    Fetches recent Gmail messages and saves
    new ones to raw_messages table.
    Returns count of new messages saved.
    """
    service  = get_gmail_service()
    result   = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        labelIds=["INBOX"]
    ).execute()

    messages  = result.get("messages", [])
    conn      = get_connection()
    cursor    = conn.cursor()
    new_count = 0

    for msg_ref in messages:
        msg_id = f"gmail_{msg_ref['id']}"  # prefix to avoid ID clash with telegram

        # Skip if already stored
        exists = cursor.execute(
            "SELECT id FROM raw_messages WHERE id = ?", (msg_id,)
        ).fetchone()
        if exists:
            continue

        # Fetch full message
        msg     = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        sender  = headers.get("From", "Unknown")
        subject = headers.get("Subject", "(no subject)")
        date    = headers.get("Date", "")
        body    = extract_body(msg["payload"])

        try:
            from email.utils import parsedate_to_datetime
            received_at = parsedate_to_datetime(date).isoformat()
        except Exception:
            received_at = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO raw_messages (id, source, sender, subject, body, received_at, processed)
            VALUES (?, 'gmail', ?, ?, ?, ?, 0)
        """, (msg_id, sender, subject, body, received_at))

        new_count += 1
        print(f"  [Gmail] {subject[:50]} — {sender[:35]}")

    conn.commit()
    conn.close()
    return new_count


if __name__ == "__main__":
    from storage.database import init_db
    init_db()

    print("Fetching emails from Gmail...\n")
    count = fetch_gmail_messages(max_results=5)
    print(f"\nDone. {count} new emails saved to database.")