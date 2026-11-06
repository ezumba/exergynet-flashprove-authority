# ExergyNet × FlashProve Authority Adapter

An open-source demonstration of the axiom:

> **MODEL INFERENCE PROVENANCE ≠ EXECUTION AUTHORITY**

This package integrates Anthropic's [FlashProve](https://github.com/anthropics/flashprove)
CPU verifier with an authority gate that mirrors the real LNES-22 deterministic
policy logic, demonstrating that a cryptographically valid inference proof does
**not** automatically grant execution authority for sensitive operations.

---

## What this is

**Local development integration.** When `LNES22_SOURCE_PATH` is set to a directory
containing the real LNES-22 `policy_gate.py`, the bridge calls
`evaluate_tool_capability()` directly and labels decisions:

```
engine: REAL_LNES22_LOCAL_DEVELOPMENT
```

When `LNES22_SOURCE_PATH` is unset (the default for external users), the bridge
runs `LOCAL_SIMULATION` mode — a faithful local mirror of the same check sequence.

**This is NOT:**
- Production LNES-22 certification
- A connection to any ExergyNet production authorization service
- An endorsement by or affiliation with Anthropic
- Authorization for mainnet execution or financial transactions

---

## Quick start

```bash
# 1. Build the FlashProve CPU verifier (requires Linux, g++ 13+, make, unzip)
bash upstream/setup.sh

# 2. Run the full test suite (LOCAL_SIMULATION mode — no real LNES-22 needed)
python -m pytest tests/test_all.py -v

# 3. Run with real LNES-22 source (optional)
export LNES22_SOURCE_PATH=/path/to/vendor/lnes22
python -m pytest tests/test_all.py -v
```

Expected without prerequisites (no cp_verify, no LNES22): **84 pass, 18 skip** (observed on Windows/Mac/Linux without build).  
Expected on Linux with cp_verify built, no LNES22: **98 pass, 4 skip** (verified 2026-11-06, WSL2/Ubuntu, Python 3.12.3).  
Expected on Linux with cp_verify + `LNES22_SOURCE_PATH`: **102/102 pass** (requires private LNES-22 source; not publicly available).  
Tests requiring the verifier binary or LNES-22 source skip automatically when those prerequisites are absent.

---

## Architecture

```
FlashProve proof  ──►  cp_verify (CPU verifier)  ──►  VerificationResult
                                                              │
                                                              ▼
CanonicalActionRequest (12 fields)  ──►  evaluate_authority_real()
                                              │
                                              ▼
                                    ReplayProtectionStore
                                    (SQLite, multiprocess-safe)
                                              │
                                    check_and_record_atomic()
                                              │
                                              ▼
                                   lnes22_authority_bridge.py
                                   (subprocess, shell=False)
                                              │
                                    LOCAL_SIMULATION or
                                    REAL_LNES22_LOCAL_DEVELOPMENT
                                              │
                                              ▼
                              AuthorityDecision (with canonical_binding_hash)
                                              │
                              execute_canonical_bound_mock_action()
                              (pre-execution binding hash verify)
                                              │
                                              ▼
                                       DemoResult (mock only)
```

---

## Capability mappings

| FP Capability | LNES-22 Capability | Risk Class | Auto-Approve |
|--------------|-------------------|------------|-------------|
| `FP.READ_FILE` | `TOOL.READ_FILE` | INFORMATIONAL | YES |
| `FP.LOG_EVENT` | `TOOL.GIT_STATUS` | INFORMATIONAL | YES |
| `FP.ECHO_INTENT` | `TOOL.WRITE_STAGED` | REVERSIBLE | YES (staging dir only) |
| `FP.SIMULATED_TRANSFER` | `TOOL.HTTP_REQUEST` | COMPENSATABLE | **NO** (always requires human approval) |

A valid FlashProve proof on `FP.SIMULATED_TRANSFER` does **not** authorize execution —
COMPENSATABLE risk class always requires human approval in auto mode. The axiom holds.

---

## Security properties

- `shell=False` enforced in all subprocess calls
- Default-deny: every code path must explicitly reach `allowed=True`
- Replay protection: SQLite `BEGIN EXCLUSIVE` — multiprocess-safe, at most one
  authorization per nonce across concurrent processes
- Pre-execution binding check: canonical 12-field hash re-derived at execution
  boundary; mismatched hash blocks execution (prevents substitution attacks)
- Engine label always present: simulated decisions never claim `REAL_LNES22`
- No production keys, real transactions, or OS commands derived from model output

---

## Repository layout

```
exergynet-flashprove/
├── README.md
├── adapter/
│   ├── flashprove_shim.py          # Main adapter
│   └── lnes22_authority_bridge.py  # LNES-22 subprocess bridge
├── policy/
│   └── allowed_commitments.json    # Sample trusted commitment registry
├── tests/
│   └── test_all.py                 # 102-test suite
├── examples/
│   └── demo_three_cases.py         # Three-case demonstration script
├── docs/                           # 23 specification and audit documents
├── upstream/                       # FlashProve build scripts and hashes
│   └── setup.sh                    # Build script (clones + compiles cp_verify)
├── generate_sha256sums.py
└── SHA256SUMS                      # Sealed digests
```

---

## License

- Adapter code (`adapter/`): Apache 2.0
- FlashProve upstream (`upstream/`): Apache 2.0 (Anthropic)
- Not affiliated with or endorsed by Anthropic

---

## Status

**Published research prototype** — public release v0.2.0 (EDT-FP-002-RC3, 2026-11-05).  
Production deployment, financial execution, and mainnet transactions are not part of this release.

> *INTELLIGENCE PROPOSES. AUTHORITY DISPOSES.*
