import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  ReferenceLine,
  LabelList,
} from "recharts";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Avatar, ScoreChip, Spinner, EmptyState } from "../components/ui.jsx";
import { formatDuration } from "../utils";

const TABS = [
  ["dashboard", "Dashboard"],
  ["engagement", "Engagement"],
  ["topics", "Topics"],
  ["scores", "Scores"],
  ["coaching", "Coaching"],
];

function pctDisplay(v) {
  if (v == null) return "—";
  const n = Number(v);
  return `${Math.round(n > 1 ? n : n * 100)}%`;
}

function pctNumber(v) {
  if (v == null) return 0;
  const n = Number(v);
  return n > 1 ? Math.round(n) : Math.round(n * 100);
}

function StatTile({ label, value }) {
  return (
    <div className="card stat-tile">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  );
}

function EngagementStat({ label, value }) {
  return (
    <div className="spread" style={{ padding: "9px 0", borderBottom: "1px solid #f0f1f3" }}>
      <span className="muted small" style={{ fontWeight: 600 }}>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CoachingDonut({ data, height = 230 }) {
  const total = data?.total ?? 0;
  const parts = [
    { name: "Self coaching", value: data?.self_coaching ?? 0, color: "#e91e63" },
    { name: "Manager led", value: data?.manager_led ?? 0, color: "#9c27b0" },
    { name: "Team coaching", value: data?.team_coaching ?? 0, color: "#14b8a6" },
  ];
  const hasData = parts.some((p) => p.value > 0);
  return (
    <div style={{ position: "relative" }}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={hasData ? parts : [{ name: "None", value: 1, color: "#e5e7eb" }]}
            dataKey="value"
            innerRadius="62%"
            outerRadius="85%"
            paddingAngle={hasData ? 3 : 0}
            stroke="none"
          >
            {(hasData ? parts : [{ color: "#e5e7eb" }]).map((p, i) => (
              <Cell key={i} fill={p.color} />
            ))}
          </Pie>
          {hasData && <Tooltip />}
        </PieChart>
      </ResponsiveContainer>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div style={{ fontSize: 28, fontWeight: 800 }}>{total}</div>
        <div className="small muted">sessions</div>
      </div>
    </div>
  );
}

export default function Insights() {
  const { tab: tabParam } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const tab = TABS.some(([k]) => k === tabParam) ? tabParam : "dashboard";
  const [days, setDays] = useState(30);
  const [teamId, setTeamId] = useState("");
  const [teams, setTeams] = useState([]);

  const [activity, setActivity] = useState(null);
  const [engagement, setEngagement] = useState(null);
  const [topics, setTopics] = useState(null);
  const [scores, setScores] = useState(null);
  const [coaching, setCoaching] = useState(null);
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [sortKey, setSortKey] = useState("calls");
  const [sortDir, setSortDir] = useState(-1);

  useEffect(() => {
    api.get("/api/admin/teams").then((d) => setTeams(Array.isArray(d) ? d : [])).catch(() => {});
  }, []);

  useEffect(() => {
    const q = `?days=${days}${teamId ? `&team_id=${teamId}` : ""}`;
    setActivity(null);
    setEngagement(null);
    setTopics(null);
    setScores(null);
    setCoaching(null);
    let cancelled = false;
    const safe = (p, set) =>
      api
        .get(p)
        .then((d) => !cancelled && set(d))
        .catch((e) => {
          if (!cancelled) {
            set(false);
            toast(e.message, "error");
          }
        });
    safe(`/api/insights/activity${q}`, setActivity);
    safe(`/api/insights/engagement${q}`, setEngagement);
    safe(`/api/insights/topics${q}`, setTopics);
    safe(`/api/insights/scores${q}`, setScores);
    safe(`/api/insights/coaching${q}`, setCoaching);
    return () => {
      cancelled = true;
    };
  }, [days, teamId]);

  useEffect(() => {
    if (Array.isArray(topics) && topics.length && selectedTopic == null) {
      setSelectedTopic(topics[0].topic?.id);
    }
  }, [topics]);

  const sortedReps = useMemo(() => {
    const reps = engagement?.reps || [];
    return [...reps].sort((a, b) => {
      const av = sortKey === "name" ? (a.user?.name || "") : Number(a[sortKey] ?? 0);
      const bv = sortKey === "name" ? (b.user?.name || "") : Number(b[sortKey] ?? 0);
      if (av < bv) return -sortDir;
      if (av > bv) return sortDir;
      return 0;
    });
  }, [engagement, sortKey, sortDir]);

  const setSort = (k) => {
    if (sortKey === k) setSortDir((d) => -d);
    else {
      setSortKey(k);
      setSortDir(-1);
    }
  };

  const topicDetail = Array.isArray(topics) ? topics.find((t) => t.topic?.id === selectedTopic) : null;
  const ov = engagement && engagement !== false ? engagement.overall : null;

  return (
    <div className="page">
      <div className="spread" style={{ marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          <h1 className="page-title">Insights</h1>
          <p className="page-sub">Team performance across calls, topics and coaching.</p>
        </div>
        <div className="flex">
          <select className="input" style={{ width: 170 }} value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">All teams</option>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
          <select className="input" style={{ width: 150 }} value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 180 days</option>
          </select>
        </div>
      </div>

      <div className="tabs" style={{ marginBottom: 22, background: "#fff", borderRadius: "10px 10px 0 0", padding: "0 8px", boxShadow: "var(--shadow)" }}>
        {TABS.map(([k, label]) => (
          <button
            key={k}
            className={"tab" + (tab === k ? " active" : "")}
            onClick={() => navigate(k === "dashboard" ? "/insights" : `/insights/${k}`)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* DASHBOARD */}
      {tab === "dashboard" && (
        <>
          {activity === null ? (
            <Spinner />
          ) : activity === false ? (
            <div className="card"><EmptyState icon="⚠️" title="Could not load activity" /></div>
          ) : (
            <>
              <div className="stat-tiles">
                <StatTile label="Dials Outbound" value={(activity.totals?.outbound ?? 0).toLocaleString()} />
                <StatTile label="Dials Inbound" value={(activity.totals?.inbound ?? 0).toLocaleString()} />
                <StatTile label="Recorded" value={(activity.totals?.recorded ?? 0).toLocaleString()} />
                <StatTile label="Total talk time" value={`${((activity.totals?.total_duration_sec ?? 0) / 3600).toFixed(1)}h`} />
              </div>
              <div className="insights-grid">
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <div className="card">
                    <h3 className="card-title">Call activity</h3>
                    <ResponsiveContainer width="100%" height={280}>
                      <LineChart data={activity.series || []}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#eef0f3" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d) => String(d).slice(5)} />
                        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="outbound" name="Outbound" stroke="#f59e0b" strokeWidth={2.5} dot={false} />
                        <Line type="monotone" dataKey="inbound" name="Inbound" stroke="#14b8a6" strokeWidth={2.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="card">
                    <h3 className="card-title">Coaching activity</h3>
                    {coaching === null ? <Spinner /> : coaching === false ? <EmptyState icon="⚠️" title="Unavailable" /> : (
                      <div className="flex" style={{ gap: 24, flexWrap: "wrap" }}>
                        <div style={{ flex: "1 1 220px", minWidth: 220 }}>
                          <CoachingDonut data={coaching} />
                        </div>
                        <div style={{ flex: "1 1 180px" }}>
                          {[
                            ["Self coaching", coaching.self_coaching, "#e91e63"],
                            ["Manager led", coaching.manager_led, "#9c27b0"],
                            ["Team coaching", coaching.team_coaching, "#14b8a6"],
                          ].map(([label, v, color]) => (
                            <div className="spread" key={label} style={{ padding: "8px 0", borderBottom: "1px solid #f0f1f3" }}>
                              <span className="flex small" style={{ gap: 7 }}>
                                <span className="dot" style={{ background: color }} /> {label}
                              </span>
                              <strong>{v ?? 0}</strong>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <div className="card">
                    <h3 className="card-title">Engagement stats</h3>
                    {!ov ? (
                      engagement === null ? <Spinner /> : <EmptyState icon="📊" title="No data" />
                    ) : (
                      <>
                        <EngagementStat label="Talktime Ratio" value={pctDisplay(ov.talk_ratio)} />
                        <EngagementStat label="Longest Monologue" value={formatDuration(ov.longest_monologue_sec)} />
                        <EngagementStat label="Longest Customer Story" value={formatDuration(ov.longest_customer_story_sec)} />
                        <EngagementStat label="Talking Speed" value={`${Math.round(ov.talking_speed_wpm || 0)} wpm`} />
                        <EngagementStat label="Patience" value={`${Number(ov.patience_sec || 0).toFixed(1)}s`} />
                        <EngagementStat label="Question Rate" value={Number(ov.question_rate || 0).toFixed(1)} />
                      </>
                    )}
                  </div>
                  <div className="card">
                    <h3 className="card-title">🔥 Hot topics</h3>
                    {topics === null ? (
                      <Spinner />
                    ) : !Array.isArray(topics) || topics.length === 0 ? (
                      <EmptyState icon="🏷️" title="No topics yet" />
                    ) : (
                      topics.slice(0, 4).map((t) => (
                        <div className="spread" key={t.topic?.id} style={{ padding: "9px 0", borderBottom: "1px solid #f0f1f3" }}>
                          <span className="flex" style={{ gap: 8, fontWeight: 600, fontSize: 13 }}>
                            <span className="dot" style={{ background: t.topic?.color || "#9ca3af" }} />
                            {t.topic?.name}
                          </span>
                          <span className="small muted">{pctDisplay(t.percentage)} · {t.calls} calls</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </>
      )}

      {/* ENGAGEMENT */}
      {tab === "engagement" && (
        <div className="card">
          <h3 className="card-title">Rep engagement</h3>
          {engagement === null ? (
            <Spinner />
          ) : engagement === false || !engagement.reps?.length ? (
            <EmptyState icon="📊" title="No engagement data" />
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data">
                <thead>
                  <tr>
                    {[
                      ["name", "Rep"],
                      ["calls", "Calls"],
                      ["talk_ratio", "Talk ratio"],
                      ["longest_monologue_sec", "Longest monologue"],
                      ["longest_customer_story_sec", "Customer story"],
                      ["talking_speed_wpm", "Speed (wpm)"],
                      ["patience_sec", "Patience (s)"],
                      ["question_rate", "Question rate"],
                    ].map(([k, label]) => (
                      <th key={k} className="sortable" onClick={() => setSort(k)}>
                        {label} {sortKey === k ? (sortDir === -1 ? "▼" : "▲") : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedReps.map((r) => (
                    <tr key={r.user?.id}>
                      <td>
                        <span className="flex">
                          <Avatar name={r.user?.name} color={r.user?.avatar_color} size={28} />
                          <span style={{ fontWeight: 600 }}>
                            {r.user?.name}
                            {r.user?.active === false && <span className="small faint"> (inactive)</span>}
                          </span>
                        </span>
                      </td>
                      <td>{r.calls ?? 0}</td>
                      <td>{pctDisplay(r.talk_ratio)}</td>
                      <td>{formatDuration(r.longest_monologue_sec)}</td>
                      <td>{formatDuration(r.longest_customer_story_sec)}</td>
                      <td>{Math.round(r.talking_speed_wpm || 0)}</td>
                      <td>{Number(r.patience_sec || 0).toFixed(1)}</td>
                      <td>{Number(r.question_rate || 0).toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TOPICS */}
      {tab === "topics" && (
        <div className="insights-grid" style={{ gridTemplateColumns: "1fr 1.6fr", marginTop: 0 }}>
          <div className="card">
            <h3 className="card-title">Topics</h3>
            {topics === null ? (
              <Spinner />
            ) : !Array.isArray(topics) || topics.length === 0 ? (
              <EmptyState icon="🏷️" title="No topic data" />
            ) : (
              topics.map((t) => (
                <div
                  key={t.topic?.id}
                  className={"topic-row" + (selectedTopic === t.topic?.id ? " selected" : "")}
                  onClick={() => setSelectedTopic(t.topic?.id)}
                >
                  <div className="spread">
                    <span className="flex" style={{ gap: 8, fontWeight: 600 }}>
                      <span className="dot" style={{ background: t.topic?.color || "#9ca3af" }} />
                      {t.topic?.name}
                    </span>
                    <span className="small muted">{pctDisplay(t.percentage)}</span>
                  </div>
                  <div className="pct-bar">
                    <div style={{ width: `${pctNumber(t.percentage)}%`, background: t.topic?.color || "var(--accent)" }} />
                  </div>
                  <div className="small faint">{t.calls} calls mention this topic</div>
                </div>
              ))
            )}
          </div>
          <div className="card">
            <h3 className="card-title">
              {topicDetail ? `${topicDetail.topic?.name} — % of calls by rep` : "Select a topic"}
            </h3>
            {!topicDetail ? (
              <EmptyState icon="👈" title="Pick a topic on the left" />
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(220, (topicDetail.reps?.length || 0) * 44 + 60)}>
                <BarChart
                  layout="vertical"
                  data={(topicDetail.reps || []).map((r) => ({
                    name: r.user?.name || "?",
                    pct: pctNumber(r.percentage),
                    calls: r.calls,
                  }))}
                  margin={{ left: 30, right: 40, top: 10, bottom: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef0f3" horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                  <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v) => [`${v}%`, "Mentions"]} />
                  <ReferenceLine
                    x={pctNumber(topicDetail.team_average)}
                    stroke="#6b7280"
                    strokeDasharray="6 4"
                    label={{ value: `Team avg ${pctNumber(topicDetail.team_average)}%`, position: "top", fontSize: 11, fill: "#6b7280" }}
                  />
                  <Bar dataKey="pct" fill={topicDetail.topic?.color || "#e91e63"} radius={[0, 6, 6, 0]} barSize={18}>
                    <LabelList dataKey="pct" position="right" formatter={(v) => `${v}%`} style={{ fontSize: 11, fill: "#6b7280" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      )}

      {/* SCORES */}
      {tab === "scores" && (
        <div className="insights-grid" style={{ marginTop: 0 }}>
          <div className="card">
            <h3 className="card-title">Leaderboard — average AI score</h3>
            {scores === null ? (
              <Spinner />
            ) : scores === false || !scores.reps?.length ? (
              <EmptyState icon="🏆" title="No scored calls yet" />
            ) : (
              [...scores.reps]
                .sort((a, b) => (b.avg_score ?? 0) - (a.avg_score ?? 0))
                .map((r, i) => (
                  <div className="leader-row" key={r.user?.id}>
                    <span className="rank">{i + 1}</span>
                    <Avatar name={r.user?.name} color={r.user?.avatar_color} size={34} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600 }}>{r.user?.name}</div>
                      <div className="small muted">{r.scored_calls} scored call{r.scored_calls === 1 ? "" : "s"}</div>
                    </div>
                    <ScoreChip score={r.avg_score} size={32} decimals={1} />
                  </div>
                ))
            )}
          </div>
          <div className="card">
            <h3 className="card-title">Skill gaps — weakest criteria first</h3>
            {scores === null ? (
              <Spinner />
            ) : scores === false || !scores.criteria?.length ? (
              <EmptyState icon="🧭" title="No criteria data" />
            ) : (
              [...scores.criteria]
                .sort((a, b) => (a.avg_score ?? 0) - (b.avg_score ?? 0))
                .map((c) => (
                  <div className="leader-row" key={c.name}>
                    <ScoreChip score={c.avg_score} size={30} decimals={1} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600 }}>{c.name}</div>
                      <div className="small muted">{c.n} evaluations</div>
                    </div>
                  </div>
                ))
            )}
          </div>
        </div>
      )}

      {/* COACHING */}
      {tab === "coaching" && (
        <div className="insights-grid" style={{ marginTop: 0 }}>
          <div className="card">
            <h3 className="card-title">Coaching activity</h3>
            {coaching === null ? <Spinner /> : coaching === false ? <EmptyState icon="⚠️" title="Unavailable" /> : <CoachingDonut data={coaching} height={280} />}
          </div>
          <div className="card">
            <h3 className="card-title">Breakdown</h3>
            {coaching && coaching !== false && (
              <>
                {[
                  ["Self coaching", coaching.self_coaching, "#e91e63", "Reps reviewing their own calls"],
                  ["Manager led", coaching.manager_led, "#9c27b0", "1:1 call reviews with a manager"],
                  ["Team coaching", coaching.team_coaching, "#14b8a6", "Group sessions and call libraries"],
                ].map(([label, v, color, sub]) => (
                  <div className="leader-row" key={label}>
                    <span className="dot" style={{ background: color, width: 14, height: 14 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600 }}>{label}</div>
                      <div className="small muted">{sub}</div>
                    </div>
                    <strong style={{ fontSize: 18 }}>{v ?? 0}</strong>
                  </div>
                ))}
                <div className="spread" style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                  <strong>Total sessions</strong>
                  <strong style={{ fontSize: 20 }}>{coaching.total ?? 0}</strong>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
