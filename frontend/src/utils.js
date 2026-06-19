// ---- formatting helpers ----

export function formatDuration(sec) {
  if (sec == null || isNaN(sec)) return "—";
  sec = Math.round(sec);
  if (sec >= 3600) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return `${h}h ${m}m`;
  }
  if (sec >= 60) {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return s ? `${m}m ${s}s` : `${m}m`;
  }
  return `${sec}s`;
}

export function mmss(sec) {
  if (sec == null || isNaN(sec)) return "0:00";
  sec = Math.max(0, Math.round(sec));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function timeStr(d) {
  let h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, "0");
  const ampm = h >= 12 ? "PM" : "AM";
  h = h % 12;
  if (h === 0) h = 12;
  return `${h}:${m} ${ampm}`;
}

export function relativeDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const now = new Date();
  const startOfDay = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / 86400000);
  if (diffDays === 0) return `Today, ${timeStr(d)}`;
  if (diffDays === 1) return `Yesterday, ${timeStr(d)}`;
  const dd = String(d.getDate()).padStart(2, "0");
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mo}/${d.getFullYear()}, ${timeStr(d)}`;
}

export function shortDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const dd = String(d.getDate()).padStart(2, "0");
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mo}/${d.getFullYear()}`;
}

export function initials(name) {
  if (!name) return "??";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function scoreColor(score) {
  if (score == null) return "#9ca3af";
  if (score < 2.5) return "#f59e0b";
  if (score < 3.5) return "#eab308";
  return "#10b981";
}

export function scoreColorHard(score) {
  // 1-2 amber/red, 3 yellow, 4-5 green
  if (score == null) return "#9ca3af";
  if (score <= 1.5) return "#ef4444";
  if (score <= 2.5) return "#f59e0b";
  if (score <= 3.5) return "#eab308";
  return "#10b981";
}

export const ACTIVITY_TYPES = [
  "Outbound - Acquisition",
  "Outbound - In Life",
  "Inbound - Call From Customer",
  "Proposal",
  "Service Call",
  "Voicemail",
  "Teams Meeting",
];

export function isTeamsMeeting(call) {
  if (!call) return false;
  return call.activity_type === "Teams Meeting" || (!call.from_number && !call.to_number);
}

export function callTitle(call) {
  if (isTeamsMeeting(call)) return call.customer_name || "Teams Meeting";
  const num = call.direction === "inbound" ? call.from_number : call.to_number;
  const word = call.direction === "inbound" ? "from" : "to";
  return `Call ${word} ${num || "unknown"}`;
}
