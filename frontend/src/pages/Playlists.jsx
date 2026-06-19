import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Avatar, ScoreChip, Modal, Spinner, EmptyState, SkeletonRows } from "../components/ui.jsx";
import { formatDuration, relativeDate, callTitle, isTeamsMeeting } from "../utils";
import {
  PlayIcon, PlusIcon, XIcon, EditIcon, TrashIcon,
  FlameIcon, ChevronLeftIcon, ChevronRightIcon, HeadphonesIcon, VideoIcon,
} from "../components/Icons.jsx";

function trackTitle(call) {
  if (call.customer_name && call.customer_name !== "Unknown Customer") return call.customer_name;
  return callTitle(call);
}

/* Trending calls — moved here from the old Home page. The month's most-played calls. */
function TrendingCard() {
  const [trending, setTrending] = useState(null);
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    api.get("/api/calls/trending").then((d) => setTrending(Array.isArray(d) ? d : [])).catch(() => setTrending([]));
  }, []);
  const trend = trending && trending.length ? trending[idx % trending.length] : null;
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="spread" style={{ marginBottom: 12 }}>
        <h2 className="card-title" style={{ margin: 0 }}>
          <span className="flex"><FlameIcon size={17} /> Trending this month</span>
        </h2>
        {trending && trending.length > 1 && (
          <div className="trend-nav">
            <button className="icon-btn" onClick={() => setIdx((i) => (i - 1 + trending.length) % trending.length)} aria-label="Previous"><ChevronLeftIcon size={17} /></button>
            <button className="icon-btn" onClick={() => setIdx((i) => (i + 1) % trending.length)} aria-label="Next"><ChevronRightIcon size={17} /></button>
          </div>
        )}
      </div>
      {trending === null ? (
        <SkeletonRows n={3} h={60} />
      ) : !trend ? (
        <EmptyState icon="🔥" title="Nothing trending yet" sub="The month's most-played calls will appear here." />
      ) : (
        <Link to={`/calls/${trend.id}`} style={{ display: "block", textDecoration: "none", color: "inherit" }}>
          <div style={{ background: "var(--accent-grad)", borderRadius: 10, color: "#fff", padding: 16, marginBottom: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 15 }}>{trend.customer_name || "Unknown customer"}</div>
            <div style={{ opacity: 0.9, fontSize: 12.5, marginTop: 2 }}>
              {isTeamsMeeting(trend) ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><VideoIcon size={12} /> Teams Meeting</span>
              ) : (<>{callTitle(trend)} · {trend.activity_type}</>)}
            </div>
            <div className="flex" style={{ marginTop: 12, justifyContent: "space-between" }}>
              <span className="flex" style={{ fontSize: 12.5 }}><HeadphonesIcon size={15} /> {trend.times_played ?? trend.plays ?? 0} plays</span>
              <span style={{ fontSize: 12.5 }}>{formatDuration(trend.duration_sec)}</span>
            </div>
          </div>
          <div className="flex">
            <Avatar name={trend.host?.name} color={trend.host?.avatar_color} size={32} />
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{trend.host?.name || "Unknown host"}</div>
              <div className="small muted">{relativeDate(trend.started_at)}</div>
            </div>
            <span style={{ marginLeft: "auto" }}>{trend.overall_score != null && <ScoreChip score={trend.overall_score} size={28} />}</span>
          </div>
          {trending.length > 1 && (
            <div className="small faint" style={{ textAlign: "center", marginTop: 12 }}>{(idx % trending.length) + 1} of {trending.length}</div>
          )}
        </Link>
      )}
    </div>
  );
}

function PlaylistFormModal({ title, initial, saving, onSave, onClose }) {
  const [name, setName] = useState(initial?.name || "");
  const [description, setDescription] = useState(initial?.description || "");
  return (
    <Modal title={title} onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) onSave({ name: name.trim(), description: description.trim() });
        }}
      >
        <label className="field">
          <span>Name</span>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Best discovery calls"
            autoFocus
          />
        </label>
        <label className="field">
          <span>Description (optional)</span>
          <textarea
            className="input"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What makes these calls worth a listen?"
          />
        </label>
        <div className="flex" style={{ justifyContent: "flex-end", marginTop: 16 }}>
          <button type="button" className="btn btn-outline" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || !name.trim()}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function TrackRow({ item, onRemove }) {
  const call = item.call;
  return (
    <div className="track-row">
      <Link to={`/calls/${call.id}`} className="play-link" title="Open call">
        <PlayIcon size={15} />
      </Link>
      <Avatar name={call.host?.name} color={call.host?.avatar_color} size={32} />
      <div className="meta">
        <div className="top">{trackTitle(call)}</div>
        <div className="sub">
          {call.host?.name || "Unknown host"} · {call.activity_type}
        </div>
      </div>
      <span className="small muted" style={{ whiteSpace: "nowrap" }}>{formatDuration(call.duration_sec)}</span>
      <span className="small faint" style={{ whiteSpace: "nowrap" }}>{relativeDate(call.started_at)}</span>
      {call.overall_score != null && <ScoreChip score={call.overall_score} size={26} />}
      <button
        className="icon-btn"
        onClick={() => onRemove(call)}
        title="Remove from playlist"
        aria-label="Remove from playlist"
      >
        <XIcon size={15} />
      </button>
    </div>
  );
}

export default function Playlists() {
  const toast = useToast();
  const [playlists, setPlaylists] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [renaming, setRenaming] = useState(null);
  const [saving, setSaving] = useState(false);
  const [menuFor, setMenuFor] = useState(null);
  const menuRef = useRef(null);

  const loadPlaylists = async (selectId) => {
    try {
      const d = await api.get("/api/playlists");
      const list = Array.isArray(d) ? d : [];
      setPlaylists(list);
      setSelectedId((cur) => {
        const want = selectId != null ? selectId : cur;
        if (want != null && list.some((p) => p.id === want)) return want;
        return list.length ? list[0].id : null;
      });
    } catch (e) {
      setPlaylists([]);
      toast(e.message, "error");
    }
  };

  useEffect(() => {
    loadPlaylists();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    setDetailError("");
    api
      .get(`/api/playlists/${selectedId}`)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setDetailError(e.message));
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  useEffect(() => {
    if (menuFor == null) return;
    const close = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuFor(null);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuFor]);

  const createPlaylist = async (body) => {
    setSaving(true);
    try {
      const p = await api.post("/api/playlists", body);
      setShowCreate(false);
      toast(`Playlist "${p.name}" created`, "success");
      await loadPlaylists(p.id);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const saveRename = async (body) => {
    if (!renaming) return;
    setSaving(true);
    try {
      await api.patch(`/api/playlists/${renaming.id}`, body);
      setPlaylists((ps) => (ps || []).map((p) => (p.id === renaming.id ? { ...p, ...body } : p)));
      setDetail((d) => (d && d.id === renaming.id ? { ...d, ...body } : d));
      setRenaming(null);
      toast("Playlist updated", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const deletePlaylist = async (p) => {
    if (!window.confirm(`Delete playlist "${p.name}"? This cannot be undone.`)) return;
    setMenuFor(null);
    try {
      await api.del(`/api/playlists/${p.id}`);
      toast("Playlist deleted", "success");
      if (selectedId === p.id) setSelectedId(null);
      await loadPlaylists();
    } catch (e) {
      toast(e.message, "error");
    }
  };

  const removeTrack = async (call) => {
    if (!window.confirm("Remove this call from the playlist?")) return;
    try {
      await api.del(`/api/playlists/${selectedId}/items/${call.id}`);
      setDetail((d) => (d ? { ...d, items: (d.items || []).filter((it) => it.call?.id !== call.id) } : d));
      setPlaylists((ps) =>
        (ps || []).map((p) => (p.id === selectedId ? { ...p, tracks: Math.max(0, (p.tracks || 1) - 1) } : p))
      );
      toast("Removed from playlist", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  };

  const items = detail?.items || [];

  return (
    <div className="page">
      <div className="spread" style={{ marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 className="page-title">Playlists</h1>
          <p className="page-sub">Curated collections of calls for sharing and coaching.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <PlusIcon size={15} /> New Playlist
        </button>
      </div>

      <TrendingCard />

      <div className="playlists-layout">
        {/* left pane: playlist list */}
        <div className="card playlist-side">
          <h2 className="card-title" style={{ padding: "4px 8px 0" }}>Playlists</h2>
          {playlists === null ? (
            <SkeletonRows n={5} h={44} />
          ) : playlists.length === 0 ? (
            <EmptyState icon="🎵" title="No playlists yet" sub="Create one to start collecting standout calls." />
          ) : (
            playlists.map((p) => (
              <div
                key={p.id}
                className={"playlist-row" + (p.id === selectedId ? " selected" : "")}
                onClick={() => setSelectedId(p.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && setSelectedId(p.id)}
              >
                <div className="meta">
                  <div className="name">{p.name}</div>
                  <div className="small muted">
                    {p.tracks} track{p.tracks === 1 ? "" : "s"}
                  </div>
                </div>
                <Avatar name={p.owner?.name} color={p.owner?.avatar_color} size={26} />
                {p.can_edit && (
                  <span style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
                    <button
                      className="icon-btn"
                      onClick={() => setMenuFor(menuFor === p.id ? null : p.id)}
                      aria-label="Playlist options"
                    >
                      ⋯
                    </button>
                    {menuFor === p.id && (
                      <div className="menu-pop" ref={menuRef}>
                        <button
                          onClick={() => {
                            setMenuFor(null);
                            setRenaming(p);
                          }}
                        >
                          <EditIcon size={14} /> Rename
                        </button>
                        <button className="danger" onClick={() => deletePlaylist(p)}>
                          <TrashIcon size={14} /> Delete
                        </button>
                      </div>
                    )}
                  </span>
                )}
              </div>
            ))
          )}
        </div>

        {/* right pane: selected playlist */}
        <div className="card playlists-main">
          {playlists !== null && playlists.length === 0 ? (
            <EmptyState
              icon="🎧"
              title="Build your first playlist"
              sub='Click "New Playlist" to group great calls for onboarding, coaching or sharing wins.'
            />
          ) : detailError ? (
            <EmptyState icon="⚠️" title="Could not load playlist" sub={detailError} />
          ) : !detail ? (
            <Spinner />
          ) : (
            <>
              <div className="playlist-head">
                <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
                  <h2 style={{ margin: 0, fontSize: 18 }}>{detail.name}</h2>
                  <span className="faint">|</span>
                  <span className="muted small" style={{ fontWeight: 600 }}>
                    {items.length} track{items.length === 1 ? "" : "s"}
                  </span>
                  <span className="faint">|</span>
                  <span className="flex" style={{ gap: 6 }}>
                    <Avatar name={detail.owner?.name} color={detail.owner?.avatar_color} size={22} />
                    <span className="muted small" style={{ fontWeight: 600 }}>{detail.owner?.name}</span>
                  </span>
                </div>
                {detail.description && <p className="muted" style={{ margin: "8px 0 0" }}>{detail.description}</p>}
              </div>
              {items.length === 0 ? (
                <EmptyState icon="🎵" title="No calls yet" sub="Add calls from any call page." />
              ) : (
                items.map((it) => <TrackRow key={it.item_id} item={it} onRemove={removeTrack} />)
              )}
            </>
          )}
        </div>
      </div>

      {showCreate && (
        <PlaylistFormModal
          title="New playlist"
          saving={saving}
          onSave={createPlaylist}
          onClose={() => setShowCreate(false)}
        />
      )}
      {renaming && (
        <PlaylistFormModal
          title="Rename playlist"
          initial={renaming}
          saving={saving}
          onSave={saveRename}
          onClose={() => setRenaming(null)}
        />
      )}
    </div>
  );
}
