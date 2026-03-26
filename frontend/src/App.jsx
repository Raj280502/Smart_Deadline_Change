import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = "http://localhost:8000";

// ── Helpers ──────────────────────────────────────────────────
function getRiskLevel(score) {
  if (score >= 0.8) return "CRITICAL";
  if (score >= 0.6) return "HIGH";
  if (score >= 0.3) return "MEDIUM";
  return "LOW";
}

function getRiskColor(level) {
  return {
    CRITICAL: "text-red-400 bg-red-400/10 border-red-400/30",
    HIGH:     "text-orange-400 bg-orange-400/10 border-orange-400/30",
    MEDIUM:   "text-amber-400 bg-amber-400/10 border-amber-400/30",
    LOW:      "text-green-400 bg-green-400/10 border-green-400/30",
  }[level] || "text-slate-400 bg-slate-400/10 border-slate-400/30";
}

function formatDate(d) {
  if (!d) return "No date";
  const dt = new Date(d);
  return dt.toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric"
  });
}

// ── Stat Card ─────────────────────────────────────────────────
function StatCard({ value, label, color }) {
  return (
    <div className="bg-[#0d1320] border border-[#1e2d45] rounded-xl p-5 text-center">
      <div className={`text-4xl font-black ${color}`}>{value}</div>
      <div className="text-xs text-slate-500 mt-2 uppercase tracking-widest">{label}</div>
    </div>
  );
}

// ── Deadline Card ─────────────────────────────────────────────
function DeadlineCard({ d }) {
  const risk  = getRiskLevel(d.risk_score || 0);
  const color = getRiskColor(risk);
  return (
    <div className="bg-[#111827] border border-[#1e2d45] rounded-lg p-4 hover:border-cyan-500/30 transition-all">
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="font-bold text-sm text-white leading-tight">
          📌 {d.event_name}
        </span>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded border shrink-0 ${color}`}>
          {risk}
        </span>
      </div>
      <div className="text-xs text-slate-400 space-y-1">
        <div>📅 {formatDate(d.deadline_date)}
          {d.deadline_time && ` · ${d.deadline_time}`}
        </div>
        {d.venue && <div>📍 {d.venue}</div>}
        <div className="flex justify-between pt-1">
          <span>{d.source}</span>
          <span>Confidence: {((d.confidence || 0) * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
}

// ── Change Card ───────────────────────────────────────────────
function ChangeCard({ c }) {
  return (
    <div className="bg-amber-400/5 border border-amber-400/20 rounded-lg p-4">
      <div className="font-bold text-sm text-white mb-2">
        ⚠️ {c.event_name}
      </div>
      <div className="text-xs text-slate-400 mb-1 capitalize">
        {c.field_changed?.replace("_", " ")} changed:
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="text-red-400 line-through">{c.old_value}</span>
        <span className="text-slate-500">→</span>
        <span className="text-green-400 font-bold">{c.new_value}</span>
      </div>
      <div className="text-[10px] text-slate-600 mt-2">
        {c.detected_at?.slice(0, 10)}
      </div>
    </div>
  );
}

// ── Sender Row ────────────────────────────────────────────────
function SenderRow({ s }) {
  const rate    = s.change_rate || 0;
  const pct     = Math.round(rate * 100);
  const barColor= pct >= 60 ? "bg-red-500" : pct >= 30 ? "bg-amber-500" : "bg-green-500";
  return (
    <div className="bg-[#111827] border border-[#1e2d45] rounded-lg p-3">
      <div className="text-xs font-bold text-white mb-1 truncate">
        {s.sender}
      </div>
      <div className="flex justify-between text-[10px] text-slate-500 mb-2">
        <span>{s.total_deadlines} deadlines · {s.total_changes} changes</span>
        <span>{pct}% change rate</span>
      </div>
      <div className="w-full bg-[#1e2d45] rounded-full h-1.5">
        <div
          className={`h-1.5 rounded-full transition-all duration-700 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── Chat Bubble ───────────────────────────────────────────────
function Bubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div className={`max-w-[85%] px-4 py-2.5 rounded-xl text-sm leading-relaxed
        ${isUser
          ? "bg-violet-600/30 border border-violet-500/40 text-white"
          : "bg-cyan-500/10 border border-cyan-500/20 text-slate-200"
        }`}>
        {msg.content}
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────
export default function App() {
  const [tab,        setTab]        = useState("deadlines");
  const [deadlines,  setDeadlines]  = useState([]);
  const [changes,    setChanges]    = useState([]);
  const [senders,    setSenders]    = useState([]);
  const [messages,   setMessages]   = useState([
    { role: "assistant", content: "Hi Raj! 👋 Ask me anything about your deadlines." }
  ]);
  const [question,   setQuestion]   = useState("");
  const [loading,    setLoading]    = useState(false);
  const [chatLoading,setChatLoading]= useState(false);
  const [processing, setProcessing] = useState(false);
  const chatEndRef = useRef(null);

  // Auto scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Fetch all data
  async function fetchAll() {
    setLoading(true);
    try {
      const [dl, ch, sn] = await Promise.all([
        axios.get(`${API}/deadlines`),
        axios.get(`${API}/changes`),
        axios.get(`${API}/predictions/senders`),
      ]);
      setDeadlines(dl.data.deadlines    || []);
      setChanges(ch.data.changes        || []);
      setSenders(sn.data.sender_stats   || []);
    } catch (e) {
      console.error("Fetch error:", e);
    }
    setLoading(false);
  }

  // Run full pipeline
  async function runPipeline() {
    setProcessing(true);
    try {
      await axios.post(`${API}/ingest`);
      await axios.post(`${API}/process`);
      await fetchAll();
    } catch (e) {
      console.error("Pipeline error:", e);
    }
    setProcessing(false);
  }

  useEffect(() => { fetchAll(); }, []);

  // Send chat message
  async function sendMessage() {
    if (!question.trim() || chatLoading) return;
    const q = question.trim();
    setQuestion("");
    setMessages(prev => [...prev, { role: "user", content: q }]);
    setChatLoading(true);
    try {
      const res = await axios.post(
        `${API}/chat?question=${encodeURIComponent(q)}`
      );
      setMessages(prev => [...prev, {
        role: "assistant", content: res.data.answer
      }]);
    } catch {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "Sorry, something went wrong. Is the server running?"
      }]);
    }
    setChatLoading(false);
  }

  // Stats
  const highRisk = deadlines.filter(d => (d.risk_score || 0) >= 0.6).length;

  // Tabs
  const tabs = [
    { id: "deadlines", label: "📌 Deadlines" },
    { id: "changes",   label: "⚠️ Changes"   },
    { id: "senders",   label: "📊 Senders"   },
    { id: "chat",      label: "💬 Chat"      },
  ];

  return (
    <div className="min-h-screen bg-[#080c14] text-slate-200 font-sans">

      {/* Grid background */}
      <div className="fixed inset-0 opacity-[0.03] pointer-events-none"
        style={{
          backgroundImage: "linear-gradient(#00e5ff 1px, transparent 1px), linear-gradient(90deg, #00e5ff 1px, transparent 1px)",
          backgroundSize: "40px 40px"
        }}
      />

      <div className="relative z-10 max-w-6xl mx-auto px-6 py-10">

        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-block text-[10px] font-mono tracking-[3px] text-cyan-400
            border border-cyan-400/30 px-3 py-1 rounded mb-4">
            GENA I · MULTI-AGENT · RAG · MCP
          </div>
          <h1 className="text-4xl font-black mb-2"
            style={{
              background: "linear-gradient(135deg, #fff 0%, #00e5ff 50%, #7c3aed 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent"
            }}>
            Smart Deadline & Change
          </h1>
          <p className="text-slate-500 text-sm">
            Proactive AI monitoring for deadlines · Built with LangGraph + Groq
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-center gap-3 mb-8">
          <button
            onClick={runPipeline}
            disabled={processing}
            className="px-5 py-2 rounded-lg border border-cyan-400/50 text-cyan-400
              hover:bg-cyan-400/10 transition-all text-sm font-bold disabled:opacity-50"
          >
            {processing ? "⏳ Processing..." : "▶ Run Pipeline"}
          </button>
          <button
            onClick={fetchAll}
            disabled={loading}
            className="px-5 py-2 rounded-lg border border-slate-600 text-slate-400
              hover:bg-slate-800 transition-all text-sm disabled:opacity-50"
          >
            {loading ? "Loading..." : "🔄 Refresh"}
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          <StatCard value={deadlines.length} label="Deadlines"       color="text-cyan-400" />
          <StatCard value={changes.length}   label="Changes"         color="text-amber-400" />
          <StatCard value={highRisk}         label="High Risk"       color="text-red-400" />
          <StatCard value={senders.length}   label="Senders Tracked" color="text-green-400" />
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-[#0d1320] border border-[#1e2d45]
          rounded-xl p-1 w-fit">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-5 py-2 rounded-lg text-sm font-bold transition-all
                ${tab === t.id
                  ? "bg-cyan-400/10 text-cyan-400 border border-cyan-400/30"
                  : "text-slate-500 hover:text-slate-300"
                }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="bg-[#0d1320] border border-[#1e2d45] rounded-xl p-6">

          {/* Deadlines Tab */}
          {tab === "deadlines" && (
            <div>
              <h2 className="text-xs font-mono text-cyan-400 tracking-widest
                uppercase mb-4">
                All Extracted Deadlines
              </h2>
              {deadlines.length === 0
                ? <p className="text-slate-500 text-sm">
                    No deadlines yet. Click "Run Pipeline" to process emails.
                  </p>
                : <div className="grid grid-cols-2 gap-3">
                    {deadlines.map((d, i) => <DeadlineCard key={i} d={d} />)}
                  </div>
              }
            </div>
          )}

          {/* Changes Tab */}
          {tab === "changes" && (
            <div>
              <h2 className="text-xs font-mono text-amber-400 tracking-widest
                uppercase mb-4">
                Deadline Change History
              </h2>
              {changes.length === 0
                ? <p className="text-slate-500 text-sm">
                    No changes detected yet.
                  </p>
                : <div className="grid grid-cols-2 gap-3">
                    {changes.map((c, i) => <ChangeCard key={i} c={c} />)}
                  </div>
              }
            </div>
          )}

          {/* Senders Tab */}
          {tab === "senders" && (
            <div>
              <h2 className="text-xs font-mono text-green-400 tracking-widest
                uppercase mb-4">
                Sender Risk Profiles
              </h2>
              {senders.length === 0
                ? <p className="text-slate-500 text-sm">
                    No sender data yet.
                  </p>
                : <div className="space-y-3">
                    {senders.map((s, i) => <SenderRow key={i} s={s} />)}
                  </div>
              }
            </div>
          )}

          {/* Chat Tab */}
          {tab === "chat" && (
            <div>
              <h2 className="text-xs font-mono text-violet-400 tracking-widest
                uppercase mb-4">
                Ask Your Deadline Assistant
              </h2>

              {/* Suggested Questions */}
              <div className="flex flex-wrap gap-2 mb-4">
                {[
                  "What's due this week?",
                  "What changed recently?",
                  "Which deadlines are high risk?",
                  "Was anything cancelled?",
                ].map((q, i) => (
                  <button
                    key={i}
                    onClick={() => setQuestion(q)}
                    className="text-xs px-3 py-1.5 rounded-full border border-[#1e2d45]
                      text-slate-400 hover:border-violet-500/40 hover:text-violet-300
                      transition-all"
                  >
                    {q}
                  </button>
                ))}
              </div>

              {/* Messages */}
              <div className="bg-[#080c14] rounded-xl border border-[#1e2d45]
                p-4 h-72 overflow-y-auto mb-4">
                {messages.map((m, i) => <Bubble key={i} msg={m} />)}
                {chatLoading && (
                  <div className="flex justify-start mb-3">
                    <div className="px-4 py-2.5 rounded-xl text-sm
                      bg-cyan-500/10 border border-cyan-500/20 text-slate-400">
                      Thinking...
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Input */}
              <div className="flex gap-3">
                <input
                  className="flex-1 bg-[#111827] border border-[#1e2d45] rounded-xl
                    px-4 py-3 text-sm text-white placeholder-slate-600
                    focus:outline-none focus:border-violet-500/50 transition-all"
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && sendMessage()}
                  placeholder="What deadlines do I have this week?"
                />
                <button
                  onClick={sendMessage}
                  disabled={chatLoading || !question.trim()}
                  className="px-6 py-3 rounded-xl border border-violet-500/50
                    text-violet-400 font-bold text-sm hover:bg-violet-500/10
                    transition-all disabled:opacity-50"
                >
                  Send
                </button>
              </div>
            </div>
          )}

        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-[10px] text-slate-600 font-mono
          tracking-widest">
          SMART DEADLINE & CHANGE · GENAI PROJECT · TEAM OF 3
        </div>

      </div>
    </div>
  );
}