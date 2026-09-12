import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { measurementApi, boqApi, getApiErrorMessage } from "../services/api";
import type { Boq, BoqItem, Measurement } from "../types";

const MEASUREMENT_STATUSES = ["All", "Draft", "Submitted", "Approved", "Rejected"];

type MeasurementsProps = {
  role: string;
};

type MeasurementForm = {
  boq_id: string;
  boq_item_id: string;
  measurement_date: string;
  quantity: string;
  reference: string;
  description: string;
  remarks: string;
};

function Measurements({ role }: MeasurementsProps) {
  const navigate = useNavigate();
  
  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [boqs, setBoqs] = useState<Boq[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  
  // Filters
  const [boqItemFilter, setBoqItemFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // Create Modal State
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<MeasurementForm>({
    boq_id: "",
    boq_item_id: "",
    measurement_date: new Date().toISOString().slice(0, 10),
    quantity: "",
    reference: "",
    description: "",
    remarks: "",
  });

  // Modal contextual data
  const [formItems, setFormItems] = useState<BoqItem[]>([]);
  const [loadingItems, setLoadingItems] = useState(false);

  const canWrite = ["Admin", "Project Manager", "Engineer"].includes(role);

  async function loadMeasurements() {
    try {
      setLoading(true);
      setError("");
      
      const params: Record<string, string> = {};
      if (boqItemFilter.trim()) params.boq_item_id = boqItemFilter.trim();
      if (statusFilter !== "All") params.status = statusFilter;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;

      const [measRes, boqRes] = await Promise.all([
        measurementApi.list(params),
        boqApi.list()
      ]);
      setMeasurements(measRes.data);
      setBoqs(boqRes.data);
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to load measurements."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMeasurements();
  }, [boqItemFilter, statusFilter, dateFrom, dateTo]);

  // Load items when a BOQ is selected in the form
  useEffect(() => {
    async function loadFormItems() {
      if (!form.boq_id) {
        setFormItems([]);
        return;
      }
      try {
        setLoadingItems(true);
        const revisionsRes = await boqApi.listRevisions(form.boq_id);
        const approvedRev = revisionsRes.data.find(r => r.status === "Approved");
        if (approvedRev) {
          const itemsRes = await boqApi.listItems(approvedRev.id);
          setFormItems(itemsRes.data);
        } else {
          setFormItems([]);
        }
      } catch (err) {
        console.error("Failed to load BOQ items", err);
        setFormItems([]);
      } finally {
        setLoadingItems(false);
      }
    }
    loadFormItems();
  }, [form.boq_id]);

  function resetForm() {
    setForm({
      boq_id: "",
      boq_item_id: "",
      measurement_date: new Date().toISOString().slice(0, 10),
      quantity: "",
      reference: "",
      description: "",
      remarks: "",
    });
    setFormItems([]);
  }

  async function createMeasurement(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.boq_item_id || !form.measurement_date || !form.quantity || !form.reference || !form.description) {
      setError("Please fill in all required fields.");
      return;
    }

    try {
      setSaving(true);
      setError("");
      const payload = {
        boq_item_id: form.boq_item_id,
        measurement_date: form.measurement_date,
        quantity: form.quantity,
        reference: form.reference.trim(),
        description: form.description.trim(),
        ...(form.remarks.trim() ? { remarks: form.remarks.trim() } : {})
      };
      const response = await measurementApi.create(payload);
      resetForm();
      setShowForm(false);
      await loadMeasurements();
      navigate(`/measurements/${response.data.measurement.id}`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to create measurement."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="boq-page">
      <div className="page-heading page-heading-row">
        <div>
          <div className="eyebrow">Project Controls</div>
          <h1>Measurements</h1>
          <p className="muted">Manage and track BOQ measurements.</p>
        </div>
        {canWrite && (
          <button type="button" onClick={() => setShowForm(true)}>
            + Create Measurement
          </button>
        )}
      </div>

      {error && <div className="alert error">{error}</div>}

      <section className="card">
        <div className="registry-toolbar">
          <div>
            <strong>{measurements.length}</strong>
            <span className="muted"> Measurements found</span>
          </div>
          <div className="registry-filters">
            <input
              className="search-input"
              type="text"
              placeholder="BOQ Item ID..."
              value={boqItemFilter}
              onChange={(event) => setBoqItemFilter(event.target.value)}
              title="Filter by exact BOQ Item UUID"
            />
            <select
              className="filter-select"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              {MEASUREMENT_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status === "All" ? "All Statuses" : status}
                </option>
              ))}
            </select>
            <input 
              type="date" 
              className="filter-select" 
              value={dateFrom} 
              onChange={(e) => setDateFrom(e.target.value)}
              title="Date From"
            />
            <input 
              type="date" 
              className="filter-select" 
              value={dateTo} 
              onChange={(e) => setDateTo(e.target.value)}
              title="Date To"
            />
          </div>
        </div>

        {loading ? (
          <p className="muted">Loading Measurements...</p>
        ) : measurements.length === 0 ? (
          <p className="muted empty-state">No measurements found.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Quantity</th>
                  <th>Reference</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {measurements.map((meas) => (
                  <tr key={meas.id}>
                    <td>{new Date(meas.measurement_date).toLocaleDateString("en-IN")}</td>
                    <td>{meas.quantity}</td>
                    <td>{meas.reference}</td>
                    <td><span className={`boq-status status-${meas.status.toLowerCase()}`}>{meas.status}</span></td>
                    <td>{new Date(meas.created_at).toLocaleDateString("en-IN")}</td>
                    <td><Link className="project-link" to={`/measurements/${meas.id}`}>View</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showForm && (
        <div className="modal-backdrop boq-modal-backdrop">
          <div className="card modal boq-modal" style={{ maxWidth: "600px" }}>
            <div className="modal-header">
              <div>
                <div className="eyebrow">Measurement</div>
                <h2>Create Measurement</h2>
              </div>
              <button className="secondary" type="button" onClick={() => { setShowForm(false); resetForm(); }}>
                Close
              </button>
            </div>
            <form onSubmit={createMeasurement}>
              <div className="form-grid">
                <label>
                  BOQ (Approved)
                  <select
                    value={form.boq_id}
                    onChange={(event) => setForm({ ...form, boq_id: event.target.value, boq_item_id: "" })}
                  >
                    <option value="">Select an Approved BOQ</option>
                    {boqs.filter(b => b.status === "Approved").map((boq) => (
                      <option key={boq.id} value={boq.id}>
                        {boq.boq_number} - {boq.title}
                      </option>
                    ))}
                  </select>
                </label>

                {form.boq_id && (
                  <label>
                    BOQ Item
                    {loadingItems ? (
                      <div className="muted">Loading items...</div>
                    ) : (
                      <select
                        required
                        value={form.boq_item_id}
                        onChange={(event) => setForm({ ...form, boq_item_id: event.target.value })}
                      >
                        <option value="">Select BOQ Item</option>
                        {formItems.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.item_number} ({item.item_code}) - {item.description.substring(0, 30)}... | Unit: {item.unit} | BOQ Qty: {item.quantity}
                          </option>
                        ))}
                      </select>
                    )}
                  </label>
                )}

                <label>
                  Measurement Date
                  <input
                    required
                    type="date"
                    value={form.measurement_date}
                    onChange={(event) => setForm({ ...form, measurement_date: event.target.value })}
                  />
                </label>

                <label>
                  Quantity
                  <input
                    required
                    type="number"
                    step="0.001"
                    min="0"
                    value={form.quantity}
                    onChange={(event) => setForm({ ...form, quantity: event.target.value })}
                    placeholder="0.000"
                  />
                </label>

                <label>
                  Reference
                  <input
                    required
                    minLength={1}
                    maxLength={255}
                    value={form.reference}
                    onChange={(event) => setForm({ ...form, reference: event.target.value })}
                    placeholder="e.g. MB/24/01"
                  />
                </label>

                <label style={{ gridColumn: "1 / -1" }}>
                  Description
                  <textarea
                    required
                    rows={2}
                    value={form.description}
                    onChange={(event) => setForm({ ...form, description: event.target.value })}
                    placeholder="Measurement details"
                  />
                </label>
                
                <label style={{ gridColumn: "1 / -1" }}>
                  Remarks (Optional)
                  <textarea
                    rows={2}
                    value={form.remarks}
                    onChange={(event) => setForm({ ...form, remarks: event.target.value })}
                    placeholder="Additional notes"
                  />
                </label>
              </div>
              <div className="form-actions">
                <button className="secondary" type="button" onClick={() => { setShowForm(false); resetForm(); }}>
                  Cancel
                </button>
                <button type="submit" disabled={saving || !form.boq_item_id}>
                  {saving ? "Creating..." : "Create Measurement"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

export default Measurements;
