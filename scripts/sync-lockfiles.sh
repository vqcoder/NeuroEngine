#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# sync-lockfiles.sh
#
# Regenerate per-app package-lock.json files so they stay in sync with each
# app's package.json.  Each Dockerfile runs `npm ci` against the app's OWN
# lockfile (Docker build context = app directory), so these must be kept
# up-to-date whenever a dependency is added/removed/changed.
#
# Run from the repo root:
#   bash scripts/sync-lockfiles.sh
#
# The script works by creating a temporary directory for each app, running
# `npm install --package-lock-only` in isolation (outside the workspace),
# then copying the resulting lockfile back into the app directory.
# ---------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Apps that have their own Dockerfile and need an isolated lockfile.
APPS=(
  "apps/dashboard"
  "apps/watchlab"
  "apps/alpha-engine"
)

for app_dir in "${APPS[@]}"; do
  full_path="$REPO_ROOT/$app_dir"
  pkg="$full_path/package.json"

  if [ ! -f "$pkg" ]; then
    echo "⚠  Skipping $app_dir — no package.json found"
    continue
  fi

  echo "🔄 Syncing lockfile for $app_dir …"

  tmp="$(mktemp -d)"
  cp "$pkg" "$tmp/package.json"

  # Generate lockfile in isolation (no workspace context)
  (cd "$tmp" && npm install --package-lock-only --ignore-scripts 2>/dev/null)

  if [ -f "$tmp/package-lock.json" ]; then
    cp "$tmp/package-lock.json" "$full_path/package-lock.json"
    echo "   ✅ $app_dir/package-lock.json updated"
  else
    echo "   ❌ Failed to generate lockfile for $app_dir"
  fi

  rm -rf "$tmp"
done

echo ""
echo "Done. Verify with: git diff --stat '**/package-lock.json'"
