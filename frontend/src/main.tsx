import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUp,
  ArrowUpRight,
  AudioLines,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock3,
  Command,
  Compass,
  FileText,
  Github,
  Inbox,
  Layers3,
  ListTodo,
  Mail,
  MessageCircle,
  MoreHorizontal,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
  Zap,
  CalendarDays,
  Brain,
  Activity,
  Link2,
  LockKeyhole,
  PanelLeftClose,
} from "lucide-react";
import "./style.css";

type Row = Record<string, any>;
type Dashboard = {
  config: Row;
  conversations: Row[];
  tasks: Row[];
  memories: Row[];
  approvals: Row[];
  events: Row[];
  runs: Row[];
  outbox: Row[];
  jobs: Row[];
};
type Message = { id?: string; role: string; content: string };
const starter = [
  {
    icon: Compass,
    title: "Find my focus",
    hint: "A brief from your priorities & workspace",
    prompt: "Brief me on my priorities",
  },
  {
    icon: Mail,
    title: "Close the loop",
    hint: "Prepare a revenue update for leadership",
    prompt:
      "Find revenue emails and post a summary to the leadership Slack channel",
  },
  {
    icon: ListTodo,
    title: "Make a plan",
    hint: "Capture the next thing that matters",
    prompt: "Add task Prepare the launch decision memo",
  },
];
const nav = [
  { id: "desk", label: "My desk", icon: Compass },
  { id: "tasks", label: "Tasks", icon: ListTodo },
  { id: "approvals", label: "Approvals", icon: ShieldCheck },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "connectors", label: "Connectors", icon: Layers3 },
];
function App() {
  const [data, setData] = useState<Dashboard | null>(null),
    [view, setView] = useState("desk"),
    [cid, setCid] = useState<string | null>(null),
    [messages, setMessages] = useState<Message[]>([]),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [modal, setModal] = useState<string | null>(null),
    [guide, setGuide] = useState(""),
    [token, setToken] = useState(sessionStorage.getItem("cos-token") || ""),
    [filter, setFilter] = useState(""),
    [sidebar, setSidebar] = useState(false),
    [jobId, setJobId] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null),
    composer = useRef<HTMLTextAreaElement>(null);
  async function api(path: string, options: RequestInit = {}) {
    const res = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: "Bearer " + token } : {}),
        ...options.headers,
      },
    });
    const json = await res.json();
    if (!res.ok)
      throw new Error(
        typeof json.detail === "string"
          ? json.detail
          : "The request could not be completed",
      );
    return json;
  }
  async function refresh() {
    try {
      setData(await api("/api/dashboard"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [token]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);
  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    async function poll() {
      try {
        const job = await api("/api/jobs/" + jobId);
        if (stopped) return;
        if (["completed", "failed", "interrupted"].includes(job.status)) {
          setMessages(
            job.result?.messages || [
              ...messages,
              {
                role: "assistant",
                content:
                  job.result?.error ||
                  "This run was interrupted. Check Activity before trying again.",
              },
            ],
          );
          setBusy(false);
          setJobId(null);
          refresh();
          return;
        }
        setTimeout(poll, 1000);
      } catch (e) {
        if (!stopped) {
          setError((e as Error).message);
          setTimeout(poll, 3000);
        }
      }
    }
    poll();
    return () => {
      stopped = true;
    };
  }, [jobId]);
  async function submit(text = input) {
    if (!text.trim() || busy) return;
    setError("");
    setView("desk");
    setBusy(true);
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text.trim() }]);
    try {
      const accepted = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ content: text.trim(), conversation_id: cid }),
      });
      setCid(accepted.conversation_id);
      setJobId(accepted.job_id);
      refresh();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
      setInput(text);
    }
  }
  async function openConversation(id: string) {
    if (busy) return;
    try {
      const r = await api("/api/conversations/" + id);
      setCid(id);
      setMessages(r.messages);
      setView("desk");
      setSidebar(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function mutate(path: string, method = "POST", body?: Row) {
    try {
      setError("");
      await api(path, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function showGuide() {
    setModal("imessage");
    try {
      const r = await api("/api/setup/imessage");
      setGuide(r.content);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const pending = data?.approvals.filter((a) => a.status === "pending") || [],
    tasks = data?.tasks.filter((t) => t.status === "open") || [];
  const recent =
    data?.conversations.filter((c) =>
      c.title.toLowerCase().includes(filter.toLowerCase()),
    ) || [];
  const mode = data?.config.mode || "demo";
  const im = data?.config.imessage || {};
  const title =
    view === "desk" ? "My desk" : nav.find((n) => n.id === view)?.label;
  const fmt = (date: string) =>
    new Date(date).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
  return (
    <div className="app-shell">
      <aside className={"sidebar " + (sidebar ? "open" : "")}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView("desk");
          }}
        >
          <span className="brand-mark">
            <Command size={22} />
          </span>
          <span>
            Chief Of Staff<small>PERSONAL OPERATING SYSTEM</small>
          </span>
        </a>
        <button
          className="new-chat"
          onClick={() => {
            if (!busy) {
              setCid(null);
              setMessages([]);
              setView("desk");
              setSidebar(false);
              composer.current?.focus();
            }
          }}
        >
          <Plus size={17} />
          New conversation<span>↗</span>
        </button>
        <div className="section-label">WORKSPACE</div>
        <nav>
          {nav.map((n) => (
            <button
              key={n.id}
              className={view === n.id ? "nav-item active" : "nav-item"}
              onClick={() => {
                setView(n.id);
                setSidebar(false);
              }}
            >
              <n.icon size={18} />
              {n.label}
              {n.id === "approvals" && pending.length > 0 ? (
                <b>{pending.length}</b>
              ) : n.id === "desk" ? (
                <span className="nav-dot" />
              ) : null}
            </button>
          ))}
        </nav>
        <div className="recent-head section-label">
          CONVERSATIONS{" "}
          <button
            aria-label="Search conversations"
            onClick={() => setModal("search")}
          >
            <Search size={14} />
          </button>
        </div>
        <div className="recent-list">
          {recent.slice(0, 7).map((c) => (
            <button
              key={c.id}
              className={c.id === cid ? "selected" : ""}
              onClick={() => openConversation(c.id)}
            >
              <MessageCircle size={14} />
              <span>{c.title}</span>
            </button>
          ))}
          {!recent.length && (
            <span className="empty-recent">
              A little less noise.
              <br />A little more clarity.
            </span>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="local-badge">
            <span className="status-dot" />
            Running locally <LockKeyhole size={12} />
          </div>
          <button className="profile" onClick={() => setModal("settings")}>
            <span className="avatar">Y</span>
            <span>
              Your workspace
              <small>{mode === "demo" ? "Demo mode" : "OpenAI mode"}</small>
            </span>
            <Settings2 size={16} />
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <div className="breadcrumb">
            <button
              className="mobile-toggle"
              aria-label="Open navigation"
              onClick={() => setSidebar(!sidebar)}
            >
              <PanelLeftClose size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={12} />
            <strong>{title}</strong>
          </div>
          <div className="header-right">
            <span className="mode-pill">
              <span />
              {mode === "demo" ? "DEMO WORKSPACE" : "MODEL CONNECTED"}
            </span>
            <button
              className="icon-button"
              aria-label="Connection settings"
              onClick={() => setModal("settings")}
            >
              <Settings2 size={17} />
            </button>
          </div>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {view === "desk" ? (
          <main className="desk">
            <div className="main-column">
              <div className="eyebrow">
                <span className="little-line" />
                YOUR DAY, CONSIDERED.
              </div>
              <div className="welcome-heading">
                <h1>
                  A clear head.
                  <br />
                  <em>A capable right hand.</em>
                </h1>
                <span className="sun-orbit">
                  <Sparkles size={26} />
                </span>
              </div>
              <p className="intro">
                From scattered context to your next best move.
                <br />
                Think out loud. I’ll help connect the dots.
              </p>
              <div className="chat-area">
                {messages.length === 0 ? (
                  <>
                    <div className="ready">
                      <span className="ready-mark">
                        <AudioLines size={19} />
                      </span>
                      <span>What should we make room for today?</span>
                      <small>
                        Start with a thought, or choose a direction.
                      </small>
                    </div>
                    <div className="starter-grid">
                      {starter.map((s) => (
                        <button
                          key={s.title}
                          onClick={() => submit(s.prompt)}
                          disabled={busy}
                        >
                          <s.icon size={19} />
                          <h3>
                            {s.title}
                            <ArrowUpRight size={15} />
                          </h3>
                          <p>{s.hint}</p>
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="messages">
                    {messages.map((m, i) => (
                      <div key={m.id || i} className={"message " + m.role}>
                        <div className="message-label">
                          {m.role === "user" ? (
                            <span className="avatar tiny">Y</span>
                          ) : (
                            <span className="bot-avatar">
                              <Command size={14} />
                            </span>
                          )}
                          {m.role === "user" ? "You" : "Chief Of Staff"}
                        </div>
                        <div className="message-content">{m.content}</div>
                      </div>
                    ))}
                  </div>
                )}
                {busy && (
                  <div className="thinking" role="status">
                    <span />
                    <span />
                    <span />
                    Connecting the dots{" "}
                    <small>Follow the run in Activity</small>
                  </div>
                )}
                <div ref={bottom} />
              </div>
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
              >
                <textarea
                  ref={composer}
                  aria-label="Message Chief Of Staff"
                  placeholder="What’s on your mind?"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  disabled={busy}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      submit();
                    }
                  }}
                />
                <div className="composer-bottom">
                  <span>
                    <ShieldCheck size={14} />
                    You’re in control. Actions need your approval.
                  </span>
                  <button
                    type="submit"
                    aria-label="Send message"
                    disabled={busy || !input.trim()}
                  >
                    <ArrowUp size={18} />
                  </button>
                </div>
              </form>
              <div className="composer-note">
                {mode === "demo"
                  ? "Demo services use sample data. Tasks and memory are saved locally."
                  : "OpenAI processes your prompts and tool context. Service connectors currently use sample data."}
                <span>Enter to send · Shift + Enter for a new line</span>
              </div>
            </div>
            <aside className="context-column">
              <div className="date-line">
                {new Date().toLocaleDateString("en-US", {
                  weekday: "long",
                  month: "short",
                  day: "numeric",
                })}
                <span>YOUR CONTEXT</span>
              </div>
              <section className="focus-card">
                <div className="card-top">
                  <span className="card-kicker">
                    <Compass size={15} />
                    TODAY’S FOCUS
                  </span>
                  <span className="small-circle">
                    <MoreHorizontal size={16} />
                  </span>
                </div>
                <h2>
                  Less busy.
                  <br />
                  More intentional.
                </h2>
                <p>A few things worth moving forward.</p>
                <div className="focus-tasks">
                  {tasks.slice(0, 3).map((t) => (
                    <button
                      key={t.id}
                      onClick={() => mutate("/api/tasks/" + t.id, "PATCH")}
                    >
                      <Circle size={16} />
                      <span>{t.title}</span>
                      {t.priority === "high" && (
                        <span className="priority-dot" />
                      )}
                    </button>
                  ))}
                  {!tasks.length && (
                    <span>You have room for a new priority.</span>
                  )}
                </div>
                <button className="text-link" onClick={() => setView("tasks")}>
                  View all tasks
                  <ArrowUpRight size={14} />
                </button>
              </section>
              <section className="review-card">
                <div className="card-kicker">
                  <ShieldCheck size={15} />
                  THE FINAL SAY
                </div>
                <div className="review-count">
                  {pending.length}
                  <span>
                    {pending.length === 1 ? "action" : "actions"} waiting
                    <br />
                    for your approval
                  </span>
                </div>
                <button
                  className="outline-button"
                  onClick={() => setView("approvals")}
                >
                  Review proposals
                  <ArrowUpRight size={14} />
                </button>
              </section>
              <section className="connected-card">
                <div className="card-kicker">WITH YOU, WHERE YOU ARE</div>
                <div className="imessage-line">
                  <span className="imessage-icon">
                    <MessageCircle size={22} />
                  </span>
                  <span>
                    iMessage
                    <small>
                      {im.connected
                        ? "Bridge connected"
                        : "Your chief of staff, in Messages"}
                    </small>
                  </span>
                </div>
                <button className="text-link" onClick={showGuide}>
                  {im.connected ? "View bridge setup" : "Set up iMessage"}
                  <ArrowUpRight size={14} />
                </button>
              </section>
              <div className="quiet-note">
                <LockKeyhole size={14} />
                <span>
                  Your context stays on this machine
                  <br />
                  until you choose a model or action.
                </span>
              </div>
            </aside>
          </main>
        ) : (
          <main className="page-content">
            <div className="eyebrow">YOUR PERSONAL OPERATING SYSTEM</div>
            <h1>
              {title}
              <em className="page-subtitle">
                {
                  (
                    {
                      tasks: "Make room for what matters.",
                      approvals: "Every action, on your terms.",
                      memory: "The details worth keeping.",
                      activity: "A clear record of the work.",
                      connectors: "Context, connected.",
                    } as Row
                  )[view]
                }
              </em>
            </h1>
            {view === "tasks" && (
              <>
                <div className="page-toolbar">
                  <span>{tasks.length} open priorities</span>
                  <button
                    className="primary-button"
                    onClick={() => {
                      setView("desk");
                      setInput("Add task ");
                      setTimeout(() => composer.current?.focus(), 100);
                    }}
                  >
                    <Plus size={15} />
                    Add a task
                  </button>
                </div>
                <div className="list-panel">
                  {data?.tasks.map((t) => (
                    <button
                      className={
                        "task-row " + (t.status === "done" ? "done" : "")
                      }
                      key={t.id}
                      onClick={() => mutate("/api/tasks/" + t.id, "PATCH")}
                    >
                      {t.status === "done" ? (
                        <CheckCircle2 size={20} />
                      ) : (
                        <Circle size={20} />
                      )}
                      <span>
                        {t.title}
                        <small>{t.due || "No deadline set"}</small>
                      </span>
                      <b className={"tag " + t.priority}>{t.priority}</b>
                    </button>
                  ))}
                  {!data?.tasks.length && (
                    <Empty
                      icon={ListTodo}
                      text="Start with one meaningful task."
                    />
                  )}
                </div>
              </>
            )}
            {view === "approvals" && (
              <>
                <p className="page-description">
                  Review the exact tool and arguments before anything is sent,
                  posted, or changed in an external workspace. Simulated service
                  actions affect sample data.
                </p>
                <div className="proposal-list">
                  {data?.approvals.map((a) => (
                    <section className="proposal" key={a.id}>
                      <div className="proposal-heading">
                        <span className="proposal-icon">
                          <ShieldCheck size={20} />
                        </span>
                        <div>
                          <h3>
                            {a.name === "imessage_draft"
                              ? "Send an iMessage"
                              : a.name.replaceAll("_", " ")}
                          </h3>
                          <small>
                            {a.name === "imessage_draft"
                              ? "Native Messages · real outgoing text"
                              : "Simulated workspace · sample data"}
                          </small>
                        </div>
                        <span className={"tag " + a.status}>
                          {a.status.replaceAll("_", " ")}
                        </span>
                      </div>
                      <pre>{JSON.stringify(a.arguments, null, 2)}</pre>
                      {a.error && <p className="inline-error">{a.error}</p>}
                      {a.status === "pending" && (
                        <div className="proposal-actions">
                          <button
                            className="outline-button"
                            onClick={() =>
                              mutate("/api/approvals/" + a.id, "POST", {
                                approve: false,
                              })
                            }
                          >
                            Reject
                          </button>
                          <button
                            className="primary-button"
                            onClick={() =>
                              mutate("/api/approvals/" + a.id, "POST", {
                                approve: true,
                              })
                            }
                          >
                            <Check size={16} />
                            Approve action
                          </button>
                        </div>
                      )}
                    </section>
                  ))}
                  {!data?.approvals.length && (
                    <Empty
                      icon={ShieldCheck}
                      text="Nothing needs your approval yet."
                    />
                  )}
                </div>
                {!!data?.outbox.length && (
                  <>
                    <h2 className="subhead">iMessage outbox</h2>
                    {data.outbox.map((o) => (
                      <div className="outbox-row" key={o.id}>
                        <MessageCircle size={17} />
                        <span>
                          {o.recipient}
                          <small>{o.content}</small>
                        </span>
                        <b className="tag">{o.status}</b>
                      </div>
                    ))}
                  </>
                )}
              </>
            )}
            {view === "memory" && (
              <>
                <p className="page-description">
                  Only preferences you explicitly ask to remember are stored
                  here. You can remove them at any time.
                </p>
                <div className="memory-grid">
                  {data?.memories.map((m) => (
                    <article key={m.id}>
                      <Brain size={21} />
                      <p>{m.content}</p>
                      <div>
                        <small>
                          Saved {new Date(m.created_at).toLocaleDateString()}
                        </small>
                        <button
                          className="icon-button"
                          aria-label="Forget memory"
                          onClick={() =>
                            mutate("/api/memories/" + m.id, "DELETE")
                          }
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
                <button
                  className="outline-button"
                  onClick={() => {
                    setView("desk");
                    setInput("Remember ");
                    setTimeout(() => composer.current?.focus(), 100);
                  }}
                >
                  <Plus size={15} />
                  Save a preference
                </button>
              </>
            )}
            {view === "activity" && (
              <>
                <p className="page-description">
                  Inspect routing decisions, tool inputs, actual results,
                  errors, and run limits. This is the execution trail, not
                  hidden model reasoning.
                </p>
                <div className="activity-layout">
                  <div className="runs">
                    {data?.runs.map((r) => (
                      <details className="run" key={r.id}>
                        <summary>
                          <span className={"run-dot " + r.status} />
                          <span>
                            {data.conversations.find(
                              (c) => c.id === r.conversation_id,
                            )?.title || "Conversation"}
                            <small>
                              {fmt(r.started_at)} · {r.mode} ·{" "}
                              {r.trace.duration_ms ?? 0} ms
                            </small>
                          </span>
                          <b className="tag">{r.status.replaceAll("_", " ")}</b>
                        </summary>
                        <pre>{JSON.stringify(r.trace, null, 2)}</pre>
                        {r.error && <p className="inline-error">{r.error}</p>}
                        {data.events
                          .filter((e) => e.run_id === r.id)
                          .reverse()
                          .map((e) => (
                            <details className="event" key={e.id}>
                              <summary>
                                <Zap size={14} />
                                {e.name}
                                <span>
                                  {e.error ? "Failed" : "Recorded"} ·{" "}
                                  {e.duration_ms} ms
                                </span>
                              </summary>
                              <pre>
                                {JSON.stringify(
                                  {
                                    arguments: e.arguments,
                                    result: e.result,
                                    error: e.error,
                                  },
                                  null,
                                  2,
                                )}
                              </pre>
                            </details>
                          ))}
                      </details>
                    ))}
                    {!data?.runs.length && (
                      <Empty
                        icon={Activity}
                        text="Your next conversation starts the trail."
                      />
                    )}
                  </div>
                </div>
              </>
            )}
            {view === "connectors" && (
              <>
                <p className="page-description">
                  Seven simulated services make the walkthrough reproducible.
                  Enable the native iMessage bridge or configure live MCP
                  servers to connect your own workspace.
                </p>
                <div className="connector-grid">
                  <article className="connector featured">
                    <span className="imessage-icon">
                      <MessageCircle size={26} />
                    </span>
                    <span className={"tag " + (im.connected ? "approved" : "")}>
                      {im.connected
                        ? "Connected"
                        : im.enabled
                          ? "Enabled · bridge offline"
                          : "Not connected"}
                    </span>
                    <h2>iMessage</h2>
                    <p>
                      Send a /cos command from an allowlisted contact. Review
                      and approve the reply on your desk.
                    </p>
                    <button className="primary-button" onClick={showGuide}>
                      {im.connected ? "View setup" : "Connect iMessage"}
                      <ArrowUpRight size={15} />
                    </button>
                    <small>macOS · explicit commands · approved replies</small>
                  </article>
                  {(data?.config.mcp_servers || []).map((s: Row) => (
                    <article className="connector" key={"mcp-" + s.name}>
                      <span className="service-icon">
                        <Link2 size={22} />
                      </span>
                      <span className="tag">{s.status}</span>
                      <h2>{s.name}</h2>
                      <p>
                        Live MCP connector · {s.tool_count} discovered tools.
                        Mutations require approval unless explicitly configured
                        as read-only.
                      </p>
                      <small>{s.error || "Streamable HTTP transport"}</small>
                    </article>
                  ))}
                  {data?.config.services.map((s: Row, i: number) => {
                    const Icon = [
                      Mail,
                      CalendarDays,
                      FileText,
                      MessageCircle,
                      ListTodo,
                      Github,
                      Search,
                    ][i];
                    return (
                      <article className="connector" key={s.name}>
                        <span className="service-icon">
                          <Icon size={22} />
                        </span>
                        <span className="tag">Simulated</span>
                        <h2>{s.name}</h2>
                        <p>
                          Sample workspace tools available to the orchestrator.
                          No live account is connected.
                        </p>
                        <small>Included in the 191-tool catalog</small>
                      </article>
                    );
                  })}
                </div>
              </>
            )}
          </main>
        )}
        <footer>
          <span>
            <Command size={12} />
            Chief Of Staff
          </span>
          <span>Designed for a little more headspace.</span>
          <span>
            LOCAL FIRST <span className="status-dot" />
          </span>
        </footer>
      </div>
      {modal && (
        <div className="modal-backdrop" onClick={() => setModal(null)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={
              modal === "imessage" ? "iMessage setup" : "Workspace settings"
            }
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              aria-label="Close dialog"
              onClick={() => setModal(null)}
            >
              <X size={20} />
            </button>
            {modal === "imessage" ? (
              <>
                <span className="imessage-icon">
                  <MessageCircle size={30} />
                </span>
                <h2>
                  Your chief of staff,
                  <br />
                  <em>one message away.</em>
                </h2>
                <p>
                  The bridge runs on your Mac. It reads new, allowlisted{" "}
                  <strong>/cos</strong> commands and sends replies only after
                  you approve them here.
                </p>
                <div className="setup-status">
                  <span className="status-dot" />{" "}
                  {im.connected
                    ? "Bridge connected"
                    : im.enabled
                      ? "Enabled; waiting for bridge"
                      : "Bridge is not enabled"}
                </div>
                <pre className="setup-guide">
                  {guide || "Loading setup guide…"}
                </pre>
              </>
            ) : modal === "search" ? (
              <>
                <h2>Find a conversation</h2>
                <input
                  className="settings-input"
                  aria-label="Search conversations"
                  autoFocus
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Search by title"
                />
                {recent.map((c) => (
                  <button
                    className="search-result"
                    key={c.id}
                    onClick={() => {
                      openConversation(c.id);
                      setModal(null);
                    }}
                  >
                    <MessageCircle size={16} />
                    {c.title}
                    <ArrowUpRight size={14} />
                  </button>
                ))}
              </>
            ) : (
              <>
                <span className="service-icon">
                  <Settings2 size={24} />
                </span>
                <h2>Your workspace</h2>
                <p>
                  Mode: <strong>{mode}</strong> · Model:{" "}
                  <strong>{data?.config.model || "Not loaded"}</strong>
                  <br />
                  Switch modes in .env and restart the server. In OpenAI mode,
                  prompts and tool context are sent to your configured provider.
                </p>
                <label>
                  Optional local API token
                  <input
                    className="settings-input"
                    type="password"
                    value={token}
                    onChange={(e) => {
                      setToken(e.target.value);
                      sessionStorage.setItem("cos-token", e.target.value);
                    }}
                    placeholder="Match COS_API_TOKEN from .env"
                  />
                </label>
                <p className="fine-print">
                  Stored for this browser session only. Never enter your OpenAI
                  API key here.
                </p>
                <div className="settings-facts">
                  <span>
                    <ShieldCheck size={16} />
                    External actions require review
                  </span>
                  <span>
                    <Inbox size={16} />
                    Conversations persist in SQLite
                  </span>
                  <span>
                    <Layers3 size={16} />
                    191 simulated tools · 7 local tools
                  </span>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
function Empty({ icon: Icon, text }: { icon: any; text: string }) {
  return (
    <div className="empty-state">
      <Icon size={32} />
      <p>{text}</p>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
