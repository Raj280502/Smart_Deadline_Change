import sqlite3
import os

# Use storage/ by default so Render persistent disk keeps SQLite data.
DB_PATH = os.getenv("DATABASE_PATH", os.path.join("storage", "smart_deadline.db"))

def get_connection():
    """Get a connection to the SQLite database."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
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


    # Table 2: extracted deadlines
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deadlines (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id    TEXT,            -- links back to raw_messages
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
    ensure_column(cursor, "deadlines", "message_id", "TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS change_history (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            deadline_id    INTEGER,
            field_changed  TEXT,
            old_value      TEXT,
            new_value      TEXT,
            detected_at    TEXT,
            source_message TEXT,
            FOREIGN KEY(deadline_id) REFERENCES deadlines(id)
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT UNIQUE NOT NULL,
            password_hash   TEXT NOT NULL,
            created_at      TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_credentials (
            user_id       INTEGER PRIMARY KEY,
            encrypted_json TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS placement_drives (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER DEFAULT 1,
            portal_name      TEXT NOT NULL,
            external_id      TEXT,
            company_name     TEXT NOT NULL,
            role             TEXT,
            min_package      TEXT,
            max_package      TEXT,
            min_stipend      TEXT,
            max_stipend      TEXT,
            location         TEXT,
            duration         TEXT,
            criteria         TEXT,
            eligible_branches TEXT,
            deadline_date    TEXT,
            deadline_time    TEXT,
            job_description  TEXT,
            jd_summary       TEXT,
            document_url     TEXT,
            local_document   TEXT,
            apply_url        TEXT,
            status           TEXT DEFAULT 'open',
            source_hash      TEXT,
            first_seen_at    TEXT,
            last_seen_at     TEXT,
            UNIQUE(user_id, portal_name, external_id)
        )
    """)
    ensure_column(cursor, "placement_drives", "user_id", "INTEGER DEFAULT 1")
    ensure_column(cursor, "placement_drives", "min_stipend", "TEXT")
    ensure_column(cursor, "placement_drives", "max_stipend", "TEXT")
    ensure_column(cursor, "placement_drives", "eligible_branches", "TEXT")
    ensure_placement_drives_user_scoped_unique(cursor)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS placement_drive_changes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER DEFAULT 1,
            drive_id       INTEGER NOT NULL,
            field_changed  TEXT NOT NULL,
            old_value      TEXT,
            new_value      TEXT,
            detected_at    TEXT NOT NULL,
            FOREIGN KEY(drive_id) REFERENCES placement_drives(id)
        )
    """)
    ensure_column(cursor, "placement_drive_changes", "user_id", "INTEGER DEFAULT 1")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS placement_scrape_runs (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id               INTEGER DEFAULT 1,
            portal_name           TEXT NOT NULL,
            started_at            TEXT NOT NULL,
            finished_at           TEXT,
            status                TEXT NOT NULL,
            new_drives_count      INTEGER DEFAULT 0,
            changed_drives_count  INTEGER DEFAULT 0,
            error_message         TEXT
        )
    """)
    ensure_column(cursor, "placement_scrape_runs", "user_id", "INTEGER DEFAULT 1")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")


def ensure_column(cursor, table_name: str, column_name: str, column_type: str):
    """Add a column when an older local SQLite database is missing it."""
    columns = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    if column_name not in [column[1] for column in columns]:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )


def ensure_placement_drives_user_scoped_unique(cursor):
    """Migrate older DBs from global drive uniqueness to per-user uniqueness."""
    row = cursor.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'placement_drives'
        """
    ).fetchone()
    if not row or not row[0]:
        return

    normalized_sql = " ".join(row[0].replace("\n", " ").split()).lower()
    if "unique(user_id, portal_name, external_id)" in normalized_sql:
        return
    if "unique(portal_name, external_id)" not in normalized_sql:
        return

    cursor.execute("ALTER TABLE placement_drives RENAME TO placement_drives_old")
    cursor.execute("""
        CREATE TABLE placement_drives (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER DEFAULT 1,
            portal_name      TEXT NOT NULL,
            external_id      TEXT,
            company_name     TEXT NOT NULL,
            role             TEXT,
            min_package      TEXT,
            max_package      TEXT,
            min_stipend      TEXT,
            max_stipend      TEXT,
            location         TEXT,
            duration         TEXT,
            criteria         TEXT,
            eligible_branches TEXT,
            deadline_date    TEXT,
            deadline_time    TEXT,
            job_description  TEXT,
            jd_summary       TEXT,
            document_url     TEXT,
            local_document   TEXT,
            apply_url        TEXT,
            status           TEXT DEFAULT 'open',
            source_hash      TEXT,
            first_seen_at    TEXT,
            last_seen_at     TEXT,
            UNIQUE(user_id, portal_name, external_id)
        )
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO placement_drives (
            id, user_id, portal_name, external_id, company_name, role,
            min_package, max_package, min_stipend, max_stipend, location,
            duration, criteria, eligible_branches, deadline_date, deadline_time,
            job_description, jd_summary, document_url, local_document, apply_url,
            status, source_hash, first_seen_at, last_seen_at
        )
        SELECT
            id, COALESCE(user_id, 1), portal_name, external_id, company_name, role,
            min_package, max_package, min_stipend, max_stipend, location,
            duration, criteria, eligible_branches, deadline_date, deadline_time,
            job_description, jd_summary, document_url, local_document, apply_url,
            status, source_hash, first_seen_at, last_seen_at
        FROM placement_drives_old
    """)
    cursor.execute("DROP TABLE placement_drives_old")

# Run init when this file is imported
if __name__ == "__main__":
    init_db()
    
