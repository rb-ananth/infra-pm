import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import api, { boqApi, getApiErrorMessage } from "../services/api";
import type { Boq, Contract, Project } from "../types";
import { formatInrAsCrore } from "../utils/money";

const BOQ_STATUSES = ["All", "Draft", "Submitted", "Approved", "Superseded"];

type BoqRegistryProps = {
  role: string;
};

type BoqForm = {
  contract_id: string;
  boq_number: string;
  title: string;
  description: string;
};

function BoqRegistry({ role }: BoqRegistryProps) {
  const navigate = useNavigate();
  const [boqs, setBoqs] = useState<Boq[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState<BoqForm>({
    contract_id: "",
    boq_number: "",
    title: "",
    description: "",
  });

  const canWrite = role === "Admin" || role === "Project Manager";

  async function loadData() {
    try {
      setLoading(true);
      setError("");
      const [boqResponse, contractResponse, projectResponse] = await Promise.all([
        boqApi.list(),
        boqApi.listContracts(),
        api.get<Project[]>("/projects/"),
      ]);
      setBoqs(boqResponse.data);
      setContracts(contractResponse.data);
      setProjects(projectResponse.data);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load BOQ registry."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const contractMap = useMemo(
    () => new Map(contracts.map((contract) => [contract.id, contract])),
    [contracts],
  );
  const projectMap = useMemo(
    () => new Map(projects.map((project) => [project.id, project])),
    [projects],
  );

  const filteredBoqs = useMemo(() => {
    const query = search.trim().toLowerCase();
    return boqs.filter((boq) => {
      const contract = contractMap.get(boq.contract_id);
      const project = contract ? projectMap.get(contract.project_id) : undefined;
      const matchesSearch =
        !query ||
        boq.boq_number.toLowerCase().includes(query) ||
        boq.title.toLowerCase().includes(query) ||
        contract?.contract_number.toLowerCase().includes(query) ||
        project?.name.toLowerCase().includes(query);
      const matchesStatus = statusFilter === "All" || boq.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [boqs, contracts, contractMap, projectMap, search, statusFilter]);

  function resetForm() {
    setForm({ contract_id: "", boq_number: "", title: "", description: "" });
  }

  async function createBoq(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const boqNumber = form.boq_number.trim();
    const title = form.title.trim();
    if (!form.contract_id || !boqNumber || !title) {
      setError("Contract, BOQ number, and title are required.");
      return;
    }

    try {
      setSaving(true);
      setError("");
      const response = await boqApi.create({
        contract_id: form.contract_id,
        boq_number: boqNumber,
        title,
        ...(form.description.trim() ? { description: form.description.trim() } : {}),
      });
      resetForm();
      setShowForm(false);
      await loadData();
      navigate(`/boqs/${response.data.id}`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to create BOQ."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="boq-page">
      <div className="page-heading page-heading-row">
        <div>
          <div className="eyebrow">Contract Controls</div>
          <h1>BOQ Registry</h1>
          <p className="muted">Manage bills of quantities and their controlled revisions.</p>
        </div>
        {canWrite && (
          <button type="button" onClick={() => setShowForm(true)}>
            + Create BOQ
          </button>
        )}
      </div>

      {error && <div className="alert error">{error}</div>}

      <section className="card">
        <div className="registry-toolbar">
          <div>
            <strong>{filteredBoqs.length}</strong>
            <span className="muted"> BOQs shown</span>
          </div>
          <div className="registry-filters">
            <input
              className="search-input"
              type="search"
              placeholder="Search BOQ, contract, or project..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <select
              className="filter-select"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              {BOQ_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status === "All" ? "All Statuses" : status}
                </option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <p className="muted">Loading BOQs...</p>
        ) : filteredBoqs.length === 0 ? (
          <p className="muted empty-state">No BOQs found.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>BOQ Number</th>
                  <th>Title</th>
                  <th>Contract</th>
                  <th>Project</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredBoqs.map((boq) => {
                  const contract = contractMap.get(boq.contract_id);
                  const project = contract ? projectMap.get(contract.project_id) : undefined;
                  return (
                    <tr key={boq.id}>
                      <td><strong>{boq.boq_number}</strong></td>
                      <td>{boq.title}</td>
                      <td>{contract?.contract_number || "Unknown contract"}</td>
                      <td>{project?.name || "Unknown project"}</td>
                      <td><span className={`boq-status status-${boq.status.toLowerCase()}`}>{boq.status}</span></td>
                      <td>{new Date(boq.updated_at).toLocaleDateString("en-IN")}</td>
                      <td><Link className="project-link" to={`/boqs/${boq.id}`}>View</Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showForm && (
        <div className="modal-backdrop boq-modal-backdrop">
          <div className="card modal boq-modal">
            <div className="modal-header">
              <div>
                <div className="eyebrow">BOQ Registration</div>
                <h2>Create BOQ</h2>
              </div>
              <button className="secondary" type="button" onClick={() => setShowForm(false)}>
                Close
              </button>
            </div>
            <form onSubmit={createBoq}>
              <div className="form-grid">
                <label>
                  Contract
                  <select
                    required
                    value={form.contract_id}
                    onChange={(event) => setForm({ ...form, contract_id: event.target.value })}
                  >
                    <option value="">Select contract</option>
                    {contracts.map((contract) => (
                      <option key={contract.id} value={contract.id}>
                        {contract.contract_number} — ₹{formatInrAsCrore(contract.contract_value)} Cr
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  BOQ Number
                  <input
                    required
                    minLength={1}
                    maxLength={100}
                    value={form.boq_number}
                    onChange={(event) => setForm({ ...form, boq_number: event.target.value })}
                    placeholder="BOQ-PWD-001"
                  />
                </label>
                <label>
                  Title
                  <input
                    required
                    minLength={1}
                    maxLength={255}
                    value={form.title}
                    onChange={(event) => setForm({ ...form, title: event.target.value })}
                    placeholder="Civil Works"
                  />
                </label>
                <label>
                  Description
                  <textarea
                    rows={4}
                    value={form.description}
                    onChange={(event) => setForm({ ...form, description: event.target.value })}
                    placeholder="Scope and measurement basis"
                  />
                </label>
              </div>
              <div className="form-actions">
                <button className="secondary" type="button" onClick={() => setShowForm(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={saving}>
                  {saving ? "Creating..." : "Create BOQ"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

export default BoqRegistry;
