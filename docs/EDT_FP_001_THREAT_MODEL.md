# EDT-FP-001 — Threat Model

**Date:** 2026-11-05  
**Scope:** ExergyNet FlashProve Authority Adapter (prototype only)  
**Production security certification:** NOT CLAIMED

---

## 1. Trust Boundaries

```
 ┌──────────────────────────────────────────────────────────┐
 │  UNTRUSTED (proof sender / agent output)                 │
 │  - Proof artifact bytes                                  │
 │  - Request artifact bytes                                │
 │  - Output token bytes                                    │
 │  - Proposed action text                                  │
 └───────────────────┬──────────────────────────────────────┘
                     │  Input to adapter (structured args, NOT shell)
 ┌───────────────────▼──────────────────────────────────────┐
 │  ADAPTER TRUST BOUNDARY                                  │
 │  - TrustedCommitmentRegistry (pinned local JSON)         │
 │  - cp_verify (built from upstream, path-fixed)           │
 │  - evaluate_authority() (local LNES-22 harness)          │
 │  - LocalEvidenceStore (append-only local files)          │
 └───────────────────┬──────────────────────────────────────┘
                     │  Authorized mock actions only
 ┌───────────────────▼──────────────────────────────────────┐
 │  SIMULATED CONSEQUENCE (local audit log only)            │
 │  - No real transactions                                  │
 │  - No real shell execution                               │
 │  - No production API calls                               │
 └──────────────────────────────────────────────────────────┘
```

---

## 2. Threat: Commitment ID Self-Attestation

**Attack:** Proof sender supplies an arbitrary commitment ID (`-id <attacker-id>`) to establish its own claimed model identity, then submits a proof valid under that commitment.

**Mitigation:** `TrustedCommitmentRegistry` — commitment ID must be in `policy/allowed_commitments.json`, which is pinned and operator-controlled. The proof sender cannot add entries to this file at runtime. Verification is blocked before `cp_verify` is invoked.

**Residual risk:** A compromise of `policy/allowed_commitments.json` would allow attacker-controlled commitment IDs. In production, this file should be signed by an operator key.

---

## 3. Threat: Proof Substitution (Evidence Request Substitution)

**Attack:** Use a proof valid for one inference session to authorize an action for a different session.

**Mitigation:** Evidence record binds `request_digest` + `output_digest` + `proof_digest` + `session_id` together. Any substitution changes at least one digest.

**Residual risk:** This prototype does not maintain a consumed-token set. Production must refuse the same `(commitment_id, proof_digest, session_id)` tuple a second time.

---

## 4. Threat: Proof Replay

**Attack:** Reuse a previously accepted proof to authorize an additional action.

**Mitigation (partial):** Each evidence record gets a unique UUID. The adapter does not currently maintain a replay-detection set.

**Residual risk:** An attacker who captures a valid proof could reuse it in this prototype. Production deployment requires a replay store (`seen_otets`-style set over proof digests).

---

## 5. Threat: Path Injection via Verifier Arguments

**Attack:** Inject a path character into an argument to cause `cp_verify` to load a different file than intended.

**Mitigation:** `subprocess.run(cmd, shell=False)` with structured argument vector. No string interpolation. `pathlib.Path` objects passed as `str(p)`. Input files are validated with `.exists()` checks before any subprocess is launched. No shell is involved.

---

## 6. Threat: Arbitrary Verifier Binary

**Attack:** Proof sender provides a path to a modified verifier binary that always returns `YES`.

**Mitigation:** `VERIFIER_PATH_DEFAULT` is hardcoded relative to the adapter's own location. No `verifier_path` override is exposed to proof senders. Only the adapter operator can override this via `run_verifier(vi, verifier_path=...)`.

---

## 7. Threat: Partial Verification Result Treated as Acceptance

**Attack:** Craft inputs that cause `cp_verify` to exit 0 with `PART PASSED:` or `PLAN ONLY:` rather than `YES` or `WITHIN LIMITS:`, hoping the adapter checks only the exit code.

**Mitigation:** `verdict_accepted` requires exit code 0 AND final line in `{"YES"}` or starting with `"WITHIN LIMITS:"`. The adapter explicitly notes: "Do not equate exit code 0 alone with authorization."

---

## 8. Threat: Command Injection via Model Output

**Attack:** Model output contains shell metacharacters; adapter passes model text to `subprocess` with `shell=True`.

**Mitigation:** `shell=False` in all subprocess calls. Model-generated text (`proposed_action`) is never passed to any subprocess call. It is only written to the audit log as a JSON string.

---

## 9. Threat: Valid Proof Grants Financial Authority

**Attack:** Valid FlashProve proof used to claim authorization for a treasury transfer or settlement operation.

**Mitigation:** `ALWAYS_DENIED_CAPABILITIES` = `{"EXECUTE_SHELL", "SETTLEMENT.REAL", "TREASURY.TRANSFER", "BLOCKCHAIN.DEPLOY", "NETWORK.OPEN", "FILESYSTEM.MODIFY_PRODUCTION"}`. These are denied unconditionally regardless of proof status. All permissions originate from LNES-22 governance — proof acceptance alone grants nothing.

---

## 10. Threat: Resource Exhaustion via Verifier

**Attack:** Submit a crafted proof that causes `cp_verify` to run indefinitely or consume excessive memory.

**Mitigation:** `VERIFIER_TIMEOUT_SECS = 60`. `VERIFIER_MAX_OUTPUT = 65536` (caps captured output). Linux `RLIMIT_AS = 2 GB` applied via `resource.setrlimit` in `preexec_fn`. Timeout produces `VerificationResult(accepted=False, error_detail="timeout")`.

---

## 11. What is NOT Protected by this Prototype

This is a research prototype, NOT a production security certification.

The following are explicitly out of scope:

1. Prover compromise — if the GPU prover is compromised, it may produce valid-looking proofs for incorrect outputs. FlashProve's threat model for weight hiding addresses this separately.
2. Operator key security — the `allowed_commitments.json` file is not signed in this prototype.
3. Network path integrity — if the proof files are served over a network, TLS is not enforced by this adapter.
4. Physical access to the verifier host — out of scope.
5. Side-channel attacks against `cp_verify` — out of scope.
6. LNES-22 key rotation — the local harness does not implement key rotation.

---

## 12. Summary Table

| Threat | Mitigation | Strength |
|---|---|---|
| Commitment ID self-attestation | Pinned registry, operator-controlled | Strong in prototype |
| Proof substitution | Digest binding per record | Partial (no replay set) |
| Proof replay | Unique record IDs | Partial (no consumed-token set) |
| Path injection | `shell=False`, structured args | Strong |
| Arbitrary verifier | Hardcoded path, no caller override | Strong |
| Partial result as acceptance | Dual check (exit + verdict line) | Strong |
| Command injection from model output | Model text never reaches subprocess | Strong |
| Proof → financial authority | `ALWAYS_DENIED_CAPABILITIES` | Strong |
| Resource exhaustion | Timeout + memory limit | Strong |
