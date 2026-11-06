#!/usr/bin/env bash
# EDT-FP-001: Clone FlashProve upstream and build the CPU verifier (Route 1).
# Run as a non-root user from this directory (exergynet-flashprove/upstream/).
# Requires: Linux, bash, g++ 13+, make, python3, unzip
# WSL2: run from the upstream/ directory inside your exergynet-flashprove checkout
set -euo pipefail

UPSTREAM_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(dirname "$UPSTREAM_DIR")"
LOG="$UPSTREAM_DIR/setup.log"

echo "[EDT-FP-001] FlashProve upstream setup — $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee "$LOG"
echo "Workspace: $WORKSPACE_DIR" | tee -a "$LOG"
echo "Upstream:  $UPSTREAM_DIR"  | tee -a "$LOG"

# ── Step 1: Clone or verify upstream ──────────────────────────────────────
if [ -f "$UPSTREAM_DIR/AGENTS.md" ]; then
  echo "[SKIP] upstream already present (AGENTS.md found)" | tee -a "$LOG"
else
  echo "[STEP 1] Cloning anthropics/FlashProve ..." | tee -a "$LOG"
  # Clone into a temp dir then move contents here (can't clone into non-empty dir)
  TMP_CLONE="$(mktemp -d)"
  git clone --depth 1 https://github.com/anthropics/FlashProve "$TMP_CLONE/flashprove" 2>&1 | tee -a "$LOG"
  cp -r "$TMP_CLONE/flashprove/." "$UPSTREAM_DIR/"
  rm -rf "$TMP_CLONE"
  echo "[OK] Clone complete" | tee -a "$LOG"
fi

# ── Record upstream commit ─────────────────────────────────────────────────
GIT_COMMIT="$(git -C "$UPSTREAM_DIR" rev-parse HEAD 2>/dev/null || echo 'unknown')"
echo "[INFO] Upstream commit: $GIT_COMMIT" | tee -a "$LOG"
echo "$GIT_COMMIT" > "$UPSTREAM_DIR/UPSTREAM_COMMIT.txt"

# ── Step 2: Build cp_verify (Route 1) ─────────────────────────────────────
echo "[STEP 2] Building cp_verify via verifier/build.sh ..." | tee -a "$LOG"
cd "$UPSTREAM_DIR"

# Run as non-root; build.sh will refuse to work in a root-owned directory
BUILD_LOG="$UPSTREAM_DIR/build.log"
echo "build started $(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$BUILD_LOG"
nohup bash -c 'verifier/build.sh; echo "exit code $?"' >> "$BUILD_LOG" 2>&1 &
BUILD_PID=$!
echo "[INFO] Build PID: $BUILD_PID" | tee -a "$LOG"
echo "[INFO] Tailing build.log ... (may take 1-2 minutes)" | tee -a "$LOG"

# Wait for build to complete (poll every 5s, max 10 min)
ELAPSED=0
while ! grep -q "^exit code" "$BUILD_LOG" 2>/dev/null; do
  sleep 5
  ELAPSED=$((ELAPSED + 5))
  if [ $ELAPSED -ge 600 ]; then
    echo "[FAIL] Build did not complete within 10 minutes" | tee -a "$LOG"
    exit 1
  fi
done

EXIT_CODE="$(grep "^exit code" "$BUILD_LOG" | tail -1 | awk '{print $3}')"
BUILD_LINE="$(grep "^THE VERIFIER IS BUILT:" "$BUILD_LOG" | tail -1 || true)"
echo "[BUILD] Exit code: $EXIT_CODE" | tee -a "$LOG"
echo "[BUILD] $BUILD_LINE" | tee -a "$LOG"

if [ "$EXIT_CODE" != "0" ]; then
  echo "[FAIL] verifier/build.sh exited with code $EXIT_CODE" | tee -a "$LOG"
  tail -20 "$BUILD_LOG" | tee -a "$LOG"
  exit 1
fi

# ── Step 3: Hash artifacts ─────────────────────────────────────────────────
echo "[STEP 3] Hashing artifacts ..." | tee -a "$LOG"
sha256sum "$UPSTREAM_DIR/bin/cp_verify" \
          "$UPSTREAM_DIR/examples/accepted-proof/example.proof" \
          "$UPSTREAM_DIR/examples/accepted-proof/example.req" \
          "$UPSTREAM_DIR/examples/accepted-proof/example.y" \
          "$UPSTREAM_DIR/examples/accepted-proof/ID.txt" \
          2>/dev/null | tee "$UPSTREAM_DIR/ARTIFACT_HASHES.txt" | tee -a "$LOG"

# ── Step 4: Run reference verification ────────────────────────────────────
echo "[STEP 4] Running reference proof verification ..." | tee -a "$LOG"
COMMITMENT_ID="$(cat "$UPSTREAM_DIR/examples/accepted-proof/ID.txt")"
echo "[INFO] Commitment ID: $COMMITMENT_ID" | tee -a "$LOG"

VERIFY_OUTPUT="$(
  "$UPSTREAM_DIR/bin/cp_verify" \
    "$UPSTREAM_DIR/examples/accepted-proof/config" \
    "$UPSTREAM_DIR/examples/accepted-proof/ivk" \
    "$UPSTREAM_DIR/examples/accepted-proof/example.req" \
    "$UPSTREAM_DIR/examples/accepted-proof/example.y" \
    "$UPSTREAM_DIR/examples/accepted-proof/example.proof" \
    -id "$COMMITMENT_ID" 2>&1
)"
VERIFY_EXIT=$?
LAST_LINE="$(echo "$VERIFY_OUTPUT" | tail -1)"

echo "[VERIFY] Exit code: $VERIFY_EXIT" | tee -a "$LOG"
echo "[VERIFY] Last line: $LAST_LINE"   | tee -a "$LOG"
echo "$VERIFY_OUTPUT" > "$UPSTREAM_DIR/reference_verify_output.txt"

if [ "$VERIFY_EXIT" = "0" ] && [ "$LAST_LINE" = "YES" ]; then
  echo "" | tee -a "$LOG"
  echo "EDT_FP_001_VERIFIER_QUALIFIED" | tee -a "$LOG"
  echo "  - cp_verify built successfully" | tee -a "$LOG"
  echo "  - Reference proof accepted: YES" | tee -a "$LOG"
  echo "  - Upstream commit: $GIT_COMMIT" | tee -a "$LOG"
else
  echo "[FAIL] Reference verification failed" | tee -a "$LOG"
  echo "  Exit: $VERIFY_EXIT  Last: $LAST_LINE" | tee -a "$LOG"
  exit 1
fi
