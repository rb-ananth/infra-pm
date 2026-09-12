import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { measurementApi, getApiErrorMessage } from "../services/api";
import type { MeasurementDetail } from "../types";

type MeasurementDetailsProps = {
  role: string;
};

export default function MeasurementDetails({ role }: MeasurementDetailsProps) {
  const { measurementId } = useParams();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<MeasurementDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  // Edit Modal State
  const [showEditForm, setShowEditForm] = useState(false);
  const [editForm, setEditForm] = useState({
    measurement_date: "",
    quantity: "",
    reference: "",
    description: "",
    remarks: "",
  });

  async function loadData() {
    if (!measurementId) return;
    try {
      setLoading(true);
      setError("");
      const response = await measurementApi.get(measurementId);
      setDetail(response.data);
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to load measurement details."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [measurementId]);

  if (loading) {
    return (
      <section className="boq-page">
        <p className="muted">Loading measurement details...</p>
      </section>
    );
  }

  if (error || !detail) {
    return (
      <section className="boq-page">
        <div className="alert error">{error || "Measurement not found."}</div>
      </section>
    );
  }

  const { measurement, boq_item, cumulative_approved_quantity, balance_quantity, percentage_executed, is_overrun, overrun_quantity } = detail;

  const canEdit = ["Admin", "Project Manager", "Engineer"].includes(role) && ["Draft", "Rejected"].includes(measurement.status);
  const canSubmit = ["Admin", "Project Manager", "Engineer"].includes(role) && measurement.status === "Draft";
  const canApprove = ["Admin", "Project Manager"].includes(role) && measurement.status === "Submitted";
  const canReject = ["Admin", "Project Manager", "Engineer"].includes(role) && measurement.status === "Submitted";

  function openEditForm() {
    setEditForm({
      measurement_date: measurement.measurement_date,
      quantity: measurement.quantity,
      reference: measurement.reference,
      description: measurement.description,
      remarks: measurement.remarks || "",
    });
    setShowEditForm(true);
  }

  async function handleUpdate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!measurementId) return;
    try {
      setActionLoading(true);
      setError("");
      const payload = {
        measurement_date: editForm.measurement_date,
        quantity: editForm.quantity,
        reference: editForm.reference.trim(),
        description: editForm.description.trim(),
        remarks: editForm.remarks.trim() || undefined,
      };
      await measurementApi.update(measurementId, payload);
      setShowEditForm(false);
      await loadData();
    } catch (err) {
      setError(getApiErrorMessage(err, "Failed to update measurement."));
    } finally {
      setActionLoading(false);
    }
  }

  async function handleAction(action: "submit" | "approve" | "reject") {
    if (!measurementId) return;
    const confirmMessage = `Are you sure you want to ${action} this measurement?`;
    if (!window.confirm(confirmMessage)) return;

    try {
      setActionLoading(true);
      setError("");
      if (action === "submit") await measurementApi.submit(measurementId);
      if (action === "approve") await measurementApi.approve(measurementId);
      if (action === "reject") await measurementApi.reject(measurementId);
      await loadData();
    } catch (err) {
      setError(getApiErrorMessage(err, `Failed to ${action} measurement.`));
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <section className="boq-page">
      <div className="page-heading page-heading-row">
        <div>
          <div className="eyebrow">Measurement</div>
          <h1>{measurement.reference}</h1>
          <p className="muted">Detailed view and workflow actions.</p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {canEdit && <button className="secondary" onClick={openEditForm} disabled={actionLoading}>Edit</button>}
          {canSubmit && <button onClick={() => handleAction("submit")} disabled={actionLoading}>Submit</button>}
          {canApprove && <button onClick={() => handleAction("approve")} disabled={actionLoading}>Approve</button>}
          {canReject && <button className="danger" onClick={() => handleAction("reject")} disabled={actionLoading}>Reject</button>}
        </div>
      </div>

      {is_overrun && (
        <div className="alert warning">
          <strong>Overrun Detected:</strong> This measurement contributes to an overrun of {overrun_quantity} {boq_item.unit}.
        </div>
      )}

      {error && <div className="alert error">{error}</div>}

      <div className="stats-grid">
        <div className="card stat-card">
          <div className="stat-label">Status</div>
          <div className="stat-value">
            <span className={`boq-status status-${measurement.status.toLowerCase()}`}>
              {measurement.status}
            </span>
          </div>
        </div>
        <div className="card stat-card">
          <div className="stat-label">Percentage Executed</div>
          <div className="stat-value">{percentage_executed}%</div>
        </div>
        <div className="card stat-card">
          <div className="stat-label">Measurement Qty</div>
          <div className="stat-value">{measurement.quantity}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-label">Balance Qty</div>
          <div className="stat-value">{balance_quantity}</div>
        </div>
      </div>

      <div className="details-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginTop: "1.5rem" }}>
        <section className="card">
          <h3>Measurement Information</h3>
          <dl className="details-list">
            <dt>Measurement Date</dt>
            <dd>{new Date(measurement.measurement_date).toLocaleDateString("en-IN")}</dd>
            
            <dt>Reference</dt>
            <dd>{measurement.reference}</dd>
            
            <dt>Description</dt>
            <dd>{measurement.description}</dd>
            
            <dt>Remarks</dt>
            <dd>{measurement.remarks || "-"}</dd>
            
            <dt>Created At</dt>
            <dd>{new Date(measurement.created_at).toLocaleString("en-IN")}</dd>
          </dl>
        </section>

        <section className="card">
          <h3>BOQ Item Context</h3>
          <dl className="details-list">
            <dt>Item Number</dt>
            <dd>{boq_item.item_number} ({boq_item.item_code})</dd>
            
            <dt>Description</dt>
            <dd>{boq_item.description}</dd>
            
            <dt>Unit</dt>
            <dd>{boq_item.unit}</dd>
            
            <dt>BOQ Quantity</dt>
            <dd>{boq_item.quantity}</dd>
            
            <dt>Cumulative Approved Qty</dt>
            <dd>{cumulative_approved_quantity}</dd>
          </dl>
        </section>
      </div>

      {showEditForm && (
        <div className="modal-backdrop boq-modal-backdrop">
          <div className="card modal boq-modal">
            <div className="modal-header">
              <div>
                <div className="eyebrow">Measurement</div>
                <h2>Edit Measurement</h2>
              </div>
              <button className="secondary" type="button" onClick={() => setShowEditForm(false)}>
                Close
              </button>
            </div>
            <form onSubmit={handleUpdate}>
              <div className="form-grid">
                <label>
                  Measurement Date
                  <input
                    required
                    type="date"
                    value={editForm.measurement_date}
                    onChange={(e) => setEditForm({ ...editForm, measurement_date: e.target.value })}
                  />
                </label>

                <label>
                  Quantity
                  <input
                    required
                    type="number"
                    step="0.001"
                    min="0"
                    value={editForm.quantity}
                    onChange={(e) => setEditForm({ ...editForm, quantity: e.target.value })}
                  />
                </label>

                <label>
                  Reference
                  <input
                    required
                    maxLength={255}
                    value={editForm.reference}
                    onChange={(e) => setEditForm({ ...editForm, reference: e.target.value })}
                  />
                </label>

                <label style={{ gridColumn: "1 / -1" }}>
                  Description
                  <textarea
                    required
                    rows={2}
                    value={editForm.description}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  />
                </label>

                <label style={{ gridColumn: "1 / -1" }}>
                  Remarks (Optional)
                  <textarea
                    rows={2}
                    value={editForm.remarks}
                    onChange={(e) => setEditForm({ ...editForm, remarks: e.target.value })}
                  />
                </label>
              </div>
              <div className="form-actions">
                <button className="secondary" type="button" onClick={() => setShowEditForm(false)}>
                  Cancel
                </button>
                <button type="submit" disabled={actionLoading}>
                  {actionLoading ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
