# Device-Use EXPANSION Review — 2026-03-16

## Review Mode: SCOPE EXPANSION
## Reviewer: Claude Opus 4.6 (CEO Plan Review)
## Status: Complete — all 10 sections reviewed, 0 unresolved decisions

---

## Executive Summary

Device-use is a well-architected v0.1.0 prototype — "ROS for lab instruments" — with solid safety design (5-layer guard), clean abstractions (VisionBackend protocol, BaseOperator hierarchy), and 530 unit tests. However, it has **critical governance and production gaps**:

1. **Zero BDD tests** — violates mandatory project conventions
2. **No coverage enforcement** — `fail_under` not set
3. **Safety L3 is a stub** — `StateVerificationChecker` always returns `allowed=True`
4. **No data push to labclaw** — instruments produce results that stay in memory
5. **Sync/async split** — BaseInstrument sync, DeviceAgent async, Orchestrator uses ThreadPoolExecutor
6. **939-line HTML string** in Python source with CORS `allow_origins=["*"]`

The EXPANSION path: fix governance (P0), refactor to async-first (P0), implement safety L3 + MCP push (P1), then operator auto-negotiation (P2).

---

## System Audit

| Metric | Value |
|--------|-------|
| Source | 44 files, ~30K lines Python |
| Tests | 530 tests, 22 test files, **0 BDD features** ★ |
| Coverage | **Not enforced** |
| Instruments | NMR (TopSpin) + Plate Reader |
| Operator layers | L3 (A11y) partial, L4 (CU) working; L1, L2 not implemented |
| Safety layers | L1 (whitelist) ✅, L2 (bounds) ✅, L3 (verify) ★STUB, L4 (human) ✅, L5 (e-stop) ✅ |
| MCP tools | 9 tools (list_instruments, list_tools, call_tool, nmr_*, plate_reader_*, run_pipeline) |
| Stale branches | `feat/e2e-closed-loop`, `fix/audit-closeout` |

## Architecture Strengths
- 5-layer safety chain with rate limiting, forbidden regions, emergency stop
- VisionBackend protocol — multi-provider (Claude, GPT, Gemini, UI-TARS)
- 4-layer operator abstraction (API→Script→A11y→CU) with IntEnum ordering
- SkillContext 4-layer prompt assembly with token budgets and RAG

## Critical Findings

### Error/Rescue Gaps
1. **L3 safety stub** — always passes → physical risk with hardware
2. **A11y operator crash** — no null guards on ctypes window handles
3. **MCP call_tool()** — no try/except on `json.loads(params)`
4. **SSE streaming** — generator doesn't detect client disconnect
5. **Orchestrator parallel batch** — shared dict context without thread safety

### Security
1. **CORS `allow_origins=["*"]`** on web app
2. **`run_pipeline()` MCP tool** — accepts external JSON pipeline definition, no validation
3. **`sys.path.insert` hack** in web/app.py

### Code Quality
1. 939-line HTML string embedded in Python
2. `_get_orchestrator()` duplicated in MCP server + web app
3. SSE streaming pattern duplicated 2x
4. `VisionBackend.plan()` returns untyped `dict[str, Any]`

---

## Priority Roadmap

### P0 — Prerequisites (before feature work)
| # | Item | Effort | Depends On |
|---|------|--------|------------|
| DU1 | BDD tests + coverage enforcement | M (2-3 days) | — |
| DU2 | Async-first refactor (BaseInstrument + Orchestrator) | M (3 days) | — |

### P1 — Core Features
| # | Item | Effort | Depends On |
|---|------|--------|------------|
| DU3 | Safety L3 vision verification | M (3 days) | DU2 |
| DU4 | MCP event push to labclaw | M (2 days) | DU2 + labclaw TODO-3 |

### P2 — Advanced Features
| # | Item | Effort | Depends On |
|---|------|--------|------------|
| DU5 | Operator auto-negotiation (probe + fallback) | L (5 days) | DU2 |

### P3 — Tech Debt
| # | Item | Effort | Depends On |
|---|------|--------|------------|
| DU6 | Extract web UI from Python string, fix CORS | S (1 day) | — |

### Delight Items
| # | Item | Effort |
|---|------|--------|
| DD1 | `device-use doctor` diagnostic command | S (30 min) |
| DD2 | Action replay GIF (visual audit trail) | S (30 min) |
| DD3 | "Watch me" mode (narrated GUI actions) | S (30 min) |
| DD4 | Live pipeline terminal visualization | S (30 min) |
| DD5 | Instrument connection chime | S (30 min) |

---

## Key Decisions
1. **SCOPE EXPANSION** — device-use becomes universal instrument SDK
2. **BDD governance first** — fix convention violations before feature work
3. **Async-first** — align with labclaw async refactor
4. **MCP bidirectional** — device-use pushes data, labclaw subscribes (shared decision with labclaw review)

## Cross-Repo Dependencies

```
device-use DU2 (async)  ←→  labclaw TODO-1 (async daemon)     — same async model
device-use DU4 (MCP push) → labclaw TODO-3 (MCP client)       — DU4 needs TODO-3 done
device-use DU4 (MCP push) = labclaw TODO-4 (data pipeline)    — two sides of same coin
```
