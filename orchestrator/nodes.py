import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from storage.database import get_connection
from storage.vector_store import (
    search_similar_deadlines,
    add_deadline_to_vector_store
)
from agents.classifier import classify_message, parse_llm_response


# ══════════════════════════════════════════════════════
# NODE 1 — Classifier Node
# Reads current_message from state
# Runs LLM classification
# Returns classification result
# ══════════════════════════════════════════════════════
def classifier_node(state: dict) -> dict:
    msg = state["current_message"]
    log = state.get("agent_log", [])

    print(f"\n[Classifier Node] Processing: {msg.get('subject') or msg.get('body', '')[:50]}")

    result = classify_message(
        message_id=msg["id"],
        sender=msg.get("sender", ""),
        subject=msg.get("subject", ""),
        body=msg.get("body", "")
    )

    log.append(f"Classifier: is_deadline={result['is_deadline_related']}, confidence={result['confidence']}")

    return {
        "classification": result,
        "agent_log":      log
    }


# ══════════════════════════════════════════════════════
# NODE 2 — Router Node (conditional logic)
# Decides what happens next based on classification
# ══════════════════════════════════════════════════════
def router_node(state: dict) -> dict:
    classification = state.get("classification", {})
    log            = state.get("agent_log", [])

    is_relevant = classification.get("is_deadline_related", False)
    confidence  = classification.get("confidence", 0.0)

    if is_relevant and confidence >= 0.5:
        next_action = "rag_search"
        log.append("Router: deadline detected → routing to RAG search")
    else:
        next_action = "discard"
        log.append(f"Router: not relevant (confidence={confidence}) → discarding")

    return {
        "next_action": next_action,
        "agent_log":   log
    }


# ══════════════════════════════════════════════════════
# NODE 3 — RAG Search Node
# Takes the classified deadline
# Searches ChromaDB for similar existing deadlines
# This is the Agentic RAG step
# ══════════════════════════════════════════════════════
def rag_search_node(state: dict) -> dict:
    classification = state["classification"]
    log            = state.get("agent_log", [])

    # Build search query from extracted deadline info
    query_parts = []
    if classification.get("event_name"):
        query_parts.append(classification["event_name"])
    if classification.get("deadline_date"):
        query_parts.append(classification["deadline_date"])

    query = " ".join(query_parts)
    print(f"\n[RAG Search Node] Searching for: '{query}'")

    # Search ChromaDB for similar deadlines
    similar = search_similar_deadlines(
        query_text=query,
        top_k=3,
        threshold=0.6   # only return strong matches
    )

    if similar:
        print(f"  Found {len(similar)} similar deadline(s):")
        for s in similar:
            print(f"  → '{s['text']}' (similarity: {s['similarity']})")
    else:
        print("  No similar deadlines found — this is a new deadline.")

    log.append(f"RAG Search: found {len(similar)} similar deadline(s) for '{query}'")

    return {
        "similar_deadlines": similar,
        "agent_log":         log
    }


# ══════════════════════════════════════════════════════
# NODE 4 — Change Detection Node
# Compares new deadline with similar ones found by RAG
# Decides: new deadline OR change to existing one
# ══════════════════════════════════════════════════════
def change_detection_node(state: dict) -> dict:
    classification = state["classification"]
    similar        = state.get("similar_deadlines", [])
    msg            = state["current_message"]
    log            = state.get("agent_log", [])

    change_detected = False
    change_details  = {}

    if similar:
        # Get the most similar existing deadline
        best_match  = similar[0]
        similarity  = best_match["similarity"]
        metadata    = best_match["metadata"]

        print(f"\n[Change Detection Node] Best match similarity: {similarity}")

        # High similarity = likely the same event
        if similarity >= 0.75:
            old_date = metadata.get("deadline_date", "")
            new_date = classification.get("deadline_date", "")
            old_time = metadata.get("deadline_time", "")
            new_time = classification.get("deadline_time", "")
            old_venue = metadata.get("venue", "")
            new_venue = classification.get("venue", "")

            changes = []

            # Check each field for changes
            if old_date and new_date and old_date != new_date:
                changes.append({
                    "field":     "deadline_date",
                    "old_value": old_date,
                    "new_value": new_date
                })

            if old_time and new_time and old_time != new_time:
                changes.append({
                    "field":     "deadline_time",
                    "old_value": old_time,
                    "new_value": new_time
                })

            if old_venue and new_venue and old_venue != new_venue:
                changes.append({
                    "field":     "venue",
                    "old_value": old_venue,
                    "new_value": new_venue
                })

            # Also check if LLM itself flagged it as a change
            if classification.get("is_change"):
                change_detected = True

            if changes:
                change_detected = True
                change_details  = {
                    "matched_deadline_id": best_match["id"],
                    "similarity":          similarity,
                    "changes":             changes,
                    "description":         classification.get("change_description", "")
                }
                print(f"  ⚠️  CHANGE DETECTED: {changes}")
            else:
                print("  Same event found but no field changes detected.")

        else:
            print(f"  Similarity {similarity} below threshold — treating as new deadline.")

    else:
        print("\n[Change Detection Node] No similar deadlines — saving as new.")

    # Save deadline to SQLite + ChromaDB
    save_deadline_to_db(
        msg=msg,
        classification=classification,
        change_detected=change_detected,
        change_details=change_details
    )

    log.append(f"Change Detection: change_detected={change_detected}")

    return {
        "change_detected": change_detected,
        "change_details":  change_details,
        "agent_log":       log
    }


# ══════════════════════════════════════════════════════
# NODE 5 — Discard Node
# Marks message as processed without saving a deadline
# ══════════════════════════════════════════════════════
def discard_node(state: dict) -> dict:
    msg = state["current_message"]
    log = state.get("agent_log", [])

    # Mark as processed so we don't re-classify it
    conn = get_connection()
    conn.execute(
        "UPDATE raw_messages SET processed = 1 WHERE id = ?",
        (msg["id"],)
    )
    conn.commit()
    conn.close()

    log.append("Discard: message marked as processed, no deadline saved")
    print(f"  [Discard Node] Skipped: {msg.get('subject', '')[:50]}")

    return {"agent_log": log}


# ══════════════════════════════════════════════════════
# HELPER — Save deadline to SQLite + ChromaDB
# ══════════════════════════════════════════════════════
def save_deadline_to_db(msg: dict, classification: dict,
                        change_detected: bool, change_details: dict):
    conn   = get_connection()
    cursor = conn.cursor()

    # Save to deadlines table
    cursor.execute("""
        INSERT INTO deadlines
            (message_id, event_name, deadline_date, deadline_time,
             venue, confidence, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        msg["id"],
        classification.get("event_name"),
        classification.get("deadline_date"),
        classification.get("deadline_time"),
        classification.get("venue"),
        classification.get("confidence", 0.0),
        msg.get("source", "unknown"),
        datetime.now().isoformat()
    ))

    deadline_id = cursor.lastrowid

    # Save change history if change detected
    if change_detected and change_details.get("changes"):
        for change in change_details["changes"]:
            cursor.execute("""
                INSERT INTO change_history
                    (deadline_id, field_changed, old_value,
                     new_value, detected_at, source_message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                deadline_id,
                change["field"],
                change["old_value"],
                change["new_value"],
                datetime.now().isoformat(),
                msg["id"]
            ))

    # Mark message as processed
    conn.execute(
        "UPDATE raw_messages SET processed = 1 WHERE id = ?",
        (msg["id"],)
    )

    conn.commit()
    conn.close()

    # Add to ChromaDB vector store
    add_deadline_to_vector_store(deadline_id, {
        "event_name":    classification.get("event_name"),
        "deadline_date": classification.get("deadline_date"),
        "deadline_time": classification.get("deadline_time"),
        "venue":         classification.get("venue"),
        "source":        msg.get("source"),
        "message_id":    msg["id"]
    })

    print(f"  [Saved] '{classification.get('event_name')}' → deadline_id={deadline_id}")
    
# ══════════════════════════════════════════════════════
# NODE 6 — Prediction Node
# Runs after change_detection
# Calculates risk score for the deadline
# Updates sender stats
# ══════════════════════════════════════════════════════
def prediction_node(state: dict) -> dict:
    classification = state.get("classification", {})
    change_detected = state.get("change_detected", False)
    msg            = state["current_message"]
    log            = state.get("agent_log", [])

    from agents.prediction import (
        update_sender_stats,
        calculate_risk_score,
        update_deadline_risk_score
    )
    from storage.database import get_connection

    sender        = msg.get("sender", "unknown")
    deadline_date = classification.get("deadline_date")

    # Update sender stats with this interaction
    update_sender_stats(sender, is_change=change_detected)

    # Calculate risk score
    risk_result = calculate_risk_score(sender, deadline_date)
    risk_score  = risk_result["risk_score"]
    risk_level  = risk_result["risk_level"]

    print(f"\n[Prediction Node] Sender: {sender[:40]}")
    print(f"  Risk Score: {risk_score} ({risk_level})")
    for reason in risk_result["reasons"]:
        print(f"  → {reason}")

    # Update the deadline record with risk score
    conn = get_connection()
    row  = conn.execute(
        "SELECT id FROM deadlines WHERE message_id = ?",
        (msg["id"],)
    ).fetchone()
    conn.close()

    if row:
        update_deadline_risk_score(row["id"], risk_score)

    log.append(
        f"Prediction: risk_score={risk_score}, level={risk_level}"
    )

    return {
        "agent_log": log
    }
    
# ══════════════════════════════════════════════════════
# NODE 7 — Notification Node
# Runs after prediction node
# Sends Telegram alert if:
# 1. A change was detected (always notify)
# 2. New deadline with HIGH/CRITICAL risk (notify)
# 3. New deadline with high urgency (notify)
# ══════════════════════════════════════════════════════
def notification_node(state: dict) -> dict:
    classification  = state.get("classification", {})
    change_detected = state.get("change_detected", False)
    change_details  = state.get("change_details", {})
    msg             = state["current_message"]
    log             = state.get("agent_log", [])

    from agents.notification import (
        send_message,
        format_change_alert,
        format_new_deadline_alert
    )
    from agents.prediction import calculate_risk_score
    from storage.database import get_connection

    sender      = msg.get("sender", "unknown")
    deadline_date = classification.get("deadline_date")

    # Get risk result for this sender
    risk_result = calculate_risk_score(sender, deadline_date)
    risk_level  = risk_result.get("risk_level", "LOW")
    urgency     = classification.get("urgency", "low")

    notification_sent = False

    # ── Case 1: Change detected → always notify ──────
    if change_detected and change_details.get("changes"):
        text = format_change_alert(
            classification=classification,
            change_details=change_details,
            risk_result=risk_result,
            sender=sender
        )
        send_message(text)
        notification_sent = True
        log.append("Notification: change alert sent")

    # ── Case 2: New deadline, HIGH/CRITICAL risk ─────
    elif not change_detected and risk_level in ("HIGH", "CRITICAL"):
        text = format_new_deadline_alert(
            classification=classification,
            risk_result=risk_result,
            sender=sender
        )
        send_message(text)
        notification_sent = True
        log.append(f"Notification: high risk alert sent ({risk_level})")

    # ── Case 3: High urgency deadline ────────────────
    elif not change_detected and urgency == "high":
        text = format_new_deadline_alert(
            classification=classification,
            risk_result=risk_result,
            sender=sender
        )
        send_message(text)
        notification_sent = True
        log.append("Notification: urgent deadline alert sent")

    else:
        log.append("Notification: no alert needed")
        print(f"  [Notification Node] No alert needed for this message.")

    return {"agent_log": log}

def calendar_mcp_node(state: dict) -> dict:
    classification  = state.get("classification", {})
    change_detected = state.get("change_detected", False)
    change_details  = state.get("change_details", {})
    log             = state.get("agent_log", [])

    # Only sync if there's a deadline date
    if not classification.get("deadline_date"):
        log.append("Calendar MCP: no date found — skipped")
        return {"agent_log": log}

    print(f"\n[Calendar MCP Node] Syncing to Google Calendar...")

    try:
        from integrations.calendar_client import sync_deadline_to_calendar
        action = sync_deadline_to_calendar(
            classification=classification,
            change_detected=change_detected,
            change_details=change_details
        )
        log.append(f"Calendar MCP: {action}")

    except Exception as e:
        # Never let calendar errors break the pipeline
        print(f"  [Calendar MCP] Warning: {e}")
        log.append(f"Calendar MCP: error — {str(e)[:100]}")

    return {"agent_log": log}