import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { boqApi, getApiErrorMessage } from "../services/api";
import BoqImportWorkflow from "../components/BoqImportWorkflow";
import type { BoqItem, BoqRevisionDetail } from "../types";
import { formatInr, formatInrAsCrore } from "../utils/money";

type BoqRevisionDetailsProps = {
  role: string;
};

type ItemForm = {
  item_code: string;
  item_number: string;
  description: string;
  unit: string;
  quantity: string;
  rate: string;
};

const EMPTY_FORM: ItemForm = {
  item_code: "",
  item_number: "",
  description: "",
  unit: "",
  quantity: "",
  rate: "",
};

function validateDecimal(value: string, maxPlaces: number, label: string): string {
  if (!value.trim()) return `${label} is required.`;
  if (!/^\d+(\.\d+)?$/.test(value.trim())) return `${label} must be a nonnegative number.`;
  const [, fraction = ""] = value.trim().split(".");
  if (fraction.length > maxPlaces) return `${label} can have at most ${maxPlaces} decimal places.`;
  return "";
}

function BoqRevisionDetails({ role }: BoqRevisionDetailsProps) {
  const { boqId, revisionId } = useParams<{ boqId: string; revisionId: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<BoqRevisionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [editingItem, setEditingItem] = useState<BoqItem | null>(null);
  const [form, setForm] = useState<ItemForm>(EMPTY_FORM);

  const canWrite = role === "Admin" || role === "Project Manager";
  const isDraft = detail?.revision.status === "Draft";

  async function loadDetail() {
    if (!revisionId) {
      setError("Revision ID is missing.");
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      setError("");
      const response = await boqApi.getRevision(revisionId);
      setDetail(response.data);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load revision details."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDetail();
  }, [revisionId]);

  function openCreateForm() {
    setEditingItem(null);
    setForm(EMPTY_FORM);
    setError("");
    setShowForm(true);
  }

  function openEditForm(item: BoqItem) {
    setEditingItem(item);
    setForm({
      item_code: item.item_code,
      item_number: item.item_number,
      description: item.description,
      unit: item.unit,
      quantity: item.quantity,
      rate: item.rate,
    });
    setError("");
    setShowForm(true);
  }

  async function saveItem(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!revisionId) return;
    const requiredFields: Array<[keyof ItemForm, string]> = [
      ["item_code", "Item code"],
      ["item_number", "Item number"],
      ["description", "Description"],
      ["unit", "Unit"],
    ];
    for (const [field, label] of requiredFields) {
      if (!form[field].trim()) {
        setError(`${label} is required.`);
        return;
      }
    }
    const quantityError = validateDecimal(form.quantity, 3, "Quantity");
    const rateError = validateDecimal(form.rate, 2, "Rate");
    if (quantityError || rateError) {
      setError(quantityError || rateError);
      return;
    }

    try {
      setSaving(true);
      setError("");
      const payload = {
        item_code: form.item_code.trim(),
        item_number: form.item_number.trim(),
        description: form.description.trim(),
        unit: form.unit.trim(),
        quantity: form.quantity.trim(),
        rate: form.rate.trim(),
      };
      if (editingItem) {
        await boqApi.updateItem(editingItem.id, payload);
      } else {
        await boqApi.createItem(revisionId, payload);
      }
      setShowForm(false);
      setEditingItem(null);
      await loadDetail();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, editingItem ? "Unable to update item." : "Unable to add item."));
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(status: "Submitted" | "Approved") {
    if (!revisionId) return;
    const label = status === "Submitted" ? "submit" : "approve";
    if (!window.confirm(`Are you sure you want to ${label} this revision?`)) return;
    try {
      setSaving(true);
      setError("");
      await boqApi.updateRevision(revisionId, { status });
      await loadDetail();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, `Unable to ${label} revision.`));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="muted">Loading revision...</p>;
  }

  if (error && !detail) {
    return (
      <section className="card">
        <p className="error">{error}</p>
        <Link to={`/boqs/${boqId || ""}`} className="back-link">← BOQ Details</Link>
      </section>
    );
  }

  if (!detail) return null;

  const { boq, revision, items, total } = detail;

  return (
    <section className="boq-page">
      <div className="page-heading">
        <Link to={`/boqs/${boq.id}`} className="back-link">← {boq.boq_number}</Link>
        <div className="boq-header-grid">
          <div>
            <div className="eyebrow">BOQ Revision {revision.revision_number}</div>
            <h1>{boq.title}</h1>
            <p className="muted">{revision.revision_date}{revision.remarks ? ` · ${revision.remarks}` : ""}</p>
          </div>
          <span className={`boq-status status-${revision.status.toLowerCase()}`}>{revision.status}</span>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      <section className="revision-summary">
        <div className="revision-summary-copy">
          <div className="eyebrow">Controlled Revision</div>
          <strong>Revision {revision.revision_number}</strong>
          <span className="muted">{isDraft ? "Items remain editable until submission." : "Items are locked for this revision."}</span>
        </div>
        <div className="revision-total">
          <span className="muted">Revision Total</span>
          <strong>₹{formatInr(total)}</strong>
          <small>₹{formatInrAsCrore(total)} Cr</small>
        </div>
        <div className="revision-actions">
          {canWrite && isDraft && (
            <>
              <button type="button" className="secondary" onClick={() => setShowImport(true)}>Import BOQ Items</button>
              <button type="button" onClick={openCreateForm}>+ Add Item</button>
              <button type="button" className="secondary" disabled={saving} onClick={() => changeStatus("Submitted")}>Submit Revision</button>
            </>
          )}
          {canWrite && revision.status === "Submitted" && (
            <button type="button" disabled={saving} onClick={() => changeStatus("Approved")}>Approve Revision</button>
          )}
        </div>
      </section>

      <section className="card">
        <div className="section-title">
          <div>
            <div className="eyebrow">Measured Scope Basis</div>
            <h2>BOQ Items</h2>
            <p className="muted">Rates are INR. Amounts are calculated and returned by the API.</p>
          </div>
          <span className="muted">{items.length} item{items.length === 1 ? "" : "s"}</span>
        </div>

        {items.length === 0 ? (
          <p className="muted empty-state">No items in this revision.</p>
        ) : (
          <div className="table-wrap">
            <table className="boq-items-table">
              <thead>
                <tr><th>#</th><th>Item Code</th><th>Description</th><th>Unit</th><th>Quantity</th><th>Rate (₹)</th><th>Amount (₹)</th>{isDraft && canWrite && <th>Actions</th>}</tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.item_number}</strong></td>
                    <td>{item.item_code}</td>
                    <td>{item.description}</td>
                    <td>{item.unit}</td>
                    <td>{item.quantity}</td>
                    <td className="money-cell">₹{formatInr(item.rate)}</td>
                    <td className="money-cell"><strong>₹{formatInr(item.amount)}</strong></td>
                    {isDraft && canWrite && <td><button type="button" className="table-action" onClick={() => openEditForm(item)}>Edit</button></td>}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><td colSpan={isDraft && canWrite ? 6 : 5}>Total</td><td className="money-cell"><strong>₹{formatInr(total)}</strong></td>{isDraft && canWrite && <td />}</tr>
              </tfoot>
            </table>
          </div>
        )}
      </section>

      {showForm && (
        <div className="modal-backdrop boq-modal-backdrop">
          <div className="card modal boq-modal">
            <div className="modal-header">
              <div><div className="eyebrow">{editingItem ? "Draft Item" : "New BOQ Item"}</div><h2>{editingItem ? `Edit Item ${editingItem.item_number}` : "Add Item"}</h2></div>
              <button className="secondary" type="button" onClick={() => setShowForm(false)}>Close</button>
            </div>
            <form onSubmit={saveItem}>
              <div className="form-grid">
                <label>Item Code<input required value={form.item_code} onChange={(event) => setForm({ ...form, item_code: event.target.value })} placeholder="CIV-001" /></label>
                <label>Item Number<input required value={form.item_number} onChange={(event) => setForm({ ...form, item_number: event.target.value })} placeholder="1.1" /></label>
                <label>Description<textarea required rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Reinforced concrete work" /></label>
                <label>Unit<input required value={form.unit} onChange={(event) => setForm({ ...form, unit: event.target.value })} placeholder="Cum, Sqm, Nos" /></label>
                <label>Quantity<input required min="0" step="0.001" inputMode="decimal" value={form.quantity} onChange={(event) => setForm({ ...form, quantity: event.target.value })} /></label>
                <label>Rate (₹ INR)<input required min="0" step="0.01" inputMode="decimal" value={form.rate} onChange={(event) => setForm({ ...form, rate: event.target.value })} /></label>
              </div>
              <p className="form-note">Amount is calculated by the server from quantity × rate.</p>
              <div className="form-actions">
                <button className="secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" disabled={saving}>{saving ? "Saving..." : editingItem ? "Update Item" : "Add Item"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showImport && revisionId && (
        <BoqImportWorkflow
          revisionId={revisionId}
          onClose={() => setShowImport(false)}
          onImported={loadDetail}
        />
      )}
    </section>
  );
}

export default BoqRevisionDetails;
