// ===== Auth =====
export interface LoginRequest { email: string; password: string }
export interface RegisterRequest { email: string; password: string; full_name: string; organization_name?: string }
export interface TokenResponse { access_token: string; refresh_token: string; token_type: string }

// ===== User =====
export interface User { id: string; email: string; full_name: string; role: string; is_active: boolean; created_at: string }

// ===== Organization =====
export interface Organization { id: string; name: string; slug: string; domain?: string; default_jurisdiction?: string; default_governing_law?: string; is_active: boolean; created_at: string }

// ===== Document =====
export type DocumentType = "contract" | "policy" | "memo" | "pleading" | "board_resolution" | "nda" | "employment_agreement" | "compliance_doc" | "statute" | "regulation" | "case_law" | "guidance" | "other";
export type ProcessingStatus = "pending" | "parsing" | "chunking" | "embedding" | "indexing" | "completed" | "failed";

export interface Document {
  id: string; organization_id: string; title: string; description?: string;
  document_type: DocumentType; file_name: string; file_size: number; mime_type: string;
  jurisdiction?: string; governing_law?: string; effective_date?: string; expiry_date?: string;
  parties?: Record<string, any>; extracted_metadata?: Record<string, any>;
  processing_status: ProcessingStatus; page_count?: number; matter_id?: string;
  created_at: string; updated_at: string;
}

// ===== Matter =====
export type MatterType = "litigation" | "transaction" | "advisory" | "regulatory" | "corporate" | "employment" | "ip" | "real_estate" | "other";
export type MatterStatus = "active" | "on_hold" | "closed" | "archived";

export interface Matter {
  id: string; organization_id: string; title: string; reference_number?: string;
  description?: string; matter_type: MatterType; status: MatterStatus;
  jurisdiction?: string; governing_law?: string; counterparty?: string; client_name?: string;
  tags?: string[]; opened_at?: string; closed_at?: string; created_at: string; updated_at: string;
}

export interface Deadline {
  id: string; matter_id: string; title: string; description?: string;
  due_date: string; status: string; priority: number;
  is_court_deadline: boolean; source_document_id?: string; created_at: string;
}

// ===== Analysis =====
export type RiskLevel = "critical" | "high" | "medium" | "low" | "info";

export interface Citation { citation_text: string; source_title?: string; source_type?: string; jurisdiction?: string; authority_level?: string; relevant_passage?: string; confidence: number }

export interface IssueAnalysis { issue: string; rule: string; authority: Citation[]; analysis: string; uncertainty?: string; recommendation: string; risk_level: RiskLevel }

export interface AskResponse {
  id: string; question: string; answer: string; issues: IssueAnalysis[];
  citations: Citation[]; confidence_score: number; risk_flags: string[];
  follow_up_questions: string[]; model_used?: string; created_at: string;
}

export interface ReviewResponse {
  id: string; document_id: string; summary: string; clauses: any[];
  risk_flags: any[]; missing_clauses: string[]; unusual_terms: string[];
  key_dates: any[]; key_obligations: any[]; overall_risk_level: RiskLevel;
  confidence_score: number; created_at: string;
}

// ===== Playbook =====
export interface PlaybookClause {
  id: string; clause_type: string; clause_name: string; position: string;
  standard_language: string; fallback_language?: string; negotiation_notes?: string;
  risk_if_deviated?: string; importance_weight: number;
}

export interface Playbook {
  id: string; name: string; description?: string; document_type: string;
  jurisdiction?: string; version: number; is_active: boolean;
  clauses: PlaybookClause[]; created_at: string;
}

// ===== Legal Sources =====
export interface ExternalSearchResult {
  title: string; citation: string; content_type: string; jurisdiction: string;
  jurisdiction_code: string; court_name?: string; court_level?: number;
  date_decided?: string; date_enacted?: string; summary?: string;
  source_url?: string; source_adapter: string; authority_level: string;
  is_current: boolean; external_id: string;
}

// ===== Conversation =====
export interface Conversation { id: string; title?: string; mode: string; matter_id?: string; is_active: boolean; created_at: string; updated_at: string }
export interface Message { id: string; role: string; content: string; sequence_number: number; model_used?: string; sources_used?: any[]; created_at: string }

// ===== Regulatory =====
export interface RegulatoryAlert {
  id: string; alert_type: string; title: string; summary: string;
  risk_level?: string; source_url?: string; source_citation?: string;
  is_read: boolean; created_at: string;
}

// ===== Pagination =====
export interface PaginatedResponse<T> { items: T[]; total: number; page: number; page_size: number; pages: number }
