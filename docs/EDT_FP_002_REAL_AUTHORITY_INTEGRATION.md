# EDT-FP-002 — Real LNES-22 Authority Integration

**Date:** 2026-11-05  
**Status:** COMPLETE — 92/92 tests PASS (WSL2 Linux, Python 3.12.3)

---

## What Was Built

### `adapter/lnes22_authority_bridge.py` (new)

Standalone subprocess bridge that:
1. Reads a JSON authority request from stdin
2. Resolves the FP.* capability to its TOOL.* equivalent
3. Calls the **real** `evaluate_tool_capability()` from `policy_gate.py` when
   `LNES22_SOURCE_PATH` is set, or falls back to `LOCAL_SIMULATION`
4. Writes a JSON decision to stdout

**Key design:** `shell=False`, structured args only, no network calls, no production keys.

### `adapter/flashprove_shim.py` additions

| Addition | Purpose |
|----------|---------|
| `CanonicalActionRequest` | 12-field canonical action request (§III) |
| `canonical_action_request_hash()` | SHA-256 of canonical JSON of all 12 fields |
| `content_replay_hash()` | SHA-256 of 10 content fields (excludes request_id, timestamp_utc) |
| `ReplayProtectionStore` | Durable JSON-file replay detection (§IV) |
| `RealAuthorityGateway` | Subprocess gateway to the bridge (§II) |
| `evaluate_authority_real()` | Full integration: principal check → replay → LNES-22 bridge |

---

## Integration Architecture

```
FlashProve Proof Evidence
         │
         ▼
 run_verifier() → VerificationResult.accepted
         │
         ▼ (proof.accepted → delegation_valid)
evaluate_authority_real(CanonicalActionRequest, VerificationResult, ReplayStore)
         │
         ├─→ principal/session validation (always-deny on empty)
         ├─→ always-denied capability check (no proof overrides)
         ├─→ ReplayProtectionStore.check_replay(content_replay_hash)
         │
         ├─→ RealAuthorityGateway.evaluate(capability_id, delegation_valid, ...)
         │          │
         │          └─→ subprocess: lnes22_authority_bridge.py
         │                   │
         │                   ├── LNES22_SOURCE_PATH set → _evaluate_real()
         │                   │       imports policy_gate.py (read-only)
         │                   │       maps FP.* → TOOL.*, calls evaluate_tool_capability()
         │                   │       returns engine="REAL_LNES22_LOCAL_DEVELOPMENT"
         │                   │
         │                   └── not set → _evaluate_local()
         │                           mirrors evaluate_tool_capability() check sequence
         │                           returns engine="LOCAL_SIMULATION"
         │
         └─→ AuthorityDecision(allowed, reason, action_id)
                  reason includes "[engine=...]" label — always visible
```

---

## Proof → Delegation Semantic

An accepted FlashProve proof is treated as the delegation evidence for capabilities
with `authority_requirements`. This creates the semantic link:

- `FP.READ_FILE` / `FP.LOG_EVENT` / `FP.ECHO_INTENT` — no authority requirements →
  LNES-22 auto-allows regardless of proof status (INFORMATIONAL/REVERSIBLE)
- `FP.SIMULATED_TRANSFER` — has `authority_requirements` ("REQUEST_EXTERNAL_CALL") →
  even with `delegation_valid=True` (accepted proof), COMPENSATABLE risk class
  means `requires_human_approval=True` → not auto-approved

This is the precise demonstration of the axiom:
**MODEL INFERENCE PROVENANCE ≠ EXECUTION AUTHORITY**

The proof shows what the model said. The authority gate independently evaluates
the capability. For sensitive operations (COMPENSATABLE/IRREVERSIBLE), human
approval is always required regardless of proof status.

---

## Labeling Guarantees

| Condition | `engine` label |
|-----------|---------------|
| Real LNES-22 source available | `REAL_LNES22_LOCAL_DEVELOPMENT` |
| Simulation mode | `LOCAL_SIMULATION` |
| Import failed | `LOCAL_SIMULATION_IMPORT_ERROR` |
| Bridge subprocess failed | `BRIDGE_ERROR` |
| Bridge binary not present | `BRIDGE_UNAVAILABLE` |

The `evaluate_authority_real()` function embeds the engine label in the
`AuthorityDecision.reason` as `[engine=<label>]`, ensuring every audit record
shows whether a real or simulated decision was made.

---

## Constraints Respected

- `policy_gate.py` and `capability_registry.py` NOT modified (read-only import)
- No production authorization services called
- No production signing keys accessed
- All subprocess calls use `shell=False`
- Simulated decision MUST NOT be labeled as actual LNES-22 authorization —
  `LOCAL_SIMULATION` label enforced and tested (see `TestEngineLabelAuthentication`)
- No real financial transfers or OS commands derived from model output
