from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import time 
import sys
import os
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

import json
from datetime import datetime
from storage.database import get_connection

load_dotenv()

llm=ChatGroq(
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0
)

CLASSIFIER_PROMPT=ChatPromptTemplate.from_messages(
    [
        ("system", """You are a deadline detection assistant.
Your job is to analyze messages and emails and detect if they contain
any deadline, event, exam, submission, or schedule information.

You must ALWAYS respond with valid JSON only. No explanation, no markdown,
no extra text — just the raw JSON object.

If the message contains deadline information, extract it carefully.
If the date has changed or been rescheduled, mark is_change as true.

Respond with exactly this JSON structure:
{{
    "is_deadline_related": true or false,
    "confidence": 0.0 to 1.0,
    "event_name": "name of the event or exam or submission",
    "deadline_date": "YYYY-MM-DD or null if not found",
    "deadline_time": "HH:MM or null if not found",
    "venue": "location or null if not found",
    "is_change": true or false,
    "change_description": "what changed, or null if not a change",
    "urgency": "high, medium, or low"
}}

Rules:
- If not deadline related, still return the full JSON with is_deadline_related: false
- For deadline_date, always convert to YYYY-MM-DD format
- confidence should reflect how sure you are this is a deadline
- is_change should be true if the message says something was rescheduled,
  postponed, moved, changed, or cancelled
- urgency is high if deadline is within 3 days, medium within a week, low otherwise

"""),
        ("human",""" Analyze this message:
         Sender: {sender}
         Subject: {subject}
         Message: {body}

         Today's date is: {today}

         Respond with JSON only."""
         )
    ]
)

str_parser=StrOutputParser()

classifier_chain=CLASSIFIER_PROMPT|llm|str_parser


def parse_llm_response(response_text:str)-> dict:
    """
    Safely parse LLM response as JSON.
    LLMs sometimes wrap JSON in markdown code blocks
    like ```json ... ``` — we handle that here.
    """
    text=response_text.strip()
    if text.startswith("```"):
        lines= text.split("\n")
        text="\n".join(lines[1:-1])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  Warning: Could not parse LLM response as JSON: {e}")
        print(f"  Raw response: {response_text[:200]}")
        # Return a safe default
        return {
            "is_deadline_related": False,
            "confidence": 0.0,
            "event_name": None,
            "deadline_date": None,
            "deadline_time": None,
            "venue": None,
            "is_change": False,
            "change_description": None,
            "urgency": "low"
        }
def classify_message(message_id: str, sender: str,
                     subject: str, body: str) -> dict:
    """
    Runs one message through the classifier chain.
    Returns the extracted deadline info as a dictionary.
    """
    print(f"  Classifying: {subject or body[:50]}...")
    truncated_body = (body or "")[:2000]

    response = classifier_chain.invoke({
        "sender":  sender  or "Unknown",
        "subject": subject or "(no subject)",
        "body":    truncated_body,
        "today":   datetime.now().strftime("%Y-%m-%d")
    })

    result = parse_llm_response(response)
    return result




def save_deadline(message_id: str, result: dict, source: str):
    """
    Saves extracted deadline to the deadlines table.
    Only saves if the LLM is confident it's deadline-related.
    """
    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO deadlines
            (message_id, event_name, deadline_date, deadline_time,
             venue, confidence, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        message_id,
        result.get("event_name"),
        result.get("deadline_date"),
        result.get("deadline_time"),
        result.get("venue"),
        result.get("confidence", 0.0),
        source,
        datetime.now().isoformat()
    ))
    deadline_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    
    # Also add to ChromaDB vector store
    from storage.vector_store import add_deadline_to_vector_store
    add_deadline_to_vector_store(deadline_id, {
        "event_name":    result.get("event_name"),
        "deadline_date": result.get("deadline_date"),
        "deadline_time": result.get("deadline_time"),
        "venue":         result.get("venue"),
        "source":        source,
        "message_id":    message_id
    })

def mark_as_processed(message_id: str):
    """Mark message as processed so we don't classify it again."""
    conn = get_connection()
    conn.execute(
        "UPDATE raw_messages SET processed = 1 WHERE id = ?",
        (message_id,)
    )
    conn.commit()
    conn.close()


def run_classifier(confidence_threshold: float = 0.5):
    """
    Main function — reads all unprocessed messages,
    classifies each one, saves deadlines found.

    confidence_threshold: only save deadlines above this score
    """
    conn = get_connection()
    messages = conn.execute("""
        SELECT id, source, sender, subject, body
        FROM raw_messages
        WHERE processed = 0
        ORDER BY received_at ASC
    """).fetchall()
    conn.close()

    if not messages:
        print("No unprocessed messages found.")
        return

    print(f"Found {len(messages)} unprocessed messages. Classifying...\n")

    deadlines_found = 0
    changes_found   = 0

    for msg in messages:
        msg = dict(msg)

        result = classify_message(
            message_id=msg["id"],
            sender=msg["sender"]  or "",
            subject=msg["subject"] or "",
            body=msg["body"]    or ""
        )

        # Always mark as processed regardless of result
        mark_as_processed(msg["id"])

        if result["is_deadline_related"] and result["confidence"] >= confidence_threshold:
            save_deadline(msg["id"], result, msg["source"])
            deadlines_found += 1

            # Print what we found
            change_tag = " ⚠️ CHANGE DETECTED" if result["is_change"] else ""
            print(f"  ✅ DEADLINE FOUND{change_tag}")
            print(f"     Event:      {result['event_name']}")
            print(f"     Date:       {result['deadline_date']}")
            print(f"     Time:       {result['deadline_time']}")
            print(f"     Confidence: {result['confidence']}")
            print(f"     Urgency:    {result['urgency']}")
            if result["is_change"]:
                changes_found += 1
                print(f"     Change:     {result['change_description']}")
            print()
        else:
            print(f"  ⏭️  Not deadline-related (confidence: {result['confidence']})")
        time.sleep(2)

    print(f"\nDone. {deadlines_found} deadlines found, {changes_found} changes detected.")


if __name__ == "__main__":
    from storage.database import init_db
    init_db()
    run_classifier()
