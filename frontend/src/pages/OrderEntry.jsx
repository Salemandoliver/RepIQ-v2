import React, { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import api, { fetchBlobUrl } from "../api";
import { useToast } from "../components/Toast.jsx";
import { Modal, EmptyState, Skeleton, GBDate } from "../components/ui.jsx";

// Order Entry (brief §14) — RepIQ's replacement for the NetSuite Sales Order module + Excel trackers.
// Operations + admin create/edit; managers/reps see their scope. Runs alongside the live trackers.

const BADGE_COLOR = {
  "WITH BT": "var(--accent)", "PENDING BILLING": "var(--amber)", "FULLY BILLED": "#3b82f6",
  "PARTIALLY PAID": "#8b5cf6", PAID: "var(--green)", CANCELLED: "var(--text-faint)",
  "NON-COMMISSIONABLE": "var(--text-faint)", "PAYMENT ISSUE": "var(--red)",
};
const gbp = (n) => (n == null ? "—" : "£" + Math.round(n).toLocaleString("en-GB"));
const dmy = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "");

function Badge({ badge }) {
  const c = BADGE_COLOR[badge] || "var(--text-faint)";
  return <span className="siq-chip" style={{ color: c, borderColor: c, background: `color-mix(in srgb, ${c} 12%, transparent)`, fontWeight: 700, fontSize: 11 }}>{badge}</span>;
}

function Field({ label, children, w }) {
  return (
    <label className="field" style={{ margin: "0 0 10px", flex: w || "1 1 180px", minWidth: 140 }}>
      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-soft)" }}>{label}</span>
      {children}
    </label>
  );
}

// ---------------------------------------------------------------- line items tab
function ItemsTab({ order, meta, canWrite, onChange }) {
  const toast = useToast();
  const [draft, setDraft] = useState(null);
  const blank = { item: "", productId: "", contractValue: "", quantity: 1, gm: "", newRen: "new",
    schedule5Area: "", productGroup1: "", productGroup2: "", primarySplitPct: 100, secondSplitPct: 0,
    btCommissionPaid: false, schedule5Check: "" };

  const save = async () => {
    const b = { ...draft };
    try {
      if (draft.id) await api.patch(`/api/v1/orders/${order.id}/lines/${draft.id}`, b);
      else await api.post(`/api/v1/orders/${order.id}/lines`, b);
      setDraft(null); onChange();
    } catch (e) { toast(e.message, "error"); }
  };
  const del = async (lid) => { try { await api.delete(`/api/v1/orders/${order.id}/lines/${lid}`); onChange(); } catch (e) { toast(e.message, "error"); } };
  const pick = (pid) => {
    const p = meta.products.find((x) => x.id === pid);
    setDraft((d) => ({ ...d, productId: pid, item: p ? p.name : d.item,
      productGroup1: p?.group1 || d.productGroup1, productGroup2: p?.group2 || d.productGroup2,
      schedule5Area: p?.schedule5Area || d.schedule5Area }));
  };

  return (
    <div>
      <table className="data siq-perf" style={{ width: "100%" }}>
        <thead><tr><th>Item</th><th>Schedule 5</th><th className="num">Contract</th><th className="num">GM</th><th className="num">Qty</th><th>BT Paid</th>{canWrite && <th></th>}</tr></thead>
        <tbody>
          {(order.lines || []).map((l) => (
            <tr key={l.id}>
              <td>{l.item}</td><td className="muted">{l.schedule5Area || "—"}</td>
              <td className="num">{gbp(l.contractValue)}</td><td className="num">{gbp(l.gm)}</td>
              <td className="num">{l.quantity}</td>
              <td>{l.btCommissionPaid ? <span style={{ color: "var(--green)" }}>✓</span> : "—"}</td>
              {canWrite && <td><a className="hr-action" style={{ cursor: "pointer" }} onClick={() => setDraft({ ...blank, ...l })}>Edit</a> · <a className="hr-action" style={{ cursor: "pointer", color: "var(--red)" }} onClick={() => del(l.id)}>×</a></td>}
            </tr>
          ))}
          {(order.lines || []).length === 0 && <tr><td colSpan={7} className="muted small">No line items yet.</td></tr>}
        </tbody>
      </table>
      {canWrite && !draft && <button className="btn btn-outline btn-sm" style={{ marginTop: 8 }} onClick={() => setDraft({ ...blank })}>+ Add line</button>}
      {draft && (
        <div className="siq-note" style={{ marginTop: 10 }}>
          <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
            <Field label="Product" w="1 1 240px">
              <select className="input" value={draft.productId} onChange={(e) => pick(e.target.value)}>
                <option value="">— select / free text —</option>
                {meta.products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="Item name" w="1 1 240px"><input className="input" value={draft.item} onChange={(e) => setDraft({ ...draft, item: e.target.value })} /></Field>
            <Field label="Contract value (£)"><input className="input" type="number" value={draft.contractValue} onChange={(e) => setDraft({ ...draft, contractValue: e.target.value })} /></Field>
            <Field label="GM (£)"><input className="input" type="number" value={draft.gm} onChange={(e) => setDraft({ ...draft, gm: e.target.value })} /></Field>
            <Field label="Qty" w="0 0 70px"><input className="input" type="number" value={draft.quantity} onChange={(e) => setDraft({ ...draft, quantity: e.target.value })} /></Field>
            <Field label="New/Ren" w="0 0 110px">
              <select className="input" value={draft.newRen} onChange={(e) => setDraft({ ...draft, newRen: e.target.value })}><option value="new">New</option><option value="renewal">Renewal</option></select>
            </Field>
            <Field label="Schedule 5 check" w="1 1 170px">
              <select className="input" value={draft.schedule5Check || ""} onChange={(e) => setDraft({ ...draft, schedule5Check: e.target.value })}>
                <option value="">—</option>{(meta.schedule5Check || []).map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </select>
            </Field>
            <label className="flex" style={{ gap: 6, alignItems: "center", fontSize: 13 }}>
              <input type="checkbox" checked={!!draft.btCommissionPaid} onChange={(e) => setDraft({ ...draft, btCommissionPaid: e.target.checked })} /> BT Commission Paid
            </label>
          </div>
          <div className="flex" style={{ gap: 6, marginTop: 6 }}>
            <button className="btn btn-primary btn-sm" onClick={save}>Save line</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setDraft(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- sales team tab
function AgentsTab({ order, canWrite, onChange }) {
  const toast = useToast();
  const [rows, setRows] = useState(() => (order.agents || []).map((a) => ({ ...a })));
  const add = () => setRows([...rows, { name: "", salesRole: "first_sales_rep", isPrimary: rows.length === 0, contributionPct: 0 }]);
  const save = async () => {
    try { await api.put(`/api/v1/orders/${order.id}/agents`, { agents: rows }); onChange(); toast("Sales team saved", "success"); }
    catch (e) { toast(e.message, "error"); }
  };
  const upd = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div>
      <table className="data siq-perf" style={{ width: "100%" }}>
        <thead><tr><th>Agent</th><th>Role</th><th>Primary</th><th className="num">Contribution %</th><th className="num">£ (net)</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{canWrite ? <input className="input" value={r.name} onChange={(e) => upd(i, "name", e.target.value)} /> : r.name}</td>
              <td>{canWrite ? <select className="input" value={r.salesRole || ""} onChange={(e) => upd(i, "salesRole", e.target.value)}>
                {["first_sales_rep", "second_sales_rep", "closer", "admin_agent", "agent"].map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}
              </select> : r.salesRole}</td>
              <td><input type="checkbox" disabled={!canWrite} checked={!!r.isPrimary} onChange={(e) => upd(i, "isPrimary", e.target.checked)} /></td>
              <td className="num">{canWrite ? <input className="input" style={{ width: 80 }} type="number" value={r.contributionPct} onChange={(e) => upd(i, "contributionPct", e.target.value)} /> : `${r.contributionPct}%`}</td>
              <td className="num">{gbp(r.contributionAmount)}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={5} className="muted small">No agents on this order.</td></tr>}
        </tbody>
      </table>
      {canWrite && <div className="flex" style={{ gap: 6, marginTop: 8 }}>
        <button className="btn btn-outline btn-sm" onClick={add}>+ Add agent</button>
        <button className="btn btn-primary btn-sm" onClick={save}>Save sales team</button>
      </div>}
    </div>
  );
}

// ---------------------------------------------------------------- order form
function OrderForm({ id, meta, onClose, onSaved }) {
  const toast = useToast();
  const [o, setO] = useState(null);
  const [tab, setTab] = useState("summary");
  const canWrite = meta.canWrite;
  const isNew = id === "new";

  const load = () => {
    if (isNew) { setO({ status: "O", orderDate: new Date().toISOString().slice(0, 10), leAcquisitionStatus: "acquisition", lines: [], agents: [] }); return; }
    api.get(`/api/v1/orders/${id}`).then(setO).catch((e) => toast(e.message, "error"));
  };
  useEffect(load, [id]);
  const set = (k, v) => setO((p) => ({ ...p, [k]: v }));

  const saveHeader = async () => {
    const body = {
      orderDate: o.orderDate, companyName: o.companyName, leCode: o.leCode,
      leAcquisitionStatus: o.leAcquisitionStatus, oppId: o.oppId, mainOrderNumber: o.mainOrderNumber,
      volReference: o.volReference, orderNotes: o.orderNotes, status: o.status,
      commissionCrqRef: o.commissionCrqRef, reportingCrqRef: o.reportingCrqRef,
      orderCancelled: o.orderCancelled, cancellationReason: o.cancellationReason,
    };
    try {
      if (isNew) { const created = await api.post("/api/v1/orders", body); setO(created); onSaved(); toast(`Order ${created.orderNumber} created`, "success"); }
      else { const upd = await api.patch(`/api/v1/orders/${o.id}`, body); setO(upd); onSaved(); toast("Order saved", "success"); }
    } catch (e) { toast(e.message, "error"); }
  };
  const changeStatus = async (status) => {
    try { const upd = await api.post(`/api/v1/orders/${o.id}/status`, { status }); setO(upd); onSaved(); }
    catch (e) { toast(e.message, "error"); }
  };

  if (!o) return <Modal wide title="Order" onClose={onClose}><Skeleton h={200} /></Modal>;
  const title = isNew ? "New order" : `${o.orderNumber} · ${o.companyName || ""}`;
  const tabs = isNew ? [["summary", "Summary"]] : [["summary", "Summary"], ["items", "Items"], ["team", "Sales Team"]];

  return (
    <Modal wide title={title} onClose={onClose}>
      {!isNew && <div className="flex" style={{ gap: 10, alignItems: "center", marginBottom: 10 }}>
        <Badge badge={o.badge} />
        {canWrite && <select className="input" style={{ width: 240 }} value={o.status} onChange={(e) => changeStatus(e.target.value)}>
          {meta.statuses.map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}
        </select>}
        <span className="muted small">Total {gbp(o.total)} · {o.financialMonth ? `FY month ${dmy(o.financialMonth)}` : ""}{o.locked ? " · 🔒 locked" : ""}</span>
      </div>}

      <div className="tabs" style={{ marginBottom: 12 }}>
        {tabs.map(([k, l]) => <button key={k} className={`tab${tab === k ? " active" : ""}`} onClick={() => setTab(k)}>{l}</button>)}
      </div>

      {tab === "summary" && (
        <div>
          <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
            <Field label="Order date"><GBDate value={o.orderDate} onChange={(v) => set("orderDate", v)} /></Field>
            <Field label="Company name" w="1 1 240px"><input className="input" value={o.companyName || ""} onChange={(e) => set("companyName", e.target.value)} /></Field>
            <Field label="LE code"><input className="input" value={o.leCode || ""} onChange={(e) => set("leCode", e.target.value)} /></Field>
            <Field label="Acquisition"><select className="input" value={o.leAcquisitionStatus || "acquisition"} onChange={(e) => set("leAcquisitionStatus", e.target.value)}>{(meta.acquisition || []).map((a) => <option key={a} value={a}>{a}</option>)}</select></Field>
          </div>
          <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
            <Field label="OPP ID"><input className="input" value={o.oppId || ""} onChange={(e) => set("oppId", e.target.value)} /></Field>
            <Field label="Main order number"><input className="input" value={o.mainOrderNumber || ""} onChange={(e) => set("mainOrderNumber", e.target.value)} /></Field>
            <Field label="VOL reference"><input className="input" value={o.volReference || ""} onChange={(e) => set("volReference", e.target.value)} /></Field>
          </div>
          <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
            <Field label="Commission CRQ ref"><input className="input" value={o.commissionCrqRef || ""} onChange={(e) => set("commissionCrqRef", e.target.value)} /></Field>
            <Field label="Reporting CRQ ref"><input className="input" value={o.reportingCrqRef || ""} onChange={(e) => set("reportingCrqRef", e.target.value)} /></Field>
          </div>
          <Field label="Order notes" w="1 1 100%"><textarea className="input" rows={2} value={o.orderNotes || ""} onChange={(e) => set("orderNotes", e.target.value)} /></Field>
          <label className="flex" style={{ gap: 6, alignItems: "center", fontSize: 13, marginTop: 4 }}>
            <input type="checkbox" checked={!!o.orderCancelled} onChange={(e) => set("orderCancelled", e.target.checked)} /> Order cancelled
          </label>
          {o.orderCancelled && <Field label="Cancellation reason" w="1 1 100%"><input className="input" value={o.cancellationReason || ""} onChange={(e) => set("cancellationReason", e.target.value)} /></Field>}
          {canWrite && <button className="btn btn-primary" style={{ marginTop: 10 }} onClick={saveHeader} disabled={o.locked}>{isNew ? "Create order" : "Save"}</button>}
        </div>
      )}
      {tab === "items" && <ItemsTab order={o} meta={meta} canWrite={canWrite && !o.locked} onChange={load} />}
      {tab === "team" && <AgentsTab order={o} canWrite={canWrite && !o.locked} onChange={load} />}
    </Modal>
  );
}

// ---------------------------------------------------------------- import modal
function ImportModal({ onClose, onDone }) {
  const toast = useToast();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const send = async (path, then) => {
    if (!file) return toast("Choose an ERP Dump file first", "error");
    setBusy(true);
    const fd = new FormData(); fd.append("file", file);
    try { const r = await api.upload(`/api/v1/orders/import/${path}`, fd); then(r); }
    catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <Modal wide title="Import orders — NetSuite ERP Dump" onClose={onClose}>
      <div className="muted small" style={{ marginBottom: 8 }}>
        Upload the ERP Dump export (CSV or XLSX). Only the current financial year is imported (from 30 Mar);
        existing SO numbers are skipped. Runs alongside the live trackers.
      </div>
      <input type="file" accept=".csv,.xlsx,.xlsm" onChange={(e) => { setFile(e.target.files[0]); setPreview(null); }} />
      <div className="flex" style={{ gap: 8, marginTop: 10 }}>
        <button className="btn btn-outline" disabled={busy} onClick={() => send("analyze", setPreview)}>{busy ? "Reading…" : "Dry run"}</button>
        {preview && <button className="btn btn-primary" disabled={busy} onClick={() => send("commit", (r) => { toast(`Imported ${r.created} orders`, "success"); onDone(); })}>Commit import ({preview.new} new)</button>}
      </div>
      {preview && (
        <div className="siq-note" style={{ marginTop: 12 }}>
          <div><b>{preview.totalOrders}</b> orders in file · <b>{preview.new}</b> new · {preview.duplicates} already in RepIQ · {preview.skippedBeforeFY} skipped (before {dmy(preview.floor)})</div>
          {preview.unmatchedHeaders?.length > 0 && <div className="small" style={{ marginTop: 6, color: "var(--amber)" }}>Unmapped columns: {preview.unmatchedHeaders.join(", ")}</div>}
          <table className="data siq-perf" style={{ marginTop: 8 }}>
            <thead><tr><th>SO#</th><th>Date</th><th>Company</th><th>Status</th><th className="num">Lines</th><th>New?</th></tr></thead>
            <tbody>{(preview.preview || []).slice(0, 30).map((p, i) => (
              <tr key={i}><td>{p.so}</td><td>{dmy(p.date)}</td><td>{p.company}</td><td>{p.status}</td><td className="num">{p.lines}</td><td>{p.isNew ? "✓" : "dup"}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- page
export default function OrderEntry() {
  const { user } = useOutletContext() || {};
  const toast = useToast();
  const [meta, setMeta] = useState(null);
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);     // order id | "new"
  const [importing, setImporting] = useState(false);
  const [reload, setReload] = useState(0);
  const isAdmin = user?.role === "admin";

  useEffect(() => { api.get("/api/v1/orders/meta").then(setMeta).catch(() => setMeta({ canWrite: false, statuses: [], products: [] })); }, []);
  useEffect(() => {
    setData(null);
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    api.get(`/api/v1/orders?${params}`).then(setData).catch((e) => { toast(e.message, "error"); setData({ orders: [] }); });
  }, [status, q, reload]);

  const download = async (path, name) => {
    try { const url = await fetchBlobUrl(`/api/v1/orders/report/${path}`); const a = document.createElement("a"); a.href = url; a.download = name; a.click(); }
    catch (e) { toast(e.message, "error"); }
  };
  const bump = () => setReload((k) => k + 1);

  return (
    <div className="page" style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 22px 60px" }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26 }}>Order Entry</h1>
          <div className="muted small">{data ? `${data.total} orders` : "Sales orders, line items, status & commission"}</div>
        </div>
        <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-outline btn-sm" onClick={() => download("status-search", "order-status.csv")}>⤓ Status CSV</button>
          <button className="btn btn-outline btn-sm" onClick={() => download("erp-dump", "erp-dump.csv")}>⤓ ERP dump</button>
          {isAdmin && <button className="btn btn-outline" onClick={() => setImporting(true)}>⇪ Import</button>}
          {meta?.canWrite && <button className="btn btn-primary" onClick={() => setOpen("new")}>+ New order</button>}
        </div>
      </div>

      <div className="flex" style={{ gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <input className="input" placeholder="Search company / SO# / OPP / main order…" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "1 1 280px" }} />
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: 220 }}>
          <option value="">All statuses</option>
          {(meta?.statuses || []).map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}
        </select>
      </div>

      {!data ? <Skeleton h={300} /> : data.orders.length === 0 ? (
        <EmptyState icon="📦" title="No orders" sub={meta?.canWrite ? "Create one, or import the ERP dump." : "Orders you're on will appear here."} />
      ) : (
        <div className="card" style={{ overflowX: "auto" }}>
          <table className="data siq-perf" style={{ width: "100%" }}>
            <thead><tr><th>SO#</th><th>Date</th><th>Company</th><th>LE</th><th>OPP ID</th><th>Status</th><th className="num">Total</th></tr></thead>
            <tbody>
              {data.orders.map((o) => (
                <tr key={o.id} style={{ cursor: "pointer" }} onClick={() => setOpen(o.id)}>
                  <td><b>{o.orderNumber}</b></td><td>{dmy(o.orderDate)}</td><td>{o.companyName}</td>
                  <td className="muted">{o.leCode || "—"}</td><td className="muted">{o.oppId || "—"}</td>
                  <td><Badge badge={o.badge} /></td><td className="num">{gbp(o.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {open && meta && <OrderForm id={open} meta={meta} onClose={() => setOpen(null)} onSaved={bump} />}
      {importing && <ImportModal onClose={() => setImporting(false)} onDone={() => { setImporting(false); bump(); }} />}
    </div>
  );
}
