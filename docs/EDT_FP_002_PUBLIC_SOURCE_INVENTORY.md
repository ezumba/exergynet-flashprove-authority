# EDT-FP-002 — Public Source Inventory

**Date:** 2026-11-05  
**Status:** SEALED — pending Trustee authorization for publication  
**Directive item:** 7 (final-RC verification)

This inventory defines the boundary between what is included in the public
open-source release package and what is explicitly excluded. The public package
must not contain proprietary ExergyNet runtime files, credentials, internal
governance configuration, or confidential architecture.

---

## INCLUDED in public release

| File | Description |
|------|-------------|
| `adapter/flashprove_shim.py` | Main adapter: FlashProve verification + LNES-22 authority bridge |
| `adapter/lnes22_authority_bridge.py` | Subprocess bridge to real or simulated LNES-22 engine |
| `tests/test_all.py` | 92-test suite (EDT-FP-001 + EDT-FP-002, including multiprocess race test) |
| `examples/demo_three_cases.py` | Three-path demonstration (CASE A/B/C) |
| `policy/allowed_commitments.json` | Sample trusted commitment registry (synthetic fixtures only) |
| `upstream/setup.sh` | FlashProve build script (builds from Anthropic source) |
| `upstream/UPSTREAM_COMMIT.txt` | Pinned FlashProve commit hash |
| `upstream/ARTIFACT_HASHES.txt` | Verifier binary hash reference |
| `generate_sha256sums.py` | SHA-256 digest generator for all deliverables |
| `SHA256SUMS` | Sealed digests of all deliverable files |
| `docs/EDT_FP_001_*.md` | All EDT-FP-001 documentation (11 files) |
| `docs/EDT_FP_002_*.md` | All EDT-FP-002 documentation (10 files) |
| `README.md` | Public-facing integration guide |

---

## EXCLUDED from public release

| Item | Reason |
|------|--------|
| `upstream/bin/cp_verify` | Binary artifact — users build from source via `upstream/setup.sh` |
| Any real LNES-22 source files (`policy_gate.py`, `capability_registry.py`, etc.) | Private ExergyNet proprietary runtime; users bring their own if testing real integration |
| Any private keys or wallet addresses | Never committed; enforced by `.gitignore` |
| `VAULT_LEDGER.md` | Internal ExergyNet infrastructure record (mainnet addresses, server IPs) |
| `PROJECT_BLOCKERS.md` | Internal governance/deployment register |
| `LWP_MAINTENANCE_POLICY.md` | Internal living white paper policy |
| Any `exergynet/` subdirectory content | Proprietary ExergyNet project code |
| Any AWS/EC2 credentials or IAM keys | Never committed |
| Any production RPC URLs or private RPC endpoints | Internal infrastructure |
| Internal OTET harness or authority process isolation tooling | Proprietary |

---

## Sensitive boundary: LNES-22 source

The public package includes `adapter/lnes22_authority_bridge.py`, which can OPTIONALLY
be pointed at a real LNES-22 source directory via the `LNES22_SOURCE_PATH` environment
variable. If that variable is unset (the default for external users), the bridge runs
in `LOCAL_SIMULATION` mode, which mirrors the same check sequence without requiring any
proprietary source.

The public package does NOT include the real LNES-22 `policy_gate.py` or
`capability_registry.py`. The simulation mode is functionally independent and sufficient
for all demonstration purposes.

---

## Engine label guarantee (item 8)

The integration is identified as `REAL_LNES22_LOCAL_DEVELOPMENT` only when a
real LNES-22 source directory is present and passes file verification. It is NOT
presented as production LNES-22 certification, cloud LNES-22, or any production
authorization service.

The `README.md` explicitly states:
> This is a **local development integration** that demonstrates the authority-separation
> axiom using the real LNES-22 policy engine when source is available, or a faithful
> local simulation when it is not. It is **not** production LNES-22 certification and
> is **not** connected to any ExergyNet production authorization service.

---

## Disclosure classification

| Disclosure category | Level |
|--------------------|-------|
| Capability mapping (FP.* → TOOL.*) | PUBLIC — demonstrates architectural principle |
| LNES-22 policy logic (check order, risk class taxonomy) | DERIVED PUBLIC — same posture as published academic descriptions of deterministic policy engines |
| Real LNES-22 source code | EXCLUDED — proprietary |
| ExergyNet infrastructure (IPs, keys, mainnet addresses) | EXCLUDED — internal |
| Integration result / test outcomes | PUBLIC — demonstrates axiom holds |

---

## Publication blockers (unchanged)

| Blocker | Class | Resolution |
|---------|-------|------------|
| Trustee authorization | GOVERNANCE | Explicit operator approval required |

**No publication is authorized under EDT-FP-002.**
