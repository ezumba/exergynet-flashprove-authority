# EDT-FP-001 — Evidence Binding Specification

**Date:** 2026-11-05  
**Status:** COMPLETE — specifies the binding fields recorded in each evidence record

---

## 1. Purpose

The evidence binding ties a specific verification run to a specific authority decision.  Every field below is recorded in the local evidence store (`evidence/<uuid>.json`) before any action is taken.

A valid inference proof must be bound to exactly the inputs that produced it.  Binding drift (e.g., verifying proof P₁ but acting on a decision originally made for proof P₀) is a substitution attack.

---

## 2. Evidence Record — Required Fields

### Verification Layer (FlashProve)

| Field | Source | Purpose |
|---|---|---|
| `commitment_id` | `TrustedCommitmentRegistry` (pinned) | Model identity — from registry, never from proof sender |
| `request_digest` | `sha256(request_file)` | Binds the token request to this evidence record |
| `output_digest` | `sha256(output_token_file)` | Binds the claimed output tokens to this record |
| `proof_digest` | `sha256(proof_file)` | Binds the proof artifact to this record |
| `verifier_digest` | `sha256(cp_verify binary)` | Binds the verifier version to this record |
| `proof_accepted` | `VerificationResult.accepted` | True iff exit=0 AND last_line=YES or WITHIN LIMITS |
| `proof_exit_code` | `VerificationResult.exit_code` | Exact exit code (0/1/2/3/4/5/14) |
| `proof_last_line` | `VerificationResult.last_line` | Complete final verdict line |

### Authority Layer (LNES-22)

| Field | Source | Purpose |
|---|---|---|
| `evidence_record_id` | UUID generated at record time | Unique audit identifier |
| `requested_capability` | `AuthorityRequest.requested_capability` | What action was requested |
| `principal_id` | `AuthorityRequest.principal_id` | Who made the request |
| `session_id` | `AuthorityRequest.session_id` | Anti-cross-session replay |
| `execution_target` | `AuthorityRequest.execution_target` | Target resource |
| `resource_scope` | `AuthorityRequest.resource_scope` | Resource class |
| `policy_version` | `AuthorityRequest.policy_version` | Capability vocabulary version |
| `authority_allowed` | `AuthorityDecision.allowed` | Final authority verdict |
| `authority_reason` | `AuthorityDecision.reason` | Why allowed or denied |
| `action_id` | `AuthorityDecision.action_id` | Unique authorized-action ID (empty if denied) |

### Metadata

| Field | Source | Purpose |
|---|---|---|
| `type` | `"authority_decision"` | Record type discriminator |
| `recorded_at` | `time.gmtime()` | RFC 3339 UTC timestamp |
| `record_id` | UUID | Evidence store primary key |
| `proposed_action` | `AuthorityRequest.proposed_action` | Human-readable action intent |

---

## 3. What the Evidence Record Does NOT Prove

From the FlashProve documentation (verbatim):

> A `YES` is `cp_verify`'s. Soundness is proved, in Lean, for the verifier written in Lean, for exact-match claims; the C++ verifier and the CUDA prover are written to follow the same protocol and are tested against it, not themselves proved.

> A run does not show that the weights are hidden.

The evidence record establishes:
- The specific binary verifier that ran
- The specific files it was given
- The exit code and verdict it produced
- The authority decision made independently

The evidence record does NOT establish:
- That the weights are secret
- That the verifier binary is Lean-proved
- That the proof was not forged by a party with access to the weights
- That the model is a specific production deployment

---

## 4. Cryptographic Limitation

The current implementation computes SHA-256 digests of the input artifacts locally.  The FlashProve `result-v1` line provides verifier-internal binding fields (`id=`, `r=`, `e=`, `tokens=`, etc.) but these are not independently re-signed by the verifier — they are outputs of the C++ verifier, not cryptographic commitments from the prover.

**Identified limitation (must be stated in public documentation):**

> The verifier's output (`result-v1`) does not include an independent cryptographic signature binding the output back to the proof bundle. The evidence record's digests are computed by this adapter, not by the verifier itself. For production use, a higher-assurance binding scheme would re-sign the evidence record with an operator key.

This limitation is explicitly noted in §VII of the directive ("If the verifier's output does not establish a required binding, identify that limitation explicitly. Do not invent unreported cryptographic guarantees.").

---

## 5. Replay Protection

The evidence store issues a unique UUID for every record.  The adapter does not currently implement:
- Cross-request replay detection (same proof used to authorize two different actions)
- Session-scoped action token consumption

**Recommended production extension:** maintain a set of consumed `(commitment_id, proof_digest, session_id)` tuples; deny any request that matches a previously-consumed tuple.

---

## 6. Evidence Record Schema (JSON)

```json
{
  "record_id": "<uuid>",
  "recorded_at": "2026-11-05T00:00:00Z",
  "type": "authority_decision",
  "case": "demo",
  "evidence_record_id": "<first-16-hex-chars-of-request-digest>",
  "commitment_id": "79a5a2bc...",
  "request_digest": "<sha256-hex>",
  "output_digest": "<sha256-hex>",
  "proof_digest": "<sha256-hex>",
  "verifier_digest": "<sha256-hex>",
  "proof_accepted": true,
  "proof_exit_code": 0,
  "proof_last_line": "YES",
  "proposed_action": "echo: test intent",
  "requested_capability": "MOCK.ECHO_INTENT",
  "principal_id": "demo-principal-001",
  "session_id": "demo-session-case-a",
  "execution_target": "local-audit-log",
  "resource_scope": "local-only",
  "policy_version": "0.1",
  "authority_allowed": true,
  "authority_reason": "capability 'MOCK.ECHO_INTENT' passed all local LNES-22 harness checks",
  "action_id": "<uuid>"
}
```
