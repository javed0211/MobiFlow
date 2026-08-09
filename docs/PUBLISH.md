# Publishing MobiFlow

MobiFlow’s **engine is Python** (`pip install mobiflow`).  
The **npm package** is a thin Node launcher so users can run `npx mobiflow` / `npm i -g mobiflow`.

## One-shot release

```bash
./publish.sh 0.2.0            # bump version → tests → PyPI → npm → tag → push
./publish.sh v0.2.0 --dry-run
./publish.sh --version 0.2.0 --npm-only
./publish.sh                  # publish current matching versions
./publish.sh 0.2.0 --yes      # skip confirmation
```

`0.2.0` updates both `pyproject.toml` and `package.json`, auto-commits
`Bump version to 0.2.0`, then publishes. Use `--no-commit` to leave the bump unstaged.

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
npx mobiflow@0.1.0 --help
npm install -g mobiflow
mobiflow --help
```

The npm bin (`bin/mobiflow.js`) will:

1. Prefer an existing `mobiflow` on `PATH`
2. Else `python3 -m mobiflow`
3. Else `pip install mobiflow==<npm version>` (falls back to GitHub tag `v<version>`)

Override install source:

```bash
export MOBIFLOW_PIP_SPEC='git+https://github.com/javed0211/MobiFlow.git@main'
npx mobiflow status
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
- [ ] PyPI upload succeeded (or GitHub fallback is acceptable for first npm cut)
- [ ] `npm whoami` works
- [ ] `npm publish --access public`
- [ ] Tag `v0.1.0` pushed
