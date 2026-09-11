import axios from "axios";
import type {
  Boq,
  BoqItem,
  BoqRevision,
  BoqRevisionDetail,
  Contract,
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
  }
  return fallback;
}
