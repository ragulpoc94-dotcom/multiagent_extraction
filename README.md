# N² Agentic Extraction Arena

A proof of concept that benchmarks three Groq-hosted open-weight LLMs on requirement-driven document extraction. It answers two questions separately:

- **Which model writes the best extraction prompt?**
- **Which model extracts best?**

Each of the three models reads the same Excel requirement workbook and writes its own extraction prompt (P1, P2, P3). Every prompt then runs, unchanged, on every model:

| Prompt generator | Extraction M1 | Extraction M2 | Extraction M3 |
|---|---|---|---|
| M1 → P1 | P1 × M1 | P1 × M2 | P1 × M3 |
| M2 → P2 | P2 × M1 | P2 × M2 | P2 × M3 |
| M3 → P3 | P3 × M1 | P3 × M2 | P3 × M3 |

That gives **9 independent extraction runs per document**. Each run gets the same processed document text, the same original workbook, one unchanged generated prompt (as the system message) and a common JSON output contract. No run sees another run's output.

## Stack

- **Backend:** Python 3.11+, FastAPI and Uvicorn, Pydantic v2, Groq Python SDK, Pandas and OpenPyXL, PyMuPDF (pypdf fallback), Tesseract OCR via pytesseract, SQLite, Pytest.
- **Frontend:** React 18 and TypeScript, Vite, Tailwind CSS, shadcn/ui-style components on Radix, Lucide, Recharts, TanStack Query, React Router, Vitest.

## Repository layout

```text
backend/
  app/
    main.py                  FastAPI factory, CORS, centralized error envelope, lifespan
    core/                    config (.env), errors, utils
    schemas/                 requirement + extraction Pydantic models (common output contract)
    db/repository.py         SQLite persistence (JSON documents + indexed columns)
    services/
      groq_client.py         Groq SDK wrapper: semaphore, RPM limiter, exponential backoff, retry-after
      excel_service.py       dynamic sheet/header/column-role discovery -> canonical field schema
      document_service.py    PDF text, Tesseract OCR, page rendering, page provenance
      export_service.py      JSON / CSV / Excel report generation
    agents/                  the six logical agents
      requirement_agent.py   1. Requirement Understanding (deterministic schema + 3 model interpretations)
      prompt_agent.py        2. Prompt Generation (3 independent LLM-written prompts)
      document_agent.py      3. Document Processing (process once, page-aligned chunking)
      extraction_agent.py    4. Cross-Model Extraction (the 3 × 3 orchestrator)
      validation_agent.py    5. Validation (JSON, schema, types, missing, evidence-in-document)
      evaluation_agent.py    6. Evaluation & Comparison (golden-label accuracy, rankings, agreement)
    jobs/runner.py           background competition jobs, restart recovery, resume
    api/v1/routes.py         versioned REST API
  tests/                     pytest suite (mocked Groq) + opt-in live Groq test
frontend/
  src/pages/                 Overview, Requirement Studio, Prompt Studio, Document Workspace,
                             Competition Arena, Results, Evaluation, Export Center
  src/components/            app shell, shadcn-style UI primitives, execution drawer
  src/test/                  Vitest + Testing Library tests
```

## Setup (macOS)

Prerequisites: Python 3.11+, Node 20+, and Tesseract (`brew install tesseract`).

```bash
# 1. Credentials: one Groq key for all three models. Never commit .env.
cp .env.example .env
#    edit .env and set GROQ_API_KEY, MODEL_1, MODEL_2, MODEL_3

# 2. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev            # http://localhost:5173 (proxies /api to :8000)
```

Check the models are available on your Groq account. Use the "Check availability" button on the Overview page, or run:

```bash
curl -s localhost:8000/api/v1/models/verify | python3 -m json.tool
```

## Run with Docker (no Python, Node or Tesseract needed)

One image contains the backend, the built frontend and Tesseract, all served on port 8000. You only need Docker and a `.env` file with `GROQ_API_KEY` set.

```bash
cp .env.example .env          # then set GROQ_API_KEY
docker build -t n2-extraction-arena .
docker run --rm -p 8000:8000 --env-file .env -v n2-data:/data n2-extraction-arena
# open http://localhost:8000
```

A ready-made image (amd64 and arm64) is published to GitHub Container Registry on every push to `main`, so you can skip the build:

```bash
docker run --rm -p 8000:8000 --env-file .env -v n2-data:/data ghcr.io/ragulpoc94-dotcom/multiagent_extraction:latest
```

Or `docker compose up`. Uploads and the SQLite database are kept in the `n2-data` volume. To run on a machine without the source code, export the image with `docker save n2-extraction-arena | gzip > n2-extraction-arena.tar.gz` and load it there with `docker load -i n2-extraction-arena.tar.gz`. Build with `--platform linux/amd64` for Windows and Intel machines. See `DOCKER_SETUP.txt` for step-by-step instructions.

## Using it

1. **Requirement Studio:** upload the workbook. Fields, types, mandatory flags, instructions and rule sheets are discovered automatically. Optionally have the three models interpret it.
2. **Generate 3 prompts:** each model writes its own prompt. All three are stored verbatim with model ID, timestamp, latency and token usage.
3. **Document Workspace:** upload a PDF, PNG, JPEG or TIFF. Each page records whether its text came from the PDF or from OCR. Then click **Run 3 × 3 competition**.
4. **Competition Arena:** watch the nine cells fill in live (status polling). Click any cell for its fields, evidence, validation issues and raw response.
5. **Results Comparison:** a field-by-field grid of all nine runs. It highlights agreement, disagreement, nulls and validation failures, and filters by generator, model and field.
6. **Evaluation:** upload golden labels (JSON `{field: value}`, or CSV/XLSX with `field,value` columns) to get field accuracy and exact-match accuracy. You'll see generator, model and combination rankings, a heatmap, latency and token charts, and own-prompt vs other-prompt results.
7. **Export Center:** download the Excel report, CSV comparison, consolidated JSON, prompts JSON, or individual run outputs.

## How results are scored (no invented numbers)

- **Accuracy is computed only from golden labels.** *Field accuracy* normalises values by data type before comparing: dates to ISO, numbers parsed (currency symbols and Indian or Western digit grouping handled), strings compared on alphanumerics only. *Exact match* compares the trimmed raw strings.
- **Without golden labels**, runs are ranked by **verified fill rate**: the share of expected fields that are non-null, type-valid, and whose quoted evidence was found in the document text. The UI labels it explicitly as not accuracy.
- **Agreement** (each run vs the most common value across runs) is reported separately and never used as accuracy.
- A value whose evidence quote isn't in the document is flagged **unsupported**. Malformed JSON is recorded as invalid and never repaired. Failed API calls score 0, and skipped cells (where the prompt failed to generate) are excluded.
- Rankings: each **prompt generator** is averaged across the three extraction models, and each **extraction model** across the three prompts. The **best combination** is the top single cell.

## Reliability

- Bounded concurrency (`MAX_CONCURRENCY`) and a client-side RPM limiter (`REQUESTS_PER_MINUTE`).
- 429, 5xx, timeouts and connection errors are retried with exponential backoff and jitter, honouring `retry-after` (`MAX_RETRIES`). 4xx errors such as an unknown model or bad key fail fast with a clear error.
- If a model rejects JSON mode, the call is retried once without it. The output is still strictly validated.
- Long documents are split into page-aligned chunks within `MAX_DOCUMENT_TOKENS`. Each chunk keeps its `=== PAGE n ===` markers, and per-field results merge in page order. The chunk count is shown in the UI.
- Competitions run as background tasks, and progress is persisted cell by cell in SQLite. If the server restarts mid-run, the competition is marked **interrupted** and **Re-run unfinished** resumes only the incomplete cells.
- API keys are kept as `SecretStr`, are never logged, and are redacted from error text. Document contents aren't logged.

## Tests

```bash
cd backend && pytest                 # mocked Groq: Excel, OCR, retries, 9 combinations, validation, evaluation, exports, API
cd backend && pytest -m live -s      # REAL Groq inference on synthetic data (needs .env); prints the leaderboard
cd frontend && npm run typecheck && npm test && npm run build
```

The end-to-end tests use a synthetic workbook and a synthetic two-page PDF/PNG generated at test time. No real banking data is included.

## API (v1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | service, OCR, PDF engine, Groq SDK, missing config |
| GET | `/api/v1/models` · `/models/verify` | configured models · availability on the Groq account |
| GET | `/api/v1/overview` | dashboard counts and recent runs |
| POST | `/api/v1/requirements/upload` | upload workbook → canonical schema |
| POST | `/api/v1/requirements/{id}/understand` | 3 independent model interpretations |
| POST | `/api/v1/prompts/generate` | 3 independently generated prompts |
| GET | `/api/v1/prompts/{run_id}` | prompts with metadata |
| POST | `/api/v1/documents/upload` · `/{id}/process` | upload · extract text/OCR per page |
| GET | `/api/v1/documents/{id}/pages/{n}/image` | page preview PNG |
| POST | `/api/v1/competitions` | create and start a 3 × 3 competition |
| GET | `/api/v1/competitions/{run_id}` · `/status` · `/results` | metadata · live cell status · full results |
| POST | `/api/v1/competitions/{run_id}/resume` | re-run unfinished cells |
| POST/GET | `/api/v1/evaluations/{run_id}` | evaluate (optional golden upload) · fetch |
| GET | `/api/v1/exports/{run_id}?kind=xlsx\|csv\|consolidated\|prompts\|execution` | downloads |

All JSON responses use `{ "success", "data", "error": {code, message, details}, "meta" }`.

## Data handling

Use synthetic or anonymised documents unless the bank has approved external processing: document text is sent to Groq. Uploads and the SQLite database live in `backend/data/`, which is git-ignored.

## Known limitations

- Single-process job runner, so run one Uvicorn worker. A queue (RQ/Celery) would be the next step for multi-worker deployments.
- Token counts for budgeting are estimated at about 4 characters per token. Reported usage comes from Groq.
- Evidence verification is a normalised substring match, so heavily garbled OCR can mark correct values as unsupported.
- Agreement highlighting in the UI uses loose alphanumeric matching. Accuracy uses the backend's type-aware normalisation.
