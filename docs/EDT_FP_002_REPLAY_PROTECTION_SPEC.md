# EDT-FP-002 — Replay Protection Specification

**Date:** 2026-11-05  
**Status:** COMPLETE — 7/7 adversarial scenarios PASS

---

## Design

### Store

**Class:** `ReplayProtectionStore` (`adapter/flashprove_shim.py`)  
**Persistence:** JSON file at `evidence_dir/replay_protection_store.json`  
**Durable:** survives process restarts (JSON file, not in-memory only)

**Key:** `content_replay_hash` (SHA-256 of 10 content fields)  
**Value:**
```json
{
  "canonical_binding_hash": "<64-hex>",
  "decision": "ALLOWED | DENIED",
  "first_seen_utc": "2026-11-05T00:00:00Z",
  "record_id": "<uuid>"
}
```

### What Counts as a Replay

A request is a replay if its `content_replay_hash` has been seen before.

The `content_replay_hash` covers 10 fields:
`session_id`, `principal_id`, `capability_id`, `capability_hash`,
`commitment_id`, `request_digest`, `output_token_digest`, `proof_digest`,
`verifier_digest`, `target_environment`

It EXCLUDES `request_id` and `timestamp_utc`. This means:
- Same content submitted again (even with a new UUID and later timestamp) → REPLAY
- Different session or different proof → different hash → NOT a replay

### Integration

`evaluate_authority_real()` checks the store before calling the LNES-22 bridge:
1. Compute `content_replay_hash(request)`
2. `replay_store.check_replay(hash)` → `replay_detected: bool`
3. Pass `replay_detected` to `RealAuthorityGateway.evaluate()`
4. LNES-22 `evaluate_tool_capability(replay_detected=True)` → DENY immediately
5. If NOT a replay: record the hash after evaluation (regardless of ALLOW/DENY)

---

## 7 Adversarial Scenarios

| # | Scenario | Test | Result |
|---|---------|------|--------|
| 1 | Exact replay after first use | `test_recorded_hash_is_a_replay` | **PASS** |
| 2 | Cross-session replay (same content, different session_id → different hash → NOT a replay) | `test_cross_session_replay_different_hash_not_detected` | **PASS** |
| 3 | Different capability → not a replay | `test_different_capability_not_a_replay` | **PASS** |
| 4 | Different request_id/timestamp → still detected as replay (same content hash) | `test_same_content_different_request_id_same_replay_hash`, `test_same_content_different_timestamp_same_replay_hash` | **PASS** |
| 5 | `replay_detected=True` in bridge → DENY even for INFORMATIONAL capability | `test_replay_detected_flag_denies_informational_capability` | **PASS** |
| 6 | `evaluate_authority_real()` detects replay on second call | `test_replay_detected_in_evaluate_authority_real` | **PASS** |
| 7 | Replay detection survives process restart (durable JSON store) | `test_replay_detection_survives_reload` | **PASS** |

---

## Notes

- Thread safety: single-process only (no file locking). Concurrent multi-process use not supported.
- `record()` is idempotent: second call with same hash is a no-op (tested: `test_record_is_idempotent`).
- Replay detection happens BEFORE the LNES-22 bridge call — if a replay is detected, the bridge is still called with `replay_detected=True`, which triggers the first check in `evaluate_tool_capability()`.
