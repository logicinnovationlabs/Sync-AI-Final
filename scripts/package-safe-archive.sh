#!/usr/bin/env bash
# Create a distribution archive that never includes secrets or local junk.
# Prefer git archive (honours .gitignore). Do NOT zip the raw working tree.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${1:-$(dirname "$ROOT")/SnyQ_Phase_2-safe-${STAMP}.zip}"

echo "Packaging from: $ROOT"
echo "Output:         $OUT"

rm -f "$OUT"
TMP_TAR="$(mktemp -t snyq-archive.XXXXXX).tar"
TMP_DIR="$(mktemp -d -t snyq-archive.XXXXXX)"
cleanup() {
  rm -f "$TMP_TAR"
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

git rev-parse --is-inside-work-tree >/dev/null
git archive --format=tar -o "$TMP_TAR" HEAD
mkdir -p "$TMP_DIR"
tar -xf "$TMP_TAR" -C "$TMP_DIR"

# Fail closed if tracked content somehow contains live secret markers.
# Allow known fake fixtures (seed_fake_service_account, fixtures/, unit-test stubs).
if grep -R --binary-files=without-match -E 'GOCSPX-|BEGIN RSA PRIVATE KEY|BEGIN PRIVATE KEY|BEGIN OPENSSH PRIVATE KEY|sk-or-v1-' "$TMP_DIR" \
  | grep -Ev 'seed_fake_service_account\.py|/fixtures/|test_grounded_chat_prompt\.py|DEV_FAKE_PRIVATE_KEY_NOT_REAL|DO_NOT_USE_IN_PRODUCTION' >/dev/null 2>&1; then
  echo "ERROR: secret marker found in git archive contents. Aborting." >&2
  exit 1
fi

(
  cd "$TMP_DIR"
  if command -v zip >/dev/null 2>&1; then
    zip -qr "$OUT" .
  else
    python - <<'PY' "$OUT"
import sys, zipfile, os
out = sys.argv[1]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _, files in os.walk("."):
        for name in files:
            path = os.path.join(root, name)
            zf.write(path, path)
print("wrote", out)
PY
  fi
)

echo "OK: created via git archive (tracked files only)."
echo "Archive: $OUT"
echo "Reminder: rotate Google OAuth client secret + JWT keys if a previous raw zip was shared."
