import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import api, { boqApi, getApiErrorMessage } from "../services/api";
import type { Boq, BoqRevision, Contract, Project } from "../types";
import { formatInr } from "../utils/money";

type BoqDetailsProps = {
  role: string;
};

type RevisionForm = {
  revision_number: string;
  revision_date: string;
  remarks: string;
};

function BoqDetails({ role }: BoqDetailsProps) {
  const { boqId } = useParams<{ boqId: string }>();
  const navigate = useNavigate();
  const [boq, setBoq] = useState<Boq | null>(null);
  const [revisions, setRevisions] = useState<BoqRevision[]>([]);
  const [revisionTotals, setRevisionTotals] = useState<Record<string, string>>({});
  const [contract, setContract] = useState<Contract | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState<RevisionForm>({
    revision_number: "1",
    revision_date: new Date().toISOString().slice(0, 10),
    remarks: "",
  });

  const canWrite = role === "Admin" || role === "Project Manager";

  async function loadData() {
    if (!boqId) {
      setError("BOQ ID is missing.");
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      setError("");
      const [boqResponse, revisionsResponse, contractsResponse, projectsResponse] = await Promise.all([
        boqApi.get(boqId),
        boqApi.listRevisions(boqId),
        boqApi.listContracts(),
        api.get<Project[]>("/projects/"),
      ]);
      const loadedBoq = boqResponse.data;
      const loadedContract = contractsResponse.data.find((item) => item.id === loadedBoq.contract_id) || null;
      const revisionDetails = await Promise.all(
        revisionsResponse.data.map((revision) => boqApi.getRevision(revision.id)),
      );
      const totals = Object.fromEntries(
        revisionDetails.map((response) => [response.data.revision.id, response.data.total]),
      );
      setBoq(loadedBoq);
      setRevisions(revisionsResponse.data);
      setRevisionTotals(totals);
      setContract(loadedContract);
      setProject(loadedContract ? projectsResponse.data.find((item) => item.id === loadedContract.project_id) || null : null);
      const nextRevision = revisionsResponse.data.reduce(
        (highest, revision) => Math.max(highest, revision.revision_number),
        0,
      ) + 1;
      setForm((current) => ({ ...current, revision_number: String(nextRevision) }));
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load BOQ details."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [boqId]);

  const latestRevisionId = useMemo(
    () => revisions.reduce<BoqRevision | null>((latest, revision) =>
      !latest || revision.revision_number > latest.revision_number ? revision : latest, null)?.id,
    [revisions],
  );

  async function createRevision(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!boqId || !form.revision_date || !form.revision_number) {
      setError("Revision number and date are required.");
      return;
    }
    const revisionNumber = Number.parseInt(form.revision_number, 10);
    if (!Number.isInteger(revisionNumber) || revisionNumber < 1) {
      setError("Revision number must be a whole number of at least 1.");
      return;
    }
    try {
      setSaving(true);
      setError("");
      const response = await boqApi.createRevision(boqId, {
        revision_number: revisionNumber,
        revision_date: form.revision_date,
        ...(form.remarks.trim() ? { remarks: form.remarks.trim() } : {}),
      });
      setShowForm(false);
      await loadData();
      navigate(`/boqs/${boqId}/revisions/${response.data.id}`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to create revision."));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="muted">Loading BOQ details...</p>;
  }

  if (error || !boq) {
    return (
      <section className="card">
        <p className="error">{error || "BOQ not found."}</p>
        <Link to="/boqs" className="back-link">← BOQ Registry</Link>
      </section>
    );
  }

  return (
    <section className="boq-page">
      <div className="page-heading">
        <Link to="/boqs" className="back-link">← BOQ Registry</Link>
        <div className="boq-header-grid">
          <div>
            <div className="eyebrow">Bill of Quantities</div>
            <h1>{boq.title}</h1>
            <p className="muted">{boq.boq_number}</p>
          </div>
          <span className={`boq-status status-${boq.status.toLowerCase()}`}>{boq.status}</span>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      <section className="stats boq-context-stats">
        <div className="card"><span>Contract</span><strong>{contract?.contract_number || "Unknown"}</strong></div>
        <div className="card"><span>Project</span><strong>{project?.name || "Unknown"}</strong></div>
        <div className="card"><span>Created</span><strong>{new Date(boq.created_at).toLocaleDateString("en-IN")}</strong></div>
        <div className="card"><span>Updated</span><strong>{new Date(boq.updated_at).toLocaleDateString("en-IN")}</strong></div>
      </section>

      {boq.description && (
        <section className="card boq-description-card">
          <div className="eyebrow">Scope</div>
          <p>{boq.description}</p>
        </section>
      )}

      <section className="card">
        <div className="section-title">
          <div>
            <div className="eyebrow">Controlled History</div>
            <h2>BOQ Revisions</h2>
            <p className="muted">Draft revisions can be edited until submitted.</p>
          </div>
          {canWrite && (
            <button type="button" onClick={() => setShowForm(true)}>
              + New Revision
            </button>
          )}
        </div>

        {revisions.length === 0 ? (
          <p className="muted empty-state">No revisions found.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Revision</th><th>Date</th><th>Status</th><th>Remarks</th><th>Total</th><th>Action</th></tr>
              </thead>
              <tbody>
                {revisions.map((revision) => (
                  <tr key={revision.id} className={revision.id === latestRevisionId ? "current-row" : undefined}>
                    <td><strong>Rev {revision.revision_number}</strong>{revision.id === latestRevisionId && <span className="current-label">Current</span>}</td>
                    <td>{new Date(`${revision.revision_date}T00:00:00`).toLocaleDateString("en-IN")}</td>
                    <td><span className={`boq-status status-${revision.status.toLowerCase()}`}>{revision.status}</span></td>
                    <td>{revision.remarks || "—"}</td>
                    <td className="money-cell">
                      {revisionTotals[revision.id]
                        ? `₹${formatInr(revisionTotals[revision.id])}`
                        : "—"}
                    </td>
                    <td><Link className="project-link" to={`/boqs/${boq.id}/revisions/${revision.id}`}>Open</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showForm && (
        <div className="modal-backdrop boq-modal-backdrop">
          <div className="card modal boq-modal">
            <div className="modal-header">
              <div><div className="eyebrow">Controlled Change</div><h2>New Revision</h2></div>
              <button className="secondary" type="button" onClick={() => setShowForm(false)}>Close</button>
            </div>
            <form onSubmit={createRevision}>
              <div className="form-grid">
                <label>Revision Number<input required min="1" step="1" type="number" value={form.revision_number} onChange={(event) => setForm({ ...form, revision_number: event.target.value })} /></label>
                <label>Revision Date<input required type="date" value={form.revision_date} onChange={(event) => setForm({ ...form, revision_date: event.target.value })} /></label>
                <label>Remarks<textarea rows={4} value={form.remarks} onChange={(event) => setForm({ ...form, remarks: event.target.value })} placeholder="Revision basis or approval note" /></label>
              </div>
              <div className="form-actions">
                <button className="secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" disabled={saving}>{saving ? "Creating..." : "Create Revision"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

export default BoqDetails;
