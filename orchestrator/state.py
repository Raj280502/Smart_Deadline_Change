from typing import TypedDict, List, Optional

class DeadlineState(TypedDict):
    """
    Shared state passed between all agents in the graph.
    Every agent reads from this and returns updates to it.
    TypedDict gives us type hints so we know what each field contains.
    """

    # ── Input ──────────────────────────────────────────
    # The current message being processed
    current_message: dict

    # ── Classifier Output ──────────────────────────────
    # Result from the classifier agent
    classification: dict

    # ── RAG Output ─────────────────────────────────────
    # Similar deadlines found in ChromaDB
    similar_deadlines: List[dict]

    # ── Change Detection Output ─────────────────────────
    # Whether a change was detected
    change_detected: bool
    change_details:  dict

    # ── Flow Control ────────────────────────────────────
    # Tells conditional edges which path to take
    next_action: str

    # ── Audit Trail ─────────────────────────────────────
    # Log of what each agent did — useful for debugging
    agent_log: List[str]