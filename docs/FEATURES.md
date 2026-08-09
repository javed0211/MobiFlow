# MobiFlow features

Feature deep-dives. For **writing cases** (template, run knobs, `data:`, incremental),
see **[CASES.md](CASES.md)**.

## Maestro languages: YAML + JavaScript

Maestro’s primary language is **YAML**. MobiFlow also supports Maestro’s built-in **JavaScript** (GraalJS):

| Mechanism | Use |
|-----------|-----|
| `${expression}` | Dynamic values in YAML fields |
| `evalScript` | Short inline logic / set `output.*` |
| `runScript: scripts/foo.js` | Reusable helper files |

Configure via:

```yaml
stack:
  language: yaml+js   # or yaml for YAML-only
  scripts_dir: flows/scripts
```

During `mobiflow init`, pick **YAML + JavaScript** (default) or **YAML only**.
Codegen emits companion `.js` files when the goal needs dynamic data; simple smoke flows stay YAML-only.

Example:

```yaml
appId: com.android.settings
---
- runScript: scripts/helpers.js
- evalScript: ${setOutput('runId', 'run-' + Date.now())}
- launchApp
- assertVisible: "Settings"
- stopApp
```

## Devices & auto-start (macOS + Windows)

MobiFlow discovers **online** devices and **startable** targets:

| Target | Detect | Auto-start |
|--------|--------|------------|
| Android (adb) | `adb devices` | — (already online) |
| Android AVD | `emulator -list-avds` | `emulator -avd <name>` on **Windows & macOS** |
| iOS Simulator | `xcrun simctl list` | `simctl boot` + open Simulator.app (**macOS only**) |

```yaml
device:
  provider: local     # local | browserstack | testmu | maestro
  platform: android   # or ios
  auto_start: true
  use_maestro_cli: true   # prefer `maestro start-device` before adb/simctl
  boot_timeout_s: 120
  device_id: ""       # optional: AVD name, emulator-5554, or iOS UDID
  # device_model / device_os / device_locale — passed to maestro start-device
```

```bash
mobiflow devices              # online only
mobiflow devices --all        # + startable AVDs / shutdown sims
mobiflow devices --start      # ensure one is running (auto-start if needed)
mobiflow run cases/example.txt   # uses auto_start from config
```

SDK paths checked: `ANDROID_HOME` / `ANDROID_SDK_ROOT`, macOS `~/Library/Android/sdk`, Windows `%LOCALAPPDATA%\Android\Sdk`. With `use_maestro_cli: true` (default), MobiFlow tries `maestro start-device` / `maestro list-devices` first.

## Cloud device labs (BrowserStack + TestMu + Maestro Cloud)

Run the same Maestro flows on real devices in the cloud — no local emulator required.

| Provider | How it runs | Credentials |
|----------|-------------|-------------|
| `browserstack` | App Automate Maestro REST (upload app + zip suite → build → poll) | `BROWSERSTACK_USERNAME` / `BROWSERSTACK_ACCESS_KEY` |
| `testmu` | TestMu AI HyperExecute (uploads app, generates YAML, runs CLI) | `TESTMU_USERNAME` / `TESTMU_ACCESS_KEY` (or `LT_*`) |
| `maestro` | Official `maestro cloud` CLI | `MAESTRO_CLOUD_API_KEY` (or `MAESTRO_API_KEY`) |

```yaml
device:
  provider: browserstack          # or testmu | maestro
  platform: android
  device_id: "Google Pixel 7-13.0"  # TestMu e.g. "Pixel 6-14"; Maestro e.g. pixel_7
  app_path: builds/app-debug.apk  # upload each run
  # app_url: bs://…               # or reuse a previous upload / Maestro app id
  cloud_project: MobiFlow
  real_mobile: true               # testmu only
  cloud_timeout_s: 1800
```

```bash
export BROWSERSTACK_USERNAME=...
export BROWSERSTACK_ACCESS_KEY=...
# or: TESTMU_USERNAME / TESTMU_ACCESS_KEY (LT_USERNAME / LT_ACCESS_KEY also work)
# or: MAESTRO_CLOUD_API_KEY=...

mobiflow status                 # shows cloud readiness
mobiflow run cases/example.txt  # uploads + executes on the cloud device
mobiflow test-flow flows/foo.yaml
```

Notes:

- Adaptive hierarchy heal is **local-only**; cloud heal uses failure logs.
- TestMu auto-downloads the HyperExecute CLI to `~/.mobiflow/bin` on first run.
- Maestro Cloud runs via `maestro cloud` with your API key.
- `mobiflow init` step 3 lets you pick BrowserStack / TestMu and set device + app path.

## Dual LLM roles

| Role | Config key | Used for |
|------|------------|----------|
| Discovery | `llm.discovery` | Explore app / build grounded plan before codegen |
| Codegen | `llm.codegen` | Maestro YAML authoring + heal repairs |

Both resolve from `llm.json`. They may be the same profile or different providers.

## Explore-then-generate

When `run.explore: true` (default), MobiFlow **explores first**, then authors YAML:

```
launch app → hierarchy → discovery LLM decides next tap/scroll
        → repeat (≤ explore_steps) → grounded plan + selectors
        → codegen writes YAML from exploration
        → maestro test → heal on failure
```

```yaml
run:
  explore: true
  explore_steps: 5
```

| Mode | When | Behavior |
|------|------|----------|
| Live local | device online | Multi-step navigate + observe via discovery LLM |
| Cloud / no device | BrowserStack/TestMu or offline | Plan-only explore from the goal text |
| Off | `explore: false` or pasted YAML | Skip explore; codegen from goal (+ one hierarchy if adaptive) |

Exploration is saved to `.mobiflow/runs/<case>-<ts>/exploration.json`.

## Interactive explore (separate mode)

`mobiflow run` always explores **automatically** (when enabled). For an operator-driven
session, use a separate command:

```bash
# LLM proposes each tap/scroll; you Accept / Edit / Skip / Done / Quit
mobiflow explore "Open Settings → Network" --interactive

# Same, but auto-accept every discovery action
mobiflow explore "…" --auto

# Explore then codegen YAML (does not run the final test)
mobiflow explore "…" --interactive --gen --out flows/network.yaml
```

| Mode | Command | Who decides each step |
|------|---------|------------------------|
| Automatic (in `run`) | `mobiflow run …` | Discovery LLM, no prompts |
| Interactive session | `mobiflow explore --interactive` | You confirm each proposed action |
| Maestro Studio UI | `mobiflow studio` | Official Maestro interactive UI (local only) |

Interactive explore is **local-device only**. Cloud providers fall back to plan-only explore.
It does **not** launch Maestro Studio — that is `mobiflow studio`.

## Heal loop

`run.heal` (default `2`) = number of repair attempts after a failed `maestro test`.
Each repair sends previous YAML + failure log (+ optional hierarchy) + exploration context to the codegen model.

## App lifecycle (preflight)

Before explore/run on a **local** device, MobiFlow can install a package and/or
clear app state:

```yaml
device:
  app_path: builds/app-debug.apk   # used by preflight install + cloud upload
run:
  preflight: [install, clear]      # or just [clear]
```

Case-level override:

```text
@smoke
appId: com.example.app
clearState: true
task: …
```

| Step | Local | Cloud |
|------|-------|-------|
| `install` | `adb install -r` (Android) / `simctl install` (`.app`) | Upload via `device.app_path` (existing) |
| `clear` | Maestro `clearState` (+ `clearKeychain` on iOS) | Skipped (use lab fresh device / reinstall) |

## Suite runner

Run a directory of cases and get one aggregate report:

```bash
mobiflow run cases/ --tag smoke
mobiflow suite                    # defaults to stack.cases_dir
mobiflow suite cases/ --fail-fast
```

| Flag / config | Behavior |
|---------------|----------|
| `--tag smoke` | Only cases with `@smoke` |
| `run.fail_fast` / `--fail-fast` | Stop after first failure |
| `run.jobs` | Reserved for parallel suites (currently sequential) |
| `run.retries` | Re-run same YAML before each heal (flake control) |
| `run.reuse_flow` / `--reuse-flow` | Skip LLM; use `flows/<case>.yaml` or case `flow:` |
| `run.incremental` / `--incremental` | Classify numbered steps; gap-explore only appended ones |
| `run.extend_explore` / `--extend-explore` | Full explore + extend codegen from prior YAML |
| `run.env` / case `env:` | Maestro `--env KEY=VALUE` (values can be env var names) |
| `run.jobs` / `--jobs N` | Parallel suite workers |
| case `expect:` | Force `assertVisible` lines into generated/reused YAML |
| case `data:` | Path to JSON / YAML / `.env` (relative or absolute) → Maestro `--env` |

### Case data files

```text
data: data/login.json          # relative to case dir, then repo root
# data: /abs/path/users.yaml
# data: ../fixtures/creds.env
```

Supported: `.json`, `.yaml` / `.yml`, `.env`. Nested keys flatten to Maestro env
names (`user.email` → `USER_EMAIL`). Merge order: **config `run.env` < data file <
case `env:`**. Values are available as `${KEY}` in generated YAML and as a prompt
block for explore/codegen. `DATA_PATH` is always set to the resolved absolute path.

```json
{ "search_query": "Albert Einstein", "user": { "name": "demo" } }
```
→ `--env SEARCH_QUERY=… --env USER_NAME=demo --env DATA_PATH=…`

### Case template & per-case run options

Copy `cases/example.txt` (or the template from `mobiflow init`). Precedence for run
knobs is **CLI → case file → `mobiflow.config.yaml`**.

| Case key | Meaning |
|----------|---------|
| `codegen: false` | Reuse frozen YAML (same as `reuseFlow: true`) |
| `reuseFlow` / `incremental` / `extendExplore` | Exclusive modes (same as CLI) |
| `retries` / `heal` / `explore` / `exploreSteps` | Flake + explore controls |
| `genOnly` / `adaptive` / `timeout` | Author-only / heal / per-case timeout |
| `strict: true` | Unknown keys are errors (default: warn) |

```text
@smoke
appId: org.wikipedia
platform: android
codegen: false
retries: 1
heal: 2
task: |
  1. Launch the app
  2. Confirm Search is visible
```

Then `mobiflow run cases/my-flow.txt` needs no flags for that behavior.

### Incremental case growth

When a case uses **numbered steps** (`1. …`, `2. …`), a successful run stamps them under
`.mobiflow/guidance/<case>.json`. Later:

```bash
# Appended steps only — replay prior YAML (no stopApp), explore the gap, extend YAML
mobiflow run cases/wikipedia_complex_search.txt --incremental

# Messy mid-flow edits — full explore, but seed codegen from prior YAML
mobiflow run cases/wikipedia_complex_search.txt --extend-explore

# Unchanged guidance under --incremental → same as --reuse-flow
```

**Mutually exclusive** with each other and `--reuse-flow`. Without a guidance stamp, the
first `--incremental` run treats an existing flow as **dirty** (seeded full explore); after
a successful pass the stamp is written for true append detection.

Cloud runs download screenshots/video/logs into `.mobiflow/runs/.../cloud/` when
APIs expose them (BrowserStack sessions; Maestro Cloud / TestMu best-effort).
Local runs with `run.video: true` capture MP4 via `maestro record --local`.
HTML reports link `video_url` and embed pulled screenshots.

Selector memory persists under `.mobiflow/selectors/<appId>.json` and feeds
codegen prompts on later runs.

```bash
mobiflow import-flow studio-export.yaml --tag smoke
mobiflow baseline update example shot.png
mobiflow baseline compare example shot.png
mobiflow suite --jobs 2 --reuse-flow
```

Outputs under `.mobiflow/reports/suite-<name>-<ts>/`:

- `junit.xml` — multi-testcase JUnit
- `report.html` — suite index
- `suite.json` + `suite.latest.json`

## CI

`.github/workflows/ci.yml` runs lint + unit tests on every PR. An optional
`cloud-suite` job runs when repository variable `MOBIFLOW_CLOUD_CI=true` and
uploads `.mobiflow/reports/` as an artifact. Configure cloud + LLM secrets in
the repo settings.

## Gen-only

`mobiflow run cases/foo.txt --gen-only` or `mobiflow gen "…"` authors YAML without touching the device.

## Paste YAML

If the case `task:` (or `mobiflow gen` argument) already looks like Maestro YAML (`appId:` + `---` or command list), it is executed as-is — no LLM re-authoring.

## Artifacts & reporting

Under `.mobiflow/`:

- `flows/<case>.yaml` — last generated flow
- `runs/<case>-<timestamp>/` — durable run folder (flow, Maestro debug/output, screenshots)
- `runs/<case>-<timestamp>.json` + `<case>.latest.json` — run summary
- `reports/<case>-<timestamp>/` — JUnit + interactive HTML dashboard (also mirrored under the run folder)

```yaml
run:
  save_artifacts: true
  video: true                  # local: maestro record --local after test
  reports: [junit, html]       # or [] to disable
  report_dir: .mobiflow/reports
  include_tags: []             # maestro test --include-tags
  exclude_tags: []             # maestro test --exclude-tags
  maestro_config: ""           # optional Maestro workspace config.yaml
```

| Output | Path |
|--------|------|
| JUnit XML | `.mobiflow/reports/<case>-<ts>/junit.xml` |
| HTML dashboard | `.mobiflow/reports/<case>-<ts>/index.html` (`report.html` mirror) |
| Pack JSON | `.mobiflow/reports/<case>-<ts>/pack.json` |
| Simple HTML | `.mobiflow/reports/<case>-<ts>/report-simple.html` (fallback card) |
| Screenshots | `.mobiflow/runs/<case>-<ts>/screenshots/` |
| Local video | `.mobiflow/runs/<case>-<ts>/…/*.mp4` (when `run.video: true`) |
| Maestro debug | `.mobiflow/runs/<case>-<ts>/attempts/01/maestro-debug/` |

The dashboard is a single-file SPA (`window.__MOBIFLOW_REPORT__` pack). Sample:
[docs/samples/execution-report/](samples/execution-report/).

```bash
# Rebuild from .mobiflow/runs/*.json
mobiflow report --out .mobiflow/reports/rebuild

# Serve .mobiflow/ so screenshot relative paths resolve
mobiflow serve --port 8765
```

UI source lives in `report-ui/` (Vite). Rebuild the embedded bundle:

```bash
cd report-ui && npm ci && npm run build
# copies into src/mobiflow/report/static/index.html
```

Local runs pass Maestro `--debug-output`, `--test-output-dir`, and `--format JUNIT`.
Cloud runs still get MobiFlow JUnit/HTML (with dashboard link when available).
