import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "../services/api";
import type { Project, User } from "../types";
import { formatInrAsCrore } from "../utils/money";

type Department = {
  id: string;
  code: string;
  name: string;
};

function ProjectDetails() {
  const { projectId } = useParams<{ projectId: string }>();

  const [project, setProject] = useState<Project | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [projectManagers, setProjectManagers] = useState<User[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadProject() {
      if (!projectId) {
        setError("Project ID is missing.");
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError("");

        const [
          projectResponse,
          departmentsResponse,
          managersResponse,
        ] = await Promise.all([
          api.get(`/projects/${projectId}`),
          api.get("/departments"),
          api.get("/users/project-managers"),
        ]);

        setProject(projectResponse.data);
        setDepartments(departmentsResponse.data);
        setProjectManagers(managersResponse.data);
      } catch {
        setError("Unable to load project details.");
      } finally {
        setLoading(false);
      }
    }

    loadProject();
  }, [projectId]);

  if (loading) {
    return <p className="muted">Loading project details...</p>;
  }

  if (error || !project) {
    return (
      <section className="card">
        <p className="error">{error || "Project not found."}</p>
        <Link to="/projects" className="back-link">
          ← Back to Projects
        </Link>
      </section>
    );
  }

  const department = departments.find(
    (item) => item.id === project.dept_id,
  );

  const manager = projectManagers.find(
    (item) => item.id === project.pm_id,
  );

  return (
    <>
      <div className="page-heading">
        <Link to="/projects" className="back-link">
          ← Project Registry
        </Link>

        <div className="eyebrow">Project Details</div>

        <div className="project-title-row">
          <div>
            <h1>{project.name}</h1>
            <p className="muted">{project.code}</p>
          </div>

          <span className="status status-large">
            {project.status}
          </span>
        </div>
      </div>

      <section className="stats project-stats">
        <div className="card">
          <span>Estimated Cost</span>
          <strong>
            ₹{formatInrAsCrore(project.total_estimated_cost)} Cr
          </strong>
        </div>

        <div className="card">
          <span>Start Date</span>
          <strong>{project.start_date}</strong>
        </div>

        <div className="card">
          <span>Expected Completion</span>
          <strong>{project.expected_completion}</strong>
        </div>

        <div className="card">
          <span>Project Status</span>
          <strong>{project.status}</strong>
        </div>
      </section>

      <section className="card">
        <div className="section-title">
          <div>
            <div className="eyebrow">Project Information</div>
            <h2>Project Overview</h2>
          </div>
        </div>

        <div className="details-grid">
          <div className="detail-item">
            <span>Project Code</span>
            <strong>{project.code}</strong>
          </div>

          <div className="detail-item">
            <span>Department</span>
            <strong>
              {department
                ? `${department.code} — ${department.name}`
                : project.dept_id}
            </strong>
          </div>

          <div className="detail-item">
            <span>Project Manager</span>
            <strong>
              {manager ? manager.email : project.pm_id}
            </strong>
          </div>

          <div className="detail-item">
            <span>Created</span>
            <strong>
              {new Date(project.created_at).toLocaleString()}
            </strong>
          </div>

          <div className="detail-item">
            <span>Last Updated</span>
            <strong>
              {new Date(project.updated_at).toLocaleString()}
            </strong>
          </div>
        </div>
      </section>

      <section className="card module-section">
        <div className="section-title">
          <div>
            <div className="eyebrow">Project Controls</div>
            <h2>Control Modules</h2>
            <p className="muted">
              Project control modules will be connected as the platform
              expands.
            </p>
          </div>
        </div>

        <div className="module-grid">
          <div className="module-card">
            <strong>Contract</strong>
            <span>Contract details and administration</span>
          </div>

          <div className="module-card">
            <strong>BOQ</strong>
            <span>Bill of quantities and item controls</span>
          </div>

          <div className="module-card">
            <strong>Measurements</strong>
            <span>Measurement records and quantities</span>
          </div>

          <div className="module-card">
            <strong>RA Bills</strong>
            <span>Running account billing and certification</span>
          </div>

          <div className="module-card">
            <strong>Progress</strong>
            <span>Physical and financial progress</span>
          </div>

          <div className="module-card">
            <strong>EVM</strong>
            <span>Earned value and project performance</span>
          </div>

          <div className="module-card">
            <strong>Variations</strong>
            <span>Variation and change management</span>
          </div>

          <div className="module-card">
            <strong>EOT / Claims</strong>
            <span>Extension of time and claims management</span>
          </div>
        </div>
      </section>
    </>
  );
}

export default ProjectDetails;
