import React, { useEffect, useMemo, useState } from "react";
import api from "../api";
import { useToast } from "./Toast.jsx";
import { Modal, EmptyState, Skeleton, GBDate } from "./ui.jsx";

// Campaigns manager UI (Roadmap Phase 1) — promotions (customer-facing) + incentives (rep-facing),
// each time-bound and linked to catalogue products. Lives inside SalesIQ for managers/admin.

const STATUS_STYLE = {
  live: { c: "var(--green)", label: "● Live" },
  scheduled: { c: "var(--accent)", label: "◷ Scheduled" },
  expired: { c: "var(--text-faint)", label: "✓ Ended" },
  archived: { c: "var(--text-faint)", label: "▢ Archived" },
};
const TYPE_LABEL = { promotion: "📣 Promotion", incentive: "🎯 Incentive" };
const BASIS = [["per_sale", "Per qualifying sale"], ["threshold", "On hitting a threshold"], ["tiered", "Tiered"]];

function fmtGBP(v) {
  if (v == null || v === "") return "—";
  return "£" + Number(v).toLocaleString("en-GB");
}
function fmtRange(s, e) {
  const d = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "");
  return `${d(s)} → ${d(e)}`;
}
function daysLeft(end) {
  const ms = new Date(end + "T23:59:59") - new Date();
  return Math.ceil(ms / 86400000);
}

const BLANK = {
  type: "promotion", name: "", description: "", startDate: "", endDate: "",
  productIds: [], teams: [], talkingPoints: "",
  offer: "", customerSegments: "", sovMultiplier: "",
  rewardAmount: "", rewardBasis: "per_sale", qualifyingRule: "", targetPerRep: "", teamTarget: "",
};

function Field({ label, children, hint }) {
  return (
    <label className="field" style={{ margin: "0 0 12px" }}>
      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-soft)" }}>{label}</span>
      {children}
      {hint && <span className="muted" style={{ fontSize: 11 }}>{hint}</span>}
    </label>
  );
}

function CampaignModal({ campaign, products, teams, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState(() => ({ ...BLANK, ...(campaign || {}) }));
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const isNew = !campaign?.id;
  const isPromo = f.type === "promotion";

  const toggleProduct = (id) =>
    set("productIds", f.productIds.includes(id) ? f.productIds.filter((x) => x !== id) : [...f.productIds, id]);
  const toggleTeam = (id) =>
    set("teams", f.teams.includes(id) ? f.teams.filter((x) => x !== id) : [...f.teams, id]);

  async function save() {
    if (!f.name.trim()) return toast("Give the campaign a name", "error");
    if (!f.startDate || !f.endDate) return toast("Set a start and end date", "error");
    if (f.endDate < f.startDate) return toast("End date can't be before the start date", "error");
    setBusy(true);
    const body = {
      type: f.type, name: f.name.trim(), description: f.description, startDate: f.startDate,
      endDate: f.endDate, productIds: f.productIds, teams: f.teams, talkingPoints: f.talkingPoints,
    };
    if (isPromo) Object.assign(body, { offer: f.offer, customerSegments: f.customerSegments,
      sovMultiplier: f.sovMultiplier === "" ? null : f.sovMultiplier });
    else Object.assign(body, { rewardAmount: f.rewardAmount === "" ? null : f.rewardAmount,
      rewardBasis: f.rewardBasis, qualifyingRule: f.qualifyingRule,
      targetPerRep: f.targetPerRep === "" ? null : f.targetPerRep,
      teamTarget: f.teamTarget === "" ? null : f.teamTarget });
    try {
      if (isNew) await api.post("/api/v1/campaigns", body);
      else await api.patch(`/api/v1/campaigns/${campaign.id}`, body);
      toast(isNew ? "Campaign created" : "Campaign updated", "success");
      onSaved();
    } catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
  }

  const footer = (
    <div className="spread" style={{ width: "100%" }}>
      <div>
        {!isNew && (
          <button className="btn btn-ghost" disabled={busy} onClick={async () => {
            try { await api.patch(`/api/v1/campaigns/${campaign.id}`, { archived: !campaign.archived });
              toast(campaign.archived ? "Unarchived" : "Archived", "success"); onSaved(); }
            catch (e) { toast(e.message, "error"); }
          }}>{campaign.archived ? "Unarchive" : "Archive"}</button>
        )}
      </div>
      <div className="flex" style={{ gap: 8 }}>
        <button className="btn btn-outline" onClick={onClose} disabled={busy}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save campaign"}</button>
      </div>
    </div>
  );

  return (
    <Modal wide title={isNew ? "New campaign" : f.name || "Edit campaign"} onClose={onClose} footer={footer}>
      <Field label="Type">
        <div className="siq-seg" style={{ display: "inline-flex" }}>
          {["promotion", "incentive"].map((t) => (
            <button key={t} className={`siq-seg-btn${f.type === t ? " on" : ""}`}
              disabled={!isNew} onClick={() => set("type", t)}>{TYPE_LABEL[t]}</button>
          ))}
        </div>
        {!isNew && <span className="muted" style={{ fontSize: 11 }}> Type can't change after creation.</span>}
      </Field>

      <Field label="Name"><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)}
        placeholder={isPromo ? "e.g. Cloud Voice Spring Offer" : "e.g. Q2 Mobile Attach Bonus"} /></Field>

      <Field label="Description (internal)">
        <textarea className="input" rows={2} value={f.description || ""} onChange={(e) => set("description", e.target.value)} />
      </Field>

      <div className="flex" style={{ gap: 12 }}>
        <Field label="Starts"><GBDate value={f.startDate} onChange={(v) => set("startDate", v)} /></Field>
        <Field label="Ends"><GBDate value={f.endDate} onChange={(v) => set("endDate", v)} /></Field>
      </div>

      <Field label="Products" hint="What the campaign is about — drives detection in calls.">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
          {products.length === 0 && <span className="muted small">No products yet — add them in Settings → Products.</span>}
          {products.map((p) => (
            <button key={p.id} type="button" onClick={() => toggleProduct(p.id)}
              className={"siq-chip"} style={{ cursor: "pointer",
                background: f.productIds.includes(p.id) ? "var(--accent)" : undefined,
                color: f.productIds.includes(p.id) ? "#fff" : undefined }}>
              {p.name}
            </button>
          ))}
        </div>
      </Field>

      <Field label="Who it applies to" hint="Leave all unticked to target the whole company.">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
          {teams.map((t) => (
            <button key={t.id} type="button" onClick={() => toggleTeam(t.id)}
              className="siq-chip" style={{ cursor: "pointer",
                background: f.teams.includes(t.id) ? "var(--accent)" : undefined,
                color: f.teams.includes(t.id) ? "#fff" : undefined }}>
              {t.name}
            </button>
          ))}
        </div>
      </Field>

      {isPromo ? (
        <>
          <Field label="The offer (customer-facing)" hint="What reps should introduce on calls.">
            <textarea className="input" rows={2} value={f.offer || ""} onChange={(e) => set("offer", e.target.value)}
              placeholder="e.g. 3 months half-price on Cloud Voice for new 24-month terms" />
          </Field>
          <div className="flex" style={{ gap: 12 }}>
            <Field label="Customer segments">
              <input className="input" value={f.customerSegments || ""} onChange={(e) => set("customerSegments", e.target.value)}
                placeholder="e.g. SMEs on legacy ISDN" />
            </Field>
            <Field label="SOV weighting ×" hint="Optional extra weight in SOV.">
              <input className="input" type="number" step="0.1" value={f.sovMultiplier}
                onChange={(e) => set("sovMultiplier", e.target.value)} placeholder="1.0" />
            </Field>
          </div>
        </>
      ) : (
        <>
          <div className="siq-note" style={{ marginBottom: 12 }}>
            🔒 Incentive reward amounts are visible to managers/admin only — never shown to reps.
          </div>
          <div className="flex" style={{ gap: 12 }}>
            <Field label="Reward (£)"><input className="input" type="number" value={f.rewardAmount}
              onChange={(e) => set("rewardAmount", e.target.value)} placeholder="e.g. 50" /></Field>
            <Field label="Basis">
              <select className="input" value={f.rewardBasis} onChange={(e) => set("rewardBasis", e.target.value)}>
                {BASIS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
          </div>
          <Field label="What qualifies" hint="The rule reps' sales must meet to count.">
            <textarea className="input" rows={2} value={f.qualifyingRule || ""} onChange={(e) => set("qualifyingRule", e.target.value)}
              placeholder="e.g. Any Mobile connection added to a new or existing order" />
          </Field>
          <div className="flex" style={{ gap: 12 }}>
            <Field label="Target / rep"><input className="input" type="number" value={f.targetPerRep}
              onChange={(e) => set("targetPerRep", e.target.value)} placeholder="e.g. 10" /></Field>
            <Field label="Team target"><input className="input" type="number" value={f.teamTarget}
              onChange={(e) => set("teamTarget", e.target.value)} placeholder="e.g. 60" /></Field>
          </div>
        </>
      )}

      <Field label="Talking points (for reps)" hint="Coaching prompts surfaced to reps on relevant calls.">
        <textarea className="input" rows={3} value={f.talkingPoints || ""} onChange={(e) => set("talkingPoints", e.target.value)}
          placeholder={"One per line — e.g.\n• Lead with the saving, then the term\n• Ask about their current contract end date"} />
      </Field>
    </Modal>
  );
}

function Bar({ pct, color }) {
  return <div className="siq-bar" style={{ marginTop: 4 }}><div style={{ width: `${Math.min(100, pct || 0)}%`, background: color || "var(--accent)" }} /></div>;
}

function CampaignPerf({ campaign, onClose }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(false);
  const [co, setCo] = useState(null);
  const [coBusy, setCoBusy] = useState(false);
  useEffect(() => {
    api.get(`/api/v1/campaigns/${campaign.id}/performance`).then(setD).catch(() => setErr(true));
  }, [campaign.id]);

  const closeout = async () => {
    setCoBusy(true);
    try { setCo(await api.get(`/api/v1/campaigns/${campaign.id}/closeout`)); }
    catch (e) { setCo({ report: e.message || "Couldn't generate the report." }); }
    finally { setCoBusy(false); }
  };

  return (
    <Modal wide title={`📊 ${campaign.name}`} onClose={onClose}>
      <div className="spread" style={{ marginBottom: 10 }}>
        <span className="muted small">Adoption, reactions and rep breakdown below.</span>
        <button className="btn btn-outline btn-sm" onClick={closeout} disabled={coBusy}>
          {coBusy ? "Writing…" : "📝 AI close-out report"}
        </button>
      </div>
      {co && (
        <div className="siq-note" style={{ marginBottom: 12, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
          {co.report}
          {co.generatedAt && <div className="muted small" style={{ marginTop: 6 }}>
            {co.source === "ai" ? "AI-generated" : "From your data"} · {new Date(co.generatedAt).toLocaleString("en-GB")}
          </div>}
        </div>
      )}
      {err ? <EmptyState icon="📊" title="Couldn't load results" /> :
       !d ? <Skeleton h={260} /> : (() => {
        const t = d.totals || {};
        const reach = t.calls ? Math.round(100 * t.reach / t.calls) : 0;
        const adopt = d.adoptionRate ?? 0;
        const rx = d.reactions || {};
        const rxTotal = (rx.positive || 0) + (rx.neutral || 0) + (rx.objection || 0);
        return (
          <div>
            {t.calls === 0 && <EmptyState icon="⏳" title="No tracked calls yet"
              sub="Once calls land while this campaign is live, adoption and reactions appear here." />}
            {t.calls > 0 && <>
              <div className="siq-tiles" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
                <div className="card siq-tile"><div className="siq-tile-label">Calls in scope</div><div className="siq-tile-value">{t.calls}</div></div>
                <div className="card siq-tile"><div className="siq-tile-label">Introduced well</div>
                  <div className="siq-tile-value" style={{ color: "var(--green)" }}>{adopt}%</div>
                  <div className="siq-tile-sub">{t.addressed} calls</div></div>
                <div className="card siq-tile"><div className="siq-tile-label">Reached (incl. weak)</div>
                  <div className="siq-tile-value">{reach}%</div><div className="siq-tile-sub">{t.weak} weak</div></div>
                <div className="card siq-tile"><div className="siq-tile-label">Missed</div>
                  <div className="siq-tile-value" style={{ color: t.missed ? "var(--red)" : "var(--text)" }}>{t.missed}</div></div>
              </div>

              {d.quality && (d.quality.addressed != null || d.quality.missed != null) && (
                <div className="siq-note" style={{ marginTop: 12 }}>
                  Call quality when addressed: <b>{d.quality.addressed ?? "—"}/5</b> vs when missed: <b>{d.quality.missed ?? "—"}/5</b>
                  {d.quality.lift != null && <> · <span style={{ color: d.quality.lift >= 0 ? "var(--green)" : "var(--red)" }}>
                    {d.quality.lift >= 0 ? "+" : ""}{d.quality.lift} lift</span></>}
                </div>
              )}

              {rxTotal > 0 && (
                <div style={{ marginTop: 14 }}>
                  <div className="muted small" style={{ marginBottom: 4 }}>CUSTOMER REACTIONS (when raised)</div>
                  {[["Positive", rx.positive, "var(--green)"], ["Neutral", rx.neutral, "var(--amber)"], ["Objection", rx.objection, "var(--red)"]].map(([l, n, c]) => (
                    <div key={l} className="flex" style={{ gap: 8, alignItems: "center", marginBottom: 3 }}>
                      <span className="small" style={{ width: 70 }}>{l}</span>
                      <div style={{ flex: 1 }}><Bar pct={rxTotal ? 100 * (n || 0) / rxTotal : 0} color={c} /></div>
                      <span className="small muted" style={{ width: 24, textAlign: "right" }}>{n || 0}</span>
                    </div>
                  ))}
                </div>
              )}

              {d.incentive && (
                <div className="siq-note" style={{ marginTop: 14 }}>
                  🎯 <b>Incentive read</b> — qualifying product pitched on <b>{d.incentive.pitched}</b> calls
                  ({d.incentive.weakPitch} weak, {d.incentive.missed} missed) · {d.incentive.positiveReactions} positive
                  {d.incentive.likelyOrders ? <> · ~{d.incentive.likelyOrders} likely orders</> : null}
                  {d.incentive.rewardAmount != null && <div className="small muted" style={{ marginTop: 4 }}>
                    🔒 £{d.incentive.rewardAmount} {d.incentive.rewardBasis} · target/rep {d.incentive.targetPerRep ?? "—"} · team {d.incentive.teamTarget ?? "—"}</div>}
                </div>
              )}

              {d.leaderboard?.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="muted small" style={{ marginBottom: 6 }}>BY REP</div>
                  <table className="data siq-perf">
                    <thead><tr><th>Rep</th><th style={{ textAlign: "right" }}>Addressed</th><th style={{ textAlign: "right" }}>Weak</th><th style={{ textAlign: "right" }}>Missed</th><th style={{ textAlign: "right" }}>Rate</th></tr></thead>
                    <tbody>
                      {d.leaderboard.map((r) => (
                        <tr key={r.userId}>
                          <td>{r.name}</td>
                          <td style={{ textAlign: "right", color: "var(--green)" }}>{r.addressed}</td>
                          <td style={{ textAlign: "right" }} className="muted">{r.weak}</td>
                          <td style={{ textAlign: "right", color: r.missed ? "var(--red)" : "inherit" }}>{r.missed}</td>
                          <td style={{ textAlign: "right", fontWeight: 700, color: r.rate >= 60 ? "var(--green)" : r.rate >= 30 ? "var(--amber)" : "var(--red)" }}>{r.rate}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(d.snippets?.wins?.length > 0 || d.snippets?.misses?.length > 0) && (
                <div className="siq-grid2" style={{ marginTop: 16 }}>
                  <div>
                    <div className="muted small" style={{ marginBottom: 6 }}>🏅 STRONG INTRODUCTIONS</div>
                    {(d.snippets.wins || []).map((w, i) => (
                      <div key={i} className="siq-note" style={{ marginBottom: 6 }}>
                        <b>{w.rep || "Rep"}</b>: “{w.evidence}” {w.outcome ? <span className="muted">· {w.outcome}</span> : null}
                      </div>
                    ))}
                    {(!d.snippets.wins || d.snippets.wins.length === 0) && <div className="muted small">None yet.</div>}
                  </div>
                  <div>
                    <div className="muted small" style={{ marginBottom: 6 }}>⚠️ MISSED CHANCES</div>
                    {(d.snippets.misses || []).map((w, i) => (
                      <div key={i} className="siq-note" style={{ marginBottom: 6 }}>
                        <b>{w.rep || "Rep"}</b> didn’t raise it {w.callId ? <span className="muted">· call #{w.callId}</span> : null}
                      </div>
                    ))}
                    {(!d.snippets.misses || d.snippets.misses.length === 0) && <div className="muted small">None.</div>}
                  </div>
                </div>
              )}
            </>}
          </div>
        );
      })()}
    </Modal>
  );
}

function CampaignCard({ c, productNames, onEdit, onPerf }) {
  const st = STATUS_STYLE[c.status] || STATUS_STYLE.expired;
  const left = c.status === "live" ? daysLeft(c.endDate) : null;
  const prods = (c.productIds || []).map((id) => productNames[id]).filter(Boolean);
  return (
    <div className="card" style={{ marginBottom: 10, cursor: "pointer" }} onClick={() => onEdit(c)}>
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div>
          <div className="flex" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span className="siq-chip">{TYPE_LABEL[c.type]}</span>
            <strong style={{ fontSize: 15 }}>{c.name}</strong>
          </div>
          <div className="muted small" style={{ marginTop: 4 }}>
            {fmtRange(c.startDate, c.endDate)}
            {left != null && left >= 0 && <> · <span style={{ color: left <= 3 ? "var(--amber)" : "inherit" }}>{left}d left</span></>}
          </div>
          {prods.length > 0 && (
            <div className="flex" style={{ gap: 5, flexWrap: "wrap", marginTop: 6 }}>
              {prods.map((n) => <span key={n} className="siq-chip" style={{ fontSize: 11 }}>{n}</span>)}
            </div>
          )}
          {c.type === "promotion" && c.offer && <div className="small" style={{ marginTop: 6 }}>💬 {c.offer}</div>}
          {c.type === "incentive" && (c.rewardAmount != null) && (
            <div className="small" style={{ marginTop: 6 }}>🔒 {fmtGBP(c.rewardAmount)} {BASIS.find(([v]) => v === c.rewardBasis)?.[1] || c.rewardBasis}</div>
          )}
        </div>
        <div className="flex" style={{ gap: 8, alignItems: "center" }}>
          <button className="btn btn-outline btn-sm" onClick={(e) => { e.stopPropagation(); onPerf(c); }}>📊 Results</button>
          <span style={{ color: st.c, fontWeight: 700, fontSize: 13, whiteSpace: "nowrap" }}>{st.label}</span>
        </div>
      </div>
    </div>
  );
}

export default function CampaignsPanel() {
  const toast = useToast();
  const [campaigns, setCampaigns] = useState(null);
  const [products, setProducts] = useState([]);
  const [teams, setTeams] = useState([]);
  const [showEnded, setShowEnded] = useState(false);
  const [editing, setEditing] = useState(null);   // campaign object or {} for new
  const [perfFor, setPerfFor] = useState(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api.get("/api/v1/campaigns?include_archived=true").then((d) => setCampaigns(d.campaigns || [])).catch(() => setCampaigns([]));
    api.get("/api/v1/catalog/products").then((d) => setProducts(d.products || [])).catch(() => setProducts([]));
    api.get("/api/admin/teams").then((d) => setTeams(d || [])).catch(() => setTeams([]));
  }, [reload]);

  const productNames = useMemo(() => Object.fromEntries(products.map((p) => [p.id, p.name])), [products]);
  const refresh = () => { setEditing(null); setReload((k) => k + 1); };

  if (campaigns === null) return <div className="card" style={{ marginTop: 18 }}><Skeleton h={120} /></div>;

  const live = campaigns.filter((c) => c.status === "live");
  const scheduled = campaigns.filter((c) => c.status === "scheduled");
  const ended = campaigns.filter((c) => c.status === "expired" || c.status === "archived");

  return (
    <div className="card" style={{ marginTop: 18 }}>
      <div className="spread" style={{ marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
        <h2 className="card-title" style={{ margin: 0 }}>📣 Campaigns</h2>
        <div className="flex" style={{ gap: 8 }}>
          <button className="btn btn-outline" onClick={() => setShowEnded((v) => !v)}>
            {showEnded ? "Hide ended" : `Show ended (${ended.length})`}
          </button>
          <button className="btn btn-primary" onClick={() => setEditing({})}>+ New campaign</button>
        </div>
      </div>

      {live.length + scheduled.length === 0 && !showEnded ? (
        <EmptyState icon="📣" title="No live or upcoming campaigns"
          sub="Create a promotion or incentive — reps will see it on relevant calls and it'll be tracked automatically." />
      ) : (
        <>
          {live.length > 0 && <div className="muted small" style={{ margin: "4px 0 6px" }}>LIVE NOW</div>}
          {live.map((c) => <CampaignCard key={c.id} c={c} productNames={productNames} onEdit={setEditing} onPerf={setPerfFor} />)}
          {scheduled.length > 0 && <div className="muted small" style={{ margin: "10px 0 6px" }}>UPCOMING</div>}
          {scheduled.map((c) => <CampaignCard key={c.id} c={c} productNames={productNames} onEdit={setEditing} onPerf={setPerfFor} />)}
          {showEnded && ended.length > 0 && <div className="muted small" style={{ margin: "10px 0 6px" }}>ENDED / ARCHIVED</div>}
          {showEnded && ended.map((c) => <CampaignCard key={c.id} c={c} productNames={productNames} onEdit={setEditing} onPerf={setPerfFor} />)}
        </>
      )}

      {editing && (
        <CampaignModal campaign={editing.id ? editing : null} products={products} teams={teams}
          onClose={() => setEditing(null)} onSaved={refresh} />
      )}
      {perfFor && <CampaignPerf campaign={perfFor} onClose={() => setPerfFor(null)} />}
    </div>
  );
}
