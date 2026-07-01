from fastapi import Depends, FastAPI, Header, HTTPException
from dotenv import load_dotenv
import os
import sys
import asyncio
import hmac
from pydantic import BaseModel, EmailStr
from storage.database import init_db
from fastapi.middleware.cors import CORSMiddleware
from storage.database import get_connection
from storage.auth_repository import (
    authenticate_user,
    create_access_token,
    create_user,
    get_credential_status,
    get_user_credentials,
    public_user,
    save_user_credentials,
    verify_access_token,
)

load_dotenv()
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
init_db()


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class CredentialSettings(BaseModel):
    groq_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    placement_portal_adapter: str = "my_college"
    tpo_login_url: str = "https://tpo.vierp.in"
    tpo_home_url: str = "https://tpo.vierp.in/home"
    tpo_drives_url: str = "https://tpo.vierp.in/apply_company"
    tpo_username: str = ""
    tpo_password: str = ""
    tpo_headless: str = "true"


def get_current_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    user = verify_access_token(authorization.removeprefix("Bearer ").strip())
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


app = FastAPI(
    title=os.getenv("APP_NAME", "Smart Deadline and Change"),
    description="Proactive AI deadline monitoring system",
    version="0.3.0"
)
# Allow CORS from frontend and Render domains
allowed_origins = [
    "http://localhost:5173",           # Local Vite dev server
    "http://localhost:3000",           # Local React dev server
    "https://smart-deadline-change.vercel.app",  # Vercel frontend (update if needed)
    os.getenv("FRONTEND_URL", ""),    # Custom frontend URL
]
# Filter out empty strings
allowed_origins = [url for url in allowed_origins if url]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

DEADLINE_TRACKER_ENABLED = os.getenv("ENABLE_DEADLINE_TRACKER", "false").lower() == "true"


def require_deadline_tracker_enabled():
    if not DEADLINE_TRACKER_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Deadline tracker is disabled in this deployment.",
        )


def require_admin_secret(secret: str):
    expected = os.getenv("PLACEMENT_CRON_SECRET") or os.getenv("ADMIN_RESET_SECRET")
    if not expected or not hmac.compare_digest(secret, expected):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

@app.get("/")
def root():
    return {"message": "Smart Deadline & Change is running", "version": app.version}

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "groq_key_loaded":     bool(os.getenv("GROQ_API_KEY")),
        "telegram_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    }


@app.post("/auth/register")
def register(payload: AuthRequest):
    try:
        user = create_user(payload.email, payload.password)
    except Exception:
        raise HTTPException(status_code=400, detail="User already exists")
    return {
        "token": create_access_token(user),
        "user": public_user(user),
    }


@app.post("/auth/login")
def login(payload: AuthRequest):
    user = authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "token": create_access_token(user),
        "user": public_user(user),
    }


@app.get("/auth/me")
def me(user=Depends(get_current_user)):
    return {
        "user": public_user(user),
        "credentials": get_credential_status(user["id"]),
    }


@app.put("/settings/credentials")
def update_credentials(
    payload: CredentialSettings,
    user=Depends(get_current_user),
):
    existing = get_user_credentials(user["id"])
    incoming = payload.model_dump()
    merged = {
        **existing,
        **{key: value for key, value in incoming.items() if value not in ("", None)},
    }
    save_user_credentials(user["id"], merged)
    return {
        "status": "saved",
        "credentials": get_credential_status(user["id"]),
    }


@app.get("/settings/credentials/status")
def credential_status(user=Depends(get_current_user)):
    return {"credentials": get_credential_status(user["id"])}


@app.post("/admin/reset-users")
def reset_users(secret: str):
    """
    Delete all locally stored users and placement data.

    Intended only for early deployment testing. Requires PLACEMENT_CRON_SECRET
    or ADMIN_RESET_SECRET to be configured in the environment.
    """
    require_admin_secret(secret)
    conn = get_connection()
    counts = {}
    for table in [
        "placement_drive_changes",
        "placement_drives",
        "placement_scrape_runs",
        "user_credentials",
        "users",
    ]:
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    return {"status": "reset", "deleted": counts}


@app.post("/placements/cron/run")
def run_placement_cron(secret: str):
    """
    Deployment-friendly placement watcher entrypoint.

    Use an external cron service to call this every 30 minutes. It checks every
    user with saved TPO credentials and sends Telegram notifications.
    """
    require_admin_secret(secret)
    from integrations.placement_scraper import sync_placement_drives

    conn = get_connection()
    users = conn.execute("SELECT id, email FROM users ORDER BY id").fetchall()
    conn.close()

    results = []
    for user_row in users:
        user_id = user_row["id"]
        status = get_credential_status(user_id)
        ready = (
            status.get("tpo_username")
            and status.get("tpo_password")
            and status.get("tpo_drives_url")
        )
        if not ready:
            results.append({
                "user_id": user_id,
                "email": user_row["email"],
                "status": "skipped",
                "reason": "TPO credentials missing",
            })
            continue
        credentials = get_user_credentials(user_id)
        result = sync_placement_drives(
            send_notifications=True,
            credentials=credentials,
            user_id=user_id,
        )
        results.append({
            "user_id": user_id,
            "email": user_row["email"],
            "result": result,
        })

    return {"status": "completed", "users_checked": len(users), "results": results}

@app.get("/changes")
def list_changes():
    """View full change history with event names."""
    require_deadline_tracker_enabled()
    conn = get_connection()
    rows = conn.execute("""
        SELECT ch.id, d.event_name, ch.field_changed,
               ch.old_value, ch.new_value,
               ch.detected_at, ch.source_message
        FROM change_history ch
        JOIN deadlines d ON ch.deadline_id = d.id
        ORDER BY ch.detected_at DESC
    """).fetchall()
    conn.close()
    return {"changes": [dict(r) for r in rows]}
@app.post("/ingest")
def trigger_ingestion():
    """Manually trigger ingestion from all sources."""
    require_deadline_tracker_enabled()
    from integrations.ingestion import run_ingestion_once
    total = run_ingestion_once()
    return {"new_messages_saved": total}

@app.get("/messages")
def list_messages(source: str = None, unprocessed_only: bool = False):
    """
    View stored messages.
    Optional filters: ?source=gmail or ?source=telegram
                      ?unprocessed_only=true
    """
    require_deadline_tracker_enabled()
    conn  = get_connection()
    query = "SELECT id, source, sender, subject, body, received_at, processed FROM raw_messages WHERE 1=1"
    params = []

    if source:
        query += " AND source = ?"
        params.append(source)
    if unprocessed_only:
        query += " AND processed = 0"

    query += " ORDER BY received_at DESC LIMIT 30"
    rows   = conn.execute(query, params).fetchall()
    conn.close()
    return {"messages": [dict(r) for r in rows]}

@app.post("/process")
def process_messages():
    """
    Runs all unprocessed messages through
    the full LangGraph multi-agent pipeline.
    Replaces the old /classify endpoint.
    """
    require_deadline_tracker_enabled()
    from orchestrator.graph import process_all_unprocessed
    result = process_all_unprocessed()
    return result

@app.post("/process/single")
def process_single(message_id: str):
    """Process one specific message through the graph."""
    require_deadline_tracker_enabled()
    conn = get_connection()
    msg  = conn.execute(
        "SELECT id, source, sender, subject, body FROM raw_messages WHERE id = ?",
        (message_id,)
    ).fetchone()
    conn.close()

    if not msg:
        return {"error": "Message not found"}

    from orchestrator.graph import process_message
    result = process_message(dict(msg))
    return {
        "message_id":      message_id,
        "classification":  result.get("classification"),
        "change_detected": result.get("change_detected"),
        "change_details":  result.get("change_details"),
        "agent_log":       result.get("agent_log")
    }

@app.get("/deadlines")
def list_deadlines():
    """View all extracted deadlines."""
    require_deadline_tracker_enabled()
    conn  = get_connection()
    rows  = conn.execute("""
        SELECT id, event_name, deadline_date, deadline_time,
               venue, confidence, source, created_at
        FROM deadlines
        ORDER BY deadline_date ASC
    """).fetchall()
    conn.close()
    return {"deadlines": [dict(r) for r in rows]}


@app.get("/vector-store/search")
def search_vector_store(q: str, threshold: float = 0.3):
    """
    Search deadlines by meaning.
    Example: /vector-store/search?q=ML exam rescheduled
    """
    require_deadline_tracker_enabled()
    from storage.vector_store import search_similar_deadlines
    matches = search_similar_deadlines(q, threshold=threshold)
    return {"query": q, "matches": matches}

@app.get("/vector-store/all")
def list_vector_store():
    """See everything stored in ChromaDB."""
    require_deadline_tracker_enabled()
    from storage.vector_store import get_all_deadlines_in_store
    items = get_all_deadlines_in_store()
    return {"total": len(items), "items": items}


@app.get("/predictions/risk")
def get_high_risk():
    """See all deadlines with HIGH or CRITICAL risk."""
    require_deadline_tracker_enabled()
    from agents.prediction import get_high_risk_deadlines
    deadlines = get_high_risk_deadlines(threshold=0.6)
    return {"high_risk_deadlines": deadlines}

@app.get("/predictions/senders")
def get_sender_stats():
    """See change rate stats per sender."""
    require_deadline_tracker_enabled()
    from agents.prediction import get_all_sender_stats
    stats = get_all_sender_stats()
    return {"sender_stats": stats}

@app.post("/notify/test")
def test_notification():
    """Send a test Telegram message to verify bot is working."""
    require_deadline_tracker_enabled()
    from agents.notification import send_message
    success = send_message(
        "🤖 <b>Smart Deadline & Change</b>\n\n"
        "✅ System is running!\n"
        "Your deadline monitoring is active."
    )
    return {"sent": success}

@app.post("/calendar/test")
def test_calendar():
    """Test Google Calendar integration."""
    require_deadline_tracker_enabled()
    from integrations.calendar_client import create_calendar_event
    event = create_calendar_event(
        event_name="Smart Deadline Test",
        deadline_date="2026-04-01",
        deadline_time="10:00",
        venue="Room 301",
        description="Test from Smart Deadline & Change system"
    )
    return {
        "status":  "created",
        "link":    event.get("htmlLink"),
        "eventId": event.get("id")
    }
@app.post("/chat")
def chat_endpoint(question: str):
    """
    Ask anything about your deadlines.
    Examples:
    - What's due this week?
    - What changed about the DS exam?
    - Which deadlines are high risk?
    - Was anything cancelled?
    """
    require_deadline_tracker_enabled()
    from agents.chat_agent import chat
    result = chat(question)
    return result


@app.get("/chat/history")
def chat_history():
    """View conversation history."""
    require_deadline_tracker_enabled()
    from agents.chat_agent import get_conversation_history
    return {"history": get_conversation_history()}

@app.delete("/chat/history")
def clear_chat_history():
    """Clear conversation history."""
    require_deadline_tracker_enabled()
    from agents.chat_agent import clear_history
    clear_history()
    return {"status": "history cleared"}


@app.post("/placements/sync")
def sync_placements(send_notifications: bool = True, user=Depends(get_current_user)):
    """
    Login to the active TPO portal adapter, detect placement drives,
    read JD documents, summarize them, store them, and notify Telegram.
    """
    from integrations.placement_scraper import sync_placement_drives
    credentials = get_user_credentials(user["id"])
    return sync_placement_drives(
        send_notifications=send_notifications,
        credentials=credentials,
        user_id=user["id"],
    )


@app.get("/placements")
def list_placements(limit: int = 100, user=Depends(get_current_user)):
    """List placement drives detected from the TPO portal."""
    from storage.placement_repository import list_placement_drives
    return {"placements": list_placement_drives(limit=limit, user_id=user["id"])}


@app.get("/placements/changes")
def list_placement_drive_changes(limit: int = 100, user=Depends(get_current_user)):
    """List changes detected in placement drive data."""
    from storage.placement_repository import list_placement_changes
    return {"changes": list_placement_changes(limit=limit, user_id=user["id"])}


@app.post("/placements/test-login")
def test_placement_login(user=Depends(get_current_user)):
    """Verify that the active placement portal adapter can log in."""
    from integrations.placement_portals.registry import get_active_adapter

    credentials = get_user_credentials(user["id"])
    adapter = get_active_adapter(config=credentials)
    try:
        success = adapter.login()
        return {"portal_name": adapter.portal_name, "login_success": success}
    except Exception as exc:
        return {
            "portal_name": adapter.portal_name,
            "login_success": False,
            "error": str(exc),
        }
    finally:
        adapter.close()


@app.post("/placements/scheduler/start")
def start_placement_scheduler(
    interval_minutes: int = 30,
    send_notifications: bool = True,
    user=Depends(get_current_user),
):
    """Start automatic placement portal checking."""
    from integrations.placement_scheduler import start_scheduler
    return start_scheduler(
        interval_minutes=interval_minutes,
        send_notifications=send_notifications,
        user_id=user["id"],
    )


@app.post("/placements/scheduler/stop")
def stop_placement_scheduler(user=Depends(get_current_user)):
    """Stop automatic placement portal checking."""
    from integrations.placement_scheduler import stop_scheduler
    return stop_scheduler()


@app.get("/placements/scheduler/status")
def placement_scheduler_status(user=Depends(get_current_user)):
    """View automatic placement watcher status."""
    from integrations.placement_scheduler import get_scheduler_status
    return get_scheduler_status()
