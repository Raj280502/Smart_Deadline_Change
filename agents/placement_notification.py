import json
from datetime import datetime

from agents.notification import send_message


def notify_new_placement_drive(drive: dict) -> bool:
    return send_message(format_placement_drive_alert(drive, "NEW PLACEMENT DRIVE"))


def notify_changed_placement_drive(drive: dict, changes: list) -> bool:
    return send_message(format_placement_drive_alert(drive, "PLACEMENT DRIVE UPDATED", changes))


def format_placement_drive_alert(drive: dict, title: str, changes: list = None) -> str:
    """
    Build Telegram HTML message.

    Syntax used by Telegram:
        <b>bold text</b>
        plain new lines for readable sections
    """
    summary = _summary_dict(drive.get("jd_summary"))
    skills = summary.get("skills_required") or []

    lines = [
        f"<b>{title}</b>",
        "",
        f"<b>Company:</b> {_value(drive.get('company_name'))}",
        f"<b>Role:</b> {_value(drive.get('role'))}",
        "",
        "<b>Package:</b>",
        f"Min: {_value(drive.get('min_package'))}",
        f"Max: {_value(drive.get('max_package'))}",
        "",
        "<b>Stipend:</b>",
        f"Min: {_value(drive.get('min_stipend'))}",
        f"Max: {_value(drive.get('max_stipend'))}",
        "",
        f"<b>Location:</b> {_value(drive.get('location'))}",
        f"<b>Duration:</b> {_value(drive.get('duration'))}",
        f"<b>Criteria:</b> {_value(drive.get('criteria'))}",
        f"<b>Eligible Branches:</b> {_value(drive.get('eligible_branches'))}",
        f"<b>Deadline:</b> {_deadline(drive)}",
    ]

    if changes:
        lines.extend(["", "<b>Changes detected:</b>"])
        for change in changes[:5]:
            field = change["field_changed"].replace("_", " ").title()
            lines.append(
                f"- {field}: {_value(change.get('old_value'))} -> {_value(change.get('new_value'))}"
            )

    lines.extend([
        "",
        "<b>JD Summary:</b>",
        _value(summary.get("short_summary")),
    ])

    if skills:
        lines.extend(["", f"<b>Skills:</b> {', '.join(skills[:8])}"])

    if drive.get("document_url"):
        lines.extend(["", f"<b>JD Document:</b> {drive['document_url']}"])

    if drive.get("apply_url"):
        lines.append(f"<b>Apply/Details:</b> {drive['apply_url']}")

    lines.extend([
        "",
        f"Detected at: {datetime.now().strftime('%d %b %Y %H:%M')}",
    ])

    return "\n".join(lines)


def _summary_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"short_summary": value}
    return {"short_summary": "No JD summary available."}


def _deadline(drive: dict) -> str:
    date = drive.get("deadline_date")
    time = drive.get("deadline_time")
    if date and time:
        return f"{date} {time}"
    return _value(date)


def _value(value) -> str:
    return str(value).strip() if value else "Not mentioned"
