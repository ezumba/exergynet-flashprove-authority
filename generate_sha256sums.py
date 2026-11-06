"""
Generate SHA256SUMS for all deliverable files.
Run from workspace root: python generate_sha256sums.py
"""
import hashlib
import pathlib

WORKSPACE = pathlib.Path(__file__).resolve().parent

targets = [
    "adapter/flashprove_shim.py",
    "adapter/lnes22_authority_bridge.py",
    "tests/test_all.py",
    "examples/demo_three_cases.py",
    "policy/allowed_commitments.json",
    "docs/EDT_FP_001_UPSTREAM_RECON.md",
    "docs/EDT_FP_001_VERIFIER_BUILD_REPORT.md",
    "docs/EDT_FP_001_VALID_INVALID_PROOF_TESTS.md",
    "docs/EDT_FP_001_LNES22_INTERFACE_MAP.md",
    "docs/EDT_FP_001_EVIDENCE_BINDING_SPEC.md",
    "docs/EDT_FP_001_THREAT_MODEL.md",
    "docs/EDT_FP_001_AUTHORITY_DEMO.md",
    "docs/EDT_FP_001_PUBLIC_RELEASE_PACKAGE.md",
    "docs/EDT_FP_001_INDEPENDENT_CODEX_AUDIT.md",
    "docs/EDT_FP_001_TEST_RESULTS.md",
    "docs/EDT_FP_001_RELEASE_READINESS.md",
    "docs/EDT_FP_001_DEVELOPER_DISCOVERY_STRATEGY.md",
    "docs/EDT_FP_002_RECON_REPORT.md",
    "docs/EDT_FP_002_REAL_AUTHORITY_INTEGRATION.md",
    "docs/EDT_FP_002_EVIDENCE_BINDING_UPGRADE.md",
    "docs/EDT_FP_002_REPLAY_PROTECTION_SPEC.md",
    "docs/EDT_FP_002_REPRODUCIBLE_BUILD.md",
    "docs/EDT_FP_002_ADVERSARIAL_TEST_RESULTS.md",
    "docs/EDT_FP_002_CODEX_AUDIT.md",
    "docs/EDT_FP_002_PUBLIC_PACKAGE_MANIFEST.md",
    "docs/EDT_FP_002_RELEASE_READINESS.md",
    "docs/EDT_FP_002_CAPABILITY_RECONCILIATION.md",
    "docs/EDT_FP_002_PUBLIC_SOURCE_INVENTORY.md",
    "README.md",
    "upstream/setup.sh",
]

optional = [
    "upstream/bin/cp_verify",
    "upstream/UPSTREAM_COMMIT.txt",
    "upstream/ARTIFACT_HASHES.txt",
]

sums = []
for rel in targets:
    p = WORKSPACE / rel
    if p.is_file():
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        sums.append(f"{h}  {rel}")
    else:
        sums.append(f"{'?'*64}  {rel}  [MISSING]")

for rel in optional:
    p = WORKSPACE / rel
    if p.is_file():
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        sums.append(f"{h}  {rel}")

out = WORKSPACE / "SHA256SUMS"
out.write_text("\n".join(sums) + "\n")
print(f"Written: {out}")
for line in sums:
    print(line)
