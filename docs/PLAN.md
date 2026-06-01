# Refactoring Plan: Reducing Coupling in `job_runner.py`

## 1. Current Problems

### 1.1 `src/orchestration/job_runner.py` — the single most coupled file

`job_runner.py` (290 lines) is the central orchestrator and the highest-coupling file in the codebase. It directly imports and calls:

- **`database`** (line 13): `update_job` is called 8+ times across `run_job`, `_update_job`, `_build_step`, and `_test_step` with different field combinations. `get_job_by_id` is called 4 times. If `update_job`'s signature changes, every caller breaks. `run_job` re-fetches the job from the database three times (lines 229, 240, 249) because state is mutated via side effects rather than returned values.

- **`engine`** (line 15): `_build_step` (lines 78–103) directly calls `ensure_repo_cloned`, `update_repo`, `resolve_commit`, and `build_project`. It also reads `engine.BUILDS_DIR`. If `build_project`'s return type or error behavior changes, `_build_step` breaks. The function re-resolves the commit hash from `engine.resolve_commit` and overwrites `job["commit_hash"]` (line 90) — a silent coupling point.

- **`minecraft` modules** (lines 16–18): `_server_step` (line 127) directly calls `create_servers_dat`, `test_single_version`, `empty_directory`, and instantiates `VirtualInputController()`. `_test_step` (line 191) also creates `VirtualInputController()` (line 201) and calls `test_single_version` (line 207). No abstraction layer — if any of these change their parameter order or raise different exceptions, the server and test steps break.

- **`proxy` module** (lines 19–20): `_server_step` calls `get_proxy_manager(proxy_type)` (line 144) and directly invokes `.start()` and `.wait_for_ready()`. The `_VELOCITY_TO_PICOLIMBO_METHOD` mapping (lines 106–111) and `_DEFAULT_FORWARDING_SECRET` (line 114, referencing `VelocityProxyManager._FORWARDING_SECRET`) are hard-coded translations with no documentation.

- **`models`** (line 14): Imported but never used — dead import adding noise.

- **`versions`**: `ALL_VERSIONS` is imported dynamically inside `run_job` (line 325), surfacing coupling only at runtime.

### 1.2 Functions that do too much

| Function | Lines | Responsibilities |
|----------|-------|-----------------|
| `run_job` | 228–290 (73 lines) | Fetch job, determine versions, orchestrate build, orchestrate server, orchestrate test, update final status, handle errors/cleanup, track process lifecycle |
| `_server_step` | 127–179 (55 lines) | Validate artifact, extract config, start proxy, wait for proxy, write servers.dat, write server.toml, start PicoLimbo subprocess, poll stdout for "Listening on:", handle startup failure |
| `_test_step` | 191–224 (42 lines) | Create VirtualInputController, manage try/finally, loop over versions with cancellation check, update DB per version, call test_single_version, accumulate/persist results, kill servers in finally |

`run_job` has 3 levels of nesting (try/except/finally plus step logic) and manages process state (`proxy_proc`, `pico_limbo_proc`) manually across all steps. The `finally` block (lines 289–290) calls `_kill_server` which is also called from `_test_step`'s finally (line 215), meaning servers can be killed twice.

### 1.3 Why this causes bugs and context bloat

- **Implicit cross-step communication**: `_build_step` sets `artifact_path` via the database, but `run_job` doesn't know that — it must re-fetch the job (line 240). Control flow is split across functions communicating via a shared mutable dict + database, not return values.
- **Magic constants at module level** (lines 27–36): `SECONDS_PER_VERSION = 90`, `SERVER_CONFIG_CONTENT`, `SERVER_ADDRESS`, `PICO_LIMBO_INTERNAL_PORT = 30066`, `GAME_DIRECTORY`, `SCREENSHOTS_DIR` — used throughout with no inline explanation.
- **Hardcoded paths**: `/app/minecraft`, `/app/integration_tests_reports`, `/tmp/server.toml` scatter deployment-specific details through business logic.

### 1.4 Test fragility

`tests/test_job_runner_idempotency.py` (36.7KB, ~3x the source file) — **60% of tests verify mock call patterns, not real behavior**:

- `TestBuildStepArtifactExists` — verifies `ensure_repo_cloned`, `update_repo`, `resolve_commit` are called in sequence (line 116). Uses `_make_path_mock()` (lines 40–43) to engineer a fake `Path` with custom `__truediv__` behavior — testing path construction, not build artifact behavior.
- `TestBuildStepArtifactMissing` — verifies `build_project` is called with specific positional arguments (lines 155–157).
- `TestTestStepPersistence` — verifies `database.update_job` is called exactly 6 times for 3 versions (line 304). Tests DB call count, not persistence correctness.

Only ~40% test real behavior: ETA computation (pure function, well-tested), version iteration count, result propagation, and status transitions.

---

## 2. Proposed Structure

### 2.1 Apply Single Responsibility Principle (SRP)

Split `job_runner.py` into focused modules, each owning one responsibility:

```
src/orchestration/
├── job_runner.py          # Thin orchestrator: state machine transitions, error handling, process lifecycle
├── build_orchestrator.py  # Build pipeline: clone → update → resolve → build
├── server_orchestrator.py # Server lifecycle: config generation, proxy management, subprocess startup
├── test_orchestrator.py   # Test execution: version iteration, result accumulation, persistence
└── _steps.py              # Shared step primitives (reusable across orchestrators)
```

**`job_runner.py`** becomes a thin coordinator (~50 lines) that:
1. Fetches the job
2. Calls each orchestrator in sequence
3. Handles errors and cleanup via a context manager
4. Updates final status

**`build_orchestrator.py`** owns the build lifecycle, accepting an `Engine` interface and returning build results (artifact path, commit hash) rather than mutating a shared dict.

**`server_orchestrator.py`** owns server setup, accepting a `ProxyFactory` and `ConfigWriter` interface.

**`test_orchestrator.py`** owns test execution, accepting a `TestRunner` interface and returning results.

### 2.2 Apply Interface Segregation Principle (ISP)

Replace direct imports with interfaces:

| Current coupling | Interface to introduce |
|-----------------|----------------------|
| `database.update_job`, `database.get_job_by_id` | `JobRepository` protocol with `get(id)`, `update(id, **fields)`, `update_results(id, results)` |
| `engine.ensure_repo_cloned`, `engine.update_repo`, `engine.resolve_commit`, `engine.build_project` | `BuildEngine` protocol with `build(job) -> BuildResult` |
| `create_servers_dat`, `test_single_version`, `VirtualInputController` | `ServerSetup` and `TestRunner` protocols |
| `get_proxy_manager(proxy_type)` | `ProxyFactory` protocol with `create(proxy_type) -> ProxyManager` |

### 2.3 Apply Dependency Inversion Principle (DIP)

`job_runner.py` should depend on abstractions (protocols/interfaces), not concrete modules. Concrete implementations are wired at the entry point.

---

## 3. Dependency Injection

### 3.1 Before: Direct imports, hard to test, hard to swap

```python
# job_runner.py — current state
from src.database import get_job_by_id, update_job
from src.engine import build_project, ensure_repo_cloned, update_repo, resolve_commit
from src.minecraft.runner import create_servers_dat, test_single_version
from src.minecraft.input import VirtualInputController

def _server_step(job, ...):
    proxy = get_proxy_manager(job.get("proxy_type"))  # Direct import
    proxy.start()
    proxy.wait_for_ready()
    create_servers_dat(job)  # Direct import
    controller = VirtualInputController()  # Direct instantiation
    test_single_version(controller, ...)  # Direct import
```

**Problems**: Every test must patch 6+ module-level imports. Swapping the proxy implementation requires changing `job_runner.py`. Tests verify mock call counts, not behavior.

### 3.2 After: DI via constructor injection

```python
# job_runner.py — refactored
from typing import Protocol

class ProxyFactory(Protocol):
    def create(self, proxy_type: str) -> ProxyManager: ...

class TestRunner(Protocol):
    def run(self, controller, version) -> TestResult: ...

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
        self.config_writer.write_server_toml(job)
        # ... subprocess management
        return ServerContext(proxy, subprocess)
```

**Benefits**:
- Tests inject `MockProxyFactory`, `MockTestRunner` — no module-level patching needed
- Swapping the proxy is a wiring change at the entry point, not in business logic
- Each class has 2–3 clearly named dependencies that are visible in the constructor

### 3.3 Wiring at the entry point

```python
# main.py — wiring
from src.proxy.velocity import VelocityProxyManager
from src.minecraft.runner import MinecraftTestRunner

proxy_factory = ProxyFactoryImpl({
    "velocity": VelocityProxyManager,
})
test_runner = MinecraftTestRunner()
config_writer = ServerConfigWriter()

build_orchestrator = BuildOrchestrator(engine=build_engine)
server_orchestrator = ServerOrchestrator(
    proxy_factory=proxy_factory,
    config_writer=config_writer,
    test_runner=test_runner,
)
test_orchestrator = TestOrchestrator(test_runner=test_runner)

job_runner = JobRunner(
    repository=database,
    build_orchestrator=build_orchestrator,
    server_orchestrator=server_orchestrator,
    test_orchestrator=test_orchestrator,
)
```

---

## 4. Test Strategy

### 4.1 After the refactor, tests should look like this

**Unit tests** — each orchestrator tested in isolation with injected mocks:

```python
# test_server_orchestrator.py
def test_starts_proxy_and_writes_config():
    mock_proxy = Mock(spec=ProxyManager)
    mock_factory = Mock(spec=ProxyFactory)
    mock_factory.create.return_value = mock_proxy
    mock_writer = Mock(spec=ConfigWriter)

    orchestrator = ServerOrchestrator(mock_factory, mock_writer, mock_test_runner)
    result = orchestrator.start_servers(job)

    mock_factory.create.assert_called_once_with("velocity")
    mock_proxy.start.assert_called_once()
    mock_writer.write_servers_dat.assert_called_once_with(job)
    assert result.proxy is mock_proxy
```

No module-level `@patch` decorators. No `_make_path_mock()` helpers. No verifying call counts of `database.update_job`.

**Integration tests** — test real behavior with minimal mocks:

- Test that the orchestrator correctly accumulates test results across versions (real data flow, not mock call counts)
- Test that status transitions follow the expected state machine (real behavioral tests)
- Test ETA computation (pure function, already well-tested)

### 4.2 What to stop testing

- **Mock call counts** (e.g., "database.update_job called exactly 6 times") — this is an implementation detail. If we batch updates or change persistence strategy, these tests break without the behavior changing.
- **Argument order verification** (e.g., "build_project called with positional args (a, b, c)") — this couples tests to function signatures.
- **Path construction via fake `Path` objects** (`_make_path_mock()`) — this tests implementation of path building, not whether the build artifact exists.

### 4.3 What to keep/start testing

- **Status transitions** — "building → testing → finished" (already real behavioral tests)
- **Version iteration** — all versions are tested (already real behavioral tests)
- **Result propagation** — results from `test_single_version` flow into the result dict (already real behavioral tests)
- **ETA computation** — pure function, well-tested
- **Error handling** — what happens when build fails, server fails to start, test raises

---

## 5. Migration Steps

Each step should be independently deployable and tested. No all-or-nothing rewrite.

### Step 1: Extract `BuildOrchestrator` (1–2 hours)

- Create `src/orchestration/build_orchestrator.py`
- Move `_build_step` logic into a `BuildOrchestrator.build(job) -> BuildResult` method
- `BuildResult` is a dataclass: `artifact_path: Path | None`, `commit_hash: str`
- Inject `engine` as a `BuildEngine` protocol (or just pass the engine module for now)
- Update `run_job` to call `build_orchestrator.build(job)` and use the returned `BuildResult`
- Tests: move and adapt `_build_step` tests to test `BuildOrchestrator`

### Step 2: Extract `ServerOrchestrator` (2–3 hours)

- Create `src/orchestration/server_orchestrator.py`
- Move `_server_step` logic into `ServerOrchestrator.start_servers(job) -> ServerContext`
- `ServerContext` holds `proxy`, `pico_limbo_proc`, and cleanup method
- Inject `ProxyFactory` and `ConfigWriter` as protocols
- Update `run_job` to use the returned context
- Tests: move and adapt `_server_step` tests

### Step 3: Extract `TestOrchestrator` (1–2 hours)

- Create `src/orchestration/test_orchestrator.py`
- Move `_test_step` logic into `TestOrchestrator.run_tests(job) -> TestResults`
- Inject `TestRunner` and `JobRepository` as protocols
- Tests: move and adapt `_test_step` tests, eliminate mock-call-count tests

### Step 4: Thin `run_job` to a state machine (1 hour)

- `run_job` becomes ~50 lines: fetch job, call orchestrators in sequence, handle errors, update final status
- Replace the 3 re-fetches of the job with return values from orchestrators
- Process cleanup moves into a context manager or the orchestrators' `ServerContext`

### Step 5: Replace module-level imports with DI wiring (1 hour)

- Wire all protocols at the entry point (`main.py` or `src/main.py`)
- Replace direct `from src.database import ...` with injected `JobRepository`
- Replace `from src.engine import ...` with injected `BuildEngine`
- Replace `from src.proxy.velocity import ...` with injected `ProxyFactory`

### Step 6: Clean up tests (2–3 hours)

- Remove `_make_path_mock()` helper — test artifact existence via real `Path` or a simple `exists: bool` parameter
- Remove tests that verify mock call counts (e.g., "database.update_job called exactly 6 times")
- Keep tests that verify: status transitions, version iteration, result propagation, error handling
- The test file should shrink from 36KB to ~10–15KB

### Step 7: Remove dead code (30 min)

- Remove unused `models` import (line 14)
- Remove unused `ALL_VERSIONS` dynamic import (line 325) if no longer needed
- Consolidate magic constants into a config module or constants file
