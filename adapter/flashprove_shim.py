"""
ExergyNet FlashProve Authority Adapter — flashprove_shim.py

Accepts FlashProve cryptographic evidence, invokes the official cpu verifier
in a constrained subprocess, then passes the result to a local LNES-22 policy
harness.  The authority decision is computed independently of the proof verdict.

Mission axiom:  MODEL INFERENCE PROVENANCE ≠ EXECUTION AUTHORITY

Permitted consequences: mock filesystem action, mock command intent, mock USDC
transfer intent, local audit-log generation.  No real transactions, no real
shell execution from model output, no production API calls with privileged
credentials.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import pathlib
import sqlite3
import subprocess
import sys
try:
    import resource as _resource  # Linux only
    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False
import tempfile
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VERIFIER_PATH_DEFAULT = pathlib.Path(__file__).resolve().parents[1] / "upstream" / "bin" / "cp_verify"
EVIDENCE_DIR_DEFAULT  = pathlib.Path(__file__).resolve().parents[1] / "evidence"
POLICY_DIR            = pathlib.Path(__file__).resolve().parents[1] / "policy"
BRIDGE_PATH_DEFAULT   = pathlib.Path(__file__).resolve().parent / "lnes22_authority_bridge.py"

VERIFIER_TIMEOUT_SECS = 60
VERIFIER_MAX_OUTPUT   = 65_536       # bytes of stdout+stderr captured
MAX_MEMORY_BYTES      = 2 * 1024 ** 3  # 2 GB RLIMIT_AS guard (Linux only)

# Exit codes as documented in verifier/docs/output.md
EXIT_ACCEPTED     = 0
EXIT_REJECTED     = 1
EXIT_USAGE_ERROR  = 2
EXIT_PART_PASSED  = 3
EXIT_PLAN_ONLY    = 4
EXIT_NOT_CHECKED  = 5
EXIT_NOT_A_VERIF  = 14

ACCEPTED_EXITS    = {EXIT_ACCEPTED}
VERDICT_LINE_ACCEPT = {"YES"}         # or starts with "WITHIN LIMITS:"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class VerificationInput:
    trusted_commitment_id: str           # from pinned registry, NOT from proof sender
    config_dir:            pathlib.Path
    ivk_dir:               pathlib.Path
    request_file:          pathlib.Path
    output_token_file:     pathlib.Path
    proof_file:            pathlib.Path
    policy_name:           str = "exact-match"


@dataclasses.dataclass
class VerificationResult:
    accepted:         bool
    exit_code:        int
    last_line:        str
    stdout:           str
    stderr:           str
    commitment_id:    str
    covered_line:     str = ""
    result_v1_line:   str = ""
    proof_of_work:    str = ""
    request_digest:   str = ""
    output_digest:    str = ""
    proof_digest:     str = ""
    verifier_digest:  str = ""
    wall_clock_secs:  float = 0.0
    error_detail:     str = ""


@dataclasses.dataclass
class AuthorityRequest:
    evidence_record_id:     str
    verified_output_digest: str
    proposed_action:        str    # human-readable intent
    principal_id:           str
    requested_capability:   str    # must be in allowed set
    execution_target:       str
    resource_scope:         str
    session_id:             str
    policy_version:         str
    auth_reference:         str = ""  # OTET or delegation ref when required


@dataclasses.dataclass
class AuthorityDecision:
    allowed:   bool
    reason:    str
    action_id: str = ""
    # EDT-FP-002 §III: canonical binding hash set by evaluate_authority_real().
    # execute_canonical_bound_mock_action() re-derives this hash at the execution
    # boundary and verifies it matches before allowing any mock action to run.
    canonical_binding_hash: str = ""


@dataclasses.dataclass
class CanonicalActionRequest:
    """
    12-field canonical action request -- EDT-FP-002 §III.

    Every field contributes to a SHA-256 canonical binding hash.  Altering
    any single field produces a different hash, ensuring evidence is tightly
    bound to the exact request that was authorized.  The hash can be stored
    alongside any proof artifact as an independent audit trail entry.
    """
    request_id:          str    # UUID4 -- unique per request
    session_id:          str    # session scope
    principal_id:        str    # identity making the request
    capability_id:       str    # e.g. "FP.ECHO_INTENT"
    capability_hash:     str    # SHA-256 of capability definition (content-addressed)
    commitment_id:       str    # FlashProve commitment ID from trusted registry
    request_digest:      str    # SHA-256 of .req file (empty string if not applicable)
    output_token_digest: str    # SHA-256 of .y file (empty string if not applicable)
    proof_digest:        str    # SHA-256 of .proof file (empty string if not applicable)
    verifier_digest:     str    # SHA-256 of cp_verify binary (empty if not applicable)
    timestamp_utc:       str    # ISO 8601, e.g. "2026-11-05T12:00:00Z"
    target_environment:  str    # scope limiter, e.g. "LOCAL_SANDBOX"
    # IMPORTANT: the empty-tuple default means "caller explicitly certifies no
    # model-generated params".  This is NOT a "field not considered" default.
    # Callers MUST set this to the actual set of model-generated parameter names
    # when any exist -- omitting it is an explicit claim that none are present.
    protected_model_generated_params: tuple = dataclasses.field(default_factory=tuple)


@dataclasses.dataclass
class DemoResult:
    case:                str
    proof_verdict:       str   # PROOF_ACCEPTED | PROOF_REJECTED | PROOF_NOT_CHECKED
    authority_verdict:   str   # AUTHORITY_GRANTED | AUTHORITY_DENIED
    action_outcome:      str   # MOCK_ACTION_EXECUTED | ACTION_NOT_EXECUTED
    evidence_record_id:  str
    summary:             str


# ---------------------------------------------------------------------------
# Trusted commitment registry
# ---------------------------------------------------------------------------

class TrustedCommitmentRegistry:
    """
    Load from policy/allowed_commitments.json.
    A proof sender MUST NOT be allowed to supply an arbitrary commitment ID —
    this registry is the independent source of trust.
    """
    def __init__(self, path: pathlib.Path | None = None):
        p = path or POLICY_DIR / "allowed_commitments.json"
        with p.open() as f:
            raw: dict[str, Any] = json.load(f)
        self._entries: dict[str, dict[str, Any]] = {
            e["commitment_id"]: e for e in raw.get("commitments", [])
        }

    def is_trusted(self, commitment_id: str) -> bool:
        return commitment_id in self._entries

    def get_entry(self, commitment_id: str) -> dict[str, Any] | None:
        return self._entries.get(commitment_id)


# ---------------------------------------------------------------------------
# Evidence store
# ---------------------------------------------------------------------------

class LocalEvidenceStore:
    def __init__(self, evidence_dir: pathlib.Path | None = None):
        self._dir = evidence_dir or EVIDENCE_DIR_DEFAULT
        self._dir.mkdir(parents=True, exist_ok=True)

    def record(self, payload: dict[str, Any]) -> str:
        record_id = str(uuid.uuid4())
        payload["record_id"]  = record_id
        payload["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        dest = self._dir / f"{record_id}.json"
        dest.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return record_id


# ---------------------------------------------------------------------------
# Input file hashing
# ---------------------------------------------------------------------------

def _sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_binary(path: pathlib.Path) -> str:
    return _sha256_file(path)


# ---------------------------------------------------------------------------
# Subprocess resource limits (Linux only)
# ---------------------------------------------------------------------------

def _apply_resource_limits() -> None:
    if not _HAS_RESOURCE:
        return
    try:
        _resource.setrlimit(_resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
    except (AttributeError, OSError):
        pass


# ---------------------------------------------------------------------------
# Core verifier invocation
# ---------------------------------------------------------------------------

def run_verifier(
    vi: VerificationInput,
    verifier_path: pathlib.Path | None = None,
) -> VerificationResult:
    """
    Execute cp_verify in a constrained subprocess with structured arguments —
    no shell interpolation, fixed executable path, input file allowlisting.

    Returns a VerificationResult.  Never raises; all failures become a
    VerificationResult with accepted=False and an error_detail string.
    """
    vp = verifier_path or VERIFIER_PATH_DEFAULT
    if not vp.is_file():
        return VerificationResult(
            accepted=False, exit_code=-1, last_line="",
            stdout="", stderr="",
            commitment_id=vi.trusted_commitment_id,
            error_detail=f"verifier binary not found: {vp}",
        )

    # Allowlist: only files from the input struct may be passed
    for label, p in [
        ("config_dir",   vi.config_dir),
        ("ivk_dir",      vi.ivk_dir),
        ("request_file", vi.request_file),
        ("output_token_file", vi.output_token_file),
        ("proof_file",   vi.proof_file),
    ]:
        if not p.exists():
            return VerificationResult(
                accepted=False, exit_code=-1, last_line="",
                stdout="", stderr="",
                commitment_id=vi.trusted_commitment_id,
                error_detail=f"input file/dir missing [{label}]: {p}",
            )

    request_digest      = _sha256_file(vi.request_file)
    output_digest       = _sha256_file(vi.output_token_file)
    proof_digest        = _sha256_file(vi.proof_file)
    verifier_digest     = _sha256_binary(vp)

    # Structured argument vector — no shell=True, no string interpolation
    cmd = [
        str(vp),
        str(vi.config_dir),
        str(vi.ivk_dir),
        str(vi.request_file),
        str(vi.output_token_file),
        str(vi.proof_file),
        "-id", vi.trusted_commitment_id,
    ]

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=VERIFIER_TIMEOUT_SECS,
            preexec_fn=_apply_resource_limits,
            shell=False,
        )
        elapsed = time.monotonic() - t0
        stdout  = proc.stdout.decode("utf-8", errors="replace")[:VERIFIER_MAX_OUTPUT]
        stderr  = proc.stderr.decode("utf-8", errors="replace")[:VERIFIER_MAX_OUTPUT]
        exit_code = proc.returncode

    except subprocess.TimeoutExpired:
        return VerificationResult(
            accepted=False, exit_code=-9, last_line="TIMEOUT",
            stdout="", stderr="",
            commitment_id=vi.trusted_commitment_id,
            request_digest=request_digest, output_digest=output_digest,
            proof_digest=proof_digest, verifier_digest=verifier_digest,
            error_detail=f"verifier exceeded {VERIFIER_TIMEOUT_SECS}s timeout",
        )
    except Exception as exc:
        return VerificationResult(
            accepted=False, exit_code=-1, last_line="SUBPROCESS_FAILURE",
            stdout="", stderr="",
            commitment_id=vi.trusted_commitment_id,
            request_digest=request_digest, output_digest=output_digest,
            proof_digest=proof_digest, verifier_digest=verifier_digest,
            error_detail=f"subprocess error: {exc}",
        )

    lines       = [l for l in stdout.splitlines() if l.strip()]
    last_line   = lines[-1] if lines else ""
    covered     = next((l for l in lines if l.startswith("covered:")), "")
    result_v1   = next((l for l in lines if l.startswith("result-v1")), "")
    proof_work  = next((l for l in lines if l.startswith("proof of work:")), "")

    # Acceptance requires BOTH correct exit code AND accepted verdict line
    # Do not equate exit-code 0 alone with authorization.
    verdict_accepted = (
        exit_code == EXIT_ACCEPTED and (
            last_line == "YES" or last_line.startswith("WITHIN LIMITS:")
        )
    )

    return VerificationResult(
        accepted=verdict_accepted,
        exit_code=exit_code,
        last_line=last_line,
        stdout=stdout,
        stderr=stderr,
        commitment_id=vi.trusted_commitment_id,
        covered_line=covered,
        result_v1_line=result_v1,
        proof_of_work=proof_work,
        request_digest=request_digest,
        output_digest=output_digest,
        proof_digest=proof_digest,
        verifier_digest=verifier_digest,
        wall_clock_secs=round(elapsed, 3),
    )


# ---------------------------------------------------------------------------
# LNES-22 local policy harness (simulated, not production wired)
# ---------------------------------------------------------------------------

# Capabilities allowed for auto-evaluation (INFORMATIONAL or REVERSIBLE risk).
# This mirrors capability_registry.py's AUTO_EVALUATION_ELIGIBLE logic.
AUTO_EVAL_CAPABILITIES = {
    "MOCK.READ_FILE",
    "MOCK.LOG_EVENT",
    "MOCK.ECHO_INTENT",
    "MOCK.SIMULATED_TRANSFER",   # mock-only: no real funds moved
}

# Capabilities that require proof-required gating (always check proof first)
PROOF_REQUIRED_CAPABILITIES = {
    "MOCK.SIMULATED_TRANSFER",
    "MOCK.ECHO_INTENT",
}

# Capabilities that are never permitted regardless of proof status
ALWAYS_DENIED_CAPABILITIES = {
    "EXECUTE_SHELL",
    "SETTLEMENT.REAL",
    "TREASURY.TRANSFER",
    "BLOCKCHAIN.DEPLOY",
    "NETWORK.OPEN",
    "FILESYSTEM.MODIFY_PRODUCTION",
}


def evaluate_authority(
    request: AuthorityRequest,
    verification: VerificationResult,
) -> AuthorityDecision:
    """
    Independent LNES-22 policy harness.  The authority decision is computed
    independently of FlashProve's acceptance verdict — proof acceptance alone
    does NOT grant authority.

    This is a local simulation harness.  It is NOT connected to the production
    LNES-22 service.  It mirrors the capability_registry / policy_gate posture:
    pure function, default-deny, every path must explicitly reach allowed=True.
    """
    cap = request.requested_capability

    # Hard deny — no proof status changes this
    if cap in ALWAYS_DENIED_CAPABILITIES:
        return AuthorityDecision(
            allowed=False,
            reason=f"capability {cap!r} is unconditionally denied; "
                   "no proof status overrides this",
        )

    # Unknown capability — treat as DENY (closed vocabulary, same as LNES-22)
    if cap not in AUTO_EVAL_CAPABILITIES:
        return AuthorityDecision(
            allowed=False,
            reason=f"capability {cap!r} not in allowed vocabulary — "
                   "unmapped capability, deny by default",
        )

    # Principal must be non-empty — checked before proof gate
    if not request.principal_id:
        return AuthorityDecision(
            allowed=False,
            reason="principal_id is empty — cannot establish identity",
        )

    # Session must be non-empty — checked before proof gate
    if not request.session_id:
        return AuthorityDecision(
            allowed=False,
            reason="session_id is empty — cannot bind action to session",
        )

    # Proof-required gate: if the capability requires a valid proof and
    # verification failed, deny regardless of anything else
    if cap in PROOF_REQUIRED_CAPABILITIES and not verification.accepted:
        return AuthorityDecision(
            allowed=False,
            reason=f"capability {cap!r} requires PROOF_ACCEPTED but "
                   f"verification result was: exit={verification.exit_code} "
                   f"last_line={verification.last_line!r}",
        )

    # All checks passed
    return AuthorityDecision(
        allowed=True,
        reason=f"capability {cap!r} passed all local LNES-22 harness checks "
               "(simulated — not wired to production LNES-22 service)",
        action_id=str(uuid.uuid4()),
    )


# ---------------------------------------------------------------------------
# Canonical binding helpers (EDT-FP-002 §III)
# ---------------------------------------------------------------------------

def _canonical_json(d: dict[str, Any]) -> str:
    """Sorted keys, no whitespace, ensure_ascii=False — same formula as LNES-22."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_action_request_hash(req: CanonicalActionRequest) -> str:
    """SHA-256 of canonical JSON of all 12 binding fields."""
    fields = {
        "capability_hash":     req.capability_hash,
        "capability_id":       req.capability_id,
        "commitment_id":       req.commitment_id,
        "output_token_digest": req.output_token_digest,
        "principal_id":        req.principal_id,
        "proof_digest":        req.proof_digest,
        "request_digest":      req.request_digest,
        "request_id":          req.request_id,
        "session_id":          req.session_id,
        "target_environment":  req.target_environment,
        "timestamp_utc":       req.timestamp_utc,
        "verifier_digest":     req.verifier_digest,
    }
    return hashlib.sha256(_canonical_json(fields).encode("utf-8")).hexdigest()


def content_replay_hash(req: CanonicalActionRequest) -> str:
    """
    SHA-256 of canonical JSON of the 10 content fields (excluding request_id
    and timestamp_utc).  Two requests with identical content but different IDs
    or timestamps have the same content_replay_hash and will be detected as
    replays.
    """
    fields = {
        "capability_hash":     req.capability_hash,
        "capability_id":       req.capability_id,
        "commitment_id":       req.commitment_id,
        "output_token_digest": req.output_token_digest,
        "principal_id":        req.principal_id,
        "proof_digest":        req.proof_digest,
        "request_digest":      req.request_digest,
        "session_id":          req.session_id,
        "target_environment":  req.target_environment,
        "verifier_digest":     req.verifier_digest,
    }
    return hashlib.sha256(_canonical_json(fields).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Replay protection store (EDT-FP-002 §IV)
# ---------------------------------------------------------------------------

class ReplayProtectionStore:
    """
    Durable, multiprocess-safe replay protection store.

    Backed by SQLite with BEGIN EXCLUSIVE transactions for atomic check-and-record.
    Multiple concurrent processes racing check_and_record_atomic() on the same
    content hash will serialize: exactly one returns False (new request, now
    recorded); all others return True (replay detected, nothing inserted).

    The earlier JSON/dict backend was single-process only and could not guarantee
    this property. This implementation closes that gap (Codex audit M-3 fix upgraded
    to full multiprocess safety per EDT-FP-002 final-RC directive item 2).

    Thread/process safety: SQLite file-level locking via BEGIN EXCLUSIVE.
    """

    def __init__(self, store_path: pathlib.Path | None = None,
                 evidence_dir: pathlib.Path | None = None):
        d = evidence_dir or EVIDENCE_DIR_DEFAULT
        d.mkdir(parents=True, exist_ok=True)
        self._path = store_path or (d / "replay_protection_store.db")
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self._path), timeout=10)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS replay_seen (
                    replay_hash            TEXT PRIMARY KEY,
                    canonical_binding_hash TEXT NOT NULL DEFAULT '',
                    decision               TEXT NOT NULL DEFAULT '',
                    first_seen_utc         TEXT NOT NULL DEFAULT '',
                    record_id              TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def check_replay(self, replay_hash: str) -> bool:
        """Non-atomic precheck. Use check_and_record_atomic() for process-safe operation."""
        conn = sqlite3.connect(str(self._path), timeout=10)
        try:
            row = conn.execute(
                "SELECT 1 FROM replay_seen WHERE replay_hash = ?", (replay_hash,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def record(self, replay_hash: str, binding_hash: str,
               decision: str, record_id: str = "") -> None:
        """Non-atomic INSERT OR IGNORE. Use check_and_record_atomic() for process-safe operation."""
        conn = sqlite3.connect(str(self._path), timeout=10)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO replay_seen "
                "(replay_hash, canonical_binding_hash, decision, first_seen_utc, record_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (replay_hash, binding_hash, decision,
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), record_id),
            )
            conn.commit()
        finally:
            conn.close()

    def check_and_record_atomic(
        self, replay_hash: str, binding_hash: str = "",
        decision: str = "PENDING", record_id: str = ""
    ) -> bool:
        """
        Atomically check and conditionally record replay_hash.

        Returns True  — replay detected (hash already present, nothing inserted).
        Returns False — new request (hash not present, now inserted).

        Process-safe: uses SQLite isolation_level=None with BEGIN EXCLUSIVE.
        In a race between N concurrent processes on the same replay_hash, SQLite
        serializes all callers; exactly one process returns False (the winner that
        inserts the record); all others find the row present and return True.
        """
        conn = sqlite3.connect(str(self._path), timeout=10, isolation_level=None)
        try:
            conn.execute("BEGIN EXCLUSIVE")
            row = conn.execute(
                "SELECT 1 FROM replay_seen WHERE replay_hash = ?", (replay_hash,)
            ).fetchone()
            if row is not None:
                conn.execute("ROLLBACK")
                return True  # replay detected
            conn.execute(
                "INSERT INTO replay_seen "
                "(replay_hash, canonical_binding_hash, decision, first_seen_utc, record_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (replay_hash, binding_hash, decision,
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), record_id),
            )
            conn.execute("COMMIT")
            return False  # new request, now recorded
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def get_entry(self, replay_hash: str) -> "dict[str, Any] | None":
        """Return stored entry dict for replay_hash, or None if not found."""
        conn = sqlite3.connect(str(self._path), timeout=10)
        try:
            row = conn.execute(
                "SELECT replay_hash, canonical_binding_hash, decision, "
                "first_seen_utc, record_id "
                "FROM replay_seen WHERE replay_hash = ?",
                (replay_hash,),
            ).fetchone()
            if row is None:
                return None
            return {
                "canonical_binding_hash": row[1],
                "decision":               row[2],
                "first_seen_utc":         row[3],
                "record_id":              row[4],
            }
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Real authority gateway (EDT-FP-002 §II)
# ---------------------------------------------------------------------------

class RealAuthorityGateway:
    """
    Calls lnes22_authority_bridge.py as a subprocess.

    When LNES22_SOURCE_PATH is set to a valid directory containing
    policy_gate.py, the bridge calls the real LNES-22 evaluate_tool_capability().
    Otherwise the bridge uses LOCAL_SIMULATION mode that mirrors the same
    check sequence.

    shell=False enforced: structured argument vector only.
    """

    def __init__(self, bridge_path: pathlib.Path | None = None,
                 lnes22_source_path: str | None = None):
        self._bridge = bridge_path or BRIDGE_PATH_DEFAULT
        self._lnes22_path = (
            lnes22_source_path or os.environ.get("LNES22_SOURCE_PATH", "")
        )

    def is_available(self) -> bool:
        return self._bridge.is_file()

    def evaluate(
        self,
        capability_id: str,
        delegation_valid: bool,
        replay_detected: bool,
        protected_model_generated_params: tuple,
    ) -> dict[str, Any]:
        if not self.is_available():
            return {
                "allowed": False, "requires_human_approval": False,
                "reason": "authority bridge not available",
                "engine": "BRIDGE_UNAVAILABLE",
                "capability_id": capability_id, "capability_hash": None,
            }
        request = {
            "capability_id": capability_id,
            "delegation_valid": delegation_valid,
            "replay_detected": replay_detected,
            "protected_model_generated_params": list(protected_model_generated_params),
        }
        env = dict(os.environ)
        if self._lnes22_path:
            env["LNES22_SOURCE_PATH"] = self._lnes22_path
        try:
            proc = subprocess.run(
                [sys.executable, str(self._bridge)],
                input=json.dumps(request).encode("utf-8"),
                capture_output=True,
                timeout=10,
                shell=False,
                env=env,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"bridge exit {proc.returncode}: "
                    f"{proc.stderr.decode('utf-8', errors='replace')[:200]}"
                )
            return json.loads(proc.stdout.decode("utf-8"))
        except Exception as exc:
            return {
                "allowed": False, "requires_human_approval": False,
                "reason": f"authority bridge error: {exc}",
                "engine": "BRIDGE_ERROR",
                "capability_id": capability_id, "capability_hash": None,
            }


# ---------------------------------------------------------------------------
# Real authority evaluation (EDT-FP-002 §II–§IV)
# ---------------------------------------------------------------------------

def evaluate_authority_real(
    request: CanonicalActionRequest,
    verification: VerificationResult,
    replay_store: "ReplayProtectionStore",
    gateway: "RealAuthorityGateway | None" = None,
) -> AuthorityDecision:
    """
    Authority evaluation using the LNES-22 bridge -- EDT-FP-002 §II-IV.

    1. Principal and session validation (always-deny on empty)
    2. Always-denied capability check (no proof status overrides)
    3. Atomic nonce consumption via ReplayProtectionStore.check_and_record_atomic()
       (process-safe: SQLite BEGIN EXCLUSIVE, consume-on-attempt before bridge call)
    4. LNES-22 bridge call (real evaluate_tool_capability() or LOCAL_SIMULATION)
    5. Return AuthorityDecision with canonical_binding_hash for pre-execution verification

    Proof acceptance semantically maps to delegation_valid for the bridge:
    an accepted FlashProve proof provides the evidence binding that serves as
    the delegation grant for capabilities with authority_requirements.

    Decision labeled with engine name so simulated vs. real is always visible.
    """
    cap = request.capability_id

    if not request.principal_id:
        return AuthorityDecision(
            allowed=False,
            reason="principal_id is empty -- cannot establish identity",
        )

    if not request.session_id:
        return AuthorityDecision(
            allowed=False,
            reason="session_id is empty -- cannot bind action to session",
        )

    if cap in ALWAYS_DENIED_CAPABILITIES:
        return AuthorityDecision(
            allowed=False,
            reason=f"capability {cap!r} is unconditionally denied; "
                   "no proof status overrides this",
        )

    crh = content_replay_hash(request)
    bh  = canonical_action_request_hash(request)

    # Atomic nonce consumption (process-safe, SQLite BEGIN EXCLUSIVE).
    # Nonce is consumed BEFORE the bridge call: prevents nonce-reuse via
    # deliberate bridge errors (consume-on-attempt, not consume-on-success).
    replay_detected = replay_store.check_and_record_atomic(crh, bh, "PENDING")

    # Proof acceptance is the delegation evidence for authority_requirements
    delegation_valid = verification.accepted

    gw = gateway if gateway is not None else RealAuthorityGateway()
    result = gw.evaluate(
        capability_id=cap,
        delegation_valid=delegation_valid,
        replay_detected=replay_detected,
        protected_model_generated_params=request.protected_model_generated_params,
    )

    engine = result.get("engine", "UNKNOWN")
    reason = result.get("reason", "")
    action_id = str(uuid.uuid4()) if result.get("allowed") else ""

    return AuthorityDecision(
        allowed=result.get("allowed", False),
        reason=f"{reason} [engine={engine}]",
        action_id=action_id,
        canonical_binding_hash=bh,
    )


# ---------------------------------------------------------------------------
# Canonical-bound mock executor (EDT-FP-002 §III — pre-execution binding check)
# ---------------------------------------------------------------------------

def execute_canonical_bound_mock_action(
    canonical_req: CanonicalActionRequest,
    authority: AuthorityDecision,
    store: LocalEvidenceStore,
) -> DemoResult:
    """
    Execute a mock action with pre-execution canonical binding verification.

    Immediately before the mock execution boundary, re-derives
    canonical_action_request_hash from canonical_req and verifies it matches
    authority.canonical_binding_hash. Any hash mismatch blocks execution and
    returns ACTION_NOT_EXECUTED — preventing substitution attacks where an
    authorization for operation A is reused to execute operation B.

    Capability authority limits (verified here and in tests):
      FP.ECHO_INTENT → TOOL.WRITE_STAGED (REVERSIBLE, staging dir only).
        Actual execution writes only to the evidence store (a local JSON file).
        No path to production filesystem modification.
      FP.SIMULATED_TRANSFER → TOOL.HTTP_REQUEST (COMPENSATABLE).
        COMPENSATABLE always requires human approval in auto mode — this path
        is only reachable via a hypothetical authority override. Actual execution
        writes only a mock audit record. No network call is made.
    """
    cap = canonical_req.capability_id

    if not authority.allowed:
        return DemoResult(
            case=cap,
            proof_verdict="PROOF_NOT_CHECKED",
            authority_verdict="AUTHORITY_DENIED",
            action_outcome="ACTION_NOT_EXECUTED",
            evidence_record_id="",
            summary=f"Action blocked: {authority.reason}",
        )

    # Pre-execution binding check
    execution_binding_hash = canonical_action_request_hash(canonical_req)
    if authority.canonical_binding_hash and execution_binding_hash != authority.canonical_binding_hash:
        return DemoResult(
            case=cap,
            proof_verdict="PROOF_NOT_CHECKED",
            authority_verdict="AUTHORITY_DENIED",
            action_outcome="ACTION_NOT_EXECUTED",
            evidence_record_id="",
            summary=(
                "PRE_EXECUTION_BINDING_CHECK_FAILED: canonical binding hash mismatch "
                f"at execution boundary — "
                f"authorized={authority.canonical_binding_hash[:16]}... "
                f"executing={execution_binding_hash[:16]}..."
            ),
        )

    # Capability → mock execution outcome
    # Comments confirm neither FP.ECHO_INTENT nor FP.SIMULATED_TRANSFER acquires
    # real authority beyond writing to the local evidence store.
    _mock_outcomes: dict[str, str] = {
        "FP.READ_FILE":  "MOCK_READ: simulated file content returned",
        "FP.LOG_EVENT":  "MOCK_LOG: event appended to local audit log",
        # REVERSIBLE: staging dir only; this mock writes to evidence store, no filesystem write
        "FP.ECHO_INTENT": (
            "MOCK_ECHO: agent intent recorded (evidence store; no filesystem write)"
        ),
        # COMPENSATABLE: always requires human approval in auto mode; no network call made
        "FP.SIMULATED_TRANSFER": (
            "MOCK_TRANSFER: simulated transfer intent recorded (no funds; no network call)"
        ),
    }
    mock_outcome = _mock_outcomes.get(cap, f"MOCK_ACTION: intent recorded for {cap!r}")

    record_id = store.record({
        "type":                   "canonical_bound_execution",
        "capability_id":          cap,
        "principal_id":           canonical_req.principal_id,
        "session_id":             canonical_req.session_id,
        "canonical_binding_hash": execution_binding_hash,
        "pre_exec_binding_check": "PASS",
        "action_id":              authority.action_id,
        "commitment_id":          canonical_req.commitment_id,
        "target_environment":     canonical_req.target_environment,
        "outcome":                mock_outcome,
    })

    return DemoResult(
        case=cap,
        proof_verdict="PROOF_NOT_CHECKED",
        authority_verdict="AUTHORITY_GRANTED",
        action_outcome="MOCK_ACTION_EXECUTED",
        evidence_record_id=record_id,
        summary=mock_outcome,
    )


# ---------------------------------------------------------------------------
# Mock action executor (simulated consequences only)
# ---------------------------------------------------------------------------

def execute_mock_action(
    request: AuthorityRequest,
    authority: AuthorityDecision,
    verification: VerificationResult,
    store: LocalEvidenceStore,
) -> DemoResult:
    """
    Execute the simulated consequence of an authorized request.
    Permitted: mock filesystem action, mock command intent, mock USDC transfer
    intent, local audit-log generation.
    Prohibited: real transactions, real shell execution, production API calls.
    """
    record_id = store.record({
        "type":                  "authority_decision",
        "case":                  "demo",
        "evidence_record_id":    request.evidence_record_id,
        "verified_output_digest": verification.output_digest,
        "proof_accepted":        verification.accepted,
        "proof_exit_code":       verification.exit_code,
        "proof_last_line":       verification.last_line,
        "commitment_id":         verification.commitment_id,
        "proposed_action":       request.proposed_action,
        "requested_capability":  request.requested_capability,
        "principal_id":          request.principal_id,
        "session_id":            request.session_id,
        "execution_target":      request.execution_target,
        "resource_scope":        request.resource_scope,
        "policy_version":        request.policy_version,
        "authority_allowed":     authority.allowed,
        "authority_reason":      authority.reason,
        "action_id":             authority.action_id,
        "verifier_digest":       verification.verifier_digest,
        "request_digest":        verification.request_digest,
        "output_digest":         verification.output_digest,
        "proof_digest":          verification.proof_digest,
    })

    if not authority.allowed:
        proof_verdict = (
            "PROOF_ACCEPTED" if verification.accepted else
            ("PROOF_NOT_CHECKED" if verification.exit_code == EXIT_NOT_CHECKED else "PROOF_REJECTED")
        )
        return DemoResult(
            case=request.requested_capability,
            proof_verdict=proof_verdict,
            authority_verdict="AUTHORITY_DENIED",
            action_outcome="ACTION_NOT_EXECUTED",
            evidence_record_id=record_id,
            summary=f"Action blocked: {authority.reason}",
        )

    # Simulate action — write intent to audit log, no real side effects
    mock_outcome = {
        "MOCK.READ_FILE":           "MOCK_READ: simulated file content returned",
        "MOCK.LOG_EVENT":           "MOCK_LOG: event appended to local audit log",
        "MOCK.ECHO_INTENT":         "MOCK_ECHO: agent intent recorded",
        "MOCK.SIMULATED_TRANSFER":  "MOCK_TRANSFER: simulated 1.00 USDC transfer intent recorded (no funds moved)",
    }.get(request.requested_capability, "MOCK_ACTION: intent recorded")

    store.record({
        "type":          "mock_action_executed",
        "action_id":     authority.action_id,
        "capability":    request.requested_capability,
        "target":        request.execution_target,
        "outcome":       mock_outcome,
        "principal_id":  request.principal_id,
        "session_id":    request.session_id,
    })

    return DemoResult(
        case=request.requested_capability,
        proof_verdict="PROOF_ACCEPTED",
        authority_verdict="AUTHORITY_GRANTED",
        action_outcome="MOCK_ACTION_EXECUTED",
        evidence_record_id=record_id,
        summary=mock_outcome,
    )


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------

def run_demo_case(
    label:             str,
    vi:                VerificationInput,
    authority_request: AuthorityRequest,
    verifier_path:     pathlib.Path | None = None,
    evidence_dir:      pathlib.Path | None = None,
    registry:          TrustedCommitmentRegistry | None = None,
) -> DemoResult:
    """
    Execute one complete demo case:
      1. Validate the commitment ID against the trusted registry
      2. Run the verifier in a constrained subprocess
      3. Evaluate authority independently of proof verdict
      4. Execute the simulated (mock) consequence if authorized
      5. Persist the evidence record
    """
    store = LocalEvidenceStore(evidence_dir)

    # Commitment ID must come from the trusted registry, not from the proof sender
    reg = registry or TrustedCommitmentRegistry()
    if not reg.is_trusted(vi.trusted_commitment_id):
        record_id = store.record({
            "type":          "commitment_rejected",
            "commitment_id": vi.trusted_commitment_id,
            "reason":        "commitment_id not in trusted registry",
        })
        return DemoResult(
            case=label,
            proof_verdict="PROOF_REJECTED",
            authority_verdict="AUTHORITY_DENIED",
            action_outcome="ACTION_NOT_EXECUTED",
            evidence_record_id=record_id,
            summary=f"Rejected: commitment_id {vi.trusted_commitment_id!r} not in trusted registry",
        )

    vr = run_verifier(vi, verifier_path)

    # Update evidence request ID before authority evaluation
    authority_request = dataclasses.replace(
        authority_request,
        evidence_record_id=authority_request.evidence_record_id or vr.request_digest[:16],
        verified_output_digest=vr.output_digest,
    )

    ad = evaluate_authority(authority_request, vr)
    return execute_mock_action(authority_request, ad, vr, store)
