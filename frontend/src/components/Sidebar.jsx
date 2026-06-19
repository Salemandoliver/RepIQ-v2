import React, { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Avatar } from "./ui.jsx";
import api, { clearAuth } from "../api";
import {
  HomeIcon,
  PlayCircleIcon,
  InsightsIcon,
  CoachingIcon,
  PlaylistIcon,
  ReportsIcon,
  SettingsIcon,
  LogoutIcon,
  BuildingIcon,
  TrendingUpIcon,
} from "./Icons.jsx";

export default function Sidebar({ user }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [companyLogo, setCompanyLogo] = useState(() => {
    try { return sessionStorage.getItem("repiq_company_logo") || null; } catch { return null; }
  });
  const navigate = useNavigate();
  const popRef = useRef(null);

  // The company logo (set in Settings → Company) is shown as the app's small brand mark.
  useEffect(() => {
    api.get("/api/company").then((d) => {
      setCompanyLogo(d?.logo || null);
      try { d?.logo ? sessionStorage.setItem("repiq_company_logo", d.logo) : sessionStorage.removeItem("repiq_company_logo"); } catch { /* ignore */ }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const close = (e) => {
      if (popRef.current && !popRef.current.contains(e.target)) setMenuOpen(false);
    };
    if (menuOpen) document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  const logout = () => {
    clearAuth();
    navigate("/login");
  };

  const link = (to, label, Icon, end = false) => (
    <NavLink to={to} end={end} className={({ isActive }) => "sidebar-link" + (isActive ? " active" : "")}>
      <Icon size={21} />
      <span className="sidebar-tip">{label}</span>
    </NavLink>
  );

  // SalesIQ — reserved, specs to follow. Shown but not yet active.
  const comingSoon = (label, Icon) => (
    <div className="sidebar-link sidebar-link-soon" aria-disabled="true" title={`${label} — coming soon`}>
      <Icon size={21} />
      <span className="sidebar-tip">{label} · coming soon</span>
    </div>
  );

  const SunIcon = ({ size = 21 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
  const GridIcon = ({ size = 21 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
  const UsersIcon = ({ size = 21 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
  const isManagerOrAdmin = user?.role === "admin" || user?.sales_role === "manager";

  return (
    <aside className="sidebar">
      <NavLink to="/" className="sidebar-logo" title="RepIQ">
        {companyLogo
          ? <img src={companyLogo} alt="Company logo" className="sidebar-company-logo" style={{ width: "100%", height: "100%", objectFit: "contain", background: "#fff", borderRadius: "inherit", padding: 3, boxSizing: "border-box" }} />
          : "IQ"}
      </NavLink>
      <nav className="sidebar-nav">
        {user?.sales_role === "manager"
          ? link("/command-centre", "Command Centre", GridIcon)
          : link("/today", "Today", SunIcon)}
        {link("/salesiq", "SalesIQ", TrendingUpIcon)}
        {link("/companyiq", "CompanyIQ", BuildingIcon)}
        {link("/recordings", "Recordings", PlayCircleIcon)}
        {link("/insights", "Insights", InsightsIcon)}
        {link("/insights/coaching", "Coaching", CoachingIcon)}
        {link("/playlists", "Playlists", PlaylistIcon)}
        {link("/reports", "AI Reports", ReportsIcon)}
      </nav>
      <div className="sidebar-bottom">
        {isManagerOrAdmin && link("/people", "People", UsersIcon)}
        {user?.role === "admin" && link("/settings", "Settings", SettingsIcon)}
        <button
          style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
          onClick={() => setMenuOpen((o) => !o)}
          aria-label="Account"
        >
          <Avatar name={user?.name} color={user?.avatar_color} size={36} photo={user?.photo} />
        </button>
      </div>
      {menuOpen && (
        <div className="user-pop" ref={popRef}>
          <div className="name">{user?.preferred_name || user?.name}</div>
          {user?.preferred_name && user?.preferred_name !== user?.name && (
            <div className="small muted" style={{ marginTop: -2 }}>{user?.name}</div>
          )}
          <div className="email">{user?.email}</div>
          <div className="small muted" style={{ marginBottom: 10, textTransform: "capitalize" }}>
            Role: {user?.role}
          </div>
          <button className="btn btn-primary btn-sm" style={{ marginBottom: 8, width: "100%", justifyContent: "center" }}
            onClick={() => { setMenuOpen(false); navigate("/account"); }}>
            My profile &amp; account
          </button>
          <button className="btn btn-outline btn-sm" onClick={logout}>
            <LogoutIcon size={14} /> Sign out
          </button>
        </div>
      )}
    </aside>
  );
}
