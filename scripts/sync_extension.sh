#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CHROME_DIR="${REPO_ROOT}/sentience-chrome"
SDK_EXT_DIR="${REPO_ROOT}/sdk-python/predicate/extension"

if [[ ! -d "${CHROME_DIR}" ]]; then
  echo "[sync_extension] sentience-chrome not found at ${CHROME_DIR}"
  exit 1
fi

if [[ ! -f "${CHROME_DIR}/package.json" ]]; then
  echo "[sync_extension] package.json missing in sentience-chrome"
  exit 1
fi

echo "[sync_extension] Building sentience-chrome..."
pushd "${CHROME_DIR}" >/dev/null
npm run build
popd >/dev/null

echo "[sync_extension] Syncing dist/ and pkg/ to sdk-python..."
mkdir -p "${SDK_EXT_DIR}/dist" "${SDK_EXT_DIR}/pkg"
cp "${CHROME_DIR}/dist/"* "${SDK_EXT_DIR}/dist/"
cp "${CHROME_DIR}/pkg/"* "${SDK_EXT_DIR}/pkg/"

echo "[sync_extension] Done."
