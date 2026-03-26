import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime 
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser 
from storage.vector_store import search_similar_deadlines
from storage.database import get_connection


load_dotenv()

llm=ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.3
)

conversation_history=[]
MAX_HISTORY=10

CHAT_PROMPT=ChatPromptTemplate.from_messages(
    [
        ("system", """You are a smart deadline assistant for a college student.
You have access to the student's deadline database which has been provided to you as context.

Your job is to answer questions about:
- Upcoming deadlines
- Deadline changes and rescheduling
- High risk deadlines (likely to change again)
- Specific events or exams

Rules:
- Only answer based on the context provided
- If you don't find relevant info in context, say so clearly
- Be concise and helpful
- Format dates clearly (e.g., "April 10, 2026")
- Mention risk levels when relevant
- If a deadline was changed, always mention both old and new values
- Today's date is: {today}

DEADLINE CONTEXT FROM DATABASE:
{context}

CHANGE HISTORY CONTEXT:
{change_context}
"""),
    ("human", "{question}")
    ]
)

str_parser=StrOutputParser()
chat_chain= CHAT_PROMPT|llm|str_parser

def get_all_deadlines_context() -> str:
    """
    Fetches all deadlines from SQLite and formats
    them as readable context for the LLM.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT event_name, deadline_date, deadline_time,
               venue, confidence, risk_score, source, created_at
        FROM deadlines
        ORDER BY deadline_date ASC
    """).fetchall()
    conn.close()
    
    if not rows:
        return "No deadlines found in database."

    lines = []
    for r in rows:
        r = dict(r)
        line = f"- {r['event_name']}"
        if r['deadline_date']:
            line += f" | Date: {r['deadline_date']}"
        if r['deadline_time']:
            line += f" at {r['deadline_time']}"
        if r['venue']:
            line += f" | Venue: {r['venue']}"
        if r['risk_score']:
            risk = "HIGH" if r['risk_score'] >= 0.6 else "LOW"
            line += f" | Risk: {risk} ({r['risk_score']:.2f})"
        lines.append(line)

    return "\n".join(lines)

def get_change_history_context() -> str:
    """
    Fetches all change history from SQLite and
    formats it as readable context for the LLM.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT d.event_name, ch.field_changed,
               ch.old_value, ch.new_value, ch.detected_at
        FROM change_history ch
        JOIN deadlines d ON ch.deadline_id = d.id
        ORDER BY ch.detected_at DESC
        LIMIT 20
    """).fetchall()
    conn.close()

    if not rows:
        return "No changes detected yet."

    lines = []
    for r in rows:
        r    = dict(r)
        line = (
            f"- {r['event_name']}: "
            f"{r['field_changed']} changed from "
            f"'{r['old_value']}' to '{r['new_value']}' "
            f"(detected: {r['detected_at'][:10]})"
        )
        lines.append(line)

    return "\n".join(lines)


def search_relevant_context(question: str) -> str:
    """
    Agentic RAG — searches ChromaDB for deadlines
    relevant to the user's question.
    Returns formatted context string.
    """
    # Search ChromaDB by meaning
    matches = search_similar_deadlines(
        query_text=question,
        top_k=5,
        threshold=0.2  # low threshold to catch more results
    )

    if not matches:
        # Fallback — return all deadlines if no semantic match
        return get_all_deadlines_context()

    lines = []
    for m in matches:
        meta = m["metadata"]
        line = f"- {meta.get('event_name', 'Unknown')}"
        if meta.get('deadline_date'):
            line += f" | Date: {meta['deadline_date']}"
        if meta.get('deadline_time'):
            line += f" at {meta['deadline_time']}"
        if meta.get('venue'):
            line += f" | Venue: {meta['venue']}"
        line += f" | Relevance: {m['similarity']:.2f}"
        lines.append(line)

    return "\n".join(lines) if lines else get_all_deadlines_context()

def chat(question:str, session_id:str="default")-> dict:
    """Main chat function.
    Takes a question, searches relevant context,
    generates an answer using Groq.
    
    Returns dict with answer and sources used.

    """
    print(f"\n[Chat Agent] Question: {question}")
    
    semantic_context=search_relevant_context(question)
    change_context = get_change_history_context()
    
    answer = chat_chain.invoke({
        "question":       question,
        "context":        semantic_context,
        "change_context": change_context,
        "today":          datetime.now().strftime("%Y-%m-%d")
    })
    
    print(f"[Chat Agent] Answer: {answer[:100]}...")
    
    # Step 4 — Save to conversation history
    conversation_history.append({
        "role":      "user",
        "content":   question,
        "timestamp": datetime.now().isoformat()
    })
    conversation_history.append({
        "role":      "assistant",
        "content":   answer,
        "timestamp": datetime.now().isoformat()
    })
    # Keep only last N messages
    if len(conversation_history) > MAX_HISTORY * 2:
        conversation_history.pop(0)
        conversation_history.pop(0)
        
    return {
        "question":        question,
        "answer":          answer,
        "context_used":    semantic_context,
        "sources_checked": len(conversation_history)
    }

def get_conversation_history() -> list:
    """Returns the current conversation history."""
    return conversation_history

def clear_history():
    """Clears conversation history."""
    conversation_history.clear()
    
    

if __name__ == "__main__":
    from storage.database import init_db
    init_db()

    print("Chat Agent Test — type 'quit' to exit\n")
    print("=" * 50)

    test_questions = [
        "What deadlines do I have this week?",
        "What changed about the Data Structures exam?",
        "Which deadlines are high risk?",
        "When is the GenAI project due?",
        "Was anything cancelled?"
    ]

    for q in test_questions:
        print(f"\nQ: {q}")
        result = chat(q)
        print(f"A: {result['answer']}")
        print("-" * 50)