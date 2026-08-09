# MobiFlow

CLI-only mobile automation: describe a scenario in natural language,
generate **Maestro** flow YAML with an LLM, run it on a device/emulator,
and self-heal via a verify/repair loop — all in the terminal.

Configure LLMs with `llm.json` + `mobiflow.config.yaml`, scaffold with
`mobiflow init`, then author cases and run them locally or in the cloud.

## Requirements

- Python 3.11+
- An LLM API key (OpenAI / Azure / Anthropic / Google)
- [Maestro CLI](https://maestro.mobile.dev) + a JDK (`JAVA_HOME`)
- Android emulator (`adb`) and/or booted iOS Simulator

```bash
# Maestro (macOS/Linux)
curl -Ls "https://get.maestro.mobile.dev" | bash
```

## Install

**Python (recommended):**

```bash
pip install mobiflow
# or from source
pip install -e ".[dev]"
```

**npm wrapper** (launches the Python CLI; requires Python 3.11+):

```bash
npm install -g @qubiqlabs/mobiflow
# or
npx @qubiqlabs/mobiflow --help
```

See [docs/PUBLISH.md](docs/PUBLISH.md) for maintainers.

## Quick start

```bash
mobiflow init
# Guided wizard:
#   Step 1/5 — Project path
#   Step 2/5 — LLM provider & models (writes llm.json)
#   Step 3/5 — Device defaults + language (yaml | yaml+js)
#   Step 4/5 — Detect missing packages → optional auto-install
#   Step 5/5 — Write mobiflow.config.yaml + example case

export OPENAI_API_KEY=sk-...   # or AZURE_OPENAI_API_KEY / ANTHROPIC_API_KEY / …

mobiflow status
mobiflow run cases/example.txt
```

Non-interactive (auto-installs missing Maestro / JDK / pip packages by default):

```bash
mobiflow init --mode local --path . --yes
mobiflow init --mode local --path . --yes --no-install-deps   # skip installs
mobiflow setup                # re-check / install anytime
mobiflow setup --check-only   # report only
mobiflow setup --install-adb  # also Homebrew android-platform-tools
```

### Auto-install during setup

Step 4 (and `mobiflow setup`) probes and can install:

| Dependency | How |
|------------|-----|
| Python packages (`openai`, `anthropic`, …) | `pip install` |
| Maestro CLI | official `get.maestro.mobile.dev` installer |
| JDK | Homebrew `openjdk` (when `brew` is available) |
| Android `adb` | optional Homebrew `android-platform-tools` |

Xcode / full Android SDK are reported but not auto-installed.

## LLM configuration

**Two files:**

1. `llm.json` — named provider profiles (no secrets)
2. `mobiflow.config.yaml` `llm:` — picks `discovery` + `codegen` by profile id

```yaml
llm:
  catalog: llm.json
  discovery: azure-gpt4o      # adaptive explore / plan
  codegen: anthropic-sonnet   # Maestro YAML authoring
```

```json
{
  "version": 1,
  "models": {
    "azure-gpt4o": {
      "provider": "azure",
      "model": "gpt-4o",
      "deployment": "gpt-4o",
      "api_key_env": "AZURE_OPENAI_API_KEY",
      "endpoint": "https://YOUR.openai.azure.com",
      "endpoint_env": "AZURE_OPENAI_ENDPOINT",
      "api_version": "2025-03-01-preview"
    }
  }
}
```

Keys live only in env vars named by `api_key_env`. Never paste secrets into YAML/JSON.

```bash
mobiflow llm list
mobiflow config show
```

## Test case format (`.txt`)

Cases are free-form text with optional run knobs and external data. Full reference:
**[docs/CASES.md](docs/CASES.md)**.

```text
@smoke
appId: org.wikipedia
platform: android
codegen: true          # false → reuse flows/<case>.yaml
retries: 0
heal: 2
data: data/example.json
task: |
  Open Wikipedia, dismiss onboarding, confirm Search is visible
  1. Launch the app
  2. Tap Search and type ${SEARCH_QUERY}
  3. Confirm Search results are visible
```

**Precedence for run knobs:** CLI → case file → `mobiflow.config.yaml`.  
**Data:** `data:` accepts a relative or absolute path to `.json` / `.yaml` / `.env`;
values flatten into Maestro `--env` / `${KEY}`.

```bash
mobiflow run cases/example.txt
mobiflow run cases/wikipedia_complex_search.txt   # iOS Wikipedia + data file
```

## Commands

| Command | Behavior |
|---------|----------|
| `mobiflow init` | Wizard / non-interactive scaffold (+ optional deps install) |
| `mobiflow setup` | Detect / auto-install missing Maestro, JDK, pip packages |
| `mobiflow run <case.txt>` | Explore → LLM YAML → device (+ heal) |
| `mobiflow run cases/ [--tag smoke]` | Suite: all (or tagged) cases + aggregate JUnit/HTML |
| `mobiflow suite [cases/]` | Same as `run` on a directory (defaults to `cases/`) |
| `mobiflow run <case.txt> --gen-only` | Author YAML only |
| `mobiflow run … --reuse-flow` | Skip LLM; use frozen `flows/<case>.yaml` |
| `mobiflow run … --incremental` | Gap-explore only newly appended numbered steps |
| `mobiflow run … --extend-explore` | Full explore + extend codegen from prior YAML |
| `mobiflow gen "Open Settings…"` | One-shot NL → YAML |
| `mobiflow explore "…" [--interactive]` | Discovery session (confirm each action with `--interactive`) |
| `mobiflow import-flow flow.yaml` | Studio/YAML → MobiFlow case (+ copy into `flows/`) |
| `mobiflow baseline update/compare` | Visual PNG baseline |
| `mobiflow studio` | Open Maestro Studio (local device UI) |
| `mobiflow test-flow flows/foo.yaml` | Run existing YAML |
| `mobiflow status` / `devices` | Maestro + local devices + cloud lab readiness |
| `mobiflow devices --start` | Auto-start Android AVD (Win/Mac) or Xcode sim (Mac) |
| `mobiflow config show` / `llm list` | Inspect config / catalog |

## Languages

| `stack.language` | Behavior |
|------------------|----------|
| `yaml+js` (default) | Maestro YAML + optional JS (`evalScript` / `runScript` / `${…}`) |
| `yaml` | YAML commands only |

Companion scripts land under `flows/scripts/`.

## Reporting

Each live run writes **JUnit** plus a full interactive **HTML dashboard** (cases, timeline,
logs, screenshots, cloud links) under `.mobiflow/reports/` — same SPA also under the run folder.
Open `index.html` (or `report.html`). Rebuild a pack from past runs anytime:

```bash
mobiflow report --out .mobiflow/reports/latest
mobiflow serve          # http://127.0.0.1:8765 — needed for local screenshot paths
```

```yaml
run:
  reports: [junit, html]
  report_dir: .mobiflow/reports
```

Sample dashboard: [docs/samples/execution-report/](docs/samples/execution-report/).
Suites write aggregate reports under `.mobiflow/reports/suite-<name>-<ts>/`.
GitHub Actions (`.github/workflows/ci.yml`) runs lint + unit tests; set
`MOBIFLOW_CLOUD_CI=true` plus cloud/LLM secrets for an optional smoke suite job.

## Cloud device labs

Set `device.provider` to `browserstack` or `testmu` to run on real devices in the cloud
(same Maestro YAML; no local emulator required). See [docs/FEATURES.md](docs/FEATURES.md).

```bash
export BROWSERSTACK_USERNAME=... BROWSERSTACK_ACCESS_KEY=...
# or TESTMU_USERNAME / TESTMU_ACCESS_KEY (LT_* aliases work)
```

## Pipeline

```
1. Load case + config + optional data: file → Maestro env
2. Resolve run mode (codegen / reuse / incremental / extend) — CLI > case > config
3. Explore app with discovery LLM (or replay prefix + gap for --incremental)
4. Author / extend Maestro YAML (+ JS when enabled)
5. Local: maestro test --device <id>
   Cloud: upload app + suite → Maestro Cloud / BrowserStack / TestMu HyperExecute
6. On fail → repair with failure log (≤ heal) → re-run
7. Write flows/<case>.yaml (+ scripts), guidance stamp, reports under .mobiflow/
```

## Docs

| Doc | Contents |
|-----|----------|
| [docs/CASES.md](docs/CASES.md) | Case template, run knobs, `data:`, incremental |
| [docs/FEATURES.md](docs/FEATURES.md) | Devices, cloud, suite, JS, reporting, CI |
| [docs/PUBLISH.md](docs/PUBLISH.md) | PyPI + npm publish steps |
