# EDT-FP-001 — Test Results

**Date:** 2026-11-05  
**Status:** COMPLETE — All tests passed

---

## Final Test Results

### WSL2 Linux (Python 3.12.3, pytest 9.1.1) — Full Suite Including Verifier

```
45 passed in 9.16s
EXIT: 0
```

**All 45 tests passed.** No failures, no skips.

| Test Class | Tests | Status |
|---|---|---|
| `TestVerifierInvocation` | 4 | **PASS** |
| `TestAcceptedProof` | 2 | **PASS** |
| `TestRejectedProof` | 6 | **PASS** |
| `TestNonVerificationStatus` | 4 | **PASS** |
| `TestTimeout` | 1 | **PASS** |
| `TestInvalidArguments` | 3 | **PASS** |
| `TestOutputMismatch` | 1 | **PASS** |
| `TestEvidenceReplay` | 3 | **PASS** |
| `TestUnauthorizedOperation` | 5 | **PASS** |
| `TestAuthorityServiceFailure` | 6 | **PASS** |
| `TestCrossSessionAuthorization` | 1 | **PASS** |
| `TestActionTargetMismatch` | 1 | **PASS** |
| `TestAuditPersistence` | 2 | **PASS** |
| `TestNoFinancialSideEffects` | 2 | **PASS** |
| `TestThreeCaseDemo` | 4 | **PASS** |

**Total: 45/45 PASS**

### Windows (Python 3.13.13, pytest 9.0.3) — Non-Verifier Tests

```
32 passed, 13 skipped in 0.08s
EXIT: 0
```

Verifier-requiring tests are properly skipped on Windows (Linux ELF cannot execute). Platform guard added to `VERIFIER_AVAILABLE` check: `platform.system() == "Windows"` → skip.

---

## Three-Case Demo Results (WSL2 Execution, 2026-11-05)

```
python3 examples/demo_three_cases.py
```

| Case | Expected | Result |
|---|---|---|
| A: Verified + Authorized | PROOF_ACCEPTED / AUTHORITY_GRANTED / MOCK_ACTION_EXECUTED | **PASS** |
| B: Verified + Unauthorized | PROOF_ACCEPTED / AUTHORITY_DENIED / ACTION_NOT_EXECUTED | **PASS** |
| C: Invalid Proof + Gate | PROOF_REJECTED / AUTHORITY_DENIED / ACTION_NOT_EXECUTED | **PASS** |

**Case C detail:** Verifier returned `exit=1 last_line='NO: proof-refused'` — the real FlashProve CPU verifier rejected the byte-flipped proof. The proof-required gate then blocked the simulated transfer.

---

## Bugs Found and Fixed During Test Development

1. **`resource` module not on Windows** — Linux-only module; fixed with conditional import in `flashprove_shim.py`
2. **Authority check ordering** — `principal_id`/`session_id` checks happened after the proof-required gate; reordered to enforce identity first
3. **`or` short-circuit in test assertion** — `result.action_outcome or result.summary` bypassed summary check; fixed to check `result.summary` directly
4. **Audit record field selection** — test took `files[0]` alphabetically, could land on `mock_action_executed` record instead of `authority_decision`; fixed to search by `type` field
5. **Verifier availability on Windows** — `VERIFIER_AVAILABLE` checked only file existence; added platform check and executable test via `_verifier_runnable()`

---

## Behavioral Invariants Confirmed by Tests

1. **Commitment ID gating:** Untrusted commitment IDs blocked before invoking verifier — no subprocess, no network call. ✓
2. **Always-denied capabilities:** `EXECUTE_SHELL`, `SETTLEMENT.REAL`, `TREASURY.TRANSFER`, `BLOCKCHAIN.DEPLOY`, `NETWORK.OPEN` denied unconditionally, even with `accepted=True`. ✓
3. **Proof-required gate:** `MOCK.SIMULATED_TRANSFER` denied when `accepted=False`. ✓
4. **Exit-code-only acceptance blocked:** `exit_code=0` with `PLAN ONLY:` last line is not accepted. ✓
5. **Non-verification status values not accepted:** `NOT CHECKED`, `NOT-A-VERIFICATION`, `PLAN ONLY`, `PART PASSED` all → `accepted=False`. ✓
6. **Timeout non-accepted:** Timeout → `accepted=False`. ✓
7. **Empty principal denied:** `AuthorityRequest` with `principal_id=""` denied. ✓
8. **Empty session denied:** `AuthorityRequest` with `session_id=""` denied. ✓
9. **Unknown capability denied:** Any capability not in vocabulary denied. ✓
10. **Mock financial action contains no real funds:** `MOCK.SIMULATED_TRANSFER` outcome string "no funds moved". ✓
11. **Denied decision carries empty action_id.** ✓
12. **Reference proof genuinely accepted:** `exit=0, last_line="YES"`. ✓
13. **Altered proof genuinely rejected:** `exit=1, last_line="NO: proof-refused"`. ✓
14. **Wrong output token file rejected.** ✓
15. **Missing file rejected before verifier runs.** ✓
16. **Structured invocation (no shell=True).** ✓
