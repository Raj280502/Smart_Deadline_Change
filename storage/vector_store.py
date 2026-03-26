import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from datetime import datetime


# ── Initialize Embedding Model ───────────────────────────────
# This runs locally — free, no API key needed
# all-MiniLM-L6-v2 is small (90MB) but very good for
# semantic similarity tasks
print("Loading embedding model...")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
print("Embedding model loaded.")


# ── Initialize ChromaDB ──────────────────────────────────────
# persist_directory means data is saved to disk
# so embeddings survive restarts
chroma_client = chromadb.PersistentClient(
    path="./chroma_db",
)


# Our collection — like a table but for vectors
# get_or_create means safe to call multiple times
deadline_collection = chroma_client.get_or_create_collection(
    name="deadlines",
    metadata={"hnsw:space": "cosine"}  # cosine similarity for text
)

def embed_deadline(deadline: dict) -> str:
    """
    Converts a deadline dictionary into a
    searchable text string for embedding.

    We combine event name + date + source into one string
    because that's what we want to match on semantically.
    """
    parts = []

    if deadline.get("event_name"):
        parts.append(deadline["event_name"])
    if deadline.get("deadline_date"):
        parts.append(f"on {deadline['deadline_date']}")
    if deadline.get("deadline_time"):
        parts.append(f"at {deadline['deadline_time']}")
    if deadline.get("venue"):
        parts.append(f"at {deadline['venue']}")

    return " ".join(parts) if parts else "unknown deadline"

def add_deadline_to_vector_store(deadline_id: int, deadline: dict):
    """
    Embeds a deadline and stores it in ChromaDB.

    deadline_id: the SQLite row ID (used as unique key)
    deadline: dict with event_name, deadline_date, etc.
    """
    text = embed_deadline(deadline)

    # Generate embedding vector
    vector = embedding_model.encode(text).tolist()

    # Store in ChromaDB with metadata
    # metadata lets us filter and retrieve deadline details
    deadline_collection.add(
        ids=[str(deadline_id)],
        embeddings=[vector],
        documents=[text],
        metadatas=[{
            "event_name":    deadline.get("event_name")    or "",
            "deadline_date": deadline.get("deadline_date") or "",
            "deadline_time": deadline.get("deadline_time") or "",
            "venue":         deadline.get("venue")         or "",
            "source":        deadline.get("source")        or "",
            "message_id":    deadline.get("message_id")    or "",
            "added_at":      datetime.now().isoformat()
        }]
    )

    print(f"  Added to vector store: '{text}'")


def search_similar_deadlines(query_text: str, top_k: int = 3,
                              threshold: float = 0.7):
    """
    Searches ChromaDB for deadlines similar to query_text.

    Returns list of matches above the similarity threshold.
    Each match has: id, text, metadata, similarity_score.

    This is the core of our RAG + Change Detection pipeline.
    """
    # Check if collection has any data
    if deadline_collection.count() == 0:
        return []

    # Embed the query
    query_vector = embedding_model.encode(query_text).tolist()

    # Search ChromaDB
    results = deadline_collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, deadline_collection.count())
    )

    matches = []
    if not results["ids"][0]:
        return matches

    for i, doc_id in enumerate(results["ids"][0]):
        # ChromaDB returns distances (0 = identical, 2 = opposite)
        # Convert to similarity score (1 = identical, 0 = no match)
        distance   = results["distances"][0][i]
        similarity = 1 - (distance / 2)

        if similarity >= threshold:
            matches.append({
                "id":         doc_id,
                "text":       results["documents"][0][i],
                "metadata":   results["metadatas"][0][i],
                "similarity": round(similarity, 4)
            })

    # Sort by similarity descending
    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches


def get_all_deadlines_in_store() -> list:
    """Returns all deadlines currently in ChromaDB."""
    if deadline_collection.count() == 0:
        return []

    results = deadline_collection.get()
    items   = []

    for i, doc_id in enumerate(results["ids"]):
        items.append({
            "id":       doc_id,
            "text":     results["documents"][i],
            "metadata": results["metadatas"][i]
        })

    return items


def remove_deadline_from_store(deadline_id: int):
    """Remove a deadline from ChromaDB by its ID."""
    deadline_collection.delete(ids=[str(deadline_id)])


if __name__ == "__main__":
    print("\n── Vector Store Test ──\n")

    # Test 1: Add some sample deadlines
    test_deadlines = [
        {
            "id": 1,
            "data": {
                "event_name":    "Machine Learning Exam",
                "deadline_date": "2026-03-27",
                "deadline_time": "10:00",
                "venue":         "Room 301",
                "source":        "gmail",
                "message_id":    "test_001"
            }
        },
        {
            "id": 2,
            "data": {
                "event_name":    "Data Structures Assignment",
                "deadline_date": "2026-03-25",
                "deadline_time": "23:59",
                "venue":         None,
                "source":        "gmail",
                "message_id":    "test_002"
            }
        },
        {
            "id": 3,
            "data": {
                "event_name":    "Project Submission",
                "deadline_date": "2026-04-01",
                "deadline_time": "17:00",
                "venue":         "Lab 204",
                "source":        "telegram",
                "message_id":    "test_003"
            }
        }
    ]

    print("Adding test deadlines to vector store...")
    for item in test_deadlines:
        add_deadline_to_vector_store(item["id"], item["data"])

    print(f"\nTotal in store: {deadline_collection.count()}")

    # Test 2: Search for similar deadlines
    print("\n── Search Tests ──\n")

    queries = [
        "ML exam rescheduled",
        "data structures homework due",
        "submit project by April"
    ]

    for query in queries:
        print(f"Query: '{query}'")
        matches = search_similar_deadlines(query, threshold=0.3)
        if matches:
            for m in matches:
                print(f"  Match: '{m['text']}' | similarity: {m['similarity']}")
        else:
            print("  No matches found.")
        print()