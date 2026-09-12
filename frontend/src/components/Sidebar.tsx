import { NavLink } from "react-router-dom";

type SidebarProps = {
  role: string;
};

function Sidebar({ role }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">IP</div>
        <div>
          <strong>InfraPM</strong>
          <span>Intelligence</span>
        </div>
      </div>

      <nav className="nav">
        <NavLink
          to="/"
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
        >
          Dashboard
        </NavLink>

        <NavLink
          to="/projects"
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
        >
          Projects
        </NavLink>

        <NavLink
          to="/contractors"
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
        >
          Contractors
        </NavLink>

        <NavLink
          to="/contracts"
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
        >
          Contracts
        </NavLink>

        <NavLink
          to="/boqs"
          end
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
        >
          BOQs
        </NavLink>

        <NavLink
          to="/measurements"
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
        >
          Measurements
        </NavLink>

        <NavLink
          to="/ra-bills"
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
        >
          RA Bills
        </NavLink>

        <NavLink
          to="/departments"
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
        >
          Departments
        </NavLink>

        {role === "Admin" && (
          <NavLink
            to="/audit-logs"
            className={({ isActive }) =>
              isActive ? "nav-link active" : "nav-link"
            }
          >
            Audit Logs
          </NavLink>
        )}
      </nav>

      <div className="sidebar-footer">
        <span>Sprint 1</span>
        <small>Project Controls Platform</small>
      </div>
    </aside>
  );
}

export default Sidebar;
