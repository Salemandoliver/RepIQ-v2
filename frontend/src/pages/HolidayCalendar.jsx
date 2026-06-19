import React, { useEffect, useState } from "react";
import api from "../api";
import { useToast } from "../components/Toast.jsx";
import { Skeleton, EmptyState } from "../components/ui.jsx";

// Company holiday calendar — visible to every signed-in user. Reads RepIQ's own leave data.
function leaveIcon(code, weekend) {
  if (code) {
    const c = String(code).toUpperCase();
    if (c === "H") return { ico: "🌴", t: "Holiday" };
    if (c === "H1" || c === "H2" || c === "HD") return { ico: "🏖️", t: "Half day" };
    if (c[0] === "S") return { ico: "🤒", t: "Sick" };
    if (c === "B" || c === "BH") return { ico: "·", t: "Bank holiday", muted: true };
    if (c === "C") return { ico: "🕊️", t: "Compassionate" };
    return { ico: "📋", t: "Leave" };
  }
  if (weekend) return { ico: "·", t: "Weekend", muted: true };
  return { ico: "🧍", t: "Working", work: true };
}
const HOL_LEGEND = [["🧍", "Working"], ["🌴", "Holiday"], ["🏖️", "Half day"], ["🤒", "Sick"],
  ["🕊️", "Compassionate"], ["📋", "Other leave"], ["·", "Weekend / bank holiday"]];

export default function HolidayCalendar() {
  const toast = useToast();
  const now = new Date();
  const [ym, setYm] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [team, setTeam] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/salesiq/holiday-calendar?ym=${ym}&team=${encodeURIComponent(team)}`)
      .then(setData).catch((e) => { toast(e.message, "error"); setData(null); })
      .finally(() => setLoading(false));
  }, [ym, team]);

  const shift = (delta) => {
    let [y, m] = ym.split("-").map(Number);
    m += delta;
    if (m < 1) { y -= 1; m = 12; }
    if (m > 12) { y += 1; m = 1; }
    setYm(`${y}-${String(m).padStart(2, "0")}`);
  };
  const [yy, mm] = ym.split("-").map(Number);
  const label = new Date(yy, mm - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  const todayDay = (yy === now.getFullYear() && mm === now.getMonth() + 1) ? now.getDate() : null;
  const teamOpts = [["all", "All Teams"], ...((data?.teamsAvailable) || []).map((tn) => [tn.toLowerCase(), tn])];

  return (
    <div className="page" style={{ maxWidth: 1180, margin: "0 auto", padding: "28px 22px 60px" }}>
      <div className="spread" style={{ marginBottom: 18, flexWrap: "wrap", gap: 10 }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>🗓️ Holiday Calendar</h1>
        <div className="flex" style={{ gap: 12, flexWrap: "wrap" }}>
          <div className="flex" style={{ gap: 8 }}>
            <button className="btn btn-outline" onClick={() => shift(-1)} aria-label="Previous month">‹</button>
            <strong style={{ fontSize: 16, minWidth: 140, textAlign: "center", alignSelf: "center" }}>{label}</strong>
            <button className="btn btn-outline" onClick={() => shift(1)} aria-label="Next month">›</button>
          </div>
          <select className="input siq-team-sel" value={team} onChange={(e) => setTeam(e.target.value)}>
            {teamOpts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      <div className="card">
        {loading ? (
          <Skeleton h={320} style={{ borderRadius: 10 }} />
        ) : !data?.found ? (
          <EmptyState icon="🗓️" title="No holiday data for this month" sub="Run the holiday sync in Settings → HR Import once, then it refreshes automatically." />
        ) : (
          <>
            <div className="hol-cal-wrap">
              <table className="hol-cal">
                <thead>
                  <tr>
                    <th className="hol-corner">Employee</th>
                    {data.days.map((d) => (
                      <th key={d.day} className={(d.weekend ? "we" : "") + (todayDay === d.day ? " today" : "")} title={d.weekday}>
                        <div className="hol-dnum">{d.day}</div>
                        <div className="hol-dwk">{d.weekday[0]}</div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.people.map((p) => (
                    <tr key={p.name}>
                      <td className="hol-name">{p.name}</td>
                      {data.days.map((d) => {
                        const m = leaveIcon(p.cells[d.day], d.weekend);
                        return (
                          <td key={d.day} title={`${p.name} · ${d.day} ${d.weekday} · ${m.t}`}
                            className={"hol-c" + (m.muted ? " mut" : "") + (d.weekend ? " we" : "") + (todayDay === d.day ? " today" : "")}>
                            {m.ico}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex" style={{ gap: 14, flexWrap: "wrap", marginTop: 14 }}>
              {HOL_LEGEND.map(([ico, t]) => (
                <span key={t} className="small muted" style={{ display: "inline-flex", gap: 5, alignItems: "center" }}>{ico} {t}</span>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
