# EDT-FP-001 — Public Release Package

**Date:** 2026-11-05  
**Status:** DRAFT — pending Trustee authorization before any public publication  
**Repository name:** `exergynet-flashprove-authority`

---

## Package Contents

```
exergynet-flashprove-authority/
├── README.md                        # Main project README
├── LICENSE                          # Apache 2.0 (ExergyNet code)
├── NOTICE                           # Attribution for FlashProve upstream
├── UPSTREAM_PROVENANCE.md           # Upstream commit, hashes, attribution
├── ARCHITECTURE.md                  # System architecture diagram + narrative
├── SECURITY.md                      # Security considerations and limits
├── THREAT_MODEL.md                  # Threat model (this doc's content)
├── adapter/
│   ├── flashprove_shim.py           # Main authority adapter
│   └── __init__.py
├── policy/
│   └── allowed_commitments.json     # Pinned trusted commitment IDs
├── tests/
│   └── test_all.py                  # Full test suite
├── examples/
│   └── demo_three_cases.py          # Three-case demonstration script
├── docs/
│   ├── EDT_FP_001_UPSTREAM_RECON.md
│   ├── EDT_FP_001_LNES22_INTERFACE_MAP.md
│   ├── EDT_FP_001_EVIDENCE_BINDING_SPEC.md
│   ├── EDT_FP_001_THREAT_MODEL.md
│   └── EDT_FP_001_AUTHORITY_DEMO.md
└── SHA256SUMS                       # Hashes of all deliverable files
```

---

## README.md — Main Text (Draft)

```markdown
# ExergyNet FlashProve Authority Adapter

**FlashProve provides cryptographic evidence about model inference.
ExergyNet supplies a distinct authorization boundary for consequential agent actions.
This adapter demonstrates how the two can be composed without equating
inference provenance with permission.**

## What This Is

This is an independent ExergyNet research prototype demonstrating the composition of:

1. **FlashProve** (Anthropic, Apache 2.0) — CPU verifier for zero-knowledge proofs
   of AI inference. Answers: "Did the committed model produce this output?"

2. **ExergyNet LNES-22** — Authority control plane. Answers: "Is this principal
   authorized to execute this action under this policy?"

These are different security questions. A YES from FlashProve does not imply
authorization from LNES-22.

## Three Demonstrated Cases

| Case | Proof | Authority | Action |
|------|-------|-----------|--------|
| A | Accepted | Granted | MOCK_ACTION_EXECUTED |
| B | Accepted | Denied | ACTION_NOT_EXECUTED |
| C | Rejected | Denied (gate) | ACTION_NOT_EXECUTED |

## Quick Start

Requirements: Python 3.9+, Linux, bash, g++ 13+ (for verifier build)

    # Clone with submodule or clone upstream separately
    git clone https://github.com/exergynet/exergynet-flashprove-authority
    cd exergynet-flashprove-authority

    # Build the FlashProve CPU verifier (Route 1 — CPU only, no GPU required)
    cd upstream && verifier/build.sh && cd ..

    # Run the three-case demonstration
    python examples/demo_three_cases.py

    # Run the test suite
    python -m pytest tests/test_all.py -v

## Disclaimers

- **Independent ExergyNet project.** Not affiliated with Anthropic.
- **Not endorsed by Anthropic.**
- **Uses FlashProve research artifacts** (Apache 2.0, Anthropic).
- **Prototype, not production security certification.**
- **The included proof demonstrates a synthetic fixture.**
  It does not prove that any real Claude or Llama production model answered any real request.
- **Production model support requires independently qualified commitments and proofs.**

## Attribution

FlashProve is © Anthropic PBC, licensed under the Apache License, Version 2.0.
See UPSTREAM_PROVENANCE.md and NOTICE for full attribution details.
```

---

## UPSTREAM_PROVENANCE.md — Required Content

```markdown
# FlashProve Upstream Provenance

## Repository

- **URL:** https://github.com/anthropics/FlashProve
- **Organization:** Anthropic PBC
- **License:** Apache License, Version 2.0
- **Version:** 0.16.0
- **Release date:** 2026-11-02
- **Upstream commit:** <see upstream/UPSTREAM_COMMIT.txt>

## What we use

Route 1 only: CPU verifier (`verifier/build.sh` → `bin/cp_verify`) and reference
example proof (`examples/accepted-proof/`).

We do NOT use: prover/, GPU code, any weight files.
We do NOT modify: any upstream source file.

## Changes

None. The upstream is used exactly as provided. No upstream source files are modified.

## Artifact Hashes

See upstream/ARTIFACT_HASHES.txt (populated by upstream/setup.sh after build).

## Attribution

Acknowledgments from the FlashProve repository:
Alessandro Chiesa, Giacomo Fenzi, Guy Weissenberg, Miranda Christ,
Rahul Dalal, Ben Mayer, James Petrie (VerInf).
```

---

## What Must NOT Be Published

Per §XIV of the directive, the following must NOT appear in the public release:

- Proprietary ExergyNet control-plane internals (production `policy_gate.py`, production `capability_registry.py` with live tool surface, production `lnes22_bridge.py` endpoints)
- Unreleased ExergyNet roadmaps
- Treasury addresses or wallet addresses
- Production settlement receipt formats or on-chain contract addresses
- Security-relevant implementation details beyond the standalone demonstration
- Production API keys, AWS credentials, Ed25519 authority signing keys

---

## Publication Gate

**NOT authorized for publication** until the Trustee explicitly authorizes release.

This document is an internal draft and preparation record only.
