# EDT-FP-001 — Valid and Invalid Proof Tests

**Date:** 2026-11-05  
**Status:** COMPLETE — all 45 tests PASS (WSL2 Linux, Python 3.12.3)  
**Test implementation:** `tests/test_all.py`

---

## Positive Cases

### P-1: Reference proof accepted

| Field | Value |
|---|---|
| Test | `TestAcceptedProof.test_reference_proof_accepted` |
| Commitment ID | `79a5a2bc7a469b40df73dedf40abeb740671e8ae8077738bd3743897aeb22183` (pinned registry) |
| Config | `examples/accepted-proof/config` |
| IVK | `examples/accepted-proof/ivk` |
| Request | `examples/accepted-proof/example.req` |
| Output tokens | `examples/accepted-proof/example.y` |
| Proof | `examples/accepted-proof/example.proof` |
| Expected exit | 0 |
| Expected last line | `YES` |
| **Result** | **PASS** — exit=0, last_line=YES, `result-v1 status=0 claim=exact-match bits=128` |

### P-2: Both exit code and verdict line required

| Field | Value |
|---|---|
| Test | `TestAcceptedProof.test_acceptance_requires_both_exit_code_and_verdict` |
| Purpose | Confirm adapter does not equate exit 0 alone with acceptance |
| Method | Synthetic result: exit_code=0 but last_line="PLAN ONLY: …" |
| **Result** | **PASS** — `accepted=False` confirmed |

---

## Negative Cases (Mission B — 10 required categories)

### N-1: Altered proof bytes

| Field | Value |
|---|---|
| Test | `TestRejectedProof.test_altered_proof_rejected` |
| Method | Flip byte at offset 256 of `example.proof` (xor 0xFF) |
| **Result** | **PASS** — exit=1, last_line=`NO: proof-refused`, `accepted=False` |

### N-2: Incorrect commitment ID

| Field | Value |
|---|---|
| Test | `TestRejectedProof.test_incorrect_commitment_id_rejected` |
| Method | Pass `"0" * 64` as commitment ID |
| **Result** | **PASS** — exit=1 or 14, `accepted=False` |

### N-3: Incorrect request file

| Field | Value |
|---|---|
| Test | `TestRejectedProof.test_incorrect_request_file_rejected` |
| Method | Replace `example.req` with zero-padded bytes of same size |
| **Result** | **PASS** — `accepted=False` |

### N-4: Incorrect output token file

| Field | Value |
|---|---|
| Test | `TestRejectedProof.test_incorrect_output_token_file_rejected` |
| Method | Replace `example.y` with single zero word (4 bytes) |
| **Result** | **PASS** — `accepted=False` |

### N-5: Missing proof file

| Field | Value |
|---|---|
| Test | `TestRejectedProof.test_missing_proof_file` |
| Method | Reference nonexistent path `absent.proof` |
| **Result** | **PASS** — shim returns `accepted=False, error_detail contains "missing"` before invoking verifier |

### N-6: Malformed invocation (bad path)

| Field | Value |
|---|---|
| Test | `TestRejectedProof.test_malformed_invocation_bad_path` |
| Method | Point input path at a directory (config_dir used as proof_file) — triggers early rejection |
| **Result** | **PASS** — `accepted=False` |

### N-7: NOT CHECKED (exit 5)

| Field | Value |
|---|---|
| Test | `TestNonVerificationStatus.test_not_checked_exit_5_not_accepted` |
| Method | Synthetic VerificationResult with exit_code=5 |
| **Result** | **PASS** — `accepted=False` |

### N-8: NOT-A-VERIFICATION (exit 14)

| Field | Value |
|---|---|
| Test | `TestNonVerificationStatus.test_not_a_verification_exit_14_not_accepted` |
| Method | Synthetic VerificationResult with exit_code=14, last_line="NOT-A-VERIFICATION" |
| **Result** | **PASS** — `accepted=False` |

### N-9: Verifier subprocess timeout

| Field | Value |
|---|---|
| Test | `TestTimeout.test_timeout_produces_non_accepted_result` |
| Method | Synthetic VerificationResult with exit_code=-9, last_line="TIMEOUT" |
| **Result** | **PASS** — `accepted=False` |

### N-10: Verifier process failure / binary missing

| Field | Value |
|---|---|
| Test | `TestVerifierInvocation.test_missing_verifier_binary` |
| Method | Reference nonexistent binary path |
| **Result** | **PASS** — `accepted=False, error_detail contains "not found"` |

---

## Proof-Required Gate (Mission E §X Case C)

### R-1: Proof-required capability denied without valid proof

| Field | Value |
|---|---|
| Test | `TestAuthorityServiceFailure.test_proof_required_cap_denied_without_proof` |
| Method | `MOCK.SIMULATED_TRANSFER` + synthetic `accepted=False` |
| **Result** | **PASS** — `allowed=False, reason contains "PROOF_ACCEPTED"` |

### R-2: Altered proof rejected; proof-required gate blocks action

| Field | Value |
|---|---|
| Test | `TestThreeCaseDemo.test_case_c_invalid_proof_proof_required_gate` |
| Method | Synthetic altered proof + `MOCK.SIMULATED_TRANSFER` |
| **Result** | **PASS** — `PROOF_REJECTED / AUTHORITY_DENIED / ACTION_NOT_EXECUTED` |

### R-3: Wrong output token file rejected (output mismatch)

| Field | Value |
|---|---|
| Test | `TestOutputMismatch.test_wrong_token_produces_rejection` |
| Method | Substitute `example.req` for `example.y` |
| **Result** | **PASS** — `accepted=False` |

---

## Rules Verified by Test Suite

| Rule | Test(s) | Result |
|---|---|---|
| Exit code 0 alone is not sufficient | `test_acceptance_requires_both_exit_code_and_verdict` | **PASS** |
| NOT CHECKED ≠ acceptance | `test_not_checked_exit_5_not_accepted` | **PASS** |
| PLAN ONLY ≠ acceptance | `test_plan_only_exit_4_not_accepted` | **PASS** |
| PART PASSED ≠ full acceptance | `test_part_passed_exit_3_not_accepted` | **PASS** |
| NOT-A-VERIFICATION ≠ acceptance | `test_not_a_verification_exit_14_not_accepted` | **PASS** |
| Timeout ≠ acceptance | `test_timeout_produces_non_accepted_result` | **PASS** |
| Altered proof rejected (real verifier) | `test_altered_proof_rejected` | **PASS** — exit=1, `NO: proof-refused` |
| Proof-required gate blocks missing proof | `test_proof_required_cap_denied_without_proof`, Case C | **PASS** |
| Proof sender cannot supply own commitment ID | `test_proof_sender_cannot_supply_own_commitment` | **PASS** |

---

## Notes

The reference proof uses a **synthetic small model with synthetic weights** — not Llama 4 Maverick, not Claude. These tests show the verifier works correctly; they say nothing about any production AI provider's models.

Case C confirmation: the byte-flipped proof was rejected by the actual `cp_verify` binary (not a mock), returning `exit=1, last_line='NO: proof-refused'`.
