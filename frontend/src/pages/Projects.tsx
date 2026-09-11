import { useEffect, useMemo, useState } from "react";
import api from "../services/api";
import type { Project, User } from "../types";

type Department = {
  id: string;
  code: string;
  name: string;
};

function Projects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [projectManagers, setProjectManagers] = useState<User[]>([]);

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All");

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [form, setForm] = useState({
    code: "",
    name: "",
    dept_id: "",
    pm_id: "",
    status: "Proposed",
    total_estimated_cost: "",
    start_date: "",
    expected_completion: "",
  });

  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [projectsResponse, departmentsResponse, pmResponse] =
        await Promise.all([
          api.get("/projects"),
          api.get("/departments"),
          api.get("/users/project-managers"),
        ]);

      setProjects(projectsResponse.data);
      setDepartments(departmentsResponse.data);
      setProjectManagers(pmResponse.data);
    } catch {
      setError("Unable to load project registry data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const statuses = useMemo(() => {
    return ["All", ...new Set(projects.map((project) => project.status))];
  }, [projects]);

  const filteredProjects = useMemo(() => {
    const query = search.trim().toLowerCase();

    return projects.filter((project) => {
      const matchesSearch =
        !query ||
        project.code.toLowerCase().includes(query) ||
        project.name.toLowerCase().includes(query);

      const matchesStatus =
        status === "All" || project.status === status;

      return matchesSearch && matchesStatus;
    });
  }, [projects, search, status]);

  function updateField(field: string, value: string) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function resetForm() {
    setForm({
      code: "",
      name: "",
      dept_id: "",
      pm_id: "",
      status: "Proposed",
      total_estimated_cost: "",
      start_date: "",
      expected_completion: "",
    });
  }

  async function createProject(event: React.FormEvent) {
    event.preventDefault();

    setError("");
    setSuccess("");

    if (
      form.expected_completion &&
      form.start_date &&
      form.expected_completion < form.start_date
    ) {
      setError(
        "Expected completion date cannot be before the start date.",
      );
      return;
    }

    try {
      setSaving(true);

      await api.post("/projects/", {
        code: form.code.trim(),
        name: form.name.trim(),
        dept_id: form.dept_id,
        pm_id: form.pm_id,
        status: form.status,
        total_estimated_cost: form.total_estimated_cost,
        start_date: form.start_date,
        expected_completion: form.expected_completion,
      });

      resetForm();
      setShowCreateForm(false);
      setSuccess("Project created successfully.");

      await loadData();
    } catch (requestError: any) {
      const detail = requestError?.response?.data?.detail;

      if (typeof detail === "string") {
        setError(detail);
      } else {
        setError("Unable to create project.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="page-heading page-heading-row">
        <div>
          <div className="eyebrow">Project Controls</div>
          <h1>Project Registry</h1>
          <p className="muted">
            Search, review, and register infrastructure projects.
          </p>
        </div>

        <button onClick={() => setShowCreateForm(true)}>
          + Create Project
        </button>
      </div>

      {success && <div className="alert success">{success}</div>}
      {error && <div className="alert error">{error}</div>}

      {showCreateForm && (
        <section className="card create-project-card">
          <div className="section-title">
            <div>
              <div className="eyebrow">Project Registration</div>
              <h2>Create Project</h2>
            </div>

            <button
              type="button"
              className="secondary"
              onClick={() => {
                setShowCreateForm(false);
                setError("");
              }}
            >
              Cancel
            </button>
          </div>

          <form onSubmit={createProject}>
            <div className="form-grid">
              <label>
                Project Code
                <input
                  required
                  minLength={2}
                  maxLength={50}
                  value={form.code}
                  onChange={(event) =>
                    updateField("code", event.target.value)
                  }
                  placeholder="PWD-2026-002"
                />
              </label>

              <label>
                Project Name
                <input
                  required
                  minLength={3}
                  maxLength={255}
                  value={form.name}
                  onChange={(event) =>
                    updateField("name", event.target.value)
                  }
                  placeholder="District Hospital Upgrade"
                />
              </label>

              <label>
                Department
                <select
                  required
                  value={form.dept_id}
                  onChange={(event) =>
                    updateField("dept_id", event.target.value)
                  }
                >
                  <option value="">Select department</option>

                  {departments.map((department) => (
                    <option
                      key={department.id}
                      value={department.id}
                    >
                      {department.code} — {department.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Project Manager
                <select
                  required
                  value={form.pm_id}
                  onChange={(event) =>
                    updateField("pm_id", event.target.value)
                  }
                >
                  <option value="">Select project manager</option>

                  {projectManagers.map((manager) => (
                    <option key={manager.id} value={manager.id}>
                      {manager.email}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Status
                <select
                  value={form.status}
                  onChange={(event) =>
                    updateField("status", event.target.value)
                  }
                >
                  <option value="Proposed">Proposed</option>
                  <option value="Execution">Execution</option>
                  <option value="Closed">Closed</option>
                  <option value="Suspended">Suspended</option>
                </select>
              </label>

              <label>
                Estimated Cost (Cr)
                <input
                  required
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.total_estimated_cost}
                  onChange={(event) =>
                    updateField(
                      "total_estimated_cost",
                      event.target.value,
                    )
                  }
                  placeholder="25.50"
                />
              </label>

              <label>
                Start Date
                <input
                  required
                  type="date"
                  value={form.start_date}
                  onChange={(event) =>
                    updateField("start_date", event.target.value)
                  }
                />
              </label>

              <label>
                Expected Completion
                <input
                  required
                  type="date"
                  value={form.expected_completion}
                  min={form.start_date || undefined}
                  onChange={(event) =>
                    updateField(
                      "expected_completion",
                      event.target.value,
                    )
                  }
                />
              </label>
            </div>

            <div className="form-actions">
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  resetForm();
                  setShowCreateForm(false);
                  setError("");
                }}
              >
                Cancel
              </button>

              <button type="submit" disabled={saving}>
                {saving ? "Creating..." : "Create Project"}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="card">
        <div className="registry-toolbar">
          <div>
            <strong>{filteredProjects.length}</strong>
            <span className="muted"> projects shown</span>
          </div>

          <div className="registry-filters">
            <input
              className="search-input"
              type="search"
              placeholder="Search code or project name..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />

            <select
              className="filter-select"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              {statuses.map((projectStatus) => (
                <option key={projectStatus} value={projectStatus}>
                  {projectStatus}
                </option>
              ))}
            </select>
          </div>
        </div>

        {loading && (
          <p className="muted">Loading projects...</p>
        )}

        {!loading && !error && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Project</th>
                  <th>Status</th>
                  <th>Estimate</th>
                  <th>Start Date</th>
                  <th>Expected Completion</th>
                </tr>
              </thead>

              <tbody>
                {filteredProjects.map((project) => (
                  <tr key={project.id}>
                    <td>{project.code}</td>

                    <td>
                      <strong>{project.name}</strong>
                    </td>

                    <td>
                      <span className="status">
                        {project.status}
                      </span>
                    </td>

                    <td>
                      ₹
                      {Number(
                        project.total_estimated_cost,
                      ).toFixed(2)}{" "}
                      Cr
                    </td>

                    <td>{project.start_date}</td>

                    <td>{project.expected_completion}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filteredProjects.length === 0 && (
              <p className="muted empty-state">
                No projects match the current filters.
              </p>
            )}
          </div>
        )}
      </section>
    </>
  );
}

export default Projects;
