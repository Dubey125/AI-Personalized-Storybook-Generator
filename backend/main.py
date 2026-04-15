import os
import asyncio
import json
import re
import time
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque
from io import BytesIO
from threading import Lock
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
import uuid
import sys
from PIL import Image, UnidentifiedImageError

# Add models to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from backend.models.image_generation import ImageGenerator
from backend.models.controlnet_utils import ControlNetPoseHelper
from utils.face_identity import FaceIdentityService
from utils.story_templates import build_story_scenes
from utils.pose_templates import get_pose_template
from utils.pdf_builder import build_storybook_pdf
from backend.config import settings
from backend.job_store import JobStore
from backend.session_store import SessionStore

try:
    from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest
except Exception:  # pragma: no cover
    Counter = None
    Histogram = None
    CONTENT_TYPE_LATEST = "text/plain"
    generate_latest = None

app = FastAPI(title=settings.api_title)
# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}',
    datefmt='%Y-%m-%dT%H:%M:%S%z',
)
logger = logging.getLogger("storybook-api")

# Initialize AI Generator
image_generator = ImageGenerator()
face_identity_service = FaceIdentityService()
controlnet_helper = ControlNetPoseHelper()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
JOB_DIR = os.path.join(OUTPUT_DIR, "jobs")
ADAPTER_DIR = os.path.join(OUTPUT_DIR, "adapters")
DATABASE_PATH = str(Path(PROJECT_ROOT) / settings.sqlite_db_path)

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(JOB_DIR, exist_ok=True)
os.makedirs(ADAPTER_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

job_store = JobStore(DATABASE_PATH)
session_store = SessionStore(DATABASE_PATH)

_request_buckets = defaultdict(deque)
_request_buckets_lock = Lock()
VALID_GENDERS = {"boy", "girl", "child"}
VALID_TRAINING_MODES = {"embedding_seed", "lora", "dreambooth"}
VALID_ADAPTER_EXTENSIONS = {".safetensors", ".bin", ".pt", ".ckpt"}

app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
_retention_task = None

if Counter and Histogram:
    REQUEST_COUNT = Counter(
        "storybook_api_requests_total",
        "Total API requests",
        ["method", "path", "status"],
    )
    REQUEST_LATENCY = Histogram(
        "storybook_api_request_latency_seconds",
        "API request latency seconds",
        ["method", "path"],
    )
else:
    REQUEST_COUNT = None
    REQUEST_LATENCY = None


def _client_ip(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@app.middleware("http")
async def api_guardrails(request: Request, call_next):
    started = time.perf_counter()
    if request.url.path.startswith("/api"):
        auth_token = settings.api_auth_token
        if auth_token:
            bearer = (request.headers.get("authorization") or "").strip()
            expected = f"Bearer {auth_token}"
            if bearer != expected:
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        now = time.time()
        window = max(settings.rate_limit_window_seconds, 1)
        max_requests = max(settings.rate_limit_max_requests, 1)
        ip = _client_ip(request)

        with _request_buckets_lock:
            bucket = _request_buckets[ip]
            while bucket and now - bucket[0] > window:
                bucket.popleft()

            if len(bucket) >= max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please retry later."},
                )

            bucket.append(now)

    response = await call_next(request)

    if settings.metrics_enabled and REQUEST_COUNT and REQUEST_LATENCY:
        path = request.url.path
        REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(time.perf_counter() - started)

    return response


def find_uploaded_file(session_id: str) -> str:
    for file_name in os.listdir(UPLOAD_DIR):
        if file_name.startswith(f"{session_id}."):
            return os.path.join(UPLOAD_DIR, file_name)
    return ""


def validate_session_upload(session_id: str) -> str:
    uploaded = find_uploaded_file(session_id)
    if not uploaded:
        raise HTTPException(status_code=404, detail="Uploaded image not found for this session ID")
    return uploaded


def save_session_metadata(session_id: str, metadata: dict) -> None:
    session_store.upsert(session_id, metadata)


def load_session_metadata(session_id: str) -> dict:
    return session_store.get(session_id)


def _cleanup_old_files(base_dir: str, cutoff_epoch: float, excluded_paths: set[str] | None = None) -> int:
    excluded_paths = excluded_paths or set()
    removed = 0
    for file_name in os.listdir(base_dir):
        file_path = os.path.join(base_dir, file_name)
        if not os.path.isfile(file_path):
            continue
        if os.path.abspath(file_path) in excluded_paths:
            continue
        try:
            if os.path.getmtime(file_path) < cutoff_epoch:
                os.remove(file_path)
                removed += 1
        except OSError:
            continue
    return removed


def run_retention_cleanup(retention_hours: int | None = None) -> dict:
    hours = retention_hours if retention_hours is not None else settings.retention_hours
    hours = max(hours, 1)
    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_epoch = cutoff_dt.timestamp()
    cutoff_iso = cutoff_dt.isoformat()

    excluded = {os.path.abspath(DATABASE_PATH)}
    uploads_removed = _cleanup_old_files(UPLOAD_DIR, cutoff_epoch, excluded_paths=excluded)
    outputs_removed = _cleanup_old_files(OUTPUT_DIR, cutoff_epoch, excluded_paths=excluded)
    adapters_removed = _cleanup_old_files(ADAPTER_DIR, cutoff_epoch)
    jobs_removed = job_store.delete_older_than(cutoff_iso)
    sessions_removed = session_store.delete_older_than(cutoff_iso)

    return {
        "retention_hours": hours,
        "cutoff": cutoff_iso,
        "uploads_removed": uploads_removed,
        "outputs_removed": outputs_removed,
        "adapters_removed": adapters_removed,
        "jobs_removed": jobs_removed,
        "sessions_removed": sessions_removed,
    }


async def _retention_loop() -> None:
    while True:
        try:
            run_retention_cleanup()
        except Exception:
            logger.exception("Retention loop execution failed")
        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup_tasks() -> None:
    global _retention_task
    logger.info("Starting up Personalized AI Storybook Generator...")
    
    # Verify model and hardware
    try:
        device = image_generator.device
        runtime = image_generator.runtime_mode()
        logger.info(f"Model hardware: {device}, Runtime mode: {runtime}")
        
        # Warm up model if on CUDA
        if device == "cuda":
            logger.info("Warming up Stable Diffusion model...")
            await run_in_threadpool(image_generator.load_model)
    except Exception as e:
        logger.error(f"Startup check failed: {e}")

    if settings.retention_enabled:
        _retention_task = asyncio.create_task(_retention_loop())


@app.on_event("shutdown")
async def shutdown_tasks() -> None:
    global _retention_task
    if _retention_task:
        _retention_task.cancel()
        _retention_task = None


def validate_name_and_gender(name: str, gender: str) -> tuple[str, str]:
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Name is required")
    if len(normalized_name) > settings.max_name_length:
        raise HTTPException(
            status_code=400,
            detail=f"Name must be at most {settings.max_name_length} characters",
        )
    if not re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", normalized_name):
        raise HTTPException(status_code=400, detail="Name contains unsupported characters")

    normalized_gender = (gender or "").strip().lower()
    if normalized_gender not in VALID_GENDERS:
        raise HTTPException(status_code=400, detail="Gender must be one of: boy, girl, child")

    return normalized_name, normalized_gender


def validate_session_id(session_id: str) -> str:
    try:
        return str(uuid.UUID((session_id or "").strip()))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id") from exc


def validate_training_mode(training_mode: str | None) -> str:
    selected_mode = (training_mode or settings.character_training_mode or "embedding_seed").strip().lower()
    if selected_mode not in VALID_TRAINING_MODES:
        raise HTTPException(
            status_code=400,
            detail="training_mode must be one of: embedding_seed, lora, dreambooth",
        )
    return selected_mode


def _resolve_adapter_disk_path(adapter_path: str | None) -> str:
    if not adapter_path:
        return ""
    if adapter_path.startswith("/outputs/"):
        relative = adapter_path.replace("/outputs/", "", 1)
        return os.path.join(OUTPUT_DIR, relative)
    return adapter_path


def _resolve_default_adapter_disk_path() -> str:
    configured_path = (settings.default_lora_adapter_path or "").strip()
    if not configured_path:
        return ""

    if os.path.isabs(configured_path):
        return configured_path
    return os.path.join(PROJECT_ROOT, configured_path)


def _resolve_generation_adapter_disk_path(profile: dict | None) -> str:
    profile = profile or {}
    adapter_disk_path = _resolve_adapter_disk_path(profile.get("adapter_path"))
    if adapter_disk_path and os.path.exists(adapter_disk_path):
        return adapter_disk_path

    default_adapter_disk_path = _resolve_default_adapter_disk_path()
    if default_adapter_disk_path and os.path.exists(default_adapter_disk_path):
        return default_adapter_disk_path

    return ""


def _validate_trained_adapter_artifact(adapter_disk_path: str, selected_mode: str) -> None:
    if not os.path.exists(adapter_disk_path):
        raise RuntimeError("Training completed but adapter artifact was not found")

    if os.path.getsize(adapter_disk_path) <= 0:
        raise RuntimeError("Training completed but adapter artifact is empty")

    _, extension = os.path.splitext(adapter_disk_path)
    if selected_mode in {"lora", "dreambooth"} and extension.lower() not in VALID_ADAPTER_EXTENSIONS:
        raise RuntimeError(
            f"Unsupported adapter artifact extension '{extension}'. Expected one of: {sorted(VALID_ADAPTER_EXTENSIONS)}"
        )


def validate_upload(file: UploadFile, file_bytes: bytes) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is missing")

    file_ext = file.filename.split(".")[-1].lower()
    if file_ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    if len(file_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds max upload size of {settings.max_upload_size_mb}MB",
        )

    try:
        with Image.open(BytesIO(file_bytes)) as uploaded_image:
            uploaded_image.verify()
        with Image.open(BytesIO(file_bytes)) as uploaded_image:
            width, height = uploaded_image.size
            if width * height > settings.max_upload_image_pixels:
                raise HTTPException(
                    status_code=413,
                    detail="Image dimensions exceed server limits",
                )
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image") from exc

    return file_ext


def get_identity_metadata(session_id: str, user_image_path: str, name: str, gender: str) -> dict:
    metadata = load_session_metadata(session_id)
    if metadata.get("identity_seed") is not None:
        character_profile = metadata.get("character_profile")
        if not character_profile:
            metadata["character_profile"] = {
                "status": "ready",
                "consistency_method": settings.character_training_mode,
                "adapter_path": None,
                "notes": "Character profile prepared from upload identity data.",
            }
            save_session_metadata(session_id, metadata)
        return metadata

    identity_profile = face_identity_service.build_identity_profile(user_image_path)
    metadata = {
        "session_id": session_id,
        "name": name,
        "gender": gender,
        "identity_seed": identity_profile["identity_seed"],
        "identity_method": identity_profile["identity_method"],
        "face_detected": identity_profile["face_detected"],
        "embedding_dim": identity_profile["embedding_dim"],
        "diagnostic": identity_profile["diagnostic"],
        "character_profile": {
            "status": "ready",
            "consistency_method": settings.character_training_mode,
            "adapter_path": None,
            "notes": "Character profile prepared from upload identity data.",
        },
    }
    save_session_metadata(session_id, metadata)
    return metadata


def run_storybook_generation(job_id: str, session_id: str, name: str, gender: str) -> None:
    try:
        job_store.update(job_id, status="preparing_character_profile")
        user_image_path = validate_session_upload(session_id)
        metadata = get_identity_metadata(session_id, user_image_path, name, gender)

        scenes = build_story_scenes(name=name, gender=gender)
        negative_prompt = "ugly, deformed, blurry, realistic, bad anatomy, extra limbs"
        generated_scenes = []
        base_seed = int(metadata.get("identity_seed", 1313))
        profile = metadata.get("character_profile", {})
        prompt_suffix = profile.get("prompt_suffix", "")
        adapter_disk_path = _resolve_generation_adapter_disk_path(profile)
        job_store.update(job_id, status="generating_scenes")

        for index, scene in enumerate(scenes):
            job_store.update(job_id, status=f"running_scene_{index + 1}")
            pose_image = get_pose_template(index)
            scene_prompt = scene["prompt"]
            if prompt_suffix:
                scene_prompt = f"{scene_prompt}, {prompt_suffix}"
            try:
                image = controlnet_helper.generate_with_pose(
                    prompt=scene_prompt,
                    pose_image=pose_image,
                    negative_prompt=negative_prompt,
                    seed=base_seed + (index * 17),
                )
            except Exception:
                image = image_generator.generate_image(
                    prompt=scene_prompt,
                    negative_prompt=negative_prompt,
                    seed=base_seed + (index * 17),
                    adapter_path=adapter_disk_path,
                    reference_image_path=user_image_path,
                )

            image_filename = f"{session_id}_scene_{index + 1}.png"
            image_path = os.path.join(OUTPUT_DIR, image_filename)
            image.save(image_path)

            generated_scenes.append(
                {
                    "title": scene["title"],
                    "story_text": scene["story_text"],
                    "image_path": image_path,
                    "image_url": f"/outputs/{image_filename}",
                }
            )

        pdf_filename = f"{session_id}_storybook.pdf"
        pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)
        job_store.update(job_id, status="building_storybook_pdf")
        build_storybook_pdf(pdf_path=pdf_path, scenes=generated_scenes)

        result = {
            "message": "Storybook generated successfully",
            "scene_count": len(generated_scenes),
            "scenes": [
                {
                    "title": scene["title"],
                    "story_text": scene["story_text"],
                    "image_url": scene["image_url"],
                }
                for scene in generated_scenes
            ],
            "pdf_url": f"/outputs/{pdf_filename}",
            "identity_seed": base_seed,
            "identity_method": metadata.get("identity_method", "unknown"),
            "character_profile": metadata.get("character_profile", {}),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        job_store.update(job_id, status="completed", result=result)
    except Exception as exc:
        logger.exception("Storybook generation failed for job %s", job_id)
        job_store.update(job_id, status="failed", error=str(exc))


def run_character_training(job_id: str, session_id: str, name: str, gender: str, training_mode: str) -> None:
    try:
        started_at = datetime.now(timezone.utc)
        job_store.update(job_id, status="preparing_character_profile")
        user_image_path = validate_session_upload(session_id)
        metadata = get_identity_metadata(session_id, user_image_path, name, gender)
        profile = metadata.get("character_profile", {})

        selected_mode = validate_training_mode(training_mode)
        profile["consistency_method"] = selected_mode
        profile["status"] = "training"
        save_session_metadata(session_id, {**metadata, "character_profile": profile})
        job_store.update(job_id, status="training_character_adapter")

        adapter_public_path = None
        adapter_disk_path = ""
        training_log = ""
        training_command_used = ""
        artifact_size_bytes = 0
        if selected_mode in {"lora", "dreambooth"}:
            adapter_filename = f"{session_id}_{selected_mode}_adapter.safetensors"
            adapter_disk_path = os.path.join(ADAPTER_DIR, adapter_filename)

            command_template = settings.character_training_command
            if command_template:
                rendered_command = command_template.format(
                    session_id=session_id,
                    mode=selected_mode,
                    image_path=user_image_path,
                    output_path=adapter_disk_path,
                    name=name,
                    gender=gender,
                )
                training_command_used = rendered_command
                completed = subprocess.run(
                    rendered_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=settings.character_training_timeout_seconds,
                    check=True,
                )
                training_log = (completed.stdout or "")[-4000:]
                _validate_trained_adapter_artifact(adapter_disk_path, selected_mode)
            else:
                # Fallback placeholder to keep pipeline operational when a real trainer is not configured.
                adapter_payload = {
                    "session_id": session_id,
                    "name": name,
                    "gender": gender,
                    "training_mode": selected_mode,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "identity_seed": metadata.get("identity_seed"),
                    "note": "Placeholder adapter artifact; set CHARACTER_TRAINING_COMMAND for real fine-tuning.",
                }
                adapter_filename = f"{session_id}_{selected_mode}_adapter.json"
                adapter_disk_path = os.path.join(ADAPTER_DIR, adapter_filename)
                with open(adapter_disk_path, "w", encoding="utf-8") as artifact:
                    json.dump(adapter_payload, artifact, indent=2)
                training_command_used = "<internal-placeholder>"

            adapter_public_path = f"/outputs/adapters/{adapter_filename}"
            artifact_size_bytes = os.path.getsize(adapter_disk_path)

        duration_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()

        profile.update(
            {
                "status": "trained" if selected_mode in {"lora", "dreambooth"} else "ready",
                "adapter_path": adapter_public_path,
                "prompt_suffix": f"char_{session_id[:8]}",
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "training_log_tail": training_log,
                "training_command": training_command_used,
                "training_duration_seconds": round(duration_seconds, 3),
                "artifact_size_bytes": artifact_size_bytes,
                "notes": "Character profile updated and ready for generation.",
            }
        )
        metadata["character_profile"] = profile
        save_session_metadata(session_id, metadata)

        result = {
            "message": "Character training completed",
            "session_id": session_id,
            "training_mode": selected_mode,
            "character_profile": profile,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        job_store.update(job_id, status="completed", result=result)
    except Exception as exc:
        logger.exception("Character training failed for job %s", job_id)
        job_store.update(job_id, status="failed", error=str(exc))


def enqueue_background_job(
    background_tasks: BackgroundTasks,
    function_path: str,
    fallback_callable,
    *args,
) -> str:
    if settings.enable_redis_queue:
        try:
            import redis  # pylint: disable=import-outside-toplevel
            from rq import Queue  # pylint: disable=import-outside-toplevel

            redis_conn = redis.from_url(settings.redis_url)
            queue = Queue(
                settings.redis_queue_name,
                connection=redis_conn,
                default_timeout=settings.redis_job_timeout_seconds,
            )
            queue.enqueue(
                function_path,
                *args,
                job_timeout=settings.redis_job_timeout_seconds,
                result_ttl=86400,
                failure_ttl=86400,
            )
            return "redis"
        except Exception:
            logger.exception("Failed to enqueue via Redis queue, falling back to in-process tasks")

    background_tasks.add_task(fallback_callable, *args)
    return "in-process"

@app.get("/")
def read_root():
    return {"message": "Welcome to the AI Storybook Generator API!"}


@app.get("/api/system-status")
def system_status():
    default_adapter_disk_path = _resolve_default_adapter_disk_path()
    default_adapter_exists = bool(default_adapter_disk_path and os.path.exists(default_adapter_disk_path))

    model_device = image_generator.device
    model_runtime = image_generator.runtime_mode()
    identity_mode = "insightface-ready"
    try:
        # pylint: disable=import-outside-toplevel
        import insightface  # noqa: F401
    except Exception:
        identity_mode = "fallback"

    return {
        "status": "ok",
        "model_device": model_device,
        "model_runtime": model_runtime,
        "default_adapter_exists": default_adapter_exists,
        "default_adapter_path": settings.default_lora_adapter_path,
        "default_adapter_scale": settings.default_lora_adapter_scale,
        "identity_mode": identity_mode,
        "max_upload_size_mb": settings.max_upload_size_mb,
        "allowed_origins": settings.allowed_origins,
        "queue_mode": "redis" if settings.enable_redis_queue else "in-process",
    }


@app.get("/api/generate")
async def generate_single_image(
    prompt: str = "storybook child in jungle, cartoon style",
    session_id: str | None = None,
):
    safe_prompt = (prompt or "").strip()
    if not safe_prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    if len(safe_prompt) > 500:
        raise HTTPException(status_code=400, detail="prompt must be at most 500 characters")

    try:
        seed = 42
        reference_image_path = ""
        profile = {}

        if session_id:
            safe_session_id = validate_session_id(session_id)
            reference_image_path = validate_session_upload(safe_session_id)
            metadata = load_session_metadata(safe_session_id)
            if metadata:
                profile = metadata.get("character_profile", {})
                seed = int(metadata.get("identity_seed", seed))

        adapter_disk_path = _resolve_generation_adapter_disk_path(profile)
        image = await run_in_threadpool(
            image_generator.generate_image,
            safe_prompt,
            "ugly, deformed, blurry, realistic, bad anatomy",
            seed,
            adapter_disk_path,
            settings.default_lora_adapter_scale,
            reference_image_path,
        )

        output_name = f"quick_{uuid.uuid4().hex}.png"
        output_path = os.path.join(OUTPUT_DIR, output_name)
        await run_in_threadpool(image.save, output_path)
        return FileResponse(output_path, media_type="image/png", filename=output_name)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Quick image generation failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/api/health")
def health_check():
    response = {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "queue_mode": "redis" if settings.enable_redis_queue else "in-process",
    }

    if settings.enable_redis_queue:
        try:
            import redis  # pylint: disable=import-outside-toplevel

            redis_conn = redis.from_url(settings.redis_url)
            redis_conn.ping()
            response["redis"] = "ok"
        except Exception:
            response["redis"] = "unavailable"
            response["status"] = "degraded"

    return response


@app.get("/metrics")
def metrics():
    if not settings.metrics_enabled or not generate_latest:
        raise HTTPException(status_code=404, detail="Metrics are disabled")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/admin/retention/run")
def run_retention(retention_hours: int | None = None):
    if not settings.retention_enabled:
        raise HTTPException(status_code=400, detail="Retention is disabled")
    report = run_retention_cleanup(retention_hours=retention_hours)
    return {"message": "Retention cleanup completed", "report": report}

@app.post("/api/upload")
async def upload_user_info(
    name: str = Form(...),
    gender: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        name, gender = validate_name_and_gender(name, gender)

        # Generate a unique ID for the user session
        session_id = str(uuid.uuid4())

        file_bytes = await file.read()
        file_ext = validate_upload(file, file_bytes)

        # Save the uploaded file
        file_name = f"{session_id}.{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, file_name)

        with open(file_path, "wb") as buffer:
            buffer.write(file_bytes)

        metadata = get_identity_metadata(session_id, file_path, name, gender)
        metadata["upload_file"] = file_name
        save_session_metadata(session_id, metadata)
            
        return JSONResponse(status_code=200, content={
            "message": "File and information uploaded successfully",
            "session_id": session_id,
            "name": name,
            "gender": gender,
            "identity_seed": metadata["identity_seed"],
            "identity_method": metadata["identity_method"],
            "face_detected": metadata["face_detected"],
            "diagnostic": metadata["diagnostic"],
            "character_profile": metadata.get("character_profile", {}),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail="Internal server error") from e

@app.post("/api/preview")
async def generate_preview(session_id: str, name: str, gender: str):
    try:
        session_id = validate_session_id(session_id)
        name, gender = validate_name_and_gender(name, gender)

        # Validate upload exists for this session before generation.
        user_image_path = validate_session_upload(session_id)
        metadata = get_identity_metadata(session_id, user_image_path, name, gender)
        profile = metadata.get("character_profile", {})
        prompt_suffix = profile.get("prompt_suffix")
        adapter_disk_path = _resolve_generation_adapter_disk_path(profile)

        identity_seed = int(metadata.get("identity_seed", 1313))
        
        # 2. Setup prompt for the preview
        prompt = (
            f"A high quality illustration of a young {gender} named {name}, smiling, cartoon style, "
            "vibrant colors, magical background, same child face identity, consistent facial features, masterpiece"
        )
        if prompt_suffix:
            prompt = f"{prompt}, {prompt_suffix}"
        negative_prompt = "ugly, deformed, blurry, realistic, bad anatomy"
        
        # 3. Generate the image
        # Note: In a real run, this would inject the Face ID bindings.
        image = await run_in_threadpool(
            image_generator.generate_image,
            prompt,
            negative_prompt,
            identity_seed,
            adapter_disk_path,
            settings.default_lora_adapter_scale,
            user_image_path,
        )
        
        # 4. Save the generated preview
        preview_filename = f"{session_id}_preview.png"
        preview_path = os.path.join(OUTPUT_DIR, preview_filename)
        await run_in_threadpool(image.save, preview_path)
        
        return JSONResponse(status_code=200, content={
            "message": "Preview generated successfully",
            "preview_url": f"/outputs/{preview_filename}",
            "identity_seed": identity_seed,
            "identity_method": metadata.get("identity_method", "unknown"),
            "character_profile": metadata.get("character_profile", {}),
        })
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        with open("C:/Users/yadav/Desktop/storybook/backend/error_logs.txt", "w") as f:
            traceback.print_exc(file=f)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.post("/api/train-character")
async def train_character(
    session_id: str,
    name: str,
    gender: str,
    background_tasks: BackgroundTasks,
    training_mode: str | None = None,
):
    try:
        session_id = validate_session_id(session_id)
        name, gender = validate_name_and_gender(name, gender)
        selected_mode = validate_training_mode(training_mode)

        validate_session_upload(session_id)
        job = job_store.create(
            payload={
                "session_id": session_id,
                "name": name,
                "gender": gender,
                "job_type": "train-character",
                "training_mode": selected_mode,
            }
        )
        queue_mode = enqueue_background_job(
            background_tasks,
            "backend.main.run_character_training",
            run_character_training,
            job["job_id"],
            session_id,
            name,
            gender,
            selected_mode,
        )
        return JSONResponse(
            status_code=202,
            content={
                "message": "Character training started",
                "job_id": job["job_id"],
                "status": job["status"],
                "queue_mode": queue_mode,
                "training_mode": selected_mode,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Character training queueing failed")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.post("/api/train-character/upload-adapter")
async def upload_character_adapter(
    session_id: str = Form(...),
    training_mode: str = Form("lora"),
    adapter_file: UploadFile = File(...),
):
    try:
        session_id = validate_session_id(session_id)
        selected_mode = validate_training_mode(training_mode)
        if selected_mode not in {"lora", "dreambooth"}:
            raise HTTPException(status_code=400, detail="Adapter upload is supported only for lora or dreambooth")

        if not adapter_file.filename:
            raise HTTPException(status_code=400, detail="adapter_file is required")

        extension = os.path.splitext(adapter_file.filename)[1].lower()
        if extension not in VALID_ADAPTER_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported adapter extension '{extension}'. Allowed: {sorted(VALID_ADAPTER_EXTENSIONS)}",
            )

        adapter_bytes = await adapter_file.read()
        if not adapter_bytes:
            raise HTTPException(status_code=400, detail="Adapter file is empty")

        max_adapter_size_bytes = 512 * 1024 * 1024
        if len(adapter_bytes) > max_adapter_size_bytes:
            raise HTTPException(status_code=413, detail="Adapter file exceeds 512MB limit")

        user_image_path = validate_session_upload(session_id)
        existing_metadata = load_session_metadata(session_id)
        metadata = get_identity_metadata(
            session_id,
            user_image_path,
            existing_metadata.get("name", "child"),
            existing_metadata.get("gender", "child"),
        )

        adapter_filename = f"{session_id}_{selected_mode}_adapter{extension}"
        adapter_disk_path = os.path.join(ADAPTER_DIR, adapter_filename)
        with open(adapter_disk_path, "wb") as adapter_out:
            adapter_out.write(adapter_bytes)

        _validate_trained_adapter_artifact(adapter_disk_path, selected_mode)

        profile = metadata.get("character_profile", {})
        profile.update(
            {
                "status": "trained",
                "consistency_method": selected_mode,
                "adapter_path": f"/outputs/adapters/{adapter_filename}",
                "prompt_suffix": profile.get("prompt_suffix") or f"char_{session_id[:8]}",
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "training_command": "colab-upload",
                "training_duration_seconds": profile.get("training_duration_seconds", 0),
                "artifact_size_bytes": len(adapter_bytes),
                "notes": "Adapter uploaded from external trainer (for example Colab).",
            }
        )
        metadata["character_profile"] = profile
        save_session_metadata(session_id, metadata)

        return {
            "message": "Adapter uploaded and linked successfully",
            "session_id": session_id,
            "training_mode": selected_mode,
            "character_profile": profile,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Adapter upload failed")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.post("/api/generate-storybook")
async def generate_storybook(
    session_id: str,
    name: str,
    gender: str,
    background_tasks: BackgroundTasks,
):
    try:
        session_id = validate_session_id(session_id)
        name, gender = validate_name_and_gender(name, gender)

        validate_session_upload(session_id)
        job = job_store.create(
            payload={
                "session_id": session_id,
                "name": name,
                "gender": gender,
                "job_type": "generate-storybook",
            }
        )
        queue_mode = enqueue_background_job(
            background_tasks,
            "backend.main.run_storybook_generation",
            run_storybook_generation,
            job["job_id"],
            session_id,
            name,
            gender,
        )
        return JSONResponse(
            status_code=202,
            content={
                "message": "Storybook generation started",
                "job_id": job["job_id"],
                "status": job["status"],
                "queue_mode": queue_mode,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Storybook queueing failed")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    try:
        job_id = str(uuid.UUID((job_id or "").strip()))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid job_id") from exc

    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "result": job.get("result"),
        "error": job.get("error"),
    }


@app.get("/api/sessions/{session_id}/character-profile")
async def get_character_profile(session_id: str):
    session_id = validate_session_id(session_id)
    metadata = load_session_metadata(session_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "name": metadata.get("name"),
        "gender": metadata.get("gender"),
        "identity_seed": metadata.get("identity_seed"),
        "identity_method": metadata.get("identity_method"),
        "character_profile": metadata.get("character_profile", {}),
    }


@app.get("/api/admin/training-jobs")
async def get_recent_training_jobs(limit: int = 20, cursor: str | None = None):
    safe_limit = min(max(limit, 1), 100)
    jobs, next_cursor = job_store.list_recent_paginated(
        limit=safe_limit,
        job_type="train-character",
        cursor=cursor,
    )

    items = []
    for job in jobs:
        profile = (job.get("result") or {}).get("character_profile", {})
        items.append(
            {
                "job_id": job.get("job_id"),
                "status": job.get("status"),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "session_id": job.get("payload", {}).get("session_id"),
                "training_mode": job.get("payload", {}).get("training_mode"),
                "artifact_path": profile.get("adapter_path"),
                "artifact_size_bytes": profile.get("artifact_size_bytes", 0),
                "training_duration_seconds": profile.get("training_duration_seconds"),
                "error": job.get("error"),
            }
        )

    return {"count": len(items), "items": items, "next_cursor": next_cursor}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
