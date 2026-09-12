import axios from "axios";
import type {
  Boq,
  BoqItem,
  BoqRevision,
  BoqRevisionDetail,
  BoqImportPreview,
  BoqImportResult,
  Contract,
  Measurement,
  MeasurementDetail,
} from "../types";

const api = axios.create({
  baseURL: "http://localhost:8000/api/v1"
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;

export const boqApi = {
  list: () => api.get<Boq[]>("/boqs/"),
  get: (boqId: string) => api.get<Boq>(`/boqs/${boqId}`),
  create: (payload: {
    contract_id: string;
    boq_number: string;
    title: string;
    description?: string;
  }) => api.post<Boq>("/boqs/", payload),
  update: (boqId: string, payload: Record<string, string>) =>
    api.put<Boq>(`/boqs/${boqId}`, payload),
  listRevisions: (boqId: string) =>
    api.get<BoqRevision[]>(`/boqs/${boqId}/revisions`),
  createRevision: (
    boqId: string,
    payload: {
      revision_number: number;
      revision_date: string;
      remarks?: string;
    },
  ) => api.post<BoqRevision>(`/boqs/${boqId}/revisions`, payload),
  getRevision: (revisionId: string) =>
    api.get<BoqRevisionDetail>(`/boq-revisions/${revisionId}`),
  updateRevision: (revisionId: string, payload: Record<string, string>) =>
    api.put<BoqRevision>(`/boq-revisions/${revisionId}`, payload),
  listItems: (revisionId: string) =>
    api.get<BoqItem[]>(`/boq-revisions/${revisionId}/items`),
  createItem: (
    revisionId: string,
    payload: {
      item_code: string;
      item_number: string;
      description: string;
      unit: string;
      quantity: string;
      rate: string;
    },
  ) => api.post<BoqItem>(`/boq-revisions/${revisionId}/items`, payload),
  getItem: (itemId: string) => api.get<BoqItem>(`/boq-items/${itemId}`),
  updateItem: (itemId: string, payload: Record<string, string>) =>
    api.put<BoqItem>(`/boq-items/${itemId}`, payload),
  listContracts: () => api.get<Contract[]>("/contracts/"),
  previewImport: (revisionId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.post<BoqImportPreview>(
      `/boq-revisions/${revisionId}/import/preview`,
      formData,
    );
  },
  importItems: (revisionId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.post<BoqImportResult>(
      `/boq-revisions/${revisionId}/import`,
      formData,
    );
  },
};

export const measurementApi = {
  list: (params?: { boq_item_id?: string; status?: string; date_from?: string; date_to?: string }) =>
    api.get<Measurement[]>("/measurements", { params }),
  get: (id: string) => api.get<MeasurementDetail>(`/measurements/${id}`),
  create: (payload: { boq_item_id: string; measurement_date: string; quantity: string; reference: string; description: string; remarks?: string }) =>
    api.post<MeasurementDetail>("/measurements", payload),
  update: (id: string, payload: { measurement_date?: string; quantity?: string; reference?: string; description?: string; remarks?: string }) =>
    api.put<MeasurementDetail>(`/measurements/${id}`, payload),
  submit: (id: string) => api.post<MeasurementDetail>(`/measurements/${id}/submit`),
  approve: (id: string) => api.post<MeasurementDetail>(`/measurements/${id}/approve`),
  reject: (id: string) => api.post<MeasurementDetail>(`/measurements/${id}/reject`),
};

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => item?.msg)
        .filter(Boolean)
        .join(" ");
    }
    if (detail && typeof detail === "object") {
      if (Array.isArray((detail as { errors?: unknown }).errors)) {
        const messages = (detail as { errors: Array<{ message?: unknown }> }).errors
          .map((item) => (typeof item?.message === "string" ? item.message : ""))
          .filter(Boolean);
        if (messages.length > 0) {
          return messages.join("; ");
        }
      }
      if (typeof (detail as { message?: unknown }).message === "string") {
        return (detail as { message: string }).message;
      }
    }
  }
  return fallback;
}

export function getApiErrorDetail(error: unknown): unknown {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.detail;
  }
  return undefined;
}

export const raBillApi = {
  list: (params?: {
    contract_id?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
  }) => api.get<import("../types").RABill[]>("/ra-bills/", { params }),
  get: (billId: string) => api.get<import("../types").RABillDetail>(`/ra-bills/${billId}`),
  create: (data: {
    contract_id: string;
    bill_number: string;
    bill_date: string;
    period_from: string;
    period_to: string;
    remarks?: string;
  }) => api.post<import("../types").RABill>("/ra-bills/", data),
  update: (billId: string, data: {
    bill_number?: string;
    bill_date?: string;
    period_from?: string;
    period_to?: string;
    remarks?: string;
  }) => api.put<import("../types").RABill>(`/ra-bills/${billId}`, data),
  submit: (billId: string) => api.post<import("../types").RABill>(`/ra-bills/${billId}/submit`),
  approve: (billId: string) => api.post<import("../types").RABill>(`/ra-bills/${billId}/approve`),
  reject: (billId: string) => api.post<import("../types").RABill>(`/ra-bills/${billId}/reject`),
  getEligibleMeasurements: (contractId: string) =>
    api.get<import("../types").Measurement[]>(`/ra-bills/${contractId}/eligible-measurements`),
  addItems: (billId: string, data: { measurement_ids: string[] }) =>
    api.post<import("../types").RABillDetail>(`/ra-bills/${billId}/items`, data),
  deleteItem: (billId: string, itemId: string) =>
    api.delete(`/ra-bills/${billId}/items/${itemId}`),
  addDeduction: (billId: string, data: {
    deduction_type: string;
    description?: string;
    amount: string;
  }) => api.post<import("../types").RABillDeduction>(`/ra-bills/${billId}/deductions`, data),
  updateDeduction: (billId: string, deductionId: string, data: {
    deduction_type: string;
    description?: string;
    amount: string;
  }) => api.put<import("../types").RABillDeduction>(`/ra-bills/${billId}/deductions/${deductionId}`, data),
  deleteDeduction: (billId: string, deductionId: string) =>
    api.delete(`/ra-bills/${billId}/deductions/${deductionId}`),
};

export const evmApi = {
  getEvm: (projectId: string, asOfDate: string) =>
    api.get<import("../types").EVMResponse>(`/projects/${projectId}/evm?as_of_date=${asOfDate}`),
  getTrend: (projectId: string) =>
    api.get<import("../types").EVMTrendPoint[]>(`/projects/${projectId}/evm/trend`),
  listBaselines: (projectId: string) =>
    api.get<import("../types").EVMBaseline[]>(`/projects/${projectId}/evm/baselines`),
  createBaseline: (projectId: string, data: {
    baseline_number: string;
    name: string;
    effective_date: string;
    remarks?: string;
  }) => api.post<import("../types").EVMBaseline>(`/projects/${projectId}/evm/baselines`, data),
  getBaseline: (baselineId: string) =>
    api.get<import("../types").EVMBaseline>(`/evm-baselines/${baselineId}`),
  updateBaseline: (baselineId: string, data: {
    name?: string;
    effective_date?: string;
    remarks?: string;
    status?: string;
  }) => api.put<import("../types").EVMBaseline>(`/evm-baselines/${baselineId}`, data),
  approveBaseline: (baselineId: string) =>
    api.post<import("../types").EVMBaseline>(`/evm-baselines/${baselineId}/approve`),
  supersedeBaseline: (baselineId: string) =>
    api.post<import("../types").EVMBaseline>(`/evm-baselines/${baselineId}/supersede`),
  listPeriods: (baselineId: string) =>
    api.get<import("../types").EVMBaselinePeriod[]>(`/evm-baselines/${baselineId}/periods`),
  addPeriod: (baselineId: string, data: {
    period_date: string;
    planned_percentage: string;
  }) => api.post<import("../types").EVMBaselinePeriod>(`/evm-baselines/${baselineId}/periods`, data),
  updatePeriod: (periodId: string, data: {
    period_date?: string;
    planned_percentage?: string;
  }) => api.put<import("../types").EVMBaselinePeriod>(`/evm-baseline-periods/${periodId}`, data),
};
