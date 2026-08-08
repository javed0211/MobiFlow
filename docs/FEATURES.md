# MobiFlow features

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
  platform: android   # or ios
  auto_start: true
  boot_timeout_s: 120
  device_id: ""       # optional: AVD name, emulator-5554, or iOS UDID
```

```bash
mobiflow devices              # online only
mobiflow devices --all        # + startable AVDs / shutdown sims
mobiflow devices --start      # ensure one is running (auto-start if needed)
mobiflow run cases/example.txt   # uses auto_start from config
```

SDK paths checked: `ANDROID_HOME` / `ANDROID_SDK_ROOT`, macOS `~/Library/Android/sdk`, Windows `%LOCALAPPDATA%\Android\Sdk`.

## Dual LLM roles

| Role | Config key | Used for |
|------|------------|----------|
| Discovery | `llm.discovery` | Reserved for adaptive plan / hierarchy-aware explore |
| Codegen | `llm.codegen` | Maestro YAML authoring + heal repairs |

Both resolve from `llm.json`. They may be the same profile or different providers.

## Heal loop

`run.heal` (default `2`) = number of repair attempts after a failed `maestro test`.
Each repair sends previous YAML + failure log (+ optional hierarchy) to the codegen model.

## Gen-only

`mobiflow run cases/foo.txt --gen-only` or `mobiflow gen "…"` authors YAML without touching the device.

## Paste YAML

If the case `task:` (or `mobiflow gen` argument) already looks like Maestro YAML (`appId:` + `---` or command list), it is executed as-is — no LLM re-authoring.

## Artifacts

Under `.mobiflow/`:

- `flows/<case>.yaml` — last generated flow
- `runs/<case>-<timestamp>.json` + `<case>.latest.json` — run summary
