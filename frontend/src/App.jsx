import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

function parseSummary(value) {
  if (!value) return {};
  if (typeof value === "object") return value;
  try {
    return JSON.parse(value);
  } catch {
    return { short_summary: value };
  }
}

function formatDate(value) {
  if (!value) return "No deadline";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function daysUntil(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);
  return Math.ceil((date - today) / 86400000);
}

function urgencyOf(drive) {
  const days = daysUntil(drive.deadline_date);
  if (days === null) return { label: "Watching", tone: "slate" };
  if (days < 0) return { label: "Closed", tone: "slate" };
  if (days === 0) return { label: "Today", tone: "red" };
  if (days <= 2) return { label: `${days}d left`, tone: "amber" };
  return { label: `${days}d left`, tone: "emerald" };
}

function riskLabel(score = 0) {
  if (score >= 0.8) return "Critical";
  if (score >= 0.6) return "High";
  if (score >= 0.3) return "Medium";
  return "Low";
}

function toneClasses(tone) {
  return {
    red: "border-red-400/40 bg-red-500/10 text-red-200",
    amber: "border-amber-400/40 bg-amber-500/10 text-amber-200",
    emerald: "border-emerald-400/40 bg-emerald-500/10 text-emerald-200",
    cyan: "border-cyan-400/40 bg-cyan-500/10 text-cyan-200",
    violet: "border-violet-400/40 bg-violet-500/10 text-violet-200",
    slate: "border-slate-600 bg-slate-800/70 text-slate-300",
  }[tone] || "border-slate-600 bg-slate-800/70 text-slate-300";
}

function StatusPill({ tone = "slate", children }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${toneClasses(tone)}`}>
      {children}
    </span>
  );
}

function Metric({ label, value, tone = "slate" }) {
  return (
    <div className="border border-slate-800 bg-slate-950/70 p-4">
      <div className="text-[11px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`mt-2 text-2xl font-black ${tone === "red" ? "text-red-300" : tone === "emerald" ? "text-emerald-300" : tone === "amber" ? "text-amber-300" : "text-slate-100"}`}>
        {value}
      </div>
    </div>
  );
}

function DriveListItem({ drive, active, onSelect }) {
  const urgency = urgencyOf(drive);
  const summary = parseSummary(drive.jd_summary);
  return (
    <button
      onClick={() => onSelect(drive)}
      className={`w-full border p-4 text-left transition ${
        active
          ? "border-cyan-400 bg-cyan-500/10"
          : "border-slate-800 bg-slate-950/70 hover:border-slate-600"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-bold text-slate-100">{drive.company_name}</div>
          <div className="mt-1 line-clamp-1 text-xs text-slate-400">{drive.role || "Role not mentioned"}</div>
        </div>
        <StatusPill tone={urgency.tone}>{urgency.label}</StatusPill>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-500">
        <span>Package: <b className="text-slate-300">{drive.min_package || "NA"}-{drive.max_package || "NA"}</b></span>
        <span>Stipend: <b className="text-slate-300">{drive.min_stipend || "NA"}</b></span>
        <span className="col-span-2">Deadline: <b className="text-slate-300">{formatDate(drive.deadline_date)}{drive.deadline_time ? `, ${drive.deadline_time}` : ""}</b></span>
      </div>
      {summary.short_summary && (
        <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-slate-400">
          {summary.short_summary}
        </p>
      )}
    </button>
  );
}

function DriveDetail({ drive }) {
  if (!drive) {
    return (
      <section className="border border-slate-800 bg-slate-950/70 p-6">
        <div className="text-sm font-bold text-slate-100">No drive selected</div>
        <p className="mt-2 text-sm text-slate-500">
          When a company appears, select it here to review package, eligibility, and JD summary.
        </p>
      </section>
    );
  }

  const urgency = urgencyOf(drive);
  const summary = parseSummary(drive.jd_summary);
  const skills = summary.skills_required || [];
  const responsibilities = summary.responsibilities || [];

  return (
    <section className="border border-slate-800 bg-slate-950/70">
      <div className="border-b border-slate-800 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xl font-black text-slate-50">{drive.company_name}</div>
            <div className="mt-1 text-sm text-cyan-300">{drive.role || "Role not mentioned"}</div>
          </div>
          <StatusPill tone={urgency.tone}>{urgency.label}</StatusPill>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-px border-b border-slate-800 bg-slate-800 text-sm">
        {[
          ["Min Package", drive.min_package],
          ["Max Package", drive.max_package],
          ["Min Stipend", drive.min_stipend],
          ["Max Stipend", drive.max_stipend],
          ["Location", drive.location],
          ["Duration", drive.duration],
        ].map(([label, value]) => (
          <div key={label} className="bg-slate-950 p-4">
            <div className="text-[11px] uppercase tracking-widest text-slate-500">{label}</div>
            <div className="mt-1 text-slate-200">{value || "Not mentioned"}</div>
          </div>
        ))}
      </div>

      <div className="space-y-5 p-5">
        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-amber-300">Deadline</div>
          <div className="mt-1 text-sm text-slate-200">{formatDate(drive.deadline_date)}{drive.deadline_time ? ` at ${drive.deadline_time}` : ""}</div>
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-emerald-300">Criteria</div>
          <p className="mt-1 text-sm leading-relaxed text-slate-300">{drive.criteria || "Criteria not mentioned."}</p>
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-cyan-300">Eligible Branches</div>
          <p className="mt-1 text-sm leading-relaxed text-slate-300">{drive.eligible_branches || "Eligible branches not listed yet."}</p>
        </div>

        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-violet-300">JD Summary</div>
          <p className="mt-2 text-sm leading-relaxed text-slate-300">
            {summary.short_summary || "JD summary will appear after a company document is extracted."}
          </p>
        </div>

        {skills.length > 0 && (
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-slate-400">Skills</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {skills.slice(0, 10).map((skill, index) => (
                <StatusPill key={`${skill}-${index}`} tone="cyan">{skill}</StatusPill>
              ))}
            </div>
          </div>
        )}

        {responsibilities.length > 0 && (
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-slate-400">Responsibilities</div>
            <ul className="mt-2 space-y-2 text-sm text-slate-300">
              {responsibilities.slice(0, 5).map((item, index) => (
                <li key={index} className="border-l border-slate-700 pl-3">{item}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-wrap gap-3 pt-2">
          {drive.document_url && (
            <a className="border border-cyan-400/40 px-4 py-2 text-sm font-bold text-cyan-200 hover:bg-cyan-500/10" href={drive.document_url} target="_blank" rel="noreferrer">
              Open JD
            </a>
          )}
          {drive.apply_url && (
            <a className="border border-emerald-400/40 px-4 py-2 text-sm font-bold text-emerald-200 hover:bg-emerald-500/10" href={drive.apply_url} target="_blank" rel="noreferrer">
              Open Portal
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

function DeadlineItem({ deadline }) {
  const risk = riskLabel(deadline.risk_score || 0);
  const tone = risk === "High" || risk === "Critical" ? "red" : risk === "Medium" ? "amber" : "slate";
  return (
    <div className="border border-slate-800 bg-slate-950/70 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-bold text-slate-100">{deadline.event_name}</div>
          <div className="mt-1 text-xs text-slate-500">{formatDate(deadline.deadline_date)}{deadline.deadline_time ? `, ${deadline.deadline_time}` : ""}</div>
        </div>
        <StatusPill tone={tone}>{risk}</StatusPill>
      </div>
    </div>
  );
}

function Bubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] border px-4 py-2 text-sm leading-relaxed ${
        isUser
          ? "border-cyan-400/40 bg-cyan-500/10 text-cyan-50"
          : "border-slate-800 bg-slate-950 text-slate-200"
      }`}>
        {msg.content}
      </div>
    </div>
  );
}

function AuthScreen({ onAuth, sessionMessage = "" }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(sessionMessage);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setError(sessionMessage);
  }, [sessionMessage]);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await axios.post(`${API}/auth/${mode}`, { email, password });
      onAuth(res.data);
    } catch (err) {
      setError(
        err.response?.data?.detail
        || err.message
        || "Authentication failed. Check backend URL and CORS settings."
      );
    }
    setLoading(false);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#090d12] p-6 text-slate-200">
      <form onSubmit={submit} className="w-full max-w-md border border-slate-800 bg-[#0d131b] p-6">
        <div className="text-xs font-bold uppercase tracking-[0.24em] text-cyan-300">Placement Watcher</div>
        <h1 className="mt-3 text-2xl font-black text-white">
          {mode === "login" ? "Sign in" : "Create account"}
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Use your own TPO, Groq, and Telegram credentials after login.
        </p>

        <div className="mt-6 space-y-3">
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="w-full border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none focus:border-cyan-400"
            placeholder="Email"
            required
          />
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none focus:border-cyan-400"
            placeholder="Password"
            required
          />
        </div>

        {error && <div className="mt-4 border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div>}

        <button
          disabled={loading}
          className="mt-5 w-full border border-cyan-400 bg-cyan-500/10 px-4 py-3 text-sm font-bold text-cyan-100 disabled:opacity-50"
        >
          {loading ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
        </button>

        <button
          type="button"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
          className="mt-4 w-full text-sm font-bold text-slate-400 hover:text-slate-200"
        >
          {mode === "login" ? "New here? Create an account" : "Already have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}

function SettingsPanel({ credentialStatus, onSave }) {
  const [form, setForm] = useState({
    groq_api_key: "",
    telegram_bot_token: "",
    telegram_chat_id: "",
    placement_portal_adapter: "my_college",
    tpo_login_url: "https://tpo.vierp.in",
    tpo_home_url: "https://tpo.vierp.in/home",
    tpo_drives_url: "https://tpo.vierp.in/apply_company",
    tpo_username: "",
    tpo_password: "",
    tpo_headless: "true",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  function update(key, value) {
    setSaved(false);
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await onSave(form);
      setSaved(true);
      setForm((current) => ({
        ...current,
        groq_api_key: "",
        telegram_bot_token: "",
        telegram_chat_id: "",
        tpo_username: "",
        tpo_password: "",
      }));
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Could not save credentials.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-6 max-w-4xl border border-slate-800 bg-slate-950/70 p-5">
      <h2 className="text-sm font-black uppercase tracking-widest text-slate-300">Your credentials</h2>
      <p className="mt-2 text-sm text-slate-500">
        These values are encrypted in the backend database and used only for your account.
      </p>

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <Field label="Groq API Key" value={form.groq_api_key} onChange={(v) => update("groq_api_key", v)} placeholder={credentialStatus?.groq_api_key ? "Saved. Enter new value to replace." : "gsk_..."} />
        <Field label="Telegram Bot Token" value={form.telegram_bot_token} onChange={(v) => update("telegram_bot_token", v)} placeholder={credentialStatus?.telegram_bot_token ? "Saved. Enter new value to replace." : "Bot token"} />
        <Field label="Telegram Chat ID" value={form.telegram_chat_id} onChange={(v) => update("telegram_chat_id", v)} placeholder={credentialStatus?.telegram_chat_id ? "Saved. Enter new value to replace." : "Chat ID"} />
        <Field label="TPO Username" value={form.tpo_username} onChange={(v) => update("tpo_username", v)} placeholder={credentialStatus?.tpo_username ? "Saved. Enter new value to replace." : "Your portal username"} />
        <Field label="TPO Password" type="password" value={form.tpo_password} onChange={(v) => update("tpo_password", v)} placeholder={credentialStatus?.tpo_password ? "Saved. Enter new value to replace." : "Your portal password"} />
        <Field label="TPO Login URL" value={form.tpo_login_url} onChange={(v) => update("tpo_login_url", v)} />
        <Field label="TPO Home URL" value={form.tpo_home_url} onChange={(v) => update("tpo_home_url", v)} />
        <Field label="TPO Drives URL" value={form.tpo_drives_url} onChange={(v) => update("tpo_drives_url", v)} />
      </div>

      <div className="mt-5 flex items-center gap-3">
        <button disabled={saving} className="border border-cyan-400 bg-cyan-500/10 px-4 py-2 text-sm font-bold text-cyan-100 disabled:opacity-50">
          {saving ? "Saving..." : "Save Credentials"}
        </button>
        {saved && <span className="text-sm text-emerald-300">Saved</span>}
      </div>

      {error && (
        <div className="mt-4 border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">
          {error}
        </div>
      )}
    </form>
  );
}

function Field({ label, value, onChange, placeholder = "", type = "text" }) {
  return (
    <label className="block">
      <span className="text-xs font-bold uppercase tracking-widest text-slate-500">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="mt-2 w-full border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400"
      />
    </label>
  );
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem("auth_token") || "");
  const [user, setUser] = useState(null);
  const [authNotice, setAuthNotice] = useState("");
  const [credentialStatus, setCredentialStatus] = useState(null);
  const [view, setView] = useState("watch");
  const [deadlines, setDeadlines] = useState([]);
  const [changes, setChanges] = useState([]);
  const [placements, setPlacements] = useState([]);
  const [placementChanges, setPlacementChanges] = useState([]);
  const [placementStatus, setPlacementStatus] = useState(null);
  const [health, setHealth] = useState(null);
  const [selectedDriveId, setSelectedDriveId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [assistantMessages, setAssistantMessages] = useState([
    { role: "assistant", content: "Ask me about drives, deadlines, or recent changes." },
  ]);
  const [question, setQuestion] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  function authHeaders() {
    return { Authorization: `Bearer ${token}` };
  }

  function handleAuth(data) {
    localStorage.setItem("auth_token", data.token);
    setToken(data.token);
    setUser(data.user);
    setAuthNotice("");
    setView("settings");
  }

  function logout(message = "") {
    localStorage.removeItem("auth_token");
    setToken("");
    setUser(null);
    setCredentialStatus(null);
    setAuthNotice(message);
  }

  async function fetchAll() {
    setLoading(true);
    try {
      const healthRes = await axios.get(`${API}/health`);
      setHealth(healthRes.data);

      const [deadlinesRes, changesRes] = await Promise.allSettled([
        axios.get(`${API}/deadlines`),
        axios.get(`${API}/changes`),
      ]);
      setDeadlines(deadlinesRes.status === "fulfilled" ? deadlinesRes.value.data.deadlines || [] : []);
      setChanges(changesRes.status === "fulfilled" ? changesRes.value.data.changes || [] : []);

      if (token) {
        const [meRes, placementsRes, placementChangesRes, schedulerRes] = await Promise.all([
          axios.get(`${API}/auth/me`, { headers: authHeaders() }),
          axios.get(`${API}/placements`, { headers: authHeaders() }),
          axios.get(`${API}/placements/changes`, { headers: authHeaders() }),
          axios.get(`${API}/placements/scheduler/status`, { headers: authHeaders() }),
        ]);
        setUser(meRes.data.user);
        setCredentialStatus(meRes.data.credentials);
        setPlacements(placementsRes.data.placements || []);
        setPlacementChanges(placementChangesRes.data.changes || []);
        setPlacementStatus((current) => ({
          ...(current || {}),
          ...(schedulerRes.data || {}),
        }));

        const firstDrive = placementsRes.data.placements?.[0];
        if (!selectedDriveId && firstDrive) setSelectedDriveId(firstDrive.id);
      }
    } catch (error) {
      console.error("Fetch error:", error);
      if (error.response?.status === 401) {
        logout("Your session expired or became invalid after deployment. Please sign in again.");
      }
    }
    setLoading(false);
  }

  async function syncPlacements(sendNotifications = false) {
    setSyncing(true);
    try {
      const res = await axios.post(
        `${API}/placements/sync?send_notifications=${sendNotifications}`,
        {},
        { headers: authHeaders() },
      );
      setPlacementStatus((current) => ({
        ...(current || {}),
        last_result: res.data,
        last_error: res.data?.status === "failed" ? res.data.error || "Placement sync failed." : "",
        last_run_at: new Date().toISOString(),
      }));
      await fetchAll();
    } catch (error) {
      console.error("Placement sync failed:", error);
      const detail = error.response?.data?.detail || error.response?.data?.error;
      if (error.response?.status === 401) {
        logout("Your session expired before running placement sync. Please sign in again.");
        setSyncing(false);
        return;
      }
      setPlacementStatus((current) => ({
        ...(current || {}),
        last_error: detail || "Placement sync failed. Check API logs.",
      }));
    }
    setSyncing(false);
  }

  async function toggleScheduler() {
    if (placementStatus?.running) {
      const res = await axios.post(`${API}/placements/scheduler/stop`, {}, { headers: authHeaders() });
      setPlacementStatus(res.data);
    } else {
      const res = await axios.post(`${API}/placements/scheduler/start?interval_minutes=30&send_notifications=true`, {}, { headers: authHeaders() });
      setPlacementStatus(res.data);
    }
  }

  async function saveCredentials(form) {
    try {
      const res = await axios.put(`${API}/settings/credentials`, form, {
        headers: authHeaders(),
      });
      setCredentialStatus(res.data.credentials);
    } catch (error) {
      if (error.response?.status === 401) {
        logout("Your session expired while saving credentials. Please sign in again.");
        return;
      }
      throw error;
    }
  }

  async function sendQuestion() {
    if (!question.trim() || chatLoading) return;
    const q = question.trim();
    setQuestion("");
    setAssistantMessages((items) => [...items, { role: "user", content: q }]);
    setChatLoading(true);
    try {
      const res = await axios.post(`${API}/chat?question=${encodeURIComponent(q)}`);
      setAssistantMessages((items) => [...items, { role: "assistant", content: res.data.answer }]);
    } catch {
      setAssistantMessages((items) => [...items, { role: "assistant", content: "I could not reach the assistant API." }]);
    }
    setChatLoading(false);
  }

  useEffect(() => {
    // Initial API hydration for the app shell.
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [assistantMessages, chatLoading]);

  const sortedPlacements = useMemo(() => {
    return [...placements].sort((a, b) => {
      const da = daysUntil(a.deadline_date);
      const db = daysUntil(b.deadline_date);
      return (da ?? 9999) - (db ?? 9999);
    });
  }, [placements]);

  const selectedDrive = sortedPlacements.find((item) => item.id === selectedDriveId) || sortedPlacements[0];
  const urgentDrives = sortedPlacements.filter((item) => {
    const days = daysUntil(item.deadline_date);
    return days !== null && days >= 0 && days <= 2;
  });
  const lastResult = placementStatus?.last_result;

  const nav = [
    ["watch", "Placement Watch"],
    ["deadlines", "Deadline Monitor"],
    ["assistant", "Assistant"],
    ["activity", "Activity"],
    ["settings", "Settings"],
  ];

  if (!token) {
    return <AuthScreen onAuth={handleAuth} sessionMessage={authNotice} />;
  }

  return (
    <div className="min-h-screen bg-[#090d12] text-slate-200">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col lg:flex-row">
        <aside className="border-b border-slate-800 bg-[#0d131b] p-5 lg:w-72 lg:border-b-0 lg:border-r">
          <div className="text-lg font-black tracking-tight text-white">Placement Watcher</div>
          <div className="mt-1 text-xs text-slate-500">{user?.email || "Signed in"}</div>
          <p className="mt-2 text-sm leading-relaxed text-slate-500">
            VIERP drives, JD summaries, and Telegram alerts in one place.
          </p>

          <div className="mt-6 space-y-2">
            {nav.map(([id, label]) => (
              <button
                key={id}
                onClick={() => setView(id)}
                className={`w-full border px-4 py-3 text-left text-sm font-bold transition ${
                  view === id
                    ? "border-cyan-400 bg-cyan-500/10 text-cyan-100"
                    : "border-transparent text-slate-400 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="mt-8 space-y-3 border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-500">Telegram</span>
              <StatusPill tone={credentialStatus?.telegram_bot_token && credentialStatus?.telegram_chat_id ? "emerald" : "amber"}>
                {credentialStatus?.telegram_bot_token && credentialStatus?.telegram_chat_id ? "Ready" : "Missing"}
              </StatusPill>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-500">Scheduler</span>
              <StatusPill tone={placementStatus?.running ? "emerald" : "slate"}>
                {placementStatus?.running ? "Running" : "Stopped"}
              </StatusPill>
            </div>
            <div className="text-xs text-slate-600">
              Last checked: {placementStatus?.last_run_at ? new Date(placementStatus.last_run_at).toLocaleString("en-IN") : "Not yet"}
            </div>
            <button onClick={logout} className="w-full border border-slate-700 px-3 py-2 text-xs font-bold text-slate-400 hover:text-slate-100">
              Sign out
            </button>
          </div>
        </aside>

        <main className="flex-1 p-5 lg:p-8">
          <header className="flex flex-col gap-4 border-b border-slate-800 pb-6 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-xs font-bold uppercase tracking-[0.24em] text-cyan-300">Student alert center</div>
              <h1 className="mt-2 text-3xl font-black text-white">Never miss a placement drive</h1>
              <p className="mt-2 text-sm text-slate-500">
                Sync VIERP, read JD documents, and send Telegram alerts when new companies appear.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => syncPlacements(false)}
                disabled={syncing}
                className="border border-slate-600 px-4 py-2 text-sm font-bold text-slate-200 hover:border-cyan-400 hover:text-cyan-200 disabled:opacity-50"
              >
                {syncing ? "Checking..." : "Check Now"}
              </button>
              <button
                onClick={() => syncPlacements(true)}
                disabled={syncing}
                className="border border-emerald-400 bg-emerald-500/10 px-4 py-2 text-sm font-bold text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
              >
                Check + Notify
              </button>
              <button
                onClick={toggleScheduler}
                className="border border-violet-400/60 px-4 py-2 text-sm font-bold text-violet-200 hover:bg-violet-500/10"
              >
                {placementStatus?.running ? "Stop Auto Check" : "Start Auto Check"}
              </button>
            </div>
          </header>

          {view === "watch" && (
            <div className="mt-6 space-y-6">
              <div className="grid gap-3 md:grid-cols-4">
                <Metric label="Open Drives" value={sortedPlacements.length} tone="emerald" />
                <Metric label="Needs Attention" value={urgentDrives.length} tone={urgentDrives.length ? "red" : "slate"} />
                <Metric label="Last Seen" value={lastResult?.total_seen ?? 0} tone="cyan" />
                <Metric label="Changed" value={placementChanges.length} tone="amber" />
              </div>

              {lastResult?.status === "success" && lastResult.total_seen === 0 && (
                <div className="border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-400">
                  VIERP currently reports no scheduled companies. The watcher is still working and will notify when a drive appears.
                </div>
              )}

              {lastResult?.status === "success" && lastResult.total_seen > 0 && (
                <div className="border border-emerald-400/30 bg-emerald-500/10 p-4 text-sm text-emerald-100">
                  Sync completed. Seen: {lastResult.total_seen}, New: {lastResult.new_drives}, Changed: {lastResult.changed_drives}.
                </div>
              )}

              {lastResult?.status === "failed" && (
                <div className="border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-200">
                  {lastResult.error || "Placement sync failed."}
                </div>
              )}

              {placementStatus?.last_error && (
                <div className="border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-200">
                  {placementStatus.last_error}
                </div>
              )}

              <div className="grid gap-5 lg:grid-cols-[420px_1fr]">
                <section className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-black uppercase tracking-widest text-slate-300">Company Inbox</h2>
                    <button onClick={fetchAll} className="text-xs font-bold text-cyan-300 hover:text-cyan-100">
                      {loading ? "Refreshing" : "Refresh"}
                    </button>
                  </div>

                  {sortedPlacements.length === 0 ? (
                    <div className="border border-slate-800 bg-slate-950/70 p-6">
                      <div className="text-sm font-bold text-slate-100">No saved drives yet</div>
                      <p className="mt-2 text-sm leading-relaxed text-slate-500">
                        This is normal when VIERP shows no scheduled company. Keep auto-check on after deployment to get Telegram alerts.
                      </p>
                    </div>
                  ) : (
                    sortedPlacements.map((drive) => (
                      <DriveListItem
                        key={drive.id}
                        drive={drive}
                        active={selectedDrive?.id === drive.id}
                        onSelect={(item) => setSelectedDriveId(item.id)}
                      />
                    ))
                  )}
                </section>

                <DriveDetail drive={selectedDrive} />
              </div>
            </div>
          )}

          {view === "deadlines" && (
            <div className="mt-6 grid gap-5 lg:grid-cols-2">
              <section>
                <h2 className="mb-3 text-sm font-black uppercase tracking-widest text-slate-300">Email & Message Deadlines</h2>
                <div className="space-y-3">
                  {deadlines.length === 0 ? (
                    <div className="border border-slate-800 bg-slate-950/70 p-6 text-sm text-slate-500">No extracted deadlines yet.</div>
                  ) : (
                    deadlines.map((deadline) => <DeadlineItem key={deadline.id} deadline={deadline} />)
                  )}
                </div>
              </section>

              <section>
                <h2 className="mb-3 text-sm font-black uppercase tracking-widest text-slate-300">Deadline Changes</h2>
                <div className="space-y-3">
                  {changes.length === 0 ? (
                    <div className="border border-slate-800 bg-slate-950/70 p-6 text-sm text-slate-500">No deadline changes detected yet.</div>
                  ) : (
                    changes.map((change) => (
                      <div key={change.id} className="border border-amber-400/20 bg-amber-500/5 p-4 text-sm">
                        <div className="font-bold text-slate-100">{change.event_name}</div>
                        <div className="mt-1 text-xs text-slate-400">
                          {change.field_changed?.replace("_", " ")}: {change.old_value || "blank"} to {change.new_value || "blank"}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </section>
            </div>
          )}

          {view === "assistant" && (
            <div className="mt-6 max-w-3xl">
              <section className="border border-slate-800 bg-slate-950/70">
                <div className="border-b border-slate-800 p-5">
                  <h2 className="text-sm font-black uppercase tracking-widest text-slate-300">Ask the assistant</h2>
                  <p className="mt-2 text-sm text-slate-500">Use this for questions about deadlines, changes, and saved placement drives.</p>
                </div>
                <div className="h-96 space-y-3 overflow-y-auto p-5">
                  {assistantMessages.map((msg, index) => <Bubble key={index} msg={msg} />)}
                  {chatLoading && <Bubble msg={{ role: "assistant", content: "Thinking..." }} />}
                  <div ref={chatEndRef} />
                </div>
                <div className="flex gap-3 border-t border-slate-800 p-4">
                  <input
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => event.key === "Enter" && sendQuestion()}
                    className="min-w-0 flex-1 border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400"
                    placeholder="Which companies are closing soon?"
                  />
                  <button
                    onClick={sendQuestion}
                    disabled={!question.trim() || chatLoading}
                    className="border border-cyan-400 px-5 py-3 text-sm font-bold text-cyan-200 disabled:opacity-50"
                  >
                    Send
                  </button>
                </div>
              </section>
            </div>
          )}

          {view === "activity" && (
            <div className="mt-6 grid gap-5 lg:grid-cols-2">
              <section>
                <h2 className="mb-3 text-sm font-black uppercase tracking-widest text-slate-300">Placement Changes</h2>
                <div className="space-y-3">
                  {placementChanges.length === 0 ? (
                    <div className="border border-slate-800 bg-slate-950/70 p-6 text-sm text-slate-500">No placement changes yet.</div>
                  ) : (
                    placementChanges.map((change) => (
                      <div key={change.id} className="border border-amber-400/20 bg-amber-500/5 p-4 text-sm">
                        <div className="font-bold text-slate-100">{change.company_name}</div>
                        <div className="mt-1 text-xs text-slate-400">
                          {change.field_changed?.replace("_", " ")}: {change.old_value || "blank"} to {change.new_value || "blank"}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </section>

              <section className="border border-slate-800 bg-slate-950/70 p-5">
                <h2 className="text-sm font-black uppercase tracking-widest text-slate-300">System Status</h2>
                <div className="mt-5 space-y-4 text-sm">
                  <div className="flex justify-between border-b border-slate-800 pb-3">
                    <span className="text-slate-500">API</span>
                    <span className="text-emerald-300">{health?.status || "Unknown"}</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800 pb-3">
                    <span className="text-slate-500">Groq</span>
                    <span className={health?.groq_key_loaded ? "text-emerald-300" : "text-amber-300"}>{health?.groq_key_loaded ? "Configured" : "Missing"}</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800 pb-3">
                    <span className="text-slate-500">Telegram</span>
                    <span className={credentialStatus?.telegram_bot_token && credentialStatus?.telegram_chat_id ? "text-emerald-300" : "text-amber-300"}>{credentialStatus?.telegram_bot_token && credentialStatus?.telegram_chat_id ? "Configured" : "Missing"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Auto check</span>
                    <span className={placementStatus?.running ? "text-emerald-300" : "text-slate-400"}>{placementStatus?.running ? "Running" : "Stopped"}</span>
                  </div>
                </div>
              </section>
            </div>
          )}

          {view === "settings" && (
            <div>
              <SettingsPanel
                credentialStatus={credentialStatus}
                onSave={saveCredentials}
              />

              <section className="mt-5 max-w-4xl border border-slate-800 bg-slate-950/70 p-5">
                <h2 className="text-sm font-black uppercase tracking-widest text-slate-300">Setup checklist</h2>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {[
                    ["Groq API key", credentialStatus?.groq_api_key],
                    ["Telegram bot token", credentialStatus?.telegram_bot_token],
                    ["Telegram chat ID", credentialStatus?.telegram_chat_id],
                    ["TPO username", credentialStatus?.tpo_username],
                    ["TPO password", credentialStatus?.tpo_password],
                    ["TPO portal URL", credentialStatus?.tpo_drives_url],
                  ].map(([label, ready]) => (
                    <div key={label} className="flex items-center justify-between border border-slate-800 bg-slate-950 p-3 text-sm">
                      <span className="text-slate-400">{label}</span>
                      <StatusPill tone={ready ? "emerald" : "amber"}>{ready ? "Saved" : "Needed"}</StatusPill>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
