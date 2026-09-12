import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from "recharts";

import api, { evmApi, getApiErrorMessage } from "../services/api";
import type {
  EVMResponse,
  EVMTrendPoint,
  EVMBaseline,
  EVMBaselinePeriod,
  Project
} from "../types";
import { formatInrAsCrore, formatInr } from "../utils/money";

type EVMProps = {
  role: string;
};

export default function EVM({ role }: EVMProps) {
  const { projectId } = useParams<{ projectId: string }>();

  const [project, setProject] = useState<Project | null>(null);
  const [asOfDate, setAsOfDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  
  const [evmSummary, setEvmSummary] = useState<EVMResponse | null>(null);
  const [trend, setTrend] = useState<EVMTrendPoint[]>([]);
  const [baselines, setBaselines] = useState<EVMBaseline[]>([]);
  const [activeBaseline, setActiveBaseline] = useState<EVMBaseline | null>(null);
  const [periods, setPeriods] = useState<EVMBaselinePeriod[]>([]);

  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [error, setError] = useState("");

  const canEdit = role === "Admin" || role === "Project Manager";

  // Forms states
  const [showCreateBaseline, setShowCreateBaseline] = useState(false);
  const [newBaseline, setNewBaseline] = useState({ baseline_number: "", name: "", effective_date: "", remarks: "" });
  
  const [showEditBaseline, setShowEditBaseline] = useState(false);
  const [editBaselineData, setEditBaselineData] = useState<{ id: string; name: string; effective_date: string; remarks: string }>({ id: "", name: "", effective_date: "", remarks: "" });

  const [showAddPeriod, setShowAddPeriod] = useState(false);
  const [newPeriod, setNewPeriod] = useState({ period_date: "", planned_percentage: "" });

  const [showEditPeriod, setShowEditPeriod] = useState(false);
  const [editPeriodData, setEditPeriodData] = useState<{ id: string; period_date: string; planned_percentage: string }>({ id: "", period_date: "", planned_percentage: "" });

  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    if (!projectId) return;
    loadInitialData();
  }, [projectId]);

  useEffect(() => {
    if (projectId) {
      loadSummaryAndTrend();
    }
  }, [projectId, asOfDate]);

  async function loadInitialData() {
    try {
      setLoading(true);
      setError("");

      const [projRes, baselinesRes] = await Promise.all([
        api.get(`/projects/${projectId}`),
        evmApi.listBaselines(projectId!)
      ]);

      setProject(projRes.data);
      setBaselines(baselinesRes.data);
      
      const approved = baselinesRes.data.find((b: EVMBaseline) => b.status === "Approved");
      if (approved) {
        loadBaselineDetails(approved);
      } else if (baselinesRes.data.length > 0) {
        loadBaselineDetails(baselinesRes.data[0]);
      }
    } catch (err) {
      setError(getApiErrorMessage(err, "Failed to load EVM data."));
    } finally {
      setLoading(false);
    }
  }

  async function loadSummaryAndTrend() {
    try {
      setSummaryLoading(true);
      const [summaryRes, trendRes] = await Promise.all([
        evmApi.getEvm(projectId!, asOfDate),
        evmApi.getTrend(projectId!)
      ]);
      setEvmSummary(summaryRes.data);
      setTrend(trendRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setSummaryLoading(false);
    }
  }

  async function loadBaselineDetails(b: EVMBaseline) {
    setActiveBaseline(b);
    try {
      const res = await evmApi.listPeriods(b.id);
      setPeriods(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleCreateBaseline(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId) return;
    try {
      setSubmitting(true);
      setActionError("");
      const res = await evmApi.createBaseline(projectId, newBaseline);
      const created = res.data;
      setBaselines([...baselines, created]);
      setShowCreateBaseline(false);
      setNewBaseline({ baseline_number: "", name: "", effective_date: "", remarks: "" });
      loadBaselineDetails(created);
    } catch (err) {
      setActionError(getApiErrorMessage(err, "Failed to create baseline."));
    } finally {
      setSubmitting(false);
    }
  }

  function openEditBaseline(b: EVMBaseline) {
    setEditBaselineData({ id: b.id, name: b.name, effective_date: b.effective_date, remarks: b.remarks || "" });
    setShowEditBaseline(true);
  }

  async function handleEditBaseline(e: React.FormEvent) {
    e.preventDefault();
    try {
      setSubmitting(true);
      setActionError("");
      const res = await evmApi.updateBaseline(editBaselineData.id, {
        name: editBaselineData.name,
        effective_date: editBaselineData.effective_date,
        remarks: editBaselineData.remarks || undefined
      });
      setBaselines(baselines.map(b => b.id === editBaselineData.id ? res.data : b));
      if (activeBaseline?.id === editBaselineData.id) {
        setActiveBaseline(res.data);
      }
      setShowEditBaseline(false);
    } catch (err) {
      setActionError(getApiErrorMessage(err, "Failed to update baseline."));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApprove(baselineId: string) {
    if (!window.confirm("Are you sure you want to approve this baseline?")) return;
    try {
      setSubmitting(true);
      setActionError("");
      const res = await evmApi.approveBaseline(baselineId);
      setBaselines(baselines.map(b => b.id === baselineId ? res.data : b));
      setActiveBaseline(res.data);
      loadSummaryAndTrend();
    } catch (err) {
      alert(getApiErrorMessage(err, "Failed to approve baseline."));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSupersede(baselineId: string) {
    if (!window.confirm("Are you sure you want to supersede this baseline?")) return;
    try {
      setSubmitting(true);
      setActionError("");
      const res = await evmApi.supersedeBaseline(baselineId);
      setBaselines(baselines.map(b => b.id === baselineId ? res.data : b));
      setActiveBaseline(res.data);
      loadSummaryAndTrend();
    } catch (err) {
      alert(getApiErrorMessage(err, "Failed to supersede baseline."));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAddPeriod(e: React.FormEvent) {
    e.preventDefault();
    if (!activeBaseline) return;
    try {
      setSubmitting(true);
      setActionError("");
      const res = await evmApi.addPeriod(activeBaseline.id, newPeriod);
      const newPeriods = [...periods, res.data].sort((a, b) => a.period_date.localeCompare(b.period_date));
      setPeriods(newPeriods);
      setShowAddPeriod(false);
      setNewPeriod({ period_date: "", planned_percentage: "" });
      loadSummaryAndTrend();
    } catch (err) {
      setActionError(getApiErrorMessage(err, "Failed to add period."));
    } finally {
      setSubmitting(false);
    }
  }

  function openEditPeriod(p: EVMBaselinePeriod) {
    setEditPeriodData({ id: p.id, period_date: p.period_date, planned_percentage: p.planned_percentage });
    setShowEditPeriod(true);
  }

  async function handleEditPeriod(e: React.FormEvent) {
    e.preventDefault();
    try {
      setSubmitting(true);
      setActionError("");
      const res = await evmApi.updatePeriod(editPeriodData.id, {
        period_date: editPeriodData.period_date,
        planned_percentage: editPeriodData.planned_percentage
      });
      const newPeriods = periods.map(p => p.id === editPeriodData.id ? res.data : p).sort((a, b) => a.period_date.localeCompare(b.period_date));
      setPeriods(newPeriods);
      setShowEditPeriod(false);
      loadSummaryAndTrend();
    } catch (err) {
      setActionError(getApiErrorMessage(err, "Failed to update period."));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <p className="muted">Loading EVM data...</p>;
  if (error || !project) return <p className="error">{error || "Project not found"}</p>;

  return (
    <>
      <div className="page-heading">
        <Link to={`/projects/${projectId}`} className="back-link">
          ← Back to Project
        </Link>
        <div className="eyebrow">Project Controls</div>
        <h1>Earned Value Management</h1>
      </div>

      <div className="card" style={{ marginBottom: '2rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
        <strong>As Of Date:</strong>
        <input 
          type="date" 
          value={asOfDate} 
          onChange={e => setAsOfDate(e.target.value)} 
          style={{ width: 'auto' }}
        />
        {summaryLoading && <span className="muted">Recalculating...</span>}
      </div>

      {evmSummary && (
        <>
          <section className="stats" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <div className="card">
              <span>Planned Value (PV)</span>
              <strong>₹{formatInrAsCrore(evmSummary.pv)} Cr</strong>
            </div>
            <div className="card">
              <span>Earned Value (EV)</span>
              <strong>₹{formatInrAsCrore(evmSummary.ev)} Cr</strong>
            </div>
            <div className="card">
              <span>Actual Cost (AC)</span>
              <strong>₹{formatInrAsCrore(evmSummary.ac)} Cr</strong>
            </div>
            <div className="card">
              <span>SPI / CPI</span>
              <strong>
                {evmSummary.spi !== null ? evmSummary.spi : 'N/A'} / {evmSummary.cpi !== null ? evmSummary.cpi : 'N/A'}
              </strong>
            </div>
          </section>

          <section className="stats" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <div className="card">
              <span>Schedule Variance (SV)</span>
              <strong className={!evmSummary.sv.startsWith('-') ? 'success' : 'error'}>
                ₹{formatInrAsCrore(evmSummary.sv)} Cr
              </strong>
            </div>
            <div className="card">
              <span>Cost Variance (CV)</span>
              <strong className={!evmSummary.cv.startsWith('-') ? 'success' : 'error'}>
                ₹{formatInrAsCrore(evmSummary.cv)} Cr
              </strong>
            </div>
            <div className="card">
              <span>Schedule Status</span>
              <strong>{evmSummary.schedule_status}</strong>
            </div>
            <div className="card">
              <span>Cost Status</span>
              <strong>{evmSummary.cost_status}</strong>
            </div>
          </section>

          <section className="card" style={{ marginBottom: '2rem' }}>
            <div className="section-title">
              <h2>EVM Trend</h2>
            </div>
            <div style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis 
                    tickFormatter={(val) => `₹${formatInrAsCrore(String(val))}Cr`} 
                    width={80}
                  />
                  <Tooltip 
                    formatter={(value: any) => [`₹${formatInrAsCrore(String(value))} Cr`]}
                    labelFormatter={(label) => `Date: ${label}`}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="pv" name="Planned Value" stroke="#3b82f6" activeDot={{ r: 8 }} />
                  <Line type="monotone" dataKey="ev" name="Earned Value" stroke="#10b981" />
                  <Line type="monotone" dataKey="ac" name="Actual Cost" stroke="#ef4444" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        </>
      )}

      <section className="card">
        <div className="section-title">
          <h2>Baselines</h2>
          {canEdit && (
            <button onClick={() => { setActionError(""); setShowCreateBaseline(true); }}>Create Baseline</button>
          )}
        </div>

        {baselines.length === 0 ? (
          <p className="muted">No baselines configured yet.</p>
        ) : (
          <div style={{ display: 'flex', gap: '1rem', overflowX: 'auto', paddingBottom: '1rem' }}>
            {baselines.map(b => (
              <div 
                key={b.id} 
                className={`card ${activeBaseline?.id === b.id ? 'active' : ''}`}
                style={{ cursor: 'pointer', minWidth: '250px', border: activeBaseline?.id === b.id ? '2px solid var(--accent)' : '' }}
              >
                <div onClick={() => loadBaselineDetails(b)}>
                  <strong>{b.name}</strong> ({b.baseline_number})
                  <br/>
                  <span className={`status ${b.status === 'Approved' ? 'success' : ''}`}>{b.status}</span>
                </div>
                {canEdit && b.status === "Draft" && (
                  <button className="secondary" style={{ marginTop: '0.5rem', width: '100%' }} onClick={(e) => { e.stopPropagation(); setActionError(""); openEditBaseline(b); }}>
                    Edit Baseline
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {activeBaseline && (
        <section className="card">
          <div className="section-title">
            <div>
              <h3>Periods for {activeBaseline.name}</h3>
              <p className="muted">Status: {activeBaseline.status}</p>
            </div>
            {canEdit && activeBaseline.status === 'Draft' && (
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button onClick={() => { setActionError(""); setShowAddPeriod(true); }}>Add Period</button>
                <button className="success" onClick={() => handleApprove(activeBaseline.id)} disabled={submitting}>Approve</button>
              </div>
            )}
            {canEdit && activeBaseline.status === 'Approved' && (
              <button className="warning" onClick={() => handleSupersede(activeBaseline.id)} disabled={submitting}>Supersede</button>
            )}
          </div>

          {periods.length === 0 ? (
            <p className="muted">No periods defined.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Period Date</th>
                  <th>Planned %</th>
                  <th className="right">Planned Value (₹)</th>
                  {canEdit && activeBaseline.status === 'Draft' && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {periods.map(p => (
                  <tr key={p.id}>
                    <td>{p.period_date}</td>
                    <td>{p.planned_percentage}%</td>
                    <td className="right">{formatInr(p.planned_value)}</td>
                    {canEdit && activeBaseline.status === 'Draft' && (
                      <td>
                        <button className="secondary" onClick={() => { setActionError(""); openEditPeriod(p); }}>Edit</button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {/* Modals */}
      {showCreateBaseline && (
        <div className="modal">
          <div className="modal-content">
            <h3>Create Baseline</h3>
            <form onSubmit={handleCreateBaseline}>
              <label>
                Baseline Number
                <input required value={newBaseline.baseline_number} onChange={e => setNewBaseline({...newBaseline, baseline_number: e.target.value})} />
              </label>
              <label>
                Name
                <input required value={newBaseline.name} onChange={e => setNewBaseline({...newBaseline, name: e.target.value})} />
              </label>
              <label>
                Effective Date
                <input type="date" required value={newBaseline.effective_date} onChange={e => setNewBaseline({...newBaseline, effective_date: e.target.value})} />
              </label>
              <label>
                Remarks
                <input value={newBaseline.remarks} onChange={e => setNewBaseline({...newBaseline, remarks: e.target.value})} />
              </label>
              {actionError && <p className="error">{actionError}</p>}
              <div className="actions">
                <button type="button" className="secondary" onClick={() => setShowCreateBaseline(false)}>Cancel</button>
                <button type="submit" disabled={submitting}>{submitting ? 'Creating...' : 'Create'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showEditBaseline && (
        <div className="modal">
          <div className="modal-content">
            <h3>Edit Baseline</h3>
            <form onSubmit={handleEditBaseline}>
              <label>
                Name
                <input required value={editBaselineData.name} onChange={e => setEditBaselineData({...editBaselineData, name: e.target.value})} />
              </label>
              <label>
                Effective Date
                <input type="date" required value={editBaselineData.effective_date} onChange={e => setEditBaselineData({...editBaselineData, effective_date: e.target.value})} />
              </label>
              <label>
                Remarks
                <input value={editBaselineData.remarks} onChange={e => setEditBaselineData({...editBaselineData, remarks: e.target.value})} />
              </label>
              {actionError && <p className="error">{actionError}</p>}
              <div className="actions">
                <button type="button" className="secondary" onClick={() => setShowEditBaseline(false)}>Cancel</button>
                <button type="submit" disabled={submitting}>{submitting ? 'Saving...' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showAddPeriod && activeBaseline && (
        <div className="modal">
          <div className="modal-content">
            <h3>Add Period to {activeBaseline.name}</h3>
            <form onSubmit={handleAddPeriod}>
              <label>
                Period Date
                <input type="date" required value={newPeriod.period_date} onChange={e => setNewPeriod({...newPeriod, period_date: e.target.value})} />
              </label>
              <label>
                Planned Percentage (0-100)
                <input 
                  type="number" 
                  step="0.0001" 
                  min="0" 
                  max="100"
                  required 
                  value={newPeriod.planned_percentage} 
                  onChange={e => setNewPeriod({...newPeriod, planned_percentage: e.target.value})} 
                />
              </label>
              {actionError && <p className="error">{actionError}</p>}
              <div className="actions">
                <button type="button" className="secondary" onClick={() => setShowAddPeriod(false)}>Cancel</button>
                <button type="submit" disabled={submitting}>{submitting ? 'Adding...' : 'Add'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showEditPeriod && (
        <div className="modal">
          <div className="modal-content">
            <h3>Edit Period</h3>
            <form onSubmit={handleEditPeriod}>
              <label>
                Period Date
                <input type="date" required value={editPeriodData.period_date} onChange={e => setEditPeriodData({...editPeriodData, period_date: e.target.value})} />
              </label>
              <label>
                Planned Percentage (0-100)
                <input 
                  type="number" 
                  step="0.0001" 
                  min="0" 
                  max="100"
                  required 
                  value={editPeriodData.planned_percentage} 
                  onChange={e => setEditPeriodData({...editPeriodData, planned_percentage: e.target.value})} 
                />
              </label>
              {actionError && <p className="error">{actionError}</p>}
              <div className="actions">
                <button type="button" className="secondary" onClick={() => setShowEditPeriod(false)}>Cancel</button>
                <button type="submit" disabled={submitting}>{submitting ? 'Saving...' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
