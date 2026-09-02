# Publishing MobiFlow

The **npm package** (`@qubiqlabs/mobiflow`) is the user-facing install. It ships
`pyproject.toml` + `src/mobiflow` and the Node launcher installs that tree with
pip (Python 3.11+ on PATH; **no git clone**).

Scoped package name: **`@qubiqlabs/mobiflow`** (publishes under the `qubiqlabs` org/user).

## One-shot release

```bash
./publish.sh 0.2.0            # bump version → tests → PyPI → npm → tag → push
./publish.sh v0.2.0 --dry-run
./publish.sh --version 0.2.0 --npm-only
./publish.sh                  # publish current matching versions
./publish.sh 0.2.0 --yes      # skip confirmation
```

Notes:
  `npm login` unlocks **npm only**. PyPI is a separate token
  (`TWINE_PASSWORD` / `~/.pypirc`). Without it, `./publish.sh` skips PyPI
  automatically and still publishes to npm.

```bash
./publish.sh 0.2.0 --npm-only --yes    # force npm-only
./publish.sh 0.2.0 --pypi-only --yes   # requires PyPI token
```

| File | Field |
|------|--------|
| `pyproject.toml` | `project.version` |
| `package.json` | `version` |
| Git tag | `v0.1.0` |

---

## 1. Publish to PyPI (recommended first)

```bash
python3.12 -m pip install --upgrade build twine
python3.12 -m build
python3.12 -m twine check dist/*
python3.12 -m twine upload dist/*
```

Needs a [PyPI API token](https://pypi.org/manage/account/token/) (`TWINE_USERNAME=__token__`, `TWINE_PASSWORD=pypi-…`).

Test install:

```bash
pip install mobiflow==0.1.0
mobiflow --help
```

---

## 2. Publish to npm

```bash
npm login          # one-time; opens browser / OTP
npm whoami         # must succeed

# Dry run
npm pack --dry-run

# Publish (public)
npm publish --access public
```

Requires an [npmjs.com](https://www.npmjs.com) account with 2FA enabled for publishing.

After publish:

```bash
npx @qubiqlabs/mobiflow@0.2.0 --help
npm install -g @qubiqlabs/mobiflow
mobiflow --help
```

The npm bin (`bin/mobiflow.js`) will:

1. Find Python 3.11+ on PATH
2. Create `~/.mobiflow/venv` if needed, then `pip install` the engine from
   **this npm package directory** when the installed version does not match
   `package.json`
3. Run `python -m mobiflow …`

Override the pip spec (optional, for contributors):

```bash
export MOBIFLOW_PIP_SPEC='/path/to/MobiFlow'
npx @qubiqlabs/mobiflow status
```

---

## 3. Tag a release

```bash
git tag -a v0.1.0 -m "mobiflow 0.1.0"
git push origin v0.1.0
```

Create a GitHub Release from that tag for release notes.

---

## Checklist

- [ ] Tests green: `pytest`
- [ ] Version bumped in `pyproject.toml` + `package.json`
- [ ] `LICENSE` present
- [ ] `npm pack --dry-run` includes `bin/`, `src/mobiflow/`, `pyproject.toml`
- [ ] `npm whoami` works
- [ ] `npm publish --access public`
- [ ] Tag `v0.1.0` pushed
