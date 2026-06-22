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
const ACQ_LABEL = { acquisition: "Acquisition", in_life: "In-Life", renewal: "In-Life" };
const gbp = (n) => (n == null ? "—" : "£" + Math.round(n).toLocaleString("en-GB"));
const dmy = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "");

function Badge({ badge }) {
  const c = BADGE_COLOR[badge] || "var(--text-faint)";
  return <span className="siq-chip" style={{ color: c, borderColor: c, background: `color-mix(in srgb, ${c} 12%, transparent)`, fontWeight: 700, fontSize: 11 }}>{badge}</span>;
}

function Placed({ placed }) {
  return placed
    ? <span style={{ color: "var(--green)", fontWeight: 700 }}>Y</span>
    : <span style={{ color: "var(--red)", fontWeight: 700 }}>N</span>;
}

function Field({ label, children, w }) {
  return (
    <label className="field" style={{ margin: "0 0 10px", flex: w || "1 1 180px", minWidth: 140 }}>
      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-soft)" }}>{label}</span>
      {children}
    </label>
  );
}

// Searchable Rate Card product picker — a real dropdown that lists matching products (the native
// <datalist> didn't reliably show the list across browsers).
function ItemPicker({ value, products, onPick, onText }) {
  const [open, setOpen] = useState(false);
  const q = (value || "").trim().toLowerCase();
  const matches = (q ? products.filter((p) => (p.name || "").toLowerCase().includes(q)) : products).slice(0, 80);
  return (
    <div style={{ position: "relative" }}>
      <input className="input" value={value} placeholder="Start typing a product…" autoComplete="off"
        onChange={(e) => { onText(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && products.length > 0 && (
        <div style={{ position: "absolute", zIndex: 60, top: "100%", left: 0, right: 0, marginTop: 2,
          maxHeight: 240, overflowY: "auto", background: "#fff", border: "1px solid var(--border)",
          borderRadius: 8, boxShadow: "0 10px 28px rgba(0,0,0,.18)" }}>
          {matches.length === 0 && <div className="muted" style={{ padding: "8px 10px", fontSize: 12 }}>No matching Rate Card product — this will be saved as free text.</div>}
          {matches.map((p) => (
            <div key={p.id} onMouseDown={() => { onPick(p); setOpen(false); }}
              style={{ padding: "7px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", gap: 8 }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#f3f5f8")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "#fff")}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</span>
              {p.category && <span className="muted" style={{ fontSize: 11, flexShrink: 0 }}>{p.category}</span>}
            </div>
          ))}
        </div>
      )}
      {open && products.length === 0 && (
        <div style={{ position: "absolute", zIndex: 60, top: "100%", left: 0, right: 0, marginTop: 2, background: "#fff",
          border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px", fontSize: 12 }} className="muted">
          No Rate Card loaded yet — an admin can upload it with the "↑ Rate card" button. You can still type a free-text item.
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- line items tab
function ItemsTab({ order, meta, canWrite, onChange }) {
  const toast = useToast();
  const [draft, setDraft] = useState(null);
  const blank = { item: "", productId: "", contractValue: "", quantity: 1, gm: "", newRen: "new",
    schedule5Area: "", productGroup1: "", productGroup2: "", primarySplitPct: 100, secondSplitPct: 0,
    btCommissionPaid: false, schedule5Check: "" };
  const products = meta.products || [];

  const save = async () => {
    const b = { ...draft };
    try {
      if (draft.id) await api.patch(`/api/v1/orders/${order.id}/lines/${draft.id}`, b);
      else await api.post(`/api/v1/orders/${order.id}/lines`, b);
      setDraft(null); onChange();
    } catch (e) { toast(e.message, "error"); }
  };
  const del = async (lid) => { try { await api.delete(`/api/v1/orders/${order.id}/lines/${lid}`); onChange(); } catch (e) { toast(e.message, "error"); } };

  // Typeahead over the imported Rate Card: pick a product to auto-fill its name + BT groups/schedule5.
  const onItem = (val) => {
    const p = products.find((x) => (x.name || "").toLowerCase() === val.toLowerCase());
    setDraft((d) => ({ ...d, item: val, productId: p ? p.id : "",
      productGroup1: p?.group1 ?? d.productGroup1, productGroup2: p?.group2 ?? d.productGroup2,
      schedule5Area: p?.schedule5Area ?? d.schedule5Area }));
  };

  return (
    <div>
      <div style={{ overflowX: "auto" }}>
      <table className="data siq-perf" style={{ width: "100%" }}>
        <thead><tr><th>Product</th><th>Sch5</th><th className="num">Contract</th><th className="num">GM</th><th className="num">Qty</th><th>BT&nbsp;Paid</th>{canWrite && <th></th>}</tr></thead>
        <tbody>
          {(order.lines || []).map((l) => (
            <tr key={l.id}>
              <td style={{ maxWidth: 300 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={l.item}>{l.item}</span>
                  {l.btCategory ? <span className="siq-chip" style={{ fontSize: 10, flexShrink: 0 }}>{l.btCategory}</span> : null}
                </div>
              </td>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>{l.schedule5Area || "—"}</td>
              <td className="num" style={{ whiteSpace: "nowrap" }}>{gbp(l.contractValue)}</td><td className="num" style={{ whiteSpace: "nowrap" }}>{gbp(l.gm)}</td>
              <td className="num">{l.quantity}</td>
              <td style={{ textAlign: "center" }}>{l.btCommissionPaid ? <span style={{ color: "var(--green)" }}>✓</span> : "—"}</td>
              {canWrite && <td style={{ whiteSpace: "nowrap" }}><a className="hr-action" style={{ cursor: "pointer" }} onClick={() => setDraft({ ...blank, ...l })}>Edit</a> · <a className="hr-action" style={{ cursor: "pointer", color: "var(--red)" }} onClick={() => del(l.id)}>×</a></td>}
            </tr>
          ))}
          {(order.lines || []).length === 0 && <tr><td colSpan={7} className="muted small">No products yet.</td></tr>}
        </tbody>
      </table>
      </div>
      {canWrite && !draft && <button className="btn btn-outline btn-sm" style={{ marginTop: 8 }} onClick={() => setDraft({ ...blank })}>+ Add line</button>}
      {draft && (
        <div className="siq-note" style={{ marginTop: 10 }}>
          <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
            <Field label={`Product — pick from Rate Card (${products.length} products)`} w="1 1 100%">
              <ItemPicker value={draft.item} products={products}
                onText={(v) => onItem(v)}
                onPick={(p) => setDraft((d) => ({ ...d, item: p.name, productId: p.id,
                  productGroup1: p.group1 ?? d.productGroup1, productGroup2: p.group2 ?? d.productGroup2,
                  schedule5Area: p.schedule5Area ?? d.schedule5Area }))} />
              <span className="muted" style={{ fontSize: 11 }}>
                {draft.productId ? "✓ matched a Rate Card product" : "free text (not on the Rate Card)"}
              </span>
            </Field>
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
function AgentsTab({ order, meta, canWrite, onChange }) {
  const toast = useToast();
  const [rows, setRows] = useState(() => (order.agents || []).map((a) => ({ ...a })));
  const people = meta.people || [];
  const add = () => setRows([...rows, { name: "", userId: null, salesRole: "first_sales_rep", isPrimary: rows.length === 0, contributionPct: 0 }]);
  const save = async () => {
    try { await api.put(`/api/v1/orders/${order.id}/agents`, { agents: rows }); onChange(); toast("Sales team saved", "success"); }
    catch (e) { toast(e.message, "error"); }
  };
  const upd = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  // Pick a person from the dropdown — no free-typing, so no name typos. Stores the user id + the
  // preferred name (e.g. Kunle, Patrick).
  const pickPerson = (i, uid) => {
    if (String(uid).startsWith("__keep_")) return;           // keep the imported name as-is
    const p = people.find((x) => String(x.id) === String(uid));
    setRows(rows.map((r, j) => (j === i ? { ...r, userId: p ? p.id : null, name: p ? p.name : "" } : r)));
  };
  return (
    <div>
      <table className="data siq-perf" style={{ width: "100%" }}>
        <thead><tr><th>Agent</th><th>Role</th><th>Primary</th><th className="num">Contribution %</th><th className="num">£ (net)</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{canWrite
                ? <select className="input" value={r.userId || (r.name ? `__keep_${r.name}` : "")} onChange={(e) => pickPerson(i, e.target.value)}>
                    <option value="">— select name —</option>
                    {!r.userId && r.name && <option value={`__keep_${r.name}`}>{r.name} (from import)</option>}
                    {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                : r.name}</td>
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

// ---------------------------------------------------------------- order form (single screen)
const SALES_ROLES = ["first_sales_rep", "second_sales_rep", "closer", "admin_agent", "agent"];

function OrderForm({ id, meta, onClose, onSaved }) {
  const toast = useToast();
  const [o, setO] = useState(null);
  const [lines, setLines] = useState([]);
  const [agents, setAgents] = useState([]);
  const [removedLines, setRemovedLines] = useState([]);
  const [createdId, setCreatedId] = useState(null);
  const [saving, setSaving] = useState(false);
  const canWrite = meta.canWrite;
  const isAdmin = !!meta.canDelete;       // Cobra GM (BT-paid GM) is admin-only
  const isNew = id === "new" && !createdId;
  const people = meta.people || [];
  const products = meta.products || [];

  const hydrate = (data) => {
    setO(data);
    setLines((data.lines || []).map((l) => ({ ...l })));
    setAgents((data.agents || []).map((a) => ({ ...a })));
    setRemovedLines([]);
  };
  const load = () => {
    const realId = createdId || (id !== "new" ? id : null);
    if (!realId) { hydrate({ status: "O", orderDate: new Date().toISOString().slice(0, 10), leAcquisitionStatus: "acquisition", placed: false, lines: [], agents: [] }); return; }
    api.get(`/api/v1/orders/${realId}`).then(hydrate).catch((e) => toast(e.message, "error"));
  };
  useEffect(load, [id, createdId]);
  const set = (k, v) => setO((p) => ({ ...p, [k]: v }));

  // ---- product lines ----
  const blankLine = { item: "", productId: "", contractValue: "", gm: "", cobraGm: "", quantity: 1, newRen: "new", schedule5Area: "", schedule5Check: "", btCommissionPaid: false, dateClosed: "" };
  const addLine = () => setLines([...lines, { ...blankLine }]);
  const updLine = (i, k, v) => setLines(lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const pickProduct = (i, p) => setLines(lines.map((l, j) => (j === i ? { ...l, item: p.name, productId: p.id, productGroup1: p.group1, productGroup2: p.group2, schedule5Area: p.schedule5Area || l.schedule5Area } : l)));
  const removeLine = (i) => { const l = lines[i]; if (l.id) setRemovedLines([...removedLines, l.id]); setLines(lines.filter((_, j) => j !== i)); };
  const gmTotal = lines.reduce((s, l) => s + Number(l.gm || 0), 0);

  // ---- sales team ----
  const addAgent = () => setAgents([...agents, { userId: null, name: "", salesRole: agents.length ? "second_sales_rep" : "first_sales_rep", isPrimary: agents.length === 0, contributionPct: agents.length === 0 ? 100 : 0 }]);
  const updAgent = (i, k, v) => setAgents(agents.map((a, j) => (j === i ? { ...a, [k]: v } : a)));
  const pickAgent = (i, uid) => { if (String(uid).startsWith("__keep_")) return; const p = people.find((x) => String(x.id) === String(uid)); setAgents(agents.map((a, j) => (j === i ? { ...a, userId: p ? p.id : null, name: p ? p.name : "" } : a))); };
  const setPrimary = (i) => setAgents(agents.map((a, j) => ({ ...a, isPrimary: j === i })));
  const removeAgent = (i) => setAgents(agents.filter((_, j) => j !== i));
  const contribTotal = agents.reduce((s, a) => s + Number(a.contributionPct || 0), 0);

  const headerBody = () => ({
    orderDate: o.orderDate, companyName: o.companyName, leCode: o.leCode,
    leAcquisitionStatus: o.leAcquisitionStatus, oppId: o.oppId, mainOrderNumber: o.mainOrderNumber,
    volReference: o.volReference, orderNotes: o.orderNotes, status: o.status,
    commissionCrqRef: o.commissionCrqRef, reportingCrqRef: o.reportingCrqRef,
    orderCancelled: o.orderCancelled, cancellationReason: o.cancellationReason,
    placed: !!o.placed, weekNumber: o.weekNumber,
  });

  // One Save persists the whole order — header + products + sales team (NetSuite-style).
  const saveAll = async () => {
    if (!(o.companyName || o.leCode)) return toast("Add a company name or LE code first", "error");
    setSaving(true);
    try {
      let orderId;
      let createdNumber = o.orderNumber;
      if (isNew) { const created = await api.post("/api/v1/orders", headerBody()); orderId = created.id; createdNumber = created.orderNumber; }
      else { await api.patch(`/api/v1/orders/${o.id}`, headerBody()); orderId = o.id; }

      for (const lid of removedLines) await api.delete(`/api/v1/orders/${orderId}/lines/${lid}`);
      for (const l of lines) {
        if (!(l.item || l.gm || l.contractValue)) continue;     // skip blank rows
        const lb = {
          item: l.item || "", productId: l.productId || "",
          contractValue: Number(l.contractValue || 0), gm: Number(l.gm || 0),
          cobraGm: (l.cobraGm === "" || l.cobraGm == null) ? null : Number(l.cobraGm),
          quantity: Number(l.quantity || 1), newRen: l.newRen || "new",
          schedule5Area: l.schedule5Area || "", schedule5Check: l.schedule5Check || "",
          btCommissionPaid: !!l.btCommissionPaid, dateClosed: l.dateClosed || "",
        };
        if (l.id) await api.patch(`/api/v1/orders/${orderId}/lines/${l.id}`, lb);
        else await api.post(`/api/v1/orders/${orderId}/lines`, lb);
      }
      await api.put(`/api/v1/orders/${orderId}/agents`, { agents: agents.filter((a) => a.userId || a.name).map((a) => ({
        userId: a.userId, name: a.name, salesRole: a.salesRole, isPrimary: !!a.isPrimary, contributionPct: Number(a.contributionPct || 0),
      })) });

      onSaved(); toast(isNew ? `Order ${createdNumber} created` : "Order saved", "success");
      if (isNew) setCreatedId(orderId); else load();
    } catch (e) { toast(e.message, "error"); } finally { setSaving(false); }
  };

  if (!o) return <Modal xl title="Order" onClose={onClose}><Skeleton h={200} /></Modal>;
  const title = isNew ? "New order" : `${o.orderNumber} · ${o.companyName || ""}`;
  const colSpan = isAdmin ? 11 : 10;

  return (
    <Modal xl title={title} onClose={onClose}>
      {!isNew && <div className="flex" style={{ gap: 10, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
        <Badge badge={o.badge} />
        <span className="siq-chip" style={{ fontWeight: 700, color: o.placed ? "var(--green)" : "var(--red)", borderColor: o.placed ? "var(--green)" : "var(--red)" }}>{o.placed ? "PLACED" : "NOT PLACED"}</span>
        <span className="muted small">Total {gbp(o.total)} · {o.weekLabel || ""}{o.locked ? " · 🔒 locked" : ""}</span>
        {o.categories && <span className="muted small">· BT split — Data {gbp(o.categories.Data)} · Cloud {gbp(o.categories.Cloud)} · Mobile {gbp(o.categories.Mobile)}</span>}
      </div>}

      {/* ===== Order details ===== */}
      <div className="oe-sec" style={{ marginTop: 4 }}>Order details</div>
      {canWrite && (
        <label className="flex" style={{ gap: 8, alignItems: "center", marginBottom: 12, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: o.placed ? "color-mix(in srgb, var(--green) 8%, transparent)" : "color-mix(in srgb, var(--red) 6%, transparent)" }}>
          <input type="checkbox" checked={!!o.placed} onChange={(e) => set("placed", e.target.checked)} />
          <span style={{ fontWeight: 700 }}>Order Placed in BT systems</span>
          <span className="muted small">— tick once it's been placed in BT; leave unticked if it's missing details or waiting.</span>
        </label>
      )}
      <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
        <Field label="Order date" w="0 0 150px"><GBDate value={o.orderDate} onChange={(v) => set("orderDate", v)} /></Field>
        <Field label="Week #" w="0 0 120px">
          <input className="input" type="number" value={o.weekNumber ?? ""} placeholder="auto" onChange={(e) => set("weekNumber", e.target.value)} />
          <span className="muted" style={{ fontSize: 11 }}>{o.weekLabel || "auto from date"}</span>
        </Field>
        <Field label="Order status" w="0 0 220px">
          <select className="input" value={o.status || "O"} onChange={(e) => set("status", e.target.value)}>
            {meta.statuses.map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}
          </select>
        </Field>
        <Field label="Company name" w="1 1 240px"><input className="input" value={o.companyName || ""} onChange={(e) => set("companyName", e.target.value)} /></Field>
        <Field label="LE code" w="0 0 150px"><input className="input" value={o.leCode || ""} onChange={(e) => set("leCode", e.target.value)} /></Field>
        <Field label="LE acquisition status" w="0 0 170px">
          <select className="input" value={o.leAcquisitionStatus || "acquisition"} onChange={(e) => set("leAcquisitionStatus", e.target.value)}>
            {(meta.acquisition || []).map((a) => <option key={a} value={a}>{ACQ_LABEL[a] || a}</option>)}
          </select>
        </Field>
        <Field label="OPP ID" w="0 0 160px"><input className="input" value={o.oppId || ""} onChange={(e) => set("oppId", e.target.value)} /></Field>
        <Field label="Main order number" w="0 0 180px"><input className="input" value={o.mainOrderNumber || ""} onChange={(e) => set("mainOrderNumber", e.target.value)} /></Field>
        <Field label="VOL reference" w="0 0 150px"><input className="input" value={o.volReference || ""} onChange={(e) => set("volReference", e.target.value)} /></Field>
        <Field label="Commission CRQ ref" w="0 0 170px"><input className="input" value={o.commissionCrqRef || ""} onChange={(e) => set("commissionCrqRef", e.target.value)} /></Field>
        <Field label="Reporting CRQ ref" w="0 0 170px"><input className="input" value={o.reportingCrqRef || ""} onChange={(e) => set("reportingCrqRef", e.target.value)} /></Field>
      </div>
      <Field label="Order notes" w="1 1 100%"><textarea className="input" rows={2} value={o.orderNotes || ""} onChange={(e) => set("orderNotes", e.target.value)} /></Field>
      <label className="flex" style={{ gap: 6, alignItems: "center", fontSize: 13 }}>
        <input type="checkbox" checked={!!o.orderCancelled} onChange={(e) => set("orderCancelled", e.target.checked)} /> Order cancelled
      </label>
      {o.orderCancelled && <Field label="Cancellation reason" w="1 1 100%"><input className="input" value={o.cancellationReason || ""} onChange={(e) => set("cancellationReason", e.target.value)} /></Field>}

      {/* ===== Products ===== */}
      <div className="oe-sec">Products <span className="muted small" style={{ fontWeight: 400 }}>· order GM total {gbp(gmTotal)}</span></div>
      <div style={{ overflowX: "auto" }}>
        <table className="oe-grid">
          <thead><tr>
            <th style={{ minWidth: 240 }}>Product</th><th className="num">Contract £</th><th className="num">GM £</th>
            {isAdmin && <th className="num" title="What BT actually paid us — drives commission">Cobra GM £</th>}
            <th className="num">Qty</th><th>New/Ren</th><th>Sch5 Area</th><th>Sch5 Check</th><th>BT&nbsp;Paid</th><th>Date closed</th><th></th>
          </tr></thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={l.id || `n${i}`}>
                <td><ItemPicker value={l.item} products={products} onText={(v) => updLine(i, "item", v)} onPick={(p) => pickProduct(i, p)} /></td>
                <td><input className="input" type="number" style={{ width: 92 }} value={l.contractValue ?? ""} onChange={(e) => updLine(i, "contractValue", e.target.value)} /></td>
                <td><input className="input" type="number" style={{ width: 84 }} value={l.gm ?? ""} onChange={(e) => updLine(i, "gm", e.target.value)} /></td>
                {isAdmin && <td><input className="input" type="number" style={{ width: 92, background: l.btCommissionPaid ? "color-mix(in srgb, var(--green) 8%, transparent)" : undefined }} value={l.cobraGm ?? ""} placeholder={l.btCommissionPaid ? "BT paid" : "—"} onChange={(e) => updLine(i, "cobraGm", e.target.value)} /></td>}
                <td><input className="input" type="number" style={{ width: 52 }} value={l.quantity ?? 1} onChange={(e) => updLine(i, "quantity", e.target.value)} /></td>
                <td><select className="input" value={l.newRen || "new"} onChange={(e) => updLine(i, "newRen", e.target.value)}><option value="new">New</option><option value="renewal">Renewal</option></select></td>
                <td><input className="input" style={{ width: 110 }} value={l.schedule5Area || ""} onChange={(e) => updLine(i, "schedule5Area", e.target.value)} /></td>
                <td><select className="input" value={l.schedule5Check || ""} onChange={(e) => updLine(i, "schedule5Check", e.target.value)}><option value="">—</option>{(meta.schedule5Check || []).map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select></td>
                <td style={{ textAlign: "center" }}><input type="checkbox" checked={!!l.btCommissionPaid} onChange={(e) => updLine(i, "btCommissionPaid", e.target.checked)} /></td>
                <td><GBDate value={l.dateClosed || ""} onChange={(v) => updLine(i, "dateClosed", v)} /></td>
                <td>{canWrite && <a className="hr-action" style={{ color: "var(--red)", cursor: "pointer", fontWeight: 700 }} onClick={() => removeLine(i)}>×</a>}</td>
              </tr>
            ))}
            {lines.length === 0 && <tr><td colSpan={colSpan} className="muted small">No products yet.</td></tr>}
          </tbody>
        </table>
      </div>
      {canWrite && <button className="btn btn-outline btn-sm" style={{ marginTop: 8 }} onClick={addLine}>+ Add product</button>}
      {isAdmin && <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>Cobra GM = what BT actually paid us (admin only). Commission runs pay on this when set.</div>}

      {/* ===== Sales team ===== */}
      <div className="oe-sec">Sales team</div>
      <table className="oe-grid">
        <thead><tr><th style={{ minWidth: 220 }}>Name</th><th>Role</th><th>Primary</th><th className="num">Contribution %</th><th></th></tr></thead>
        <tbody>
          {agents.map((a, i) => (
            <tr key={i}>
              <td><select className="input" value={a.userId || (a.name ? `__keep_${a.name}` : "")} onChange={(e) => pickAgent(i, e.target.value)}>
                <option value="">— select name —</option>
                {!a.userId && a.name && <option value={`__keep_${a.name}`}>{a.name} (imported)</option>}
                {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select></td>
              <td><select className="input" value={a.salesRole || ""} onChange={(e) => updAgent(i, "salesRole", e.target.value)}>{SALES_ROLES.map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}</select></td>
              <td style={{ textAlign: "center" }}><input type="radio" checked={!!a.isPrimary} onChange={() => setPrimary(i)} /></td>
              <td><input className="input" type="number" style={{ width: 80 }} value={a.contributionPct ?? 0} onChange={(e) => updAgent(i, "contributionPct", e.target.value)} /></td>
              <td>{canWrite && <a className="hr-action" style={{ color: "var(--red)", cursor: "pointer", fontWeight: 700 }} onClick={() => removeAgent(i)}>×</a>}</td>
            </tr>
          ))}
          {agents.length === 0 && <tr><td colSpan={5} className="muted small">No sales reps on this order yet.</td></tr>}
        </tbody>
      </table>
      {canWrite && <div className="flex" style={{ gap: 10, alignItems: "center", marginTop: 8 }}>
        <button className="btn btn-outline btn-sm" onClick={addAgent}>+ Add sales rep / BC</button>
        <span className="muted small" style={{ color: agents.length && contribTotal !== 100 ? "var(--amber)" : "var(--text-soft)" }}>
          Total contribution: {contribTotal}%{agents.length > 0 && contribTotal !== 100 ? " (should be 100%)" : ""}
        </span>
      </div>}

      {/* ===== Sticky save bar ===== */}
      {canWrite && (
        <div style={{ position: "sticky", bottom: -22, background: "#fff", paddingTop: 12, paddingBottom: 4, marginTop: 18, borderTop: "1px solid var(--border)", display: "flex", gap: 10, justifyContent: "flex-end", alignItems: "center" }}>
          {o.locked && <span className="muted small" style={{ marginRight: "auto", color: "var(--amber)" }}>🔒 Commission month locked — admin override only</span>}
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
          <button className="btn btn-primary" disabled={saving || o.locked} onClick={saveAll}>{saving ? "Saving…" : isNew ? "Create order" : "Save order"}</button>
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- import modal
function ImportModal({ onClose, onDone }) {
  const toast = useToast();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [replace, setReplace] = useState(false);
  const [job, setJob] = useState(null);          // live import progress
  const send = async (path, then) => {
    if (!file) return toast("Choose an ERP Dump file first", "error");
    setBusy(true);
    const fd = new FormData(); fd.append("file", file);
    try { const r = await api.upload(`/api/v1/orders/import/${path}`, fd); then(r); }
    catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  // Run the import as a background job and poll its progress (so a big replace can't time out).
  const commit = async () => {
    if (!file) return toast("Choose an ERP Dump file first", "error");
    setBusy(true);
    setJob({ status: "starting", done: 0, total: preview?.totalOrders || 0, deleted: 0 });
    const fd = new FormData(); fd.append("file", file);
    let jobId;
    try { jobId = (await api.upload(`/api/v1/orders/import/start?replace=${replace}`, fd)).jobId; }
    catch (e) { toast(e.message, "error"); setBusy(false); setJob(null); return; }
    let misses = 0;
    const poll = async () => {
      try {
        const p = await api.get(`/api/v1/orders/import/progress/${jobId}`);
        setJob(p);
        if (p.status === "done") {
          toast(replace ? `Replaced — deleted ${p.deleted}, imported ${p.created}` : `Imported ${p.created} orders`, "success");
          setBusy(false); onDone(); return;
        }
        if (p.status === "error") { toast(p.error || "Import failed", "error"); setBusy(false); return; }
        setTimeout(poll, 800);
      } catch (e) {
        if (++misses > 5) { toast("Lost track of the import — check the list to confirm.", "error"); setBusy(false); return; }
        setTimeout(poll, 1200);
      }
    };
    setTimeout(poll, 600);
  };
  return (
    <Modal wide title="Import orders — NetSuite ERP Dump" onClose={onClose}>
      <div className="muted small" style={{ marginBottom: 8 }}>
        Upload the ERP Dump export (CSV or XLSX). Only the current financial year is imported (from 30 Mar).
        Imported orders are marked <b>Placed</b> and stamped with their BT week number; you can change Order
        Placed manually afterwards.
      </div>
      <input type="file" accept=".csv,.xlsx,.xlsm" onChange={(e) => { setFile(e.target.files[0]); setPreview(null); }} />
      <label className="flex" style={{ gap: 8, alignItems: "center", marginTop: 10, padding: "8px 12px",
        border: "1px solid var(--border)", borderRadius: 8, background: replace ? "color-mix(in srgb, var(--red) 7%, transparent)" : "transparent" }}>
        <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
        <span><b>Fully replace existing data</b> — delete all previously-imported orders first, then load this file as the source of truth. <span className="muted">(Manually-created orders are kept.)</span></span>
      </label>
      <div className="flex" style={{ gap: 8, marginTop: 10 }}>
        <button className="btn btn-outline" disabled={busy} onClick={() => send("analyze", setPreview)}>{busy ? "Reading…" : "Dry run"}</button>
        {preview && <button className={`btn ${replace ? "btn-danger" : "btn-primary"}`} disabled={busy} onClick={commit}>
          {busy ? "Working…" : replace ? `Replace all — import ${preview.totalOrders} orders` : `Commit import (${preview.new} new)`}
        </button>}
      </div>
      {preview && replace && !job && <div className="small" style={{ marginTop: 8, color: "var(--red)" }}>
        Replace mode: every previously-imported order will be deleted, then all {preview.totalOrders} orders in this file imported fresh.
      </div>}
      {job && (() => {
        const pct = job.total ? Math.min(100, Math.round((100 * (job.done || 0)) / job.total)) : (job.status === "done" ? 100 : 0);
        const label = job.status === "starting" ? "Starting…"
          : job.status === "deleting" ? `Deleting old orders…`
          : job.status === "done" ? `Done — imported ${job.created}${job.deleted ? `, deleted ${job.deleted}` : ""}`
          : job.status === "error" ? "Failed"
          : `Importing… ${job.done || 0} of ${job.total}${job.deleted ? ` · deleted ${job.deleted}` : ""}`;
        return (
          <div style={{ marginTop: 14 }}>
            <div className="small" style={{ marginBottom: 4, color: job.status === "error" ? "var(--red)" : "var(--text-soft)" }}>{label}</div>
            <div style={{ height: 12, background: "var(--border)", borderRadius: 6, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${pct}%`,
                background: job.status === "error" ? "var(--red)" : job.status === "done" ? "var(--green)" : "var(--accent)",
                transition: "width .3s ease" }} />
            </div>
            {job.status === "error" && job.error && <div className="small" style={{ marginTop: 6, color: "var(--red)" }}>{job.error}</div>}
          </div>
        );
      })()}
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
  const [period, setPeriod] = useState("month");   // all | week | month | quarter
  const [periodVal, setPeriodVal] = useState("");  // week "num:weekYear" · month "YYYY-MM" · quarter "YYYY-Qn"
  const [placedF, setPlacedF] = useState("");      // "" | "true" | "false"
  const [open, setOpen] = useState(null);          // order id | "new"
  const [importing, setImporting] = useState(false);
  const [reload, setReload] = useState(0);
  const [sort, setSort] = useState({ key: "orderDate", dir: "desc" });
  const isAdmin = user?.role === "admin";

  const sorted = useMemo(() => {
    const rows = [...(data?.orders || [])];
    const { key, dir } = sort;
    rows.sort((a, b) => {
      let av = a[key], bv = b[key];
      if (key === "total" || key === "weekNumber") { av = av ?? 0; bv = bv ?? 0; }
      else { av = (av ?? "").toString().toLowerCase(); bv = (bv ?? "").toString().toLowerCase(); }
      if (av < bv) return dir === "asc" ? -1 : 1;
      if (av > bv) return dir === "asc" ? 1 : -1;
      return 0;
    });
    return rows;
  }, [data, sort]);
  const toggleSort = (key) => setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }));

  // Load meta, then default the list to the CURRENT sales month.
  useEffect(() => {
    api.get("/api/v1/orders/meta").then((m) => {
      setMeta(m);
      setPeriodVal(m.currentMonth || "");
    }).catch(() => setMeta({ canWrite: false, statuses: [], products: [], people: [], weeks: [], months: [], quarters: [] }));
  }, []);

  useEffect(() => {
    if (!meta) return;
    setData(null);
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    if (placedF) params.set("placed", placedF);
    if (period !== "all" && periodVal) {
      params.set("period", period);
      if (period === "week") {
        const [num, wy] = periodVal.split(":");
        params.set("week", num); if (wy) params.set("week_year", wy);
      } else if (period === "month") { params.set("month", periodVal); }
      else if (period === "quarter") { params.set("quarter", periodVal); }
    }
    params.set("limit", "500");
    api.get(`/api/v1/orders?${params}`).then(setData).catch((e) => { toast(e.message, "error"); setData({ orders: [] }); });
  }, [status, q, period, periodVal, placedF, reload, meta]);

  // When switching the period TYPE, default its value sensibly.
  const changePeriod = (p) => {
    setPeriod(p);
    if (p === "month") setPeriodVal(meta?.currentMonth || "");
    else if (p === "quarter") setPeriodVal(meta?.currentQuarter || (meta?.quarters?.[0]?.value || ""));
    else if (p === "week") {
      const cw = meta?.currentWeek;
      setPeriodVal(cw ? `${cw.number}:${cw.weekYear}` : (meta?.weeks?.[0] ? `${meta.weeks[0].number}:${meta.weeks[0].weekYear}` : ""));
    } else setPeriodVal("");
  };

  const download = async (path, name) => {
    try { const url = await fetchBlobUrl(`/api/v1/orders/report/${path}`); const a = document.createElement("a"); a.href = url; a.download = name; a.click(); }
    catch (e) { toast(e.message, "error"); }
  };
  const bump = () => setReload((k) => k + 1);

  const uploadRateCard = () => {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = ".xlsx,.xlsm";
    inp.onchange = async () => {
      if (!inp.files[0]) return;
      const fd = new FormData(); fd.append("file", inp.files[0]);
      try {
        const r = await api.upload("/api/v1/orders/import/rate-card", fd);
        toast(`Rate card loaded — ${r.products} BT products`, "success");
        api.get("/api/v1/orders/meta").then(setMeta).catch(() => {});
      } catch (e) { toast(e.message, "error"); }
    };
    inp.click();
  };

  return (
    <div className="page" style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 22px 60px" }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26 }}>Order Entry</h1>
          <div className="muted small">{data ? `${data.total} orders` : "Sales orders, products, status & commission"}</div>
        </div>
        <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-outline btn-sm" onClick={() => download("status-search", "order-status.csv")}>⤓ Status CSV</button>
          <button className="btn btn-outline btn-sm" onClick={() => download("erp-dump", "erp-dump.csv")}>⤓ ERP dump</button>
          {meta?.canWrite && <button className="btn btn-outline btn-sm" onClick={uploadRateCard}>↑ Rate card</button>}
          {meta?.canWrite && <button className="btn btn-outline" onClick={() => setImporting(true)}>⇪ Import</button>}
          {meta?.canWrite && <button className="btn btn-primary" onClick={() => setOpen("new")}>+ New order</button>}
        </div>
      </div>

      <div className="flex" style={{ gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <input className="input" placeholder="Search company / SO# / OPP / main order…" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "1 1 240px" }} />
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: 180 }}>
          <option value="">All statuses</option>
          {(meta?.statuses || []).map((s) => <option key={s.code} value={s.code}>{s.label}</option>)}
        </select>
        {/* Period filter — view a specific BT week, sales month, or quarter (defaults to this month). */}
        <select className="input" value={period} onChange={(e) => changePeriod(e.target.value)} style={{ width: 120 }}>
          <option value="week">By week</option>
          <option value="month">By month</option>
          <option value="quarter">By quarter</option>
          <option value="all">All time</option>
        </select>
        {period === "week" && (
          <select className="input" value={periodVal} onChange={(e) => setPeriodVal(e.target.value)} style={{ width: 210 }}>
            {(meta?.weeks || []).map((w) => <option key={`${w.number}:${w.weekYear}`} value={`${w.number}:${w.weekYear}`}>{w.label}</option>)}
          </select>
        )}
        {period === "month" && (
          <select className="input" value={periodVal} onChange={(e) => setPeriodVal(e.target.value)} style={{ width: 160 }}>
            {(meta?.months || []).map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        )}
        {period === "quarter" && (
          <select className="input" value={periodVal} onChange={(e) => setPeriodVal(e.target.value)} style={{ width: 140 }}>
            {(meta?.quarters || []).map((qq) => <option key={qq.value} value={qq.value}>{qq.label}</option>)}
          </select>
        )}
        <select className="input" value={placedF} onChange={(e) => setPlacedF(e.target.value)} style={{ width: 150 }}>
          <option value="">Placed: all</option>
          <option value="true">Placed only</option>
          <option value="false">Not placed</option>
        </select>
      </div>

      {!data ? <Skeleton h={300} /> : data.orders.length === 0 ? (
        <EmptyState icon="📦" title="No orders for this view" sub={meta?.canWrite ? "Try a different week/month, or create / import an order." : "Orders you're on will appear here."} />
      ) : (
        <div className="card" style={{ overflowX: "auto" }}>
          <table className="data" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {[["orderNumber", "SO#"], ["orderDate", "Date"], ["weekNumber", "Wk"], ["companyName", "Company"],
                  ["item", "Product"], ["leCode", "LE"], ["oppId", "OPP ID"], ["placed", "Placed"], ["status", "Status"], ["total", "Total", true]]
                  .map(([key, label, right]) => (
                    <th key={key} onClick={() => toggleSort(key)}
                      style={{ cursor: "pointer", textAlign: right ? "right" : "left", whiteSpace: "nowrap",
                        userSelect: "none", padding: "8px 10px", color: "var(--text-soft)", fontWeight: 600 }}>
                      {label}{sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : ""}
                    </th>
                  ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((o) => (
                <tr key={o.id} style={{ cursor: "pointer", borderTop: "1px solid var(--border)" }} onClick={() => setOpen(o.id)}>
                  <td style={{ padding: "8px 10px" }}><b>{o.orderNumber}</b></td>
                  <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>{dmy(o.orderDate)}</td>
                  <td style={{ padding: "8px 10px" }} className="muted" title={o.weekLabel || ""}>{o.weekNumber ?? "—"}</td>
                  <td style={{ padding: "8px 10px" }}>{o.companyName}</td>
                  <td style={{ padding: "8px 10px", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    className="muted" title={o.item || ""}>
                    {o.item || "—"}{o.itemCount > 1 ? <span style={{ color: "var(--text-faint)" }}> +{o.itemCount - 1}</span> : ""}
                  </td>
                  <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }} className="muted">{o.leCode || "—"}</td>
                  <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }} className="muted">{o.oppId || "—"}</td>
                  <td style={{ padding: "8px 10px", textAlign: "center" }}><Placed placed={o.placed} /></td>
                  <td style={{ padding: "8px 10px" }}><Badge badge={o.badge} /></td>
                  <td style={{ padding: "8px 10px", textAlign: "right", whiteSpace: "nowrap" }}>{gbp(o.total)}</td>
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
