import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar"
]


def get_calendar_service():
    """Get Google Calendar API service using existing token."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    return build("calendar", "v3", credentials=creds)


def find_existing_event(event_name: str, approximate_date: str) -> dict:
    """
    Searches Google Calendar for an existing event
    matching the event name.
    Returns the event dict if found, None otherwise.
    """
    service = get_calendar_service()

    # Search window — 60 days before and after approximate date
    try:
        center = datetime.fromisoformat(approximate_date)
    except Exception:
        center = datetime.now()

    time_min = (center - timedelta(days=60)).isoformat() + "Z"
    time_max = (center + timedelta(days=60)).isoformat() + "Z"

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        q=event_name,          # search by keyword
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])

    if events:
        print(f"  [Calendar] Found existing event: '{events[0]['summary']}'")
        return events[0]

    return None


def create_calendar_event(event_name: str, deadline_date: str,
                          deadline_time: str = None,
                          venue: str = None,
                          description: str = "") -> dict:
    """
    Creates a new Google Calendar event for a deadline.
    Returns the created event.
    """
    service = get_calendar_service()

    # Build start datetime
    if deadline_time:
        start_str = f"{deadline_date}T{deadline_time}:00"
        start     = {"dateTime": start_str, "timeZone": "Asia/Kolkata"}
        # 1 hour duration for timed events
        end_dt    = datetime.fromisoformat(start_str) + timedelta(hours=1)
        end       = {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"}
    else:
        # All-day event if no time specified
        start = {"date": deadline_date}
        end   = {"date": deadline_date}

    event_body = {
        "summary":     f"📌 {event_name}",
        "description": description or f"Deadline tracked by Smart Deadline & Change",
        "start":       start,
        "end":         end,
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup",  "minutes": 1440},  # 1 day before
                {"method": "popup",  "minutes": 120},   # 2 hours before
                {"method": "email",  "minutes": 1440},  # email 1 day before
            ]
        }
    }

    if venue:
        event_body["location"] = venue

    event = service.events().insert(
        calendarId="primary",
        body=event_body
    ).execute()

    print(f"  [Calendar] ✅ Created event: '{event_name}' on {deadline_date}")
    return event


def update_calendar_event(event_id: str, event_name: str,
                          new_date: str, new_time: str = None,
                          change_description: str = "") -> dict:
    """
    Updates an existing Google Calendar event with new date/time.
    Adds a note to description about what changed and when.
    """
    service = get_calendar_service()

    # Get existing event
    event = service.events().get(
        calendarId="primary",
        eventId=event_id
    ).execute()

    # Update date/time
    if new_time:
        start_str = f"{new_date}T{new_time}:00"
        event["start"] = {"dateTime": start_str, "timeZone": "Asia/Kolkata"}
        end_dt         = datetime.fromisoformat(start_str) + timedelta(hours=1)
        event["end"]   = {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"}
    else:
        event["start"] = {"date": new_date}
        event["end"]   = {"date": new_date}

    # Append change note to description
    old_desc      = event.get("description", "")
    change_note   = (
        f"\n\n⚠️ CHANGED on {datetime.now().strftime('%d %b %Y %H:%M')}: "
        f"{change_description}"
    )
    event["description"] = old_desc + change_note

    updated = service.events().update(
        calendarId="primary",
        eventId=event_id,
        body=event
    ).execute()

    print(f"  [Calendar] ✅ Updated event: '{event_name}' → {new_date}")
    return updated


def delete_calendar_event(event_id: str, event_name: str):
    """Deletes a calendar event (used when deadline is cancelled)."""
    service = get_calendar_service()
    service.events().delete(
        calendarId="primary",
        eventId=event_id
    ).execute()
    print(f"  [Calendar] 🗑️ Deleted event: '{event_name}'")


def sync_deadline_to_calendar(classification: dict,
                               change_detected: bool,
                               change_details: dict) -> str:
    """
    Main function called by the MCP node.
    Decides whether to create or update a calendar event.
    Returns action taken.
    """
    event_name    = classification.get("event_name", "Unknown Event")
    deadline_date = classification.get("deadline_date")
    deadline_time = classification.get("deadline_time")
    venue         = classification.get("venue")

    if not deadline_date:
        print("  [Calendar] No date found — skipping calendar sync.")
        return "skipped"

    if change_detected:
        # Try to find and update existing event
        existing = find_existing_event(event_name, deadline_date)

        if existing:
            change_desc = change_details.get("description", "Date/time updated")
            update_calendar_event(
                event_id=existing["id"],
                event_name=event_name,
                new_date=deadline_date,
                new_time=deadline_time,
                change_description=change_desc
            )
            return "updated"
        else:
            # No existing event found — create new one
            create_calendar_event(
                event_name=event_name,
                deadline_date=deadline_date,
                deadline_time=deadline_time,
                venue=venue,
                description="Created after deadline change detected."
            )
            return "created"
    else:
        # New deadline — create calendar event
        create_calendar_event(
            event_name=event_name,
            deadline_date=deadline_date,
            deadline_time=deadline_time,
            venue=venue
        )
        return "created"


if __name__ == "__main__":
    print("Testing Calendar integration...\n")
    result = create_calendar_event(
        event_name="Test Deadline",
        deadline_date="2026-04-01",
        deadline_time="10:00",
        venue="Room 301",
        description="Test event from Smart Deadline & Change"
    )
    print(f"Event created: {result.get('htmlLink')}")