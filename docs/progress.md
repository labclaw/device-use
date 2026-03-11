# Device-Use Progress Report

**Last updated:** 2026-03-11
**Branch:** `feat/ai-scientist-loop` (worktree: `wt-device-use-ai-scientist`)

---

## Current Milestone: AI Scientist Closed-Loop Demo

### Delivered (2026-03-11)

| Deliverable | File | Lines | Status |
|-------------|------|-------|--------|
| AI Scientist closed-loop demo | `demos/17_ai_scientist_loop.py` | 654 | DONE |
| Unit + integration tests | `tests/test_ai_scientist_loop.py` | 277 | 32/32 PASS |
| Full regression | `tests/` | — | 442/451 PASS (9 pre-existing) |

### Demo Capabilities

```
Scientific Question
       |
  ┌────▼────┐
  │ OBSERVE  │  Connect TopSpin, process FID, extract peaks, spectral library baseline
  └────┬─────┘
  ┌────▼────────┐
  │ HYPOTHESIZE │  NMRBrain (Claude API / cached), parse compound + confidence + assignments
  └────┬────────┘
  ┌────▼────┐
  │ VERIFY  │  PubChem cross-ref, formula match, peak coverage, library score
  └────┬────┘
  ┌────▼─────┐
  │ EVALUATE │  Grounding score = 0.3*formula + 0.4*peaks + 0.3*library
  └────┬─────┘
       │ score >= 0.7 → ACCEPT
       │ score <  0.7 → add constraints, loop back to HYPOTHESIZE (max 3 iterations)
  ┌────▼────┐
  │ REPORT  │  IMRAD markdown, audit trail, zero hallucination (programmatic, no AI)
  └─────────┘
```

### Verified Runs

| Dataset | Compound | Score | Iterations | Time | Mode |
|---------|----------|-------|------------|------|------|
| exam_CMCse_1 | Alpha Ionone | 0.92 | 1 | 48s | cached AI |
| exam_CMCse_3 | Strychnine | 1.00 | 1 | 51s | cached AI |
| exam_CMCse_1 | Alpha Ionone | 1.00 | 1 | 40s | --no-brain (library only) |

---

## Overall Project Status

### device-use (this repo)

| Component | Status | Tests | Notes |
|-----------|--------|-------|-------|
| NMR adapter (offline) | DONE | 95+ | TopSpin examdata, nmrglue |
| NMR brain (Claude) | DONE | — | Cached fallback for demos |
| Plate reader adapter | DONE | 22 | Absorbance + fluorescence |
| Orchestrator | DONE | 53 | Pipeline + registry + events |
| MCP server | DONE | 12 | Claude Code integration |
| Web GUI | DONE | 16 | FastAPI port 8420 |
| PubChem tool | DONE | — | PUG REST lookup |
| ToolUniverse | DONE | — | 600+ Harvard tools |
| Spectral library | DONE | — | Peak fingerprint matching |
| SkillContext (4-layer) | DONE | — | SOUL + profile + science + RAG |
| **AI Scientist demo** | **DONE** | **32** | **Closed-loop, grounded** |
| Operators (4-layer) | PROTOTYPE | 0 | base.py + a11y.py, uncommitted |
| CU GUI automation | PROTOTYPE | — | GPT-5.4 + AppleScript |
| **Total** | — | **442** | **17 demos** |

### Sibling repos

| Repo | Status | Key milestone |
|------|--------|---------------|
| device-skills | bruker-topspin complete | skill.yaml + SOUL.md + 574 docs |
| labwork-web | 17/17 tests pass | FastAPI + vanilla JS debug UI |
| labclaw | Core architecture built | Pre-v0.1.0, TDD |
| labwork | Electron shell | MCP integration, rebuild planned |

### CU Research (v3.1 FINAL)

| Model | OSWorld | Source verified |
|-------|---------|----------------|
| GPT-5.4 | 75.0% | OpenAI blog (not XLANG) |
| Claude Sonnet 4.6 | 72.11% | XLANG verified |
| Human baseline | 72.36% | XLANG verified |
| Agent S3 + BJudge | 72.58% | Paper v2 |

**Architecture decision:** 4-layer control (API > Script > A11y > CU)
**A11y breakthrough:** TopSpin Java/OpenJDK exposes 421 AX elements on macOS

---

## Backlog (Priority Order)

| # | Task | Priority | Status |
|---|------|----------|--------|
| 1 | Merge `feat/ai-scientist-loop` → main | P0 | Awaiting approval |
| 2 | Commit operators/ code (base.py, a11y.py) | P0 | Uncommitted on main |
| 3 | TopSpin A11y end-to-end test (click_menu) | P0 | read_state verified |
| 4 | Test multi-iteration loop with live API key | P1 | Not tested |
| 5 | Instrument Profile YAML schema | P1 | Not started |
| 6 | Connect operators to TopSpinAdapter | P1 | Not started |
| 7 | Windows UIA operator design | P2 | Architecture only |
| 8 | Claude CU single-action backend | P2 | Not started |
| 9 | Labwork rebuild Phase 1 (Agent SDK + Eigent) | P3 | Research complete |
| 10 | UI-Venus-1.5-8B local grounding model | P3 | Not started |

---

## Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-11 | 4-layer operator architecture | API > Script > A11y > CU fallback chain |
| 2026-03-11 | GPT-5.4 for CU production, Claude for safety-critical | OSWorld scores + batch efficiency |
| 2026-03-11 | Windows is bigger target than macOS | Most scientific software is Windows-only |
| 2026-03-11 | Zero-hallucination reports (programmatic, not AI-written) | Grounding score + audit trail |
| 2026-03-11 | Closed-loop iteration with grounding threshold | Score < 0.7 triggers refinement |
