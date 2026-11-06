# EDT-FP-002 — Reproducible Build

**Date:** 2026-11-05  
**Status:** QUALIFIED — same build as EDT-FP-001 (no new binary artifacts)

---

## FlashProve Verifier

EDT-FP-002 uses the same `cp_verify` binary built during EDT-FP-001.
No new upstream dependencies or build steps were added.

| Artifact | Value |
|----------|-------|
| Upstream commit | `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` |
| `cp_verify` SHA-256 | `7f9efc1e86a848a3715c6cc870e465ac2a1c5e8fd1eac09e4809023de7604394` |
| Build path | `upstream/bin/cp_verify` |
| Build script | `upstream/run_build.sh` |
| Build platform | WSL2 Linux (`/mnt/c/...`), non-root user `edt` |

Build verification:
```
THE VERIFIER IS BUILT: upstream/bin/cp_verify
Reference proof: exit=0, last_line=YES, result-v1 status=0
```

## Python Components

EDT-FP-002 adds two Python files:

| File | Note |
|------|------|
| `adapter/lnes22_authority_bridge.py` | Pure Python, no compiled components, no C extensions |
| Additions to `adapter/flashprove_shim.py` | Same |

Both files use only Python 3.10+ standard library modules. No additional
`pip install` required beyond the EDT-FP-001 requirements (pytest).

## Test Reproducibility

The full test suite (92 tests) is deterministic:
- No random seeds
- No time-dependent logic in test assertions
- Temporary directories cleaned up after each test
- Replay protection store uses fresh temporary dirs per test

To reproduce:
```bash
cd exergynet-flashprove/
python -m pytest tests/test_all.py -v
```

Expected without LNES22_SOURCE_PATH: 88 passed, 4 skipped (real-LNES-22 round-trip tests skip gracefully)
Expected with LNES22_SOURCE_PATH set: 92 passed
(verifier-requiring tests and LNES22_REAL_AVAILABLE tests skip on Windows).

## Hash Stability

`SHA256SUMS` updated after EDT-FP-002 code is complete. All deliverable
files are listed with their SHA-256 digests.
