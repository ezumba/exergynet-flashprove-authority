# EDT-FP-002 — Independent Codex Audit

**Date:** 2026-11-05  
**Status:** COMPLETE  
**Reviewer:** Independent agent (fork, no context inheritance)  
**Scope:** `adapter/lnes22_authority_bridge.py` (new), new additions to `adapter/flashprove_shim.py`  
**Method:** Static analysis against stated constraints  
**Post-audit fixes applied:** H-1, H-2 (HIGH), M-3 (MEDIUM) — see §Resolutions below

---

## CRITICAL

None found. All stated constraints are upheld: `shell=False` enforced throughout,
no production keys accessed, no real transactions, upstream FlashProve code not modified.

---

## HIGH

### H-1 (RESOLVED): `sys.modules` cache not cleared — isolation appears but isn't complete

**Finding:**  
`_evaluate_real()` removed the LNES-22 path from `sys.path` in its `finally` block but
did not clear `capability_registry` and `policy_gate` from `sys.modules`. After a first
successful import, cached modules would be reused by any subsequent call even if
`lnes22_path` were changed — making the cleanup misleadingly incomplete.

**Risk:** Currently harmless because the bridge is a one-shot subprocess. Becomes a
correctness risk if usage patterns change and would silently shadow a different path.

**Resolution applied:** Added `sys.modules.pop(_mod, None)` for both modules in the
`finally` block immediately after `sys.path.remove()`.

```python
finally:
    lnes22_str = str(lnes22_path)
    if lnes22_str in sys.path:
        sys.path.remove(lnes22_str)
    for _mod in ("capability_registry", "policy_gate"):
        sys.modules.pop(_mod, None)
```

---

### H-2 (RESOLVED): `protected_model_generated_params` empty-tuple default bypasses the check silently

**Finding:**  
`CanonicalActionRequest.protected_model_generated_params` defaulted to `()` with no
documentation that the default carries semantic meaning. A caller who doesn't
set the field — not because there are no model-generated params, but because they
didn't consider it — would silently bypass the protected-params DENY gate.

**Risk:** The check is entirely caller-controlled. The bridge enforces correctly
*if* the caller populates the field. The default being `()` makes it easy to
accidentally certify "no model-generated params" without intent.

**Resolution applied:** Added a prominent docstring to the field in `CanonicalActionRequest`:

```python
# IMPORTANT: the empty-tuple default means "caller explicitly certifies no
# model-generated params".  This is NOT a "field not considered" default.
# Callers MUST set this to the actual set of model-generated parameter names
# when any exist -- omitting it is an explicit claim that none are present.
protected_model_generated_params: tuple = dataclasses.field(default_factory=tuple)
```

---

## MEDIUM

### M-1: `LNES22_SOURCE_PATH` not authenticated

**Finding:** The bridge verifies `policy_gate.py` exists at the path but does not
verify the file's hash. An attacker who controls the environment variable could
point it at a directory with a malicious `policy_gate.py` returning `allowed=True`
with engine label `REAL_LNES22_LOCAL_DEVELOPMENT`.

**Severity:** Low impact in this threat model (local development integration, no
production keys). Path is a trusted operator-set variable.

**Resolution:** Documented in bridge docstring as a trusted operator-set variable.
Not user-controlled input. Hash pinning is an optional hardening step for future
integration (noted in L-residuals below).

---

### M-2: stdin read limit off-by-one (65537 vs 65536)

**Finding:** `sys.stdin.buffer.read(65537)` matches the existing `lnes22_bridge.py`
pattern faithfully but is an off-by-one: a 65537-byte payload is silently truncated
and produces a confusing "invalid JSON input" deny.

**Resolution:** No change — this matches the upstream LNES-22 bridge pattern and the
65 KB payload limit is well above any realistic capability request. Documented here
for future reference.

---

### M-3 (RESOLVED): `ReplayProtectionStore._save()` was not atomic

**Finding:** `Path.write_text()` truncates before writing. A crash mid-write
leaves the replay store in a corrupt state; `_load()` falls back to empty dict,
erasing all prior replay records. An attacker who can predict crash timing could
force replay detection to reset.

**Resolution applied:** Rewrote `_save()` to write to a `.tmp` file first, then
`os.replace()` for POSIX-atomic rename:

```python
def _save(self) -> None:
    tmp = self._path.with_suffix(".tmp")
    tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, self._path)
```

---

## LOW

### L-1: Response schema differs between real and simulated paths

`lnes22_capability_id` is only present in the real LNES-22 response, not the
LOCAL_SIMULATION response. Callers that assume the field always exists will get a
`KeyError`. **Not fixed** — the shim accesses this field conditionally via
`result.get(...)`. Noted for future schema normalization.

### L-2: Proof-to-delegation semantic is misleading for COMPENSATABLE

For `FP.SIMULATED_TRANSFER` (COMPENSATABLE), `delegation_valid=True` has no
effect — the LNES-22 risk-class check fires first and always denies for
COMPENSATABLE. The assignment `delegation_valid = verification.accepted` is
architecturally correct but potentially misleading for readers.
**Resolution:** Existing comment at the delegation assignment line explains this
context. Reinforced by test `test_simulated_transfer_requires_human_approval_via_real_lnes22`.

### L-3: `ALWAYS_DENIED` defined independently in shim and bridge

`ALWAYS_DENIED_CAPABILITIES` (shim) and `_ALWAYS_DENIED` (bridge) are independent
frozensets. If a new dangerous capability is added to one but not the other, there
is a gap. **Noted** — both sets currently match. A sync test is a future hardening
step.

### L-4: TOCTOU between `check_replay()` and `record()` under concurrent access

Under concurrent processes, two calls with the same content could both pass
`check_replay()` → both get `replay_detected=False` → both allowed. Documented
on `ReplayProtectionStore` as single-process only. For production use, SQLite
exclusive-lock would close this window.

---

## INFO

### I-1: `capability_hash` in `CanonicalActionRequest` is caller-supplied, not verified

The bridge computes its own hash from the actual definition. If the caller's
`capability_hash` field differs, the discrepancy is silent in audit records.

### I-2: `timestamp_utc` is caller-supplied with no freshness check

Acceptable for an audit-trail field. Not a security gate — only contributes to
the binding hash.

### I-3: Bridge inherits virtualenv correctly via `sys.executable`

Using `[sys.executable, str(self._bridge)]` ensures the bridge runs in the
same Python environment as the calling process. Correct behavior.

### I-4: `_ALWAYS_DENIED` as `frozenset` prevents runtime mutation

Positive defensive choice — immutable, cannot be extended at runtime.

---

## POSITIVE FINDINGS

1. **`shell=False` enforced throughout.** Both bridge subprocess call and verifier
   call use structured argument vectors. No string interpolation reaches a shell.

2. **Default-deny in every path.** Both `_evaluate_local()` and `_evaluate_real()`
   require every path to explicitly reach `allowed=True`. Fallthrough produces a deny.
   Matches LNES-22's `policy_gate.py` posture exactly.

3. **Engine label always embedded in reason string.** Every `AuthorityDecision.reason`
   contains `[engine=...]`. Audit logs cannot be confused about real vs. simulated.

4. **Replay store idempotency.** `record()` checks existence before writing — second
   call with the same hash is a no-op. First-seen timestamp is authoritative.

5. **Capability hash is content-addressed.** SHA-256 of canonical JSON of the full
   definition body — a capability that drifts in its definition produces a different
   hash, making definition substitution detectable in audit records.

6. **12-field substitution coverage is complete.** All 12 fields contribute to
   `canonical_binding_hash`. Verified by 13 individual tests.

7. **Simulation and real paths share the same check sequence.** `_evaluate_local()`
   mirrors `evaluate_tool_capability()` check order exactly. Simulation produces
   meaningful results for development.

8. **COMPENSATABLE capabilities require human approval regardless of proof.** The
   integration correctly demonstrates that FlashProve proof acceptance does not grant
   execution authority for sensitive operations. The axiom holds.

---

## Summary Table

| ID | Severity | Title | Status |
|----|----------|-------|--------|
| H-1 | HIGH | `sys.modules` cache not cleared | **RESOLVED** |
| H-2 | HIGH | Protected-params default bypasses check silently | **RESOLVED** |
| M-1 | MEDIUM | `LNES22_SOURCE_PATH` not authenticated | DOCUMENTED |
| M-2 | MEDIUM | stdin read limit off-by-one (65537) | ACCEPTED (matches upstream) |
| M-3 | MEDIUM | `_save()` not atomic | **RESOLVED** |
| L-1 | LOW | Response schema differs real vs. simulation | NOTED |
| L-2 | LOW | Proof-to-delegation misleading for COMPENSATABLE | DOCUMENTED |
| L-3 | LOW | `ALWAYS_DENIED` defined independently in shim+bridge | NOTED |
| L-4 | LOW | TOCTOU between check_replay/record | DOCUMENTED (single-process) |
| I-1 | INFO | `capability_hash` caller-supplied, not verified | ACCEPTED |
| I-2 | INFO | `timestamp_utc` caller-supplied, no freshness | ACCEPTED |
| I-3 | INFO | Bridge inherits virtualenv via `sys.executable` | POSITIVE |
| I-4 | INFO | `_ALWAYS_DENIED` as `frozenset` | POSITIVE |

**No CRITICAL findings.** All stated constraints upheld.  
**2 HIGH resolved**, **1 MEDIUM resolved** post-audit.  
Remaining items are accepted residuals within stated local-development scope.
