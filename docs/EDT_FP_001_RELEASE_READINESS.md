# EDT-FP-001 — Release Readiness

**Date:** 2026-11-05  
**Status:** QUALIFIED — awaiting Trustee authorization for publication

---

## Acceptance Criteria

| Criterion | Status | Notes |
|---|---|---|
| `EDT_FP_001_VERIFIER_QUALIFIED` | **PASS** | Build exit 0, reference proof YES, 2026-11-05 |
| `EDT_FP_001_AUTHORITY_SHIM_QUALIFIED` | **PASS** | 45/45 tests pass (WSL2), all 3 demo cases pass |
| `EDT_FP_001_PUBLIC_RELEASE_READY` | NOT_AUTHORIZED | Trustee authorization required |

---

## Gate Checklist

### G1: Upstream build

- [x] `verifier/build.sh` ran successfully in WSL2 as non-root user `edt`
- [x] `upstream/bin/cp_verify` present and executable (SHA-256: `7f9efc1e86a848a3...`)
- [x] `upstream/UPSTREAM_COMMIT.txt` = `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c`
- [x] `upstream/ARTIFACT_HASHES.txt` populated
- [x] Reference proof: exit 0, last line `YES`, `result-v1 status=0`
- [x] `THE VERIFIER IS BUILT:` line present in build output
- [x] `build.sh: note:` warning quoted in build report (WSL2 `/mnt/c` permissions note)

### G2: Adapter correctness

- [x] `flashprove_shim.py` — structured subprocess, `shell=False`, fail-closed
- [x] `policy/allowed_commitments.json` — two synthetic-fixture commitment IDs
- [x] `TrustedCommitmentRegistry` blocks untrusted IDs before verifier runs
- [x] `evaluate_authority()` — default-deny, closed vocabulary, independent of proof verdict
- [x] `ALWAYS_DENIED_CAPABILITIES` covers all financial/shell/deployment capabilities
- [x] `PROOF_REQUIRED_CAPABILITIES` enforces proof-required gate
- [x] Evidence store writes `authority_decision` and `mock_action_executed` records
- [x] Resource limits applied on Linux (conditional `resource` module import)

### G3: Test suite

- [x] **WSL2 Linux: 45/45 PASS** (Python 3.12.3, pytest 9.1.1, 9.16s, 2026-11-05)
- [x] **Windows: 32 passed, 13 skipped** (Python 3.13.13, pytest 9.0.3, verifier-requiring tests properly skipped on Windows)
- [x] All 10 negative proof categories covered (altered proof, wrong commitment, missing file, wrong token, bad path, non-verification status exits, timeout, self-attestation blocked)
- [x] All 5 always-denied capabilities tested (shell, settlement, treasury, deploy, network)
- [x] Three-case demo tests pass (Cases A, B, C)

### G4: Documentation completeness

- [x] `EDT_FP_001_UPSTREAM_RECON.md`
- [x] `EDT_FP_001_VERIFIER_BUILD_REPORT.md` ← populated with real build output
- [x] `EDT_FP_001_VALID_INVALID_PROOF_TESTS.md`
- [x] `EDT_FP_001_LNES22_INTERFACE_MAP.md`
- [x] `EDT_FP_001_EVIDENCE_BINDING_SPEC.md`
- [x] `EDT_FP_001_THREAT_MODEL.md`
- [x] `EDT_FP_001_AUTHORITY_DEMO.md`
- [x] `EDT_FP_001_TEST_RESULTS.md` ← updated with 45/45 results
- [x] `EDT_FP_001_PUBLIC_RELEASE_PACKAGE.md` (draft — NOT published)
- [x] `EDT_FP_001_INDEPENDENT_CODEX_AUDIT.md` (PENDING independent execution)
- [x] `EDT_FP_001_DEVELOPER_DISCOVERY_STRATEGY.md`
- [x] `EDT_FP_001_RELEASE_READINESS.md` (this file)

### G5: License compliance

- [x] Apache 2.0 upstream attribution in `EDT_FP_001_UPSTREAM_RECON.md`
- [x] No upstream source files modified
- [x] "not affiliated with Anthropic", "not endorsed by Anthropic", "research prototype" in demo output
- [x] `upstream/NOTICE` and `upstream/LICENSE` preserved in repo
- [x] `SHA256SUMS` file present with all deliverable hashes

### G6: Security review

- [x] No production API keys, AWS credentials, or private keys in any file
- [x] No production treasury addresses
- [x] No production settlement logic wired
- [x] `ALWAYS_DENIED_CAPABILITIES` covers financial/shell/deployment operations
- [ ] Independent Codex audit complete (PENDING — out-of-scope for this session)

---

## Remaining Blocker

| Blocker | Class | Resolution |
|---|---|---|
| Independent Codex audit | PROCESS | Requires separate execution |
| Trustee authorization for publication | GOVERNANCE | Explicit operator approval required before any public release |

---

## Final Status

```
EDT_FP_001_VERIFIER_QUALIFIED
  Upstream commit: 9e2bdd8ff5bf9c62f18263d7dac189b0400b260c
  Reference proof: exit=0, last_line=YES
  cp_verify SHA-256: 7f9efc1e86a848a3715c6cc870e465ac2a1c5e8fd1eac09e4809023de7604394

EDT_FP_001_AUTHORITY_SHIM_QUALIFIED
  WSL2 Linux: 45/45 pytest PASS
  Windows: 32/32 non-verifier pytest PASS (13 properly skipped)
  Three-case demo: CASE A/B/C all PASS
    Case C confirmed: altered proof rejected with exit=1 last_line='NO: proof-refused'

EDT_FP_001_PUBLIC_RELEASE_READY: NOT_AUTHORIZED
  Per directive §XVIII: no prototype acceptance authorizes public publication.
  Trustee authorization required before any public release action.
```

---

## No Prototype Acceptance Authorizes

- Production deployment
- Mainnet execution
- Public publication

Per directive §XVIII: "No prototype acceptance authorizes production deployment, Mainnet execution or public publication."
