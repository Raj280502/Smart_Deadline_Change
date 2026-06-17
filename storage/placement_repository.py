import hashlib
import json
from datetime import datetime
from typing import Dict, List, Tuple

from storage.database import get_connection


TRACKED_FIELDS = [
    "company_name",
    "role",
    "min_package",
    "max_package",
    "min_stipend",
    "max_stipend",
    "location",
    "duration",
    "criteria",
    "eligible_branches",
    "deadline_date",
    "deadline_time",
    "job_description",
    "jd_summary",
    "document_url",
    "apply_url",
    "status",
]


def make_source_hash(drive: dict) -> str:
    """Create a stable hash so we can detect any portal data change."""
    payload = {field: drive.get(field) or "" for field in TRACKED_FIELDS}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def upsert_placement_drive(drive: dict, user_id: int = 1) -> Tuple[dict, List[dict], bool]:
    """
    Insert or update a placement drive.

    Returns:
        saved_drive, changes, is_new
    """
    now = datetime.now().isoformat()
    source_hash = make_source_hash(drive)

    conn = get_connection()
    existing = conn.execute(
        """
        SELECT * FROM placement_drives
        WHERE user_id = ? AND portal_name = ? AND external_id = ?
        """,
        (user_id, drive["portal_name"], drive.get("external_id")),
    ).fetchone()

    if not existing:
        cursor = conn.execute(
            """
            INSERT INTO placement_drives (
                user_id, portal_name, external_id, company_name, role, min_package,
                max_package, min_stipend, max_stipend, location, duration,
                criteria, eligible_branches, deadline_date, deadline_time,
                job_description, jd_summary, document_url,
                local_document, apply_url, status, source_hash,
                first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                drive["portal_name"],
                drive.get("external_id"),
                drive["company_name"],
                drive.get("role"),
                drive.get("min_package"),
                drive.get("max_package"),
                drive.get("min_stipend"),
                drive.get("max_stipend"),
                drive.get("location"),
                drive.get("duration"),
                drive.get("criteria"),
                drive.get("eligible_branches"),
                drive.get("deadline_date"),
                drive.get("deadline_time"),
                drive.get("job_description"),
                drive.get("jd_summary"),
                drive.get("document_url"),
                drive.get("local_document"),
                drive.get("apply_url"),
                drive.get("status", "open"),
                source_hash,
                now,
                now,
            ),
        )
        drive_id = cursor.lastrowid
        conn.commit()
        saved = get_placement_drive_by_id(drive_id, conn)
        conn.close()
        return saved, [], True

    existing_dict = dict(existing)
    changes = []

    if existing_dict.get("source_hash") != source_hash:
        for field in TRACKED_FIELDS:
            old_value = existing_dict.get(field)
            new_value = drive.get(field)
            if (old_value or "") != (new_value or ""):
                changes.append({
                    "field_changed": field,
                    "old_value": old_value,
                    "new_value": new_value,
                })

        conn.execute(
            """
            UPDATE placement_drives SET
                company_name = ?, role = ?, min_package = ?, max_package = ?,
                min_stipend = ?, max_stipend = ?, location = ?, duration = ?,
                criteria = ?, eligible_branches = ?, deadline_date = ?,
                deadline_time = ?, job_description = ?, jd_summary = ?,
                document_url = ?, local_document = ?, apply_url = ?,
                status = ?, source_hash = ?, last_seen_at = ?
            WHERE id = ?
            """,
            (
                drive["company_name"],
                drive.get("role"),
                drive.get("min_package"),
                drive.get("max_package"),
                drive.get("min_stipend"),
                drive.get("max_stipend"),
                drive.get("location"),
                drive.get("duration"),
                drive.get("criteria"),
                drive.get("eligible_branches"),
                drive.get("deadline_date"),
                drive.get("deadline_time"),
                drive.get("job_description"),
                drive.get("jd_summary"),
                drive.get("document_url"),
                drive.get("local_document"),
                drive.get("apply_url"),
                drive.get("status", "open"),
                source_hash,
                now,
                existing_dict["id"],
            ),
        )

        for change in changes:
            conn.execute(
                """
                INSERT INTO placement_drive_changes (
                    user_id, drive_id, field_changed, old_value, new_value, detected_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    existing_dict["id"],
                    change["field_changed"],
                    change["old_value"],
                    change["new_value"],
                    now,
                ),
            )
    else:
        conn.execute(
            "UPDATE placement_drives SET last_seen_at = ? WHERE id = ?",
            (now, existing_dict["id"]),
        )

    conn.commit()
    saved = get_placement_drive_by_id(existing_dict["id"], conn)
    conn.close()
    return saved, changes, False


def get_placement_drive_by_id(drive_id: int, conn=None) -> Dict:
    owns_conn = conn is None
    conn = conn or get_connection()
    row = conn.execute(
        "SELECT * FROM placement_drives WHERE id = ?",
        (drive_id,),
    ).fetchone()
    if owns_conn:
        conn.close()
    return dict(row) if row else {}


def list_placement_drives(limit: int = 100, user_id: int = 1) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM placement_drives
        WHERE user_id = ?
        ORDER BY COALESCE(deadline_date, '9999-12-31') ASC, last_seen_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def list_placement_changes(limit: int = 100, user_id: int = 1) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT c.id, d.company_name, d.role, c.field_changed,
               c.old_value, c.new_value, c.detected_at
        FROM placement_drive_changes c
        JOIN placement_drives d ON c.drive_id = d.id
        WHERE c.user_id = ?
        ORDER BY c.detected_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def start_scrape_run(portal_name: str, user_id: int = 1) -> int:
    now = datetime.now().isoformat()
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO placement_scrape_runs (user_id, portal_name, started_at, status)
        VALUES (?, ?, ?, 'running')
        """,
        (user_id, portal_name, now),
    )
    conn.commit()
    run_id = cursor.lastrowid
    conn.close()
    return run_id


def finish_scrape_run(
    run_id: int,
    status: str,
    new_count: int = 0,
    changed_count: int = 0,
    error_message: str = None,
):
    conn = get_connection()
    conn.execute(
        """
        UPDATE placement_scrape_runs SET
            finished_at = ?,
            status = ?,
            new_drives_count = ?,
            changed_drives_count = ?,
            error_message = ?
        WHERE id = ?
        """,
        (
            datetime.now().isoformat(),
            status,
            new_count,
            changed_count,
            error_message,
            run_id,
        ),
    )
    conn.commit()
    conn.close()
