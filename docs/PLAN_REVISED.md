# Refactoring Plan: Reducing Coupling Across the Codebase

> This plan covers all Python modules in the project. See the original `docs/PLAN.md` for the initial `job_runner.py`-focused analysis. This revision incorporates findings from all 10 feature/test pairs.

---

## 1. Current Problems

### 1.1 `src/orchestration/job_runner.py` — the central coupling hub

`job_runner.py` (290 lines) directly imports and calls 6+ external modules. `update_job` is called 8+ times with different field combinations; `get_job_by_id` is called 4 times. The function re-fetches the job from the database three times (lines 229, 240, 249) because state is mutated via side effects rather than returned values.

| Function | Lines | Responsibilities |
|----------|-------|-----------------|
| `run_job` | 228–290 (73 lines) | Fetch job, determine versions, orchestrate build, orchestrate server, orchestrate test, update status, handle errors/cleanup, track process lifecycle |
| `_server_step` | 127–179 (55 lines) | Validate artifact, extract config, start proxy, wait for proxy, write servers.dat, write server.toml, start PicoLimbo subprocess, poll stdout, handle startup failure |
| `_test_step` | 191–224 (42 lines) | Create VirtualInputController, manage try/finally, loop over versions with cancellation, update DB per version, call test_single_version, accumulate/persist results, kill servers |

**Implicit cross-step communication**: `_build_step` sets `artifact_path` via the database, but `run_job` must re-fetch the job (line 240) to see it. Control flow is split across functions communicating via a shared mutable dict + database, not return values.

### 1.2 `src/proxy/velocity.py` — SRP violations and security risk

| Function | Lines | Responsibilities |
|----------|-------|-----------------|
| `start()` | 103–138 (36 lines) | Generate/write velocity.toml config, write forwarding.secret, copy plugins, download jar, start Java subprocess |
| `_generate_config()` | 204–223 (20 lines) | Hand-rolled TOML serializer via f-strings — incomplete (no `int`, `datetime`, or inline table support); if a future config key is an integer, it produces TOML-unparseable output |
| `_copy_plugins()` | 139–165 (27 lines) | Dual `plugin`/`plugins` parameters with no deduplication or validation — passing both copies the plugin twice |
| `wait_for_ready()` | 152–187 (36 lines) | Busy-polling with `time.sleep(0.1)`, reads stdout one line at a time, `remaining = proc.stdout.read()` at line 168 is unreachable |
| `download_if_needed()` | 45–90 (46 lines) | Three nested branches for `latest_mc_version`, assign-then-check-again pattern makes data flow hard to trace |

**Security**: `_FORWARDING_SECRET = "sup3r-s3cr3t"` (line 131) is a hardcoded class-level secret used by every deployment.

### 1.3 `src/database.py` — schema migrations baked into data access

| Function | Lines | Problems |
|----------|-------|----------|
| `_ensure_db()` | 18–74 | Directory creation + schema creation + 5 blind `ALTER TABLE` migration attempts — every DB operation pays this cost |
| `_row_to_dict()` | 195–235 | 4 `try/except KeyError` fallback paths for migrated columns — zero test coverage, makes the "current" job dict shape impossible to determine |
| `create_job()` | 88–126 | 10 parameters, legacy `plugin`/`plugins` conversion, JSON-serializes versions, then calls `get_job_by_id()` — a second DB round-trip to return what was just inserted |
| `get_connection()` | 77–85 | Implicit side effects: calls `_ensure_db()`, enables WAL mode — a caller expecting "a connection" gets schema migrations as hidden side effects |
| `update_job()` | 143–156 | **SQL injection vulnerability** — column names from `**fields` dict keys with zero validation |

**Global mutable state**: `DB_PATH = Path("/app/builds/jobs.db")` (line 9) — tests patch it via three separate mocks just to get a testable in-memory DB.

### 1.4 `src/builder/engine.py` — module-level globals and misleading contracts

| Function | Lines | Problems |
|----------|-------|----------|
| `create_job()` | 128–158 (31 lines) | 5 responsibilities (extract owner, clone repo, resolve commit, create DB record, return job), 9 parameters, misleading docstring, dead `import json` |
| `resolve_commit()` | 95–113 (19 lines) | Name implies read-only lookup but also checks out the ref — side effect hidden in the name |
| `build_project()` | 111–132 (22 lines) | 5 responsibilities (create dir, check artifact, run cargo, verify artifact, copy), wrong error message on line 126 ("Cargo build may have failed silently" — but `_run` would have raised `RuntimeError`) |

**Bug**: `COMMIT_HASH_RE = r"^[0-9a-f]{40}$"` (line 28) rejects valid uppercase hex hashes — git commit hashes are case-insensitive. No test catches this.

**Module-level globals**: `REPOS_DIR = Path("/app/repos")` and `BUILDS_DIR = Path("/app/builds")` (lines 17–18) — no way to inject or override, tests must patch module attributes.

### 1.5 `src/minecraft/runner.py` — untested core logic

| Function | Lines | Problems |
|----------|-------|----------|
| `test_single_version()` | 177–220 (44 lines) | 6 responsibilities (start MC, wait for game, log in, wait 30s, screenshot, handle subprocess lifecycle), 3 levels of nesting, **zero tests** |
| `wait_for_game()` | 89–127 (39 lines) | Combines window discovery, window positioning (LWJGL 2), and main menu detection — no tests |
| `log_to_multiplayer()` | 130–152 (23 lines) | Embeds hardcoded click coordinates (`507, 438`, `507, 264/146`, `201, 630`) with no semantic meaning — no tests |
| `start_minecraft()` | 154–173 (20 lines) | Hardcoded JVM args (`-Xmx2G`, `-Xms2G`), hardcoded resolution (`1024x768`), no tests |

**Dead code**: `from ..versions import Version` (line 23) — imported but never used. `window_id: str` parameter in `capture_screenshot` (line 169) — accepted but completely ignored.

**7 of 10 public functions are entirely untested.**

### 1.6 `src/minecraft/wait_for.py` — God function with heavy mock plumbing

`wait_for_screen_region()` (lines 18–90, 73 lines) does 5 things:
1. Directory validation
2. Reference image discovery, loading, size filtering, error handling
3. Screen capture polling loop with timeout
4. Image comparison via `ImageChops.difference`
5. Debug image saving on timeout

The function has 3 levels of nesting. `last_capture` (line 62) is a deferred-use variable — assigned inside the loop but only used in the error path after the loop exits, making its `None` vs not-`None` state non-obvious.

### 1.7 `src/minecraft/env.py` — no abstraction layer for nbtlib

| Function | Lines | Problems |
|----------|-------|----------|
| `create_options_txt()` | 20–42 (23 lines) | Mixes business logic (which options to include) with filesystem I/O (directory creation, file writing) |
| `create_servers_dat()` | 45–75 (31 lines) | Uses concrete `nbtlib.File`, `nbtlib.List`, `nbtlib.Compound` types directly — zero abstraction, tests cannot verify output without module-level mocking |

**Duplicated code**: Parent-directory creation is copied verbatim in both functions (lines 38–39 and 67–68).

**Magic strings**: Option keys and values (`"skipMultiplayerWarning:true"`, `"tutorialStep:none"`, `"joinedFirstServer:true"`) are hardcoded inline with no data-driven mapping.

### 1.8 `src/versions.py` — unconventional `__new__` factory with 55% unnecessary mocking

`Version.__new__` (lines 2–58) has 4 responsibilities: string parsing, protocol version lookup via linear scan of 66-entry `ALL_VERSIONS`, type validation, and instance construction. Using `__new__` for factory dispatch is unconventional and requires reading the entire method to understand the dual-path dispatch (string vs. integer form).

**Covert coupling**: `supports_option()` and `is_lwjgl2()` create sentinel `Version(…, 0)` objects where `0` is not a real protocol version. This hidden contract is not documented.

**Import-time side effects**: Importing the module does 66 object constructions.

### 1.9 `src/main.py` — module-level side effects and duplicated response logic

| Problem | Location |
|---------|----------|
| `get_job()` and `list_jobs()` duplicate the same response-building block (ETA computation, TestResult construction, dict conversion) — DRY violation | Lines 71–93 and 127–156 |
| `_compute_eta()` is called as a private method from the API layer — couples API to internal implementation | Lines 82 and 139 |
| `worker.start_queue_worker()` runs at module import time (line 40) — `import src.main` triggers a side effect | Line 40 |
| `/{full_path:path}` catch-all route with `if full_path.startswith("api/")` workaround (line 191) — fragile, easy to break | Lines 188–200 |
| Module-level globals: `PLUGINS_DIR`, `WEBUI_DIR` | Lines 158, 184 |
| `get_screenshot()` reads entire file into memory instead of using `FileResponse` streaming | Line 123 |

### 1.10 Test file coupling patterns

| Test File | Problems |
|-----------|----------|
| `test_job_runner_idempotency.py` (36.7KB) | 60% test mock call patterns. `_make_path_mock()` engineers fake `Path` objects to test path construction mechanics. Tests "database.update_job called exactly 6 times" — coupling to call count. |
| `test_proxy.py` | `test_stop_forces_kill_on_timeout` patches the wrong target (class method instead of instance) — **false positive**. `TestJobRunnerProxyIntegration` tests job_runner's control flow, not velocity's behavior. Unnecessary `patch("pathlib.Path.mkdir")`. |
| `test_engine.py` | `_make_path_mock()` helper (same anti-pattern). `TestCreateJob` verifies exact positional argument order of `database.create_job`. `Path.exists` patched globally (line 245). No test for uppercase hex commit hashes. |
| `test_wait_for.py` | One test (`test_passes_correct_bbox_to_grab`) is a **no-op** — it sets up mocks and ends with `pass`. Heavy mock plumbing: 5–6 `patch` calls per test. `call_count` closure anti-pattern used in multiple tests. |
| `test_minecraft_runner.py` | Every `TestCaptureScreenshot` test mocks `get_window_info` which is never called — dead setup. Tests verify mock call patterns, not file output. |
| `test_minecraft_env.py` | `mock_nbt` fixture patches all nbtlib symbols at module level — no test writes an actual NBT file and reads it back. Complex `_NbtListCallable` and `MockNbtList` classes engineered just to make dict construction pass through. |
| `test_versions.py` | 16 of 28+ tests use `@patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)` unnecessarily — `supports_option` and `is_lwjgl2` use the integer form internally, bypassing `ALL_VERSIONS` entirely. |
| `test_api.py` | Module-level `sys.modules` mutation at import time (line 52). `_make_job` helper couples to internal DB dict format. `patch("pathlib.Path", ...)` replaces Path globally. Zero tests for plugin or frontend endpoints. |
| `test_plugin_api.py` | Global `sys.modules` mutation at import time. Patching loop in `client` fixture. Engine tests assert positional argument order and index `call_args[0]` at hardcoded indices. Database tests mixed into API test file. `_setup_inmemory_db()` is a mini test framework with nested class, 3 patchers, and manual schema. |

---

## 2. Proposed Structure

### 2.1 Module-level SRP splits

```
src/
├── orchestration/
│   ├── job_runner.py          # Thin orchestrator: state machine transitions, error handling, process lifecycle (~50 lines)
│   ├── build_orchestrator.py  # Build pipeline: clone → update → resolve → build
│   ├── server_orchestrator.py # Server lifecycle: config generation, proxy management, subprocess startup
│   └── test_orchestrator.py   # Test execution: version iteration, result accumulation, persistence
├── proxy/
│   ├── base.py                # ProxyManager protocol / base class
│   ├── velocity.py            # VelocityProxyManager — keep, but split start() into smaller methods
│   └── manager.py             # get_proxy_manager() → ProxyFactoryImpl (new)
├── builder/
│   ├── engine.py              # BuildEngine protocol + implementation
│   └── worker.py              # Queue worker — move startup to FastAPI startup event
├── database.py                # JobRepository protocol + SQLite implementation
├── minecraft/
│   ├── runner.py              # MinecraftTestRunner protocol + implementation
│   ├── env.py                 # ConfigWriter protocol + implementation (options, servers.dat)
│   ├── wait_for.py            # ScreenRegionMatcher protocol + implementation
│   └── input.py               # VirtualInputController — keep as-is (thin wrapper)
├── versions.py                # Version — refactor __new__ to classmethod
└── main.py                    # API layer — thin, no business logic
```

### 2.2 Protocol interfaces to introduce

| Protocol | Provides abstraction for |
|----------|------------------------|
| `JobRepository` | `database` — `get(id)`, `update(id, **fields)`, `create(**fields)`, `list(status?)`, `update_results(id, results)` |
| `BuildEngine` | `engine` — `build(job) -> BuildResult` |
| `BuildResult` | Dataclass: `artifact_path: Path | None`, `commit_hash: str` |
| `ServerContext` | Dataclass: `proxy: ProxyManager`, `pico_limbo_proc: subprocess.Popen`, `cleanup()` |
| `ProxyFactory` | `get_proxy_manager()` — `create(proxy_type) -> ProxyManager` |
| `TestRunner` | `test_single_version()` — `run(version) -> TestResult` |
| `ConfigWriter` | `create_servers_dat()`, `create_options_txt()` — `write_servers(job)`, `write_options(job)` |
| `ScreenRegionMatcher` | `wait_for_screen_region()` — `wait(reference_dir, target_region, timeout) -> bool` |

### 2.3 Dependency Inversion at the entry point

All concrete implementations wired in `main.py` (or a dedicated `di.py`):

```python
# Wiring example
database = SQLiteJobRepository()
engine = BuildEngineImpl()
test_runner = MinecraftTestRunner()
config_writer = ServerConfigWriter()
proxy_factory = ProxyFactoryImpl({"velocity": VelocityProxyManager})

build_orchestrator = BuildOrchestrator(engine)
server_orchestrator = ServerOrchestrator(proxy_factory, config_writer, test_runner)
test_orchestrator = TestOrchestrator(test_runner, database)

job_runner = JobRunner(database, build_orchestrator, server_orchestrator, test_orchestrator)
```

---

## 3. Dependency Injection

### 3.1 Before: Direct imports, hard to test, hard to swap

```python
# velocity.py — current state
class VelocityProxyManager:
    _FORWARDING_SECRET = "sup3r-s3cr3t"  # Hardcoded secret

    def start(self):
        self._write_config()          # writes velocity.toml
        self._write_secret()          # writes forwarding.secret
        self._copy_plugins()          # copies jar files
        self._download_jar()          # downloads from API
        self._start_subprocess()      # launches Java
```

**Problems**: 5 responsibilities in `start()`, hardcoded secret, no way to test plugin copying in isolation, no way to swap the config format without editing the class.

### 3.2 Before: Module-level mocking in tests

```python
# test_job_runner_idempotency.py — current state
class TestBuildStepArtifactExists:
    def test_no_build_when_artifact_exists(self):
        with patch("src.engine.ensure_repo_cloned"), \
             patch("src.engine.update_repo"), \
             patch("src.engine.resolve_commit"), \
             patch("src.database.update_job"), \
             patch("src.database.get_job_by_id"):
            # 5 patches to test one function
```

**Problems**: 5 module-level patches to test one function. Tests verify call graph, not behavior. `_make_path_mock()` creates fake `Path` objects — testing Path construction mechanics.

### 3.3 After: Constructor injection with protocols

```python
# server_orchestrator.py — refactored
class ServerOrchestrator:
    def __init__(
        self,
        proxy_factory: ProxyFactory,
        config_writer: ConfigWriter,
        test_runner: TestRunner,
    ):
        self.proxy_factory = proxy_factory
        self.config_writer = config_writer
        self.test_runner = test_runner

    def start_servers(self, job: Job) -> ServerContext:
        proxy = self.proxy_factory.create(job.proxy_type)
        proxy.start()
        proxy.wait_for_ready()
        self.config_writer.write_servers_dat(job)
        self.config_writer.write_options(job)
        ctx = self._start_pico_limbo(job, proxy)
        return ServerContext(proxy, ctx.subprocess, ctx.cleanup)
```

**Benefits**:
- Tests inject `MockProxyFactory`, `MockConfigWriter`, `MockTestRunner` — no module-level patching needed
- Swapping the proxy is a wiring change at the entry point, not in business logic
- Each class has 2–3 clearly named dependencies visible in the constructor

### 3.4 Before: Global state coupling in tests

```python
# test_plugin_api.py — current state (module level)
mock_database = MagicMock()
mock_engine = MagicMock()
mock_job_runner = MagicMock()
sys_modules_backup = {}

def _patch_modules():
    global sys_modules_backup
    sys_modules_backup = {
        "src.database": sys.modules.get("src.database"),
        "src.builder.engine": sys.modules.get("src.builder.engine"),
        ...
    }
    sys.modules["src.database"] = mock_database
    ...

_patch_modules()  # Runs on import — side effect before any test code
from src.main import app
```

**Problems**: Test file cannot be imported in isolation. Global mutable state shared across all tests. Patching loop in `client` fixture.

### 3.5 After: Per-test dependency injection

```python
# test_server_orchestrator.py — refactored
@pytest.fixture
def server_orchestrator(mock_proxy_factory, mock_config_writer, mock_test_runner):
    return ServerOrchestrator(mock_proxy_factory, mock_config_writer, mock_test_runner)

def test_starts_proxy_and_writes_config(server_orchestrator, sample_job):
    result = server_orchestrator.start_servers(sample_job)
    assert result.proxy is mock_proxy_factory.create.return_value
    mock_config_writer.write_servers_dat.assert_called_once_with(sample_job)
```

No module-level patches. No `sys.modules` manipulation. Each test is isolated.

---

## 4. Test Strategy

### 4.1 After the refactor, tests should look like this

**Unit tests** — each orchestrator tested in isolation with injected mocks:

```python
def test_all_versions_are_tested(mock_test_runner):
    orchestrator = TestOrchestrator(test_runner=mock_test_runner, repository=mock_repo)
    mock_repo.get.return_value = Job(id="j1", versions=["1.20", "1.19", "1.18"], status="testing")
    results = orchestrator.run_tests(Job(id="j1", versions=["1.20", "1.19", "1.18"], status="testing"))
    assert mock_test_runner.run.call_count == 3
    assert results["1.20"]["passed"] is True
```

No module-level `@patch`. No `_make_path_mock()`. No verifying `database.update_job` call counts.

**Integration tests** — test real behavior with minimal mocks:

- Test that the orchestrator correctly accumulates test results across versions (real data flow)
- Test that status transitions follow the expected state machine
- Test ETA computation (pure function, already well-tested)
- Test `Version._cmp` (pure function, already well-tested)
- Test `_is_lwjgl2_version` and `parse_window_info` (pure functions, already well-tested)

### 4.2 What to stop testing

- **Mock call counts** — "database.update_job called exactly 6 times" is an implementation detail
- **Argument order verification** — "build_project called with positional args (a, b, c)" couples tests to function signatures
- **Path construction via fake `Path` objects** — `_make_path_mock()` tests Path mechanics, not behavior
- **No-op tests** — `test_passes_correct_bbox_to_grab` in `test_wait_for.py` ends with `pass`
- **Tests that patch the wrong target** — `test_stop_forces_kill_on_timeout` patches `subprocess.Popen.wait` (class) instead of `proc.wait` (instance)
- **Tests that verify hardcoded constants** — "timeout=1800" in mock assertions

### 4.3 What to keep/start testing

- **Status transitions** — "building → testing → finished"
- **Version iteration** — all versions are tested
- **Result propagation** — results flow into the result dict
- **ETA computation** — pure function
- **Version comparison** — `_cmp`, `__str__`, `__repr__`, `is_lwjgl2`
- **Error handling** — build fails, server fails to start, test raises
- **Real file I/O** — `create_options_txt` writes correct content (already tested), `create_servers_dat` should write a real NBT file and read it back

### 4.4 Test file cleanup targets

| Test File | Current Size | Target | Actions |
|-----------|-------------|--------|---------|
| `test_job_runner_idempotency.py` | 36.7KB | ~10KB | Remove `_make_path_mock()`, remove mock-call-count tests, keep status transitions |
| `test_engine.py` | 22KB | ~8KB | Remove `_make_path_mock()`, remove positional arg tests, add uppercase hex test |
| `test_wait_for.py` | 23KB | ~8KB | Remove no-op test, replace `call_count` closures with real-time fixtures, test real file I/O |
| `test_proxy.py` | 23KB | ~10KB | Fix `stop` timeout test target, move job_runner tests out, remove unnecessary `Path.mkdir` patches |
| `test_minecraft_env.py` | 10KB | ~6KB | Write real NBT file and read it back, remove `mock_nbt` fixture, consolidate duplicate tests |
| `test_versions.py` | 12KB | ~6KB | Remove unnecessary `@patch(ALL_VERSIONS)`, consolidate redundant tests, add `__eq__`/`__lt__` tests |
| `test_minecraft_runner.py` | 8KB | ~10KB | Add tests for `test_single_version`, `wait_for_game`, `log_to_multiplayer` |
| `test_api.py` | 17KB | ~15KB | Replace `sys.modules` patching with fixture-based DI, add plugin/frontend endpoint tests |
| `test_plugin_api.py` | 15KB | ~8KB | Remove global `sys.modules` mutation, move engine tests to `test_engine.py`, remove `_ConnHolder` |

---

## 5. Migration Steps

Each step should be independently deployable and tested. No all-or-nothing rewrite.

### Step 1: Fix critical bugs (1–2 hours)

- [ ] Fix `COMMIT_HASH_RE` to accept uppercase hex: `r"^[0-9a-fA-F]{40}$"` in `engine.py`
- [ ] Add test for uppercase hex commit hashes in `test_engine.py`
- [ ] Fix `test_stop_forces_kill_on_timeout` — patch `proc.wait` (instance), not `subprocess.Popen.wait` (class) in `test_proxy.py`
- [ ] Remove no-op test `test_passes_correct_bbox_to_grab` in `test_wait_for.py`
- [ ] Remove dead import `from ..versions import Version` in `runner.py`
- [ ] Remove dead import `from src.models import ...` in `job_runner.py`
- [ ] Remove dead `import json` in `engine.py:create_job()`

### Step 2: Extract `BuildOrchestrator` (2–3 hours)

- [ ] Create `src/orchestration/build_orchestrator.py`
- [ ] Move `_build_step` logic into `BuildOrchestrator.build(job) -> BuildResult`
- [ ] `BuildResult` is a dataclass: `artifact_path: Path | None`, `commit_hash: str`
- [ ] Inject `engine` as a `BuildEngine` protocol
- [ ] Update `run_job` to call `build_orchestrator.build(job)`
- [ ] Move and adapt `_build_step` tests; remove `_make_path_mock()` helper
- [ ] Remove `REPOS_DIR`/`BUILDS_DIR` module-level globals from `engine.py`; pass them as constructor args to `BuildEngineImpl`

### Step 3: Extract `ServerOrchestrator` (2–3 hours)

- [ ] Create `src/orchestration/server_orchestrator.py`
- [ ] Move `_server_step` logic into `ServerOrchestrator.start_servers(job) -> ServerContext`
- [ ] `ServerContext` holds `proxy`, `pico_limbo_proc`, and `cleanup()` method
- [ ] Inject `ProxyFactory` and `ConfigWriter` as protocols
- [ ] Update `run_job` to use the returned context
- [ ] Move and adapt `_server_step` tests
- [ ] Move `TestJobRunnerProxyIntegration` tests out of `test_proxy.py` (they test job_runner, not velocity)

### Step 4: Extract `TestOrchestrator` (1–2 hours)

- [ ] Create `src/orchestration/test_orchestrator.py`
- [ ] Move `_test_step` logic into `TestOrchestrator.run_tests(job) -> TestResults`
- [ ] Inject `TestRunner` and `JobRepository` as protocols
- [ ] Tests: eliminate mock-call-count tests (e.g., "database.update_job called exactly 6 times")

### Step 5: Thin `run_job` to a state machine (1 hour)

- [ ] `run_job` becomes ~50 lines: fetch job, call orchestrators in sequence, handle errors, update final status
- [ ] Replace the 3 re-fetches of the job with return values from orchestrators
- [ ] Process cleanup moves into a context manager or the orchestrators' `ServerContext`

### Step 6: Split `velocity.py` — apply SRP (2 hours)

- [ ] Split `start()` into: `_generate_config()`, `_write_secret()`, `_copy_plugins()`, `_download_jar()`, `_start_subprocess()`
- [ ] Replace hand-rolled TOML serializer with `tomli-w` library
- [ ] Remove dual `plugin`/`plugins` parameters — keep only `plugins: list[str]`
- [ ] Replace hardcoded `_FORWARDING_SECRET` with environment variable or constructor argument
- [ ] Fix `wait_for_ready()` — replace `time.sleep(0.1)` with `asyncio.sleep(0.1)` or `select.select()` for non-blocking behavior
- [ ] Simplify `download_if_needed()` — flatten the nested branches

### Step 7: Refactor `database.py` — separate migrations from access (2 hours)

- [ ] Extract `_ensure_db()` migration logic into a separate `migrate()` function called once at startup, not on every connection
- [ ] Remove `_row_to_dict()` fallback paths (or add tests for them)
- [ ] Add schema validation to `update_job()` — define allowed column names and reject unknown ones
- [ ] Fix `create_job()` double DB call — return the inserted data directly instead of re-querying
- [ ] Move `DB_PATH` to a constructor parameter or config object
- [ ] Add tests for JSON parsing edge cases in `get_tested_versions_for_commit()` and `get_latest_test_results_for_commit()`

### Step 8: Refactor `engine.py` — fix contract violations (1–2 hours)

- [ ] Rename `resolve_commit()` to `resolve_and_checkout_commit()` or split into two functions
- [ ] Fix error message in `build_project()` — don't say "may have failed silently" when `_run` already raised
- [ ] Move `REPOS_DIR`/`BUILDS_DIR` to constructor arguments
- [ ] Remove dead `import json` from `create_job()`

### Step 9: Refactor `minecraft/runner.py` — add tests, extract logic (2–3 hours)

- [ ] Split `test_single_version()` — extract subprocess lifecycle into a helper
- [ ] Split `wait_for_game()` — separate window discovery from window positioning
- [ ] Replace hardcoded click coordinates in `log_to_multiplayer()` with named constants or a mapping
- [ ] Add tests for `test_single_version()`, `wait_for_game()`, `log_to_multiplayer()`
- [ ] Remove dead `window_id` parameter from `capture_screenshot()`

### Step 10: Refactor `minecraft/wait_for.py` — reduce nesting (1–2 hours)

- [ ] Extract directory validation into a separate function
- [ ] Extract reference image loading into a separate function
- [ ] Extract image comparison into a separate function
- [ ] Replace `call_count` closure anti-pattern in tests with real-time fixtures (e.g., `freezegun`)
- [ ] Test real file I/O instead of heavy mock plumbing

### Step 11: Refactor `minecraft/env.py` — add nbtlib abstraction (1–2 hours)

- [ ] Create a `DataBuilder` protocol or use `nbtlib` types through a thin wrapper
- [ ] Extract parent-directory creation into a shared helper
- [ ] Replace hardcoded option strings with a data-driven mapping: `OPTION_MAP = {"skipMultiplayerWarning": "true", ...}`
- [ ] Replace `mock_nbt` fixture — write a real NBT file and read it back

### Step 12: Refactor `versions.py` — cleaner factory pattern (1 hour)

- [ ] Replace `__new__` factory dispatch with `Version.from_string()` classmethod and `Version(major, minor, patch, protocol_version)` constructor
- [ ] Replace sentinel `Version(…, 0)` objects in `supports_option()` and `is_lwjgl2()` with direct integer comparison
- [ ] Remove unnecessary `@patch(ALL_VERSIONS)` from 16+ tests
- [ ] Consolidate redundant tests into parameterized tests
- [ ] Add tests for `__eq__`, `__lt__`, `__le__`

### Step 13: Refactor `main.py` — remove side effects, deduplicate (1–2 hours)

- [ ] Move `worker.start_queue_worker()` to `@app.on_event("startup")` handler
- [ ] Extract `_build_job_response(job)` helper to eliminate DRY violation between `get_job()` and `list_jobs()`
- [ ] Replace `get_screenshot()` file read with `FileResponse` streaming
- [ ] Move `PLUGINS_DIR` and `WEBUI_DIR` to constructor arguments or config
- [ ] Replace module-level `sys.modules` patching in tests with fixture-based DI

### Step 14: Refactor test infrastructure (2–3 hours)

- [ ] Create a `conftest.py` with DI fixtures for all protocols (mock database, mock engine, mock test runner, etc.)
- [ ] Remove all module-level `_patch_modules()` / `_unpatch_modules()` functions
- [ ] Remove all `_make_path_mock()` helpers
- [ ] Remove all `call_count` closure patterns
- [ ] Move engine tests from `test_plugin_api.py` to `test_engine.py`
- [ ] Move database tests from `test_plugin_api.py` to `test_database.py`
- [ ] Add tests for plugin upload/list/delete endpoints in `test_api.py`
- [ ] Add tests for frontend catch-all route in `test_api.py`

### Step 15: Consolidate magic constants (1 hour)

- [ ] Create `src/config.py` or `src/constants.py` for:
  - `SECONDS_PER_VERSION = 90`
  - `SERVER_ADDRESS`, `PICO_LIMBO_INTERNAL_PORT = 30066`
  - `GAME_DIRECTORY`, `SCREENSHOTS_DIR`
  - `_QUIT_REGION_NEWER`, `_QUIT_REGION_OLDER` (with `(x, y, width, height)` documentation)
  - Click coordinates in `log_to_multiplayer()`
- [ ] Replace hardcoded paths with configuration

### Step 16: Remove dead code and unused imports (30 min)

- [ ] Remove unused `models` import from `job_runner.py`
- [ ] Remove unused `ALL_VERSIONS` dynamic import from `run_job()`
- [ ] Remove unused `Version` import from `runner.py`
- [ ] Remove unused `window_id` parameter from `capture_screenshot()`
- [ ] Remove dead `import json` from `engine.py`
- [ ] Remove unreachable `remaining = proc.stdout.read()` from `wait_for_ready()`
