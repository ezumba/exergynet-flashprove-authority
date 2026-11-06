# EDT-FP-001 — Authority Demonstration

**Date:** 2026-11-05  
**Status:** Design complete; execution requires built verifier (Route 1)

---

## Overview

Three required demonstration cases per §X of the directive.

```
CASE A:  VERIFIED  +  AUTHORIZED       →  PROOF_ACCEPTED / AUTHORITY_GRANTED / MOCK_ACTION_EXECUTED
CASE B:  VERIFIED  +  UNAUTHORIZED     →  PROOF_ACCEPTED / AUTHORITY_DENIED  / ACTION_NOT_EXECUTED
CASE C:  INVALID PROOF + PROOF-REQD    →  PROOF_REJECTED / PROOF_REQUIRED_GATE_DENIED / ACTION_NOT_EXECUTED
```

---

## CASE A: Verified + Authorized

**Proof input:** Reference FlashProve fixture (`examples/accepted-proof/`)  
**Commitment:** `79a5a2bc7a469b40df73dedf40abeb740671e8ae8077738bd3743897aeb22183` (from pinned registry)  
**Capability:** `MOCK.ECHO_INTENT` (in `AUTO_EVAL_CAPABILITIES`; not in `PROOF_REQUIRED_CAPABILITIES`)  
**Expected cp_verify output:** exit 0, last line `YES`  

**Authority path:**
1. `TrustedCommitmentRegistry` → commitment trusted ✓
2. `run_verifier()` → `VerificationResult(accepted=True, exit_code=0, last_line="YES")`
3. `evaluate_authority()` → `MOCK.ECHO_INTENT` in `AUTO_EVAL_CAPABILITIES`, not in `ALWAYS_DENIED`, principal and session non-empty → `PolicyDecision(allowed=True, ...)`
4. `execute_mock_action()` → writes audit record, returns `"MOCK_ECHO: agent intent recorded"`

**Expected outputs:**
```
PROOF_ACCEPTED
AUTHORITY_GRANTED
MOCK_ACTION_EXECUTED
```

**What is NOT executed:** No real shell command. No real network call. No real USDC transfer.

---

## CASE B: Verified + Unauthorized

**Proof input:** Same reference fixture as Case A  
**Commitment:** Same (trusted)  
**Capability:** `SETTLEMENT.REAL` (in `ALWAYS_DENIED_CAPABILITIES`)  
**Expected cp_verify output:** exit 0, last line `YES` (proof itself is valid)  

**Authority path:**
1. `TrustedCommitmentRegistry` → trusted ✓
2. `run_verifier()` → `VerificationResult(accepted=True, exit_code=0, last_line="YES")`
3. `evaluate_authority()` → `SETTLEMENT.REAL` in `ALWAYS_DENIED_CAPABILITIES` → `PolicyDecision(allowed=False, reason="capability 'SETTLEMENT.REAL' is unconditionally denied...")`
4. `execute_mock_action()` → no action; returns `AuthorityDecision.allowed=False`

**Expected outputs:**
```
PROOF_ACCEPTED
AUTHORITY_DENIED
ACTION_NOT_EXECUTED
```

**Key principle demonstrated:** A valid inference proof does not grant execution authority. The authority decision is computed independently.

---

## CASE C: Invalid Proof + Proof-Required Gate

**Proof input:** Reference fixture with single byte flipped at offset 256 (`proof_bytes[256] ^= 0xFF`)  
**Commitment:** Same (trusted)  
**Capability:** `MOCK.SIMULATED_TRANSFER` (in `PROOF_REQUIRED_CAPABILITIES`)  

**Authority path:**
1. `TrustedCommitmentRegistry` → trusted ✓
2. `run_verifier()` → exit 1, last line `NO: <name>` → `VerificationResult(accepted=False, ...)`
3. `evaluate_authority()` → `MOCK.SIMULATED_TRANSFER` in `PROOF_REQUIRED_CAPABILITIES` and `verification.accepted=False` → `PolicyDecision(allowed=False, reason="capability requires PROOF_ACCEPTED but...")`
4. `execute_mock_action()` → no action

**Expected outputs:**
```
PROOF_REJECTED
PROOF_REQUIRED_GATE_DENIED
ACTION_NOT_EXECUTED
```

**Key principle demonstrated:** No circumstance may allow invalid proof evidence to satisfy a proof-required policy.

---

## Execution

```bash
# From workspace root (exergynet-flashprove/)
# Prerequisite: upstream/setup.sh has been run in WSL2

# Run three-case demo
python examples/demo_three_cases.py

# Run full test suite  
python -m pytest tests/test_all.py -v
```

---

## Execution Firewall (§XI)

All demonstrations use simulated consequences only.

| Permitted | Prohibited |
|---|---|
| Mock filesystem action (audit log write) | Real treasury transaction |
| Mock command intent (echo to audit log) | Production API invocation with privileged credential |
| Mock USDC transfer intent (string in log) | Actual blockchain transfer |
| Local audit-log generation | Real arbitrary shell execution from model output |
| Local evidence record write | Production LNES-22 policy change |
| | Writing to a live Omega Carrier tenant |
| | Production settlement receipt creation |

---

## Offline Capability

The demonstration runs without network connectivity after:
1. `git clone` of upstream (one-time)
2. `verifier/build.sh` (one-time)
3. `pip install pytest` (one-time, test runner only)

No network calls are made during proof verification or authority evaluation.
