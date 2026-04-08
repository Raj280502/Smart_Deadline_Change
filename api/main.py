from fastapi import FastAPI
from dotenv import load_dotenv
import os
from storage.database import init_db
from fastapi.middleware.cors import CORSMiddleware
from storage.database import get_connection
from integrations.ingestion import run_ingestion_once
from storage.database import get_connection
from orchestrator.graph import process_all_unprocessed
from storage.database import get_connection
from orchestrator.graph import process_message

load_dotenv()
init_db()


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
    allow_methods=["*"],
    allow_headers=["*"],
)

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
@app.get("/changes")
def list_changes():
    """View full change history with event names."""
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
    total = run_ingestion_once()
    return {"new_messages_saved": total}

@app.get("/messages")
def list_messages(source: str = None, unprocessed_only: bool = False):
    """
    View stored messages.
    Optional filters: ?source=gmail or ?source=telegram
                      ?unprocessed_only=true
    """
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
    result = process_all_unprocessed()
    return result

@app.post("/process/single")
def process_single(message_id: str):
    """Process one specific message through the graph."""
    conn = get_connection()
    msg  = conn.execute(
        "SELECT id, source, sender, subject, body FROM raw_messages WHERE id = ?",
        (message_id,)
    ).fetchone()
    conn.close()

    if not msg:
        return {"error": "Message not found"}

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
    from storage.vector_store import search_similar_deadlines
    matches = search_similar_deadlines(q, threshold=threshold)
    return {"query": q, "matches": matches}

@app.get("/vector-store/all")
def list_vector_store():
    """See everything stored in ChromaDB."""
    from storage.vector_store import get_all_deadlines_in_store
    items = get_all_deadlines_in_store()
    return {"total": len(items), "items": items}


@app.get("/predictions/risk")
def get_high_risk():
    """See all deadlines with HIGH or CRITICAL risk."""
    from agents.prediction import get_high_risk_deadlines
    deadlines = get_high_risk_deadlines(threshold=0.6)
    return {"high_risk_deadlines": deadlines}

@app.get("/predictions/senders")
def get_sender_stats():
    """See change rate stats per sender."""
    from agents.prediction import get_all_sender_stats
    stats = get_all_sender_stats()
    return {"sender_stats": stats}

@app.post("/notify/test")
def test_notification():
    """Send a test Telegram message to verify bot is working."""
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
    from agents.chat_agent import chat
    result = chat(question)
    return result


@app.get("/chat/history")
def chat_history():
    """View conversation history."""
    from agents.chat_agent import get_conversation_history
    return {"history": get_conversation_history()}

@app.delete("/chat/history")
def clear_chat_history():
    """Clear conversation history."""
    from agents.chat_agent import clear_history
    clear_history()
    return {"status": "history cleared"}