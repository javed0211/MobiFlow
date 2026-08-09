#!/usr/bin/env bash
# publish.sh — release MobiFlow to PyPI + npm (and optionally tag/push).
#
# Usage:
#   ./publish.sh 0.2.0            # bump version, then publish
#   ./publish.sh v0.2.0 --dry-run
#   ./publish.sh --version 0.2.0 --npm-only
#   ./publish.sh                  # publish current pyproject/package version
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

DRY_RUN=0
DO_PYPI=1
DO_NPM=1
DO_TAG=1
DO_TESTS=1
DO_COMMIT=1
ASSUME_YES=0
REQUESTED_VERSION=""
PYPI_EXPLICIT=0
NPM_EXPLICIT=0

usage() {
  cat <<'EOF'
publish.sh — release MobiFlow to PyPI + npm (and optionally tag/push).

Usage:
  ./publish.sh 0.2.0                 # bump version, publish
  ./publish.sh v0.2.0 --dry-run
  ./publish.sh --version 0.2.0
  ./publish.sh 0.2.0 --npm-only      # npm only (uses npm login — no PyPI token)
  ./publish.sh 0.2.0 --pypi-only     # PyPI only (needs TWINE_PASSWORD / ~/.pypirc)
  ./publish.sh 0.2.0 --skip-tests
  ./publish.sh 0.2.0 --skip-tag
  ./publish.sh 0.2.0 --no-commit
  ./publish.sh 0.2.0 --yes

Notes:
  npm login is enough for npm publish. It does NOT unlock PyPI.
  Without a PyPI token, PyPI is skipped automatically (unless --pypi-only).

Credentials:
  npm:  npm login
  PyPI: TWINE_USERNAME=__token__  TWINE_PASSWORD=pypi-...
        (or ~/.pypirc)
EOF
  exit "${1:-0}"
}

is_version() {
  [[ "$1" =~ ^[vV]?[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]
}

normalize_version() {
  local v="$1"
  v="${v#v}"
  v="${v#V}"
  echo "$v"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --dry-run) DRY_RUN=1 ;;
    --npm-only) DO_PYPI=0; DO_NPM=1; NPM_EXPLICIT=1 ;;
    --pypi-only) DO_PYPI=1; DO_NPM=0; PYPI_EXPLICIT=1 ;;
    --skip-tests) DO_TESTS=0 ;;
    --skip-tag) DO_TAG=0 ;;
    --no-commit) DO_COMMIT=0 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --version)
      shift
      [[ $# -gt 0 ]] || { echo "error: --version needs a value" >&2; usage 1; }
      REQUESTED_VERSION="$(normalize_version "$1")"
      ;;
    --version=*)
      REQUESTED_VERSION="$(normalize_version "${1#--version=}")"
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage 1
      ;;
    *)
      if is_version "$1"; then
        REQUESTED_VERSION="$(normalize_version "$1")"
      else
        echo "Unknown argument: $1 (expected version like 0.2.0)" >&2
        usage 1
      fi
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
command -v node >/dev/null 2>&1 || die "node is required"

read_py_version() {
  "$PYTHON" -c "
import re, pathlib
t = pathlib.Path('pyproject.toml').read_text()
m = re.search(r'^version\s*=\s*\"([^\"]+)\"', t, re.M)
assert m, 'version not found in pyproject.toml'
print(m.group(1))
"
}

read_npm_version() {
  node -p "require('./package.json').version"
}

set_versions() {
  local ver="$1"
  "$PYTHON" - <<PY
from pathlib import Path
import re, json

ver = "${ver}"
py = Path("pyproject.toml")
text = py.read_text()
new, n = re.subn(
    r'^version\s*=\s*"[^"]+"',
    f'version = "{ver}"',
    text,
    count=1,
    flags=re.M,
)
if n != 1:
    raise SystemExit("could not update version in pyproject.toml")
py.write_text(new)

pkg_path = Path("package.json")
pkg = json.loads(pkg_path.read_text())
pkg["version"] = ver
pkg_path.write_text(json.dumps(pkg, indent=2) + "\n")
print(f"updated pyproject.toml + package.json → {ver}")
PY
}

PY_VERSION="$(read_py_version)"
NPM_VERSION="$(read_npm_version)"

if [[ -n "$REQUESTED_VERSION" ]]; then
  is_version "$REQUESTED_VERSION" || die "invalid version: ${REQUESTED_VERSION}"
  VERSION="$(normalize_version "$REQUESTED_VERSION")"
  if [[ "$PY_VERSION" != "$VERSION" || "$NPM_VERSION" != "$VERSION" ]]; then
    info "Bumping version ${PY_VERSION}/${NPM_VERSION} → ${VERSION}"
    set_versions "$VERSION"
    ok "files updated"
  else
    ok "already at ${VERSION}"
  fi
else
  [[ "$PY_VERSION" == "$NPM_VERSION" ]] || die \
    "version mismatch: pyproject.toml=$PY_VERSION package.json=$NPM_VERSION (pass a version to fix)"
  VERSION="$PY_VERSION"
fi

# re-read after bump
VERSION="$(read_py_version)"
NPM_VERSION="$(read_npm_version)"
[[ "$VERSION" == "$NPM_VERSION" ]] || die "version sync failed after bump"
TAG="v${VERSION}"

info "MobiFlow ${VERSION}  (tag ${TAG})"
info "Python: $PYTHON"
[[ "$DRY_RUN" -eq 1 ]] && info "DRY RUN — no upload / push / commit"

if [[ "$ASSUME_YES" -ne 1 ]]; then
  read -r -p "Continue publish ${VERSION}? [y/N] " ans
  [[ "${ans:-}" =~ ^[Yy]$ ]] || die "aborted"
fi

# --- git: commit version bump if needed ---
STATUS="$(git status --porcelain)"
if [[ -n "$STATUS" ]]; then
  OTHER="$(git status --porcelain | grep -vE ' (pyproject\.toml|package\.json)$' || true)"
  if [[ -n "$OTHER" ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      info "Warning: dirty tree (allowed in --dry-run):"
      echo "$OTHER" | sed 's/^/    /'
    else
      die "working tree not clean — commit or stash first (aside from version bump)"
    fi
  fi
  if git status --porcelain | grep -qE 'pyproject\.toml|package\.json'; then
    if [[ "$DO_COMMIT" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
      info "Committing version bump"
      git add pyproject.toml package.json
      git commit -m "Bump version to ${VERSION}"
      ok "committed version ${VERSION}"
    elif [[ "$DRY_RUN" -eq 1 ]]; then
      info "Would commit: Bump version to ${VERSION}"
    else
      info "Left version bump uncommitted (--no-commit)"
    fi
  fi
fi

# After optional commit, tree must be clean for a real publish
if [[ "$DRY_RUN" -eq 0 && -n "$(git status --porcelain)" ]]; then
  die "working tree not clean after version handling"
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
ok "on branch ${BRANCH}"

# Restore bumped files if dry-run exits early
restore_dry_run_versions() {
  if [[ "$DRY_RUN" -eq 1 && -n "$REQUESTED_VERSION" ]]; then
    if git status --porcelain | grep -qE 'pyproject\.toml|package\.json'; then
      info "Dry-run: restoring pyproject.toml / package.json"
      git checkout -- pyproject.toml package.json 2>/dev/null || true
    fi
  fi
}
trap restore_dry_run_versions EXIT

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

has_pypi_creds() {
  [[ -n "${TWINE_PASSWORD:-}" ]] && return 0
  [[ -n "${PYPI_TOKEN:-}" ]] && return 0
  if [[ -f "${HOME}/.pypirc" ]] && grep -qE 'password\s*=' "${HOME}/.pypirc" 2>/dev/null; then
    return 0
  fi
  return 1
}

# --- npm first (uses npm login; no PyPI token) ---
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
    if [[ -n "${NPM_OTP:-}" ]]; then
      npm publish --access public --otp="$NPM_OTP"
    else
      npm publish --access public
    fi
    ok "npm: $(node -p "require('./package.json').name")@${VERSION}"
  fi
fi

# --- PyPI (separate credentials from npm) ---
if [[ "$DO_PYPI" -eq 1 ]]; then
  if ! has_pypi_creds; then
    if [[ "$PYPI_EXPLICIT" -eq 1 ]]; then
      die "PyPI token required for --pypi-only. Set TWINE_PASSWORD=pypi-... or configure ~/.pypirc
    npm login does not provide PyPI access."
    fi
    info "Skipping PyPI (no TWINE_PASSWORD / ~/.pypirc) — npm login is not used for PyPI"
    info "Later: TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-… ./publish.sh ${VERSION} --pypi-only --skip-tag --yes"
  else
    info "Building Python package ${VERSION}"
    "$PYTHON" -m pip install -q --upgrade build twine
    rm -rf dist build *.egg-info src/*.egg-info
    "$PYTHON" -m build
    "$PYTHON" -m twine check dist/*
    ok "sdist + wheel OK"

    if [[ -n "${PYPI_TOKEN:-}" && -z "${TWINE_PASSWORD:-}" ]]; then
      export TWINE_PASSWORD="$PYPI_TOKEN"
    fi
    export TWINE_USERNAME="${TWINE_USERNAME:-__token__}"
    # Never hang on an interactive password prompt
    export TWINE_NON_INTERACTIVE=1

    if [[ "$DRY_RUN" -eq 1 ]]; then
      info "Would run: twine upload dist/*"
    else
      info "Uploading to PyPI"
      "$PYTHON" -m twine upload --non-interactive dist/* 2>/dev/null \
        || "$PYTHON" -m twine upload dist/*
      ok "PyPI: mobiflow==${VERSION}"
    fi
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
echo "    npx @qubiqlabs/mobiflow@${VERSION} --help"
echo "    npm install -g @qubiqlabs/mobiflow@${VERSION}"
if has_pypi_creds || [[ "$DO_PYPI" -eq 0 ]]; then
  echo "    pip install mobiflow==${VERSION}   # after PyPI upload"
fi
echo "    docs: docs/PUBLISH.md"
