# Refactoring Plan: Reducing Coupling Across the Codebase (DDD Edition)

> This plan supersedes `docs/PLAN.md` and `docs/PLAN_REVISED.md`. It incorporates all previous findings and adds Domain-Driven Design structure: aggregates, entities, value objects, domain services, anti-corruption layer, and repository pattern.

---

## Part 1: Current Problems (All Findings from PLAN_REVISED)

### 1.1 `src/orchestration/job_runner.py` — the central coupling hub

`job_runner.py` (290 lines) directly imports and calls 6+ external modules. `update_job` is called 8+ times with different field combinations; `get_job_by_id` is called 4 times. The function re-fetches the job from the database three times (lines 229, 240, 249) because state is mutated via side effects rather than returned values.

| Function | Lines | Responsibilities |
|----------|-------|-----------------|
| `run_job` | 228–290 (73 lines) | Fetch job, determine versions, orchestrate build, orchestrate server, orchestrate test, update status, handle errors/cleanup, track process lifecycle |
| `_server_step` | 127–179 (55 lines) | Validate artifact, extract config, start proxy, wait for proxy, write servers.dat, write server.toml, start PicoLimbo subprocess, poll stdout, handle startup failure |
| `_test_step` | 191–224 (42 lines) | Create VirtualInputController, manage try/finally, loop over versions with cancellation, update DB per version, call test_single_version, accumulate/persist results, kill servers |

**Implicit cross-step communication**: `_build_step` sets `artifact_path` via the database, but `run_job` must re-fetch the job (line 240) to see it. Control flow is split across functions communicating via a shared mutable dict + database, not return values.

### 1.2 `src/proxy/velocity.py` — SRP violations and security risk

| Function | Lines | Problems |
|----------|-------|----------|
| `start()` | 103–138 (36 lines) | Generate/write velocity.toml config, write forwarding.secret, copy plugins, download jar, start Java subprocess |
| `_generate_config()` | 204–223 (20 lines) | Hand-rolled TOML serializer via f-strings — incomplete (no `int`, `datetime`, or inline table support) |
| `_copy_plugins()` | 139–165 (27 lines) | Dual `plugin`/`plugins` parameters with no deduplication or validation |
| `wait_for_ready()` | 152–187 (36 lines) | Busy-polling with `time.sleep(0.1)`, `remaining = proc.stdout.read()` at line 168 is unreachable |
| `download_if_needed()` | 45–90 (46 lines) | Three nested branches for `latest_mc_version`, assign-then-check-again pattern |

**Security**: `_FORWARDING_SECRET = "sup3r-s3cr3t"` (line 131) is a hardcoded class-level secret.

### 1.3 `src/database.py` — schema migrations baked into data access

| Function | Lines | Problems |
|----------|-------|----------|
| `_ensure_db()` | 18–74 | Directory creation + schema creation + 5 blind `ALTER TABLE` migration attempts — every DB operation pays this cost |
| `_row_to_dict()` | 195–235 | 4 `try/except KeyError` fallback paths for migrated columns — zero test coverage |
| `create_job()` | 88–126 | 10 parameters, legacy `plugin`/`plugins` conversion, double DB call (insert then select) |
| `get_connection()` | 77–85 | Implicit side effects: calls `_ensure_db()`, enables WAL mode |
| `update_job()` | 143–156 | **SQL injection vulnerability** — column names from `**fields` dict keys with zero validation |

**Global mutable state**: `DB_PATH = Path("/app/builds/jobs.db")` (line 9).

### 1.4 `src/builder/engine.py` — module-level globals and misleading contracts

| Function | Lines | Problems |
|----------|-------|----------|
| `create_job()` | 128–158 (31 lines) | 5 responsibilities, 9 parameters, misleading docstring, dead `import json` |
| `resolve_commit()` | 95–113 (19 lines) | Name implies read-only lookup but also checks out the ref |
| `build_project()` | 111–132 (22 lines) | 5 responsibilities, wrong error message on line 126 |

**Bug**: `COMMIT_HASH_RE = r"^[0-9a-f]{40}$"` (line 28) rejects valid uppercase hex hashes.

**Module-level globals**: `REPOS_DIR` and `BUILDS_DIR` (lines 17–18).

### 1.5 `src/minecraft/runner.py` — untested core logic

| Function | Lines | Problems |
|----------|-------|----------|
| `test_single_version()` | 177–220 (44 lines) | 6 responsibilities, 3 levels of nesting, **zero tests** |
| `wait_for_game()` | 89–127 (39 lines) | Combines window discovery, positioning, menu detection — no tests |
| `log_to_multiplayer()` | 130–152 (23 lines) | Hardcoded click coordinates with no semantic meaning — no tests |
| `start_minecraft()` | 154–173 (20 lines) | Hardcoded JVM args, resolution — no tests |

**Dead code**: `from ..versions import Version` (line 23) unused. `window_id` parameter in `capture_screenshot` (line 169) ignored.

**7 of 10 public functions entirely untested.**

### 1.6 `src/minecraft/wait_for.py` — God function

`wait_for_screen_region()` (lines 18–90, 73 lines) does 5 things: directory validation, reference image loading, polling loop, image comparison, debug image saving. 3 levels of nesting.

### 1.7 `src/minecraft/env.py` — no abstraction layer for nbtlib

Both `create_options_txt()` and `create_servers_dat()` mix business logic with filesystem I/O. Parent-directory creation is duplicated verbatim. Option key/value pairs are hardcoded magic strings.

### 1.8 `src/versions.py` — unconventional `__new__` factory

`Version.__new__` (lines 2–58) uses dual-path dispatch (string vs. integer form). `supports_option()` and `is_lwjgl2()` create sentinel `Version(…, 0)` objects. 55% of tests use unnecessary `@patch(ALL_VERSIONS)`.

### 1.9 `src/main.py` — module-level side effects and duplicated response logic

`worker.start_queue_worker()` runs at module import time (line 40). `get_job()` and `list_jobs()` duplicate the same response-building block. `/{full_path:path}` catch-all route is fragile.

### 1.10 Test file coupling patterns

| Test File | Problems |
|-----------|----------|
| `test_job_runner_idempotency.py` (36.7KB) | 60% test mock call patterns. `_make_path_mock()` engineers fake `Path` objects. |
| `test_proxy.py` | `test_stop_forces_kill_on_timeout` patches wrong target — **false positive**. `TestJobRunnerProxyIntegration` tests job_runner, not velocity. |
| `test_engine.py` | `_make_path_mock()` helper. `TestCreateJob` verifies exact positional argument order. `Path.exists` patched globally. |
| `test_wait_for.py` | `test_passes_correct_bbox_to_grab` is a **no-op** (ends with `pass`). Heavy mock plumbing. |
| `test_minecraft_runner.py` | `TestCaptureScreenshot` mocks `get_window_info` which is never called. |
| `test_minecraft_env.py` | `mock_nbt` fixture patches all nbtlib symbols — no test writes a real NBT file. |
| `test_versions.py` | 16 of 28+ tests use `@patch(ALL_VERSIONS)` unnecessarily. |
| `test_api.py` | Module-level `sys.modules` mutation. `_make_job` couples to internal DB format. |
| `test_plugin_api.py` | Global `sys.modules` mutation at import time. Engine tests assert positional argument order. Database tests mixed into API test file. |

---

## Part 2: DDD Analysis — External Service Coupling

Beyond the problems listed above, the codebase has a deeper structural issue: **external service calls are embedded directly in business logic**, making them impossible to test in isolation and impossible to swap implementations.

### 2.1 Pattern 1: Git Operations (engine.py)

```python
# engine.py — current state: git commands scattered in business logic
def ensure_repo_cloned(owner, repo_name):
    _run(["git", "clone", "--depth", "1", f"https://github.com/{owner}/{repo_name}.git", ...])

def update_repo(repo_path, ref):
    _run(["git", "fetch", "--depth=1", "origin", ref], ...)
    _run(["git", "checkout", "FETCH_HEAD"], ...)

def resolve_commit(repo_path, ref):
    _run(["git", "checkout", ref], ...)
    _run(["git", "rev-parse", "HEAD"], ...)
```

**Problems**:
- Git is called as a subprocess with raw command strings — no abstraction
- `REPOS_DIR` is a hardcoded module-level global
- `_run()` is a thin wrapper with a hardcoded 1800s timeout
- `resolve_commit()` mutates filesystem but has a read-only name
- Tests must mock `subprocess.run` globally — fragile and verbose

### 2.2 Pattern 2: PaperMC API (velocity.py)

```python
# velocity.py — current state: PaperMC API calls embedded in proxy manager
def _get_latest_mc_version(self):
    resp = httpx.get(f"{VELOCITY_API_BASE}/versions", timeout=30.0)
    ...

def _get_velocity_download_url(self, mc_version):
    resp = httpx.get(f"{VELOCITY_API_BASE}/versions/{mc_version}/builds", timeout=30.0)
    ...

def _download_file(self, url, dest):
    resp = httpx.get(url, timeout=120.0, follow_redirects=True)
    dest.write_bytes(resp.content)
```

**Problems**:
- `VELOCITY_API_BASE` and `PROXY_CACHE_DIR` are hardcoded module-level globals
- Three separate HTTP calls with different URL patterns — no unified API client
- `_download_file()` also handles partial download cleanup — mixes HTTP with filesystem
- `download_if_needed()` has three nested branches — hard to test error paths
- Tests must mock `httpx.get` at module level — fragile

### 2.3 Pattern 3: Minecraft Launcher API (runner.py)

```python
# runner.py — current state: minecraft_launcher_lib calls in business logic
def start_minecraft(version):
    minecraft_directory = minecraft_launcher_lib.utils.get_minecraft_directory()
    minecraft_launcher_lib.install.install_minecraft_version(version, minecraft_directory)
    options = minecraft_launcher_lib.utils.generate_test_options()
    minecraft_command = minecraft_launcher_lib.command.get_minecraft_command(version, minecraft_directory, options)
    return subprocess.Popen(minecraft_command, ...)
```

**Problems**:
- `minecraft_launcher_lib` is imported at module level — import failure breaks entire module
- `GAME_DIRECTORY` is hardcoded
- JVM args and resolution are hardcoded strings
- No abstraction — if `minecraft_launcher_lib` API changes, `start_minecraft` breaks

### 2.4 Pattern 4: xdotool Window Management (runner.py)

```python
# runner.py — current state: xdotool subprocess calls scattered
def get_minecraft_window():
    subprocess.run(["xdotool", "search", "--name", title], ...)

def get_window_info(window_id):
    subprocess.run(["xdotool", "getwindowgeometry", window_id], ...)

def wait_for_game(version):
    subprocess.run(["xdotool", "windowmove", window_id, "0", "0"], ...)
```

**Problems**:
- xdotool calls are scattered across `get_minecraft_window()`, `get_window_info()`, and `wait_for_game()`
- No abstraction — each call is a raw subprocess invocation
- `wait_for_game()` mixes window discovery, positioning, and menu detection

### 2.5 Pattern 5: Cargo Build (engine.py)

```python
# engine.py — current state: cargo build embedded in business logic
def build_project(repo_path, commit_hash, owner, ref):
    _run(["cargo", "build", "--release"], cwd=repo_path)
```

**Problems**:
- `cargo` is called via subprocess with hardcoded flags
- Mixed with artifact directory creation and file copying
- `BUILDS_DIR` hardcoded at module level

---

## Part 3: DDD Model — Aggregates, Entities, Value Objects, Domain Services

### 3.1 Aggregate: `Job`

The `Job` is the central aggregate root. Everything else revolves around it.

```
Job (Aggregate Root)
├── job_id: JobId (value object)
├── repo_url: RepoUrl (value object)
├── ref: Ref (value object — branch name or commit hash)
├── commit_hash: CommitHash (value object, resolved from ref)
├── status: JobStatus (value object: queued, building, testing, finished, failed)
├── versions: list[Version] (value objects)
├── proxy_type: ProxyType (value object: none, velocity, bungeecord)
├── forwarding_method: ForwardingMethod (value object)
├── plugins: list[str]
├── login_wait_timeout: int
├── test_results: dict[str, TestResult] (value objects, accumulated)
├── artifact_path: ArtifactPath | None (value object)
├── created_at: datetime
└── updated_at: datetime
```

**Invariants the aggregate enforces**:
- A job in "building" status cannot have test_results
- A job in "testing" status must have an artifact_path
- A job in "finished" or "failed" status cannot be modified

### 3.2 Supporting Value Objects

| Value Object | Purpose |
|-------------|---------|
| `JobId` | Unique job identifier (UUID) |
| `RepoUrl` | Validated GitHub URL |
| `Ref` | Branch name or commit hash |
| `CommitHash` | 40-char hex string (validated, case-insensitive) |
| `JobStatus` | State machine: queued → building → testing → finished/failed |
| `Version` | Minecraft version string (refactored from current `Version` class) |
| `ProxyType` | none, velocity, bungeecord |
| `ForwardingMethod` | none, legacy, bungeeguard, modern |
| `TestResult` | version, passed, screenshot_path, duration_seconds, error |
| `ArtifactPath` | Path to built binary |

### 3.3 Domain Services

These are stateless services that orchestrate use cases using repositories and other services:

| Domain Service | Responsibility |
|---------------|---------------|
| `JobOrchestrator` | Orchestrates the full job lifecycle: build → server setup → test → result persistence |
| `BuildService` | Resolves ref, clones/updates repo, builds artifact, returns `BuildResult` |
| `TestService` | Iterates versions, runs tests, accumulates results |
| `ServerSetupService` | Configures proxy, writes config files, starts PicoLimbo |

### 3.4 Anti-Corruption Layer (ACL)

Each external service gets a dedicated adapter that isolates the domain from external API changes:

| ACL Adapter | Wraps | Purpose |
|------------|-------|---------|
| `GitRepository` | `subprocess.run(["git", ...])` | Clone, fetch, checkout, resolve commit |
| `CargoBuildAdapter` | `subprocess.run(["cargo", ...])` | Build PicoLimbo binary |
| `ArtifactRepository` | PaperMC API (`httpx.get`) | Download Velocity jar, manage cache |
| `MinecraftLauncher` | `minecraft_launcher_lib` | Install MC, get command, generate options |
| `WindowManager` | xdotool subprocess | Search windows, get geometry, move windows |
| `ScreenRegionMatcher` | PIL/pyscreenshot | Wait for screen region match |
| `ConfigWriter` | nbtlib, file I/O | Write servers.dat, options.txt, velocity.toml |

### 3.5 Repository Pattern

| Repository | Persists | Storage |
|-----------|---------|---------|
| `JobRepository` | `Job` aggregate | SQLite (current `database.py`) |
| `ArtifactStorage` | Build artifacts, screenshots | File system |

---

## Part 4: Proposed Structure (DDD-Aligned)

```
src/
├── domain/
│   ├── __init__.py
│   ├── job.py                    # Job aggregate root + invariants
│   ├── value_objects.py          # JobId, RepoUrl, Ref, CommitHash, JobStatus, Version, ProxyType, TestResult, etc.
│   ├── services.py               # JobOrchestrator, BuildService, TestService, ServerSetupService (interfaces)
│   └── events.py                 # JobCreated, JobStatusChanged, TestResultPersisted
│
├── infrastructure/
│   ├── __init__.py
│   ├── git_repository.py         # GitRepository — wraps subprocess git commands
│   ├── cargo_build.py            # CargoBuildAdapter — wraps cargo build
│   ├── artifact_repository.py    # ArtifactRepository — wraps PaperMC API
│   ├── minecraft_launcher.py     # MinecraftLauncher — wraps minecraft_launcher_lib
│   ├── window_manager.py         # WindowManager — wraps xdotool
│   ├── screen_region.py          # ScreenRegionMatcher — wraps PIL/pyscreenshot
│   ├── config_writer.py          # ConfigWriter — wraps nbtlib, file I/O
│   └── database.py               # SQLiteJobRepository — persists Job aggregate
│
├── application/
│   ├── __init__.py
│   ├── job_orchestrator.py       # JobOrchestrator — uses domain services + repositories
│   └── build_service.py          # BuildService — uses GitRepository + CargoBuildAdapter
│
├── proxy/
│   ├── __init__.py
│   ├── base.py                   # ProxyManager protocol (thin — just interface)
│   └── velocity.py               # VelocityProxyManager — uses ArtifactRepository + ConfigWriter
│
├── minecraft/
│   ├── __init__.py
│   ├── runner.py                 # MinecraftTestRunner — uses MinecraftLauncher + WindowManager + ScreenRegionMatcher
│   ├── env.py                    # (moved to infrastructure/config_writer.py)
│   ├── input.py                  # VirtualInputController — thin wrapper, keep as-is
│   └── wait_for.py               # (moved to infrastructure/screen_region.py)
│
├── builder/
│   ├── __init__.py
│   ├── engine.py                 # (reduced to thin facade or removed entirely)
│   └── worker.py                 # Queue worker — move startup to FastAPI startup event
│
├── config.py                     # All magic constants, paths, timeouts
├── di.py                         # Dependency injection wiring
├── main.py                       # API layer — thin, no business logic
└── versions.py                   # Version — refactor to pure value object
```

---

## Part 5: Anti-Corruption Layer — Detailed Design

### 5.1 `GitRepository` — isolates all git operations

```python
# infrastructure/git_repository.py
class GitRepository:
    """Anti-corruption layer for git operations.

    Replaces direct subprocess.run(["git", ...]) calls throughout the codebase.
    """
    def __init__(self, repos_dir: Path, timeout: float = 1800.0):
        self._repos_dir = repos_dir
        self._timeout = timeout

    def clone(self, owner: str, repo_name: str) -> Path:
        """Clone a GitHub repo. Returns the repo path."""
        repo_path = self._repos_dir / owner / repo_name
        if repo_path.exists() and (repo_path / ".git").exists():
            return repo_path
        self._run_git(["clone", "--depth", "1",
                       f"https://github.com/{owner}/{repo_name}.git",
                       str(repo_path)])
        return repo_path

    def update(self, repo_path: Path, ref: str) -> None:
        """Fetch and checkout a ref."""
        self._run_git(["fetch", "--depth=1", "origin", ref], cwd=repo_path)
        self._run_git(["checkout", "FETCH_HEAD"], cwd=repo_path)

    def resolve(self, repo_path: Path, ref: str) -> CommitHash:
        """Resolve a ref to a commit hash. Checkout the ref as a side effect."""
        if is_commit_hash(ref):
            self._run_git(["checkout", ref], cwd=repo_path)
            return CommitHash(ref)
        self.update(repo_path, ref)
        output = self._run_git(["rev-parse", "HEAD"], cwd=repo_path)
        return CommitHash(output)

    def _run_git(self, args: list[str], cwd: Path | None = None) -> str:
        ...  # Single subprocess wrapper with timeout
```

**Benefits**:
- All git operations in one place — easy to swap for a library like `gitpython` or test with a mock
- `REPOS_DIR` is a constructor parameter, not a module-level global
- Timeout is configurable per instance
- Tests inject `MockGitRepository` — no subprocess mocking needed

### 5.2 `ArtifactRepository` — isolates PaperMC API

```python
# infrastructure/artifact_repository.py
class ArtifactRepository:
    """Anti-corruption layer for artifact downloads (PaperMC API).

    Replaces direct httpx.get() calls in VelocityProxyManager.
    """
    def __init__(self, api_base: str, cache_dir: Path, http_client: httpx.AsyncClient | None = None):
        self._api_base = api_base
        self._cache_dir = cache_dir
        self._http = http_client or httpx.Client()

    def get_latest_mc_version(self) -> str:
        """Fetch latest MC version with a stable Velocity build from PaperMC API."""
        resp = self._http.get(f"{self._api_base}/versions", timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        versions = data.get("versions", [])
        if not versions:
            raise RuntimeError("No Minecraft versions found for Velocity")
        return versions[0]["version"]["id"]

    def get_download_url(self, mc_version: str) -> str | None:
        """Get download URL for the latest stable Velocity build for a given MC version."""
        resp = self._http.get(f"{self._api_base}/versions/{mc_version}/builds", timeout=30.0)
        resp.raise_for_status()
        builds = resp.json()
        stable = [b for b in builds if b.get("channel") == "STABLE"]
        if not stable:
            return None
        download_info = stable[0].get("downloads", {}).get("server:default")
        return download_info.get("url") if download_info else None

    def download(self, url: str, dest: Path) -> Path:
        """Download a file. Cleans up partial downloads on failure."""
        try:
            resp = self._http.get(url, timeout=120.0, follow_redirects=True)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return dest
        except httpx.HTTPError:
            if dest.exists():
                dest.unlink()
            raise

    def get_cached_or_download(self, mc_version: str) -> Path:
        """Get cached jar if available, otherwise download."""
        cached = self._cache_dir / f"velocity-{mc_version}.jar"
        if cached.exists():
            return cached
        url = self.get_download_url(mc_version)
        if not url:
            raise RuntimeError(f"No stable build for MC {mc_version}")
        return self.download(url, cached)
```

**Benefits**:
- PaperMC API calls are isolated in one class
- `api_base` and `cache_dir` are constructor parameters
- `http_client` is injectable — tests can use `httpx.MockTransport`
- `download_if_needed()` in `VelocityProxyManager` becomes a one-liner: `return self.artifact_repo.get_cached_or_download(mc_version)`

### 5.3 `MinecraftLauncher` — isolates minecraft_launcher_lib

```python
# infrastructure/minecraft_launcher.py
class MinecraftLauncher:
    """Anti-corruption layer for minecraft_launcher_lib.

    Replaces direct minecraft_launcher_lib calls in runner.py.
    """
    def __init__(self, game_directory: Path | None = None,
                 jvm_args: list[str] | None = None,
                 resolution: tuple[int, int] | None = None):
        self._game_directory = game_directory or Path("minecraft")
        self._jvm_args = jvm_args or ["-Xmx2G", "-Xms2G"]
        self._resolution = resolution or (1024, 768)

    def get_command(self, version: str) -> list[str]:
        """Get the Minecraft launch command for a version."""
        directory = minecraft_launcher_lib.utils.get_minecraft_directory()
        minecraft_launcher_lib.install.install_minecraft_version(version, directory)
        options = minecraft_launcher_lib.utils.generate_test_options()
        options["jvmArguments"] = self._jvm_args
        options["customResolution"] = True
        options["resolutionWidth"] = str(self._resolution[0])
        options["resolutionHeight"] = str(self._resolution[1])
        options["gameDirectory"] = str(self._game_directory)
        return minecraft_launcher_lib.command.get_minecraft_command(version, directory, options)
```

**Benefits**:
- Hardcoded JVM args and resolution are constructor parameters
- Tests inject `MockMinecraftLauncher` — no module-level `minecraft_launcher_lib` patching
- If `minecraft_launcher_lib` API changes, only this file needs updating

### 5.4 `WindowManager` — isolates xdotool

```python
# infrastructure/window_manager.py
class WindowManager:
    """Anti-corruption layer for xdotool window management.

    Replaces scattered subprocess.run(["xdotool", ...]) calls.
    """
    def search_by_name(self, pattern: str) -> str | None:
        """Search for a window by name pattern. Returns window ID or None."""
        result = subprocess.run(["xdotool", "search", "--name", pattern],
                                capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
        return None

    def search_by_class(self, class_name: str) -> str | None:
        """Search for a window by class. Returns last match or None."""
        result = subprocess.run(["xdotool", "search", "--class", class_name],
                                capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[-1]
        return None

    def get_geometry(self, window_id: str) -> dict[str, int] | None:
        """Get window geometry. Returns {x, y, width, height} or None."""
        result = subprocess.run(["xdotool", "getwindowgeometry", window_id],
                                capture_output=True, text=True)
        return parse_window_info(result.stdout.strip())

    def move_to(self, window_id: str, x: int, y: int) -> None:
        """Move a window to absolute coordinates."""
        subprocess.run(["xdotool", "windowmove", window_id, str(x), str(y)],
                       capture_output=True)
```

**Benefits**:
- All xdotool calls consolidated in one class
- `parse_window_info` is a pure function, easily tested
- Tests inject `MockWindowManager` — no subprocess mocking needed

### 5.5 `CargoBuildAdapter` — isolates cargo build

```python
# infrastructure/cargo_build.py
class CargoBuildAdapter:
    """Anti-corruption layer for cargo build commands.

    Replaces subprocess.run(["cargo", "build", ...]) in engine.py.
    """
    def __init__(self, timeout: float = 1800.0, release: bool = True):
        self._timeout = timeout
        self._release = release

    def build(self, repo_path: Path) -> Path:
        """Build the project. Returns path to the binary."""
        flags = ["build", "--release"] if self._release else ["build"]
        subprocess.run(["cargo"] + flags, cwd=str(repo_path),
                       capture_output=True, text=True, timeout=self._timeout)
        # Verify artifact exists
        source = repo_path / "target" / "release" / "pico_limbo"
        if not source.exists():
            raise FileNotFoundError(f"Build artifact not found at {source}")
        return source
```

### 5.6 `ConfigWriter` — isolates nbtlib and file I/O

```python
# infrastructure/config_writer.py
class ConfigWriter:
    """Anti-corruption layer for configuration file generation.

    Replaces direct nbtlib, TOML, and file I/O in env.py and velocity.py.
    """
    def __init__(self, version_support: VersionSupport | None = None):
        self._version_support = version_support or VersionSupport()

    def write_servers_dat(self, output_path: Path, servers: list[ServerEntry]) -> None:
        """Write servers.dat using nbtlib."""
        ...

    def write_options_txt(self, output_path: Path, version: Version) -> None:
        """Write options.txt with version-appropriate options."""
        ...

    def write_velocity_toml(self, output_path: Path, config: dict) -> None:
        """Write velocity.toml using tomli-w."""
        ...
```

---

## Part 6: Domain Services — How They Use the ACL

### 6.1 `BuildService` — uses `GitRepository` + `CargoBuildAdapter`

```python
# application/build_service.py
class BuildService:
    def __init__(self, git_repo: GitRepository,
                 cargo: CargoBuildAdapter,
                 artifact_storage: ArtifactStorage,
                 builds_dir: Path):
        self._git = git_repo
        self._cargo = cargo
        self._storage = artifact_storage
        self._builds_dir = builds_dir

    def build(self, job: Job) -> BuildResult:
        """Build a job: clone/update repo, resolve commit, build artifact."""
        owner, repo_name = RepoUrl(job.repo_url).parse()

        # Git: clone or update
        repo_path = self._git.clone(owner, repo_name)
        self._git.update(repo_path, job.ref)

        # Git: resolve commit
        commit_hash = self._git.resolve(repo_path, job.ref)

        # Build
        source = self._cargo.build(repo_path)

        # Persist artifact
        artifact_path = self._storage.store(source, job, commit_hash)

        return BuildResult(commit_hash=commit_hash, artifact_path=artifact_path)
```

**Before** (engine.py): `create_job()` calls `ensure_repo_cloned()`, `resolve_commit()`, and `build_project()` — all with hardcoded paths and direct subprocess calls.

**After**: `BuildService.build()` uses injected `GitRepository` and `CargoBuildAdapter`. All external calls are in the ACL. Tests inject mocks.

### 6.2 `ServerSetupService` — uses `ArtifactRepository` + `ConfigWriter` + `WindowManager`

```python
# application/server_setup_service.py
class ServerSetupService:
    def __init__(self, proxy_factory: ProxyFactory,
                 config_writer: ConfigWriter,
                 artifact_repo: ArtifactRepository):
        self._proxy_factory = proxy_factory
        self._config = config_writer
        self._artifact_repo = artifact_repo

    def setup(self, job: Job) -> ServerContext:
        """Set up proxy, config, and PicoLimbo subprocess."""
        # Proxy: download jar if needed, start
        proxy = self._proxy_factory.create(job.proxy_type)
        if job.proxy_type != ProxyType.NONE:
            proxy.start(config_dir=...)  # uses ArtifactRepository internally

        # Config: write servers.dat, options.txt
        self._config.write_servers_dat(...)
        self._config.write_options_txt(...)

        # Start PicoLimbo subprocess...
        return ServerContext(proxy, pico_limbo_proc, cleanup)
```

### 6.3 `TestService` — uses `MinecraftLauncher` + `WindowManager` + `ScreenRegionMatcher`

```python
# application/test_service.py
class TestService:
    def __init__(self, minecraft: MinecraftLauncher,
                 window_manager: WindowManager,
                 screen_matcher: ScreenRegionMatcher,
                 input_controller: VirtualInputController,
                 screenshot_dir: Path):
        self._minecraft = minecraft
        self._wm = window_manager
        self._screen = screen_matcher
        self._input = input_controller
        self._screenshots = screenshot_dir

    def test_version(self, version: str, commit_hash: str) -> TestResult:
        """Test a single Minecraft version."""
        cmd = self._minecraft.get_command(version)
        process = subprocess.Popen(cmd, ...)

        # Window management
        window_id = self._wait_for_game(version)
        self._input.set_window(window_id)
        self._log_to_multiplayer(version)
        time.sleep(30)

        # Screenshot
        screenshot_path = self._capture_screenshot(version, commit_hash)

        return TestResult(version=version, passed=True, screenshot_path=screenshot_path)

    def _wait_for_game(self, version: str) -> str:
        """Wait for Minecraft main menu using WindowManager + ScreenRegionMatcher."""
        window_id = self._find_window(version)
        if is_lwjgl2_version(version):
            self._wm.move_to(window_id, 0, 0)
        self._screen.wait_for_region("references", _QUIT_REGION, timeout=15.0)
        return window_id
```

---

## Part 7: Dependency Injection — Wiring Everything

```python
# di.py
from pathlib import Path
from src.config import Config

def build_container(config: Config):
    """Wire all dependencies. Called once at startup."""

    # Infrastructure adapters
    git_repo = GitRepository(repos_dir=config.repos_dir, timeout=1800.0)
    cargo = CargoBuildAdapter(timeout=1800.0, release=True)
    artifact_repo = ArtifactRepository(
        api_base=config.papermc_api_base,
        cache_dir=config.proxy_cache_dir,
    )
    minecraft = MinecraftLauncher(
        game_directory=config.minecraft_dir,
        jvm_args=["-Xmx2G", "-Xms2G"],
        resolution=(1024, 768),
    )
    window_manager = WindowManager()
    screen_matcher = ScreenRegionMatcher()
    config_writer = ConfigWriter()
    job_repo = SQLiteJobRepository(db_path=config.db_path)

    # Domain services
    build_service = BuildService(git_repo, cargo, ArtifactStorage(config.builds_dir), config.builds_dir)
    test_service = TestService(minecraft, window_manager, screen_matcher, VirtualInputController(), config.screenshots_dir)
    server_setup = ServerSetupService(ProxyFactoryImpl(config.proxy_types), config_writer, artifact_repo)

    # Application orchestrator
    job_orchestrator = JobOrchestrator(job_repo, build_service, server_setup, test_service)

    return {
        "job_orchestrator": job_orchestrator,
        "job_repo": job_repo,
        "build_service": build_service,
        "test_service": test_service,
        "server_setup": server_setup,
    }
```

---

## Part 8: Test Strategy (DDD-Aligned)

### 8.1 Unit tests — test domain logic with injected mocks

```python
# test_build_service.py
def test_build_clones_repo_resolves_commit_and_builds():
    mock_git = Mock(spec=GitRepository)
    mock_git.clone.return_value = Path("/tmp/repo")
    mock_git.resolve.return_value = CommitHash("abc123")

    mock_cargo = Mock(spec=CargoBuildAdapter)
    mock_cargo.build.return_value = Path("/tmp/repo/target/release/pico_limbo")

    mock_storage = Mock(spec=ArtifactStorage)
    mock_storage.store.return_value = Path("/app/builds/abc123/pico_limbo")

    service = BuildService(mock_git, mock_cargo, mock_storage, Path("/app/builds"))

    job = Job(job_id="j1", repo_url="https://github.com/Quozul/PicoLimbo.git",
              ref="main", versions=["1.20"], proxy_type=ProxyType.VELOCITY)
    result = service.build(job)

    mock_git.clone.assert_called_once_with("Quozul", "PicoLimbo")
    mock_git.update.assert_called_once_with(Path("/tmp/repo"), "main")
    mock_git.resolve.assert_called_once_with(Path("/tmp/repo"), "main")
    mock_cargo.build.assert_called_once_with(Path("/tmp/repo"))
    assert result.commit_hash == CommitHash("abc123")
    assert result.artifact_path == Path("/app/builds/abc123/pico_limbo")
```

**No subprocess mocking. No `@patch`. No `_make_path_mock()`.** Just inject mocks and verify the domain logic.

### 8.2 Integration tests — test ACL adapters with real external services

```python
# test_git_repository.py
def test_clone_clones_repo(tmp_path):
    git = GitRepository(repos_dir=tmp_path)
    path = git.clone("Quozul", "PicoLimbo")
    assert (path / ".git").exists()

def test_update_fetches_and_checkouts(tmp_path):
    git = GitRepository(repos_dir=tmp_path)
    git.clone("Quozul", "PicoLimbo")
    git.update(tmp_path / "PicoLimbo", "main")
    result = subprocess.run(["git", "rev-parse", "HEAD"],
                            cwd=str(tmp_path / "PicoLimbo"),
                            capture_output=True, text=True)
    assert result.returncode == 0
```

**Real git operations on a temp directory.** No mocking needed.

### 8.3 What to stop testing

- **Mock call counts** — "database.update_job called exactly 6 times"
- **Argument order verification** — "build_project called with positional args"
- **Path construction via fake `Path` objects** — `_make_path_mock()`
- **No-op tests** — `test_passes_correct_bbox_to_grab` ends with `pass`
- **Tests that patch the wrong target** — `test_stop_forces_kill_on_timeout`
- **Tests that verify hardcoded constants** — "timeout=1800" in mock assertions
- **Global `sys.modules` mutation** — module-level `_patch_modules()`

### 8.4 What to keep/start testing

- **Domain invariants** — Job cannot be in "testing" without an artifact
- **State machine transitions** — queued → building → testing → finished
- **ACL adapters with real services** — git clone, PaperMC API
  - **NOT cargo build**: `CargoBuildAdapter` is a local build step, not an external service. Tests must use `subprocess.run` mocking to verify command construction. Do NOT write integration tests that compile Rust code.
- **Pure value objects** — CommitHash validation, Version comparison, JobStatus transitions
- **Error paths** — network failure, build failure, timeout

### 8.5 Test file cleanup targets

| Test File | Current Size | Target | Actions |
|-----------|-------------|--------|---------|
| `test_job_runner_idempotency.py` | 36.7KB | ~10KB | Remove `_make_path_mock()`, remove mock-call-count tests |
| `test_engine.py` | 22KB | ~5KB | Replace with `test_build_service.py` (domain tests with injected mocks — no real cargo build) |
| `test_wait_for.py` | 23KB | ~5KB | Replace with `test_screen_region.py` (ACL integration tests) |
| `test_proxy.py` | 23KB | ~8KB | Fix `stop` timeout test, move job_runner tests out, add `test_artifact_repository.py` |
| `test_minecraft_runner.py` | 8KB | ~8KB | Replace with `test_minecraft_launcher.py` (ACL) + `test_test_service.py` (domain) |
| `test_minecraft_env.py` | 10KB | ~5KB | Write real NBT file and read it back, remove `mock_nbt` fixture |
| `test_versions.py` | 12KB | ~4KB | Remove unnecessary `@patch(ALL_VERSIONS)`, consolidate tests |
| `test_api.py` | 17KB | ~12KB | Replace `sys.modules` patching with fixture-based DI, add plugin/frontend tests |
| `test_plugin_api.py` | 15KB | ~5KB | Remove global `sys.modules` mutation, move engine tests out, remove `_ConnHolder` |

---

## Part 9: Migration Steps

Each step should be independently deployable and tested. No all-or-nothing rewrite.

### Step 0: Fix critical bugs (1–2 hours)

- [ ] Fix `COMMIT_HASH_RE` to accept uppercase hex: `r"^[0-9a-fA-F]{40}$"` in `engine.py`
- [ ] Add test for uppercase hex commit hashes in `test_engine.py`
- [ ] Fix `test_stop_forces_kill_on_timeout` — patch `proc.wait` (instance), not `subprocess.Popen.wait` (class)
- [ ] Remove no-op test `test_passes_correct_bbox_to_grab` in `test_wait_for.py`
- [ ] Remove dead import `from ..versions import Version` in `runner.py`
- [ ] Remove dead import `from src.models import ...` in `job_runner.py`
- [ ] Remove dead `import json` in `engine.py:create_job()`
- [ ] Remove unreachable `remaining = proc.stdout.read()` from `wait_for_ready()`

### Step 1: Create `config.py` — consolidate all magic constants (30 min)

- [ ] Create `src/config.py` with all paths, timeouts, hardcoded values
- [ ] Move `SECONDS_PER_VERSION`, `SERVER_ADDRESS`, `PICO_LIMBO_INTERNAL_PORT`, `GAME_DIRECTORY`, `SCREENSHOTS_DIR`, `REPOS_DIR`, `BUILDS_DIR`, `VELOCITY_API_BASE`, `PROXY_CACHE_DIR`, `_QUIT_REGION_NEWER`, `_QUIT_REGION_OLDER`, click coordinates
- [ ] Document each constant with rationale

### Step 2: Create `GitRepository` — the first ACL adapter (2 hours)

- [ ] Create `src/infrastructure/git_repository.py`
- [ ] Implement `clone()`, `update()`, `resolve()` methods
- [ ] Move `_run()` subprocess wrapper into `GitRepository`
- [ ] Inject `repos_dir` and `timeout` as constructor parameters
- [ ] Create `test_git_repository.py` with integration tests (real git on temp dir)
- [ ] Update `engine.py` to use `GitRepository` — remove `ensure_repo_cloned()`, `update_repo()`, `resolve_commit()`
- [ ] Update tests to inject `MockGitRepository`

### Step 3: Create `ArtifactRepository` — PaperMC API ACL (2 hours)

- [ ] Create `src/infrastructure/artifact_repository.py`
- [ ] Implement `get_latest_mc_version()`, `get_download_url()`, `download()`, `get_cached_or_download()`
- [ ] Inject `api_base`, `cache_dir`, `http_client` as constructor parameters
- [ ] Create `test_artifact_repository.py` with integration tests (real PaperMC API)
- [ ] Update `velocity.py` to use `ArtifactRepository` — remove `_get_latest_mc_version()`, `_get_velocity_download_url()`, `_download_file()`
- [ ] Remove hardcoded `VELOCITY_API_BASE` and `PROXY_CACHE_DIR` from `velocity.py`

### Step 4: Create `CargoBuildAdapter` (1 hour)

- [ ] Create `src/infrastructure/cargo_build.py`
- [ ] Implement `build()` method
- [ ] Inject `timeout`, `release` as constructor parameters
- [ ] Update `engine.py` to use `CargoBuildAdapter` — remove inline cargo subprocess call
- [ ] Create `test_cargo_build.py` with **unit tests only** — mock `subprocess.run` to verify command construction, timeout, and release flag. Do NOT write integration tests that compile Rust code.

### Step 5: Create `MinecraftLauncher` — minecraft_launcher_lib ACL (1–2 hours)

- [ ] Create `src/infrastructure/minecraft_launcher.py`
- [ ] Implement `get_command()` method
- [ ] Inject `game_directory`, `jvm_args`, `resolution` as constructor parameters
- [ ] Update `runner.py` to use `MinecraftLauncher` — remove direct `minecraft_launcher_lib` calls
- [ ] Remove hardcoded `GAME_DIRECTORY` from `runner.py`

### Step 6: Create `WindowManager` — xdotool ACL (1 hour)

- [ ] Create `src/infrastructure/window_manager.py`
- [ ] Implement `search_by_name()`, `search_by_class()`, `get_geometry()`, `move_to()`
- [ ] Move `parse_window_info()` here as a pure function (easily tested)
- [ ] Update `runner.py` to use `WindowManager` — remove scattered xdotool subprocess calls
- [ ] Create `test_window_manager.py` with integration tests

### Step 7: Create `ConfigWriter` — nbtlib and file I/O ACL (1–2 hours)

- [ ] Create `src/infrastructure/config_writer.py`
- [ ] Implement `write_servers_dat()`, `write_options_txt()`, `write_velocity_toml()`
- [ ] Extract parent-directory creation into a shared helper
- [ ] Replace hardcoded option strings with data-driven mapping
- [ ] Replace hand-rolled TOML serializer with `tomli-w`
- [ ] Update `env.py` and `velocity.py` to use `ConfigWriter`
- [ ] Create `test_config_writer.py` — write real NBT files and read them back

### Step 8: Extract `ScreenRegionMatcher` — PIL/pyscreenshot ACL (1 hour)

- [ ] Create `src/infrastructure/screen_region.py`
- [ ] Move `wait_for_screen_region()` here
- [ ] Extract directory validation, image loading, polling loop, comparison into separate methods
- [ ] Create `test_screen_region.py` with integration tests (real reference images)

### Step 9: Refactor `Version` — pure value object (1 hour)

- [ ] Replace `__new__` factory dispatch with `Version.from_string()` classmethod
- [ ] Replace sentinel `Version(…, 0)` objects with direct integer comparison
- [ ] Remove unnecessary `@patch(ALL_VERSIONS)` from tests
- [ ] Consolidate redundant tests into parameterized tests
- [ ] Add tests for `__eq__`, `__lt__`, `__le__`

### Step 10: Define `Job` aggregate and value objects (2–3 hours)

- [ ] Create `src/domain/job.py` with `Job` aggregate root and invariants
- [ ] Create `src/domain/value_objects.py` with all value objects
- [ ] Move `models.py` JobCreate/JobUpdate Pydantic models to `src/domain/` or keep as API boundary
- [ ] Create `test_job.py` with invariant tests

### Step 11: Extract `BuildService` — domain service (2 hours)

- [ ] Create `src/application/build_service.py`
- [ ] Use `GitRepository`, `CargoBuildAdapter`, `ArtifactStorage`
- [ ] Remove `create_job()` from `engine.py` (or reduce to thin wrapper)
- [ ] Create `test_build_service.py` with **unit tests** — inject mocked `GitRepository`, `CargoBuildAdapter`, and `ArtifactStorage`. Verify domain logic (call order, return values). Do NOT write integration tests that clone repos and compile Rust code.

### Step 12: Extract `TestService` — domain service (2–3 hours)

- [ ] Create `src/application/test_service.py`
- [ ] Use `MinecraftLauncher`, `WindowManager`, `ScreenRegionMatcher`
- [ ] Split `test_single_version()` into smaller methods
- [ ] Replace hardcoded click coordinates with semantic constants
- [ ] Remove dead `window_id` parameter from `capture_screenshot()`
- [ ] Create `test_test_service.py`

### Step 13: Extract `ServerSetupService` — domain service (2 hours)

- [ ] Create `src/application/server_setup_service.py`
- [ ] Use `ProxyFactory`, `ConfigWriter`, `ArtifactRepository`
- [ ] Move `_server_step` logic here
- [ ] Create `test_server_setup_service.py`

### Step 14: Thin `job_runner.py` to `JobOrchestrator` (1 hour)

- [ ] `JobOrchestrator` becomes ~50 lines: fetch job, call services in sequence, handle errors, update final status
- [ ] Replace the 3 re-fetches of the job with return values from services
- [ ] Process cleanup moves into a context manager or `ServerContext`
- [ ] Remove duplicate response-building logic

### Step 15: Refactor `database.py` — JobRepository (2 hours)

- [ ] Extract `_ensure_db()` migration logic into a separate `migrate()` function called once at startup
- [ ] Remove `_row_to_dict()` fallback paths (or add tests)
- [ ] Add schema validation to `update_job()` — define allowed column names
- [ ] Fix `create_job()` double DB call — return inserted data directly
- [ ] Move `DB_PATH` to constructor parameter
- [ ] Add tests for JSON parsing edge cases
- [ ] Remove timing-dependent test (`time.sleep`)

### Step 16: Refactor `velocity.py` — SRP + security (2 hours)

- [ ] Split `start()` into smaller methods
- [ ] Remove dual `plugin`/`plugins` parameters — keep only `plugins: list[str]`
- [ ] Replace hardcoded `_FORWARDING_SECRET` with constructor argument or environment variable
- [ ] Fix `wait_for_ready()` — replace `time.sleep(0.1)` with `asyncio.sleep(0.1)` or `select.select()`

### Step 17: Refactor `main.py` — remove side effects (1–2 hours)

- [ ] Move `worker.start_queue_worker()` to `@app.on_event("startup")` handler
- [ ] Replace `get_screenshot()` file read with `FileResponse` streaming
- [ ] Replace module-level `sys.modules` patching in tests with fixture-based DI
- [ ] Move `PLUGINS_DIR` and `WEBUI_DIR` to `Config`

### Step 18: Create `di.py` — dependency injection wiring (1 hour)

- [ ] Wire all dependencies in one place
- [ ] Replace all module-level imports with injected dependencies
- [ ] Create `conftest.py` with DI fixtures for tests

### Step 19: Clean up test infrastructure (2–3 hours)

- [ ] Remove all module-level `_patch_modules()` / `_unpatch_modules()` functions
- [ ] Remove all `_make_path_mock()` helpers
- [ ] Remove all `call_count` closure patterns
- [ ] Move engine tests from `test_plugin_api.py` to `test_build_service.py`
- [ ] Move database tests from `test_plugin_api.py` to `test_database.py`
- [ ] Move `TestJobRunnerProxyIntegration` from `test_proxy.py` to `test_server_setup_service.py`
- [ ] Add tests for plugin upload/list/delete endpoints
- [ ] Add tests for frontend catch-all route

### Step 20: Remove dead code and unused imports (30 min)

- [ ] Remove unused `models` import from `job_runner.py`
- [ ] Remove unused `ALL_VERSIONS` dynamic import from `run_job()`
- [ ] Remove unused `Version` import from `runner.py`
- [ ] Remove unused `window_id` parameter from `capture_screenshot()`
- [ ] Remove dead `import json` from `engine.py`
- [ ] Consolidate duplicate `import shutil` in `_copy_plugins()`

---

## Appendix: Before/After Comparison — Git Operations

### Before: `engine.py` — git commands scattered in business logic

```python
# engine.py — 100+ lines of git + build logic mixed together
REPOS_DIR = Path("/app/repos")  # Hardcoded global

def _run(cmd, cwd):
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=1800)
    ...

def ensure_repo_cloned(owner, repo_name):
    repo_path = REPOS_DIR / owner / repo_name
    if repo_path.exists() and (repo_path / ".git").exists():
        return repo_path
    _run(["git", "clone", "--depth", "1", f"https://github.com/{owner}/{repo_name}.git", str(repo_path)])
    return repo_path

def resolve_commit(repo_path, ref):
    if is_commit_hash(ref):
        _run(["git", "checkout", ref], cwd=repo_path)
        return ref
    _run(["git", "fetch", "--depth=1", "origin", ref], cwd=repo_path)
    _run(["git", "checkout", "FETCH_HEAD"], cwd=repo_path)
    output = _run(["git", "rev-parse", "HEAD"], cwd=repo_path)
    return output

def build_project(repo_path, commit_hash, owner, ref):
    artifact_dir = BUILDS_DIR / owner / ref / commit_hash  # Hardcoded global
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "pico_limbo"
    if artifact_path.exists():
        return str(artifact_path)
    _run(["cargo", "build", "--release"], cwd=repo_path)  # Hardcoded command
    ...

def create_job(repo_url, ref, ...):  # 9 parameters
    owner, repo_name = extract_owner_from_url(repo_url)
    repo_path = ensure_repo_cloned(owner, repo_name)
    commit_hash = resolve_commit(repo_path, ref)
    job = database.create_job(repo_url, ref, owner, commit_hash, ...)
    return job
```

**Problems**: 5 responsibilities, hardcoded globals, subprocess calls everywhere, tests must mock `subprocess.run` globally.

### After: `BuildService` — clean domain service with injected ACL

```python
# application/build_service.py
class BuildService:
    def __init__(self, git_repo: GitRepository, cargo: CargoBuildAdapter,
                 artifact_storage: ArtifactStorage, builds_dir: Path):
        self._git = git_repo
        self._cargo = cargo
        self._storage = artifact_storage
        self._builds_dir = builds_dir

    def build(self, job: Job) -> BuildResult:
        owner, repo_name = RepoUrl(job.repo_url).parse()
        repo_path = self._git.clone(owner, repo_name)
        self._git.update(repo_path, job.ref)
        commit_hash = self._git.resolve(repo_path, job.ref)
        source = self._cargo.build(repo_path)
        artifact_path = self._storage.store(source, job, commit_hash)
        return BuildResult(commit_hash=commit_hash, artifact_path=artifact_path)
```

**Benefits**: 15 lines, clear intent, injectable dependencies, testable with mocks, no subprocess calls visible.

### Before: Test — mock subprocess globally

```python
# test_engine.py — current state
@patch("subprocess.run")
@patch.object(Path, "exists")
@patch.object(Path, "mkdir")
@patch("shutil.copy2")
class TestBuildProject:
    def test_builds_and_copies_when_artifact_missing(self, mock_copy, mock_mkdir, mock_exists, mock_run):
        mock_exists.return_value = False
        # 4 patches to test one function
        result = engine.build_project(mock_repo_path, "abc123", "owner", "main")
        mock_run.assert_any_call(["cargo", "build", "--release"], cwd=str(mock_repo_path))
```

### After: Test — inject mocks, verify domain logic

```python
# test_build_service.py
def test_builds_and_stores_artifact():
    mock_git = Mock(spec=GitRepository)
    mock_git.clone.return_value = Path("/tmp/repo")
    mock_git.resolve.return_value = CommitHash("abc123")

    mock_cargo = Mock(spec=CargoBuildAdapter)
    mock_cargo.build.return_value = Path("/tmp/repo/target/release/pico_limbo")

    mock_storage = Mock(spec=ArtifactStorage)
    mock_storage.store.return_value = Path("/app/builds/abc123/pico_limbo")

    service = BuildService(mock_git, mock_cargo, mock_storage, Path("/app/builds"))
    result = service.build(Job(...))

    mock_git.clone.assert_called_once_with("owner", "repo")
    mock_cargo.build.assert_called_once_with(Path("/tmp/repo"))
    mock_storage.store.assert_called_once()
    assert result.artifact_path == Path("/app/builds/abc123/pico_limbo")
```

**No subprocess mocking. No `@patch`. Clear intent. 15 lines.**
