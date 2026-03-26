import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
from dotenv import load_dotenv
from storage.database import get_connection

load_dotenv()

# ── Festival / Holiday Calendar ──────────────────────────────
# Deadlines near these dates get a risk bonus
# because postponements are historically common around holidays
INDIAN_HOLIDAYS_2026 = [
    date(2026, 3, 29),   # Holi
    date(2026, 4, 14),   # Ambedkar Jayanti
    date(2026, 4, 18),   # Good Friday
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 8, 15),   # Independence Day
    date(2026, 8, 27),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 9),   # Diwali
    date(2026, 11, 11),  # Diwali (Lakshmi Puja)
    date(2026, 12, 25),  # Christmas
]

RISK_LEVELS = {
    (0.0, 0.3):  ("LOW",    "This sender rarely changes deadlines."),
    (0.3, 0.6):  ("MEDIUM", "This sender occasionally changes deadlines."),
    (0.6, 0.8):  ("HIGH",   "This sender frequently changes deadlines."),
    (0.8, 1.01): ("CRITICAL","This sender almost always changes deadlines."),
}


def get_risk_level(score: float) -> tuple:
    """Convert numeric score to risk label + description."""
    for (low, high), (label, desc) in RISK_LEVELS.items():
        if low <= score < high:
            return label, desc
    return "LOW", "This sender rarely changes deadlines."


def update_sender_stats(sender: str, is_change: bool):
    """
    Called every time a deadline is processed.
    Updates the running stats for this sender.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    now    = datetime.now().isoformat()

    # Check if sender already exists
    existing = cursor.execute(
        "SELECT * FROM sender_stats WHERE sender = ?", (sender,)
    ).fetchone()

    if existing:
        # Update existing record
        cursor.execute("""
            UPDATE sender_stats SET
                total_deadlines  = total_deadlines + 1,
                total_changes    = total_changes + ?,
                last_change_at   = CASE WHEN ? = 1 THEN ? ELSE last_change_at END,
                last_deadline_at = ?
            WHERE sender = ?
        """, (
            1 if is_change else 0,
            1 if is_change else 0,
            now,
            now,
            sender
        ))
    else:
        # Insert new sender record
        cursor.execute("""
            INSERT INTO sender_stats
                (sender, total_deadlines, total_changes,
                 last_change_at, last_deadline_at)
            VALUES (?, 1, ?, ?, ?)
        """, (
            sender,
            1 if is_change else 0,
            now if is_change else None,
            now
        ))

    conn.commit()
    conn.close()


def calculate_risk_score(sender: str, deadline_date: str) -> dict:
    """
    Calculates how likely this deadline is to change.

    Two factors:
    1. Sender change rate — how often has this sender changed deadlines?
    2. Festival proximity — is the deadline near a holiday?

    Returns dict with score, level, and explanation.
    """
    conn = get_connection()
    stats = conn.execute(
        "SELECT * FROM sender_stats WHERE sender = ?", (sender,)
    ).fetchone()
    conn.close()

    score       = 0.0
    reasons     = []

    # ── Factor 1: Sender change rate ────────────────────
    if stats:
        total      = stats["total_deadlines"]
        changes    = stats["total_changes"]

        if total > 0:
            change_rate = changes / total

            # Recency weight — recent changes matter more
            # If they changed something in last 30 days, bump the rate up
            recency_weight = 1.0
            if stats["last_change_at"]:
                try:
                    last_change = datetime.fromisoformat(stats["last_change_at"])
                    days_since  = (datetime.now() - last_change).days
                    if days_since <= 30:
                        recency_weight = 1.3  # recent change → higher risk
                    elif days_since <= 60:
                        recency_weight = 1.1
                except Exception:
                    pass

            sender_score = min(change_rate * recency_weight, 0.8)
            score       += sender_score

            reasons.append(
                f"Sender has changed {changes} out of {total} deadlines "
                f"(rate: {change_rate:.0%})"
            )
    else:
        # Unknown sender — neutral risk
        score += 0.1
        reasons.append("New sender — no history available")

    # ── Factor 2: Festival proximity ────────────────────
    if deadline_date:
        try:
            dl_date    = date.fromisoformat(deadline_date)
            days_away  = (dl_date - date.today()).days

            # Check proximity to each holiday (within 5 days)
            for holiday in INDIAN_HOLIDAYS_2026:
                gap = abs((dl_date - holiday).days)
                if gap <= 5:
                    festival_bonus = 0.2
                    score         += festival_bonus
                    reasons.append(
                        f"Deadline is within 5 days of a holiday "
                        f"({holiday.strftime('%b %d')})"
                    )
                    break  # only count once

            # Deadline very soon — harder to change but still possible
            if 0 < days_away <= 2:
                reasons.append("Deadline is imminent (within 2 days)")

        except ValueError:
            pass

    # Cap score at 1.0
    score              = min(score, 1.0)
    level, description = get_risk_level(score)

    return {
        "risk_score":   round(score, 3),
        "risk_level":   level,
        "description":  description,
        "reasons":      reasons,
        "sender_stats": dict(stats) if stats else None
    }


def update_deadline_risk_score(deadline_id: int, risk_score: float):
    """Update the risk_score column on an existing deadline record."""
    conn = get_connection()
    conn.execute(
        "UPDATE deadlines SET risk_score = ? WHERE id = ?",
        (risk_score, deadline_id)
    )
    conn.commit()
    conn.close()


def get_high_risk_deadlines(threshold: float = 0.6) -> list:
    """Returns all upcoming deadlines above the risk threshold."""
    conn  = get_connection()
    rows  = conn.execute("""
        SELECT id, event_name, deadline_date, deadline_time,
               risk_score, source, created_at
        FROM deadlines
        WHERE risk_score >= ?
        ORDER BY risk_score DESC
    """, (threshold,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_sender_stats() -> list:
    """Returns sender stats sorted by change rate."""
    conn  = get_connection()
    rows  = conn.execute("""
        SELECT sender, total_deadlines, total_changes,
               ROUND(CAST(total_changes AS FLOAT) /
               NULLIF(total_deadlines, 0), 2) as change_rate,
               last_change_at, last_deadline_at
        FROM sender_stats
        ORDER BY change_rate DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    from storage.database import init_db
    init_db()

    # Simulate some sender history
    print("Simulating sender history...\n")
    update_sender_stats("professor@college.edu", is_change=True)
    update_sender_stats("professor@college.edu", is_change=True)
    update_sender_stats("professor@college.edu", is_change=False)
    update_sender_stats("professor@college.edu", is_change=True)

    # Calculate risk
    result = calculate_risk_score(
        sender="professor@college.edu",
        deadline_date="2026-03-27"
    )

    print(f"Risk Score:  {result['risk_score']}")
    print(f"Risk Level:  {result['risk_level']}")
    print(f"Description: {result['description']}")
    print(f"Reasons:")
    for r in result["reasons"]:
        print(f"  → {r}")

    print("\nAll sender stats:")
    for s in get_all_sender_stats():
        print(f"  {s}")