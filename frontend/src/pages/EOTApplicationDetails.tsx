import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api, { eotApi } from "../services/api";
import type { EOTApplication, Contract, Project } from "../types";

export default function EOTApplicationDetails({ role, userId }: { role: string, userId: string }) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [app, setApp] = useState<EOTApplication | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [project, setProject] = useState<Project | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const [decisionDays, setDecisionDays] = useState<number>(0);
  const [decisionReason, setDecisionReason] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  const fetchApp = async () => {
    if (!id) return false;
    setLoading(true);
    setRefreshError(null);
    try {
      const res = await eotApi.get(id);
      setApp(res.data);
      setDecisionDays(res.data.claimed_days);

      const contractRes = await api.get<Contract>(`/contracts/${res.data.contract_id}`);
      setContract(contractRes.data);

      const projectRes = await api.get<Project>(`/projects/${contractRes.data.project_id}`);
      setProject(projectRes.data);

      setLoading(false);
      return true;
    } catch (err: any) {
      console.error(err);
      setRefreshError("Failed to load or refresh EOT application data.");
      setLoading(false);
      return false;
    }
  };

  useEffect(() => {
    fetchApp();
  }, [id]);

  const handleAction = async (action: 'submit' | 'review' | 'approve' | 'reject') => {
    if (!id) return;
    setActionLoading(true);
    setError(null);
    setRefreshError(null);
    try {
      if (action === 'submit') {
        await eotApi.submit(id);
      } else if (action === 'review') {
        await eotApi.review(id);
      } else if (action === 'approve') {
        await eotApi.approve(id, { approved_days: decisionDays, decision_reason: decisionReason });
      } else if (action === 'reject') {
        await eotApi.reject(id, { decision_reason: decisionReason });
      }

      // Clear stale data before refresh so if refresh fails, user doesn't see old state.
      setApp(null);
      const success = await fetchApp();
      if (!success) {
        setError(`Action '${action}' succeeded, but failed to fetch the updated state from the server.`);
      }
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || `Failed to ${action} EOT application`);
    } finally {
      setActionLoading(false);
    }
  };

  const currentError = error || refreshError;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <div className="flex items-center space-x-4">
          <button onClick={() => navigate("/eot")} className="text-gray-500 hover:text-gray-700">
            &larr; Back to List
          </button>
          <h1 className="text-2xl font-bold">EOT: {app ? app.application_number : (id?.substring(0,8) + '...')}</h1>
          {app && (
            <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full
                ${app.status === 'Approved' ? 'bg-green-100 text-green-800' :
                  app.status === 'Rejected' ? 'bg-red-100 text-red-800' :
                  'bg-yellow-100 text-yellow-800'}`}>
              {app.status}
            </span>
          )}
        </div>
        <button
          onClick={fetchApp}
          className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {currentError && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4">
          <p className="text-sm text-red-700">{currentError}</p>
        </div>
      )}

      {loading && !app ? (
        <div className="p-8 flex justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : !app ? (
        <div className="p-8 text-center text-gray-500">
          No data available.
        </div>
      ) : (
        <>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-200">
              <h3 className="text-lg leading-6 font-medium text-gray-900">Application Information</h3>
            </div>
            <div className="px-6 py-5 grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <p className="text-sm font-medium text-gray-500">Contract</p>
                <p className="mt-1 text-sm text-gray-900">{contract ? contract.contract_number : app.contract_id}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Project</p>
                <p className="mt-1 text-sm text-gray-900">{project ? `${project.code} - ${project.name}` : '-'}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Submission Date</p>
                <p className="mt-1 text-sm text-gray-900">{app.submission_date || 'Not submitted'}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Event Date</p>
                <p className="mt-1 text-sm text-gray-900">{app.event_date}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Notice Date</p>
                <p className="mt-1 text-sm text-gray-900">{app.notice_date}</p>
              </div>
              <div className="md:col-span-2">
                <p className="text-sm font-medium text-gray-500">Cause of Delay</p>
                <p className="mt-1 text-sm text-gray-900">{app.cause_of_delay}</p>
              </div>

              <div className="md:col-span-2 border-t border-gray-100 pt-4 mt-2">
                <h4 className="text-sm font-bold text-gray-700 mb-4">Dates & Extensions</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div>
                    <p className="text-xs font-medium text-gray-500">Original Completion</p>
                    <p className="mt-1 text-sm text-gray-900">{contract?.original_completion_date ?? '-'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500">Current Completion</p>
                    <p className="mt-1 text-sm text-gray-900 font-medium">{contract?.current_completion_date ?? '-'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500">Claimed Days</p>
                    <p className="mt-1 text-sm text-gray-900 font-semibold">{app.claimed_days}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500">Approved Days</p>
                    <p className="mt-1 text-sm text-gray-900 font-bold text-blue-600">{app.approved_days ?? '-'}</p>
                  </div>
                </div>

                {(app.previous_completion_date || app.revised_completion_date) && (
                  <div className="mt-4 pt-4 border-t border-gray-100 flex space-x-8">
                    <div>
                      <p className="text-xs font-medium text-gray-500">Pre-EOT Completion</p>
                      <p className="mt-1 text-sm text-gray-500">{app.previous_completion_date}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500">Revised Completion (Post-EOT)</p>
                      <p className="mt-1 text-sm text-gray-900 font-bold">{app.revised_completion_date}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {(app.decision_reason || app.decision_date) && (
            <div className="bg-white rounded-lg shadow overflow-hidden">
              <div className="px-6 py-5 border-b border-gray-200">
                <h3 className="text-lg leading-6 font-medium text-gray-900">Decision History</h3>
              </div>
              <div className="px-6 py-5 grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <p className="text-sm font-medium text-gray-500">Decision Date</p>
                  <p className="mt-1 text-sm text-gray-900">{app.decision_date ? new Date(app.decision_date).toLocaleString() : '-'}</p>
                </div>
                <div className="md:col-span-2">
                  <p className="text-sm font-medium text-gray-500">Decision Reason</p>
                  <p className="mt-1 text-sm text-gray-900">{app.decision_reason}</p>
                </div>
              </div>
            </div>
          )}

          <div className="bg-gray-50 rounded-lg p-6 border border-gray-200">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Actions</h3>

            {app.status === 'Draft' && userId === app.created_by && ['Admin', 'Project Manager', 'Engineer'].includes(role) && (
              <button
                onClick={() => {
                  if (window.confirm("Are you sure you want to submit this EOT application?")) {
                    handleAction('submit');
                  }
                }}
                disabled={actionLoading}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                Submit Application
              </button>
            )}

            {app.status === 'Submitted' && ['Admin', 'Project Manager'].includes(role) && (
              <button
                onClick={() => handleAction('review')}
                disabled={actionLoading}
                className="px-4 py-2 bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:opacity-50"
              >
                Mark Under Review
              </button>
            )}

            {app.status === 'Under Review' && userId !== app.created_by && ['Admin', 'Project Manager'].includes(role) && (
              <div className="space-y-4 max-w-lg">
                <div>
                  <label className="block text-sm font-medium text-gray-700">Approved Days</label>
                  <input
                    type="number"
                    value={decisionDays}
                    onChange={e => setDecisionDays(parseInt(e.target.value) || 0)}
                    min="0"
                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 sm:text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Decision Reason</label>
                  <textarea
                    value={decisionReason}
                    onChange={e => setDecisionReason(e.target.value)}
                    rows={3}
                    placeholder="Required for both approval and rejection"
                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 sm:text-sm"
                  ></textarea>
                </div>
                <div className="flex space-x-4 pt-2">
                  <button
                    onClick={() => {
                      if (!decisionReason) {
                        setError("Decision reason is required.");
                        return;
                      }
                      handleAction('approve');
                    }}
                    disabled={actionLoading}
                    className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => {
                      if (!decisionReason) {
                        setError("Decision reason is required.");
                        return;
                      }
                      if (window.confirm("Are you sure you want to reject this application?")) {
                        handleAction('reject');
                      }
                    }}
                    disabled={actionLoading}
                    className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </div>
            )}

            {app.status === 'Under Review' && userId === app.created_by && ['Admin', 'Project Manager'].includes(role) && (
              <p className="text-sm text-yellow-700 bg-yellow-50 p-3 rounded-md border border-yellow-200">
                You submitted this application. Another authorized user must review and approve it.
              </p>
            )}

            {['Approved', 'Rejected'].includes(app.status) && (
              <p className="text-sm text-gray-500">No further actions available. Application is closed.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
