import { api } from "./client";
import type * as T from "@/lib/types";

// ===== Auth =====
export const auth = {
  login: (data: T.LoginRequest) => api.post<T.TokenResponse>("/auth/login", data),
  register: (data: T.RegisterRequest) => api.post<T.TokenResponse>("/auth/register", data),
  refresh: (refresh_token: string) => api.post<T.TokenResponse>("/auth/refresh", { refresh_token }),
};

// ===== Documents =====
export const documents = {
  list: (params?: Record<string, any>) => api.get<T.Document[]>("/documents", params),
  get: (id: string) => api.get<T.Document>(`/documents/${id}`),
  upload: (formData: FormData) => api.upload<T.Document>("/documents", formData),
  delete: (id: string) => api.delete(`/documents/${id}`),
  reprocess: (id: string) => api.post<T.Document>(`/documents/${id}/reprocess`),
  download: (id: string) => api.get<{ download_url: string; file_name: string }>(`/documents/${id}/download`),
};

// ===== Matters =====
export const matters = {
  list: (params?: Record<string, any>) => api.get<T.Matter[]>("/matters", params),
  get: (id: string) => api.get<T.Matter>(`/matters/${id}`),
  create: (data: Partial<T.Matter>) => api.post<T.Matter>("/matters", data),
  update: (id: string, data: Partial<T.Matter>) => api.patch<T.Matter>(`/matters/${id}`, data),
  deadlines: (id: string, params?: Record<string, any>) => api.get<T.Deadline[]>(`/matters/${id}/deadlines`, params),
  createDeadline: (id: string, data: any) => api.post<T.Deadline>(`/matters/${id}/deadlines`, data),
  notes: (id: string) => api.get<any[]>(`/matters/${id}/notes`),
  createNote: (id: string, data: any) => api.post<any>(`/matters/${id}/notes`, data),
  activity: (id: string, params?: Record<string, any>) => api.get<any[]>(`/matters/${id}/activity`, params),
  stats: (id: string) => api.get<any>(`/matters/${id}/stats`),
};

// ===== Analysis =====
export const analysis = {
  ask: (data: { question: string; document_ids?: string[]; matter_id?: string; jurisdiction?: string }) =>
    api.post<T.AskResponse>("/analysis/ask", data),
  research: (data: any) => api.post<any>("/analysis/research", data),
  review: (data: { document_id: string; playbook_id?: string; focus_areas?: string[] }) =>
    api.post<T.ReviewResponse>("/analysis/review", data),
  compare: (data: any) => api.post<any>("/analysis/compare", data),
  draft: (data: any) => api.post<any>("/analysis/draft", data),
  deadlines: (documentId: string, matterId?: string) =>
    api.post<any>(`/analysis/deadlines/${documentId}`, undefined),
  riskMatrix: (documentId: string) => api.post<any>(`/analysis/risk-matrix/${documentId}`),
  exportDocx: (analysisId: string) => {
    // Direct download — can't use the standard api client since we need a blob
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    const orgId = typeof window !== "undefined" ? localStorage.getItem("organization_id") : null;
    const base = process.env.NEXT_PUBLIC_API_URL || "";
    return fetch(`${base}/api/v1/analysis/export/${analysisId}?format=docx`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(orgId ? { "X-Organization-ID": orgId } : {}),
      },
    }).then(async (res) => {
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?(.+?)"?$/);
      const filename = match ? match[1] : `export-${analysisId.slice(0, 8)}.docx`;
      return { blob, filename };
    });
  },
};

// ===== Playbooks =====
export const playbooks = {
  list: (params?: Record<string, any>) => api.get<T.Playbook[]>("/playbooks", params),
  get: (id: string) => api.get<T.Playbook>(`/playbooks/${id}`),
  create: (data: any) => api.post<T.Playbook>("/playbooks", data),
  update: (id: string, data: any) => api.patch<T.Playbook>(`/playbooks/${id}`, data),
  templates: () => api.get<any[]>("/playbooks/templates/list"),
  useTemplate: (templateId: string) => api.post<T.Playbook>(`/playbooks/templates/${templateId}/use`),
  delete: (id: string) => api.delete(`/playbooks/${id}`),
  addClause: (id: string, data: any) => api.post<any>(`/playbooks/${id}/clauses`, data),
};

// ===== Conversations =====
export const conversations = {
  list: (params?: Record<string, any>) => api.get<T.Conversation[]>("/conversations", params),
  create: (data: any) => api.post<T.Conversation>("/conversations", data),
  messages: (id: string, params?: Record<string, any>) => api.get<T.Message[]>(`/conversations/${id}/messages`, params),
  send: (id: string, content: string) => api.post<T.Message>(`/conversations/${id}/messages`, { content }),
};

// ===== Legal Sources =====
export const legalSources = {
  search: (data: any) => api.post<any>("/legal-sources/search", data),
  citationLookup: (data: { citation: string; jurisdiction?: string }) => api.post<any>("/legal-sources/citation-lookup", data),
  goodLawCheck: (data: { citation: string; jurisdiction?: string }) => api.post<any>("/legal-sources/good-law-check", data),
  adapters: () => api.get<any>("/legal-sources/adapters"),
  importSource: (externalId: string, adapterName: string) =>
    api.post<any>(`/legal-sources/import/${externalId}`, undefined),
  starterPacks: () => api.get<any[]>("/legal-sources/starter-packs"),
  importStarterPack: (packId: string) => api.post<any>(`/legal-sources/starter-packs/${packId}/import`),
};

// ===== Memory =====
export const memory = {
  preferences: (category?: string) => api.get<any[]>("/memory/preferences", category ? { category } : undefined),
  setPreference: (data: any) => api.post<any>("/memory/preferences", data),
  matterMemories: (matterId: string) => api.get<any[]>(`/memory/matters/${matterId}`),
  addMatterMemory: (matterId: string, data: any) => api.post<any>(`/memory/matters/${matterId}`, data),
};

// ===== Legal Features =====
export const legalFeatures = {
  redline: (data: { document_id_1: string; document_id_2: string; focus_areas?: string[] }) =>
    api.post<any>("/redline/compare", data),
  versionRedline: (data: { document_id: string; version_from: number; version_to: number }) =>
    api.post<any>("/redline/version", data),
  tagPrivilege: (data: any) => api.post<any>("/privilege/tag", data),
  documentPrivileges: (docId: string) => api.get<any[]>(`/privilege/document/${docId}`),
  privilegeLog: (matterId: string) => api.get<any[]>(`/privilege/matter/${matterId}/log`),
  conflictCheck: (data: { party_names: string[]; matter_id?: string }) => api.post<any>("/conflicts/check", data),
  registerParty: (data: any) => api.post<any>("/conflicts/parties", data),
  partyHistory: (name: string) => api.get<any[]>(`/conflicts/parties/${encodeURIComponent(name)}/history`),
  multiJurisdiction: (data: { topic: string; jurisdictions: string[] }) => api.post<any>("/multi-jurisdiction/compare", data),
  regulatoryMonitors: () => api.get<any[]>("/regulatory/monitors"),
  createMonitor: (data: any) => api.post<any>("/regulatory/monitors", data),
  triggerCheck: (monitorId: string) => api.post<any>(`/regulatory/monitors/${monitorId}/check`),
  regulatoryAlerts: (params?: Record<string, any>) => api.get<T.RegulatoryAlert[]>("/regulatory/alerts", params),
  validateCitation: (data: { citation: string; jurisdiction?: string }) => api.post<any>("/citations/validate", data),
  validateBatch: (data: { citations: string[]; jurisdiction?: string }) => api.post<any>("/citations/validate/batch", data),
  submitFeedback: (data: {
    resource_type: string; resource_id: string; rating: "positive" | "negative";
    comment?: string; correction?: string; correction_type?: string;
    query?: string; analysis_id?: string; conversation_message_id?: string;
  }) => api.post<any>("/feedback", data),
  feedbackStats: (resource_type?: string) => api.get<any>("/feedback/stats", resource_type ? { resource_type } : undefined),
};

// ===== Audit =====
export const audit = {
  logs: (params?: Record<string, any>) => api.get<any>("/audit/logs", params),
};
