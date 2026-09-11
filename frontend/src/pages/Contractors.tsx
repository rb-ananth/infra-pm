import { useEffect, useMemo, useState } from "react";
import api from "../services/api";
import type { Contractor, User } from "../types";

type ContractorForm = {
  registration_number: string;
  name: string;
  status: string;
};

function Contractors() {
  const [contractors, setContractors] = useState<Contractor[]>([]);
  const [user, setUser] = useState<User | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");

  const [showForm, setShowForm] = useState(false);
  const [editingContractor, setEditingContractor] =
    useState<Contractor | null>(null);

  const [form, setForm] = useState<ContractorForm>({
    registration_number: "",
    name: "",
    status: "Active",
  });

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [contractorsResponse, userResponse] = await Promise.all([
        api.get("/contractors"),
        api.get("/users/me"),
      ]);

      setContractors(contractorsResponse.data);
      setUser(userResponse.data);
    } catch {
      setError("Unable to load contractor registry.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const filteredContractors = useMemo(() => {
    const query = search.trim().toLowerCase();

    return contractors.filter((contractor) => {
      const matchesSearch =
        !query ||
        contractor.registration_number.toLowerCase().includes(query) ||
        contractor.name.toLowerCase().includes(query);

      const matchesStatus =
        statusFilter === "All" || contractor.status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [contractors, search, statusFilter]);

  const statuses = useMemo(
    () => ["All", ...new Set(contractors.map((contractor) => contractor.status))],
    [contractors],
  );

  function resetForm() {
    setForm({
      registration_number: "",
      name: "",
      status: "Active",
    });
    setEditingContractor(null);
    setShowForm(false);
  }

  function startCreate() {
    setSuccess("");
    setError("");
    setEditingContractor(null);
    setForm({
      registration_number: "",
      name: "",
      status: "Active",
    });
    setShowForm(true);
  }

  function startEdit(contractor: Contractor) {
    setSuccess("");
    setError("");
    setEditingContractor(contractor);
    setForm({
      registration_number: contractor.registration_number,
      name: contractor.name,
      status: contractor.status,
    });
    setShowForm(true);
  }

  async function saveContractor(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setSaving(true);
      setError("");
      setSuccess("");

      if (editingContractor) {
        await api.put(`/contractors/${editingContractor.id}`, {
          name: form.name,
          status: form.status,
        });

        setSuccess("Contractor updated successfully.");
      } else {
        await api.post("/contractors", form);
        setSuccess("Contractor created successfully.");
      }

      resetForm();
      await loadData();
    } catch (requestError: any) {
      const detail = requestError?.response?.data?.detail;

      setError(
        detail ||
          (editingContractor
            ? "Unable to update contractor."
            : "Unable to create contractor."),
      );
    } finally {
      setSaving(false);
    }
  }

  const isAdmin = user?.role === "Admin";

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">Master Data</div>
          <h1>Contractor Registry</h1>
          <p className="muted">
            Manage contractors participating in infrastructure projects.
          </p>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}
      {success && <div className="alert success">{success}</div>}

      <section className="card">
        <div className="registry-toolbar">
          <div className="search-group">
            <input
              type="text"
              placeholder="Search contractor or registration number..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />

            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              {statuses.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </div>

          {isAdmin && (
            <button type="button" onClick={startCreate}>
              + Add Contractor
            </button>
          )}
        </div>
      </section>

      {showForm && isAdmin && (
        <section className="card form-card">
          <div className="section-title">
            <div>
              <div className="eyebrow">
                {editingContractor ? "Edit Contractor" : "New Contractor"}
              </div>
              <h2>
                {editingContractor
                  ? editingContractor.registration_number
                  : "Contractor Registration"}
              </h2>
            </div>
          </div>

          <form onSubmit={saveContractor}>
            <div className="form-grid">
              <label>
                Registration Number
                <input
                  type="text"
                  value={form.registration_number}
                  disabled={Boolean(editingContractor)}
                  required
                  minLength={2}
                  maxLength={100}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      registration_number: event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Contractor Name
                <input
                  type="text"
                  value={form.name}
                  required
                  minLength={2}
                  maxLength={255}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      name: event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Status
                <select
                  value={form.status}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      status: event.target.value,
                    })
                  }
                >
                  <option value="Active">Active</option>
                  <option value="Suspended">Suspended</option>
                  <option value="Inactive">Inactive</option>
                </select>
              </label>
            </div>

            <div className="form-actions">
              <button type="submit" disabled={saving}>
                {saving
                  ? "Saving..."
                  : editingContractor
                    ? "Update Contractor"
                    : "Create Contractor"}
              </button>

              <button
                type="button"
                className="button-secondary"
                onClick={resetForm}
                disabled={saving}
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="card">
        <div className="section-title">
          <div>
            <h2>Registered Contractors</h2>
            <p className="muted">
              {filteredContractors.length} contractor
              {filteredContractors.length === 1 ? "" : "s"} shown.
            </p>
          </div>
        </div>

        {loading ? (
          <p className="muted">Loading contractors...</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Registration Number</th>
                  <th>Contractor</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Updated</th>
                  {isAdmin && <th>Actions</th>}
                </tr>
              </thead>

              <tbody>
                {filteredContractors.length === 0 ? (
                  <tr>
                    <td colSpan={isAdmin ? 6 : 5}>
                      <span className="muted">
                        No contractors match the current filters.
                      </span>
                    </td>
                  </tr>
                ) : (
                  filteredContractors.map((contractor) => (
                    <tr key={contractor.id}>
                      <td>
                        <strong>{contractor.registration_number}</strong>
                      </td>

                      <td>{contractor.name}</td>

                      <td>
                        <span className="status">{contractor.status}</span>
                      </td>

                      <td>
                        {new Date(contractor.created_at).toLocaleDateString()}
                      </td>

                      <td>
                        {new Date(contractor.updated_at).toLocaleDateString()}
                      </td>

                      {isAdmin && (
                        <td>
                          <button
                            type="button"
                            className="button-secondary"
                            onClick={() => startEdit(contractor)}
                          >
                            Edit
                          </button>
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export default Contractors;
