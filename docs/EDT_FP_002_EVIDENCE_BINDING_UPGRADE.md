# EDT-FP-002 — Evidence Binding Upgrade (12-Field Canonical ActionRequest)

**Date:** 2026-11-05  
**Status:** COMPLETE — 13/13 binding tests PASS

---

## Overview

EDT-FP-001 bound evidence across four SHA-256 digests (request, output_token,
proof, verifier). EDT-FP-002 upgrades to a 12-field `CanonicalActionRequest`
whose SHA-256 canonical hash binds the entire authorization context in one
independently-verifiable record.

---

## `CanonicalActionRequest` — 12 Fields

| # | Field | Type | Binds |
|---|-------|------|-------|
| 1 | `request_id` | UUID4 | Unique per request |
| 2 | `session_id` | str | Session scope |
| 3 | `principal_id` | str | Identity making the request |
| 4 | `capability_id` | str | What is being requested (e.g. "FP.ECHO_INTENT") |
| 5 | `capability_hash` | 64-hex | SHA-256 of capability definition (content-addressed) |
| 6 | `commitment_id` | 64-hex | FlashProve commitment ID from trusted registry |
| 7 | `request_digest` | 64-hex | SHA-256 of .req file |
| 8 | `output_token_digest` | 64-hex | SHA-256 of .y file |
| 9 | `proof_digest` | 64-hex | SHA-256 of .proof file |
| 10 | `verifier_digest` | 64-hex | SHA-256 of cp_verify binary |
| 11 | `timestamp_utc` | ISO 8601 | When the request was made |
| 12 | `target_environment` | str | Scope limiter (e.g. "LOCAL_SANDBOX") |

---

## Canonical Binding Hash

```python
def canonical_action_request_hash(req: CanonicalActionRequest) -> str:
    fields = {all 12 field names and values, sorted}
    canon = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
```

**Substitution invalidation:** Altering ANY of the 12 fields produces a
different `canonical_binding_hash`. Verified by 12 individual tests
(`TestCanonicalBindingHashSubstitution`), all PASS.

---

## Content Replay Hash (10-Field Subset)

The `content_replay_hash` excludes `request_id` and `timestamp_utc` from the
hash. Two requests with identical content but different IDs or timestamps
produce the same `content_replay_hash`.

This enables replay detection across time:
- Legitimate new request: same capability + same proof → same content hash → REPLAY DETECTED
- Different session or capability: different content hash → not a replay

```python
def content_replay_hash(req: CanonicalActionRequest) -> str:
    fields = {10 content fields, excluding request_id and timestamp_utc}
    canon = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
```

---

## Canonical JSON Formula

Identical to LNES-22's `capability_hash()` and `lnes22-canonical-json.ts`:
- Sorted keys (all levels)
- No whitespace (`separators=(",", ":")`)
- `ensure_ascii=False` (non-ASCII characters not escaped)

This ensures canonical JSON produced by Python and by the TypeScript side
are byte-identical for the same content.

---

## Substitution Test Results

```
TestCanonicalBindingHashSubstitution::test_canonical_hash_is_deterministic        PASS
TestCanonicalBindingHashSubstitution::test_altering_session_id_changes_hash        PASS
TestCanonicalBindingHashSubstitution::test_altering_principal_id_changes_hash      PASS
TestCanonicalBindingHashSubstitution::test_altering_capability_id_changes_hash     PASS
TestCanonicalBindingHashSubstitution::test_altering_capability_hash_changes_hash   PASS
TestCanonicalBindingHashSubstitution::test_altering_commitment_id_changes_hash     PASS
TestCanonicalBindingHashSubstitution::test_altering_request_digest_changes_hash    PASS
TestCanonicalBindingHashSubstitution::test_altering_output_token_digest_changes_hash PASS
TestCanonicalBindingHashSubstitution::test_altering_proof_digest_changes_hash      PASS
TestCanonicalBindingHashSubstitution::test_altering_verifier_digest_changes_hash   PASS
TestCanonicalBindingHashSubstitution::test_altering_target_environment_changes_hash PASS
TestCanonicalBindingHashSubstitution::test_altering_timestamp_changes_hash         PASS
TestCanonicalBindingHashSubstitution::test_altering_request_id_changes_canonical_hash PASS
```

**Result: 13/13 PASS**
