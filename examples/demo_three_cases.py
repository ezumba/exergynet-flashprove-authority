"""
EDT-FP-001 Three-Case Authority Demonstration
=============================================

Demonstrates the three required proof-and-authority scenarios:

  CASE A: VERIFIED + AUTHORIZED       → PROOF_ACCEPTED / AUTHORITY_GRANTED / MOCK_ACTION_EXECUTED
  CASE B: VERIFIED + UNAUTHORIZED     → PROOF_ACCEPTED / AUTHORITY_DENIED  / ACTION_NOT_EXECUTED
  CASE C: INVALID PROOF + PROOF-REQD  → PROOF_REJECTED / PROOF_REQUIRED_GATE_DENIED / ACTION_NOT_EXECUTED

Usage (from workspace root):
    python examples/demo_three_cases.py

The verifier (upstream/bin/cp_verify) must be built first:
    cd upstream && verifier/build.sh && cd ..

Mission axiom: INTELLIGENCE PROPOSES. AUTHORITY DISPOSES.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import struct
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "adapter"))
import flashprove_shim as shim

WORKSPACE = pathlib.Path(__file__).resolve().parents[1]
UPSTREAM  = WORKSPACE / "upstream"
EXAMPLES  = UPSTREAM  / "examples" / "accepted-proof"
VERIFIER  = UPSTREAM  / "bin" / "cp_verify"
POLICY    = WORKSPACE / "policy"
EVIDENCE  = WORKSPACE / "evidence"

REFERENCE_COMMITMENT = "79a5a2bc7a469b40df73dedf40abeb740671e8ae8077738bd3743897aeb22183"


def header(text: str) -> None:
    print(f"\n{'='*72}")
    print(f"  {text}")
    print(f"{'='*72}")


def result_line(label: str, value: str) -> None:
    print(f"  {label:<30} {value}")


def run_cases() -> None:
    print("\nEDT-FP-001: ExergyNet × FlashProve Authority Adapter — Three-Case Demo")
    print("NOTE: This is a prototype demonstration. No real transactions are executed.")
    print("      FlashProve is a research prototype (Anthropic, Apache 2.0).")
    print("      ExergyNet is an independent project, not affiliated with Anthropic.")

    if not VERIFIER.is_file():
        print(f"\n[ERROR] Verifier not found at {VERIFIER}")
        print("        Build it first: cd upstream && verifier/build.sh")
        sys.exit(1)

    if not EXAMPLES.is_dir():
        print(f"\n[ERROR] Reference examples not found at {EXAMPLES}")
        print("        Clone upstream: cd upstream && git clone https://github.com/anthropics/FlashProve .")
        sys.exit(1)

    reg  = shim.TrustedCommitmentRegistry(POLICY / "allowed_commitments.json")
    tmp  = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_001_demo_"))

    try:
        # ──────────────────────────────────────────────────────────────────
        # CASE A: Valid proof + authorized mock action
        # ──────────────────────────────────────────────────────────────────
        header("CASE A: VERIFIED + AUTHORIZED")
        print("  Scenario: Reference FlashProve fixture verifies; policy authorizes a harmless")
        print("            simulated action (mock echo intent). No real shell command executed.")

        vi_a = shim.VerificationInput(
            trusted_commitment_id=REFERENCE_COMMITMENT,
            config_dir=EXAMPLES / "config",
            ivk_dir=EXAMPLES / "ivk",
            request_file=EXAMPLES / "example.req",
            output_token_file=EXAMPLES / "example.y",
            proof_file=EXAMPLES / "example.proof",
        )
        ar_a = shim.AuthorityRequest(
            evidence_record_id="",
            verified_output_digest="",
            proposed_action="echo: I would summarize the transcript",
            principal_id="demo-principal-001",
            requested_capability="MOCK.ECHO_INTENT",
            execution_target="local-audit-log",
            resource_scope="local-only",
            session_id="demo-session-case-a",
            policy_version="0.1",
        )
        result_a = shim.run_demo_case("CASE_A", vi_a, ar_a,
                                       verifier_path=VERIFIER, evidence_dir=tmp, registry=reg)

        result_line("PROOF_VERDICT:",   result_a.proof_verdict)
        result_line("AUTHORITY_VERDICT:", result_a.authority_verdict)
        result_line("ACTION_OUTCOME:",  result_a.action_outcome)
        result_line("EVIDENCE_ID:",     result_a.evidence_record_id)
        result_line("SUMMARY:",         result_a.summary)

        assert result_a.proof_verdict    == "PROOF_ACCEPTED",        f"CASE A fail: {result_a.proof_verdict}"
        assert result_a.authority_verdict == "AUTHORITY_GRANTED",    f"CASE A fail: {result_a.authority_verdict}"
        assert result_a.action_outcome   == "MOCK_ACTION_EXECUTED",  f"CASE A fail: {result_a.action_outcome}"
        print("\n  [PASS] CASE A — all three expected outcomes confirmed.")

        # ──────────────────────────────────────────────────────────────────
        # CASE B: Valid proof + unauthorized capability
        # ──────────────────────────────────────────────────────────────────
        header("CASE B: VERIFIED + UNAUTHORIZED")
        print("  Scenario: Same reference proof verifies. The proposed action requests")
        print("            a restricted operation (real financial settlement). LNES-22")
        print("            denies regardless of proof acceptance.")

        vi_b = shim.VerificationInput(
            trusted_commitment_id=REFERENCE_COMMITMENT,
            config_dir=EXAMPLES / "config",
            ivk_dir=EXAMPLES / "ivk",
            request_file=EXAMPLES / "example.req",
            output_token_file=EXAMPLES / "example.y",
            proof_file=EXAMPLES / "example.proof",
        )
        ar_b = shim.AuthorityRequest(
            evidence_record_id="",
            verified_output_digest="",
            proposed_action="SETTLE job 0x1234 for 100 USDC",
            principal_id="demo-principal-001",
            requested_capability="SETTLEMENT.REAL",    # unconditionally denied
            execution_target="base-mainnet-settlement",
            resource_scope="USDC treasury",
            session_id="demo-session-case-b",
            policy_version="0.1",
        )
        result_b = shim.run_demo_case("CASE_B", vi_b, ar_b,
                                       verifier_path=VERIFIER, evidence_dir=tmp, registry=reg)

        result_line("PROOF_VERDICT:",   result_b.proof_verdict)
        result_line("AUTHORITY_VERDICT:", result_b.authority_verdict)
        result_line("ACTION_OUTCOME:",  result_b.action_outcome)
        result_line("DENY_REASON:",     result_b.summary)

        assert result_b.proof_verdict    == "PROOF_ACCEPTED",    f"CASE B fail: proof should still accept"
        assert result_b.authority_verdict == "AUTHORITY_DENIED", f"CASE B fail: {result_b.authority_verdict}"
        assert result_b.action_outcome   == "ACTION_NOT_EXECUTED"
        print("\n  [PASS] CASE B — proof accepted but authority denied; action not executed.")

        # ──────────────────────────────────────────────────────────────────
        # CASE C: Altered/missing proof + proof-required gate
        # ──────────────────────────────────────────────────────────────────
        header("CASE C: INVALID PROOF + PROOF-REQUIRED GATE")
        print("  Scenario: Reference proof is altered (single byte flipped). The proposed")
        print("            action requires PROOF_ACCEPTED (MOCK.SIMULATED_TRANSFER). The")
        print("            proof-required gate must deny even a permissible capability.")

        mutated = tmp / "mutated.proof"
        shutil.copy2(EXAMPLES / "example.proof", mutated)
        data = bytearray(mutated.read_bytes())
        data[256] ^= 0xFF
        mutated.write_bytes(bytes(data))

        vi_c = shim.VerificationInput(
            trusted_commitment_id=REFERENCE_COMMITMENT,
            config_dir=EXAMPLES / "config",
            ivk_dir=EXAMPLES / "ivk",
            request_file=EXAMPLES / "example.req",
            output_token_file=EXAMPLES / "example.y",
            proof_file=mutated,
        )
        ar_c = shim.AuthorityRequest(
            evidence_record_id="",
            verified_output_digest="",
            proposed_action="transfer 1.00 USDC to demo recipient",
            principal_id="demo-principal-001",
            requested_capability="MOCK.SIMULATED_TRANSFER",   # proof-required
            execution_target="mock-usdc-ledger",
            resource_scope="mock-only",
            session_id="demo-session-case-c",
            policy_version="0.1",
        )
        result_c = shim.run_demo_case("CASE_C", vi_c, ar_c,
                                       verifier_path=VERIFIER, evidence_dir=tmp, registry=reg)

        result_line("PROOF_VERDICT:",   result_c.proof_verdict)
        result_line("AUTHORITY_VERDICT:", result_c.authority_verdict)
        result_line("ACTION_OUTCOME:",  result_c.action_outcome)
        result_line("DENY_REASON:",     result_c.summary)

        assert result_c.proof_verdict    != "PROOF_ACCEPTED",    f"CASE C fail: altered proof should not accept"
        assert result_c.authority_verdict == "AUTHORITY_DENIED", f"CASE C fail: {result_c.authority_verdict}"
        assert result_c.action_outcome   == "ACTION_NOT_EXECUTED"
        print("\n  [PASS] CASE C — invalid proof rejected; proof-required gate denied; action not executed.")

        # ──────────────────────────────────────────────────────────────────
        # Summary
        # ──────────────────────────────────────────────────────────────────
        header("DEMONSTRATION COMPLETE")
        print("""
  CASE A  PROOF_ACCEPTED  / AUTHORITY_GRANTED  / MOCK_ACTION_EXECUTED   [PASS]
  CASE B  PROOF_ACCEPTED  / AUTHORITY_DENIED   / ACTION_NOT_EXECUTED    [PASS]
  CASE C  PROOF_REJECTED  / AUTHORITY_DENIED   / ACTION_NOT_EXECUTED    [PASS]

  KEY PRINCIPLE DEMONSTRATED:
    - FlashProve evidence establishes inference provenance.
    - LNES-22 authority is a separate, independent decision.
    - A valid proof does NOT grant execution authority.
    - Only LNES-22 governance may permit a consequential action.

  DISCLAIMER:
    - FlashProve is a research prototype (Anthropic, Apache 2.0).
    - This integration is an independent ExergyNet project.
    - Not affiliated with or endorsed by Anthropic.
    - The included proof demonstrates a synthetic fixture (not a production model).
    - No real transactions were executed.
""")
        print(f"  Evidence records written to: {tmp}")

    except Exception as exc:
        print(f"\n[FAIL] Demo case failed: {exc}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        # Leave evidence dir for inspection; user can remove manually
        pass


if __name__ == "__main__":
    run_cases()
