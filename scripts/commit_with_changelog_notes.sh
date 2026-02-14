#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"Commit header\"" >&2
  exit 1
fi

header="$1"

version=$(python - <<'PY'
from src.utils.constants import APP_VERSION
print(APP_VERSION)
PY
)

if [[ -z "$version" ]]; then
  echo "Could not determine APP_VERSION" >&2
  exit 1
fi

section=$(awk "/^## \[${version}\]/{found=1; next} /^## \[/{if(found) exit} found{print}" CHANGELOG.md)

if [[ -z "$section" ]]; then
  echo "No CHANGELOG section found for version ${version}" >&2
  exit 1
fi

tmp_file=$(mktemp)
{
  echo "$header"
  echo
  echo "$section"
} > "$tmp_file"

git commit -F "$tmp_file"
rm -f "$tmp_file"
