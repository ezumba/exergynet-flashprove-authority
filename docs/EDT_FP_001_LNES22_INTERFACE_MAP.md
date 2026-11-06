# EDT-FP-001 — LNES-22 Interface Map

**Date:** 2026-11-05  
**Source files read:** (all from `<private ExergyNet source tree>/vendor/runtime/`)
- `vendor/lnes22/policy_gate.py`
- `vendor/lnes22/capability_registry.py`
- `lib/lnes22_bridge.py`
- `vendor/zcode/lnes22-ed25519.ts`
- `vendor/zcode/lnes22-canonical-json.ts`

---

## 1. policy_gate.py — Canonical Interfaces

### `PolicyDecision` (dataclass)

```python
@dataclasses.dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    requires_human_approval: bool = False
```

### `evaluate()` — OTET/rebuild path

```python
def evaluate(
    *,
    verified_review: dict[str, Any],
    requested_operation: str,
    requested_target: str,
    requested_environment: str,
    triggering_otet: str,
    seen_otets: set[str] | None = None,
) -> PolicyDecision
```

**Posture:** pure function, no I/O, default-deny.  
**Allowed operations:** `{"rebuild"}`.  
**Allowed targets:** `{"portal", "proxy", "both"}`.  
**Allowed environments:** `{"staging"}` — production requires explicit human approval.

### `evaluate_tool_capability()` — Vanguard tool path

```python
def evaluate_tool_capability(
    *,
    capability: CapabilityDefinition | None,
    protected_model_generated_params: tuple[str, ...] = (),
    delegation_valid: bool | None = None,
    replay_detected: bool = False,
) -> PolicyDecision
```

**None → DENY.** Unmapped tool treated identically to unknown tool, never auto-allowed.  
**MODEL_GENERATED params → DENY** for any capability with `protected_parameters`.  
**Delegation required → DENY** if `capability.authority_requirements` non-empty and `delegation_valid is not True`.  
**AUTO_EVALUATION_ELIGIBLE:** `{INFORMATIONAL, REVERSIBLE}` only. `COMPENSATABLE`/`IRREVERSIBLE` → `requires_human_approval=True`.

---

## 2. capability_registry.py — CapabilityDefinition

```python
@dataclasses.dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str          # e.g. "TOOL.READ_FILE"
    version: str                # "0.1"
    tool_name: str              # exact key in tools.py
    description: str
    risk_class: RiskClass       # INFORMATIONAL | REVERSIBLE | COMPENSATABLE | IRREVERSIBLE
    resource_scope: str
    authority_requirements: tuple[str, ...]  # capability strings requiring delegated authority
    protected_parameters: tuple[str, ...]    # args requiring evidence-binding origin
    evidence_requirements: tuple[str, ...]  # what must be confirmed independently
    replay_policy: str          # "none" | "idempotency_required" | "single_use"
    enabled: bool = True
```

### RiskClass Axis (Reversibility — NOT Severity)

| Class | Meaning | Auto-eval eligible |
|---|---|---|
| `INFORMATIONAL` | No material external state mutation | Yes |
| `REVERSIBLE` | External state can return to prior state | Yes |
| `COMPENSATABLE` | Cannot be reversed exactly, but compensating op exists | No |
| `IRREVERSIBLE` | Cannot reliably be undone | No |

**Note:** `RiskClass` is a REVERSIBILITY axis. `safety_gates.RiskLevel` is a SEVERITY axis. They are not interchangeable.

---

## 3. capability_hash()

```python
def capability_hash(d: CapabilityDefinition) -> str:
    # SHA-256 of canonical JSON of the definition body
    # Content-addressed identity: execution can bind to immutable definition, not just an ID string
```

The adapter binds evidence records to `capability_hash()` as well as `capability_id` for immutable auditing.

---

## 4. lnes22_bridge.py — Runtime Bridge

```python
# Reads JSON from stdin, calls evaluate_tool_capability(), writes JSON to stdout
request = json.loads(sys.stdin.read(65537))
capability = resolve_by_capability_id(request['capability_id'])
decision = evaluate_tool_capability(
    capability=capability,
    delegation_valid=request.get('delegation_valid') is True,
    replay_detected=request.get('replay_detected') is True,
    protected_model_generated_params=tuple(request.get('protected_model_generated_params', [])),
)
print(json.dumps({
    'allowed': decision.allowed,
    'reason': decision.reason,
    'requires_human_approval': decision.requires_human_approval,
    'engine': 'REAL_LNES22_LOCAL_DEVELOPMENT',
    'capability_id': ...,
    'capability_hash': ...,
}))
```

---

## 5. lnes22-ed25519.ts — Ed25519 Verification

```typescript
// 12-byte SPKI/X.509 DER envelope prefix for Ed25519 (OID 1.3.101.112)
const ED25519_SPKI_PREFIX_HEX = "302a300506032b6570032100";

function verifyEd25519(message: Buffer, signatureHex: string, publicKeyHex: string): boolean
```

**Key invariant:** Raw 32-byte Ed25519 public keys (as PyNaCl exposes via `verify_key.encode()`) must be wrapped in SPKI/X.509 DER before `crypto.createPublicKey()` will accept them.

---

## 6. lnes22-canonical-json.ts — Canonical JSON

```typescript
export function canonicalJson(obj: unknown): string {
    // JSON.stringify over deep-sorted keys; no whitespace; non-ASCII unescaped
}
```

**Signing parity note:** Python's `json.dumps` escapes non-ASCII to `\uXXXX` by default; JavaScript does NOT. The canonical JSON function uses `ensure_ascii=False` parity. Both sides sort object keys. This was a previously-discovered cross-language signing mismatch.

---

## 7. ExergyNet FlashProve Adapter Mapping

### AuthorityRequest → LNES-22 Fields

| `AuthorityRequest` field | LNES-22 analogue | Notes |
|---|---|---|
| `evidence_record_id` | `otet` / record binding | Local evidence record |
| `verified_output_digest` | `protected_parameters` evidence | FlashProve output digest |
| `proposed_action` | `requested_operation` description | Human-readable intent |
| `principal_id` | principal identity | Issuer/authority identity |
| `requested_capability` | `capability_id` | Maps to `CapabilityDefinition` |
| `execution_target` | `requested_target` | What resource will be acted on |
| `resource_scope` | `resource_scope` | Capability's resource description |
| `session_id` | session binding | Anti-cross-session replay |
| `policy_version` | `REGISTRY_VERSION` | Capability vocabulary version |
| `auth_reference` | `triggering_otet` / delegation ref | OTET or delegation token |

### Authority Decision Return

| Field | Meaning |
|---|---|
| `allowed` | Whether the action may proceed |
| `reason` | Human-readable deny/allow rationale |
| `action_id` | Unique ID for this authorized action (empty if denied) |

---

## 8. What is NOT Connected (Local Harness vs. Production)

The adapter uses a **local simulation harness** (`evaluate_authority()` in `flashprove_shim.py`).  It is NOT:

- Not connected to `lnes22_bridge.py` subprocess call path
- Not connected to production `policy_gate.py` / `capability_registry.py`
- Not connected to the Ed25519 OTET signing chain
- Not connected to production replay_store

**To wire to production LNES-22:** replace `evaluate_authority()` with a subprocess call to `lnes22_bridge.py`, supply the production `vendor/lnes22/` path, and plumb the `delegation_valid` / `replay_detected` inputs from actual authority infrastructure.

The local harness mirrors the same posture (default-deny, closed vocabulary, explicit-allow paths) but is explicitly labelled `[SIMULATED_LNES22]` throughout the test suite.

---

## 9. Missing Production Interfaces

The following ExergyNet production interfaces are NOT available to this prototype without operator authorization:

1. Production signing key (Ed25519 OTET authority key) — not read, not used
2. Production replay store — simulated with `evidence_store.py` unique record IDs
3. Production capability vocabulary (21-entry live tools registry) — mirrored locally with mock capabilities
4. Production `lnes22_authority_service.py` endpoint — not called
5. Production `shadow_listener.py` / `shadow_gate.py` — not called

**None of these are required for the prototype demonstration. The separation of concerns is architecturally demonstrated regardless.**
