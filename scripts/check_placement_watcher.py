"""Check whether the placement watcher is configured and optionally run it.

This script intentionally prints only credential presence, never secret values.
Use --live-sync to test the real TPO portal with Telegram notifications disabled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the project root is on sys.path so that 'integrations', 'storage', etc. resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integrations.placement_scraper import sync_placement_drives
from agents.placement_notification import notify_new_placement_drive
from storage.auth_repository import get_credential_status, get_user_credentials
from storage.database import get_connection, init_db
from storage.placement_repository import list_placement_drives


def _configured_for_sync(status: dict[str, bool]) -> bool:
    return bool(
        status.get("tpo_username")
        and status.get("tpo_password")
        and status.get("tpo_login_url")
        and status.get("tpo_drives_url")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-sync",
        action="store_true",
        help="Run a real TPO sync. Notifications are disabled unless --send-notifications is also passed.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        help="Use a specific saved user account instead of the first configured account.",
    )
    parser.add_argument(
        "--send-notifications",
        action="store_true",
        help="Send Telegram notifications during --live-sync.",
    )
    parser.add_argument(
        "--notify-latest",
        action="store_true",
        help="Resend Telegram notification for the latest saved drive of the selected user.",
    )
    args = parser.parse_args()

    init_db()
    conn = get_connection()
    users = conn.execute("select id, email from users order by id").fetchall()
    conn.close()

    user_statuses = []
    selected_user_id = None
    for user in users:
        status = get_credential_status(user["id"])
        if (
            selected_user_id is None
            and _configured_for_sync(status)
            and (args.user_id is None or args.user_id == user["id"])
        ):
            selected_user_id = user["id"]
        user_statuses.append(
            {
                "user_id": user["id"],
                "email_masked": _mask_email(user["email"] or ""),
                "credentials_present": status,
                "ready_for_tpo_sync": _configured_for_sync(status),
            }
        )

    output: dict[str, object] = {
        "user_count": len(users),
        "users": user_statuses,
        "selected_user_id_for_live_sync": selected_user_id,
    }

    if args.live_sync:
        if selected_user_id is None:
            output["live_sync"] = {
                "status": "skipped",
                "reason": "No user has TPO username/password and portal URLs saved.",
            }
        else:
            output["live_sync"] = sync_placement_drives(
                send_notifications=args.send_notifications,
                credentials=get_user_credentials(selected_user_id),
                user_id=selected_user_id,
            )

    if args.notify_latest:
        if selected_user_id is None:
            output["notify_latest"] = {
                "status": "skipped",
                "reason": "No configured user was found.",
            }
        else:
            credentials = get_user_credentials(selected_user_id)
            drives = list_placement_drives(limit=1, user_id=selected_user_id)
            if not drives:
                output["notify_latest"] = {
                    "status": "skipped",
                    "reason": "No saved placement drives found.",
                }
            else:
                sent = notify_new_placement_drive(
                    drives[0],
                    bot_token=credentials.get("telegram_bot_token"),
                    chat_id=credentials.get("telegram_chat_id"),
                )
                output["notify_latest"] = {
                    "status": "sent" if sent else "failed",
                    "drive_id": drives[0].get("id"),
                    "company_name": drives[0].get("company_name"),
                }

    print(json.dumps(output, indent=2, default=str))


def _mask_email(email: str) -> str:
    if "@" not in email:
        return f"{email[:2]}***" if email else ""
    name, domain = email.split("@", 1)
    return f"{name[:2]}***@{domain}"


if __name__ == "__main__":
    main()
