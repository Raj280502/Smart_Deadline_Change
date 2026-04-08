# 🤖 Smart Deadline Change

An **AI-powered deadline monitoring system** that automatically extracts deadlines from emails and messages, detects changes, predicts risk levels, syncs to Google Calendar, and sends Telegram notifications — all powered by a **multi-agent LangGraph pipeline** with **RAG-based Q&A**.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📧 **Multi-Source Ingestion** | Fetches messages from Gmail and Telegram |
| 🧠 **LLM Classification** | Uses Groq (Llama) to detect deadlines and extract structured data |
| 🕸️ **Multi-Agent Pipeline** | LangGraph workflow: Classifier → Router → RAG → Change Detection → Risk Prediction → Notification → Calendar |
| 🔍 **Semantic Search (RAG)** | ChromaDB vector store for similarity-based deadline matching |
| 📊 **Risk Prediction** | Scores deadlines based on sender behavior history + Indian holiday proximity |
| 📱 **Telegram Alerts** | Real-time notifications for changes and high-risk deadlines |
| 📅 **Google Calendar Sync** | Auto-creates/updates calendar events |
| 💬 **Chat Interface** | RAG-powered Q&A — ask questions about your deadlines |
| 🌐 **REST API** | FastAPI server with 17+ endpoints |

---

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Gmail     │     │   Telegram   │     │   LangGraph     │
│   API       │     │   Bot API    │     │   Pipeline      │
└──────┬──────┘     └──────┬───────┘     └────────┬────────┘
       │                   │                      │
       ▼                   ▼                      ▼
┌──────────────────────────────────────────────────────────┐
│                   Ingestion Layer                        │
│         Fetches & stores raw messages in SQLite          │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│              Multi-Agent LangGraph Pipeline               │
│                                                          │
│  ┌───────────┐                                          │
│  │Classifier │ → Detects deadline & extracts data       │
│  └─────┬─────┘                                          │
│        │                                                 │
│  ┌─────▼─────┐                                          │
│  │  Router   │ → Relevant or Discard?                   │
│  └─────┬─────┘                                          │
│        │                                                 │
│  ┌─────▼─────┐                                          │
│  │ RAG Search│ → Finds similar deadlines (ChromaDB)     │
│  └─────┬─────┘                                          │
│        │                                                 │
│  ┌─────▼─────────┐                                      │
│  │Change Detection│ → Compares old vs new               │
│  └─────┬─────────┘                                      │
│        │                                                 │
│  ┌─────▼──────┐                                         │
│  │Prediction  │ → Risk score (sender + holidays)        │
│  └─────┬──────┘                                         │
│        │                                                 │
│  ┌─────▼──────────┐                                     │
│  │Notification    │ → Telegram alerts                   │
│  └─────┬──────────┘                                     │
│        │                                                 │
│  ┌─────▼──────┐                                         │
│  │Calendar    │ → Google Calendar sync                  │
│  └────────────┘                                         │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                    Storage Layer                          │
│   SQLite (structured)  |  ChromaDB (vector embeddings)   │
└──────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Groq API Key** (free at https://console.groq.com)
- **Google Cloud Credentials** (Gmail & Calendar API)
- **Telegram Bot Token** (free from @BotFather)
- **Telegram Chat ID**

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/smart-deadline-change.git
cd smart-deadline-change
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Groq LLM
GROQ_API_KEY=your_groq_api_key_here

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Google OAuth (place token.json in project root after OAuth setup)
# No env var needed — token.json is auto-generated on first run
```

### 5. Initialize Database

```bash
python storage/database.py
```

### 6. Run the Application

**Option A: Start the API Server**

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

→ API available at: http://localhost:8000

**Option B: Run Ingestion + Processing Pipeline**

```bash
python integrations/ingestion.py
python orchestrator/graph.py
```

**Option C: Test the Chat Interface**

```bash
python agents/chat_agent.py
```

---

## 📁 Project Structure

```
smart-deadline-change/
├── agents/                 # AI agent modules
│   ├── chat_agent.py       # RAG-powered Q&A interface
│   ├── classifier.py       # LLM-based deadline detection
│   ├── notification.py     # Telegram alert formatting
│   └── prediction.py       # Risk scoring engine
├── api/                    # FastAPI REST server
│   └── main.py             # API endpoints
├── integrations/           # External service connections
│   ├── calendar_client.py  # Google Calendar API
│   ├── gmail_client.py     # Gmail API
│   ├── ingestion.py        # Multi-source data fetcher
│   └── telegram_client.py  # Telegram Bot API
├── orchestrator/           # LangGraph pipeline
│   ├── graph.py            # Workflow definition
│   ├── nodes.py            # Individual node implementations
│   └── state.py            # Shared state structure
├── storage/                # Data persistence
│   ├── database.py         # SQLite setup & schema
│   └── vector_store.py     # ChromaDB vector store
├── frontend/               # Web UI (React/Vite)
├── chroma_db/              # Persistent vector database
├── smart_deadline.db       # SQLite database (auto-created)
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (create this)
└── README.md               # This file
```

---

## 🌐 API Endpoints

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Server status |
| `GET` | `/health` | Health check |
| `POST` | `/ingest` | Trigger message ingestion |
| `POST` | `/process` | Process all unprocessed messages |
| `POST` | `/process/single` | Process a single message by ID |

### Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/messages` | List raw messages |
| `GET` | `/deadlines` | List all deadlines |
| `GET` | `/changes` | List change history |

### Vector Store

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/vector-store/search?q=query` | Semantic search |
| `GET` | `/vector-store/all` | List all stored items |

### Predictions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/predictions/risk` | High-risk deadlines |
| `GET` | `/predictions/senders` | Sender statistics |

### Notifications & Calendar

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/notify/test` | Send test Telegram notification |
| `POST` | `/calendar/test` | Create test calendar event |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat?question=text` | Ask a question about deadlines |
| `GET` | `/chat/history` | Get conversation history |
| `DELETE` | `/chat/history` | Clear chat history |

---

## 🔧 Configuration

### Google Cloud Setup (Gmail & Calendar)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable these APIs:
   - Gmail API
   - Google Calendar API
4. Create **OAuth 2.0 credentials** (Desktop app type)
5. Download the credentials as `credentials.json`
6. Place it in the project root
7. On first run, a browser window will open for OAuth authorization
8. `token.json` will be auto-generated and saved

### Telegram Bot Setup

1. Message **@BotFather** on Telegram
2. Send `/newbot` and follow instructions
3. Copy the **Bot Token**
4. Get your **Chat ID** by messaging your bot and checking: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`

### Groq API Key

1. Sign up at https://console.groq.com
2. Create a new API key
3. Add it to your `.env` file

---

## 📊 How Risk Scoring Works

The prediction engine calculates risk based on **two factors**:

### 1. Sender Change Rate (0.0 - 0.8)
```
sender_score = (total_changes / total_deadlines) × recency_weight
```
- `recency_weight`: 1.3 if last change within 30 days, 1.1 if within 60 days, else 1.0

### 2. Festival/Holiday Proximity (0.0 - 0.2)
- **+0.2** if deadline is within 5 days of an Indian holiday
- **+0.1** if deadline is within 2 days of holiday (imminent)

### Risk Levels

| Score | Level | Description |
|-------|-------|-------------|
| 0.0 - 0.3 | 🟢 LOW | Stable deadline, unlikely to change |
| 0.3 - 0.6 | 🟡 MEDIUM | Moderate risk, monitor closely |
| 0.6 - 0.8 | 🔴 HIGH | Likely to change, alert sent |
| 0.8 - 1.0 | 🚨 CRITICAL | Very unstable, immediate action needed |

---

## 🧪 Testing

```bash
# Test Groq LLM connection
python test_groq.py

# Test database initialization
python storage/database.py

# Test Telegram notification
python agents/notification.py

# Test Google Calendar integration
python integrations/calendar_client.py

# Test chat agent with sample questions
python agents/chat_agent.py
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **LLM** | Groq (Llama 3.3 70B, Llama 4 Scout) |
| **Agent Framework** | LangGraph + LangChain |
| **Vector DB** | ChromaDB (persistent) |
| **Embedding Model** | all-MiniLM-L6-v2 (local) |
| **Relational DB** | SQLite |
| **API Framework** | FastAPI + Uvicorn |
| **Frontend** | React + Vite |
| **HTTP Client** | httpx |
| **External APIs** | Gmail, Google Calendar, Telegram Bot |

---

## 📈 Data Flow

```
1. Ingestion
   Gmail/Telegram → raw_messages (SQLite)

2. Classification
   raw_message → Groq LLM → structured deadline data

3. Routing
   If deadline-related (confidence ≥ 0.5) → continue
   Otherwise → discard & mark processed

4. RAG Search
   Query ChromaDB for similar deadlines

5. Change Detection
   Compare new vs existing deadline fields
   → If changes found: log to change_history

6. Risk Prediction
   Calculate sender behavior risk + holiday proximity
   → Update deadline.risk_score

7. Notification
   If HIGH/CRITICAL risk or change detected → Telegram alert

8. Calendar Sync
   Create/update Google Calendar event

9. Vector Store Update
   Add deadline to ChromaDB for future semantic search
```

---

## 🚨 Common Issues

| Issue | Solution |
|-------|----------|
| `GROQ_API_KEY not found` | Ensure `.env` file exists in project root |
| `Google OAuth error` | Run `python integrations/gmail_client.py` to complete OAuth flow |
| `Telegram not sending` | Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` |
| `ChromaDB errors` | Delete `chroma_db/` folder and restart (will rebuild) |
| `Database not found` | Run `python storage/database.py` to initialize |

---

## 📝 License

MIT License — see LICENSE file for details.

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📬 Contact

For questions or support, open an issue on GitHub.

---

**Built with ❤️ using LangGraph, Groq, and FastAPI**
