export type Slot = "M1" | "M2" | "M3";
export const SLOTS: Slot[] = ["M1", "M2", "M3"];

export interface Envelope<T> {
  success: boolean;
  data: T;
  error: { code: string; message: string; details?: unknown } | null;
}

export interface ModelsInfo {
  api_key_configured: boolean;
  missing: string[];
  models: { slot: Slot; env_var: string; model_id: string | null }[];
  limits: { max_concurrency: number; max_retries: number; requests_per_minute: number; max_document_tokens: number };
}

export interface VerifyInfo {
  verified: boolean;
  reason?: string;
  models: { slot: Slot; model_id: string | null; available: boolean }[];
  account_model_count?: number;
}

export interface Health {
  status: string;
  version: string;
  groq_sdk_installed: boolean;
  pdf_engine: string;
  ocr_available: boolean;
  configuration_missing: string[];
}

export interface CanonicalField {
  key: string;
  label: string;
  description: string | null;
  data_type: "string" | "number" | "integer" | "date" | "boolean";
  raw_type: string | null;
  mandatory: boolean;
  instructions: string | null;
  examples: string | null;
  allowed_values: string[] | null;
  source_sheet: string;
  source_row: number | null;
}

export interface SheetPreview {
  name: string;
  columns: string[];
  row_count: number;
  rows: Record<string, unknown>[];
  detected_roles: Record<string, string>;
  layout: "field_rows" | "header_template" | "notes" | "empty";
}

export interface Interpretation {
  slot: Slot;
  model_id: string;
  status: "completed" | "failed";
  summary: string | null;
  fields: { key?: string; name?: string; description?: string; type?: string; mandatory?: boolean; rules?: string[] | string }[];
  business_rules: string[];
  ambiguities: string[];
  coverage: number | null;
  error: string | null;
  latency_ms: number | null;
  usage: Usage | null;
  created_at: string;
}

export interface Requirement {
  id: string;
  filename: string;
  status: string;
  created_at: string;
  requirement_set: { sheets: SheetPreview[]; fields: CanonicalField[]; business_rules: string[]; warnings: string[] };
  rendered_text?: string;
  interpretations: Interpretation[];
}

export interface RequirementSummary {
  id: string;
  filename: string;
  status: string;
  created_at: string;
  field_count: number;
  sheet_count: number;
}

export interface Usage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

export interface GeneratedPrompt {
  slot: Slot;
  prompt_id: "P1" | "P2" | "P3";
  model_id: string;
  status: "completed" | "failed";
  prompt_text: string | null;
  error?: string;
  started_at: string;
  created_at: string;
  latency_ms?: number;
  usage?: Usage;
  attempts?: number;
  used_own_interpretation: boolean;
  checks?: {
    field_key_coverage: number;
    fields_not_mentioned: string[];
    mentions_null_handling: boolean;
    mentions_evidence: boolean;
    mentions_page: boolean;
    requests_json_only: boolean;
    characters: number;
  };
}

export interface PromptRun {
  id: string;
  requirement_id: string;
  status: "completed" | "partial" | "failed";
  created_at: string;
  models: Record<Slot, string>;
  prompts: GeneratedPrompt[];
}

export interface PromptRunSummary {
  id: string;
  requirement_id: string;
  status: string;
  created_at: string;
  prompts: { prompt_id: string; model_id: string; status: string }[];
}

export interface DocPage {
  page: number;
  text?: string;
  method: "digital" | "ocr" | "ocr_failed" | "empty";
  char_count: number;
  ocr_confidence: number | null;
  error: string | null;
}

export interface DocumentRec {
  id: string;
  filename: string;
  kind: "pdf" | "image";
  mime: string;
  size_bytes: number;
  status: "uploaded" | "processing" | "processed" | "failed";
  created_at: string;
  pages: DocPage[];
  page_count?: number;
  methods?: string[];
  total_chars?: number;
  estimated_tokens?: number;
  chunks_planned?: number;
  ocr_available?: boolean;
  error?: string | null;
}

export type CellStatus = "queued" | "running" | "completed" | "failed" | "interrupted" | "skipped";

export interface Competition {
  id: string;
  status: "queued" | "running" | "completed" | "completed_with_errors" | "failed" | "interrupted";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  requirement_id: string;
  prompt_run_id: string;
  document_id: string;
  document_name: string;
  requirement_name: string;
  models: Record<Slot, string>;
  extraction_models: Record<Slot, string>;
  field_count: number;
  chunk_count: number;
  error: string | null;
  is_running?: boolean;
}

export interface CellSummary {
  id: string;
  cell: string;
  prompt_slot: Slot;
  prompt_id: string;
  prompt_model: string | null;
  extraction_slot: Slot;
  extraction_model: string;
  is_self_prompt: boolean;
  status: CellStatus;
  latency_ms: number | null;
  usage: Usage;
  attempts: number | null;
  json_valid: boolean | null;
  schema_valid: boolean | null;
  missing_rate: number | null;
  supported_fill_rate: number | null;
  chunks_done: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface CompetitionStatus {
  id: string;
  status: Competition["status"];
  is_running: boolean;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  chunk_count: number;
  counts: Partial<Record<CellStatus, number>>;
  cells: CellSummary[];
}

export type FieldStatus = "ok" | "missing" | "not_returned" | "type_error" | "unsupported" | "page_invalid";

export interface FieldValidation {
  key: string;
  status: FieldStatus;
  value: unknown;
  normalized_value: unknown;
  evidence: string | null;
  page: number | null;
  evidence_found: boolean | null;
  issues: string[];
}

export interface ValidationReport {
  json_valid: boolean;
  schema_valid: boolean;
  parse_error: string | null;
  fields_expected: number;
  fields_returned: number;
  fields_filled: number;
  missing: number;
  not_returned: number;
  type_errors: number;
  unsupported: number;
  unexpected_keys: string[];
  missing_rate: number;
  supported_fill_rate: number;
  fields: Record<string, FieldValidation>;
}

export interface Execution {
  id: string;
  competition_id: string;
  cell: string;
  prompt_slot: Slot;
  prompt_id: string;
  prompt_model: string | null;
  extraction_slot: Slot;
  extraction_model: string;
  is_self_prompt: boolean;
  status: CellStatus;
  attempts: number;
  latency_ms: number | null;
  usage: Usage;
  chunks?: { index: number; pages: number[]; status: string; latency_ms?: number; usage?: Usage; raw_response?: string; error?: string; notes?: string[]; json_valid?: boolean }[];
  raw_response?: string | null;
  normalized: { extracted_fields: Record<string, { value: unknown; evidence: string | null; page: number | null }> } | null;
  validation: ValidationReport | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Results {
  competition: Competition;
  fields: CanonicalField[];
  executions: Execution[];
}

export interface ComboMetrics {
  execution_id: string;
  cell: string;
  prompt_slot: Slot;
  prompt_id: string;
  prompt_model: string | null;
  extraction_slot: Slot;
  extraction_model: string;
  is_self_prompt: boolean;
  status: CellStatus;
  api_failure: boolean;
  json_valid: boolean;
  schema_valid: boolean;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  missing_rate: number | null;
  unsupported_rate: number | null;
  type_error_rate: number | null;
  supported_fill_rate: number | null;
  agreement_with_majority: number | null;
  field_accuracy?: number | null;
  exact_match_accuracy?: number | null;
  incorrect_rate?: number | null;
  all_fields_correct?: boolean;
  rank?: number;
}

export interface GroupRanking {
  slot: Slot;
  model_id: string;
  cells: number;
  rank: number;
  primary_metric: number | null;
  field_accuracy: number | null;
  exact_match_accuracy: number | null;
  supported_fill_rate: number | null;
  missing_rate: number | null;
  json_validity_rate: number | null;
  api_failure_rate: number | null;
  avg_latency_ms: number | null;
  avg_total_tokens: number | null;
}

export interface SubsetMetrics {
  cells: number;
  primary_metric: number | null;
  field_accuracy: number | null;
  supported_fill_rate: number | null;
  missing_rate: number | null;
  avg_latency_ms: number | null;
  avg_total_tokens: number | null;
}

export interface Evaluation {
  id: string;
  competition_id: string;
  has_golden_labels: boolean;
  primary_metric: "field_accuracy" | "supported_fill_rate";
  primary_metric_label: string;
  notes: string[];
  golden_field_count: number;
  golden_labels: Record<string, unknown> | null;
  golden_unknown_keys: string[];
  combinations: ComboMetrics[];
  leaderboard: ComboMetrics[];
  prompt_generator_ranking: GroupRanking[];
  extraction_model_ranking: GroupRanking[];
  best_combination: ComboMetrics | null;
  self_vs_cross: { self: SubsetMetrics; cross: SubsetMetrics };
  heatmap: { rows: Slot[]; cols: Slot[]; metric: string; values: (number | null)[][] };
  field_agreement: Record<string, { distinct_values: number; non_null_count: number; null_count: number; majority_share: number | null; unanimous: boolean }>;
  evaluated_at: string;
}

export interface Overview {
  counts: { requirements: number; prompt_runs: number; documents: number; competitions: number; completed_executions: number; failed_executions: number };
  recent_competitions: {
    id: string;
    status: Competition["status"];
    created_at: string;
    document_name: string;
    requirement_name: string;
    completed_cells: number;
    failed_cells: number;
    total_cells: number;
    best_combination: { cell: string; prompt_model: string; extraction_model: string } | null;
    primary_metric: string | null;
    best_score: number | null;
    has_golden_labels: boolean;
  }[];
}
