# MobiFlow

CLI-only mobile automation: describe a scenario in natural language,
generate **Maestro** flow YAML with an LLM, run it on a device/emulator,
and self-heal via a verify/repair loop — all in the terminal.

Setup mirrors the WebQA CLI (`llm.json` catalog + config selectors + `init` wizard), but the runner is Maestro instead of browser-use.

## Requirements

- Python 3.11+
- An LLM API key (OpenAI / Azure / Anthropic / Google)
- [Maestro CLI](https://maestro.mobile.dev) + a JDK (`JAVA_HOME`)
- Android emulator (`adb`) and/or booted iOS Simulator

```bash
# Maestro (macOS/Linux)
curl -Ls "https://get.maestro.mobile.dev" | bash
```

## Install (dev)

```bash
cd /Users/oldguard/Documents/MobiFlow
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

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

## LLM configuration (same model as WebQA)

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

```text
appId: org.wikipedia
platform: android
task: Open Wikipedia, dismiss onboarding, confirm Search is visible
```

## Commands

| Command | Behavior |
|---------|----------|
| `mobiflow init` | Wizard / non-interactive scaffold (+ optional deps install) |
| `mobiflow setup` | Detect / auto-install missing Maestro, JDK, pip packages |
| `mobiflow run <case.txt>` | LLM → YAML → device (+ heal) |
| `mobiflow run <case.txt> --gen-only` | Author YAML only |
| `mobiflow gen "Open Settings…"` | One-shot NL → YAML |
| `mobiflow test-flow flows/foo.yaml` | Run existing YAML |
| `mobiflow status` / `devices` | Maestro + online / startable devices |
| `mobiflow devices --start` | Auto-start Android AVD (Win/Mac) or Xcode sim (Mac) |
| `mobiflow config show` / `llm list` | Inspect config / catalog |

## Languages

| `stack.language` | Behavior |
|------------------|----------|
| `yaml+js` (default) | Maestro YAML + optional JS (`evalScript` / `runScript` / `${…}`) |
| `yaml` | YAML commands only |

Companion scripts land under `flows/scripts/`.

## Pipeline

```
1. Load case + config (llm.json profiles)
2. Author Maestro YAML (+ JS when enabled)
3. maestro test --device <id>
4. On fail → repair with failure log (≤ run.heal) → re-run
5. Write flows/<case>.yaml (+ scripts) + .mobiflow/runs/
```

## Relation to test-agent-nexus Mobile Agent

This CLI extracts the same ideas as the Nexus **Mobile Agent**
(`maestro_runner_service` + Maestro CLI): NL→YAML, live device run, heal.
It is standalone — no FastAPI / Electron / Scrum Studio required.
