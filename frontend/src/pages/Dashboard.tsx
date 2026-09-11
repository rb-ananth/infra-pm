import type { Project } from "../types";

type DashboardProps = {
  projects: Project[];
};

function Dashboard({ projects }: DashboardProps) {
  const activeProjects = projects.filter(
    (project) => project.status === "Execution",
  ).length;

  const portfolioEstimate = projects.reduce(
    (sum, project) => sum + Number(project.total_estimated_cost),
    0,
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">Portfolio overview</div>
          <h1>Executive Dashboard</h1>
          <p className="muted">
            Current project portfolio and delivery overview.
          </p>
        </div>
      </div>

      <section className="stats">
        <div className="card">
          <span>Total Projects</span>
          <strong>{projects.length}</strong>
        </div>

        <div className="card">
          <span>Active Execution</span>
          <strong>{activeProjects}</strong>
        </div>

        <div className="card">
          <span>Portfolio Estimate</span>
          <strong>₹{portfolioEstimate.toFixed(2)} Cr</strong>
        </div>

        <div className="card">
          <span>Projects at Risk</span>
          <strong>—</strong>
        </div>
      </section>

      <section className="card">
        <div className="section-title">
          <div>
            <h2>Recent Projects</h2>
            <p className="muted">
              Projects currently registered in InfraPM.
            </p>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Project</th>
                <th>Status</th>
                <th>Estimate</th>
                <th>Expected Completion</th>
              </tr>
            </thead>

            <tbody>
              {projects.map((project) => (
                <tr key={project.id}>
                  <td>{project.code}</td>
                  <td>{project.name}</td>
                  <td>
                    <span className="status">{project.status}</span>
                  </td>
                  <td>
                    ₹{Number(project.total_estimated_cost).toFixed(2)} Cr
                  </td>
                  <td>{project.expected_completion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export default Dashboard;
