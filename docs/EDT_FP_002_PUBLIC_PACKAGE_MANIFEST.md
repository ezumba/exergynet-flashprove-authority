# EDT-FP-002 — Public Package Manifest

**Package name:** `exergynet-flashprove-authority`  
**Date:** 2026-11-05  
**Status:** DRAFT — not published (Trustee authorization required)

---

## Purpose

An isolated, open-source integration package that demonstrates the axiom:

**MODEL INFERENCE PROVENANCE ≠ EXECUTION AUTHORITY**

Using Anthropic's FlashProve CPU verifier (Apache 2.0) together with an
authority gate that mirrors LNES-22's deterministic policy logic.

---

## Package Contents

```
exergynet-flashprove-authority/
├── README.md
├── LICENSE          (Apache 2.0 — covers adapter code)
├── NOTICE           (Anthropic attribution for FlashProve upstream)
├── adapter/
│   ├── flashprove_shim.py           # Main adapter (EDT-FP-001 + EDT-FP-002)
│   └── lnes22_authority_bridge.py   # Subprocess bridge to real LNES-22 (new)
├── policy/
│   └── allowed_commitments.json    # Sample trusted commitment registry
├── tests/
│   └── test_all.py                 # 92-test suite (45 original + 47 new)
├── docs/
│   ├── INTEGRATION_GUIDE.md        # How to wire a real LNES-22 source
│   └── [9 EDT_FP_002_*.md files]
├── upstream/
│   └── setup.sh                    # Build FlashProve from source
└── SHA256SUMS
```

---

## What Is Included / Excluded

| Item | Included | Reason |
|------|---------|--------|
| `adapter/flashprove_shim.py` | YES | Core integration logic |
| `adapter/lnes22_authority_bridge.py` | YES | LNES-22 bridge (uses local simulation if source not available) |
| `tests/test_all.py` | YES | Full 92-test suite |
| `upstream/setup.sh` | YES | Build script |
| `upstream/bin/cp_verify` | NO | Build from source; binary not redistributed |
| Real LNES-22 source (`policy_gate.py`, etc.) | NO | Private ExergyNet source; users bring their own |
| Production commitment IDs | NO | Sample fixtures only |
| Any private keys | NO | Never |

---

## User Setup Instructions

### Without real LNES-22 source (LOCAL_SIMULATION mode)

```bash
# 1. Build FlashProve verifier
bash upstream/setup.sh

# 2. Run tests (simulation mode — no LNES22_SOURCE_PATH needed)
python -m pytest tests/test_all.py -v
```

Tests that require real LNES-22 will be skipped automatically.

### With real LNES-22 source

```bash
# 1. Build FlashProve verifier
bash upstream/setup.sh

# 2. Set the path to your LNES-22 source directory
export LNES22_SOURCE_PATH=/path/to/vendor/lnes22

# 3. Run tests (all 92 should pass)
python -m pytest tests/test_all.py -v
```

The bridge will use the real `evaluate_tool_capability()` from your source.

---

## License

- Adapter code (`adapter/`): Apache 2.0
- FlashProve upstream: Apache 2.0 (Anthropic)
- Not affiliated with or endorsed by Anthropic

---

## Publication Blockers

| Blocker | Class | Resolution |
|---------|-------|------------|
| Trustee authorization | GOVERNANCE | Explicit operator approval required |
| Independent Codex audit completion | PROCESS | **COMPLETE** — see `EDT_FP_002_CODEX_AUDIT.md` |
