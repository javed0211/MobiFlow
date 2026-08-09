# Authoring MobiFlow cases

Cases are plain-text `.txt` files under `cases/`. One file = one scenario.
Copy `cases/example.txt` (also written by `mobiflow init`) and edit.

## Minimal case

```text
@smoke
appId: org.wikipedia
platform: android
task: Open Wikipedia and confirm Search is visible
```

## Full template

```text
@smoke @regression
appId: org.wikipedia
platform: android
# device: emulator-5554
# flow: flows/my-case.yaml
# clearState: false

# Run knobs (optional) — CLI > case > mobiflow.config.yaml
codegen: true
retries: 0
heal: 2
explore: true
# incremental: false
# extendExplore: false
# genOnly: false
# timeout: 180
# strict: false

data: data/example.json

# env:                 # overrides data file / config
#   SEARCH_QUERY = Marie Curie
expect:
  - Search

task: |
  Short intent, then numbered steps for incremental growth.

  1. Launch the app
  2. Dismiss onboarding if shown
  3. Tap Search and type ${SEARCH_QUERY}
  4. Confirm results for ${SEARCH_QUERY}
```

## Keys reference

### Identity

| Key | Required | Notes |
|-----|----------|--------|
| `appId` | recommended | Maestro package / bundle id |
| `platform` | recommended | `android` or `ios` |
| `device` | no | Device id / UDID / AVD name |
| `task` / `goal` | **yes*** | NL intent (`*` or numbered steps) |
| `flow` | no | Frozen YAML path (implies reuse when present) |
| `clearState` | no | Clear app before run |
| `@tag` | no | Suite filters (`mobiflow run cases/ --tag smoke`) |

### Run options (on the case)

| Key | Meaning |
|-----|---------|
| `codegen: false` | Reuse `flows/<case>.yaml` (no LLM) |
| `reuseFlow: true` | Same as `codegen: false` |
| `incremental: true` | Gap-explore only newly appended numbered steps |
| `extendExplore: true` | Full explore + extend codegen from prior YAML |
| `retries` | Re-run same YAML before heal |
| `heal` / `noHeal` | Repair attempts (`0` = off) |
| `explore` / `exploreSteps` | Discovery LLM before codegen |
| `genOnly` | Author YAML only |
| `adaptive` | Hierarchy-aware heal |
| `timeout` | Seconds for Maestro run |
| `strict: true` | Unknown keys are errors (default: warn) |

`reuseFlow`, `incremental`, and `extendExplore` are **mutually exclusive**
(with each other and the matching CLI flags).

**Precedence:** CLI flags → case file → `mobiflow.config.yaml`.

Inline comments on meta lines are allowed: `codegen: true  # freeze later`.

### Data & env

| Key | Meaning |
|-----|---------|
| `data:` | Path to `.json` / `.yaml` / `.yml` / `.env` |
| `env:` | Inline `KEY = value` (or `KEY = ENV_VAR_NAME`) |
| `expect:` | Force `assertVisible` texts into YAML |

**Path resolution** for `data:` (relative):

1. Directory of the case file  
2. Project repo root  
3. Current working directory  

Absolute paths work as-is.

**Merge order into Maestro `--env`:**  
`run.env` (config) < data file < case `env:`

Nested JSON/YAML flattens to env names:

```json
{ "search_query": "Albert Einstein", "user": { "name": "demo" } }
```

→ `SEARCH_QUERY`, `USER_NAME`, plus `DATA_PATH` (resolved absolute path).

Use in task / YAML as Maestro `${SEARCH_QUERY}`.

Sample files in this repo:

- `data/example.json` — used by `cases/example.txt`
- `data/wikipedia_complex_search.json` — used by `cases/wikipedia_complex_search.txt`

## Numbered steps & incremental growth

Numbered steps (`1. …`) enable guidance stamps under `.mobiflow/guidance/`
after a successful run.

```bash
# First green run (full explore + codegen)
mobiflow run cases/wikipedia_complex_search.txt

# Later: append step 11 to the case, then only explore the gap
mobiflow run cases/wikipedia_complex_search.txt --incremental
# or set incremental: true on the case
```

| Mode | Behavior |
|------|----------|
| unchanged | Reuse frozen YAML |
| append | Replay prior YAML (no `stopApp`) → explore gap → extend YAML |
| dirty | Full explore, codegen seeded from prior YAML |
| `--extend-explore` | Always full explore + extend codegen |

## Day-2 recipes

**Freeze a green flow (no LLM):**

```text
codegen: false
```

**Flaky device — retry before heal:**

```text
retries: 2
heal: 1
```

**External credentials (do not commit secrets):**

```text
data: data/login.env
```

```env
USERNAME=demo
PASSWORD=...
```

Or point `env:` values at process env names: `PASSWORD = MOBIFLOW_PASSWORD`.

## Related docs

- [FEATURES.md](FEATURES.md) — devices, cloud, suite, JS, reporting
- [README.md](../README.md) — install, quick start, commands
