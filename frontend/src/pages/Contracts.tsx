import { useEffect, useMemo, useState } from "react";

import api from "../services/api";
import type { Contract, Contractor, Project } from "../types";
import { croreToInr, formatInrAsCrore } from "../utils/money";

const CONTRACT_STATUSES = [
  "Draft",
  "Active",
  "Suspended",
  "Completed",
  "Terminated",
];

function formatDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function Contracts() {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [contractors, setContractors] = useState<Contractor[]>([]);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");

  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    contract_number: "",
    project_id: "",
    contractor_id: "",
    contract_type: "Works",
    award_date: "",
    contract_value: "",
    start_date: "",
    original_completion_date: "",
    current_completion_date: "",
    status: "Draft",
  });

  async function loadData() {
    setLoading(true);
    setError("");

    try {
      const [contractsResponse, projectsResponse, contractorsResponse] =
        await Promise.all([
          api.get("/contracts"),
          api.get("/projects"),
          api.get("/contractors"),
        ]);

      setContracts(contractsResponse.data);
      setProjects(projectsResponse.data);
      setContractors(contractorsResponse.data);
    } catch {
      setError("Unable to load contract data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const projectMap = useMemo(
    () => new Map(projects.map((project) => [project.id, project])),
    [projects],
  );

  const contractorMap = useMemo(
    () =>
      new Map(
        contractors.map((contractor) => [contractor.id, contractor]),
      ),
    [contractors],
  );

  const filteredContracts = contracts.filter((contract) => {
    const query = search.trim().toLowerCase();

    const matchesSearch =
      !query ||
      contract.contract_number.toLowerCase().includes(query) ||
      projectMap.get(contract.project_id)?.name
        .toLowerCase()
        .includes(query) ||
      contractorMap.get(contract.contractor_id)?.name
        .toLowerCase()
        .includes(query);

    const matchesStatus =
      statusFilter === "All" || contract.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  function updateField(
    field: keyof typeof form,
    value: string,
  ) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function createContract(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      await api.post("/contracts", {
        ...form,
        contract_value: croreToInr(form.contract_value),
      });

      setShowForm(false);

      setForm({
        contract_number: "",
        project_id: "",
        contractor_id: "",
        contract_type: "Works",
        award_date: "",
        contract_value: "",
        start_date: "",
        original_completion_date: "",
        current_completion_date: "",
        status: "Draft",
      });

      await loadData();
    } catch (requestError: any) {
      setError(
        requestError?.response?.data?.detail ||
          "Unable to create contract.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="contracts-page">
      <div className="contracts-page-header">
        <div>
          <div className="eyebrow">Contract Management</div>
          <h1>Contract Registry</h1>
          <p className="muted">
            Manage project contracts and contractor relationships.
          </p>
        </div>

        <button onClick={() => setShowForm(true)}>
          Create Contract
        </button>
      </div>

      <div className="toolbar">
        <input
          className="search-input contracts-search"
          placeholder="Search contract, project or contractor..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />

        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <option value="All">All Statuses</option>

          {CONTRACT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="error">{error}</p>}

      {loading ? (
        <div className="card">
          <p className="muted">Loading contracts...</p>
        </div>
      ) : filteredContracts.length === 0 ? (
        <div className="card">
          <p className="muted">
            No contracts match the current filters.
          </p>
        </div>
      ) : (
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Contract</th>
                <th>Project</th>
                <th>Contractor</th>
                <th>Value</th>
                <th>Start</th>
                <th>Completion</th>
                <th>Status</th>
              </tr>
            </thead>

            <tbody>
              {filteredContracts.map((contract) => (
                <tr key={contract.id}>
                  <td>
                    <strong>{contract.contract_number}</strong>
                    <div className="table-subtext">
                      {contract.contract_type}
                    </div>
                  </td>

                  <td>
                    {projectMap.get(contract.project_id)?.name ||
                      "Unknown project"}
                  </td>

                  <td>
                    {contractorMap.get(contract.contractor_id)?.name ||
                      "Unknown contractor"}
                  </td>

                  <td>₹{formatInrAsCrore(contract.contract_value)} Cr</td>

                  <td>{formatDate(contract.start_date)}</td>

                  <td>
                    {formatDate(contract.current_completion_date)}
                  </td>

                  <td>
                    <span
                      className={`status-badge status-${contract.status.toLowerCase()}`}
                    >
                      {contract.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <div className="modal-backdrop">
          <div className="card modal">
            <div className="modal-header">
              <div>
                <div className="eyebrow">New Contract</div>
                <h2>Create Contract</h2>
              </div>

              <button
                className="secondary"
                type="button"
                onClick={() => setShowForm(false)}
              >
                Close
              </button>
            </div>

            <form onSubmit={createContract}>
              <div className="form-grid">
                <label>
                  Contract Number
                  <input
                    required
                    value={form.contract_number}
                    onChange={(event) =>
                      updateField(
                        "contract_number",
                        event.target.value,
                      )
                    }
                  />
                </label>

                <label>
                  Contract Type
                  <select
                    value={form.contract_type}
                    onChange={(event) =>
                      updateField(
                        "contract_type",
                        event.target.value,
                      )
                    }
                  >
                    <option value="Works">Works</option>
                    <option value="Consultancy">Consultancy</option>
                    <option value="Supply">Supply</option>
                  </select>
                </label>

                <label>
                  Project
                  <select
                    required
                    value={form.project_id}
                    onChange={(event) =>
                      updateField("project_id", event.target.value)
                    }
                  >
                    <option value="">Select project</option>

                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>
                        {project.code} — {project.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Contractor
                  <select
                    required
                    value={form.contractor_id}
                    onChange={(event) =>
                      updateField(
                        "contractor_id",
                        event.target.value,
                      )
                    }
                  >
                    <option value="">Select contractor</option>

                    {contractors
                      .filter(
                        (contractor) => contractor.status === "Active",
                      )
                      .map((contractor) => (
                        <option
                          key={contractor.id}
                          value={contractor.id}
                        >
                          {contractor.registration_number} —{" "}
                          {contractor.name}
                        </option>
                      ))}
                  </select>
                </label>

                <label>
                  Award Date
                  <input
                    required
                    type="date"
                    value={form.award_date}
                    onChange={(event) =>
                      updateField("award_date", event.target.value)
                    }
                  />
                </label>

                <label>
                  Contract Value (₹ Cr)
                  <input
                    required
                    min="0"
                    step="0.01"
                    type="number"
                    value={form.contract_value}
                    onChange={(event) =>
                      updateField(
                        "contract_value",
                        event.target.value,
                      )
                    }
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
                  Original Completion
                  <input
                    required
                    type="date"
                    value={form.original_completion_date}
                    onChange={(event) =>
                      updateField(
                        "original_completion_date",
                        event.target.value,
                      )
                    }
                  />
                </label>

                <label>
                  Current Completion
                  <input
                    required
                    type="date"
                    value={form.current_completion_date}
                    onChange={(event) =>
                      updateField(
                        "current_completion_date",
                        event.target.value,
                      )
                    }
                  />
                </label>

                <label>
                  Status
                  <select
                    value={form.status}
                    onChange={(event) =>
                      updateField("status", event.target.value)
                    }
                  >
                    {CONTRACT_STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="form-actions">
                <button
                  className="secondary"
                  type="button"
                  onClick={() => setShowForm(false)}
                >
                  Cancel
                </button>

                <button type="submit" disabled={saving}>
                  {saving ? "Creating..." : "Create Contract"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

export default Contracts;
