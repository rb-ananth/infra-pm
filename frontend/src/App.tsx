import { useEffect, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import api from "./services/api";
import Sidebar from "./components/Sidebar";

import Dashboard from "./pages/Dashboard";
import Projects from "./pages/Projects";
import Contractors from "./pages/Contractors";
import Departments from "./pages/Departments";
import AuditLogs from "./pages/AuditLogs";

import type { Project, User } from "./types";

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  async function loadSession() {
    const token = localStorage.getItem("token");

    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const me = await api.get("/users/me");
      setUser(me.data);

      const projectResponse = await api.get("/projects");
      setProjects(projectResponse.data);
    } catch {
      localStorage.removeItem("token");
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSession();
  }, []);

  function logout() {
    localStorage.removeItem("token");
    setUser(null);
    setProjects([]);
  }

  if (loading) {
    return (
      <main className="center">
        <div className="card">
          <p className="muted">Loading InfraPM Intelligence...</p>
        </div>
      </main>
    );
  }

  if (!user) {
    return <Login onLogin={loadSession} />;
  }

  return (
    <div className="app-shell">
        <Sidebar role={user.role} />

        <main className="main-content">
          <header className="topbar">
            <div>
              <div className="eyebrow">InfraPM Intelligence</div>
              <span className="muted">Infrastructure Project Controls</span>
            </div>

            <div className="userbar">
              <span>
                {user.email} · {user.role}
              </span>

              <button className="secondary" onClick={logout}>
                Logout
              </button>
            </div>
          </header>

          <Routes>
            <Route
              path="/"
              element={<Dashboard projects={projects} />}
            />

            <Route
              path="/projects"
              element={<Projects />}
            />

            <Route
              path="/contractors"
              element={<Contractors />}
            />

            <Route
              path="/departments"
              element={<Departments />}
            />

            <Route
              path="/audit-logs"
              element={
                user.role === "Admin"
                  ? <AuditLogs />
                  : <Navigate to="/" replace />
              }
            />

            <Route
              path="*"
              element={<Navigate to="/" replace />}
            />
          </Routes>
        </main>
      </div>
  );
}

type LoginProps = {
  onLogin: () => Promise<void>;
};

function Login({ onLogin }: LoginProps) {
  const [email, setEmail] = useState("admin@infrapm.gov");
  const [password, setPassword] = useState("Admin@123");
  const [error, setError] = useState("");

  async function login(event: React.FormEvent) {
    event.preventDefault();
    setError("");

    try {
      const formData = new URLSearchParams();

      formData.append("username", email);
      formData.append("password", password);

      const response = await api.post(
        "/auth/login",
        formData.toString(),
        {
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
        },
      );

      localStorage.setItem("token", response.data.access_token);

      await onLogin();
    } catch {
      setError(
        "Login failed. Check the API server and credentials.",
      );
    }
  }

  return (
    <main className="center">
      <form className="card login" onSubmit={login}>
        <div className="eyebrow">InfraPM Intelligence</div>

        <h1>Project Controls Platform</h1>

        <p className="muted">
          Infrastructure project management and analytics.
        </p>

        <label>
          Email
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        {error && <p className="error">{error}</p>}

        <button type="submit">Sign in</button>
      </form>
    </main>
  );
}

export default App;
