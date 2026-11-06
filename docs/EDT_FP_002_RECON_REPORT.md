# EDT-FP-002 — LNES-22 Source Recon Report

**Date:** 2026-11-05  
**Status:** COMPLETE — all five source files read, authoritative versions confirmed  
**Authoritative path:** `<private ExergyNet source tree>/vendor/lnes22/`

---

## Files Read

| File | Location | Purpose |
|------|----------|---------|
| `policy_gate.py` | `vendor/lnes22/` | Deterministic policy gate — both `evaluate()` and `evaluate_tool_capability()` |
| `capability_registry.py` | `vendor/lnes22/` | 21-entry static capability vocabulary, `CapabilityDefinition`, `RiskClass`, `capability_hash()` |
| `lnes22_bridge.py` | `vendor/runtime/lib/` | Existing stdin/stdout subprocess bridge for TOOL.* capabilities |
| `lnes22-ed25519.ts` | `vendor/zcode/` | Ed25519 SPKI verification (TypeScript, Node.js) |
| `lnes22-canonical-json.ts` | `vendor/zcode/` | Canonical JSON (sorted keys, no whitespace, ensure_ascii=False parity) |

---

## `evaluate_tool_capability()` — Key Findings

**Location:** `policy_gate.py` lines 172–237  
**Status in source:** `staged, NOT wired to anything live` — shadow mode only

**Function signature:**
```python
def evaluate_tool_capability(
    *,
    capability: "CapabilityDefinition | None",
    protected_model_generated_params: tuple[str, ...] = (),
    delegation_valid: bool | None = None,
    replay_detected: bool = False,
) -> PolicyDecision
```

**Check sequence (default-deny, every path must explicitly reach ALLOW):**

| Order | Check | Outcome |
|-------|-------|---------|
| 1 | `capability is None` | DENY: unmapped tool |
| 2 | `replay_detected` | DENY: replay |
| 3 | `protected_model_generated_params` non-empty | DENY: model-generated params |
| 4 | `authority_requirements` and `delegation_valid != True` | DENY + requires_human_approval |
| 5 | `risk_class not in AUTO_EVALUATION_ELIGIBLE` | DENY + requires_human_approval |
| 6 | (all passed) | ALLOW |

**Critical finding on `protected_model_generated_params`:** The check is `if protected_model_generated_params:` — ANY non-empty tuple triggers DENY, regardless of overlap with `protected_parameters`. The evidence binder (caller's responsibility) is expected to only include params that are both model-generated AND in the capability's protected list.

**Critical finding on COMPENSATABLE/IRREVERSIBLE:** These risk classes always produce `allowed=False, requires_human_approval=True` in auto-evaluation mode — there is no proof-status shortcut that bypasses this. This is by design and reinforces the core axiom.

---

## `capability_registry.py` — Key Findings

**21 entries** across 4 risk classes:

| Risk Class | Capabilities | AUTO_EVAL_ELIGIBLE |
|-----------|-------------|-------------------|
| INFORMATIONAL | READ_FILE, LIST_DIRECTORY, SEARCH_FILES, GIT_STATUS, GIT_DIFF, GIT_CLONE, BEGIN_TRANSACTION, ROLLBACK_TRANSACTION | YES |
| REVERSIBLE | WRITE_STAGED, WRITE_FILE, COMMIT_TRANSACTION, GIT_ADD, GIT_COMMIT | YES |
| COMPENSATABLE | GIT_PUSH, HTTP_REQUEST | NO (requires_human_approval=True) |
| IRREVERSIBLE | EXECUTE_SHELL, AWS, AZURE, GCLOUD, TERRAFORM, DOCKER | NO (requires_human_approval=True) |

`AUTO_EVALUATION_ELIGIBLE = {RiskClass.INFORMATIONAL, RiskClass.REVERSIBLE}`

**`capability_hash()` formula** (content-addressed identity):
```python
body = {11 canonical fields}
canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
return hashlib.sha256(canon.encode("utf-8")).hexdigest()
```

---

## FP.* → TOOL.* Capability Mapping (EDT-FP-002)

| FP.* (FlashProve sandbox) | TOOL.* (real LNES-22) | Risk Class | Auto-Eval |
|--------------------------|----------------------|-----------|----------|
| FP.READ_FILE | TOOL.READ_FILE | INFORMATIONAL | YES → ALLOW |
| FP.LOG_EVENT | TOOL.GIT_STATUS | INFORMATIONAL | YES → ALLOW |
| FP.ECHO_INTENT | TOOL.WRITE_STAGED | REVERSIBLE | YES → ALLOW |
| FP.SIMULATED_TRANSFER | TOOL.HTTP_REQUEST | COMPENSATABLE | NO → requires_human_approval |

Legacy MOCK.* aliases (backward compat): MOCK.READ_FILE → FP.READ_FILE, etc.

---

## `lnes22_bridge.py` (existing) — Key Finding

The existing bridge is a 20-line stdin/stdout bridge that already imports the
real `policy_gate.py` and `capability_registry.py`. EDT-FP-002's
`lnes22_authority_bridge.py` follows the same pattern but adds:
- FP.* vocabulary with MOCK.* aliases
- FP.* → TOOL.* capability mapping
- LOCAL_SIMULATION fallback when LNES22_SOURCE_PATH not set

---

## Canonical JSON Parity

**Python formula** (from `capability_registry.capability_hash()`):
```python
json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

**TypeScript parity** (`lnes22-canonical-json.ts`): `JSON.stringify(sortDeep(obj))` — JS leaves non-ASCII unescaped by default, so only key-ordering gap to close.

EDT-FP-002 uses the Python formula for all canonical hashing.

---

## Constraints Confirmed

- `policy_gate.py` and `capability_registry.py` are **not modified** by this integration
- Both files are imported read-only via `sys.path` manipulation in the bridge subprocess
- No production authorization services are called; no production signing keys accessed
- Decisions labeled `REAL_LNES22_LOCAL_DEVELOPMENT` (not production, not authorization)
