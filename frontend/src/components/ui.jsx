import React from "react";
import { initials, scoreColorHard } from "../utils";
import { XIcon } from "./Icons.jsx";

// Collapsible card shell — click the header (or the up/down arrow) to fold. Defaults to open
// ("full display"). `actions` renders extra controls on the header right, before the arrow.
export function CollapsibleCard({ title, actions, defaultOpen = true, style, className = "card", children, titleTag = "h2" }) {
  const [open, setOpen] = React.useState(defaultOpen);
  const T = titleTag;
  return (
    <div className={className} style={style}>
      <div className="spread" style={{ cursor: "pointer", marginBottom: open ? 12 : 0 }} onClick={() => setOpen((v) => !v)}>
        <T className="card-title" style={{ margin: 0 }}>{title}</T>
        <div className="flex" style={{ gap: 10, alignItems: "center" }}>
          {actions}
          <button className="btn btn-ghost btn-sm" aria-label={open ? "Collapse" : "Expand"} style={{ lineHeight: 1 }}
            onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}>{open ? "▲" : "▼"}</button>
        </div>
      </div>
      {open && children}
    </div>
  );
}

export function Avatar({ name, color, size = 36, photo }) {
  if (photo) {
    return (
      <span className="avatar" title={name}
        style={{ width: size, height: size, padding: 0, overflow: "hidden", background: "#fff" }}>
        <img src={photo} alt={name || ""} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </span>
    );
  }
  return (
    <span
      className="avatar"
      style={{
        width: size,
        height: size,
        background: color || "#6b7280",
        fontSize: Math.max(10, Math.round(size * 0.38)),
      }}
      title={name}
    >
      {initials(name)}
    </span>
  );
}

// A UK-format date field (dd/mm/yyyy) that doesn't depend on the browser locale like the native
// <input type="date"> does. `value`/`onChange` use ISO (yyyy-mm-dd); the user sees dd/mm/yyyy.
export function GBDate({ value, onChange, style, autoFocus }) {
  const toDisp = (iso) => (iso && /^\d{4}-\d{2}-\d{2}$/.test(iso)) ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "";
  const [text, setText] = React.useState(toDisp(value));
  React.useEffect(() => { setText(toDisp(value)); }, [value]);
  const handle = (e) => {
    const digits = e.target.value.replace(/\D/g, "").slice(0, 8);
    let out = digits;
    if (digits.length >= 5) out = digits.slice(0, 2) + "/" + digits.slice(2, 4) + "/" + digits.slice(4);
    else if (digits.length >= 3) out = digits.slice(0, 2) + "/" + digits.slice(2);
    setText(out);
    onChange(digits.length === 8 ? `${digits.slice(4)}-${digits.slice(2, 4)}-${digits.slice(0, 2)}` : "");
  };
  return <input className="input" placeholder="dd/mm/yyyy" inputMode="numeric" maxLength={10}
    value={text} onChange={handle} style={style} autoFocus={autoFocus} />;
}

export function ScoreChip({ score, size = 28, decimals }) {
  if (score == null) return null;
  const txt =
    decimals != null
      ? Number(score).toFixed(decimals)
      : Number.isInteger(Number(score))
        ? String(score)
        : Number(score).toFixed(1);
  return (
    <span
      className="score-chip"
      style={{
        width: size >= 40 ? "auto" : size,
        minWidth: size,
        height: size,
        padding: size >= 40 ? "0 10px" : 0,
        background: scoreColorHard(Number(score)),
        fontSize: Math.max(11, Math.round(size * 0.45)),
      }}
      title={`AI Score: ${txt}`}
    >
      {txt}
    </span>
  );
}

export function Spinner() {
  return <div className="spinner" />;
}

export function Skeleton({ h = 16, w = "100%", style }) {
  return <div className="skeleton" style={{ height: h, width: w, ...style }} />;
}

export function SkeletonRows({ n = 5, h = 48 }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {Array.from({ length: n }).map((_, i) => (
        <Skeleton key={i} h={h} />
      ))}
    </div>
  );
}

export function EmptyState({ icon = "📭", title = "Nothing here", sub }) {
  return (
    <div className="empty-state">
      <div className="big">{icon}</div>
      <div style={{ fontWeight: 600 }}>{title}</div>
      {sub && <div className="small" style={{ marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide, xl, footer }) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={"modal" + (xl ? " xl" : wide ? " wide" : "")}>
        <div className="spread" style={{ marginBottom: 14 }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <XIcon size={18} />
          </button>
        </div>
        {children}
        {footer && (
          <div className="flex" style={{ justifyContent: "flex-end", marginTop: 18 }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
