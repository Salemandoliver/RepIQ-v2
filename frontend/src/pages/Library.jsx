import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Avatar, ScoreChip, Skeleton, EmptyState, Modal } from "../components/ui.jsx";
import { hostName } from "../components/useTeamAvatars.js";
import { formatDuration, relativeDate, callTitle, isTeamsMeeting, ACTIVITY_TYPES } from "../utils";
import {
  HeartIcon,
  ShareIcon,
  CommentIcon,
  HeadphonesIcon,
  XIcon,
  BookmarkIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  PhoneIcon,
  VideoIcon,
  ClockIcon,
} from "../components/Icons.jsx";

const EMPTY_FILTERS = {
  team_id: "",
  host_id: "",
  customer: "",
  transcript: "",
  said_by: "",
  topic_id: "",
  activity_type: "",
  direction: "",
  min_minutes: "",
  max_minutes: "",
  min_score: "",
  max_score: "",
  period_days: "",
  date_from: "",
  date_to: "",
  period_label: "",
};

const PAGE_SIZE = 16;

const PERIOD_PRESETS = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "this_week", label: "This week" },
  { key: "last_7", label: "Last 7 days" },
  { key: "this_month", label: "This month" },
  { key: "last_30", label: "Last 30 days" },
  { key: "this_quarter", label: "This quarter" },
  { key: "last_90", label: "Last 90 days" },
  { key: "this_year", label: "This year" },
  { key: "all", label: "All time" },
];

function presetRange(key) {
  const now = new Date();
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const endOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);
  switch (key) {
    case "today":
      return [startOfDay(now), now];
    case "yesterday": {
      const y = new Date(now);
      y.setDate(y.getDate() - 1);
      return [startOfDay(y), endOfDay(y)];
    }
    case "this_week": {
      const d = startOfDay(now);
      d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); // Monday start
      return [d, now];
    }
    case "last_7": {
      const d = new Date(now);
      d.setDate(d.getDate() - 7);
      return [d, now];
    }
    case "this_month":
      return [new Date(now.getFullYear(), now.getMonth(), 1), now];
    case "last_30": {
      const d = new Date(now);
      d.setDate(d.getDate() - 30);
      return [d, now];
    }
    case "this_quarter":
      return [new Date(now.getFullYear(), Math.floor(now.getMonth() / 3) * 3, 1), now];
    case "last_90": {
      const d = new Date(now);
      d.setDate(d.getDate() - 90);
      return [d, now];
    }
    case "this_year":
      return [new Date(now.getFullYear(), 0, 1), now];
    default:
      return [null, null];
  }
}

function fmtDay(iso) {
  const [y, m, d] = String(iso).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

function buildQuery(filters, page, sort) {
  const p = new URLSearchParams();
  p.set("page", page);
  p.set("page_size", PAGE_SIZE);
  p.set("sort", sort);
  Object.entries(filters).forEach(([k, v]) => {
    if (k === "period_label") return; // display-only
    if (v !== "" && v != null) p.set(k, v);
  });
  return p.toString();
}

function PeriodFilter({ filters, onChange }) {
  const [open, setOpen] = useState(false);
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const ref = useRef(null);

  useEffect(() => {
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    if (open) document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const hasRange = Boolean(filters.date_from || filters.date_to);
  const label =
    filters.period_label ||
    (filters.period_days ? `Last ${filters.period_days} days` : hasRange ? "Custom range" : "All time");
  const selectedKey =
    !hasRange && !filters.period_days
      ? "all"
      : PERIOD_PRESETS.find((p) => p.label === filters.period_label)?.key || "custom";

  const pick = (key, lab) => {
    if (key === "all") {
      onChange({ date_from: "", date_to: "", period_label: "", period_days: "" });
    } else {
      const [from, to] = presetRange(key);
      onChange({ date_from: from.toISOString(), date_to: to.toISOString(), period_label: lab, period_days: "" });
    }
    setOpen(false);
  };

  const applyCustom = () => {
    if (!customFrom && !customTo) return;
    const from = customFrom ? new Date(`${customFrom}T00:00:00`) : null;
    const to = customTo ? new Date(`${customTo}T23:59:59.999`) : null;
    onChange({
      date_from: from ? from.toISOString() : "",
      date_to: to ? to.toISOString() : "",
      period_label: `${customFrom ? fmtDay(customFrom) : "…"} – ${customTo ? fmtDay(customTo) : "…"}`,
      period_days: "",
    });
    setOpen(false);
  };

  return (
    <div className="field" style={{ position: "relative", marginBottom: 12 }} ref={ref}>
      <span style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-soft)", marginBottom: 4 }}>
        Period
      </span>
      <button type="button" className="period-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <ClockIcon size={14} />
        <span style={{ flex: 1, textAlign: "left", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {label}
        </span>
        <span
          style={{
            display: "inline-flex",
            color: "var(--text-faint)",
            transform: open ? "rotate(-90deg)" : "rotate(90deg)",
            transition: "transform 0.15s",
          }}
        >
          <ChevronRightIcon size={13} />
        </span>
      </button>
      {open && (
        <div className="period-pop">
          <div className="period-presets">
            {PERIOD_PRESETS.map((p) => (
              <button
                key={p.key}
                type="button"
                className={"period-preset" + (selectedKey === p.key ? " selected" : "")}
                onClick={() => pick(p.key, p.label)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="period-custom">
            <div
              className="small"
              style={{ fontWeight: 700, marginBottom: 8, color: selectedKey === "custom" ? "var(--accent)" : "var(--text)" }}
            >
              Custom range
            </div>
            <label className="field">
              <span>From</span>
              <input className="input" type="date" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} />
            </label>
            <label className="field">
              <span>To</span>
              <input className="input" type="date" value={customTo} onChange={(e) => setCustomTo(e.target.value)} />
            </label>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              style={{ width: "100%", justifyContent: "center" }}
              onClick={applyCustom}
              disabled={!customFrom && !customTo}
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const CALL_STATUS = {
  awaiting_recording: ["🎙️ Awaiting recording", "var(--amber)"],
  queued: ["⏳ Queued", "var(--text-soft)"],
  processing: ["⏳ Processing", "var(--text-soft)"],
  downloading: ["⏳ Processing", "var(--text-soft)"],
  transcribing: ["⏳ Transcribing", "var(--text-soft)"],
  analyzing: ["⏳ Analysing", "var(--text-soft)"],
  no_recording: ["No recording", "var(--text-faint)"],
  failed: ["⚠ Failed", "var(--red)"],
};

function CallStatusPill({ status }) {
  const s = CALL_STATUS[status];
  if (!s) return null;             // completed -> no pill
  return (
    <span className="small" style={{ fontWeight: 700, color: s[1], background: "rgba(0,0,0,0.04)", padding: "2px 8px", borderRadius: 99, whiteSpace: "nowrap" }}>
      {s[0]}
    </span>
  );
}

function CallCard({ call, onOpen, avatars }) {
  return (
    <div className="card call-card" onClick={onOpen}>
      <div className="spread">
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {call.customer_name || "Unknown customer"}
          </div>
          <div className="small muted flex" style={{ gap: 6, minWidth: 0 }}>
            {isTeamsMeeting(call) ? (
              <span className="flex" style={{ gap: 4, whiteSpace: "nowrap" }}>
                <VideoIcon size={11} /> Teams Meeting
              </span>
            ) : (
              <>
                <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{callTitle(call)}</span>
                {call.contact_calls > 1 && (
                  <span className="contact-badge" title={`${call.contact_calls} calls with this number`}>
                    <PhoneIcon size={10} /> ×{call.contact_calls}
                  </span>
                )}
              </>
            )}
          </div>
        </div>
        {call.overall_score != null
          ? <ScoreChip score={call.overall_score} size={30} />
          : <CallStatusPill status={call.status} />}
      </div>
      <div className="small" style={{ color: "var(--accent)", fontWeight: 600 }}>{call.activity_type}</div>
      <div className="flex">
        <Avatar name={hostName(call.host)} color={call.host?.avatar_color} size={28} photo={avatars?.[String(call.host?.id)]} />
        <div className="small" style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {hostName(call.host)}
          </div>
          <div className="faint">
            {relativeDate(call.started_at)} · {formatDuration(call.duration_sec)}
          </div>
        </div>
      </div>
      {call.topics && call.topics.length > 0 && (
        <div className="flex" style={{ flexWrap: "wrap", gap: 4 }}>
          {call.topics.slice(0, 3).map((t) => (
            <span key={t.topic_id} className="chip" style={{ fontSize: 11 }}>
              <span className="dot" style={{ background: t.color, width: 7, height: 7 }} />
              {t.name}
            </span>
          ))}
        </div>
      )}
      <div className="flex" style={{ gap: 14, marginTop: "auto", paddingTop: 4 }}>
        <span className="counter"><HeartIcon size={14} /> {call.likes ?? 0}</span>
        <span className="counter"><ShareIcon size={14} /> {call.shares ?? 0}</span>
        <span className="counter"><CommentIcon size={14} /> {call.comments ?? 0}</span>
        <span className="counter"><HeadphonesIcon size={14} /> {call.plays ?? 0}</span>
      </div>
    </div>
  );
}

export default function Library() {
  const navigate = useNavigate();
  const toast = useToast();
  const [searchParams] = useSearchParams();
  const [filters, setFilters] = useState(() => {
    const f = { ...EMPTY_FILTERS };
    const customer = searchParams.get("customer");
    const q = searchParams.get("q") || searchParams.get("transcript");
    if (customer) f.customer = customer;
    if (q) f.transcript = q;
    return f;
  });
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("recent");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [teams, setTeams] = useState([]);
  const [hosts, setHosts] = useState([]);
  const [topics, setTopics] = useState([]);
  const [avatars, setAvatars] = useState({});   // userId -> profile photo, for host faces
  const [saved, setSaved] = useState([]);
  const [savedOpen, setSavedOpen] = useState(false);
  const [saveModal, setSaveModal] = useState(false);
  const [saveName, setSaveName] = useState("");
  const debounceRef = useRef(null);
  const savedRef = useRef(null);

  // host profile photos (shown on the call cards instead of initials)
  useEffect(() => {
    api.get("/api/v1/hr/team/avatars").then((d) => setAvatars(d?.avatars || {})).catch(() => {});
  }, []);

  // option sources (best-effort: admin endpoints may 403 for non-admins)
  useEffect(() => {
    api.get("/api/admin/teams").then((d) => setTeams(Array.isArray(d) ? d : [])).catch(() => {});
    api
      .get("/api/admin/users")
      .then((d) => setHosts((Array.isArray(d) ? d : []).filter((u) => u.active !== false)))
      .catch(() => {
        // fallback: derive hosts from engagement insights
        api
          .get("/api/insights/engagement?days=365")
          .then((d) => setHosts((d?.reps || []).map((r) => r.user).filter(Boolean)))
          .catch(() => {});
      });
    api
      .get("/api/admin/topics")
      .then((d) => setTopics(Array.isArray(d) ? d : []))
      .catch(() => {
        api
          .get("/api/insights/topics?days=365")
          .then((d) => setTopics((Array.isArray(d) ? d : []).map((t) => t.topic).filter(Boolean)))
          .catch(() => {});
      });
    loadSaved();
  }, []);

  const loadSaved = () => {
    api
      .get("/api/calls/saved-searches/mine")
      .then((d) => setSaved(Array.isArray(d) ? d : []))
      .catch(() => {});
  };

  useEffect(() => {
    const close = (e) => {
      if (savedRef.current && !savedRef.current.contains(e.target)) setSavedOpen(false);
    };
    if (savedOpen) document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [savedOpen]);

  // fetch calls (debounced for text inputs)
  useEffect(() => {
    setLoading(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      api
        .get(`/api/calls?${buildQuery(filters, page, sort)}`)
        .then((d) => setData(d))
        .catch((e) => {
          toast(e.message, "error");
          setData({ items: [], total: 0 });
        })
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [filters, page, sort]);

  const setF = (k, v) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setPage(1);
  };

  const setPeriod = (patch) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  const activePills = useMemo(() => {
    const labels = {
      team_id: (v) => `Team: ${teams.find((t) => String(t.id) === String(v))?.name || v}`,
      host_id: (v) => `Host: ${hosts.find((h) => String(h.id) === String(v))?.name || v}`,
      customer: (v) => `Customer: ${v}`,
      transcript: (v) => `Transcript: "${v}"`,
      said_by: (v) => `Said by: ${v}`,
      topic_id: (v) => `Topic: ${topics.find((t) => String(t.id) === String(v))?.name || v}`,
      activity_type: (v) => v,
      direction: (v) => `Direction: ${v}`,
      min_minutes: (v) => `Min ${v}m`,
      max_minutes: (v) => `Max ${v}m`,
      min_score: (v) => `Score ≥ ${v}`,
      max_score: (v) => `Score ≤ ${v}`,
      period_days: (v) => `Last ${v} days`,
    };
    const pills = Object.entries(filters)
      .filter(([k]) => !["date_from", "date_to", "period_label"].includes(k))
      .filter(([, v]) => v !== "" && v != null)
      .map(([k, v]) => ({ key: k, label: labels[k] ? labels[k](v) : `${k}: ${v}` }));
    if (filters.date_from || filters.date_to) {
      pills.push({ key: "__period", label: filters.period_label || "Custom period" });
    }
    return pills;
  }, [filters, teams, hosts, topics]);

  const clearPill = (key) => {
    if (key === "__period") {
      setFilters((f) => ({ ...f, date_from: "", date_to: "", period_label: "" }));
      setPage(1);
    } else {
      setF(key, "");
    }
  };

  const openCall = (c) => {
    const q = (filters.transcript || "").trim();
    navigate(q ? `/calls/${c.id}?q=${encodeURIComponent(q)}` : `/calls/${c.id}`);
  };

  const saveSearch = async () => {
    if (!saveName.trim()) return;
    try {
      await api.post("/api/calls/saved-searches", { name: saveName.trim(), params: filters });
      toast("Search saved", "success");
      setSaveModal(false);
      setSaveName("");
      loadSaved();
    } catch (e) {
      toast(e.message, "error");
    }
  };

  const applySaved = (s) => {
    setFilters({ ...EMPTY_FILTERS, ...(s.params || {}) });
    setPage(1);
    setSavedOpen(false);
  };

  const deleteSaved = async (id, e) => {
    e.stopPropagation();
    try {
      await api.del(`/api/calls/saved-searches/${id}`);
      loadSaved();
    } catch (err) {
      toast(err.message, "error");
    }
  };

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="page">
      <div className="spread" style={{ marginBottom: 18, flexWrap: "wrap" }}>
        <div>
          <h1 className="page-title">{loading && data == null ? "…" : `${total.toLocaleString()} activities`}</h1>
          <p className="page-sub">Search and filter every recorded call.</p>
        </div>
        <div className="flex">
          <div style={{ position: "relative" }} ref={savedRef}>
            <button className="btn btn-outline" onClick={() => setSavedOpen((o) => !o)}>
              <BookmarkIcon size={15} /> Saved searches
            </button>
            {savedOpen && (
              <div
                className="card"
                style={{ position: "absolute", right: 0, top: 42, width: 260, zIndex: 60, padding: 8 }}
              >
                {saved.length === 0 ? (
                  <div className="small muted" style={{ padding: 10 }}>No saved searches yet.</div>
                ) : (
                  saved.map((s) => (
                    <div
                      key={s.id}
                      className="spread"
                      style={{ padding: "8px 10px", borderRadius: 8, cursor: "pointer" }}
                      onClick={() => applySaved(s)}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "#f4f5f7")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                    >
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{s.name}</span>
                      <button className="icon-btn" onClick={(e) => deleteSaved(s.id, e)} aria-label="Delete">
                        <XIcon size={14} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
          <button className="btn btn-primary" onClick={() => setSaveModal(true)}>
            Save Search
          </button>
          <select className="input" style={{ width: 160 }} value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="recent">Most recent</option>
            <option value="duration">Longest duration</option>
            <option value="plays">Most played</option>
          </select>
        </div>
      </div>

      {activePills.length > 0 && (
        <div className="flex" style={{ flexWrap: "wrap", marginBottom: 14 }}>
          {activePills.map((p) => (
            <span key={p.key} className="filter-pill">
              {p.label}
              <button className="x" style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", display: "flex", padding: 0 }} onClick={() => clearPill(p.key)}>
                <XIcon size={12} />
              </button>
            </span>
          ))}
          <button className="btn btn-ghost btn-sm" onClick={() => { setFilters(EMPTY_FILTERS); setPage(1); }}>
            Clear all
          </button>
        </div>
      )}

      <div className="library-layout">
        <aside className="filter-side card">
          <h3 className="card-title">Filters</h3>
          <label className="field">
            <span>Team</span>
            <select className="input" value={filters.team_id} onChange={(e) => setF("team_id", e.target.value)}>
              <option value="">All teams</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Host</span>
            <select className="input" value={filters.host_id} onChange={(e) => setF("host_id", e.target.value)}>
              <option value="">Anyone</option>
              {hosts.map((h) => (
                <option key={h.id} value={h.id}>{h.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Customer</span>
            <input className="input" value={filters.customer} placeholder="Customer name…" onChange={(e) => setF("customer", e.target.value)} />
          </label>
          <label className="field">
            <span>Transcript contains</span>
            <input className="input" value={filters.transcript} placeholder="e.g. broadband" onChange={(e) => setF("transcript", e.target.value)} />
          </label>
          <label className="field">
            <span>Said by</span>
            <select className="input" value={filters.said_by} onChange={(e) => setF("said_by", e.target.value)}>
              <option value="">Anyone</option>
              <option value="rep">Rep</option>
              <option value="customer">Customer</option>
            </select>
          </label>
          <label className="field">
            <span>Topic</span>
            <select className="input" value={filters.topic_id} onChange={(e) => setF("topic_id", e.target.value)}>
              <option value="">Any topic</option>
              {topics.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Activity type</span>
            <select className="input" value={filters.activity_type} onChange={(e) => setF("activity_type", e.target.value)}>
              <option value="">All types</option>
              {ACTIVITY_TYPES.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </label>
          <div className="field" style={{ display: "block", marginBottom: 12 }}>
            <span style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-soft)", marginBottom: 4 }}>
              Duration (minutes)
            </span>
            <div className="flex">
              <input className="input" type="number" min="0" placeholder="Min" value={filters.min_minutes} onChange={(e) => setF("min_minutes", e.target.value)} />
              <input className="input" type="number" min="0" placeholder="Max" value={filters.max_minutes} onChange={(e) => setF("max_minutes", e.target.value)} />
            </div>
          </div>
          <div className="field" style={{ display: "block", marginBottom: 12 }}>
            <span style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--text-soft)", marginBottom: 4 }}>
              AI score
            </span>
            <div className="flex">
              <input className="input" type="number" min="1" max="5" step="0.5" placeholder="Min" value={filters.min_score} onChange={(e) => setF("min_score", e.target.value)} />
              <input className="input" type="number" min="1" max="5" step="0.5" placeholder="Max" value={filters.max_score} onChange={(e) => setF("max_score", e.target.value)} />
            </div>
          </div>
          <PeriodFilter filters={filters} onChange={setPeriod} />
        </aside>

        <div style={{ flex: 1, minWidth: 0 }}>
          {loading ? (
            <div className="call-grid">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} h={180} style={{ borderRadius: 10 }} />
              ))}
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="card">
              <EmptyState icon="🔍" title="No calls match these filters" sub="Try widening your search." />
            </div>
          ) : (
            <>
              <div className="call-grid">
                {data.items.map((c) => (
                  <CallCard key={c.id} call={c} onOpen={() => openCall(c)} avatars={avatars} />
                ))}
              </div>
              <div className="pagination">
                <button className="icon-btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Previous page">
                  <ChevronLeftIcon size={17} />
                </button>
                <span className="small muted">
                  Page {page} of {totalPages}
                </span>
                <button className="icon-btn" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} aria-label="Next page">
                  <ChevronRightIcon size={17} />
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {saveModal && (
        <Modal
          title="Save this search"
          onClose={() => setSaveModal(false)}
          footer={
            <>
              <button className="btn" onClick={() => setSaveModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={saveSearch} disabled={!saveName.trim()}>Save</button>
            </>
          }
        >
          <label className="field">
            <span>Name</span>
            <input className="input" value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder="e.g. Long acquisition calls" autoFocus />
          </label>
          <div className="small muted">Saves the current filter set so you can re-apply it in one click.</div>
        </Modal>
      )}
    </div>
  );
}
