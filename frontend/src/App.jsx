import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import Layout, { Backdrop, PublicNav } from "./components/Layout";
import { Spinner } from "./components/ui";
import { useAuth } from "./context";

import Landing from "./pages/Landing";
import { Login, Signup } from "./pages/Auth";
import Verify from "./pages/Verify";

// Heavier, signed-in pages are split out so the public landing/verify pages load fast.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Records = lazy(() => import("./pages/Records"));
const Register = lazy(() => import("./pages/Register"));
const RecordDetail = lazy(() => import("./pages/RecordDetail"));
const Approvals = lazy(() => import("./pages/Approvals"));
const Audit = lazy(() => import("./pages/Audit"));
const Admin = lazy(() => import("./pages/Admin"));
const Settings = lazy(() => import("./pages/Settings"));

const Loading = () => <div style={{ display: "grid", placeItems: "center", minHeight: "40vh" }}><Spinner /></div>;

function Protected({ admin }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname + loc.search }} replace />;
  if (admin && user.role !== "admin") return <Navigate to="/dashboard" replace />;
  return <Layout />;
}

/** Verification is public: signed-in users get the app shell, everyone else the public one. */
function AdaptiveShell() {
  const { user, ready } = useAuth();
  if (!ready) return <Loading />;
  return user ? <Layout /> : <><PublicNav /><Outlet /></>;
}

function PublicShell() {
  return <><PublicNav /><Outlet /></>;
}

export default function App() {
  return (
    <>
      <Backdrop />
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route element={<PublicShell />}><Route path="/" element={<Landing />} /></Route>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route element={<AdaptiveShell />}>
            <Route path="/verify" element={<Verify />} />
            <Route path="/verify/:id" element={<Verify />} />
          </Route>
          <Route element={<Protected />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/records" element={<Records />} />
            <Route path="/records/:id" element={<RecordDetail />} />
            <Route path="/register" element={<Register />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
          <Route element={<Protected admin />}><Route path="/admin" element={<Admin />} /></Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </>
  );
}
