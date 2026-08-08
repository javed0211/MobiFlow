# mobiflow test cases

Put **one plain-text file per scenario** in this folder (`.txt`).

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
mobiflow devices
mobiflow status
```
