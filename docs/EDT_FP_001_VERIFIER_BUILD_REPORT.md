# EDT-FP-001 — Verifier Build Report

**Date:** 2026-11-05  
**Status:** COMPLETE — `EDT_FP_001_VERIFIER_QUALIFIED`  
**Build environment:** WSL2 Ubuntu 24.04, non-root user `edt`

---

## Build Summary

| Field | Value |
|---|---|
| Upstream repository | `https://github.com/anthropics/FlashProve` |
| Upstream Git commit | `9e2bdd8ff5bf9c62f18263d7dac189b0400b260c` |
| FlashProve version | 0.16.0 |
| Build command | `verifier/build.sh` (run from repository root) |
| Build exit status | **0** |
| `THE VERIFIER IS BUILT:` line | `THE VERIFIER IS BUILT: <workspace>/upstream/bin/cp_verify` |
| Build note (from AGENTS.md) | `build.sh: note: another account may be able to change /mnt/c (its group or others can write in it, and it has no sticky bit), under which this checkout lies, and so could change what is built, and this script itself; for a build that no other account can touch, keep the checkout below directories that only you can write in; if /mnt/c is yours, close it with chmod go-w` |
| `cp_verify` SHA-256 | `7f9efc1e86a848a3715c6cc870e465ac2a1c5e8fd1eac09e4809023de7604394` |
| g++ version | Ubuntu 13.3.0-6ubuntu2~24.04.1 |
| `build=` hash in result | `93afdaf592393a54ebd17b681d1c03295eb883f0161ff0e6ab872a3b39939595` |

---

## Reference Proof Verification

| Field | Value |
|---|---|
| Commitment ID | `79a5a2bc7a469b40df73dedf40abeb740671e8ae8077738bd3743897aeb22183` |
| Verifier exit status | **0** |
| Last line | **`YES`** |
| Proof type | Small model, synthetic weights — not Llama 4 Maverick, not Claude |

**Key output lines:**

```
covered: r=60 e=64 T=64 C=256 theta=256 cap=0 s=16 sh=8 positions=60..63 tokens=61..63
         y=yes next-token=no policy=exact-match above-clip=0
```

```
proof of work: up to 32 bits counted in 38 rounds; with it the least round has 128.00 bits,
               without it 96.23 bits
```

```
result-v1 status=0 claim=exact-match id=79a5a2bc7a469b40df73dedf40abeb740671e8ae8077738bd3743897aeb22183
          bits=128 work=32 work-rounds=38 least-round=128.00 least-round-without-work=96.23
          commitment-assumed-rounds=49 record=1 r=60 e=64 T=64 tokens=61..63 y=yes
          policy=exact-match C=256 theta=256 cap=0 s=16 sh=8 sT=4 F=24 above-clip=0 leaf=0
          stages=key,leaf,request dw=8
          build=93afdaf592393a54ebd17b681d1c03295eb883f0161ff0e6ab872a3b39939595
```

```
commitment: 49 closeness rounds of the one-time files rest on another source than the bound
            within a third of the distance; the table has a record: the binding of the weights
            rests on the theorem on codes (ePrint 2025/2055, Theorem 4.6), taken as given
```

```
seal: 8834e79f05dcfd1c5f38d83c1a57201a7d280c8bd061224fc574e9edd8ffec42
```

---

## Artifact Hashes (from `upstream/ARTIFACT_HASHES.txt`)

```
7f9efc1e86a848a3715c6cc870e465ac2a1c5e8fd1eac09e4809023de7604394  bin/cp_verify
5ed47fd101093e826a5bc833e57633e5a9237b49213c8f37cf518a3c1c8d9d99  examples/accepted-proof/example.proof
ce700974a03d43586d66ca742f9bbc8ad45c936d03dfdb8614dd559a2780aa13  examples/accepted-proof/example.req
add7f2a4843f8c512c0e2875546581db11b9ba227ee008b5f719dfacb125de76  examples/accepted-proof/example.y
ad3a4c1abecbae4d9f4f8640851f64796b9b1c595b40ea566d797f25ef2e7ff1  examples/accepted-proof/ID.txt
```

---

## Notes from AGENTS.md

> `YES` or `WITHIN LIMITS` on a stored example says nothing about a provider's model.
> A test pass shows only expected answers on synthetic inputs.

The reference proof fixture uses a **synthetic small model** — not Llama 4 Maverick, not Claude.
This report must state this clearly wherever the result is cited publicly.

The `build.sh: note:` warning above is about `/mnt/c` being group/other-writable under WSL2 (Windows
NTFS mount). This is an informational security note — not a build failure. The binary was produced and
verified correctly. For a production deployment, the checkout should live in a directory accessible
only to the build user.

---

## Acceptance Criterion — MET

```
EDT_FP_001_VERIFIER_QUALIFIED
```

- Build exit status = 0 ✓
- `THE VERIFIER IS BUILT:` line present ✓
- Reference verification exit status = 0 ✓
- Last line = `YES` ✓
- `result-v1` line present ✓
- `covered:` line present ✓
- `proof of work:` line present ✓
