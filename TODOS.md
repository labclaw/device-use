# TODOS.md — Device-Use

> Generated from EXPANSION Review 2026-03-16. Review: `docs/plans/2026-03-16-expansion-review.md`

## P0 — Prerequisites (before feature work)

### TODO-DU1: BDD Tests + Coverage Enforcement
- **What:** Add pytest-bdd dependency. Create initial BDD feature files for: agent loop (OBSERVE→PLAN→ACT→VERIFY), pipeline execution (sequential + parallel), safety guard (5 layers + rate limit), MCP server (9 tools + error paths). Set `fail_under` in `pyproject.toml [tool.coverage.report]`.
- **Why:** Zero BDD tests exist. This violates the mandatory project convention: "BDD is non-negotiable for ALL 5 subprojects." 530 unit tests exist but behavior specs are missing entirely. Without coverage enforcement, regressions can slip through.
- **Pros:** Brings device-use into compliance. BDD scenarios document behavior for new contributors. Coverage enforcement prevents regressions.
- **Cons:** ~2-3 day effort. Need to determine current coverage baseline first. Some components (A11y operator) are hard to test without macOS permissions.
- **Context:** Project-wide convention in root CLAUDE.md: "BDD format: Given/When/Then scenarios describing user-facing behavior." Labclaw has 46 BDD features as reference. Use `tests/features/` directory with step definitions.
- **Effort:** M (2-3 days)
- **Priority:** P0
- **Depends on:** Nothing
- **Blocks:** Everything (convention compliance gate)

### TODO-DU2: Async-First Refactor
- **What:** Make `BaseInstrument` methods async (`connect`, `list_datasets`, `process`, `acquire`). Make `Orchestrator.run()` async. Remove `ThreadPoolExecutor` from `_run_parallel_batch()` and `_execute_step_with_timeout()` — use `asyncio.gather()` and `asyncio.wait_for()`. Update all adapters (TopSpinAdapter, PlateReaderAdapter).
- **Why:** Current sync/async split: `BaseInstrument` is sync, `DeviceAgent` is async, `Orchestrator` uses ThreadPoolExecutor. MCP event push (DU4) requires async. Real-time streaming requires async. Aligns with labclaw TODO-1 (async daemon refactor) — both repos converge on async-first.
- **Pros:** Eliminates ThreadPoolExecutor hacks, enables MCP push, enables real-time streaming, aligns with labclaw architecture.
- **Cons:** ~3 day effort, touches all instrument adapters + orchestrator + tests. Breaking change for any external code using BaseInstrument.
- **Context:** `instruments/base.py` defines sync ABC. `orchestrator.py` lines 634-654 use ThreadPoolExecutor. `core/agent.py` is already async. Key methods to convert: `BaseInstrument.connect()`, `.list_datasets()`, `.process()`, `.acquire()`. `Orchestrator.run()` → `async def run()`. `_run_parallel_batch()` → `asyncio.gather()`.
- **Effort:** M (3 days)
- **Priority:** P0
- **Depends on:** DU1 (need tests before refactoring)
- **Blocks:** DU3, DU4, DU5

---

## P1 — Core Features

### TODO-DU3: Safety L3 Vision Verification
- **What:** Implement `StateVerificationChecker` to compare expected vs actual screen state after GUI actions using VLM. Currently a stub that always returns `allowed=True`. After each GUI action: capture screenshot → send to VLM with "does this match expected state?" → reject if unexpected dialog/error/misclick detected.
- **Why:** For a system controlling physical instruments (plate readers, microscopes, spectrometers), a stub safety layer is a production blocker. L3 is the layer that catches: misclicks on wrong buttons, unexpected error dialogs, instrument crash popups, wrong application focused.
- **Pros:** Completes the 5-layer safety system. Prevents physical damage from GUI automation errors. Enables unattended instrument operation.
- **Cons:** ~3 day effort. Requires VLM API call per verification (latency + cost). False positives could halt legitimate operations. Need calibration for acceptable state delta.
- **Context:** `safety/layers.py` lines 110-123 define the stub. The VLM backend (`VisionBackend.observe()`) already exists for screenshots. L3 needs: expected state description (from PromptBuilder), actual screenshot, VLM comparison, threshold for "acceptable vs unexpected change".
- **Effort:** M (3 days)
- **Priority:** P1
- **Depends on:** DU2 (async — VLM call is async)
- **Blocks:** Production lab deployment

### TODO-DU4: MCP Event Push to LabClaw
- **What:** When instrument produces data (spectrum, plate reading, any result), device-use emits MCP event `instrument.data.ready` with structured payload: `{instrument_id, data_type, timestamp, rows: [...]}`. This is the device-use side of labclaw TODO-4.
- **Why:** Currently instrument results stay in device-use memory. No mechanism to push to labclaw for discovery. This is the "hands → brain" data pipeline. Without it, the Physical AI Scientist has no feedback loop.
- **Pros:** Completes the instrument → brain data pipeline. Enables real-time discovery. No more manual CSV drops.
- **Cons:** ~2 day effort. Requires labclaw MCP client (labclaw TODO-3) to be ready. Need data format contract between device-use and labclaw.
- **Context:** `integrations/labclaw.py` already has `GUIDriver` + `DeviceUsePlugin`. Add MCP event emission in `orchestrator.py` after step completion: if step output contains instrument data, emit MCP event. `integrations/mcp_server.py` needs MCP resource or notification channel.
- **Effort:** M (2 days)
- **Priority:** P1
- **Depends on:** DU2 (async) + labclaw TODO-3 (MCP client)
- **Blocks:** labclaw TODO-4 (auto data pipeline)

---

## P2 — Advanced Features

### TODO-DU5: Operator Auto-Negotiation
- **What:** On instrument connect, probe available control layers (API→Script→A11y→CU) and auto-select best. Per-action fallback: if higher layer fails, drop to next. Currently user picks mode manually when creating adapter (e.g., `TopSpinAdapter(mode="offline")`).
- **Why:** Adding 20+ instruments requires "just works" behavior. Scientists shouldn't need to know which control layer to use. Auto-negotiation + fallback makes device-use robust against partial failures (e.g., API down but A11y works).
- **Pros:** "Just works" for new instruments. Automatic fallback on failure. Enables dynamic layer selection per action.
- **Cons:** ~5 day effort. Complex probing logic per platform. Needs per-layer health check. May have unexpected latency during negotiation.
- **Context:** `operators/base.py` defines `BaseOperator.available_layers()`. Each instrument adapter needs a `probe_layers()` method. `Orchestrator` needs layer selection logic: try highest-priority available layer, fall back on failure.
- **Effort:** L (5 days)
- **Priority:** P2
- **Depends on:** DU2 (async operators)
- **Blocks:** Multi-instrument support at scale

---

## P3 — Tech Debt

### TODO-DU6: Extract Web UI from Python String
- **What:** Move the 939-line HTML string from `web/app.py` to a proper `web/static/index.html` file. Fix CORS (`allow_origins=["*"]` → configurable). Remove `sys.path.insert(0, ...)` hack. Consider merging with labwork-web.
- **Why:** 939-line HTML string in Python is unmaintainable. CORS `allow_origins=["*"]` is a security issue. `sys.path.insert` is fragile.
- **Pros:** Cleaner code, proper CORS, standard file serving.
- **Cons:** ~1 day effort. Low impact — web UI is demo-only.
- **Context:** `web/app.py` lines 335-939. The HTML should be served via `StaticFiles` (FastAPI already imported). CORS should use env var `DEVICE_USE_CORS_ORIGINS`.
- **Effort:** S (1 day)
- **Priority:** P3
- **Depends on:** Nothing
- **Blocks:** Nothing

---

## Delight Items

### DD1: `device-use doctor`
- Diagnostic command: TopSpin reachable? A11y permissions? API key? Python SDK?
- **Effort:** S (30 min)

### DD2: Action Replay GIF
- Record screenshots during GUI automation, assemble into GIF. Visual audit trail.
- **Effort:** S (30 min) — `DemoRecorder` already exists in demos/lib/

### DD3: "Watch Me" Mode
- Narrate GUI actions in real-time: "Clicking Processing menu... Selecting FT..."
- **Effort:** S (30 min)

### DD4: Live Pipeline Terminal Viz
- Real-time terminal display: `[OK] load → [>>] process → [..] analyze`
- **Effort:** S (30 min) — `pipeline.summary()` exists, need real-time version

### DD5: Instrument Connection Chime
- Subtle audio feedback on instrument connect/disconnect.
- **Effort:** S (30 min)
