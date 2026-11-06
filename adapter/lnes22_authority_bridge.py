#!/usr/bin/env python3
"""
ExergyNet x FlashProve -- LNES-22 Authority Bridge (EDT-FP-002)

Subprocess bridge: reads a JSON authority request from stdin, routes it to
either the real LNES-22 evaluate_tool_capability() (when LNES22_SOURCE_PATH
points at a directory containing policy_gate.py) or the local simulation,
and writes a JSON decision to stdout.

This file is the integration point between FlashProve's FP.* capability
vocabulary and LNES-22's TOOL.* capability vocabulary.  When the real LNES-22
source is available, FP.* capabilities are mapped to their TOOL.* equivalents
and the real evaluate_tool_capability() is called with no modification.  When
the source is not available, LOCAL_SIMULATION mirrors the same check sequence.

Usage (called as a subprocess from flashprove_shim.py):
    import subprocess, json, sys
    request = {"capability_id": "FP.ECHO_INTENT", "delegation_valid": True,
               "replay_detected": False, "protected_model_generated_params": []}
    proc = subprocess.run(
        [sys.executable, "adapter/lnes22_authority_bridge.py"],
        input=json.dumps(request).encode(), capture_output=True,
        timeout=10, shell=False,
    )
    result = json.loads(proc.stdout)

Environment:
    LNES22_SOURCE_PATH  -- absolute path to the directory containing
                           policy_gate.py + capability_registry.py
                           (e.g. the vendor/lnes22 directory of a local
                           ExergyNet development tree).
                           If unset or the path is invalid, falls back to
                           LOCAL_SIMULATION mode.

Labeling:
    "engine": "REAL_LNES22_LOCAL_DEVELOPMENT" -- real policy_gate.py called
    "engine": "LOCAL_SIMULATION"              -- local simulation mode
    "engine": "LOCAL_SIMULATION_IMPORT_ERROR" -- real source failed to import

CONSTRAINT: This module NEVER calls the production LNES-22 service, accesses
production signing keys, or performs any real financial operation.  It is a
local development integration bridge only.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Local FP.* capability definitions (FlashProve sandbox vocabulary)
# ---------------------------------------------------------------------------
# These are synthetic test identities -- not production LNES-22 tool entries.
# They mirror CapabilityDefinition's field structure and use the same
# RiskClass taxonomy.  "lnes22_mapping" names the TOOL.* capability used
# when calling the real LNES-22 engine (read-only: FlashProve never modifies
# the LNES-22 source files).

_INFO  = "INFORMATIONAL"
_REV   = "REVERSIBLE"
_COMP  = "COMPENSATABLE"
_AUTO_EVAL_ELIGIBLE = {_INFO, _REV}

_FP_CAPS: dict[str, dict[str, Any]] = {
    "FP.READ_FILE": {
        "capability_id": "FP.READ_FILE", "version": "0.1",
        "tool_name": "fp_read_file",
        "description": "FlashProve sandbox: read a file within the sandbox workspace.",
        "risk_class": _INFO, "resource_scope": "sandbox workspace filesystem (read-only)",
        "authority_requirements": [], "protected_parameters": [],
        "evidence_requirements": [], "replay_policy": "none", "enabled": True,
        "lnes22_mapping": "TOOL.READ_FILE",
    },
    "FP.LOG_EVENT": {
        "capability_id": "FP.LOG_EVENT", "version": "0.1",
        "tool_name": "fp_log_event",
        "description": "FlashProve sandbox: append an event to the local audit log.",
        "risk_class": _INFO, "resource_scope": "local audit log (append-only)",
        "authority_requirements": [], "protected_parameters": [],
        "evidence_requirements": [], "replay_policy": "none", "enabled": True,
        "lnes22_mapping": "TOOL.GIT_STATUS",
    },
    "FP.ECHO_INTENT": {
        "capability_id": "FP.ECHO_INTENT", "version": "0.1",
        "tool_name": "fp_echo_intent",
        "description": "FlashProve sandbox: record agent intent to the evidence store.",
        "risk_class": _REV, "resource_scope": "in-process evidence store",
        "authority_requirements": [], "protected_parameters": ["intent_text"],
        "evidence_requirements": [], "replay_policy": "none", "enabled": True,
        "lnes22_mapping": "TOOL.WRITE_STAGED",
    },
    "FP.SIMULATED_TRANSFER": {
        "capability_id": "FP.SIMULATED_TRANSFER", "version": "0.1",
        "tool_name": "fp_simulated_transfer",
        "description": "FlashProve sandbox: simulated transfer intent (no real funds).",
        "risk_class": _COMP, "resource_scope": "local simulation only -- no real network",
        "authority_requirements": ["REQUEST_EXTERNAL_CALL"],
        "protected_parameters": ["amount", "destination"],
        "evidence_requirements": ["proof_accepted"], "replay_policy": "single_use",
        "enabled": True,
        "lnes22_mapping": "TOOL.HTTP_REQUEST",
    },
}

# Legacy MOCK.* aliases -- backward compatibility with EDT-FP-001 vocabulary
_MOCK_ALIASES: dict[str, str] = {
    "MOCK.READ_FILE":           "FP.READ_FILE",
    "MOCK.LOG_EVENT":           "FP.LOG_EVENT",
    "MOCK.ECHO_INTENT":         "FP.ECHO_INTENT",
    "MOCK.SIMULATED_TRANSFER":  "FP.SIMULATED_TRANSFER",
}

_ALWAYS_DENIED = frozenset({
    "EXECUTE_SHELL", "SETTLEMENT.REAL", "TREASURY.TRANSFER",
    "BLOCKCHAIN.DEPLOY", "NETWORK.OPEN", "FILESYSTEM.MODIFY_PRODUCTION",
})


def _cap_hash(cap: dict[str, Any]) -> str:
    """Content-addressed hash using the same formula as capability_registry.capability_hash()."""
    body = {k: cap[k] for k in (
        "capability_id", "version", "tool_name", "description", "risk_class",
        "resource_scope", "authority_requirements", "protected_parameters",
        "evidence_requirements", "replay_policy", "enabled",
    )}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _resolve(capability_id: str) -> dict[str, Any] | None:
    cid = _MOCK_ALIASES.get(capability_id, capability_id)
    return _FP_CAPS.get(cid)


def _deny(reason: str, capability_id: Any, cap_hash: Any, engine: str,
          requires_human: bool = False) -> dict[str, Any]:
    return {
        "allowed": False, "requires_human_approval": requires_human,
        "reason": reason, "engine": engine,
        "capability_id": capability_id, "capability_hash": cap_hash,
    }


# ---------------------------------------------------------------------------
# Local simulation (mirrors evaluate_tool_capability() check order exactly)
# ---------------------------------------------------------------------------

def _evaluate_local(request: dict[str, Any]) -> dict[str, Any]:
    """
    Local simulation of LNES-22 evaluate_tool_capability().
    Check order matches policy_gate.py exactly:
      1. capability is None / unmapped
      2. replay_detected
      3. protected_model_generated_params non-empty
      4. authority_requirements not met
      5. risk_class not in AUTO_EVALUATION_ELIGIBLE
      6. ALLOW
    """
    capability_id = request.get("capability_id", "")
    replay_detected = bool(request.get("replay_detected"))
    protected_params = tuple(request.get("protected_model_generated_params", []))
    delegation_valid = request.get("delegation_valid")

    if capability_id in _ALWAYS_DENIED:
        return _deny(f"capability {capability_id!r} is unconditionally denied",
                     capability_id, None, "LOCAL_SIMULATION")

    cap = _resolve(capability_id)
    if cap is None:
        return _deny(f"capability {capability_id!r} not in vocabulary (DENY-by-default)",
                     None, None, "LOCAL_SIMULATION")

    h = _cap_hash(cap)

    if replay_detected:
        return _deny(f"replay detected for capability {capability_id!r}",
                     capability_id, h, "LOCAL_SIMULATION", requires_human=True)

    if protected_params:
        return _deny(
            f"protected parameter(s) {list(protected_params)!r} resolved to "
            f"MODEL_GENERATED origin for capability {capability_id!r} -- "
            "untrusted for a protected field",
            capability_id, h, "LOCAL_SIMULATION")

    if cap["authority_requirements"] and delegation_valid is not True:
        return _deny(
            f"capability {capability_id!r} requires authority "
            f"{cap['authority_requirements']!r} but delegation_valid={delegation_valid!r}",
            capability_id, h, "LOCAL_SIMULATION", requires_human=True)

    if cap["risk_class"] not in _AUTO_EVAL_ELIGIBLE:
        return _deny(
            f"risk_class {cap['risk_class']} requires explicit human approval, not auto-policy",
            capability_id, h, "LOCAL_SIMULATION", requires_human=True)

    return {
        "allowed": True, "requires_human_approval": False,
        "reason": f"capability {capability_id!r} passed all LOCAL_SIMULATION checks",
        "engine": "LOCAL_SIMULATION",
        "capability_id": capability_id, "capability_hash": h,
    }


# ---------------------------------------------------------------------------
# Real LNES-22 integration (read-only import, no modification of LNES-22 source)
# ---------------------------------------------------------------------------

def _evaluate_real(request: dict[str, Any], lnes22_path: pathlib.Path) -> dict[str, Any]:
    """
    Call the real LNES-22 evaluate_tool_capability() by importing from lnes22_path.
    Maps FP.*/MOCK.* capability IDs to their TOOL.* equivalents before calling.

    CONSTRAINT: lnes22_path is read-only.  This function never modifies any
    file in that directory.  It imports, calls, and returns.
    """
    capability_id = request.get("capability_id", "")

    if capability_id in _ALWAYS_DENIED:
        return _deny(f"capability {capability_id!r} is unconditionally denied",
                     capability_id, None, "REAL_LNES22_LOCAL_DEVELOPMENT")

    cid = _MOCK_ALIASES.get(capability_id, capability_id)
    local_cap = _FP_CAPS.get(cid)
    if local_cap is None:
        return _deny(f"capability {capability_id!r} not in FP vocabulary",
                     None, None, "REAL_LNES22_LOCAL_DEVELOPMENT")

    lnes22_tool_id: str = local_cap["lnes22_mapping"]  # e.g. "TOOL.READ_FILE"

    sys.path.insert(0, str(lnes22_path))
    try:
        from capability_registry import resolve_by_capability_id  # type: ignore[import]
        from capability_registry import capability_hash as lnes22_hash  # type: ignore[import]
        from policy_gate import evaluate_tool_capability  # type: ignore[import]
    except ImportError as exc:
        return _deny(f"LNES-22 import failed: {exc}", capability_id, None,
                     "LOCAL_SIMULATION_IMPORT_ERROR")
    finally:
        lnes22_str = str(lnes22_path)
        if lnes22_str in sys.path:
            sys.path.remove(lnes22_str)
        # Clear module cache so a second call with a different lnes22_path
        # (or a repointed LNES22_SOURCE_PATH) does not reuse stale imports.
        # Safe even if import failed — pop() is a no-op on absent keys.
        for _mod in ("capability_registry", "policy_gate"):
            sys.modules.pop(_mod, None)

    real_cap = resolve_by_capability_id(lnes22_tool_id)
    if real_cap is None:
        return _deny(f"LNES-22 tool {lnes22_tool_id!r} not in real registry",
                     capability_id, None, "REAL_LNES22_LOCAL_DEVELOPMENT")

    cap_hash = lnes22_hash(real_cap)

    decision = evaluate_tool_capability(
        capability=real_cap,
        delegation_valid=request.get("delegation_valid") is True,
        replay_detected=bool(request.get("replay_detected")),
        protected_model_generated_params=tuple(
            request.get("protected_model_generated_params", [])
        ),
    )

    return {
        "allowed": decision.allowed,
        "requires_human_approval": decision.requires_human_approval,
        "reason": decision.reason,
        "engine": "REAL_LNES22_LOCAL_DEVELOPMENT",
        "capability_id": capability_id,
        "lnes22_capability_id": lnes22_tool_id,
        "capability_hash": cap_hash,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    raw = sys.stdin.buffer.read(65537)
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps(_deny(f"invalid JSON input: {exc}", None, None, "LOCAL_SIMULATION")))
        return

    lnes22_src = os.environ.get("LNES22_SOURCE_PATH", "").strip()
    lnes22_path = pathlib.Path(lnes22_src) if lnes22_src else None

    if lnes22_path and lnes22_path.is_dir() and (lnes22_path / "policy_gate.py").is_file():
        result = _evaluate_real(request, lnes22_path)
    else:
        result = _evaluate_local(request)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
