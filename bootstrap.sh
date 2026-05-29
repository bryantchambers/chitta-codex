#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

choose_python() {
  local candidates=()
  if [[ -n "${BOOTSTRAP_PYTHON:-}" ]]; then
    candidates+=("$BOOTSTRAP_PYTHON")
  fi
  candidates+=(
    "python3.12"
    "python3.11"
    "python3.10"
    "python3"
  )

  local py
  for py in "${candidates[@]}"; do
    if ! command -v "$py" >/dev/null 2>&1; then
      continue
    fi

    if "$py" - <<'PY' >/dev/null 2>&1; then
import sys
if sys.version_info >= (3, 11):
    raise SystemExit(0)
if sys.version_info >= (3, 10):
    try:
        import tomli  # noqa: F401
    except Exception:
        raise SystemExit(1)
    raise SystemExit(0)
raise SystemExit(1)
PY
      echo "$py"
      return 0
    fi
  done

  echo "No usable Python found. Need Python 3.11+, or 3.10 with tomli installed." >&2
  return 1
}

PYTHON_BIN="$(choose_python)"
exec "$PYTHON_BIN" "$SCRIPT_DIR/bootstrap.py" "$@"

