# Plan: Proxy Support (Velocity)

## Overview

Add support for routing Minecraft clients through a proxy (currently Velocity only) between the client and PicoLimbo server. The architecture becomes:

```
Minecraft Client → Proxy (Velocity:25565) → PicoLimbo (127.0.0.1:30066)
```

vs. the current direct connection:

```
Minecraft Client → PicoLimbo (127.0.0.1:25565)
```

## Design Decisions (Resolved)

| Decision | Choice |
|----------|--------|
| Opt-in per-job or global? | **Opt-in per-job** via `JobCreate.proxy` field (default `"none"`) |
| Velocity version strategy | **Always latest** stable build from PaperMC API |
| Old Minecraft version compatibility | **No verification** — let the test fail naturally |
| PicoLimbo port | **Bind to `127.0.0.1:30066`** when proxy is enabled |
| Proxy types | **None, Velocity, BungeeCord** — Velocity only for now |

## Architecture

### New Module: `src/proxy/`

```
src/proxy/
├── __init__.py        # Exports ProxyType, ProxyManager, get_proxy_manager
├── base.py            # Abstract ProxyManager base class
├── velocity.py        # Velocity-specific implementation
└── bungeecord.py      # Placeholder for future BungeeCord support
```

### New Enum: `ProxyType`

```python
from enum import Enum

class ProxyType(str, Enum):
    NONE = "none"
    VELOCITY = "velocity"
    BUNGEECORD = "bungeecord"
```

### Updated Models: `src/models.py`

Add `proxy: str = "none"` to `JobCreate`:

```python
class JobCreate(BaseModel):
    repo_url: Optional[str] = Field(
        default="https://github.com/Quozul/PicoLimbo.git",
        description="GitHub repository URL (must be github.com)",
    )
    ref: Optional[str] = Field(
        default="master",
        description="Branch name or commit hash",
    )
    versions: Optional[list[str]] = Field(
        default=None,
        description="List of Minecraft versions to test (default: all versions)",
    )
    proxy: str = Field(
        default="none",
        description="Proxy type: none, velocity, bungeecord",
    )
```

### Updated Job Runner: `src/orchestration/job_runner.py`

The `_server_step` function will be extended to:

1. Accept a `proxy_type: str = "none"` parameter
2. If proxy is enabled:
   - Download/prepare Velocity jar (if not cached)
   - Write `velocity.toml` config
   - Start Velocity process (wait for readiness)
   - Write PicoLimbo config with internal port (30066)
3. Start PicoLimbo on the internal port
4. Write `servers.dat` pointing to the proxy address (127.0.0.1:25565)
5. Track both processes for cleanup

### Proxy Cache Structure

```
cache/proxies/
├── velocity/
│   ├── velocity-4.2.3.jar
│   └── metadata.json  # {"version": "4.2.3", "downloaded_at": "...", "minecraft_version": "26.1.2"}
```

## PaperMC API: Downloading Velocity

### API Endpoints

The PaperMC Fill API provides Velocity builds at:

```
https://fill.papermc.io/v3/projects/velocity/versions/<mc_version>/builds
```

Example response for `https://fill.papermc.io/v3/projects/velocity/versions/1.21.8/builds`:

```json
[
  {
    "id": 343,
    "channel": "STABLE",
    "downloads": {
      "server": {
        "default": {
          "url": "https://cdn.papermc.io/velocity/velocity-4.2.3.jar",
          "sha512": "..."
        }
      }
    }
  },
  {
    "id": 342,
    "channel": "BETA",
    ...
  }
]
```

### Download Logic (Python)

```python
import httpx
from pathlib import Path

VELOCITY_API_BASE = "https://fill.papermc.io/v3/projects/velocity"
PROXY_CACHE_DIR = Path("/app/cache/proxies")

def get_latest_velocity_version() -> str:
    """Get the latest Minecraft version that has a stable Velocity build."""
    # Get all versions for Velocity project
    resp = httpx.get(f"{VELOCITY_API_BASE}/versions")
    resp.raise_for_status()
    versions = resp.json()  # e.g. ["1.21.8", "1.21.7", ...]
    return versions[0]  # Latest first

def get_velocity_download_url(mc_version: str) -> str | None:
    """Get the download URL for the latest stable Velocity build for a given MC version."""
    resp = httpx.get(f"{VELOCITY_API_BASE}/versions/{mc_version}/builds")
    resp.raise_for_status()
    builds = resp.json()
    
    # Find the latest stable build
    stable_builds = [b for b in builds if b["channel"] == "STABLE"]
    if not stable_builds:
        return None
    
    latest = stable_builds[0]  # Builds are ordered newest first
    return latest["downloads"]["server"]["default"]["url"]

def download_velocity_if_needed() -> Path:
    """Download Velocity jar if not already cached. Returns path to jar."""
    cache_dir = PROXY_CACHE_DIR / "velocity"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    metadata_file = cache_dir / "metadata.json"
    cached_jar = None
    
    # Check if we have a cached version
    if metadata_file.exists():
        import json
        metadata = json.loads(metadata_file.read_text())
        cached_jar = cache_dir / f"velocity-{metadata['version']}.jar"
        if cached_jar.exists():
            # Check if the cached version is still the latest
            latest_mc_version = get_latest_velocity_version()
            if metadata.get("minecraft_version") == latest_mc_version:
                return cached_jar  # Skip download
    
    # Download latest
    mc_version = get_latest_velocity_version()
    download_url = get_velocity_download_url(mc_version)
    if not download_url:
        raise RuntimeError(f"No stable Velocity build found for MC version {mc_version}")
    
    jar_filename = f"velocity-{mc_version}.jar"
    jar_path = cache_dir / jar_filename
    
    # Download
    resp = httpx.get(download_url)
    resp.raise_for_status()
    jar_path.write_bytes(resp.content)
    
    # Save metadata
    metadata_file.write_text(json.dumps({
        "version": mc_version,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "minecraft_version": mc_version,
    }))
    
    return jar_path
```

## Implementation Steps

### Step 1: Add ProxyType enum and base proxy manager

**Files**: `src/proxy/__init__.py`, `src/proxy/base.py`

- Define `ProxyType` enum with `NONE`, `VELOCITY`, and `BUNGEECORD` values
- Create abstract `ProxyManager` base class with:
  - `download_if_needed() → Path` — returns path to jar
  - `start(config_dir: Path, pico_limbo_port: int) → subprocess.Popen` — starts the proxy
  - `stop(proc: subprocess.Popen) → None` — kills the proxy process
  - `wait_for_ready(proc: subprocess.Popen, timeout: float = 30) → None` — waits for proxy to be ready
  - `config_template(pico_limbo_port: int) → dict` — returns config values for the proxy
- Factory function `get_proxy_manager(proxy_type: str) → ProxyManager | None`

### Step 2: Implement Velocity proxy manager

**Files**: `src/proxy/velocity.py`

- Implement `VelocityProxyManager` extending `ProxyManager`
- **PaperMC API integration**:
  - Use `httpx` (already a dependency) to query `https://fill.papermc.io/v3/projects/velocity/versions`
  - Get the latest Minecraft version with a stable Velocity build
  - Query `https://fill.papermc.io/v3/projects/velocity/versions/{mc_version}/builds`
  - Filter for `channel == "STABLE"`, take the first build
  - Download from `builds[0]["downloads"]["server"]["default"]["url"]`
- **Cache logic**:
  - Check `cache/proxies/velocity/` for existing jar + `metadata.json`
  - If metadata exists and `minecraft_version` matches the latest, reuse the cached jar
  - Otherwise, download the latest and overwrite
- **Config generation** (`velocity.toml`):
  ```toml
  bind = "0.0.0.0:25565"
  online-mode = false
  player-info-forwarding-mode = "none"
  
  [servers]
  limbo = "127.0.0.1:<pico_limbo_port>"
  try = ["limbo"]
  ```
- **Readiness detection**: Parse Velocity stdout for the log lines:
  ```
  [15:37:31 INFO]: Listening on /[0:0:0:0:0:0:0:0]:25565
  [15:37:31 INFO]: Done (1.13s)!
  ```
  Wait until "Done" line appears (or "Listening on" as a minimum).

### Step 3: Update models

**Files**: `src/models.py`

- Add `proxy: str = Field(default="none", description="Proxy type: none, velocity, bungeecord")` to `JobCreate`
- No validation at model level — validation happens in the job runner

### Step 4: Update job runner

**Files**: `src/orchestration/job_runner.py`

- Update `_server_step` signature: `def _server_step(job: dict, versions: list[str], proxy_type: str = "none") -> tuple[Optional[subprocess.Popen], Optional[subprocess.Popen]]`
  - Returns `(velocity_proc, pico_limbo_proc)` — both can be `None`
- When proxy is `"velocity"`:
  - Use `VelocityProxyManager` to download and start Velocity
  - PicoLimbo binds to `127.0.0.1:30066` (change `SERVER_CONFIG_CONTENT`)
  - `SERVER_ADDRESS` remains `127.0.0.1:25565` (pointing to proxy)
  - Velocity writes its own config to a temp directory
  - Start Velocity first, wait for it to be ready, then start PicoLimbo
- When proxy is `"none"`:
  - Current behavior unchanged (PicoLimbo on `0.0.0.0:25565`)
- Update `_kill_server` to accept both processes and kill them in reverse order (PicoLimbo first, then Velocity)
- Update `run_job` to:
  - Extract `proxy_type` from job (default `"none"`)
  - Pass `proxy_type` to `_server_step`
  - Handle the tuple return from `_server_step`

### Step 5: Update API layer

**Files**: `src/main.py`

- The `JobCreate` model change is automatic (FastAPI picks it up)
- No additional API changes needed — the proxy field flows through naturally to the job runner

### Step 6: Update Web UI

**Files**: `webui/src/components/JobCreation.tsx`

- Add a new dropdown/select field for proxy type selection
- Options: `None`, `Velocity`, `BungeeCord` (BungeeCord shown but not functional yet)
- Default value: `None`
- Pass the selected proxy value as `proxy` field in the job creation request to the API

Example UI addition:

```tsx
<div className="form-group">
  <label htmlFor="proxy">Proxy</label>
  <select
    id="proxy"
    value={jobForm.proxy}
    onChange={(e) => setJobForm({...jobForm, proxy: e.target.value})}
  >
    <option value="none">None</option>
    <option value="velocity">Velocity</option>
    <option value="bungeecord">BungeeCord (coming soon)</option>
  </select>
</div>
```

The `jobForm` state should include `proxy: "none"` as initial value.

### Step 7: Update Dockerfile

**Files**: `Dockerfile`

- No new dependencies needed (Java is already installed via `default-jre-headless`, `httpx` is already a Python dependency)
- No changes required

### Step 8: Add tests

**Files**: `tests/test_proxy.py`

- Unit tests for `ProxyType` enum:
  - `test_none_value`
  - `test_velocity_value`
  - `test_bungeecord_value`
- Unit tests for `VelocityProxyManager`:
  - `test_download_if_needed_caches_existing_jar` — cached jar returned without re-downloading
  - `test_download_if_needed_fetches_new_version` — downloads when metadata is stale
  - `test_write_config_generates_valid_toml` — config file contains correct values
  - `test_wait_for_ready_detects_done_log` — parses "Done" line from stdout
  - `test_wait_for_ready_timeout` — raises on missing ready signal
- Integration test: job with `proxy="velocity"` runs end-to-end (mocked or real)

### Step 9: Update docker-compose

**Files**: `docker-compose.yml`

- Add volume mount for proxy cache: `./cache/proxies:/app/cache/proxies`

## File Changes Summary

| File | Change |
|------|--------|
| `src/proxy/__init__.py` | **NEW** — exports `ProxyType`, `ProxyManager`, `get_proxy_manager` |
| `src/proxy/base.py` | **NEW** — abstract `ProxyManager` base class |
| `src/proxy/velocity.py` | **NEW** — `VelocityProxyManager` with PaperMC API integration |
| `src/proxy/bungeecord.py` | **NEW** — placeholder (raises `NotImplementedError`) |
| `src/models.py` | Add `proxy` field to `JobCreate` |
| `src/orchestration/job_runner.py` | Extend `_server_step`, `_kill_server`, `run_job` for proxy lifecycle |
| `webui/src/components/JobCreation.tsx` | Add proxy dropdown to job creation form |
| `docker-compose.yml` | Add `./cache/proxies:/app/cache/proxies` volume |
| `tests/test_proxy.py` | **NEW** — proxy unit tests |

## Port & Address Mapping

| Mode | PicoLimbo Bind | Velocity Bind | Client Connects To | servers.dat Points To |
|------|---------------|---------------|-------------------|----------------------|
| `none` | `0.0.0.0:25565` | N/A | `127.0.0.1:25565` | `127.0.0.1:25565` |
| `velocity` | `127.0.0.1:30066` | `0.0.0.0:25565` | `127.0.0.1:25565` | `127.0.0.1:25565` |

## Velocity Readiness Detection

Velocity prints these log lines on startup:

```
[15:37:31 INFO]: Listening on /[0:0:0:0:0:0:0:0]:25565
[15:37:31 INFO]: Done (1.13s)!
```

The `wait_for_ready` method should:
1. Read from Velocity's stdout line by line
2. Check for `"Listening on"` as a minimum readiness signal
3. Prefer waiting for `"Done"` for full confirmation
4. Timeout after 30 seconds with a `RuntimeError` if neither appears

## Future Extensions

- **BungeeCord support**: Add `BungeeCordProxyManager` in `src/proxy/bungeecord.py`
- **Proxy version pinning**: Allow specifying a specific Velocity version in `JobCreate`
- **Forwarding mode support**: Add support for Velocity's `FORWARD` forwarding mode (requires shared secret)
- **Version compatibility matrix**: Filter out Minecraft versions incompatible with the selected proxy
