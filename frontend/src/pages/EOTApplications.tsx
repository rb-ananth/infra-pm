import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { eotApi, boqApi } from "../services/api";
import type { EOTApplication, Contract, Project } from "../types";

export default function EOTApplications({ role }: { role: string }) {
  const [apps, setApps] = useState<EOTApplication[]>([]);
  const [contracts, setContracts] = useState<Record<string, Contract>>({});
  const [projects, setProjects] = useState<Record<string, Project>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [appsRes, contractsRes, projectsRes] = await Promise.all([
        eotApi.list(),
        boqApi.listContracts(),
        api.get<Project[]>("/projects/")
      ]);
      setApps(appsRes.data);

      const cMap: Record<string, Contract> = {};
      contractsRes.data.forEach(c => cMap[c.id] = c);
      setContracts(cMap);

      const pMap: Record<string, Project> = {};
      projectsRes.data.forEach(p => pMap[p.id] = p);
      setProjects(pMap);

    } catch (err: any) {
      console.error(err);
      setError("Failed to load EOT applications");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const filteredApps = statusFilter ? apps.filter(app => app.status === statusFilter) : apps;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Extension of Time (EOT) Applications</h1>
        <div className="space-x-4">
          <button
            onClick={fetchData}
            className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            Refresh
          </button>
          {["Admin", "Project Manager", "Engineer"].includes(role) && (
          <Link
            to="/eot/create"
            className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            Create EOT
          </Link>
          )}
        </div>
      </div>

      <div className="flex items-center space-x-4 mb-4">
        <label htmlFor="statusFilter" className="text-sm font-medium text-gray-700">Filter by Status:</label>
        <select
          id="statusFilter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="mt-1 block w-48 pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
        >
          <option value="">All Statuses</option>
          <option value="Draft">Draft</option>
          <option value="Submitted">Submitted</option>
          <option value="Under Review">Under Review</option>
          <option value="Approved">Approved</option>
          <option value="Rejected">Rejected</option>
        </select>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Number</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Project / Contract</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Submission Date</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cause</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Claimed / Approved</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredApps.length === 0 ? (
                <tr><td colSpan={6} className="px-6 py-4 text-center text-sm text-gray-500">No EOT applications found.</td></tr>
              ) : (
                filteredApps.map(app => {
                  const contract = contracts[app.contract_id];
                  const project = contract ? projects[contract.project_id] : null;
                  return (
                    <tr key={app.id}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-blue-600">
                        <Link to={`/eot/${app.id}`}>{app.application_number}</Link>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900">
                        {project ? <div className="font-semibold text-xs text-gray-500">{project.code}</div> : null}
                        <div>{contract ? contract.contract_number : app.contract_id.substring(0,8)}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{app.submission_date ?? '-'}</td>
                      <td className="px-6 py-4 text-sm text-gray-900 truncate max-w-[200px]" title={app.cause_of_delay}>{app.cause_of_delay}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{app.claimed_days} / {app.approved_days ?? '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full
                          ${app.status === 'Approved' ? 'bg-green-100 text-green-800' :
                            app.status === 'Rejected' ? 'bg-red-100 text-red-800' :
                            'bg-yellow-100 text-yellow-800'}`}>
                          {app.status}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
