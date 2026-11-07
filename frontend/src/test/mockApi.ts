import { vi } from "vitest";

const MODELS = { M1: "llama-3.3-70b-versatile", M2: "openai/gpt-oss-120b", M3: "qwen/qwen3-32b" };
const SLOTS = ["M1", "M2", "M3"] as const;

export const cells = SLOTS.flatMap((g, gi) =>
  SLOTS.map((e, ei) => ({
    id: `run_1_P${gi + 1}x${e}`, cell: `P${gi + 1}×${e}`, prompt_slot: g, prompt_id: `P${gi + 1}`, prompt_model: MODELS[g],
    extraction_slot: e, extraction_model: MODELS[e], is_self_prompt: g === e,
    status: gi === 2 && ei === 2 ? "failed" : "completed",
    latency_ms: 1200 + gi * 100 + ei * 10, usage: { prompt_tokens: 900, completion_tokens: 120, total_tokens: 1020 },
    attempts: 1, json_valid: !(gi === 2 && ei === 2), schema_valid: true, missing_rate: 0.17,
    supported_fill_rate: gi === 2 && ei === 2 ? null : 0.83, chunks_done: 1,
    error: gi === 2 && ei === 2 ? "rate_limited: simulated" : null, started_at: null, finished_at: null,
  })),
);

const ROUTES: Record<string, unknown> = {
  "/api/v1/models": { api_key_configured: true, missing: [], models: SLOTS.map((s) => ({ slot: s, env_var: `MODEL_${s[1]}`, model_id: MODELS[s] })), limits: { max_concurrency: 3, max_retries: 5, requests_per_minute: 30, max_document_tokens: 6000 } },
  "/api/v1/health": { status: "ok", version: "1.0.0", groq_sdk_installed: true, pdf_engine: "pymupdf", ocr_available: true, configuration_missing: [] },
  "/api/v1/overview": { counts: { requirements: 1, prompt_runs: 1, documents: 1, competitions: 1, completed_executions: 8, failed_executions: 1 }, recent_competitions: [{ id: "run_1", status: "completed_with_errors", created_at: new Date().toISOString(), document_name: "synthetic.pdf", requirement_name: "req.xlsx", completed_cells: 8, failed_cells: 1, total_cells: 9, best_combination: { cell: "P1×M1", prompt_model: MODELS.M1, extraction_model: MODELS.M1 }, primary_metric: "supported_fill_rate", best_score: 0.83, has_golden_labels: false }] },
  "/api/v1/competitions": [{ id: "run_1", status: "completed_with_errors", created_at: new Date().toISOString(), document_name: "synthetic.pdf" }],
  "/api/v1/competitions/run_1": { id: "run_1", status: "completed_with_errors", created_at: "", started_at: new Date(Date.now() - 30000).toISOString(), finished_at: new Date().toISOString(), requirement_id: "req_1", prompt_run_id: "prun_1", document_id: "doc_1", document_name: "synthetic.pdf", requirement_name: "req.xlsx", models: MODELS, extraction_models: MODELS, field_count: 6, chunk_count: 1, error: null },
  "/api/v1/competitions/run_1/status": { id: "run_1", status: "completed_with_errors", is_running: false, started_at: new Date(Date.now() - 30000).toISOString(), finished_at: new Date().toISOString(), error: null, chunk_count: 1, counts: { completed: 8, failed: 1 }, cells },
  "/api/v1/competitions/run_1/results": { competition: {}, fields: [], executions: [] },
  "/api/v1/requirements": [],
  "/api/v1/documents": [],
};

export function mockFetch() {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input).split("?")[0];
    if (url in ROUTES) return new Response(JSON.stringify({ success: true, data: ROUTES[url], error: null }), { status: 200 });
    return new Response(JSON.stringify({ success: false, data: null, error: { code: "not_found", message: "Not found" } }), { status: 404 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
