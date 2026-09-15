# mobiflow test cases

Put **one plain-text file per scenario** in this folder (`.txt`).

## FOSS sample apps (Joplin / Bitwarden / WDIO)

Install the APK first — see [docs/SAMPLE_APPS.md](../docs/SAMPLE_APPS.md).

```bash
mobiflow run cases/android_joplin_smoke.txt
mobiflow run cases/android_bitwarden_smoke.txt
mobiflow run cases/android_e2e_api_hooks.txt
```

## Cloud labs (BrowserStack / TestMu)

Needs credentials in the environment. Cases set `provider:` + `appPath:` so they
do not depend on `mobiflow.config.yaml`.

```bash
export BROWSERSTACK_USERNAME=... BROWSERSTACK_ACCESS_KEY=...
mobiflow apps install browserstack --download-only
mobiflow run cases/android_browserstack_smoke.txt

export TESTMU_USERNAME=... TESTMU_ACCESS_KEY=...
mobiflow apps install testmu --download-only
mobiflow run cases/android_testmu_smoke.txt
```

## Featured: gesture + business-logic lab (not Wikipedia)

```bash
mobiflow run cases/ios_gesture_logic_lab.txt
# Apps: Settings + Maps · taps/swipes/drag/long-press/scroll · copyTextFrom + JS cart rules
```

## Intent style

```text
appId: org.wikipedia
platform: android
task: Open Wikipedia, dismiss onboarding, confirm Search is visible
```

## Guided steps

```text
@smoke
appId: com.android.settings
platform: android

1. Launch Settings
2. Confirm Wi-Fi or Network is visible
```

## Commands

```bash
mobiflow run cases/example.txt
mobiflow run cases/example.txt --gen-only
mobiflow run cases/android_joplin_smoke.txt
mobiflow run cases/android_bitwarden_smoke.txt
mobiflow run cases/ios_gesture_logic_lab.txt
mobiflow run cases/android_browserstack_smoke.txt
mobiflow run cases/android_testmu_smoke.txt
mobiflow devices
mobiflow status
```
