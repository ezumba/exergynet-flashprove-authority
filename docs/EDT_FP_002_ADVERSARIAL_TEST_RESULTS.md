# EDT-FP-002 — Adversarial Test Results

**Date:** 2026-11-05  
**Status:** COMPLETE — 92/92 PASS (WSL2 Linux, Python 3.12.3, 39.13s)  
**EDT-FP-001 regression:** 45/45 PASS (unchanged)  
**EDT-FP-002 new tests:** 47/47 PASS (14 adversarial categories)

---

## Full Run

```
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
collected 92 items

[... 45 existing EDT-FP-001 tests: all PASS ...]

TestCanonicalBindingHashSubstitution::test_canonical_hash_is_deterministic        PASSED
TestCanonicalBindingHashSubstitution::test_altering_session_id_changes_hash        PASSED
TestCanonicalBindingHashSubstitution::test_altering_principal_id_changes_hash      PASSED
TestCanonicalBindingHashSubstitution::test_altering_capability_id_changes_hash     PASSED
TestCanonicalBindingHashSubstitution::test_altering_capability_hash_changes_hash   PASSED
TestCanonicalBindingHashSubstitution::test_altering_commitment_id_changes_hash     PASSED
TestCanonicalBindingHashSubstitution::test_altering_request_digest_changes_hash    PASSED
TestCanonicalBindingHashSubstitution::test_altering_output_token_digest_changes_hash PASSED
TestCanonicalBindingHashSubstitution::test_altering_proof_digest_changes_hash      PASSED
TestCanonicalBindingHashSubstitution::test_altering_verifier_digest_changes_hash   PASSED
TestCanonicalBindingHashSubstitution::test_altering_target_environment_changes_hash PASSED
TestCanonicalBindingHashSubstitution::test_altering_timestamp_changes_hash         PASSED
TestCanonicalBindingHashSubstitution::test_altering_request_id_changes_canonical_hash PASSED
TestContentReplayHashConsistency::test_same_content_different_request_id_same_replay_hash PASSED
TestContentReplayHashConsistency::test_same_content_different_timestamp_same_replay_hash  PASSED
TestContentReplayHashConsistency::test_different_session_different_replay_hash             PASSED
TestContentReplayHashConsistency::test_different_capability_different_replay_hash          PASSED
TestReplayProtectionStore::test_new_hash_not_a_replay                              PASSED
TestReplayProtectionStore::test_recorded_hash_is_a_replay                          PASSED
TestReplayProtectionStore::test_cross_session_replay_different_hash_not_detected   PASSED
TestReplayProtectionStore::test_different_capability_not_a_replay                  PASSED
TestReplayProtectionStore::test_record_is_idempotent                               PASSED
TestReplayStorePersistence::test_replay_detection_survives_reload                  PASSED
TestModelGeneratedProtectedParams::test_non_empty_params_denied_via_bridge         PASSED
TestModelGeneratedProtectedParams::test_empty_params_does_not_trigger_deny         PASSED
TestDelegationInvalidScenario::test_simulated_transfer_no_delegation_denied        PASSED
TestDelegationInvalidScenario::test_read_file_no_authority_requirements_allowed_without_delegation PASSED
TestCompensatableCapabilityBridge::test_simulated_transfer_compensatable_requires_human_approval   PASSED
TestReplayDetectedViaBridge::test_replay_detected_flag_denies_informational_capability             PASSED
TestReplayDetectedViaBridge::test_replay_detected_in_evaluate_authority_real                       PASSED
TestBridgeUnavailableFallback::test_unavailable_bridge_returns_deny_dict           PASSED
TestBridgeUnavailableFallback::test_unavailable_bridge_in_evaluate_authority_real_safe PASSED
TestEngineLabelAuthentication::test_local_simulation_engine_does_not_claim_real    PASSED
TestEngineLabelAuthentication::test_evaluate_authority_real_reason_contains_engine_label PASSED
TestEngineLabelAuthentication::test_real_lnes22_engine_label                       PASSED
TestRealLnes22RoundTrip::test_read_file_allowed_via_real_lnes22                    PASSED
TestRealLnes22RoundTrip::test_simulated_transfer_requires_human_approval_via_real_lnes22 PASSED
TestRealLnes22RoundTrip::test_lnes22_capability_hash_non_empty                     PASSED
TestMultiprocessReplayRace::test_concurrent_processes_one_wins                     PASSED
TestCanonicalBindingPreExecutionCheck::test_matching_binding_hash_allows_execution PASSED
TestCanonicalBindingPreExecutionCheck::test_mismatched_binding_hash_blocks_execution PASSED
TestCanonicalBindingPreExecutionCheck::test_empty_canonical_binding_hash_allows_execution PASSED
TestCanonicalBindingPreExecutionCheck::test_echo_intent_cannot_acquire_filesystem_write_authority PASSED
TestCanonicalBindingPreExecutionCheck::test_simulated_transfer_cannot_acquire_network_execution_authority PASSED
TestAuditRemediationRetest::test_h1_bridge_callable_twice_consistent               PASSED
TestAuditRemediationRetest::test_h2_empty_params_does_not_implicitly_bypass        PASSED
TestAuditRemediationRetest::test_m3_replay_store_uses_sqlite_atomic_check_and_record PASSED

============================= 92 passed in 39.13s ==============================
```

---

## Coverage by Adversarial Scenario

| # | Scenario | Tests | PASS |
|---|---------|-------|------|
| 1 | Replay attack via real replay_store | `test_recorded_hash_is_a_replay`, `test_replay_detected_in_evaluate_authority_real` | 2/2 |
| 2 | Cross-session replay (different session → different hash → not replay) | `test_cross_session_replay_different_hash_not_detected` | 1/1 |
| 3 | Protected-model-generated-param injection | `test_non_empty_params_denied_via_bridge`, `test_empty_params_does_not_trigger_deny` | 2/2 |
| 4 | Delegation-invalid scenario | `test_simulated_transfer_no_delegation_denied`, `test_read_file_no_authority_requirements...` | 2/2 |
| 5 | COMPENSATABLE capability via bridge | `test_simulated_transfer_compensatable_requires_human_approval` | 1/1 |
| 6 | replay_detected=True via bridge | `test_replay_detected_flag_denies_informational_capability` | 1/1 |
| 7 | Canonical binding hash — 12-field substitution | 13 substitution tests | 13/13 |
| 8 | Content replay hash excludes request_id/timestamp | 4 consistency tests | 4/4 |
| 9 | Bridge unavailable → safe fallback | `test_unavailable_bridge_returns_deny_dict`, `test_unavailable_bridge_in_evaluate_authority_real_safe` | 2/2 |
| 10 | Engine label authentication | 3 label tests | 3/3 |
| 11 | Real LNES-22 decision round-trip | 3 round-trip tests | 3/3 |
| 12 | Multiprocess replay race (8 concurrent processes, 1 winner) | `test_concurrent_processes_one_wins` | 1/1 |
| 13 | Pre-execution canonical binding check (substitution attack) | 5 binding tests | 5/5 |
| 14 | Codex audit remediation retest (H-1, H-2, M-3) | 3 retest tests | 3/3 |

**Total EDT-FP-002: 47/47 PASS**

---

## Key Findings Confirmed by Tests

1. **Proof acceptance ≠ execution authority**: `FP.SIMULATED_TRANSFER` with valid proof + delegation → still denied (COMPENSATABLE risk class requires human approval). Tests 5, 11.

2. **Any non-empty `protected_model_generated_params` → DENY**: Even a single param name triggers DENY in both real LNES-22 and local simulation. Test 3.

3. **Replay detection is content-based, not ID-based**: Same content with different request_id/timestamp still triggers replay detection. Test 8.

4. **Durable replay protection**: SQLite backend survives process restart. Test included in scenario 7.

5. **Real LNES-22 labeling**: Decisions from the real policy_gate.py are labeled `REAL_LNES22_LOCAL_DEVELOPMENT`; simulated decisions never claim `REAL_LNES22`. Test 10.

6. **12-field substitution invalidation**: Every single field change produces a different canonical_binding_hash. Test 7.

7. **Multiprocess TOCTOU protection**: SQLite `BEGIN EXCLUSIVE` ensures exactly 1 nonce winner across 8 concurrent processes. Test 12.

8. **Pre-execution substitution attack blocked**: Re-deriving the canonical hash at the execution boundary prevents an authorized hash from being applied to a different operation. Test 13.

9. **Codex HIGH findings fully remediated**: H-1 (sys.modules), H-2 (protected_model_generated_params semantic), M-3 (atomic write → SQLite) all independently retested. Test 14.
