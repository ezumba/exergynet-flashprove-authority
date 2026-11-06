# EDT-FP-002 — Capability Mapping Reconciliation

**Date:** 2026-11-05  
**Status:** COMPLETE — all four FP.* → TOOL.* mappings reconciled  
**Directive item:** 1 (final-RC verification)

---

## Summary

All four FlashProve-to-LNES-22 capability mappings have been reconciled against
the real `capability_registry.py` entries, their risk classes, protected parameters,
authority requirements, and actual execution semantics in `execute_canonical_bound_mock_action`.

**Key assertion:** Neither `FP.ECHO_INTENT` nor `FP.SIMULATED_TRANSFER` can acquire
filesystem-write or network-execution authority through the demonstration bridge.

---

## Mapping Table

| FP Cap | LNES-22 Cap | Risk Class | Resource Scope (LNES-22) | Auto-Approve Eligible | Authority Requirements |
|--------|-------------|------------|--------------------------|----------------------|----------------------|
| FP.READ_FILE | TOOL.READ_FILE | INFORMATIONAL | workspace filesystem (read-only) | YES | none |
| FP.LOG_EVENT | TOOL.GIT_STATUS | INFORMATIONAL | local git repository (read-only) | YES | none |
| FP.ECHO_INTENT | TOOL.WRITE_STAGED | REVERSIBLE | workspace .staging/ directory | YES | none |
| FP.SIMULATED_TRANSFER | TOOL.HTTP_REQUEST | COMPENSATABLE | arbitrary external network endpoint | **NO** | REQUEST_EXTERNAL_CALL |

---

## Detailed Reconciliation

### FP.READ_FILE → TOOL.READ_FILE (INFORMATIONAL)

**Risk class:** INFORMATIONAL — no material external state mutation.  
**resource_scope:** `"workspace filesystem (read-only)"` (LNES-22 registry).  
**authority_requirements:** none.  
**Auto-approve eligible:** YES (INFORMATIONAL ∈ AUTO_EVALUATION_ELIGIBLE).  
**Protected parameters:** none.

**Can acquire filesystem-write authority?** No.  
- Risk class is INFORMATIONAL (read-only scope).
- No authority_requirements gates.
- Execution outcome: `"MOCK_READ: simulated file content returned"` — no write.

---

### FP.LOG_EVENT → TOOL.GIT_STATUS (INFORMATIONAL)

**Risk class:** INFORMATIONAL — read-only git status.  
**resource_scope:** `"local git repository (read-only)"` (LNES-22 registry).  
**authority_requirements:** none.  
**Auto-approve eligible:** YES.  
**Protected parameters:** none.

**Can acquire any write authority?** No.  
- INFORMATIONAL, read-only resource scope.
- Execution outcome: `"MOCK_LOG: event appended to local audit log"` — appends to local
  evidence store JSON only, not to the git repository.

**Note on mapping:** `FP.LOG_EVENT` maps to `TOOL.GIT_STATUS` (git status read) rather
than a git-write tool. This is the correct conservative mapping: the demo simulates
intent logging using the most benign available LNES-22 tool.

---

### FP.ECHO_INTENT → TOOL.WRITE_STAGED (REVERSIBLE) — Primary Authority Concern

**Risk class:** REVERSIBLE — external state can reliably return to the previous state.  
**resource_scope (LNES-22):** `"workspace .staging/ directory"` — only the staging
area, not arbitrary filesystem paths.  
**authority_requirements:** none.  
**Auto-approve eligible:** YES (REVERSIBLE ∈ AUTO_EVALUATION_ELIGIBLE).  
**Protected parameters (LNES-22):** `("path",)` — the staged file path.  
**Protected parameters (FP.ECHO_INTENT):** `["intent_text"]` — the recorded intent text.

**Can acquire filesystem-write authority?**

**Layer 1 — Policy:** `TOOL.WRITE_STAGED` is REVERSIBLE and has no authority_requirements.
In auto mode, `evaluate_tool_capability()` returns `allowed=True` when:
- `protected_model_generated_params` is empty (caller certifies no model-generated params)
- `delegation_valid` is not required (no authority_requirements)
- `replay_detected` is False

The scope is explicitly limited to `workspace .staging/` — not production filesystem,
not arbitrary paths.

**Layer 2 — Execution:** `execute_canonical_bound_mock_action()` maps
`FP.ECHO_INTENT` to:
```
"MOCK_ECHO: agent intent recorded (evidence store; no filesystem write)"
```
This writes only to the `LocalEvidenceStore` (a JSON file in a local temp directory).
There is no code path from bridge authorization to actual `.staging/` or filesystem
modification — the mock execution layer enforces this boundary absolutely.

**Verification:** Test `test_echo_intent_cannot_acquire_filesystem_write_authority`
confirms the execution outcome contains `"no filesystem write"`.

---

### FP.SIMULATED_TRANSFER → TOOL.HTTP_REQUEST (COMPENSATABLE) — Primary Network Concern

**Risk class:** COMPENSATABLE — cannot be reversed exactly, but a compensating
operation exists.  
**resource_scope (LNES-22):** `"arbitrary external network endpoint"`.  
**authority_requirements:** `("REQUEST_EXTERNAL_CALL",)`.  
**Auto-approve eligible:** **NO** — COMPENSATABLE ∉ AUTO_EVALUATION_ELIGIBLE.  
**Protected parameters (LNES-22):** `("url",)`.  
**Protected parameters (FP.SIMULATED_TRANSFER):** `["amount", "destination"]`.

**Can acquire network-execution authority?**

**Layer 1 — Policy:** COMPENSATABLE risk class → `policy_gate.evaluate_tool_capability()`
always returns:
```
allowed = False
requires_human_approval = True
```
This is enforced by LNES-22 regardless of:
- Whether `delegation_valid` is True
- Whether `protected_model_generated_params` is empty
- Whether `replay_detected` is False

The risk-class check fires AFTER delegation and protected-params checks. For COMPENSATABLE
capabilities, the check sequence in `policy_gate.py` guarantees the auto-evaluation path
is unreachable. `FP.SIMULATED_TRANSFER` cannot be auto-approved by any combination of
valid proof + delegation in the current architecture.

**Layer 2 — Execution:** Even in a hypothetical scenario where the authority gateway
returned `allowed=True` (e.g., during isolated testing), `execute_canonical_bound_mock_action()`
maps `FP.SIMULATED_TRANSFER` to:
```
"MOCK_TRANSFER: simulated transfer intent recorded (no funds; no network call)"
```
No `requests.get()`, `urllib`, `subprocess`, or any network I/O is issued. The function
writes only to `LocalEvidenceStore`.

**Verification:** Test `test_simulated_transfer_cannot_acquire_network_execution_authority`
verifies both layer 1 (DENY from real bridge) and layer 2 (mock outcome contains
`"no network call"`).

---

## Two-Layer Authority Barrier Summary

```
FP Capability Request
        │
        ▼
  LNES-22 Bridge (policy layer)
  ┌─────────────────────────────────────┐
  │  FP.ECHO_INTENT → TOOL.WRITE_STAGED │  REVERSIBLE → auto-eligible, staging/ only
  │  FP.SIMULATED_TRANSFER → TOOL.HTTP  │  COMPENSATABLE → ALWAYS DENY in auto mode
  └─────────────────────────────────────┘
        │ allowed=True (only for INFO/REVERSIBLE with valid nonce)
        ▼
  execute_canonical_bound_mock_action() (execution layer)
  ┌──────────────────────────────────────────────────────┐
  │  Pre-execution binding check (canonical hash verify)  │
  │  FP.ECHO_INTENT  → "MOCK_ECHO: ... no filesystem write" │
  │  FP.SIMULATED_TRANSFER → "MOCK_TRANSFER: ... no network call" │
  │  All outcomes write ONLY to LocalEvidenceStore (JSON) │
  └──────────────────────────────────────────────────────┘
```

**Neither capability can acquire filesystem-write or network-execution authority.**
The axiom holds at both layers: `INTELLIGENCE PROPOSES. AUTHORITY DISPOSES.`
