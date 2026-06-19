import React from "react";
import { initials, scoreColorHard } from "../utils";
import { XIcon } from "./Icons.jsx";

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

export function Modal({ title, onClose, children, wide, footer }) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={"modal" + (wide ? " wide" : "")}>
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
