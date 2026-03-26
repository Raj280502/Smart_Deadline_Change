import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END
from orchestrator.state import DeadlineState
from orchestrator.nodes import (
    classifier_node,
    router_node,
    rag_search_node,
    change_detection_node,
    discard_node,
    prediction_node,
    notification_node  ,
    calendar_mcp_node    # ← add
         
)


def build_graph():
    """
    Builds and compiles the LangGraph multi-agent graph.
    Returns a compiled graph ready to process messages.
    """

    # Initialize graph with our shared state
    graph = StateGraph(DeadlineState)

    # ── Add Nodes ──────────────────────────────────────
    graph.add_node("classifier",       classifier_node)
    graph.add_node("router",           router_node)
    graph.add_node("rag_search",       rag_search_node)
    graph.add_node("change_detection", change_detection_node)
    graph.add_node("prediction",       prediction_node) 
    graph.add_node("notification", notification_node)# ← add
    graph.add_node("calendar_mcp", calendar_mcp_node)# ← add
    graph.add_node("discard",          discard_node)

    # ── Add Edges ──────────────────────────────────────
    # Entry point — always start with classifier
    graph.set_entry_point("classifier")

    # After classifier → always go to router
    graph.add_edge("classifier", "router")

    # Router uses conditional edge — checks next_action in state
    graph.add_conditional_edges(
        "router",
        lambda state: state["next_action"],  # reads next_action from state
        {
            "rag_search": "rag_search",  # if relevant → search ChromaDB
            "discard":    "discard"      # if not relevant → discard
        }
    )

    # After RAG search → always go to change detection
    graph.add_edge("rag_search", "change_detection")
    graph.add_edge("change_detection", "prediction")  # ← updated

    # Both change_detection and discard → END
    graph.add_edge("prediction", "notification")
    graph.add_edge("notification", "calendar_mcp")
    graph.add_edge("calendar_mcp", END)
    graph.add_edge("discard",          END)

    # Compile and return
    return graph.compile()


# Create one global instance — reused across all requests
deadline_graph = build_graph()


def process_message(message: dict) -> dict:
    """
    Runs a single message through the full agent graph.
    Returns the final state after all agents have processed it.
    """
    initial_state = {
        "current_message":   message,
        "classification":    {},
        "similar_deadlines": [],
        "change_detected":   False,
        "change_details":    {},
        "next_action":       "",
        "agent_log":         []
    }

    final_state = deadline_graph.invoke(initial_state)
    return final_state


def process_all_unprocessed():
    """
    Fetches all unprocessed messages from DB
    and runs each through the agent graph.
    """
    from storage.database import get_connection
    import time

    conn     = get_connection()
    messages = conn.execute("""
        SELECT id, source, sender, subject, body
        FROM raw_messages
        WHERE processed = 0
        ORDER BY received_at ASC
    """).fetchall()
    conn.close()

    if not messages:
        print("No unprocessed messages.")
        return {"processed": 0, "deadlines_found": 0, "changes_detected": 0}

    print(f"\nProcessing {len(messages)} messages through agent graph...\n")

    processed     = 0
    deadlines     = 0
    changes       = 0

    for msg in messages:
        msg    = dict(msg)
        result = process_message(msg)

        processed += 1
        if result.get("change_detected"):
            changes += 1
        if result.get("classification", {}).get("is_deadline_related"):
            deadlines += 1

        # Rate limit protection
        time.sleep(2)

    summary = {
        "processed":        processed,
        "deadlines_found":  deadlines,
        "changes_detected": changes
    }
    print(f"\n── Summary ──")
    print(f"  Processed:        {processed}")
    print(f"  Deadlines found:  {deadlines}")
    print(f"  Changes detected: {changes}")

    return summary


if __name__ == "__main__":
    from storage.database import init_db
    init_db()
    process_all_unprocessed()