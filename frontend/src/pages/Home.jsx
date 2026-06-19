import React, { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Avatar, ScoreChip, SkeletonRows, EmptyState } from "../components/ui.jsx";
import { formatDuration, relativeDate, callTitle, isTeamsMeeting } from "../utils";
import {
  PlayIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  HeadphonesIcon,
  FlameIcon,
  VideoIcon,
  TrophyIcon,
} from "../components/Icons.jsx";

function RecordingRow({ call }) {
  return (
    <div className="rec-row">
      <Avatar name={call.host?.name || call.customer_name} color={call.host?.avatar_color} size={36} />
      <div className="meta">
        <div className="top">{call.customer_name || "Unknown customer"}</div>
        <div className="sub">
          {isTeamsMeeting(call) ? (
            <span className="flex" style={{ gap: 4, display: "inline-flex", alignItems: "center" }}>
              <VideoIcon size={12} /> Teams Meeting
            </span>
          ) : (
            <>{callTitle(call)} · {call.activity_type}</>
          )}
        </div>
        <div className="sub faint">{relativeDate(call.started_at)} · {formatDuration(call.duration_sec)}</div>
      </div>
      {call.overall_score != null && <ScoreChip score={call.overall_score} size={26} />}
      <Link to={`/calls/${call.id}`} className="play-link" title="Open call">
        <PlayIcon size={15} />
      </Link>
    </div>
  );
}

function PickRow({ call, rank }) {
  return (
    <Link to={`/calls/${call.id}`} className="rec-row" style={{ textDecoration: "none", color: "inherit" }}>
      <div className="pick-rank">{rank}</div>
      <div className="meta">
        <div className="top">{call.customer_name || "Unknown customer"}</div>
        <div className="sub faint">
          {call.host?.name || "Unknown host"} · {call.activity_type} · {formatDuration(call.duration_sec)}
        </div>
      </div>
      {call.spin_score != null && <ScoreChip score={call.spin_score} size={28} />}
    </Link>
  );
}

export default function Home() {
  const { user } = useOutletContext();
  const toast = useToast();
  const [tab, setTab] = useState("mine");
  const [teams, setTeams] = useState([]);
  const [teamId, setTeamId] = useState("");
  const [recordings, setRecordings] = useState(null);
  const [trending, setTrending] = useState(null);
  const [trendIdx, setTrendIdx] = useState(0);
  const [picks, setPicks] = useState(null);
  const [feed, setFeed] = useState(null);

  // Load teams once (used by the Team Recordings dropdown).
  useEffect(() => {
    api
      .get("/api/admin/teams")
      .then((d) => {
        const list = Array.isArray(d) ? d : [];
        setTeams(list);
        if (list.length) setTeamId((cur) => cur || String(list[0].id));
      })
      .catch(() => {});
  }, []);

  // Recordings list — reacts to the active tab and selected team.
  useEffect(() => {
    let cancelled = false;
    if (tab === "team" && !teamId) {
      setRecordings([]);
      return;
    }
    setRecordings(null);
    let url = `/api/calls?page=1&page_size=15&sort=recent`;
    if (tab === "mine") url += "&mine=true";
    else if (tab === "team") url += `&team_id=${teamId}`;
    api
      .get(url)
      .then((d) => !cancelled && setRecordings(d.items || []))
      .catch((e) => {
        if (!cancelled) {
          setRecordings([]);
          toast(e.message, "error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tab, teamId]);

  useEffect(() => {
    api
      .get("/api/calls/trending")
      .then((d) => setTrending(Array.isArray(d) ? d : []))
      .catch(() => setTrending([]));
    api
      .get("/api/calls/calliq-picks")
      .then((d) => setPicks(Array.isArray(d) ? d : []))
      .catch(() => setPicks([]));
    api
      .get("/api/calls/live-feed")
      .then((d) => setFeed(Array.isArray(d) ? d : []))
      .catch(() => setFeed([]));
  }, []);

  const trend = trending && trending.length ? trending[trendIdx % trending.length] : null;

  return (
    <div className="page">
      <div className="spread" style={{ marginBottom: 20 }}>
        <div>
          <h1 className="page-title">Welcome back, {user?.preferred_name || (user?.name || "").split(" ")[0]} 👋</h1>
          <p className="page-sub">Here's what's happening across your team's calls.</p>
        </div>
      </div>

      <div className="home-grid">
        {/* Recordings */}
        <div className="card">
          <div className="rec-tabs-row">
            <div className="pill-tabs">
              <button className={tab === "mine" ? "active" : ""} onClick={() => setTab("mine")}>
                My Recordings
              </button>
              <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>
                Everyone's Recordings
              </button>
              <button className={tab === "team" ? "active" : ""} onClick={() => setTab("team")}>
                Team Recordings
              </button>
            </div>
            {tab === "team" && (
              <select
                className="input team-select"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
              >
                {teams.length === 0 && <option value="">No teams</option>}
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            )}
          </div>
          {recordings === null ? (
            <SkeletonRows n={6} h={52} />
          ) : recordings.length === 0 ? (
            <EmptyState
              icon="🎧"
              title={tab === "team" && !teamId ? "Pick a team" : "No recordings yet"}
              sub={tab === "team" ? "Choose a team to see its calls." : "Calls will appear here once recorded."}
            />
          ) : (
            recordings.map((c) => <RecordingRow key={c.id} call={c} />)
          )}
        </div>

        {/* Trending + Calls of the Month (stacked) */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20, minWidth: 0 }}>
          <div className="card">
            <div className="spread" style={{ marginBottom: 12 }}>
              <h2 className="card-title" style={{ margin: 0 }}>
                <span className="flex">
                  <FlameIcon size={17} /> Trending this month
                </span>
              </h2>
              {trending && trending.length > 1 && (
                <div className="trend-nav">
                  <button
                    className="icon-btn"
                    onClick={() => setTrendIdx((i) => (i - 1 + trending.length) % trending.length)}
                    aria-label="Previous"
                  >
                    <ChevronLeftIcon size={17} />
                  </button>
                  <button
                    className="icon-btn"
                    onClick={() => setTrendIdx((i) => (i + 1) % trending.length)}
                    aria-label="Next"
                  >
                    <ChevronRightIcon size={17} />
                  </button>
                </div>
              )}
            </div>
            {trending === null ? (
              <SkeletonRows n={3} h={60} />
            ) : !trend ? (
              <EmptyState icon="🔥" title="Nothing trending yet" />
            ) : (
              <Link to={`/calls/${trend.id}`} style={{ display: "block" }}>
                <div
                  style={{
                    background: "var(--accent-grad)",
                    borderRadius: 10,
                    color: "#fff",
                    padding: 16,
                    marginBottom: 12,
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: 15 }}>{trend.customer_name || "Unknown customer"}</div>
                  <div style={{ opacity: 0.9, fontSize: 12.5, marginTop: 2 }}>
                    {isTeamsMeeting(trend) ? (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <VideoIcon size={12} /> Teams Meeting
                      </span>
                    ) : (
                      <>{callTitle(trend)} · {trend.activity_type}</>
                    )}
                  </div>
                  <div className="flex" style={{ marginTop: 12, justifyContent: "space-between" }}>
                    <span className="flex" style={{ fontSize: 12.5 }}>
                      <HeadphonesIcon size={15} /> {trend.times_played ?? trend.plays ?? 0} plays
                    </span>
                    <span style={{ fontSize: 12.5 }}>{formatDuration(trend.duration_sec)}</span>
                  </div>
                </div>
                <div className="flex">
                  <Avatar name={trend.host?.name} color={trend.host?.avatar_color} size={32} />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{trend.host?.name || "Unknown host"}</div>
                    <div className="small muted">{relativeDate(trend.started_at)}</div>
                  </div>
                  <span style={{ marginLeft: "auto" }}>
                    {trend.overall_score != null && <ScoreChip score={trend.overall_score} size={28} />}
                  </span>
                </div>
                {trending.length > 1 && (
                  <div className="small faint" style={{ textAlign: "center", marginTop: 12 }}>
                    {(trendIdx % trending.length) + 1} of {trending.length}
                  </div>
                )}
              </Link>
            )}
          </div>

          {/* RepIQ Calls of the Month — top SPIN-method calls */}
          <div className="card">
            <h2 className="card-title" style={{ marginBottom: 4 }}>
              <span className="flex">
                <TrophyIcon size={17} /> RepIQ Calls of the Month
              </span>
            </h2>
            <p className="small muted" style={{ marginTop: 0, marginBottom: 12 }}>
              The month's best SPIN-method calls — refreshed as new high-quality calls come in.
            </p>
            {picks === null ? (
              <SkeletonRows n={4} h={48} />
            ) : picks.length === 0 ? (
              <EmptyState icon="🏆" title="No standout calls yet this month" sub="High-scoring SPIN calls will appear here." />
            ) : (
              picks.map((c, i) => <PickRow key={c.id} call={c} rank={i + 1} />)
            )}
          </div>
        </div>

        {/* Live feed */}
        <div className="card">
          <h2 className="card-title">Live Feed</h2>
          {feed === null ? (
            <SkeletonRows n={6} h={48} />
          ) : feed.length === 0 ? (
            <EmptyState icon="📡" title="No recent activity" />
          ) : (
            feed.map((f) => (
              <div className="feed-row" key={f.id}>
                <Avatar name={f.user?.name} color={f.user?.avatar_color} size={32} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13 }}>
                    <strong>{f.user?.name}</strong> listened to a call
                  </div>
                  {f.call && (
                    <Link to={`/calls/${f.call.id}`} className="small" style={{ color: "var(--accent)", fontWeight: 600 }}>
                      {f.call.customer_name || callTitle(f.call)}
                    </Link>
                  )}
                  <div className="small faint">
                    {f.call?.activity_type} · held {relativeDate(f.call?.started_at)} ·{" "}
                    {formatDuration(f.call?.duration_sec)}
                  </div>
                  <div className="small faint">{relativeDate(f.listened_at)}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
