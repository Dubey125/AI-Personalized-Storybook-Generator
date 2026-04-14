# Personalized AI Storybook Generator

End-to-end prototype that accepts a user photo, name, and gender, then generates:

- A personalized preview illustration
- A 5-scene illustrated story
- A downloadable PDF storybook

The pipeline now performs identity profiling at upload time:

- Uses InsightFace embedding when available
- Falls back to a deterministic image fingerprint seed when InsightFace is unavailable
- Reuses identity seed across preview and all story scenes for stronger character consistency

Current training mode:
- `embedding_seed` mode is active by default (InsightFace embedding or image fingerprint fallback)
- LoRA / DreamBooth training can be integrated by setting `CHARACTER_TRAINING_COMMAND` to produce an adapter artifact at `{output_path}`
- If `backend/models/child_model.safetensors` exists, it can be auto-applied as a default LoRA adapter via `DEFAULT_LORA_ADAPTER_PATH`

Persistence model:
- Jobs and session metadata are stored in SQLite (`SQLITE_DB_PATH`) for durable process restarts.

## Project Structure

- `backend/`: FastAPI APIs (`/api/upload`, `/api/preview`, `/api/generate-storybook`, `/api/jobs/{job_id}`, `/api/system-status`)
- `frontend/`: React UI for upload, preview, and full generation
- `models/`: AI image generation module (Diffusers)
- `utils/`: Story templates and PDF builder
- `uploads/`: Uploaded user images
- `outputs/`: Generated preview, scene images, and PDF files

## Backend Setup

1. Open terminal in `backend/`
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start server:

```bash
uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`.

## Frontend Setup

1. Open second terminal in `frontend/`
2. Install dependencies:

```bash
npm install
```

3. Start frontend:

```bash
npm start
```

Frontend runs at `http://localhost:3000` and calls backend at `http://localhost:8000` by default.

The frontend includes a "Training Admin" panel that calls `/api/admin/training-jobs` to show recent training job health and artifacts.

To override backend URL:

- Create `frontend/.env` with:

```env
REACT_APP_API_BASE_URL=http://localhost:8000
REACT_APP_API_AUTH_TOKEN=change-me-in-production
```

## Production Configuration

Configure backend environment variables before deployment:

```env
API_TITLE=Personalized AI Storybook Generator
ALLOWED_ORIGINS=https://your-frontend.example.com
API_AUTH_TOKEN=change-me-in-production
MAX_UPLOAD_SIZE_MB=8
MAX_UPLOAD_IMAGE_PIXELS=25000000
MAX_NAME_LENGTH=40
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_MAX_REQUESTS=120
ENABLE_REDIS_QUEUE=true
REDIS_URL=redis://localhost:6379/0
REDIS_QUEUE_NAME=storybook-jobs
REDIS_JOB_TIMEOUT_SECONDS=3600
CHARACTER_TRAINING_MODE=embedding_seed
CHARACTER_TRAINING_COMMAND=python -m backend.trainers.character_adapter_trainer --session-id "{session_id}" --mode "{mode}" --image-path "{image_path}" --output-path "{output_path}" --name "{name}" --gender "{gender}"
CHARACTER_TRAINING_TIMEOUT_SECONDS=7200
DEFAULT_LORA_ADAPTER_PATH=backend/models/child_model.safetensors
DEFAULT_LORA_ADAPTER_SCALE=0.85
SQLITE_DB_PATH=outputs/storybook.db
RETENTION_ENABLED=true
RETENTION_HOURS=168
METRICS_ENABLED=true
```

Notes:
- If `API_AUTH_TOKEN` is set, all `/api/*` routes require `Authorization: Bearer <token>`.
- Static generated assets remain available under `/outputs/*`.
- Rate limits are in-memory per process; use Redis-backed limits for multi-instance deployments.
- When `ENABLE_REDIS_QUEUE=true`, storybook jobs are enqueued in Redis and processed by workers.
- `CHARACTER_TRAINING_COMMAND` supports placeholders: `{session_id}`, `{mode}`, `{image_path}`, `{output_path}`, `{name}`, `{gender}`.
- For LoRA loading during generation, the training command should write a compatible adapter file (for example `.safetensors`) to `{output_path}`.
- Training profile telemetry includes duration, artifact size, and command/log tail metadata.
- Command-based adapter outputs are validated for non-empty files and supported adapter extensions.
- `/metrics` is available for Prometheus scraping when `METRICS_ENABLED=true`.

Run API and worker separately in production:

```bash
# API
uvicorn main:app --host 0.0.0.0 --port 8000

# Worker
python -m backend.worker
```

## API Overview

### `POST /api/upload`
Form fields:
- `name`: string
- `gender`: string
- `file`: image file

Returns `session_id` used in generation calls.
Also returns `identity_seed`, `identity_method`, and detection diagnostics.

### `POST /api/preview`
Query params:
- `session_id`
- `name`
- `gender`

Returns `preview_url`, which is served from `/outputs/...`.

### `GET /api/generate`

Query params:
- `prompt` (optional; default: `storybook child in jungle, cartoon style`)
- `session_id` (optional; if provided, uses uploaded face identity seed and session adapter)

Returns an image file response (`image/png`) for quick frontend preview/testing.

### `POST /api/train-character`
Query params:
- `session_id`
- `name`
- `gender`
- `training_mode` (`embedding_seed`, `lora`, `dreambooth`)

Returns a background `job_id` to poll via `/api/jobs/{job_id}`.
On completion, `result.character_profile` includes:
- `training_duration_seconds`
- `artifact_size_bytes`
- `training_log_tail`
- `training_command`

### `POST /api/train-character/upload-adapter`

Form fields:
- `session_id`
- `training_mode` (`lora` or `dreambooth`)
- `adapter_file` (`.safetensors`, `.bin`, `.pt`, `.ckpt`)

Use this endpoint when you train on Colab GPU and want to attach the exported adapter to an existing session.

### `POST /api/generate-storybook`
Query params:
- `session_id`
- `name`
- `gender`

Returns `202 Accepted` and starts an async job:
- `job_id`
- `status` (`queued`)

### `GET /api/jobs/{job_id}`
Returns job state:
- `queued`
- `running`
- `completed` with `result` payload
- `failed` with `error`

### `GET /api/system-status`
Returns runtime diagnostics:
- backend status
- model device (`cpu`/`cuda`)
- identity mode (`insightface-ready`/`fallback`)
- upload limit and CORS config

### `GET /api/admin/training-jobs`

Query params:
- `limit` (default 20, max 100)
- `cursor` (optional; use `next_cursor` from previous response)

Returns recent `train-character` jobs with status, session id, mode, artifact metadata, and errors.
Response includes `next_cursor` when more pages are available.

### `POST /api/admin/retention/run`

Runs retention cleanup immediately.

Query params:
- `retention_hours` (optional override)

Removes old uploads, generated outputs, adapter artifacts, and old SQLite job/session rows.

### `GET /metrics`

Prometheus metrics endpoint with request count and latency histograms.

## Production Baseline Improvements

- Upload validation: file type, extension, and max upload size checks
- Config-driven CORS and size limits through environment settings
- Async job execution + polling for long storybook generation
- Structured persisted job state in `outputs/jobs`
- `queue_mode` (`in-process` or `redis`)

### `GET /api/health`

Returns API health, current queue mode, and Redis availability when Redis mode is enabled.

### `GET /api/sessions/{session_id}/character-profile`

Returns identity and character profile metadata for a session, including consistency method and profile status.

## Current Prototype Notes

- Face consistency uses identity-derived deterministic seeds from uploaded face images.
- `models/image_generation.py` is ready for extension to FaceID, InsightFace embeddings, ControlNet, and LoRA adapters.
- Story scenes use predefined fantasy backgrounds while keeping character details consistent through prompt templates.

## Current End-to-End Flow

1. Upload user image + name + gender.
2. Build character profile (currently embedding/fingerprint seeded consistency profile).
3. Train character profile job (`embedding_seed`, `lora`, or `dreambooth` placeholder adapter).
4. Generate one preview image with consistent identity.
5. Generate full 5-scene storybook.
6. Download generated PDF from the frontend.

## Colab GPU Training Flow

1. Upload a photo in this app to create `session_id`.
2. Train LoRA/DreamBooth on Colab with your preferred notebook/tooling.
3. Export adapter artifact (`.safetensors` recommended).
4. In app: use **Train Character Profile** -> **Upload Colab Adapter**.
5. Generate preview and storybook using your uploaded adapter.

## Tests and CI

Backend tests are located in `backend/tests/`.

Run locally:

```bash
cd backend
pip install -r requirements.dev.txt
pytest -q
```

GitHub Actions workflow is defined at `.github/workflows/ci.yml` and runs:
- Backend tests
- Frontend production build

## Ops Quickstart

- Production environment template: `production.env.example`
- Deployment checklist: `DEPLOYMENT_CHECKLIST.md`

## Containers and Observability

Use Docker Compose profiles:

```bash
# App stack (frontend + api + worker + redis)
docker compose --profile app up --build

# Observability stack (prometheus)
docker compose --profile app --profile observability up --build
```

Observability config files:
- `observability/prometheus.yml`
- `observability/alerts.yml`
