# EDT-FP-001 — Upstream Recon
## FlashProve Repository Survey

**Date:** 2026-11-05  
**Engineer:** VANGUARD Engineering / Claude Code  
**Directive:** EDT-FP-001  
**Verification basis:** Direct fetch of github.com/anthropics/FlashProve README, AGENTS.md, verifier/build.sh, verifier/docs/output.md, integrations/README.md

---

## 1. Repository Identity

| Field | Value |
|---|---|
| Repository | `https://github.com/anthropics/FlashProve` |
| Organization | Anthropic |
| Version | 0.16.0 |
| License | Apache 2.0 |
| Release date | 2026-11-02 |
| Status | Research prototype; not maintained; not accepting contributions |
| Stars | ~879 |
| Upstream commit (pinned by setup.sh) | See `upstream/UPSTREAM_COMMIT.txt` after build |

---

## 2. What FlashProve Is

FlashProve enables an AI provider to prove which model answered a request without revealing the model's weights.  Three phases:

1. **Commit** — Provider publishes a commitment ID binding to one weight set (weights remain secret).
2. **Prove** — For each reply, the provider's GPU produces a proof that the reply is the committed model's output.
3. **Verify** — Anyone checks the proof on an ordinary CPU in seconds with `cp_verify`, without weights.

**Current supported model:** Llama 4 Maverick at full size, 1,024-token context.  
**Proof size:** ~18.78 MB per proof.  
**CPU verification time:** Seconds on a 24-core machine.  
**NOT deployed for Claude production inference.**

---

## 3. For Agents Section — Summary

The README "For agents" table defines four routes:

| Route | What it does | Needs | Time |
|---|---|---|---|
| **1** | Verify stored proof | Linux, bash, g++ 13+, <2 GB RAM | build 1–2 min, check <2 s |
| 2 | Toy proofs (CPU self-test) | Route 1 + make, python3 | ~1 min |
| 3 | Small model GPU proof | GPU stack, 10 GB RAM | 23–30 s |
| 3-full | Llama shape synthetic | GPU stack, 280 GB RAM | ~42 min |
| 4 | Llama 4 Maverick real | GPU stack, 330 GB RAM, 245 GB disk | hours |

**This directive uses Route 1 only** (CPU verifier + stored reference proof).  Routes 3 and 4 are not applicable — no GPU, no real model weights needed, and production keys must not be exposed.

---

## 4. AGENTS.md — Key Rules Extracted

Verbatim rules binding on this implementation:

- Never get past an error with `sudo`, `chmod`, `chown`, or `rm`.
- Never edit a source file to change a result.
- Do not build `prover/` unless the task needs it.
- **Never take a commitment ID from the files that came with a proof, except in the stored examples. Get it from a party you trust.**
- Run `cp_commit`, `cp_prove`, and `scales/` tools on synthetic or public weights only.
- Report: exact command, exit code, full last line.
- If accepted: include commitment ID, `r=` and `e=` from `covered:`, and lines `commitment:`, `proof of work:`, `result-v1`.

---

## 5. Verifier Build — build.sh Summary

- **Input:** `verifier/build.sh` from checkout root
- **Output:** `bin/cp_verify`
- **Compiler:** g++ 13+ or clang++ 18.1.3, `-O2`, extensive hardening flags
- **Build macros:** `BLK_FIELD=2`, `BLK_COUNT_HASH_CALLS=1`, `SERVING_BUILD=1`, `VF_SOURCE_DIGEST=<sha256>`
- **Success indicator:** line beginning `THE VERIFIER IS BUILT:`, exit code 0
- **Security checks:** directory permission validation, symlink walk, no root required

---

## 6. Reference Proof Command

```bash
bin/cp_verify \
  examples/accepted-proof/config \
  examples/accepted-proof/ivk \
  examples/accepted-proof/example.req \
  examples/accepted-proof/example.y \
  examples/accepted-proof/example.proof \
  -id "$(cat examples/accepted-proof/ID.txt)"
```

Expected: last line `YES`, exit code 0.

**Reference commitment ID:** `79a5a2bc7a469b40df73dedf40abeb740671e8ae8077738bd3743897aeb22183`

---

## 7. Verifier Exit Codes

| Exit | Last line | Meaning |
|---|---|---|
| 0 | `YES` or `WITHIN LIMITS: …` | Accepted |
| 1 | `NO: <name>` | Rejected |
| 2 | Usage/input error | Bad arguments |
| 3 | `PART PASSED: …` | Single-stage partial (not a full verdict) |
| 4 | `PLAN ONLY: …` | Planning call (not a verdict) |
| **5** | `NOT CHECKED: <name>` | Could not finish; neither accept nor reject |
| **14** | `NOT-A-VERIFICATION` | Not a valid verification call |

**Critical rule:** Acceptance requires BOTH exit code 0 AND the final verdict line being `YES` or `WITHIN LIMITS:`. Exit code 0 alone is not sufficient.

---

## 8. integrations/check_proof.py

A Python wrapper around `cp_verify` that:
1. Validates provided values against the proof files before invoking the C++ verifier.
2. Gets commitment ID from the caller — never from the server or proof bundle.
3. Creates isolated copies of config and proof files.
4. Restarts with `python -I` to prevent `PYTHONPATH`/user-site injection.
5. Returns `result:` lines and a final verdict line.

Five things the client must NEVER accept from the server: commitment ID, acceptance policy limits, token IDs, model's end-token IDs, the verifier binary.

---

## 9. Attribution Requirements (Apache 2.0)

The repository lists these contributors in ACKNOWLEDGMENTS:  
Alessandro Chiesa, Giacomo Fenzi, Guy Weissenberg, Miranda Christ, Rahul Dalal, Ben Mayer, James Petrie (VerInf).

Required for any distribution:
- Include `LICENSE` (Apache 2.0 text)
- Include `NOTICE` file (if present in upstream)
- Preserve copyright notices
- State changes made to upstream files (we make none — upstream is vendored unchanged)
- Include `UPSTREAM_PROVENANCE.md` in the public release package

---

## 10. What the Reference Proof Demonstrates

From AGENTS.md verbatim:

> `YES` or `WITHIN LIMITS` on a stored example says nothing about a provider's model. A test pass shows only expected answers on synthetic inputs.

> A run does not show that the weights are hidden: for what is proved and tested of that, point to weight hiding.

**This prototype's public documentation must state:** The included proof demonstrates a synthetic fixture. It does NOT prove that any real Claude or Llama production model answered any real request.

---

## 11. What is and is NOT Proved (Lean Verification)

From AGENTS.md:

> A `YES` is `cp_verify`'s. Soundness is proved, in Lean, for the verifier written in Lean, for exact-match claims; the C++ verifier and the CUDA prover are written to follow the same protocol and are tested against it, not themselves proved.

The ExergyNet adapter must not claim Lean-verified soundness for the C++ verifier binary — only for the Lean verifier.

---

## 12. Separation of Concerns — Core Thesis

**FlashProve:** Answers the question "Did the committed model produce this output?"  
**ExergyNet LNES-22:** Answers the question "Is this principal authorized to execute this action?"

These are different questions.  A YES from FlashProve does not imply authorization from LNES-22.  This distinction is the central architectural claim of this adapter.
