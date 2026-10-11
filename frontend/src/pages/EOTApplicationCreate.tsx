import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { eotApi, boqApi } from "../services/api";
import type { Contract } from "../types";

export default function EOTApplicationCreate({ role }: { role: string }) {
  const navigate = useNavigate();
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    contract_id: "",
    application_number: "",
    event_date: "",
    notice_date: "",
    cause_of_delay: "",
    claimed_days: 0,
  });

  useEffect(() => {
    boqApi.listContracts().then((res) => {
      setContracts(res.data);
      if (res.data.length > 0) {
        setFormData(prev => ({ ...prev, contract_id: res.data[0].id }));
      }
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setError("Failed to load contracts");
      setLoading(false);
    });
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: name === "claimed_days" ? parseInt(value) || 0 : value
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (formData.claimed_days < 0) {
      setError("Claimed days cannot be negative.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const res = await eotApi.create(formData);
      navigate(`/eot/${res.data.id}`);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || "Failed to create EOT application");
      setSaving(false);
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Create EOT Application</h1>
        <button
          onClick={() => navigate("/eot")}
          className="text-gray-600 hover:text-gray-900 font-medium"
        >
          Cancel
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <div className="bg-white rounded-lg shadow p-6">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700">Contract</label>
            <select
              name="contract_id"
              value={formData.contract_id}
              onChange={handleChange}
              required
              className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md border"
            >
              <option value="" disabled>Select a contract</option>
              {contracts.map(c => (
                <option key={c.id} value={c.id}>{c.contract_number} ({c.contract_type})</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Application Number</label>
            <input
              type="text"
              name="application_number"
              value={formData.application_number}
              onChange={handleChange}
              required
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Event Date</label>
              <input
                type="date"
                name="event_date"
                value={formData.event_date}
                onChange={handleChange}
                required
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Notice Date</label>
              <input
                type="date"
                name="notice_date"
                value={formData.notice_date}
                onChange={handleChange}
                required
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Cause of Delay</label>
            <textarea
              name="cause_of_delay"
              value={formData.cause_of_delay}
              onChange={handleChange}
              required
              rows={3}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            ></textarea>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Claimed Days</label>
            <input
              type="number"
              name="claimed_days"
              value={formData.claimed_days}
              onChange={handleChange}
              required
              min="0"
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            />
          </div>

          <div className="flex justify-end pt-4">
            <button
              type="submit"
              disabled={saving}
              className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {saving ? "Creating..." : "Create Application"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
