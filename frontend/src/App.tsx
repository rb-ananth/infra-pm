import { useEffect, useState } from "react";
import api from "./services/api";

type Project = {
  id: string;
  code: string;
  name: string;
  status: string;
  total_estimated_cost: string;
  start_date: string;
  expected_completion: string;
};

type User = {
  email: string;
  role: string;
};

function App() {
  const [email, setEmail] = useState("admin@infrapm.gov");
  const [password, setPassword] = useState("Admin@123");
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");

  async function login(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const response = await api.post("/auth/login", { email, password });
      localStorage.setItem("token", response.data.access_token);
      const me = await api.get("/users/me");
      setUser(me.data);
      const projectResponse = await api.get("/projects");
      setProjects(projectResponse.data);
    } catch {
      setError("Login failed. Check the API server and credentials.");
    }
  }

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) return;
    api.get("/users/me")
      .then((response) => setUser(response.data))
      .catch(() => localStorage.removeItem("token"));
    api.get("/projects")
      .then((response) => setProjects(response.data))
      .catch(() => undefined);
  }, []);

  function logout() {
    localStorage.removeItem("token");
    setUser(null);
    setProjects([]);
  }

  if (!user) {
    return (
      <main className="center">
        <form className="card login" onSubmit={login}>
          <div className="eyebrow">InfraPM Intelligence</div>
          <h1>Project Controls Platform</h1>
          <p className="muted">Sprint 1 foundation</p>
          <label>Email<input value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {error && <p className="error">{error}</p>}
          <button type="submit">Sign in</button>
        </form>
      </main>
    );
  }

  return (
    <div className="app">
      <header>
        <div>
          <div className="eyebrow">InfraPM Intelligence</div>
          <h1>Executive Workspace</h1>
        </div>
        <div className="userbar">
          <span>{user.email} · {user.role}</span>
          <button className="secondary" onClick={logout}>Logout</button>
        </div>
      </header>

      <section className="stats">
        <div className="card"><span>Projects</span><strong>{projects.length}</strong></div>
        <div className="card"><span>Active Execution</span><strong>{projects.filter(p => p.status === "Execution").length}</strong></div>
        <div className="card"><span>Portfolio Estimate</span><strong>₹{projects.reduce((sum, p) => sum + Number(p.total_estimated_cost), 0).toFixed(2)} Cr</strong></div>
      </section>

      <section className="card">
        <div className="section-title">
          <h2>Project Registry</h2>
          <span className="badge">V1</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Code</th><th>Project</th><th>Status</th><th>Estimate (Cr)</th><th>Completion</th></tr></thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.id}>
                  <td>{project.code}</td>
                  <td>{project.name}</td>
                  <td><span className="status">{project.status}</span></td>
                  <td>₹{Number(project.total_estimated_cost).toFixed(2)}</td>
                  <td>{project.expected_completion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default App;
