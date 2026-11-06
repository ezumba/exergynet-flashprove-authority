# EDT-FP-001 — Independent Codex Audit

**Date:** 2026-11-05  
**Status:** PENDING — independent execution not yet completed

---

## Audit Scope (per §XVI)

The independent reviewer (Codex) is requested to review:

1. FlashProve verifier invocation — structured args, no shell, correct argument order
2. Commitment-source integrity — registry pattern vs. proof-sender self-attestation
3. Input/output proof binding — digest binding fields in evidence record
4. Parser correctness — dual check (exit code + verdict line) for acceptance
5. Process isolation — `shell=False`, `preexec_fn` resource limits
6. Fail-closed behavior — missing file, timeout, error all → `accepted=False`
7. LNES-22 authority separation — proof verdict does not influence authority decision path
8. Signature handling — Ed25519 not used in prototype (correctly noted as not applicable in absence of production LNES-22 wiring)
9. Mock-action containment — `ALWAYS_DENIED_CAPABILITIES` coverage
10. Confidentiality boundaries — no production keys, no real credentials in any file
11. Public claims and source attribution — disclaimers in README draft, UPSTREAM_PROVENANCE.md

---

## Audit Artifact Hashes (to be populated by auditor)

| File | SHA-256 |
|---|---|
| `adapter/flashprove_shim.py` | _pending_ |
| `tests/test_all.py` | _pending_ |
| `policy/allowed_commitments.json` | _pending_ |
| `examples/demo_three_cases.py` | _pending_ |
| `upstream/bin/cp_verify` | _pending_ (after build) |

---

## Audit Questions for Codex

1. Does `run_verifier()` ever invoke `cp_verify` with `shell=True`?
2. Can a proof sender bypass the `TrustedCommitmentRegistry` check?
3. Does any code path allow `accepted=True` when `exit_code != 0`?
4. Does any code path allow `accepted=True` when `last_line` is not `YES` or `WITHIN LIMITS:`?
5. Can a capability in `ALWAYS_DENIED_CAPABILITIES` be granted by any path in `evaluate_authority()`?
6. Does `execute_mock_action()` ever call `subprocess`, `os.system`, or similar with model-generated text?
7. Are any private keys, production credentials, or treasury addresses reachable from this codebase?
8. Does the README draft correctly describe the prototype limitations and affiliate disclaimers?

---

## Status

```
AUDIT_STATUS: PENDING
REASON: Independent Codex execution not yet completed.
NOTE: Per §XVI, a self-authored document titled "Codex audit" is not independent verification.
      This document will be updated when Codex independently executes and reports.
```
