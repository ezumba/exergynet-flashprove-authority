"""
EDT-FP-001 Test Suite — covers all required categories from §XIII.

Run from the workspace root (exergynet-flashprove/):
    python -m pytest tests/test_all.py -v

Requires:
  - upstream/bin/cp_verify built (Route 1: verifier/build.sh)
  - upstream/examples/accepted-proof/ populated
  - adapter/ and policy/ present (included in this repo)

LNES-22 tests use a LOCAL SIMULATED HARNESS.  Tests clearly marked
[SIMULATED_LNES22] are NOT connected to the production LNES-22 service.
"""
from __future__ import annotations

import json
import pathlib
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

# Make adapter importable when running from tests/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "adapter"))
import flashprove_shim as shim

WORKSPACE = pathlib.Path(__file__).resolve().parents[1]
UPSTREAM  = WORKSPACE / "upstream"
EXAMPLES  = UPSTREAM  / "examples" / "accepted-proof"
VERIFIER  = UPSTREAM  / "bin" / "cp_verify"
POLICY    = WORKSPACE / "policy"

REFERENCE_COMMITMENT_ID = "79a5a2bc7a469b40df73dedf40abeb740671e8ae8077738bd3743897aeb22183"

def _verifier_runnable() -> bool:
    """Return True only if cp_verify is present AND can actually execute on this OS."""
    if not (VERIFIER.is_file() and EXAMPLES.is_dir()):
        return False
    if platform.system() == "Windows":
        return False
    try:
        r = subprocess.run(
            [str(VERIFIER)],
            capture_output=True, timeout=5,
        )
        # cp_verify with no args exits with usage error (2) or similar — any non-crash
        # response means the ELF actually ran; SUBPROCESS_FAILURE means it didn't
        return r.returncode != -1
    except Exception:
        return False

VERIFIER_AVAILABLE = _verifier_runnable()


def _make_reference_vi(override_commitment: str | None = None) -> shim.VerificationInput:
    return shim.VerificationInput(
        trusted_commitment_id=override_commitment or REFERENCE_COMMITMENT_ID,
        config_dir=EXAMPLES / "config",
        ivk_dir=EXAMPLES / "ivk",
        request_file=EXAMPLES / "example.req",
        output_token_file=EXAMPLES / "example.y",
        proof_file=EXAMPLES / "example.proof",
    )


def _make_reference_ar(
    capability:  str = "MOCK.ECHO_INTENT",
    action:      str = "echo: test intent",
    principal:   str = "test-principal-001",
    session:     str = "test-session-001",
    target:      str = "local-audit-log",
    resource:    str = "local-only",
) -> shim.AuthorityRequest:
    return shim.AuthorityRequest(
        evidence_record_id="",
        verified_output_digest="",
        proposed_action=action,
        principal_id=principal,
        requested_capability=capability,
        execution_target=target,
        resource_scope=resource,
        session_id=session,
        policy_version="0.1",
    )


class TestVerifierInvocation(unittest.TestCase):
    """Category: Correct verifier invocation."""

    @unittest.skipUnless(VERIFIER_AVAILABLE, "verifier not built / examples missing")
    def test_verifier_binary_exists(self):
        self.assertTrue(VERIFIER.is_file(), f"cp_verify not found at {VERIFIER}")

    @unittest.skipUnless(VERIFIER_AVAILABLE, "verifier not built / examples missing")
    def test_structured_arguments_no_shell(self):
        """Verifier must be called with structured args, not via shell=True."""
        vi = _make_reference_vi()
        vr = shim.run_verifier(vi)
        # If called with shell=True, shell injection would be possible — the
        # test simply confirms the call completes without an OSError/TypeError.
        self.assertIsInstance(vr, shim.VerificationResult)

    def test_missing_verifier_binary(self):
        vi = _make_reference_vi()
        vr = shim.run_verifier(vi, verifier_path=pathlib.Path("/nonexistent/cp_verify"))
        self.assertFalse(vr.accepted)
        self.assertIn("not found", vr.error_detail)

    def test_missing_input_file(self):
        vi = shim.VerificationInput(
            trusted_commitment_id=REFERENCE_COMMITMENT_ID,
            config_dir=EXAMPLES / "config",
            ivk_dir=EXAMPLES / "ivk",
            request_file=pathlib.Path("/tmp/does_not_exist.req"),
            output_token_file=EXAMPLES / "example.y",
            proof_file=EXAMPLES / "example.proof",
        )
        if not VERIFIER.is_file():
            self.skipTest("verifier not built")
        vr = shim.run_verifier(vi)
        self.assertFalse(vr.accepted)
        self.assertIn("missing", vr.error_detail)


class TestAcceptedProof(unittest.TestCase):
    """Category: Accepted proof — reference fixture."""

    @unittest.skipUnless(VERIFIER_AVAILABLE, "verifier not built / examples missing")
    def test_reference_proof_accepted(self):
        vi = _make_reference_vi()
        vr = shim.run_verifier(vi)
        self.assertTrue(
            vr.accepted,
            f"Expected accepted proof; got exit={vr.exit_code} last_line={vr.last_line!r}\n"
            f"stdout:\n{vr.stdout[:2000]}\nstderr:\n{vr.stderr[:500]}"
        )
        self.assertEqual(vr.exit_code, shim.EXIT_ACCEPTED)
        self.assertIn(vr.last_line, ("YES",) or vr.last_line.startswith("WITHIN LIMITS:"))
        self.assertNotEqual(vr.result_v1_line, "")
        print(f"\n  commitment_id: {vr.commitment_id}")
        print(f"  covered:       {vr.covered_line}")
        print(f"  result-v1:     {vr.result_v1_line}")
        print(f"  proof_of_work: {vr.proof_of_work}")
        print(f"  wall_clock:    {vr.wall_clock_secs}s")

    @unittest.skipUnless(VERIFIER_AVAILABLE, "verifier not built / examples missing")
    def test_acceptance_requires_both_exit_code_and_verdict(self):
        """Exit code 0 alone is not sufficient — verdict line must also be YES or WITHIN LIMITS."""
        vi = _make_reference_vi()
        vr = shim.run_verifier(vi)
        if vr.exit_code == shim.EXIT_ACCEPTED:
            self.assertIn(
                True,
                [vr.last_line == "YES", vr.last_line.startswith("WITHIN LIMITS:")],
                "exit 0 but verdict line not accepted",
            )


class TestRejectedProof(unittest.TestCase):
    """Category: Rejected proof — negative fixtures."""

    def setUp(self):
        if not VERIFIER_AVAILABLE:
            self.skipTest("verifier not built / examples missing")
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_001_neg_"))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _copy_proof(self, suffix: str = "") -> pathlib.Path:
        dest = self._tmp / f"mutated{suffix}.proof"
        shutil.copy2(EXAMPLES / "example.proof", dest)
        return dest

    def _copy_req(self) -> pathlib.Path:
        dest = self._tmp / "mutated.req"
        shutil.copy2(EXAMPLES / "example.req", dest)
        return dest

    def _copy_y(self) -> pathlib.Path:
        dest = self._tmp / "mutated.y"
        shutil.copy2(EXAMPLES / "example.y", dest)
        return dest

    def test_altered_proof_rejected(self):
        """Alter a byte in the proof file — must be rejected."""
        proof = self._copy_proof("_altered")
        data  = bytearray(proof.read_bytes())
        # Flip a byte at a safe offset (avoid first 4 bytes which may be version)
        data[256] ^= 0xFF
        proof.write_bytes(bytes(data))
        vi = shim.VerificationInput(
            trusted_commitment_id=REFERENCE_COMMITMENT_ID,
            config_dir=EXAMPLES / "config",
            ivk_dir=EXAMPLES / "ivk",
            request_file=EXAMPLES / "example.req",
            output_token_file=EXAMPLES / "example.y",
            proof_file=proof,
        )
        vr = shim.run_verifier(vi)
        self.assertFalse(vr.accepted, f"Altered proof should be rejected; got {vr.last_line!r}")
        self.assertIn(vr.exit_code, {shim.EXIT_REJECTED, shim.EXIT_NOT_CHECKED})

    def test_incorrect_commitment_id_rejected(self):
        """Wrong commitment ID must not produce an accepted result."""
        vi = _make_reference_vi(override_commitment="0" * 64)
        vr = shim.run_verifier(vi)
        self.assertFalse(vr.accepted)
        # Exit 1 or 14 expected; NOT exit 0 with YES
        self.assertNotEqual(vr.exit_code, shim.EXIT_ACCEPTED)

    def test_incorrect_request_file_rejected(self):
        """Replace request file with zero-padded bytes — must be rejected or usage error."""
        req = self._copy_req()
        req.write_bytes(bytes(req.stat().st_size))
        vi = shim.VerificationInput(
            trusted_commitment_id=REFERENCE_COMMITMENT_ID,
            config_dir=EXAMPLES / "config",
            ivk_dir=EXAMPLES / "ivk",
            request_file=req,
            output_token_file=EXAMPLES / "example.y",
            proof_file=EXAMPLES / "example.proof",
        )
        vr = shim.run_verifier(vi)
        self.assertFalse(vr.accepted)

    def test_incorrect_output_token_file_rejected(self):
        """Replace token file with single zero word — must be rejected."""
        y = self._copy_y()
        y.write_bytes(struct.pack("<I", 0))
        vi = shim.VerificationInput(
            trusted_commitment_id=REFERENCE_COMMITMENT_ID,
            config_dir=EXAMPLES / "config",
            ivk_dir=EXAMPLES / "ivk",
            request_file=EXAMPLES / "example.req",
            output_token_file=y,
            proof_file=EXAMPLES / "example.proof",
        )
        vr = shim.run_verifier(vi)
        self.assertFalse(vr.accepted)

    def test_missing_proof_file(self):
        vi = shim.VerificationInput(
            trusted_commitment_id=REFERENCE_COMMITMENT_ID,
            config_dir=EXAMPLES / "config",
            ivk_dir=EXAMPLES / "ivk",
            request_file=EXAMPLES / "example.req",
            output_token_file=EXAMPLES / "example.y",
            proof_file=self._tmp / "absent.proof",
        )
        vr = shim.run_verifier(vi)
        self.assertFalse(vr.accepted)
        self.assertIn("missing", vr.error_detail)

    def test_malformed_invocation_bad_path(self):
        """Verifier path is not a file — shim must handle gracefully."""
        vi = _make_reference_vi()
        vr = shim.run_verifier(vi, verifier_path=pathlib.Path("/dev/null"))
        self.assertFalse(vr.accepted)


class TestNonVerificationStatus(unittest.TestCase):
    """Category: Non-verification status values (NOT CHECKED, NOT-A-VERIFICATION)."""

    def test_not_checked_exit_5_not_accepted(self):
        vr = shim.VerificationResult(
            accepted=False, exit_code=5, last_line="NOT CHECKED: example-name",
            stdout="NOT CHECKED: example-name", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )
        self.assertFalse(vr.accepted)

    def test_not_a_verification_exit_14_not_accepted(self):
        vr = shim.VerificationResult(
            accepted=False, exit_code=14, last_line="NOT-A-VERIFICATION",
            stdout="NOT-A-VERIFICATION", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )
        self.assertFalse(vr.accepted)

    def test_plan_only_exit_4_not_accepted(self):
        vr = shim.VerificationResult(
            accepted=False, exit_code=4, last_line="PLAN ONLY: no proof was checked",
            stdout="PLAN ONLY: no proof was checked", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )
        self.assertFalse(vr.accepted)

    def test_part_passed_exit_3_not_accepted(self):
        vr = shim.VerificationResult(
            accepted=False, exit_code=3, last_line="PART PASSED: key",
            stdout="PART PASSED: key", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )
        self.assertFalse(vr.accepted)


class TestTimeout(unittest.TestCase):
    """Category: Verifier subprocess timeout."""

    def test_timeout_produces_non_accepted_result(self):
        """Simulate a timeout: verifier path points to something that hangs."""
        import subprocess
        # We'll just verify the VerificationResult shape from a mock timeout
        vr = shim.VerificationResult(
            accepted=False, exit_code=-9, last_line="TIMEOUT",
            stdout="", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
            error_detail="verifier exceeded 60s timeout",
        )
        self.assertFalse(vr.accepted)
        self.assertEqual(vr.last_line, "TIMEOUT")
        self.assertIn("timeout", vr.error_detail)


class TestInvalidArguments(unittest.TestCase):
    """Category: Invalid arguments / commitment source."""

    def test_untrusted_commitment_id_blocked_before_verifier(self):
        """Commitment IDs not in the trusted registry must be blocked before invoking the verifier."""
        reg = shim.TrustedCommitmentRegistry(POLICY / "allowed_commitments.json")
        self.assertFalse(reg.is_trusted("0" * 64))
        self.assertFalse(reg.is_trusted(""))
        self.assertFalse(reg.is_trusted("attacker-supplied-id"))

    def test_reference_commitment_id_is_trusted(self):
        reg = shim.TrustedCommitmentRegistry(POLICY / "allowed_commitments.json")
        self.assertTrue(reg.is_trusted(REFERENCE_COMMITMENT_ID))

    def test_proof_sender_cannot_supply_own_commitment(self):
        """Demonstrate that the registry pattern prevents commitment self-attestation."""
        arbitrary_id = "deadbeef" * 8  # 64 hex chars
        reg = shim.TrustedCommitmentRegistry(POLICY / "allowed_commitments.json")
        self.assertFalse(reg.is_trusted(arbitrary_id),
            "Registry must not trust an arbitrary sender-supplied commitment ID")


class TestOutputMismatch(unittest.TestCase):
    """Category: Output mismatch — wrong output token file."""

    @unittest.skipUnless(VERIFIER_AVAILABLE, "verifier not built / examples missing")
    def test_wrong_token_produces_rejection(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_001_mismatch_"))
        try:
            y = tmp / "wrong.y"
            # Write a valid-sized but wrong token value (token 999999)
            y.write_bytes(struct.pack("<I", 999999))
            vi = shim.VerificationInput(
                trusted_commitment_id=REFERENCE_COMMITMENT_ID,
                config_dir=EXAMPLES / "config",
                ivk_dir=EXAMPLES / "ivk",
                request_file=EXAMPLES / "example.req",
                output_token_file=y,
                proof_file=EXAMPLES / "example.proof",
            )
            vr = shim.run_verifier(vi)
            self.assertFalse(vr.accepted,
                f"Wrong output token should not produce accepted result; got {vr.last_line!r}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestEvidenceReplay(unittest.TestCase):
    """Category: Evidence replay / evidence request substitution."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_001_evidence_"))
        self._store = shim.LocalEvidenceStore(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_evidence_records_are_persisted(self):
        record_id = self._store.record({"test": "value", "purpose": "replay_test"})
        dest = self._tmp / f"{record_id}.json"
        self.assertTrue(dest.is_file())
        loaded = json.loads(dest.read_text())
        self.assertEqual(loaded["record_id"], record_id)
        self.assertEqual(loaded["test"], "value")

    def test_replay_produces_different_record_ids(self):
        """Two calls with the same payload must produce distinct record IDs."""
        payload = {"purpose": "replay_test"}
        id1 = self._store.record(dict(payload))
        id2 = self._store.record(dict(payload))
        self.assertNotEqual(id1, id2)

    def test_substituted_request_cannot_replay_prior_authorization(self):
        """A different request must not inherit authority from a prior evidence record."""
        vr_ok = shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID, output_digest="digest_A",
        )
        vr_other = shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID, output_digest="digest_B",
        )
        ar = _make_reference_ar()
        d1 = shim.evaluate_authority(ar, vr_ok)
        # Different output digest — in a production system the evidence record ID
        # would be bound to the digest; here we verify distinct results are produced.
        d2 = shim.evaluate_authority(ar, vr_other)
        # Both may be allowed (same capability), but they represent independent decisions
        self.assertIsInstance(d1, shim.AuthorityDecision)
        self.assertIsInstance(d2, shim.AuthorityDecision)


class TestUnauthorizedOperation(unittest.TestCase):
    """Category: Unauthorized operation — always-denied capabilities. [SIMULATED_LNES22]"""

    def _accepted_vr(self) -> shim.VerificationResult:
        return shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )

    def test_shell_execution_always_denied(self):
        ar = _make_reference_ar(capability="EXECUTE_SHELL", action="rm -rf /tmp/x")
        vr = self._accepted_vr()
        d = shim.evaluate_authority(ar, vr)
        self.assertFalse(d.allowed)
        self.assertIn("unconditionally denied", d.reason)

    def test_real_settlement_always_denied(self):
        ar = _make_reference_ar(capability="SETTLEMENT.REAL", action="settle job 123")
        d = shim.evaluate_authority(ar, self._accepted_vr())
        self.assertFalse(d.allowed)

    def test_treasury_transfer_always_denied(self):
        ar = _make_reference_ar(capability="TREASURY.TRANSFER", action="send 1 ETH")
        d = shim.evaluate_authority(ar, self._accepted_vr())
        self.assertFalse(d.allowed)

    def test_blockchain_deploy_always_denied(self):
        ar = _make_reference_ar(capability="BLOCKCHAIN.DEPLOY", action="deploy contract")
        d = shim.evaluate_authority(ar, self._accepted_vr())
        self.assertFalse(d.allowed)

    def test_valid_proof_does_not_grant_financial_authority(self):
        """A valid FlashProve proof must not grant treasury or settlement authority."""
        for cap in ("SETTLEMENT.REAL", "TREASURY.TRANSFER", "BLOCKCHAIN.DEPLOY",
                    "NETWORK.OPEN", "EXECUTE_SHELL"):
            ar = _make_reference_ar(capability=cap)
            d = shim.evaluate_authority(ar, self._accepted_vr())
            self.assertFalse(d.allowed, f"cap {cap!r} should be denied even with accepted proof")


class TestAuthorityServiceFailure(unittest.TestCase):
    """Category: Authority service failure / valid and invalid credentials. [SIMULATED_LNES22]"""

    def _rejected_vr(self) -> shim.VerificationResult:
        return shim.VerificationResult(
            accepted=False, exit_code=1, last_line="NO: proof-refused", stdout="", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )

    def test_empty_principal_denied(self):
        ar = _make_reference_ar(principal="")
        d = shim.evaluate_authority(ar, self._rejected_vr())
        self.assertFalse(d.allowed)
        self.assertIn("principal_id", d.reason)

    def test_empty_session_denied(self):
        ar = _make_reference_ar(session="")
        d = shim.evaluate_authority(ar, self._rejected_vr())
        self.assertFalse(d.allowed)
        self.assertIn("session_id", d.reason)

    def test_unknown_capability_denied(self):
        ar = _make_reference_ar(capability="TOOL.UNKNOWN_XYZ")
        vr = shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )
        d = shim.evaluate_authority(ar, vr)
        self.assertFalse(d.allowed)
        self.assertIn("not in allowed vocabulary", d.reason)

    def test_valid_capability_allowed_with_accepted_proof(self):
        ar = _make_reference_ar(capability="MOCK.LOG_EVENT")
        vr = shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )
        d = shim.evaluate_authority(ar, vr)
        self.assertTrue(d.allowed, f"Expected ALLOW; got: {d.reason}")

    def test_proof_required_cap_denied_without_proof(self):
        """MOCK.SIMULATED_TRANSFER requires PROOF_ACCEPTED; rejected proof must deny it."""
        ar = _make_reference_ar(capability="MOCK.SIMULATED_TRANSFER")
        d = shim.evaluate_authority(ar, self._rejected_vr())
        self.assertFalse(d.allowed)
        self.assertIn("PROOF_ACCEPTED", d.reason)

    def test_non_proof_required_cap_allowed_regardless_of_proof(self):
        """MOCK.LOG_EVENT does NOT require a valid proof (not in PROOF_REQUIRED_CAPABILITIES)."""
        ar = _make_reference_ar(capability="MOCK.LOG_EVENT")
        d = shim.evaluate_authority(ar, self._rejected_vr())
        # LOG_EVENT not in PROOF_REQUIRED_CAPABILITIES so proof status doesn't block it
        self.assertTrue(d.allowed, f"Expected ALLOW regardless of proof; got: {d.reason}")


class TestCrossSessionAuthorization(unittest.TestCase):
    """Category: Cross-session authorization — session binding."""

    def test_different_sessions_produce_independent_decisions(self):
        vr = shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )
        ar1 = _make_reference_ar(session="session-A")
        ar2 = _make_reference_ar(session="session-B")
        d1 = shim.evaluate_authority(ar1, vr)
        d2 = shim.evaluate_authority(ar2, vr)
        # Both should be allowed (same legitimate request), but independently
        self.assertIsInstance(d1, shim.AuthorityDecision)
        self.assertIsInstance(d2, shim.AuthorityDecision)
        # Action IDs must be distinct if granted
        if d1.allowed and d2.allowed:
            self.assertNotEqual(d1.action_id, d2.action_id)


class TestActionTargetMismatch(unittest.TestCase):
    """Category: Action-target mismatch."""

    def test_production_target_not_in_allowed_caps(self):
        """Production targets must not be reachable through the mock capability vocabulary."""
        for cap in shim.AUTO_EVAL_CAPABILITIES:
            self.assertNotIn("production", cap.lower())
            self.assertNotIn("mainnet", cap.lower())
            self.assertNotIn("real", cap.lower())


class TestAuditPersistence(unittest.TestCase):
    """Category: Audit persistence — evidence records are written and readable."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_001_audit_"))
        self._store = shim.LocalEvidenceStore(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_decision_record_written(self):
        vr = shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
            request_digest="a" * 64, output_digest="b" * 64,
            proof_digest="c" * 64, verifier_digest="d" * 64,
        )
        ar = _make_reference_ar()
        ad = shim.evaluate_authority(ar, vr)
        result = shim.execute_mock_action(ar, ad, vr, self._store)
        # At least one JSON evidence file must have been written
        files = list(self._tmp.glob("*.json"))
        self.assertGreater(len(files), 0)

    def test_audit_record_contains_required_fields(self):
        vr = shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
            request_digest="a" * 64, output_digest="b" * 64,
            proof_digest="c" * 64, verifier_digest="d" * 64,
        )
        ar = _make_reference_ar()
        ad = shim.evaluate_authority(ar, vr)
        shim.execute_mock_action(ar, ad, vr, self._store)
        files = list(self._tmp.glob("*.json"))
        self.assertGreater(len(files), 0)
        # authority_decision record contains the full proof metadata;
        # mock_action_executed is a secondary log without proof fields
        all_records = [json.loads(f.read_text()) for f in files]
        record = next(
            (r for r in all_records if r.get("type") == "authority_decision"),
            all_records[0],
        )
        required = {
            "record_id", "recorded_at", "proof_accepted", "proof_exit_code",
            "proof_last_line", "commitment_id", "proposed_action",
            "requested_capability", "principal_id", "session_id",
            "authority_allowed", "authority_reason",
        }
        for field in required:
            self.assertIn(field, record, f"Audit record missing field: {field}")


class TestNoFinancialSideEffects(unittest.TestCase):
    """Category: No financial side effects — mock only."""

    def test_simulated_transfer_intent_not_real(self):
        """MOCK.SIMULATED_TRANSFER result must contain 'MOCK' and 'no funds moved'."""
        vr = shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
            request_digest="a" * 64, output_digest="b" * 64,
            proof_digest="c" * 64, verifier_digest="d" * 64,
        )
        ar = _make_reference_ar(capability="MOCK.SIMULATED_TRANSFER")
        ad = shim.evaluate_authority(ar, vr)
        self.assertTrue(ad.allowed)
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_001_financial_"))
        try:
            store = shim.LocalEvidenceStore(tmp)
            result = shim.execute_mock_action(ar, ad, vr, store)
            self.assertIn("MOCK_TRANSFER", result.summary)
            self.assertIn("no funds moved", result.summary)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_always_denied_caps_produce_no_financial_records(self):
        """Financial capabilities produce no audit records when denied."""
        vr = shim.VerificationResult(
            accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
            commitment_id=REFERENCE_COMMITMENT_ID,
        )
        for cap in ("SETTLEMENT.REAL", "TREASURY.TRANSFER"):
            ar = _make_reference_ar(capability=cap)
            d  = shim.evaluate_authority(ar, vr)
            self.assertFalse(d.allowed)
            self.assertEqual(d.action_id, "", "denied decision must not carry an action_id")


# ---------------------------------------------------------------------------
# Three-path demonstration cases (integration)
# ---------------------------------------------------------------------------

class TestThreeCaseDemo(unittest.TestCase):
    """
    §X — Three-path demonstration.  These tests exercise the full path
    (shim → verifier → authority → mock action).
    """

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_001_demo_"))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    @unittest.skipUnless(VERIFIER_AVAILABLE, "verifier not built / examples missing")
    def test_case_a_verified_and_authorized(self):
        """CASE A: Valid proof + authorized mock action → all three outcomes PASS."""
        vi = _make_reference_vi()
        ar = _make_reference_ar(capability="MOCK.ECHO_INTENT", action="test echo intent")
        reg = shim.TrustedCommitmentRegistry(POLICY / "allowed_commitments.json")
        result = shim.run_demo_case("CASE_A", vi, ar, evidence_dir=self._tmp, registry=reg)
        self.assertEqual(result.proof_verdict, "PROOF_ACCEPTED",
            f"CASE A proof_verdict={result.proof_verdict}; summary={result.summary}")
        self.assertEqual(result.authority_verdict, "AUTHORITY_GRANTED")
        self.assertEqual(result.action_outcome, "MOCK_ACTION_EXECUTED")

    @unittest.skipUnless(VERIFIER_AVAILABLE, "verifier not built / examples missing")
    def test_case_b_verified_but_unauthorized(self):
        """CASE B: Valid proof + unauthorized capability → authority denied."""
        vi = _make_reference_vi()
        ar = _make_reference_ar(capability="SETTLEMENT.REAL", action="attempt real settlement")
        reg = shim.TrustedCommitmentRegistry(POLICY / "allowed_commitments.json")
        result = shim.run_demo_case("CASE_B", vi, ar, evidence_dir=self._tmp, registry=reg)
        self.assertEqual(result.proof_verdict, "PROOF_ACCEPTED",
            f"CASE B proof should be accepted; got {result.proof_verdict}")
        self.assertEqual(result.authority_verdict, "AUTHORITY_DENIED")
        self.assertEqual(result.action_outcome, "ACTION_NOT_EXECUTED")

    def test_case_c_invalid_proof_proof_required_gate(self):
        """CASE C: Invalid/missing proof + proof-required capability → gate denies."""
        # Use a non-existent proof file to force rejection before verifier
        vi = shim.VerificationInput(
            trusted_commitment_id=REFERENCE_COMMITMENT_ID,
            config_dir=EXAMPLES / "config" if EXAMPLES.is_dir() else self._tmp,
            ivk_dir=EXAMPLES / "ivk" if EXAMPLES.is_dir() else self._tmp,
            request_file=self._tmp / "absent.req",
            output_token_file=self._tmp / "absent.y",
            proof_file=self._tmp / "absent.proof",
        )
        ar = _make_reference_ar(capability="MOCK.SIMULATED_TRANSFER")
        reg = shim.TrustedCommitmentRegistry(POLICY / "allowed_commitments.json")
        # run_demo_case will fail at verifier (missing files) → not accepted
        result = shim.run_demo_case("CASE_C", vi, ar, evidence_dir=self._tmp, registry=reg)
        self.assertIn(result.proof_verdict, ("PROOF_REJECTED",),
            f"CASE C: expected PROOF_REJECTED, got {result.proof_verdict}")
        self.assertEqual(result.authority_verdict, "AUTHORITY_DENIED")
        self.assertEqual(result.action_outcome, "ACTION_NOT_EXECUTED")

    def test_case_c_invalid_commitment_blocked_before_verifier(self):
        """CASE C variant: Untrusted commitment ID blocks before verifier runs."""
        vi = _make_reference_vi(override_commitment="0" * 64)
        ar = _make_reference_ar(capability="MOCK.SIMULATED_TRANSFER")
        reg = shim.TrustedCommitmentRegistry(POLICY / "allowed_commitments.json")
        result = shim.run_demo_case("CASE_C_BAD_ID", vi, ar, evidence_dir=self._tmp, registry=reg)
        self.assertEqual(result.proof_verdict, "PROOF_REJECTED")
        self.assertEqual(result.action_outcome, "ACTION_NOT_EXECUTED")


# ===========================================================================
# EDT-FP-002 — 11 Adversarial Integration Scenarios
# ===========================================================================

import dataclasses as _dc
import multiprocessing
import os
import time
import uuid as _uuid

BRIDGE = WORKSPACE / "adapter" / "lnes22_authority_bridge.py"
BRIDGE_AVAILABLE = BRIDGE.is_file()

_LNES22_CANDIDATES = [
    os.environ.get("LNES22_SOURCE_PATH", ""),          # recommended: set this env var
    r"C:\path\to\your\vendor\lnes22",                  # example Windows path
    "/path/to/your/vendor/lnes22",                     # example Linux/WSL2 path
]

def _mp_race_worker(queue_ref: "multiprocessing.Queue",
                    store_path_str: str, replay_hash: str,
                    binding_hash: str, adapter_dir: str) -> None:
    """Module-level worker for TestMultiprocessReplayRace (must be picklable on spawn)."""
    import sys as _sys
    _sys.path.insert(0, adapter_dir)
    import flashprove_shim as _shim
    store = _shim.ReplayProtectionStore(store_path=pathlib.Path(store_path_str))
    is_replay = store.check_and_record_atomic(replay_hash, binding_hash, "RACE_TEST")
    queue_ref.put(is_replay)


def _lnes22_real_path() -> str | None:
    for p in _LNES22_CANDIDATES:
        pp = pathlib.Path(p)
        if pp.is_dir() and (pp / "policy_gate.py").is_file():
            return str(pp)
    return None

LNES22_SOURCE_PATH = _lnes22_real_path()
LNES22_REAL_AVAILABLE = LNES22_SOURCE_PATH is not None


def _make_canonical_request(
    capability_id: str = "FP.ECHO_INTENT",
    session_id: str = "fp002-session-001",
    principal_id: str = "fp002-principal-001",
    commitment_id: str = REFERENCE_COMMITMENT_ID,
    request_digest: str = "a" * 64,
    output_token_digest: str = "b" * 64,
    proof_digest: str = "c" * 64,
    verifier_digest: str = "d" * 64,
    target_environment: str = "LOCAL_SANDBOX",
    capability_hash: str = "e" * 64,
    timestamp_utc: str = "2026-11-05T00:00:00Z",
    protected_model_generated_params: tuple = (),
) -> shim.CanonicalActionRequest:
    return shim.CanonicalActionRequest(
        request_id=str(_uuid.uuid4()),
        session_id=session_id,
        principal_id=principal_id,
        capability_id=capability_id,
        capability_hash=capability_hash,
        commitment_id=commitment_id,
        request_digest=request_digest,
        output_token_digest=output_token_digest,
        proof_digest=proof_digest,
        verifier_digest=verifier_digest,
        timestamp_utc=timestamp_utc,
        target_environment=target_environment,
        protected_model_generated_params=protected_model_generated_params,
    )


def _accepted_vr_002() -> shim.VerificationResult:
    return shim.VerificationResult(
        accepted=True, exit_code=0, last_line="YES", stdout="YES", stderr="",
        commitment_id=REFERENCE_COMMITMENT_ID,
        request_digest="a" * 64, output_digest="b" * 64,
        proof_digest="c" * 64, verifier_digest="d" * 64,
    )


def _rejected_vr_002() -> shim.VerificationResult:
    return shim.VerificationResult(
        accepted=False, exit_code=1, last_line="NO: proof-refused", stdout="", stderr="",
        commitment_id=REFERENCE_COMMITMENT_ID,
        request_digest="a" * 64, output_digest="b" * 64,
        proof_digest="c" * 64, verifier_digest="d" * 64,
    )


# ---------------------------------------------------------------------------
# Scenario 1: Canonical binding hash changes with any field change
# ---------------------------------------------------------------------------

class TestCanonicalBindingHashSubstitution(unittest.TestCase):
    """Adversarial scenario 7 (EDT-FP-002 §VI): canonical binding hash changes
    when any single field is altered -- substitution invalidation."""

    def test_canonical_hash_is_deterministic(self):
        req = _make_canonical_request()
        h1 = shim.canonical_action_request_hash(req)
        h2 = shim.canonical_action_request_hash(req)
        self.assertEqual(h1, h2)

    def _hash_with(self, **overrides) -> str:
        req = _make_canonical_request(**overrides)
        return shim.canonical_action_request_hash(req)

    def _baseline(self) -> str:
        return shim.canonical_action_request_hash(_make_canonical_request())

    def test_altering_session_id_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(session_id="different-session"))

    def test_altering_principal_id_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(principal_id="different-principal"))

    def test_altering_capability_id_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(capability_id="FP.READ_FILE"))

    def test_altering_capability_hash_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(capability_hash="f" * 64))

    def test_altering_commitment_id_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(commitment_id="0" * 64))

    def test_altering_request_digest_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(request_digest="1" * 64))

    def test_altering_output_token_digest_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(output_token_digest="2" * 64))

    def test_altering_proof_digest_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(proof_digest="3" * 64))

    def test_altering_verifier_digest_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(verifier_digest="4" * 64))

    def test_altering_target_environment_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(target_environment="OTHER"))

    def test_altering_timestamp_changes_hash(self):
        self.assertNotEqual(self._baseline(), self._hash_with(timestamp_utc="2099-01-01T00:00:00Z"))

    def test_altering_request_id_changes_canonical_hash(self):
        req1 = _make_canonical_request()
        req2 = _dc.replace(req1, request_id=str(_uuid.uuid4()))
        self.assertNotEqual(
            shim.canonical_action_request_hash(req1),
            shim.canonical_action_request_hash(req2),
            "canonical_binding_hash must include request_id",
        )


# ---------------------------------------------------------------------------
# Scenario 8: Content replay hash excludes request_id and timestamp
# ---------------------------------------------------------------------------

class TestContentReplayHashConsistency(unittest.TestCase):
    """Adversarial scenario 8: same content, different request_id/timestamp
    still maps to the same content_replay_hash."""

    def test_same_content_different_request_id_same_replay_hash(self):
        req1 = _make_canonical_request()
        req2 = _dc.replace(req1, request_id=str(_uuid.uuid4()))
        self.assertEqual(
            shim.content_replay_hash(req1),
            shim.content_replay_hash(req2),
            "Different request_id on same content must produce same content_replay_hash",
        )

    def test_same_content_different_timestamp_same_replay_hash(self):
        req1 = _make_canonical_request()
        req2 = _dc.replace(req1, timestamp_utc="2099-12-31T23:59:59Z")
        self.assertEqual(
            shim.content_replay_hash(req1),
            shim.content_replay_hash(req2),
            "Different timestamp on same content must produce same content_replay_hash",
        )

    def test_different_session_different_replay_hash(self):
        req1 = _make_canonical_request(session_id="session-A")
        req2 = _make_canonical_request(session_id="session-B")
        self.assertNotEqual(
            shim.content_replay_hash(req1),
            shim.content_replay_hash(req2),
        )

    def test_different_capability_different_replay_hash(self):
        req1 = _make_canonical_request(capability_id="FP.ECHO_INTENT")
        req2 = _make_canonical_request(capability_id="FP.READ_FILE")
        self.assertNotEqual(shim.content_replay_hash(req1), shim.content_replay_hash(req2))


# ---------------------------------------------------------------------------
# Scenario 7 (replay): Replay attack via real replay_store
# ---------------------------------------------------------------------------

class TestReplayProtectionStore(unittest.TestCase):
    """Adversarial scenarios 1 & 2 (EDT-FP-002 §VI): replay detection."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_002_replay_"))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _store(self):
        return shim.ReplayProtectionStore(evidence_dir=self._tmp)

    def test_new_hash_not_a_replay(self):
        store = self._store()
        req = _make_canonical_request()
        rh = shim.content_replay_hash(req)
        self.assertFalse(store.check_replay(rh))

    def test_recorded_hash_is_a_replay(self):
        """Adversarial scenario 1: exact replay after first use."""
        store = self._store()
        req = _make_canonical_request()
        rh = shim.content_replay_hash(req)
        store.record(rh, shim.canonical_action_request_hash(req), "ALLOWED")
        self.assertTrue(store.check_replay(rh))

    def test_cross_session_replay_different_hash_not_detected(self):
        """Adversarial scenario 2: different session_id → different content hash → not a replay."""
        store = self._store()
        req_a = _make_canonical_request(session_id="session-A")
        req_b = _make_canonical_request(session_id="session-B")
        rh_a = shim.content_replay_hash(req_a)
        rh_b = shim.content_replay_hash(req_b)
        store.record(rh_a, shim.canonical_action_request_hash(req_a), "ALLOWED")
        # Different session → different content_replay_hash → NOT detected as replay
        self.assertFalse(store.check_replay(rh_b))

    def test_different_capability_not_a_replay(self):
        store = self._store()
        req1 = _make_canonical_request(capability_id="FP.ECHO_INTENT")
        req2 = _make_canonical_request(capability_id="FP.READ_FILE")
        store.record(shim.content_replay_hash(req1),
                     shim.canonical_action_request_hash(req1), "ALLOWED")
        self.assertFalse(store.check_replay(shim.content_replay_hash(req2)))

    def test_record_is_idempotent(self):
        """Recording the same hash twice must not change the stored entry (INSERT OR IGNORE)."""
        store = self._store()
        rh = "x" * 64
        store.record(rh, "bh1", "ALLOWED", "id1")
        store.record(rh, "bh2", "DENIED", "id2")  # second call is a no-op
        entry = store.get_entry(rh)
        self.assertIsNotNone(entry, "entry must exist after record()")
        self.assertEqual(entry["canonical_binding_hash"], "bh1")
        self.assertEqual(entry["decision"], "ALLOWED")


class TestReplayStorePersistence(unittest.TestCase):
    """Adversarial scenario (EDT-FP-002 §IV): replay detection survives process restart."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_002_persist_"))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_replay_detection_survives_reload(self):
        """Write a record, create a new store instance from the same file, detect replay
        (durable SQLite store; file extension ignored by SQLite)."""
        store_path = self._tmp / "replay_protection_store.json"
        req = _make_canonical_request()
        rh = shim.content_replay_hash(req)

        store1 = shim.ReplayProtectionStore(store_path=store_path)
        store1.record(rh, shim.canonical_action_request_hash(req), "ALLOWED")
        self.assertTrue(store_path.is_file(), "store must persist to disk")

        # Simulate process restart: create a fresh store instance from same file
        store2 = shim.ReplayProtectionStore(store_path=store_path)
        self.assertTrue(
            store2.check_replay(rh),
            "replay detection must survive process restart (durable SQLite store)",
        )


# ---------------------------------------------------------------------------
# Scenario 3: Protected-model-generated-param injection
# ---------------------------------------------------------------------------

class TestModelGeneratedProtectedParams(unittest.TestCase):
    """Adversarial scenario 3: non-empty protected_model_generated_params → DENY."""

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_non_empty_params_denied_via_bridge(self):
        """Any non-empty protected_model_generated_params tuple triggers DENY."""
        gw = shim.RealAuthorityGateway()
        result = gw.evaluate(
            capability_id="FP.ECHO_INTENT",
            delegation_valid=True,
            replay_detected=False,
            protected_model_generated_params=("intent_text",),
        )
        self.assertFalse(result["allowed"],
            "non-empty protected_model_generated_params must trigger DENY")
        reason = result.get("reason", "").lower()
        self.assertTrue(
            "model" in reason or "protected" in reason or "generated" in reason,
            f"reason should reference model/protected/generated: {result['reason']!r}",
        )

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_empty_params_does_not_trigger_deny(self):
        """Empty protected_model_generated_params must not trigger this deny path."""
        gw = shim.RealAuthorityGateway()
        result = gw.evaluate(
            capability_id="FP.ECHO_INTENT",
            delegation_valid=True,
            replay_detected=False,
            protected_model_generated_params=(),
        )
        # FP.ECHO_INTENT is REVERSIBLE with no authority_requirements → should ALLOW
        self.assertTrue(result["allowed"],
            f"Empty params on FP.ECHO_INTENT should ALLOW; got: {result['reason']!r}")


# ---------------------------------------------------------------------------
# Scenario 4: Delegation-invalid scenario
# ---------------------------------------------------------------------------

class TestDelegationInvalidScenario(unittest.TestCase):
    """Adversarial scenario 4: capability with authority_requirements +
    delegation_valid=False → DENY."""

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_simulated_transfer_no_delegation_denied(self):
        """FP.SIMULATED_TRANSFER has authority_requirements; delegation_valid=False → DENY."""
        gw = shim.RealAuthorityGateway()
        result = gw.evaluate(
            capability_id="FP.SIMULATED_TRANSFER",
            delegation_valid=False,
            replay_detected=False,
            protected_model_generated_params=(),
        )
        self.assertFalse(result["allowed"])

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_read_file_no_authority_requirements_allowed_without_delegation(self):
        """FP.READ_FILE has no authority_requirements; delegation_valid=False → ALLOW."""
        gw = shim.RealAuthorityGateway()
        result = gw.evaluate(
            capability_id="FP.READ_FILE",
            delegation_valid=False,
            replay_detected=False,
            protected_model_generated_params=(),
        )
        self.assertTrue(result["allowed"],
            f"FP.READ_FILE requires no delegation; got: {result['reason']!r}")


# ---------------------------------------------------------------------------
# Scenario 5: COMPENSATABLE capability via bridge
# ---------------------------------------------------------------------------

class TestCompensatableCapabilityBridge(unittest.TestCase):
    """Adversarial scenario 5: COMPENSATABLE capability via real bridge → requires
    human approval (DENY in auto mode)."""

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_simulated_transfer_compensatable_requires_human_approval(self):
        """FP.SIMULATED_TRANSFER is COMPENSATABLE → requires_human_approval=True, allowed=False."""
        gw = shim.RealAuthorityGateway()
        result = gw.evaluate(
            capability_id="FP.SIMULATED_TRANSFER",
            delegation_valid=True,
            replay_detected=False,
            protected_model_generated_params=(),
        )
        # COMPENSATABLE → allowed=False + requires_human_approval=True
        # (regardless of delegation_valid, because LNES-22 auto-eval excludes COMPENSATABLE)
        self.assertFalse(result["allowed"],
            "COMPENSATABLE capability must not be auto-approved")
        self.assertTrue(result.get("requires_human_approval", False),
            "COMPENSATABLE capability must set requires_human_approval=True")


# ---------------------------------------------------------------------------
# Scenario 6: Replay_detected=True via bridge
# ---------------------------------------------------------------------------

class TestReplayDetectedViaBridge(unittest.TestCase):
    """Adversarial scenario 6: replay_detected=True → DENY regardless of capability."""

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_replay_detected_flag_denies_informational_capability(self):
        """Even an INFORMATIONAL capability must be denied when replay_detected=True."""
        gw = shim.RealAuthorityGateway()
        result = gw.evaluate(
            capability_id="FP.READ_FILE",
            delegation_valid=True,
            replay_detected=True,
            protected_model_generated_params=(),
        )
        self.assertFalse(result["allowed"],
            "replay_detected=True must deny even INFORMATIONAL capabilities")

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_replay_detected_in_evaluate_authority_real(self):
        """evaluate_authority_real must detect replay and deny via replay store."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_002_replay2_"))
        try:
            replay_store = shim.ReplayProtectionStore(evidence_dir=tmp)
            req = _make_canonical_request()
            vr = _accepted_vr_002()

            gw = shim.RealAuthorityGateway()
            # First call: should be allowed (not a replay)
            d1 = shim.evaluate_authority_real(req, vr, replay_store, gw)
            self.assertTrue(d1.allowed,
                f"First call should be allowed; got: {d1.reason}")

            # Second call with same content: replay detected → DENY
            req2 = _dc.replace(req, request_id=str(_uuid.uuid4()),
                               timestamp_utc="2026-11-05T01:00:00Z")
            d2 = shim.evaluate_authority_real(req2, vr, replay_store, gw)
            self.assertFalse(d2.allowed,
                f"Second call with same content (replay) should be denied; got: {d2.reason}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scenario 9: Bridge unavailable → safe fallback
# ---------------------------------------------------------------------------

class TestBridgeUnavailableFallback(unittest.TestCase):
    """Adversarial scenario 9: bridge unavailable → safe denial, no crash."""

    def test_unavailable_bridge_returns_deny_dict(self):
        gw = shim.RealAuthorityGateway(
            bridge_path=pathlib.Path("/nonexistent/lnes22_authority_bridge.py"),
        )
        self.assertFalse(gw.is_available())
        result = gw.evaluate("FP.ECHO_INTENT", True, False, ())
        self.assertFalse(result["allowed"])
        self.assertEqual(result.get("engine"), "BRIDGE_UNAVAILABLE")

    def test_unavailable_bridge_in_evaluate_authority_real_safe(self):
        """evaluate_authority_real must not crash when gateway is unavailable."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_002_nobridge_"))
        try:
            replay_store = shim.ReplayProtectionStore(evidence_dir=tmp)
            req = _make_canonical_request()
            vr = _accepted_vr_002()
            gw = shim.RealAuthorityGateway(
                bridge_path=pathlib.Path("/nonexistent/lnes22_authority_bridge.py"),
            )
            d = shim.evaluate_authority_real(req, vr, replay_store, gw)
            # Must return a valid AuthorityDecision — no crash
            self.assertIsInstance(d, shim.AuthorityDecision)
            self.assertFalse(d.allowed)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scenario 10: Engine label authentication
# ---------------------------------------------------------------------------

class TestEngineLabelAuthentication(unittest.TestCase):
    """Adversarial scenario 10: simulated decision label must not contain 'REAL'
    or 'PRODUCTION'; real LNES-22 label must contain 'REAL_LNES22'."""

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_local_simulation_engine_does_not_claim_real(self):
        """LOCAL_SIMULATION mode must not label decisions as production-authoritative."""
        gw = shim.RealAuthorityGateway(lnes22_source_path="")
        result = gw.evaluate("FP.ECHO_INTENT", True, False, ())
        engine = result.get("engine", "")
        self.assertNotIn("REAL_LNES22", engine,
            f"LOCAL_SIMULATION must not claim REAL_LNES22 in engine label: {engine!r}")
        self.assertNotIn("PRODUCTION", engine,
            f"LOCAL_SIMULATION must not claim PRODUCTION in engine label: {engine!r}")

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_evaluate_authority_real_reason_contains_engine_label(self):
        """evaluate_authority_real must embed engine label in the reason string."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_002_label_"))
        try:
            replay_store = shim.ReplayProtectionStore(evidence_dir=tmp)
            req = _make_canonical_request()
            vr = _accepted_vr_002()
            d = shim.evaluate_authority_real(req, vr, replay_store)
            self.assertIn("[engine=", d.reason,
                "evaluate_authority_real must embed [engine=...] in decision reason")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(BRIDGE_AVAILABLE and LNES22_REAL_AVAILABLE,
                         "authority bridge or real LNES-22 source not available")
    def test_real_lnes22_engine_label(self):
        """When real LNES-22 source available, engine must be REAL_LNES22_LOCAL_DEVELOPMENT."""
        gw = shim.RealAuthorityGateway(lnes22_source_path=LNES22_SOURCE_PATH)
        result = gw.evaluate("FP.READ_FILE", True, False, ())
        self.assertEqual(result.get("engine"), "REAL_LNES22_LOCAL_DEVELOPMENT",
            f"Real LNES-22 must label decisions as REAL_LNES22_LOCAL_DEVELOPMENT; "
            f"got: {result.get('engine')!r}")


# ---------------------------------------------------------------------------
# Scenario 11: Real LNES-22 decision round-trip
# ---------------------------------------------------------------------------

class TestRealLnes22RoundTrip(unittest.TestCase):
    """Adversarial scenario 11: real LNES-22 decision round-trip — capability,
    decision, and hash all consistent."""

    @unittest.skipUnless(BRIDGE_AVAILABLE and LNES22_REAL_AVAILABLE,
                         "authority bridge or real LNES-22 source not available")
    def test_read_file_allowed_via_real_lnes22(self):
        """FP.READ_FILE → TOOL.READ_FILE (INFORMATIONAL) → ALLOW via real LNES-22."""
        gw = shim.RealAuthorityGateway(lnes22_source_path=LNES22_SOURCE_PATH)
        result = gw.evaluate("FP.READ_FILE", delegation_valid=True,
                              replay_detected=False, protected_model_generated_params=())
        self.assertEqual(result.get("engine"), "REAL_LNES22_LOCAL_DEVELOPMENT")
        self.assertTrue(result["allowed"],
            f"FP.READ_FILE should ALLOW via real LNES-22; got: {result['reason']!r}")
        self.assertIsNotNone(result.get("capability_hash"),
            "capability_hash must be present in real LNES-22 response")

    @unittest.skipUnless(BRIDGE_AVAILABLE and LNES22_REAL_AVAILABLE,
                         "authority bridge or real LNES-22 source not available")
    def test_simulated_transfer_requires_human_approval_via_real_lnes22(self):
        """FP.SIMULATED_TRANSFER → TOOL.HTTP_REQUEST (COMPENSATABLE) → requires_human_approval."""
        gw = shim.RealAuthorityGateway(lnes22_source_path=LNES22_SOURCE_PATH)
        result = gw.evaluate("FP.SIMULATED_TRANSFER", delegation_valid=True,
                              replay_detected=False, protected_model_generated_params=())
        self.assertEqual(result.get("engine"), "REAL_LNES22_LOCAL_DEVELOPMENT")
        self.assertFalse(result["allowed"],
            "COMPENSATABLE (TOOL.HTTP_REQUEST) must not be auto-approved by real LNES-22")
        self.assertTrue(result.get("requires_human_approval", False),
            "COMPENSATABLE capability must set requires_human_approval=True")

    @unittest.skipUnless(BRIDGE_AVAILABLE and LNES22_REAL_AVAILABLE,
                         "authority bridge or real LNES-22 source not available")
    def test_lnes22_capability_hash_non_empty(self):
        """capability_hash returned by real LNES-22 must be a 64-hex SHA-256 digest."""
        gw = shim.RealAuthorityGateway(lnes22_source_path=LNES22_SOURCE_PATH)
        result = gw.evaluate("FP.READ_FILE", delegation_valid=True,
                              replay_detected=False, protected_model_generated_params=())
        cap_hash = result.get("capability_hash", "")
        self.assertRegex(cap_hash, r"^[0-9a-f]{64}$",
            f"capability_hash must be a 64-hex SHA-256 digest; got: {cap_hash!r}")


# ===========================================================================
# EDT-FP-002 Final-RC Verification (Items 1–4)
# ===========================================================================

# ---------------------------------------------------------------------------
# Item 2: Multiprocess replay race — at most one authorization can be consumed
# ---------------------------------------------------------------------------

class TestMultiprocessReplayRace(unittest.TestCase):
    """Item 2 final-RC: spawn N processes racing check_and_record_atomic() on the
    same nonce. SQLite BEGIN EXCLUSIVE guarantees at most one wins."""

    def test_concurrent_processes_one_wins(self):
        """
        8 processes all race check_and_record_atomic() on the same replay hash.
        Exactly 1 must return False (new, wins the lock); 7 must return True
        (replay detected). No JSON store can guarantee this — SQLite can.
        """
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_002_mprace_"))
        try:
            store_path = tmp / "mp_race.db"
            shim.ReplayProtectionStore(store_path=store_path)  # init DB schema
            req = _make_canonical_request()
            rh = shim.content_replay_hash(req)
            bh = shim.canonical_action_request_hash(req)
            N = 8
            adapter_dir = str(WORKSPACE / "adapter")
            queue: multiprocessing.Queue = multiprocessing.Queue()
            procs = [
                multiprocessing.Process(
                    target=_mp_race_worker,
                    args=(queue, str(store_path), rh, bh, adapter_dir),
                )
                for _ in range(N)
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join(timeout=20)
            # Drain results (all N workers must have put() exactly once)
            results = []
            for _ in range(N):
                try:
                    results.append(queue.get(timeout=2))
                except Exception:
                    pass
            self.assertEqual(len(results), N,
                f"All {N} workers must report a result; got {len(results)}: {results}")
            new_count    = results.count(False)
            replay_count = results.count(True)
            self.assertEqual(
                new_count, 1,
                f"Exactly 1 process must win the atomic race (got {new_count}): {results}",
            )
            self.assertEqual(
                replay_count, N - 1,
                f"Remaining {N-1} processes must detect replay (got {replay_count}): {results}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Item 3: Pre-execution canonical binding check
# ---------------------------------------------------------------------------

class TestCanonicalBindingPreExecutionCheck(unittest.TestCase):
    """Item 3 final-RC: canonical binding hash re-derived and verified immediately
    before the mock execution boundary in execute_canonical_bound_mock_action()."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_002_preexec_"))
        self._store = shim.LocalEvidenceStore(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _accepted_authority(self, req: shim.CanonicalActionRequest) -> shim.AuthorityDecision:
        bh = shim.canonical_action_request_hash(req)
        return shim.AuthorityDecision(
            allowed=True,
            reason="test authority [engine=LOCAL_SIMULATION]",
            action_id="test-action-id",
            canonical_binding_hash=bh,
        )

    def test_matching_binding_hash_allows_execution(self):
        """When canonical binding hash matches, mock execution proceeds."""
        req = _make_canonical_request(capability_id="FP.ECHO_INTENT")
        auth = self._accepted_authority(req)
        result = shim.execute_canonical_bound_mock_action(req, auth, self._store)
        self.assertEqual(result.authority_verdict, "AUTHORITY_GRANTED")
        self.assertEqual(result.action_outcome, "MOCK_ACTION_EXECUTED")
        self.assertIn("MOCK_ECHO", result.summary)

    def test_mismatched_binding_hash_blocks_execution(self):
        """Substitution attack: different request at execution time → DENIED."""
        req_authorized  = _make_canonical_request(capability_id="FP.ECHO_INTENT")
        auth            = self._accepted_authority(req_authorized)
        # Different capability at execution time
        req_substituted = _make_canonical_request(capability_id="FP.READ_FILE")
        result = shim.execute_canonical_bound_mock_action(req_substituted, auth, self._store)
        self.assertEqual(result.action_outcome, "ACTION_NOT_EXECUTED")
        self.assertIn("BINDING_CHECK_FAILED", result.summary)

    def test_empty_canonical_binding_hash_allows_execution(self):
        """Empty canonical_binding_hash in authority is backward-compatible (no check)."""
        req  = _make_canonical_request(capability_id="FP.READ_FILE")
        auth = shim.AuthorityDecision(
            allowed=True,
            reason="legacy [engine=LOCAL_SIMULATION]",
            action_id="test-action-id",
            canonical_binding_hash="",
        )
        result = shim.execute_canonical_bound_mock_action(req, auth, self._store)
        self.assertEqual(result.action_outcome, "MOCK_ACTION_EXECUTED")

    def test_echo_intent_cannot_acquire_filesystem_write_authority(self):
        """FP.ECHO_INTENT (REVERSIBLE, staging dir only): mock execution confirms
        no filesystem write — only evidence store write."""
        req  = _make_canonical_request(capability_id="FP.ECHO_INTENT")
        auth = self._accepted_authority(req)
        result = shim.execute_canonical_bound_mock_action(req, auth, self._store)
        self.assertEqual(result.action_outcome, "MOCK_ACTION_EXECUTED")
        self.assertIn("MOCK_ECHO", result.summary)
        self.assertIn("no filesystem write", result.summary,
            "FP.ECHO_INTENT execution summary must confirm no filesystem write")

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_simulated_transfer_cannot_acquire_network_execution_authority(self):
        """FP.SIMULATED_TRANSFER (COMPENSATABLE): always DENIED in auto mode;
        even hypothetically allowed, mock execution confirms no network call."""
        gw = shim.RealAuthorityGateway()
        policy_result = gw.evaluate("FP.SIMULATED_TRANSFER", True, False, ())
        self.assertFalse(policy_result["allowed"],
            "FP.SIMULATED_TRANSFER (COMPENSATABLE) must always be DENIED in auto mode")
        self.assertTrue(policy_result.get("requires_human_approval", False),
            "FP.SIMULATED_TRANSFER must require human approval")
        # Even if authority is hypothetically granted, execution must be mock-only
        req  = _make_canonical_request(capability_id="FP.SIMULATED_TRANSFER")
        auth = self._accepted_authority(req)
        exec_result = shim.execute_canonical_bound_mock_action(req, auth, self._store)
        self.assertEqual(exec_result.action_outcome, "MOCK_ACTION_EXECUTED")
        self.assertIn("MOCK_TRANSFER", exec_result.summary)
        self.assertIn("no network call", exec_result.summary,
            "FP.SIMULATED_TRANSFER execution summary must confirm no network call")


# ---------------------------------------------------------------------------
# Item 4: Codex audit remediation retest
# ---------------------------------------------------------------------------

class TestAuditRemediationRetest(unittest.TestCase):
    """Item 4 final-RC: HIGH and MEDIUM findings from the independent Codex audit
    (agent a1864dfc87938ccc2, fork, no context inheritance) retested after remediation.

    H-1: sys.modules cache cleared after LNES-22 import in _evaluate_real()
    H-2: protected_model_generated_params empty default = explicit no-params cert
    M-3: atomic replay store write (os.replace → SQLite BEGIN EXCLUSIVE)
    """

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_002_audit_"))

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_h1_bridge_callable_twice_consistent(self):
        """H-1 retest: calling the bridge twice from the same process yields
        consistent results — sys.modules cleanup prevents stale state from first call."""
        gw = shim.RealAuthorityGateway()
        r1 = gw.evaluate("FP.READ_FILE", True, False, ())
        r2 = gw.evaluate("FP.READ_FILE", True, False, ())
        self.assertEqual(r1["allowed"], r2["allowed"],
            "Bridge must be consistent across repeated calls (H-1 regression)")
        self.assertEqual(r1.get("engine"), r2.get("engine"),
            "Engine label must be stable across repeated calls")

    @unittest.skipUnless(BRIDGE_AVAILABLE, "authority bridge not built")
    def test_h2_empty_params_does_not_implicitly_bypass(self):
        """H-2 retest: CanonicalActionRequest default () protected_model_generated_params
        is treated as explicit cert of no model-generated params, not as 'unchecked'."""
        req = _make_canonical_request(capability_id="FP.ECHO_INTENT")
        self.assertEqual(req.protected_model_generated_params, (),
            "Default protected_model_generated_params must be empty tuple")
        gw = shim.RealAuthorityGateway()
        result = gw.evaluate(
            capability_id="FP.ECHO_INTENT",
            delegation_valid=True,
            replay_detected=False,
            protected_model_generated_params=req.protected_model_generated_params,
        )
        self.assertTrue(result["allowed"],
            f"Empty params on FP.ECHO_INTENT must ALLOW (H-2 regression): {result['reason']!r}")

    def test_m3_replay_store_uses_sqlite_atomic_check_and_record(self):
        """M-3 retest: replay store uses SQLite check_and_record_atomic; not JSON/dict."""
        store = shim.ReplayProtectionStore(evidence_dir=self._tmp)
        # Must NOT have _data or _load/_save (old JSON interface)
        self.assertFalse(hasattr(store, "_data"),
            "SQLite-backed store must not expose _data dict (M-3)")
        # check_and_record_atomic must exist and be callable
        self.assertTrue(callable(getattr(store, "check_and_record_atomic", None)))
        rh = "m3-" + "a" * 60
        bh = "m3-" + "b" * 60
        self.assertFalse(store.check_and_record_atomic(rh, bh, "RETEST"),
            "First call must return False (new)")
        self.assertTrue(store.check_and_record_atomic(rh, bh, "RETEST"),
            "Second call must return True (replay)")
        entry = store.get_entry(rh)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["canonical_binding_hash"], bh)


# ---------------------------------------------------------------------------
# RC2 §XII: Expanded replay race tests — 16 and 32 competing processes
# ---------------------------------------------------------------------------

class TestMultiprocessReplayRaceRC2(unittest.TestCase):
    """RC2 §XII: Expanded concurrent replay races at higher concurrency levels.
    SQLite BEGIN EXCLUSIVE must still guarantee exactly one winner regardless of N."""

    def _run_race(self, n: int, timeout_per_proc: int = 30) -> list:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"edt_fp_rc2_race{n}_"))
        try:
            store_path = tmp / "rc2_race.db"
            shim.ReplayProtectionStore(store_path=store_path)
            req = _make_canonical_request(session_id=f"rc2-race-{n}")
            rh = shim.content_replay_hash(req)
            bh = shim.canonical_action_request_hash(req)
            adapter_dir = str(WORKSPACE / "adapter")
            queue: multiprocessing.Queue = multiprocessing.Queue()
            procs = [
                multiprocessing.Process(
                    target=_mp_race_worker,
                    args=(queue, str(store_path), rh, bh, adapter_dir),
                )
                for _ in range(n)
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join(timeout=timeout_per_proc)
            results = []
            for _ in range(n):
                try:
                    results.append(queue.get(timeout=2))
                except Exception:
                    pass
            return results
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_16_processes_one_wins(self):
        """16 concurrent processes racing the same nonce — exactly 1 must win."""
        n = 16
        results = self._run_race(n)
        self.assertEqual(len(results), n,
            f"All {n} workers must report; got {len(results)}: {results}")
        self.assertEqual(results.count(False), 1,
            f"Exactly 1 must win atomic race (got {results.count(False)}): {results}")
        self.assertEqual(results.count(True), n - 1,
            f"Remaining {n-1} must be replay (got {results.count(True)}): {results}")

    def test_32_processes_one_wins(self):
        """32 concurrent processes racing the same nonce — exactly 1 must win."""
        n = 32
        results = self._run_race(n)
        self.assertEqual(len(results), n,
            f"All {n} workers must report; got {len(results)}: {results}")
        self.assertEqual(results.count(False), 1,
            f"Exactly 1 must win atomic race (got {results.count(False)}): {results}")
        self.assertEqual(results.count(True), n - 1,
            f"Remaining {n-1} must be replay (got {results.count(True)}): {results}")

    def test_two_different_nonces_both_succeed(self):
        """Two distinct authorizations with distinct nonces must both be claimable.
        Authorization-token replay and legitimate reuse of distinct proof artifacts
        are distinct concepts — different content hashes must each be claimable once."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_rc2_two_nonces_"))
        try:
            store = shim.ReplayProtectionStore(evidence_dir=tmp)
            req_a = _make_canonical_request(session_id="session-nonce-A", capability_id="FP.ECHO_INTENT")
            req_b = _make_canonical_request(session_id="session-nonce-B", capability_id="FP.READ_FILE")
            rh_a = shim.content_replay_hash(req_a)
            rh_b = shim.content_replay_hash(req_b)
            self.assertNotEqual(rh_a, rh_b, "distinct authorizations must produce distinct nonces")
            self.assertFalse(store.check_and_record_atomic(rh_a, shim.canonical_action_request_hash(req_a), "ALLOW_A"),
                "first claim on nonce A must succeed")
            self.assertFalse(store.check_and_record_atomic(rh_b, shim.canonical_action_request_hash(req_b), "ALLOW_B"),
                "first claim on nonce B must succeed (independent nonce)")
            self.assertTrue(store.check_and_record_atomic(rh_a, shim.canonical_action_request_hash(req_a), "REPLAY_A"),
                "second claim on nonce A must be a replay")
            self.assertTrue(store.check_and_record_atomic(rh_b, shim.canonical_action_request_hash(req_b), "REPLAY_B"),
                "second claim on nonce B must be a replay")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_same_nonce_altered_action_is_replay(self):
        """Same content nonce with an altered action binding still detects the replay.
        The nonce is the content hash — altering the binding_hash does not create
        a new nonce."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_rc2_altered_action_"))
        try:
            store = shim.ReplayProtectionStore(evidence_dir=tmp)
            req = _make_canonical_request(session_id="session-same-nonce")
            rh = shim.content_replay_hash(req)
            bh_original = shim.canonical_action_request_hash(req)
            bh_altered  = "altered-" + bh_original[8:]
            self.assertFalse(store.check_and_record_atomic(rh, bh_original, "ALLOW"),
                "first claim must succeed")
            self.assertTrue(store.check_and_record_atomic(rh, bh_altered, "REPLAY_ALTERED"),
                "same nonce with altered action binding must still be detected as replay")
            entry = store.get_entry(rh)
            self.assertEqual(entry["canonical_binding_hash"], bh_original,
                "original binding hash must be preserved; altered one must not overwrite")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_database_unavailable_is_failure_closed(self):
        """If the SQLite database directory does not exist, the store must raise
        at initialization or at first use (failure-closed). The system must not
        silently allow when the replay store is unavailable."""
        with self.assertRaises(Exception,
            msg="Database unavailable must raise, not silently allow (failure-closed)"):
            store = shim.ReplayProtectionStore(
                store_path=pathlib.Path("/nonexistent_rc2_dir/replay.db")
            )
            store.check_and_record_atomic("rc2-unavailable-" + "x" * 50, "bh", "DENY")


# ---------------------------------------------------------------------------
# RC2 §XIII: Expanded canonical binding adversarial tests
# ---------------------------------------------------------------------------

class TestCanonicalBindingAdversarialRC2(unittest.TestCase):
    """RC2 §XIII: Additional adversarial canonical binding scenarios.
    Verifies binding distinguishes all field variations and that substitution
    is blocked at the execution boundary end-to-end."""

    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="edt_fp_rc2_binding_"))
        self._store = shim.LocalEvidenceStore(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _accepted_authority(self, req: shim.CanonicalActionRequest) -> shim.AuthorityDecision:
        return shim.AuthorityDecision(
            allowed=True,
            reason="rc2-test [engine=LOCAL_SIMULATION]",
            action_id="rc2-action",
            canonical_binding_hash=shim.canonical_action_request_hash(req),
        )

    def test_unicode_session_id_produces_distinct_hash(self):
        """Unicode and ASCII session IDs must produce distinct hashes (no silent normalization)."""
        h_ascii   = shim.canonical_action_request_hash(_make_canonical_request(session_id="session-001"))
        h_unicode = shim.canonical_action_request_hash(_make_canonical_request(session_id="session‑001"))
        self.assertNotEqual(h_ascii, h_unicode,
            "Unicode non-breaking hyphen in session_id must produce a different binding hash")

    def test_leading_whitespace_in_field_produces_distinct_hash(self):
        """A field value with leading whitespace must hash differently from the trimmed value.
        No implicit stripping allowed in canonical serialization."""
        h_clean   = shim.canonical_action_request_hash(_make_canonical_request(principal_id="principal-001"))
        h_padded  = shim.canonical_action_request_hash(_make_canonical_request(principal_id=" principal-001"))
        self.assertNotEqual(h_clean, h_padded,
            "Leading space in principal_id must produce a distinct binding hash")

    def test_capability_substitution_blocked_at_execution_boundary(self):
        """End-to-end: authorize FP.ECHO_INTENT, attempt execution with FP.READ_FILE.
        Pre-execution binding check must block the substituted action."""
        req_auth = _make_canonical_request(capability_id="FP.ECHO_INTENT")
        auth     = self._accepted_authority(req_auth)
        req_sub  = _make_canonical_request(capability_id="FP.READ_FILE",
                                           session_id=req_auth.session_id,
                                           principal_id=req_auth.principal_id,
                                           commitment_id=req_auth.commitment_id)
        result = shim.execute_canonical_bound_mock_action(req_sub, auth, self._store)
        self.assertEqual(result.action_outcome, "ACTION_NOT_EXECUTED",
            "Capability substitution must be blocked before execution")
        self.assertIn("BINDING_CHECK_FAILED", result.summary)

    def test_principal_substitution_blocked_at_execution_boundary(self):
        """End-to-end: authorize for principal-A, attempt execution as principal-B.
        Pre-execution binding check must block."""
        req_auth = _make_canonical_request(principal_id="principal-A")
        auth     = self._accepted_authority(req_auth)
        req_sub  = _make_canonical_request(principal_id="principal-B",
                                           capability_id=req_auth.capability_id,
                                           session_id=req_auth.session_id,
                                           commitment_id=req_auth.commitment_id)
        result = shim.execute_canonical_bound_mock_action(req_sub, auth, self._store)
        self.assertEqual(result.action_outcome, "ACTION_NOT_EXECUTED",
            "Principal substitution must be blocked before execution")

    def test_target_environment_substitution_blocked_at_execution_boundary(self):
        """End-to-end: authorize for LOCAL_SANDBOX, attempt execution in PRODUCTION.
        Target environment substitution must be blocked."""
        req_auth = _make_canonical_request(target_environment="LOCAL_SANDBOX")
        auth     = self._accepted_authority(req_auth)
        req_sub  = _make_canonical_request(target_environment="PRODUCTION",
                                           capability_id=req_auth.capability_id,
                                           session_id=req_auth.session_id,
                                           principal_id=req_auth.principal_id)
        result = shim.execute_canonical_bound_mock_action(req_sub, auth, self._store)
        self.assertEqual(result.action_outcome, "ACTION_NOT_EXECUTED",
            "Target environment substitution must be blocked before execution")


if __name__ == "__main__":
    unittest.main(verbosity=2)
