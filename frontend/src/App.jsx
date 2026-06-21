import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation, useOutletContext } from "react-router-dom";

// Catches any render error in a page so a single broken view shows a message instead of
// blanking the whole app (no error boundary = React unmounts everything to white).
class ErrorBoundary extends React.Component {
  constructor(p) { super(p); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidUpdate(prev) { if (prev.routeKey !== this.props.routeKey && this.state.error) this.setState({ error: null }); }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, maxWidth: 620 }}>
          <h2 style={{ marginTop: 0 }}>Something went wrong on this page</h2>
          <p className="muted">The rest of the app is fine — try another section, or reload. If it persists, let us know what you were doing.</p>
          <pre style={{ whiteSpace: "pre-wrap", background: "#f6f7f9", padding: 12, borderRadius: 8, fontSize: 12, color: "#b00" }}>
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <button className="btn btn-primary" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      );
    }
    return this.props.children;
  }
}
import { getToken, getStoredUser, setAuth, api } from "./api";
import { ToastProvider } from "./components/Toast.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Login from "./pages/Login.jsx";
import SetPassword from "./pages/SetPassword.jsx";
import Account from "./pages/Account.jsx";
import People from "./pages/People.jsx";
import HRProfile from "./pages/HRProfile.jsx";
import HolidayCalendar from "./pages/HolidayCalendar.jsx";
import Library from "./pages/Library.jsx";
import CompanyIQ from "./pages/CompanyIQ.jsx";
import SalesIQ from "./pages/SalesIQ.jsx";
import MorningDashboard from "./pages/MorningDashboard.jsx";
import CommandCentre from "./pages/CommandCentre.jsx";
import CallDetail from "./pages/CallDetail.jsx";
import Playlists from "./pages/Playlists.jsx";
import Insights from "./pages/Insights.jsx";
import Reports from "./pages/Reports.jsx";
import Settings from "./pages/Settings.jsx";
import OrderEntry from "./pages/OrderEntry.jsx";

function ProtectedLayout() {
  const location = useLocation();
  const token = getToken();
  const [user, setUser] = useState(getStoredUser());
  // Refresh the user from the server so the derived sales_role (used for role-based routing)
  // is always current, even for sessions that logged in before sales_role existed.
  useEffect(() => {
    if (!token) return;
    api.get("/api/auth/me").then((u) => { setUser(u); setAuth(token, u); }).catch(() => {});
  }, [token]);
  if (!token) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return (
    <div className="app-shell">
      <Sidebar user={user} />
      <main className="app-content">
        <ErrorBoundary routeKey={location.pathname}>
          <Outlet context={{ user }} />
        </ErrorBoundary>
      </main>
    </div>
  );
}

function AdminOnly({ children }) {
  const user = getStoredUser();
  if (!user || user.role !== "admin") return <Navigate to="/" replace />;
  return children;
}

const isManager = (u) => u?.sales_role === "manager";
const isOps = (u) => u?.platform_role === "operations";

// People management is for managers and admins; everyone else is sent home.
function PeopleArea({ children }) {
  const { user } = useOutletContext() || {};
  if (user && user.role !== "admin" && !isManager(user)) return <Navigate to="/" replace />;
  return children;
}

// "/" lands each role on the right home: Operations → Order Entry (they aren't sales reps),
// managers → Command Centre, everyone else → Today.
function RoleLanding() {
  const { user } = useOutletContext() || {};
  if (isOps(user)) return <Navigate to="/orders" replace />;
  return <Navigate to={isManager(user) ? "/command-centre" : "/today"} replace />;
}

// Managers never see the rep morning dashboard (brief: they get the Command Centre, full stop).
// Operations aren't treated as sales reps — Today is hidden for them; they land on Order Entry.
function RepArea({ children }) {
  const { user } = useOutletContext() || {};
  if (isOps(user)) return <Navigate to="/orders" replace />;
  if (isManager(user)) return <Navigate to="/command-centre" replace />;
  return children;
}

// The Command Centre is for managers/admin only; reps are sent back to their dashboard.
function ManagerArea({ children }) {
  const { user } = useOutletContext() || {};
  if (user && !isManager(user)) return <Navigate to="/today" replace />;
  return children;
}

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/set-password/:token" element={<SetPassword />} />
          <Route element={<ProtectedLayout />}>
            <Route path="/" element={<RoleLanding />} />
            <Route path="/account" element={<Account />} />
            <Route path="/people" element={<PeopleArea><People /></PeopleArea>} />
            <Route path="/people/:id" element={<HRProfile />} />
            <Route path="/today" element={<RepArea><MorningDashboard /></RepArea>} />
            <Route path="/command-centre" element={<ManagerArea><CommandCentre /></ManagerArea>} />
            <Route path="/adminhub" element={<HolidayCalendar />} />
            <Route path="/companyiq" element={<CompanyIQ />} />
            <Route path="/salesiq" element={<SalesIQ />} />
            <Route path="/orders" element={<OrderEntry />} />
            <Route path="/library" element={<Library />} />
            <Route path="/recordings" element={<Library />} />
            <Route path="/calls/:id" element={<CallDetail />} />
            <Route path="/playlists" element={<Playlists />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/insights/:tab" element={<Insights />} />
            <Route path="/reports" element={<Reports />} />
            <Route
              path="/settings"
              element={
                <AdminOnly>
                  <Settings />
                </AdminOnly>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}
