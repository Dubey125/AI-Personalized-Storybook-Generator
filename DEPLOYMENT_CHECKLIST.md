# Deployment Readiness Checklist

## 1) Configuration and Secrets
- [ ] Copy production.env.example to your real runtime env source.
- [ ] Set API_AUTH_TOKEN to a strong secret.
- [ ] Set ALLOWED_ORIGINS to your real frontend domain(s).
- [ ] Set REACT_APP_API_BASE_URL and REACT_APP_API_AUTH_TOKEN in frontend env.

## 2) Infrastructure
- [ ] Provision Redis for queue mode.
- [ ] Ensure persistent storage for outputs/ and SQLite database file.
- [ ] Confirm enough disk for generated images/PDFs and adapter artifacts.

## 3) Application Startup
- [ ] Start API service.
- [ ] Start worker service.
- [ ] Start frontend service.
- [ ] Verify API health endpoint responds successfully.

## 4) Functional Smoke Tests
- [ ] Upload a valid image and verify session_id response.
- [ ] Verify DEFAULT_LORA_ADAPTER_PATH points to a real adapter file and /api/system-status reports default_adapter_exists=true.
- [ ] Run train-character and poll until completed.
- [ ] Generate preview and ensure image loads.
- [ ] Generate full storybook and verify PDF download.
- [ ] Verify admin training jobs endpoint returns recent jobs.

## 5) Security and Guardrails
- [ ] Verify unauthorized API calls are rejected when auth token is enabled.
- [ ] Verify rate-limiting is active for burst requests.
- [ ] Confirm upload validation blocks invalid/non-image files.

## 6) Observability
- [ ] Confirm /metrics endpoint is enabled and scraped by Prometheus.
- [ ] Confirm alerts are loaded from observability/alerts.yml.
- [ ] Verify no sustained 5xx error alerts under nominal load.

## 7) Data Retention
- [ ] Verify periodic retention loop is running.
- [ ] Trigger manual cleanup via /api/admin/retention/run and verify report.
- [ ] Confirm old uploads/outputs/adapters and stale DB rows are removed.

## 8) CI and Test Baseline
- [ ] Run backend tests locally with pytest.
- [ ] Run frontend production build locally.
- [ ] Ensure GitHub Actions CI passes on main branch.
