# PicoLimbo Integration Tests

A Docker-based test harness for verifying [PicoLimbo](https://github.com/Quozul/PicoLimbo), an ultra-lightweight, multi-version Minecraft limbo server written in Rust, against real Minecraft clients across dozens of versions.

## What It Does

PicoLimbo is a lightweight Minecraft server that can handle many concurrent players. This project tests it by:

1. **Building** PicoLimbo from a Git repository (branch name or commit hash).
2. **Launching one PicoLimbo server** inside the container.
3. **Running Minecraft clients** — for each requested version, a real Minecraft instance is launched inside a virtual desktop (Xvfb/Xorg), connects to the **same** server, and is verified by matching screen regions (the quit button appearing confirms the game is fully loaded).
4. **Capturing screenshots** of each successful connection, stored as test artifacts.
5. **Shutting down** the server once all version tests are complete.

The entire system runs inside a single Docker container with a virtual display, making it suitable for CI/CD pipelines or headless environments.

## Quick Start

### Prerequisites

- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/)
- A machine with at least 2 GB of RAM (more if testing many versions concurrently)

### Running the Project

```shell
# Build and start the container in detached mode
docker compose up --build -d

# Check the API is running
curl http://localhost:8000/health
```

### Creating a Test Job

```shell
# Test a single version
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"versions": ["1.21.8"]}'

# Test multiple versions
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"versions": ["1.20.4", "1.21.0", "1.21.8"]}'

# Use a specific branch or commit
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"ref": "feature/xyz", "versions": ["1.21.8"]}'
```

### Monitoring Progress

```shell
# Check job status
curl http://localhost:8000/jobs/<job_id>

# List all jobs
curl http://localhost:8000/jobs

# Filter by status
curl "http://localhost:8000/jobs?status=testing"
```

### Visual Debugging

The container exposes a VNC server so you can watch the virtual desktop in real time:

- **Web VNC:** http://localhost:6080/vnc.html
- **VNC (port 5900):** Use any VNC client to connect to `localhost:5900` (no password)

### Viewing Results

```shell
# List screenshots for a job
curl http://localhost:8000/jobs/<job_id>/screenshots

# Download a specific screenshot
curl -o screenshot.png http://localhost:8000/jobs/<job_id>/screenshots/1.21.8

# Download the built PicoLimbo binary (debug)
curl -o pico_limbo http://localhost:8000/jobs/<job_id>/artifact
```

Screenshots and artifacts are also available on the host via Docker volumes:

- `./integration_tests_reports/` — test screenshots
- `./cache/builds/` — built binaries and database

## Configuration

### Job Parameters

| Parameter | Default | Description |
|---|---|---|
| `repo_url` | `https://github.com/Quozul/PicoLimbo.git` | GitHub repository URL (must be github.com) |
| `ref` | `master` | Branch name or commit hash |
| `versions` | All supported versions | List of Minecraft versions to test |

## Supported Minecraft Versions

The project supports **81 Minecraft versions**, ranging from **1.7.2** to **26.1.2** (the latest snapshots). Version metadata including protocol numbers is defined in `src/versions.py`.

For LWJGL 2 compatibility (Minecraft 1.7–1.12), the virtual display uses a real XRandR mode list to prevent crashes.

## Updating Reference Images

If a new Minecraft version changes the quit button texture or the game window resolution, the reference images used for screen matching need to be updated:

```shell
docker compose run --build --rm pico-tests python3 update_references.py
```

## Minimal `options.txt`

The Minecraft launcher uses a minimal `options.txt` to avoid unnecessary UI elements:

```yaml
skipMultiplayerWarning: true   # added in 1.15.2
tutorialStep: none             # added in 1.12
joinedFirstServer: true        # added in 1.16.4
```

---

## What's Missing / TODO

### Proxy Testing Scenarios (from original design)

The following proxy configurations are planned but not yet implemented:

- **Direct connection** to PicoLimbo (basic)
- **Velocity proxy** — modern forwarding (1.13+) and legacy forwarding
- **BungeeCord proxy** — with and without BungeeGuard (1.8+)
- **ViaVersion** plugin — version translation layer
- **PacketEvents** plugin — packet manipulation framework
- **Custom keep-alive plugin** — holds the player in configuration state to test server keep-alive handling

### Low Priority

- **Keep player connected for 30+ seconds** — to verify the player isn't kicked unexpectedly
- **Web-based UI** — A frontend to visualize job progress, screenshots, and results (API is already available)
- **Concurrent job processing** — Currently only one job runs at a time
- **Database migrations** — Schema is static; no migration system for adding new fields

## Known Issues

- **Monolithic job runner** — Build, server management, and Minecraft testing logic are all in `job_runner.py`. These should be split into separate modules.
- **No per-version status tracking** — The `test_results` field is a flat dict. There's no way to independently track which versions succeeded or failed within a multi-version job.
- **Duplicated response formatting** — The `test_results` dict-to-list conversion is repeated across multiple API endpoints in `main.py`.
- **Static database schema** — No migration system; adding new columns requires manual intervention.

# AI Disclosure

This project is largely vibe-coded. This is mostly fine as this is for internal use only.
