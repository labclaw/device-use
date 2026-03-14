# wt-device-use-e2e Progress

**Last updated:** 2026-03-13
**Branch:** `feat/e2e-closed-loop`
**HEAD:** `5727da0`

## Current State

- This worktree is now green on its current branch state:
  - `cd wt-device-use-e2e && pytest -q`
  - Result: `539 passed`
- The deterministic showcase demo is runnable without provider/API key:
  - `cd wt-device-use-e2e && env DEMO_DISABLE_VLM=1 DEMO_REQUIRE_VLM=0 python3 -u demos/record_full_showcase.py`
  - Result: `Pipeline: 7/7 in 172s`

## Verified Fixes

- `E2E-DEMO-001`: deterministic control path no longer depends on `OPENROUTER_API_KEY`
- `WT-TEST-001`: local test helpers no longer bleed across repos via bare `conftest` import
- `WT-TEST-002`: CLI subprocess tests now run with explicit repo-root import context

## Artifacts

- Latest deterministic demo outputs:
  - `/tmp/full_showcase_output/labclaw_full_20260313_211559.mp4`
  - `/tmp/full_showcase_output/labclaw_full_20260313_211559_4k.mp4`
  - `/tmp/full_showcase_output/labclaw_full_20260313_211559.gif`

## Working Tree Notes

- This worktree still contains additional untracked demo scripts and docs beyond the closed fixes:
  - `demos/25_vnc_cu_demo.py`
  - `demos/record_demo.py`
  - `demos/record_demo_hq.py`
  - `demos/record_full_showcase.py`
  - `demos/record_showcase.py`
  - `docs/superpowers/`

## Audit Reference

- Full cross-repo findings, fix batches, and verification evidence:
  - [`../../docs/DEEP_AUDIT_2026-03-13.md`](../../docs/DEEP_AUDIT_2026-03-13.md)
