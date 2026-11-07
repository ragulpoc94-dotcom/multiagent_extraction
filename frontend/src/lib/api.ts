import type {
  Competition, CompetitionStatus, DocumentRec, Envelope, Evaluation, Execution, Health, ModelsInfo, Overview,
  PromptRun, PromptRunSummary, Requirement, RequirementSummary, Results, VerifyInfo,
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number, public details?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError("network", "Can't reach the API server. Check that the backend is running on port 8000.", 0);
  }
  let body: Envelope<T> | null = null;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError("bad_response", `Server returned ${res.status} without a JSON body`, res.status);
  }
  if (!res.ok || !body.success) {
    const err = body?.error;
    throw new ApiError(err?.code ?? "error", err?.message ?? `Request failed (${res.status})`, res.status, err?.details);
  }
  return body.data;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const upload = (field: string, file: File): RequestInit => {
  const fd = new FormData();
  fd.append(field, file);
  return { method: "POST", body: fd };
};

export const api = {
  health: () => request<Health>("/health"),
  models: () => request<ModelsInfo>("/models"),
  verifyModels: () => request<VerifyInfo>("/models/verify"),
  overview: () => request<Overview>("/overview"),

  listRequirements: () => request<RequirementSummary[]>("/requirements"),
  getRequirement: (id: string) => request<Requirement>(`/requirements/${id}`),
  uploadRequirements: (file: File) => request<Requirement>("/requirements/upload", upload("file", file)),
  understand: (id: string) => request<Requirement>(`/requirements/${id}/understand`, { method: "POST" }),

  listPromptRuns: (requirementId?: string) =>
    request<PromptRunSummary[]>(`/prompts${requirementId ? `?requirement_id=${requirementId}` : ""}`),
  getPromptRun: (id: string) => request<PromptRun>(`/prompts/${id}`),
  generatePrompts: (requirementId: string) => request<PromptRun>("/prompts/generate", json({ requirement_id: requirementId })),

  listDocuments: () => request<DocumentRec[]>("/documents"),
  getDocument: (id: string) => request<DocumentRec>(`/documents/${id}`),
  uploadDocument: (file: File) => request<DocumentRec>("/documents/upload", upload("file", file)),
  processDocument: (id: string) => request<DocumentRec>(`/documents/${id}/process`, { method: "POST" }),
  pageImageUrl: (id: string, page: number) => `${API_BASE}/documents/${id}/pages/${page}/image`,

  listCompetitions: () => request<Competition[]>("/competitions"),
  getCompetition: (id: string) => request<Competition>(`/competitions/${id}`),
  createCompetition: (promptRunId: string, documentId: string) =>
    request<Competition>("/competitions", json({ prompt_run_id: promptRunId, document_id: documentId, auto_start: true })),
  competitionStatus: (id: string) => request<CompetitionStatus>(`/competitions/${id}/status`),
  resumeCompetition: (id: string) => request<{ id: string }>(`/competitions/${id}/resume`, { method: "POST" }),
  results: (id: string) => request<Results>(`/competitions/${id}/results`),
  execution: (runId: string, execId: string) => request<Execution>(`/competitions/${runId}/executions/${execId}`),

  getEvaluation: (id: string) => request<Evaluation>(`/evaluations/${id}`),
  evaluate: (id: string, golden?: File) =>
    request<Evaluation>(`/evaluations/${id}`, golden ? upload("golden", golden) : { method: "POST" }),
  clearGolden: (id: string) => request<Evaluation>(`/evaluations/${id}/golden`, { method: "DELETE" }),

  exportUrl: (id: string, kind: "consolidated" | "prompts" | "csv" | "xlsx" | "execution", executionId?: string) =>
    `${API_BASE}/exports/${id}?kind=${kind}${executionId ? `&execution_id=${executionId}` : ""}`,
};
