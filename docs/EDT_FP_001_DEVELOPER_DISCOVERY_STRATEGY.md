# EDT-FP-001 — Developer Discovery Strategy

**Date:** 2026-11-05  
**Status:** DRAFT — not for publication until Trustee authorization  
**Directive section:** §XV

---

## Primary Technical Thesis

**Proving inference and authorizing execution are different security problems.**

---

## 1. GitHub Repository Description (Draft)

```
ExergyNet FlashProve Authority Adapter

An independent integration demonstrating how FlashProve's CPU verifier
(Anthropic, Apache 2.0) can be composed with ExergyNet's LNES-22
deterministic execution-authority architecture.

Demonstrates: inference provenance ≠ execution authority
```

---

## 2. Architecture Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PROOF SENDER                                 │
│  (AI provider — proves which model answered, without weights)       │
└────────────────┬────────────────────────────────────────────────────┘
                 │  proof + request + output artifact
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                EXERGYNET FLASHPROVE AUTHORITY ADAPTER               │
│                                                                     │
│  ┌─────────────────────────┐   ┌────────────────────────────────┐  │
│  │  FlashProve Layer       │   │  LNES-22 Authority Layer       │  │
│  │  ─────────────────────  │   │  ─────────────────────────     │  │
│  │  1. TrustedCommitment   │   │  1. closed capability vocab    │  │
│  │     Registry (pinned)   │   │  2. default-deny policy        │  │
│  │  2. cp_verify (CPU)     │   │  3. proof-required gate        │  │
│  │  3. exit code + verdict │   │  4. always-denied list         │  │
│  │  4. artifact digests    │   │  5. principal + session bind   │  │
│  └───────────┬─────────────┘   └───────────────┬────────────────┘  │
│              │                                  │                   │
│              │  VerificationResult              │  AuthorityDecision│
│              └──────────────┬───────────────────┘                   │
│                             │                                        │
│                     ┌───────▼────────┐                              │
│                     │ LocalEvidence  │                              │
│                     │ Store          │                              │
│                     └───────┬────────┘                              │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
                   ┌──────────▼──────────┐
                   │  Mock Action        │
                   │  (simulated only)   │
                   └─────────────────────┘

RULE: Authority decision is computed INDEPENDENTLY of proof verdict.
      PROOF_ACCEPTED does not grant AUTHORITY_GRANTED.
      Only LNES-22 governance grants authority.
```

---

## 3. Minimal Demonstration Script (excerpt)

```python
# From examples/demo_three_cases.py
# CASE A: Valid proof + authorized mock action
result = run_demo_case("CASE_A", vi, ar, registry=reg)
# → PROOF_ACCEPTED / AUTHORITY_GRANTED / MOCK_ACTION_EXECUTED

# CASE B: Valid proof + unauthorized capability
ar_b = AuthorityRequest(requested_capability="SETTLEMENT.REAL", ...)
result = run_demo_case("CASE_B", vi_b, ar_b, registry=reg)
# → PROOF_ACCEPTED / AUTHORITY_DENIED / ACTION_NOT_EXECUTED

# CASE C: Altered proof + proof-required gate
result = run_demo_case("CASE_C", vi_c_mutated, ar_c, registry=reg)
# → PROOF_REJECTED / PROOF_REQUIRED_GATE_DENIED / ACTION_NOT_EXECUTED
```

---

## 4. Three-Case Test Transcript (Expected — pending verifier build)

```
==================================================================
  CASE A: VERIFIED + AUTHORIZED
==================================================================
  PROOF_VERDICT:                PROOF_ACCEPTED
  AUTHORITY_VERDICT:            AUTHORITY_GRANTED
  ACTION_OUTCOME:               MOCK_ACTION_EXECUTED
  SUMMARY:                      MOCK_ECHO: agent intent recorded

  [PASS] CASE A — all three expected outcomes confirmed.

==================================================================
  CASE B: VERIFIED + UNAUTHORIZED
==================================================================
  PROOF_VERDICT:                PROOF_ACCEPTED
  AUTHORITY_VERDICT:            AUTHORITY_DENIED
  ACTION_OUTCOME:               ACTION_NOT_EXECUTED
  DENY_REASON:                  capability 'SETTLEMENT.REAL' is
                                unconditionally denied; no proof
                                status overrides this

  [PASS] CASE B — proof accepted but authority denied; action not executed.

==================================================================
  CASE C: INVALID PROOF + PROOF-REQUIRED GATE
==================================================================
  PROOF_VERDICT:                PROOF_REJECTED
  AUTHORITY_VERDICT:            AUTHORITY_DENIED
  ACTION_OUTCOME:               ACTION_NOT_EXECUTED
  DENY_REASON:                  capability 'MOCK.SIMULATED_TRANSFER'
                                requires PROOF_ACCEPTED but verification
                                result was: exit=1 last_line='NO: ...'

  [PASS] CASE C — invalid proof rejected; proof-required gate denied.
```

---

## 5. Short Announcement (Draft — not for publication)

```
ExergyNet open-sources an authority adapter for FlashProve.

FlashProve (Anthropic, Apache 2.0) lets a provider prove which model
answered a request on a CPU in seconds, without revealing model weights.

ExergyNet's LNES-22 addresses a separate problem: whether an agent
has authority to perform a consequential operation.

The adapter demonstrates three outcomes:
  → Valid proof + authorized action: permitted (MOCK_ACTION_EXECUTED)
  → Valid proof + unauthorized action: denied (AUTHORITY_DENIED)
  → Invalid proof + proof-required action: blocked (PROOF_REJECTED)

A verified AI response is not necessarily an authorized AI action.
Inference provenance is evidence. Execution authority is a separate decision.

Code: github.com/exergynet/exergynet-flashprove-authority
License: Apache 2.0
Not affiliated with Anthropic. Not endorsed by Anthropic.
Prototype, not production security certification.
```

---

## 6. Technical Discussion Outline

Topics for developer community discussions that reference FlashProve accurately:

1. **What FlashProve proves** — model identity commitment, not model quality, not intent, not authority
2. **The inference-authorization gap** — why a proof that model X said Y does not mean Y is authorized
3. **Commitment ID as a trust anchor** — why the registry pattern matters (proof-sender self-attestation attack)
4. **Fail-closed design** — exit-code-only acceptance is insufficient; dual check required
5. **NOT CHECKED / PLAN ONLY are not verdicts** — common mistake to avoid
6. **What is NOT proved** — C++ verifier not formally proved; Lean proof only for the Lean verifier
7. **Mock-action containment** — why ALWAYS_DENIED_CAPABILITIES must be a hard list, not a soft policy

---

## 7. What to Avoid

Per §XV of the directive:

- Do not imply Anthropic discontinued provable inference research.
- Do not describe the integration as an official FlashProve extension.
- Do not claim access to Anthropic's developer community.
- Do not submit unsolicited automated comments or PRs to the upstream repository.
- Do not post until Trustee authorizes publication.
