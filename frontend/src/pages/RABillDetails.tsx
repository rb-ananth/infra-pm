import React, { useEffect, useState } from "react";

import { useParams, Link } from "react-router-dom";

import { raBillApi, boqApi, getApiErrorMessage } from "../services/api";
import type { RABillDetail, Contract, Measurement } from "../types";
import { formatInr } from "../utils/money";

type RABillDetailsProps = {
  role: string;
};

function RABillDetails({ role }: RABillDetailsProps) {
  const { billId } = useParams<{ billId: string }>();
  const [bill, setBill] = useState<RABillDetail | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  
  const [eligibleMeasurements, setEligibleMeasurements] = useState<Measurement[]>([]);
  const [showItemModal, setShowItemModal] = useState(false);
  const [selectedMeasurements, setSelectedMeasurements] = useState<string[]>([]);
  
  const [showDedModal, setShowDedModal] = useState(false);
  const [dedForm, setDedForm] = useState({ id: "", deduction_type: "", description: "", amount: "" });
  
  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState({ bill_number: "", bill_date: "", period_from: "", period_to: "", remarks: "" });
  
  const [actionLoading, setActionLoading] = useState(false);

  const canEdit = ["Admin", "Project Manager", "Billing Engineer"].includes(role) && (bill?.status === "Draft" || bill?.status === "Rejected");
  const canSubmit = ["Admin", "Project Manager", "Billing Engineer"].includes(role) && bill?.status === "Draft";
  const canApprove = ["Admin", "Project Manager"].includes(role) && bill?.status === "Submitted";
  const canReject = ["Admin", "Project Manager", "Billing Engineer"].includes(role) && bill?.status === "Submitted";

  const loadData = async () => {
    try {
      setLoading(true);
      const res = await raBillApi.get(billId!);
      setBill(res.data);
      
      const cRes = await boqApi.listContracts();
      setContract(cRes.data.find((c: any) => c.id === res.data.contract_id) || null);
      setError("");
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "An error occurred"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [billId]);

  const loadEligibleMeasurements = async () => {
    if (!bill) return;
    try {
      const res = await raBillApi.getEligibleMeasurements(bill.contract_id);
      setEligibleMeasurements(res.data);
      setSelectedMeasurements([]);
      setShowItemModal(true);
    } catch (err: unknown) {
      alert(getApiErrorMessage(err, "An error occurred"));
    }
  };

  const handleAddItems = async () => {
    if (selectedMeasurements.length === 0) return;
    try {
      setActionLoading(true);
      const res = await raBillApi.addItems(billId!, { measurement_ids: selectedMeasurements });
      setBill(res.data);
      setShowItemModal(false);
    } catch (err: unknown) {
      alert(getApiErrorMessage(err, "An error occurred"));
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteItem = async (itemId: string) => {
    if (!window.confirm("Remove this item?")) return;
    try {
      await raBillApi.deleteItem(billId!, itemId);
      await loadData();
    } catch (err: unknown) {
      alert(getApiErrorMessage(err, "An error occurred"));
    }
  };

  const handleEditSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setActionLoading(true);
      await raBillApi.update(billId!, {
        ...editForm,
        remarks: editForm.remarks.trim() || undefined
      });
      setShowEditModal(false);
      await loadData();
    } catch (err: unknown) {
      alert(getApiErrorMessage(err, "Failed to update bill"));
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveDeduction = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setActionLoading(true);
      if (dedForm.id) {
        await raBillApi.updateDeduction(billId!, dedForm.id, {
          deduction_type: dedForm.deduction_type,
          description: dedForm.description || undefined,
          amount: dedForm.amount
        });
      } else {
        await raBillApi.addDeduction(billId!, {
          deduction_type: dedForm.deduction_type,
          description: dedForm.description || undefined,
          amount: dedForm.amount
        });
      }
      setShowDedModal(false);
      await loadData();
    } catch (err: unknown) {
      alert(getApiErrorMessage(err, "An error occurred"));
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteDeduction = async (dedId: string) => {
    if (!window.confirm("Remove this deduction?")) return;
    try {
      await raBillApi.deleteDeduction(billId!, dedId);
      await loadData();
    } catch (err: unknown) {
      alert(getApiErrorMessage(err, "An error occurred"));
    }
  };

  const handleAction = async (action: 'submit' | 'approve' | 'reject') => {
    if (!window.confirm(`Are you sure you want to ${action} this bill?`)) return;
    try {
      setActionLoading(true);
      if (action === 'submit') await raBillApi.submit(billId!);
      else if (action === 'approve') await raBillApi.approve(billId!);
      else if (action === 'reject') await raBillApi.reject(billId!);
      await loadData();
    } catch (err: unknown) {
      alert(getApiErrorMessage(err, "An error occurred"));
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) return <div className="p-8 text-center text-gray-500">Loading bill...</div>;
  if (error) return <div className="bg-red-50 border-l-4 border-red-400 p-4"><p className="text-sm text-red-700">{error}</p></div>;
  if (!bill) return null;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold text-gray-900">RA Bill: {bill.bill_number}</h1>
        <div className="flex space-x-3">
          {canEdit && (
            <button
              onClick={() => {
                setEditForm({
                  bill_number: bill.bill_number,
                  bill_date: bill.bill_date,
                  period_from: bill.period_from,
                  period_to: bill.period_to,
                  remarks: bill.remarks || ""
                });
                setShowEditModal(true);
              }}
              disabled={actionLoading}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md shadow-sm hover:bg-gray-50 disabled:opacity-50"
            >
              Edit Bill
            </button>
          )}
          {canSubmit && (
            <button
              onClick={() => handleAction('submit')}
              disabled={actionLoading || bill.items.length === 0}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md shadow-sm hover:bg-blue-700 disabled:opacity-50"
            >
              Submit
            </button>
          )}
          {canApprove && (
            <button
              onClick={() => handleAction('approve')}
              disabled={actionLoading}
              className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-md shadow-sm hover:bg-green-700 disabled:opacity-50"
            >
              Approve
            </button>
          )}
          {canReject && (
            <button
              onClick={() => handleAction('reject')}
              disabled={actionLoading}
              className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-md shadow-sm hover:bg-red-700 disabled:opacity-50"
            >
              Reject
            </button>
          )}
        </div>
      </div>

      <div className="bg-white shadow overflow-hidden sm:rounded-lg">
        <div className="px-4 py-5 sm:px-6 flex justify-between">
          <div>
            <h3 className="text-lg leading-6 font-medium text-gray-900">Bill Information</h3>
            <p className="mt-1 max-w-2xl text-sm text-gray-500">Contract: {contract?.contract_number}</p>
          </div>
          <div>
            <span className={`px-3 py-1 inline-flex text-sm leading-5 font-semibold rounded-full ${
              bill.status === "Approved" ? "bg-green-100 text-green-800" :
              bill.status === "Rejected" ? "bg-red-100 text-red-800" :
              bill.status === "Submitted" ? "bg-blue-100 text-blue-800" :
              "bg-gray-100 text-gray-800"
            }`}>
              {bill.status}
            </span>
          </div>
        </div>
        <div className="border-t border-gray-200 px-4 py-5 sm:p-0">
          <dl className="sm:divide-y sm:divide-gray-200">
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Bill Date</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{bill.bill_date}</dd>
            </div>
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Period</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{bill.period_from} to {bill.period_to}</dd>
            </div>
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6 bg-gray-50">
              <dt className="text-sm font-medium text-gray-500">Financial Summary</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                <div className="grid grid-cols-3 gap-4 font-medium">
                  <div>Gross: <span className="text-indigo-700">{formatInr(bill.gross_amount)}</span></div>
                  <div>Deductions: <span className="text-red-700">{formatInr(bill.deductions_amount)}</span></div>
                  <div className="text-lg">Net Payable: <span className="text-green-700">{formatInr(bill.net_payable)}</span></div>
                </div>
              </dd>
            </div>
            {bill.remarks && (
              <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                <dt className="text-sm font-medium text-gray-500">Remarks</dt>
                <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2 whitespace-pre-wrap">{bill.remarks}</dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      {/* Bill Items */}
      <div className="bg-white shadow sm:rounded-lg">
        <div className="px-4 py-5 sm:px-6 flex justify-between items-center border-b border-gray-200">
          <h3 className="text-lg leading-6 font-medium text-gray-900">Bill Items</h3>
          {canEdit && (
            <button
              onClick={loadEligibleMeasurements}
              className="px-3 py-1 bg-white border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Add Measurements
            </button>
          )}
        </div>
        {bill.items.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No items added to this bill yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">BOQ Item</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Prev Cum. Qty</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Current Qty</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Cum. Qty</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Bal. Qty</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Rate</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Current Amt</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Prev Cum. Amt</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Cum. Amt</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">% Exec</th>
                  {canEdit && <th className="px-6 py-3"></th>}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {bill.items.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      <div className="font-medium">{item.boq_item.item_code}</div>
                      <div className="text-xs text-gray-500 truncate max-w-xs">{item.boq_item.description}</div>
                      <div className="text-xs text-gray-400 mt-1">{item.measurements.length} measurements</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                      {item.previous_cumulative_quantity} {item.boq_item.unit}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-indigo-600 text-right">
                      +{item.current_quantity} {item.boq_item.unit}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {item.cumulative_quantity} {item.boq_item.unit}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {item.balance_quantity} {item.boq_item.unit}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {formatInr(item.rate)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 text-right">
                      {formatInr(item.current_amount)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {item.previous_cumulative_amount ? formatInr(item.previous_cumulative_amount) : "N/A"}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {formatInr(item.cumulative_amount)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {item.percentage_executed}%
                    </td>
                    {canEdit && (
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <button onClick={() => handleDeleteItem(item.id)} className="text-red-600 hover:text-red-900">
                          Remove
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Deductions */}
      <div className="bg-white shadow sm:rounded-lg">
        <div className="px-4 py-5 sm:px-6 flex justify-between items-center border-b border-gray-200">
          <h3 className="text-lg leading-6 font-medium text-gray-900">Deductions</h3>
          {canEdit && (
            <button
              onClick={() => {
                setDedForm({ id: "", deduction_type: "", description: "", amount: "" });
                setShowDedModal(true);
              }}
              className="px-3 py-1 bg-white border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Add Deduction
            </button>
          )}
        </div>
        {bill.deductions.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No deductions applied.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Amount</th>
                  {canEdit && <th className="px-6 py-3"></th>}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {bill.deductions.map((ded) => (
                  <tr key={ded.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{ded.deduction_type}</td>
                    <td className="px-6 py-4 text-sm text-gray-500">{ded.description}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-red-600 font-medium text-right">
                      - {formatInr(ded.amount)}
                    </td>
                    {canEdit && (
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <button
                          onClick={() => {
                            setDedForm({ id: ded.id, deduction_type: ded.deduction_type, description: ded.description || "", amount: ded.amount });
                            setShowDedModal(true);
                          }}
                          className="text-indigo-600 hover:text-indigo-900 mr-4"
                        >
                          Edit
                        </button>
                        <button onClick={() => handleDeleteDeduction(ded.id)} className="text-red-600 hover:text-red-900">
                          Delete
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Eligible Measurements Modal */}
      {showItemModal && (
        <div className="fixed z-10 inset-0 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" onClick={() => !actionLoading && setShowItemModal(false)}></div>
            <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
            <div className="inline-block align-bottom bg-white rounded-lg px-4 pt-5 pb-4 text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full sm:p-6">
              <div>
                <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">Add Approved Measurements</h3>
                <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-md">
                  {eligibleMeasurements.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">No eligible approved measurements available.</div>
                  ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr>
                          <th className="px-4 py-2"></th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Date</th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Ref</th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Measurement Description</th>
                          <th className="px-4 py-2 text-right text-xs font-medium text-gray-500">Quantity</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {Object.entries(
                          eligibleMeasurements.reduce((acc, m) => {
                            if (!acc[m.boq_item_id]) acc[m.boq_item_id] = [];
                            acc[m.boq_item_id].push(m);
                            return acc;
                          }, {} as Record<string, Measurement[]>)
                        ).map(([boqItemId, ms]) => (
                          <React.Fragment key={boqItemId}>
                            <tr className="bg-gray-100">
                              <td colSpan={5} className="px-4 py-2 text-xs font-bold text-gray-700 uppercase">
                                BOQ Item: {bill.items.find(i => i.boq_item_id === boqItemId)?.boq_item.item_code || boqItemId}
                                {bill.items.find(i => i.boq_item_id === boqItemId) && ` - ${bill.items.find(i => i.boq_item_id === boqItemId)?.boq_item.description}`}
                              </td>
                            </tr>
                            {ms.map(m => (
                              <tr key={m.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => {
                                if (selectedMeasurements.includes(m.id)) {
                                  setSelectedMeasurements(selectedMeasurements.filter(id => id !== m.id));
                                } else {
                                  setSelectedMeasurements([...selectedMeasurements, m.id]);
                                }
                              }}>
                                <td className="px-4 py-2 text-center">
                                  <input
                                    type="checkbox"
                                    checked={selectedMeasurements.includes(m.id)}
                                    onChange={() => {}}
                                    className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                                  />
                                </td>
                                <td className="px-4 py-2 text-sm text-gray-900">{m.measurement_date}</td>
                                <td className="px-4 py-2 text-sm text-gray-900">{m.reference}</td>
                                <td className="px-4 py-2 text-sm text-gray-500">{m.description}</td>
                                <td className="px-4 py-2 text-sm text-right font-medium text-gray-900">{m.quantity}</td>
                              </tr>
                            ))}
                          </React.Fragment>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                <div className="mt-5 sm:mt-6 sm:grid sm:grid-cols-2 sm:gap-3 sm:grid-flow-row-dense">
                  <button
                    type="button"
                    onClick={handleAddItems}
                    disabled={actionLoading || selectedMeasurements.length === 0}
                    className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-indigo-600 text-base font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:col-start-2 sm:text-sm disabled:opacity-50"
                  >
                    {actionLoading ? "Adding..." : `Add Selected (${selectedMeasurements.length})`}
                  </button>
                  <button
                    type="button"
                    disabled={actionLoading}
                    onClick={() => setShowItemModal(false)}
                    className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:mt-0 sm:col-start-1 sm:text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Deduction Modal */}
      {showDedModal && (
        <div className="fixed z-10 inset-0 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" onClick={() => !actionLoading && setShowDedModal(false)}></div>
            <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
            <div className="inline-block align-bottom bg-white rounded-lg px-4 pt-5 pb-4 text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full sm:p-6">
              <div>
                <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">{dedForm.id ? "Edit" : "Add"} Deduction</h3>
                <form onSubmit={handleSaveDeduction} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Type *</label>
                    <input
                      required
                      type="text"
                      value={dedForm.deduction_type}
                      onChange={e => setDedForm({ ...dedForm, deduction_type: e.target.value })}
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                      placeholder="e.g. Tax, Advance Recovery"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Amount *</label>
                    <input
                      required
                      type="number"
                      step="0.01"
                      min="0"
                      value={dedForm.amount}
                      onChange={e => setDedForm({ ...dedForm, amount: e.target.value })}
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Description</label>
                    <textarea
                      value={dedForm.description}
                      onChange={e => setDedForm({ ...dedForm, description: e.target.value })}
                      rows={2}
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                    />
                  </div>
                  <div className="mt-5 sm:mt-6 sm:grid sm:grid-cols-2 sm:gap-3 sm:grid-flow-row-dense">
                    <button
                      type="submit"
                      disabled={actionLoading}
                      className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-indigo-600 text-base font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:col-start-2 sm:text-sm disabled:opacity-50"
                    >
                      {actionLoading ? "Saving..." : "Save"}
                    </button>
                    <button
                      type="button"
                      disabled={actionLoading}
                      onClick={() => setShowDedModal(false)}
                      className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:mt-0 sm:col-start-1 sm:text-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      )}
      {showEditModal && (
        <div className="fixed z-10 inset-0 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" onClick={() => !actionLoading && setShowEditModal(false)}></div>
            <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>
            <div className="inline-block align-bottom bg-white rounded-lg px-4 pt-5 pb-4 text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full sm:p-6">
              <div>
                <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">Edit RA Bill</h3>
                <form onSubmit={handleEditSave} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Bill Number *</label>
                    <input required type="text" value={editForm.bill_number} onChange={e => setEditForm({ ...editForm, bill_number: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Bill Date *</label>
                    <input required type="date" value={editForm.bill_date} onChange={e => setEditForm({ ...editForm, bill_date: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Period From *</label>
                      <input required type="date" value={editForm.period_from} onChange={e => setEditForm({ ...editForm, period_from: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Period To *</label>
                      <input required type="date" value={editForm.period_to} onChange={e => setEditForm({ ...editForm, period_to: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Remarks</label>
                    <textarea value={editForm.remarks} onChange={e => setEditForm({ ...editForm, remarks: e.target.value })} rows={3} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
                  </div>
                  <div className="mt-5 sm:mt-6 sm:grid sm:grid-cols-2 sm:gap-3 sm:grid-flow-row-dense">
                    <button type="submit" disabled={actionLoading} className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-indigo-600 text-base font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:col-start-2 sm:text-sm disabled:opacity-50">
                      {actionLoading ? "Saving..." : "Save"}
                    </button>
                    <button type="button" disabled={actionLoading} onClick={() => setShowEditModal(false)} className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:mt-0 sm:col-start-1 sm:text-sm">
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


export default RABillDetails;
