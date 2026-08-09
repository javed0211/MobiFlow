#!/usr/bin/env bash
# publish.sh — release MobiFlow to PyPI + npm (and optionally tag/push).
#
# Usage:
#   ./publish.sh                  # tests → build → PyPI → npm → tag → push
#   ./publish.sh --dry-run        # everything except upload / push
#   ./publish.sh --npm-only
#   ./publish.sh --pypi-only
#   ./publish.sh --skip-tests
#   ./publish.sh --skip-tag
#   ./publish.sh --yes            # no confirmation prompt
#
# Credentials:
#   PyPI: TWINE_USERNAME=__token__  TWINE_PASSWORD=pypi-...
#         (or ~/.pypirc)
#   npm:  npm login   (or NPM_TOKEN)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

DRY_RUN=0
DO_PYPI=1
DO_NPM=1
DO_TAG=1
DO_TESTS=1
ASSUME_YES=0

usage() {
  cat <<'EOF'
publish.sh — release MobiFlow to PyPI + npm (and optionally tag/push).

Usage:
  ./publish.sh                  # tests → build → PyPI → npm → tag → push
  ./publish.sh --dry-run        # everything except upload / push
  ./publish.sh --npm-only
  ./publish.sh --pypi-only
  ./publish.sh --skip-tests
  ./publish.sh --skip-tag
  ./publish.sh --yes            # no confirmation prompt

Credentials:
  PyPI: TWINE_USERNAME=__token__  TWINE_PASSWORD=pypi-...
        (or ~/.pypirc)
  npm:  npm login   (or NPM_TOKEN)
EOF
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --dry-run) DRY_RUN=1 ;;
    --npm-only) DO_PYPI=0; DO_NPM=1 ;;
    --pypi-only) DO_PYPI=1; DO_NPM=0 ;;
    --skip-tests) DO_TESTS=0 ;;
    --skip-tag) DO_TAG=0 ;;
    --yes|-y) ASSUME_YES=1 ;;
    *)
      echo "Unknown option: $1" >&2
      usage 1
      ;;
  esac
  shift
done

die() { echo "error: $*" >&2; exit 1; }
info() { echo "==> $*"; }
ok() { echo "    ✓ $*"; }

# --- tools ---
PYTHON=""
for c in "${MOBIFLOW_PYTHON:-}" "$ROOT/.venv/bin/python" python3.12 python3.11 python3; do
  [[ -z "$c" ]] && continue
  if command -v "$c" >/dev/null 2>&1 || [[ -x "$c" ]]; then
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PYTHON="$c"
      break
    fi
  fi
done
[[ -n "$PYTHON" ]] || die "Python 3.11+ required (set MOBIFLOW_PYTHON or create .venv)"

command -v npm >/dev/null 2>&1 || die "npm is required"
command -v git >/dev/null 2>&1 || die "git is required"

# --- version sync ---
PY_VERSION="$("$PYTHON" -c "
import re, pathlib
t = pathlib.Path('pyproject.toml').read_text()
m = re.search(r'^version\s*=\s*\"([^\"]+)\"', t, re.M)
assert m, 'version not found in pyproject.toml'
print(m.group(1))
")"
NPM_VERSION="$(node -p "require('./package.json').version")"

[[ "$PY_VERSION" == "$NPM_VERSION" ]] || die \
  "version mismatch: pyproject.toml=$PY_VERSION package.json=$NPM_VERSION"

VERSION="$PY_VERSION"
TAG="v${VERSION}"

info "MobiFlow ${VERSION}  (tag ${TAG})"
info "Python: $PYTHON"
[[ "$DRY_RUN" -eq 1 ]] && info "DRY RUN — no upload / push"

if [[ "$ASSUME_YES" -ne 1 ]]; then
  read -r -p "Continue publish? [y/N] " ans
  [[ "${ans:-}" =~ ^[Yy]$ ]] || die "aborted"
fi

# --- git hygiene ---
if [[ -n "$(git status --porcelain)" ]]; then
  die "working tree not clean — commit or stash first"
fi
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
ok "on branch ${BRANCH}, clean"

# --- tests ---
if [[ "$DO_TESTS" -eq 1 ]]; then
  info "Running tests"
  if [[ -x "$ROOT/.venv/bin/pytest" ]]; then
    "$ROOT/.venv/bin/pytest" -q
  else
    "$PYTHON" -m pytest -q
  fi
  ok "tests passed"
fi

# --- PyPI ---
if [[ "$DO_PYPI" -eq 1 ]]; then
  info "Building Python package"
  "$PYTHON" -m pip install -q --upgrade build twine
  rm -rf dist build *.egg-info src/*.egg-info
  "$PYTHON" -m build
  "$PYTHON" -m twine check dist/*
  ok "sdist + wheel OK"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Would run: twine upload dist/*"
  else
    info "Uploading to PyPI"
    if [[ -n "${TWINE_PASSWORD:-}" ]]; then
      export TWINE_USERNAME="${TWINE_USERNAME:-__token__}"
    fi
    "$PYTHON" -m twine upload dist/*
    ok "PyPI: mobiflow==${VERSION}"
  fi
fi

# --- npm ---
if [[ "$DO_NPM" -eq 1 ]]; then
  info "Checking npm auth"
  if ! npm whoami >/dev/null 2>&1; then
    die "not logged into npm — run: npm login"
  fi
  WHO="$(npm whoami)"
  ok "npm user: ${WHO}"

  info "npm pack dry-run"
  npm pack --dry-run >/dev/null
  ok "npm package contents OK"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Would run: npm publish --access public"
  else
    info "Publishing to npm"
    npm publish --access public
    ok "npm: mobiflow@${VERSION}"
  fi
fi

# --- git tag ---
if [[ "$DO_TAG" -eq 1 ]]; then
  if git rev-parse "$TAG" >/dev/null 2>&1; then
    ok "tag ${TAG} already exists"
  else
    if [[ "$DRY_RUN" -eq 1 ]]; then
      info "Would create tag ${TAG}"
    else
      info "Creating tag ${TAG}"
      git tag -a "$TAG" -m "mobiflow ${VERSION}"
      ok "tagged ${TAG}"
    fi
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Would push: origin HEAD + ${TAG}"
  else
    info "Pushing branch + tag"
    git push -u origin HEAD
    git push origin "$TAG"
    ok "pushed ${BRANCH} and ${TAG}"
  fi
fi

echo
info "Done."
[[ "$DRY_RUN" -eq 1 ]] && echo "    (dry-run — nothing uploaded)"
echo "    pip install mobiflow==${VERSION}"
echo "    npx mobiflow@${VERSION} --help"
echo "    docs: docs/PUBLISH.md"
