# PicoLimbo Build API — Project Plan

## Overview

Transform the PicoLimbo integration test project into a build API that compiles PicoLimbo (a Rust project) on demand, caches builds, and serves artifacts. The API runs inside the existing Docker container alongside the VNC/Xorg infrastructure.

---

## Architecture Decisions

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| **Framework** | FastAPI | Automatic OpenAPI docs, Pydantic validation, async support, simple |
| **Database** | SQLite (embedded, WAL mode) | Standalone container, zero external deps, easy backup |
| **Concurrency** | Single build worker | Simple queue, one build at a time |
| **Auth** | None (for now) | Internal use, behind Docker networking |
| **Git whitelist** | GitHub.com only | Restrict to `github.com` URLs |
| **Owner** | Auto-extracted from URL | Parse `https://github.com/{owner}/{repo}.git` |
| **Base image** | Ubuntu 26.04 | Latest LTS |
| **Rust toolchain** | `apt` + `rustup update stable` | Ensures latest stable for edition 2024 |
| **dbus** | Installed and started in entrypoint | Fixes Xorg warning: `dbus-core: error connecting to system bus` |

---

## RESTful Endpoints

### POST /jobs
Create a build job. Returns the job info immediately (status: `queued` → `building` → `finished`/`failed`).

**Request Body** (all optional):
```json
{
  "repo_url": "https://github.com/Quozul/PicoLimbo.git",
  "ref": "master"
}
```

**Response (201 Created)**:
```json
{
  "job_id": "abc123def456",
  "status": "queued",
  "repo_url": "https://github.com/Quozul/PicoLimbo.git",
  "ref": "master",
  "owner": "Quozul",
  "commit_hash": "a1b2c3d4e5f6...",
  "artifact_path": null,
  "created_at": "2026-05-30T10:00:00Z",
  "updated_at": "2026-05-30T10:00:00Z"
}
```

### GET /jobs/{job_id}
Retrieve job information.

**Response (200 OK)**:
```json
{
  "job_id": "abc123def456",
  "status": "building",
  "repo_url": "https://github.com/Quozul/PicoLimbo.git",
  "ref": "master",
  "owner": "Quozul",
  "commit_hash": "a1b2c3d4e5f6...",
  "artifact_path": "/app/builds/Quozul/master/a1b2c3d4/pico_limbo",
  "created_at": "2026-05-30T10:00:00Z",
  "updated_at": "2026-05-30T10:02:00Z"
}
```

**Response (404 Not Found)**: Job does not exist.

### GET /jobs/{job_id}/artifact
Download the built artifact binary.

- **200 OK**: Binary file with `Content-Disposition: attachment; filename="pico_limbo"`
- **404 Not Found**: Job doesn't exist, or build hasn't finished yet.

### GET /jobs
List all jobs, optionally filtered by status.

**Query Params**:
- `status` (optional): filter by status (`queued`, `building`, `finished`, `failed`)
- `limit` (optional, default 100): max number of results

**Response (200 OK)**: Array of `JobInfo` objects, sorted newest first.

### POST /jobs/{job_id}/retry
Retry a failed or finished build by resetting its status to `queued`.

- **200 OK**: Job re-queued, worker picks it up.
- **400 Bad Request**: Job is `queued` or `building`.
- **404 Not Found**: Job does not exist.

### GET /health
Liveness check.

**Response (200 OK)**: `{"status": "ok"}`

---

## Idempotency Strategy

1. **Unique job key**: `(repo_url, commit_hash)` — if a job for this pair exists, return it.
2. **Repo reuse**: If the repo is already cloned at `./cache/repos/{owner}/{repo_name}`, run `git fetch` + checkout instead of re-cloning.
3. **Commit resolution**:
   - If `ref` is a branch name → `git fetch` + `git checkout <branch>` → resolve to commit hash
   - If `ref` is a 40-char hex string → `git checkout <hash>` directly
4. **Build skip**: If artifact already exists at the expected path → mark `finished` immediately.
5. **SQLite WAL mode**: `PRAGMA journal_mode=WAL` for better concurrency.
6. **Stuck job recovery**: On startup, jobs stuck in `building` are re-queued (or marked `finished` if artifact exists).

---

## Volume Mounts (docker-compose.yml)

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| `./cache/cargo` | `/root/.cargo` | Cargo registry + git cache (like `.minecraft`) |
| `./cache/repos` | `/app/repos` | Cloned Git repositories |
| `./cache/builds` | `/app/builds` | Build artifacts |
| `./integration_tests_reports` | `/app/integration_tests_reports` | Existing — test screenshots |
| `./full_screenshots` | `/app/full_screenshots` | Existing — full screenshots |
| `./cache/.minecraft` | `/root/.minecraft` | Existing — Minecraft cache |
| `./cache/minecraft` | `/app/minecraft` | Existing — Minecraft data |

---

## File Structure

```
pico_limbo_integration_tests/
├── main.py                          # FastAPI app + route definitions
├── pico_limbo_builder.py            # Build logic + queue worker
├── models.py                        # Pydantic models (request/response)
├── database.py                      # SQLite schema + CRUD helpers
├── pyproject.toml                   # Dependencies (updated)
├── Dockerfile                       # Updated: Rust toolchain + API
├── docker-entrypoint.sh             # Updated: VNC + uvicorn
├── docker-compose.yml               # Updated: removed picolimbo, added volumes
├── PLAN.md                          # This file
└── ... (existing test files unchanged)
```

---

## Implementation Steps

### Step 1: Update `pyproject.toml`
Add `fastapi`, `uvicorn[standard]`, `pydantic` to dependencies.

### Step 2: Create `models.py`
Pydantic models:
- `JobCreate` — request body for POST /jobs
- `JobInfo` — shared response model (used by both POST and GET)

### Step 3: Create `database.py`
SQLite setup:
- Table: `jobs` (`job_id` PK, `repo_url`, `ref`, `owner`, `commit_hash`, `status`, `artifact_path`, `created_at`, `updated_at`)
- Functions:
  - `create_job()` — insert a new job
  - `get_job_by_id(job_id)` — lookup by ID
  - `get_job_by_key(repo_url, commit_hash)` — idempotency check
  - `update_job(job_id, **fields)` — update status, artifact_path, etc.

### Step 4: Create `pico_limbo_builder.py`
Build engine:
- `extract_owner_from_url(repo_url)` — parse GitHub URL → owner
- `is_commit_hash(ref)` — detect 40-char hex
- `ensure_repo_cloned(owner, repo_name)` — clone or return existing path
- `resolve_commit(repo_path, ref)` — fetch+checkout branch OR checkout commit
- `build_project(repo_path, commit_hash)` — `cargo build --release`
- `queue_worker()` — background thread pulling from the queue
- `create_or_get_job(repo_url, ref)` — idempotent entry point

### Step 5: Create `main.py`
FastAPI application:
- `POST /jobs` → create job, return JobInfo (201)
- `GET /jobs/{job_id}` → return JobInfo (404 if missing)
- `GET /jobs/{job_id}/artifact` → stream binary (404 if not ready)
- `GET /jobs` → list jobs, optionally filtered by `status` and `limit` (bonus, implemented)
- `POST /jobs/{job_id}/retry` → reset job status to `queued` for retry (bonus, implemented)
- `GET /health` → liveness check (bonus, implemented)

### Step 6: Update `Dockerfile`
- Base image: `ubuntu:26.04`
- Install `rustup` via `apt`, then `rustup default stable` + `rustup update stable`
- Install `dbus` and start daemon in entrypoint
- Copy new Python files
- Keep all existing deps (VNC, Xorg, etc.)
- Keep `EXPOSE 5900 6080` + add `8000`

### Step 7: Update `docker-entrypoint.sh`
- Start dbus daemon before Xorg
- After VNC setup, launch: `uv run uvicorn main:app --host 0.0.0.0 --port 8000`
- Add `trap` for SIGINT/SIGTERM to kill all background processes (Xorg, openbox, x11vnc, websockify, uvicorn)
- Keep existing Xorg/VNC/websockify flow unchanged

### Step 8: Update `docker-compose.yml`
- Remove `picolimbo` service
- Add new volume mounts: `cargo`, `repos`, `builds`
- Expose port `8000` for the API
- Keep existing volumes and ports

### Step 9: Update `.dockerignore`
Add `cache/`, `__pycache__/`, `*.pyc`, `*.pyo`, `.git`

### Step 10: Update `.gitignore`
Add `cache/`

---

## Bonus / Next Steps (Out of Scope for This Phase)

### ✅ Queue Persistence & Recovery (implemented)
- On container restart, scan the database for jobs with status `building`.
- For `building` jobs, verify if the artifact exists — if yes, mark `finished`; if no, re-queue as `queued`.
- SQLite WAL mode for better concurrency.

### ✅ Build Timeout (implemented)
- 30-minute timeout on `cargo build --release` via `subprocess.run(timeout=1800)`.

### Artifact Cleanup
- Implement a retention policy (e.g., keep artifacts for 30 days, or keep only the latest N builds per repo/ref).
- Run cleanup periodically or on demand via a new endpoint: `DELETE /jobs/{job_id}/artifact`.

### Concurrent Builds
- Support multiple simultaneous builds (e.g., one per repo).
- Use a thread pool with a configurable max size.
- Queue jobs that exceed the concurrency limit.

### Test Result Artifacts
- Store integration test results (screenshots, logs) as part of the job.
- New endpoint: `GET /jobs/{job_id}/results` — returns test artifacts.
- Store images as BLOBs in SQLite or as files on disk with metadata in the DB.

### Authentication
- Add API key authentication via `Authorization: Bearer <key>` header.
- Configurable via environment variable or config file.
- Protect all endpoints except `/health`.

### Frontend
- Simple web UI for browsing jobs, viewing status, and downloading artifacts.
- Could be a static SPA served by FastAPI, or a separate React/Vue app.

### ✅ Health Check (implemented)
- `GET /health` — liveness check, returns `{"status": "ok"}`

### Fork Detection & Naming
- Forks of PicoLimbo may have the same repo name but different owners.
- The `(owner, repo_name, commit_hash)` tuple uniquely identifies a build.
- Display both owner and repo name in the UI for clarity.

### Caching Cargo Dependencies
- Mount `./cache/cargo` to `/root/.cargo` in docker-compose.yml.
- This caches both the registry index and compiled dependencies.
- Similar to how `./.minecraft` caches Minecraft assets.

### Dockerfile Optimization
- Multi-stage build: build PicoLimbo in a Rust stage, copy only the artifact.
- Reduce final image size significantly.

### Webhook / Notifications
- Notify an external service when a build finishes (success or failure).
- Configurable webhook URL per job or globally.

### API Versioning
- Prefix endpoints with version: `/v1/jobs`, `/v1/jobs/{job_id}`, etc.
- Allows backward-compatible API changes in the future.

### Logging & Audit Trail
- Log all build actions (clone, fetch, build, artifact served).
- Store logs in the database or as files per job.
- New endpoint: `GET /jobs/{job_id}/logs`

---

## API Response Codes Summary

| Endpoint | Code | Meaning |
|----------|------|---------|
| POST /jobs | 201 | Job created |
| POST /jobs | 400 | Invalid request (e.g., not a GitHub URL) |
| GET /jobs/{id} | 200 | Job found |
| GET /jobs/{id} | 404 | Job not found |
| GET /jobs/{id}/artifact | 200 | Artifact ready, binary returned |
| GET /jobs/{id}/artifact | 404 | Job not found or not yet built |
| GET /jobs | 200 | List of jobs |
| POST /jobs/{id}/retry | 200 | Job re-queued |
| POST /jobs/{id}/retry | 400 | Job is `queued` or `building` |
| POST /jobs/{id}/retry | 404 | Job not found |

---

## Notes

- Default branch for PicoLimbo: `master`
- Default repo: `https://github.com/Quozul/PicoLimbo.git`
- The VNC server (port 5900/6080) and Xorg infrastructure remain in the container for debugging and future features.
- The existing integration test files are not modified in this phase.
- Database persisted at `./cache/builds/jobs.db` via the `./cache/builds` volume mount.
- SQLite uses WAL journal mode for better concurrency.
