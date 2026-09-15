# Sample apps

MobiFlow does **not** ship APK/IPA binaries in git or the npm package (Wikipedia’s
stable APK alone is ~90 MB). Instead, download on demand into local `builds/`
(gitignored).

| App | Android `appId` | iOS `appId` | Good for |
|-----|-----------------|-------------|----------|
| Wikipedia | `org.wikipedia` | `org.wikimedia.wikipedia` | Search, lists, navigation |
| Joplin | `net.cozic.joplin` | `net.cozic.joplin` | Notes, folders, search, settings |
| WDIO Native Demo | `com.wdiodemoapp` | `org.reactjs.native.example.wdiodemoapp` | Login, Forms, Swipe, Drag ([releases](https://github.com/webdriverio/native-demo-app/releases)) |
| BrowserStack Wikipedia sample | `org.wikipedia` | `org.wikimedia.wikipedia` | Cloud Maestro on App Automate (`mobiflow apps install browserstack`) |
| TestMu Proverbial | `com.lambdatest.proverbial` | `com.lambdatest.proverbial` | Cloud Maestro on HyperExecute (`mobiflow apps install testmu`) |
| Bitwarden | `com.x8bit.bitwarden` | `com.8bit.bitwarden` | Login, vault, search, settings |
| Settings | `com.android.settings` | `com.apple.Preferences` | System UI (preinstalled) |

## Install with MobiFlow (recommended)

```bash
# List supported sample apps
mobiflow apps list

# Download Wikipedia APK + adb install on the connected emulator/device
mobiflow apps install wikipedia

# Joplin
mobiflow apps install joplin

# WebdriverIO Native Demo (E2E sample)
mobiflow apps install wdio

# BrowserStack / TestMu cloud sample APKs (download-only, then upload on run)
mobiflow apps install browserstack --download-only
mobiflow apps install testmu --download-only

# Download only (no install)
mobiflow apps install wikipedia --download-only

# Pin a device / use a local APK (any app — Sauce Labs demo, etc.)
mobiflow apps install wikipedia --device emulator-5554
mobiflow apps install /path/to/MyDemoApp.apk
mobiflow apps install saucelabs /path/to/MyDemoApp.apk
mobiflow app install saucelabs /path/to/MyDemoApp.apk
```

APKs are cached as `builds/wikipedia.apk` / `builds/joplin.apk` / `builds/wdio.apk`
/ `builds/browserstack.apk` / `builds/testmu.apk`.

**iOS Simulator:** App Store IPAs cannot be sideloaded. Pass a locally built
`.app` with `--app path/to/Wikipedia.app` (uses `simctl install`).

## Manual install

### Joplin (Android)

APKs: [github.com/laurent22/joplin-android](https://github.com/laurent22/joplin-android/tags)

```bash
adb install -r path/to/joplin-vX.Y.Z.apk
```

### Wikipedia (Android)

Stable builds: [releases.wikimedia.org/mobile/android/wikipedia/stable](https://releases.wikimedia.org/mobile/android/wikipedia/stable/)

Or set in config and use preflight install:

```yaml
device:
  platform: android
  app_path: builds/wikipedia.apk
run:
  preflight: [install]
```

### WebdriverIO Native Demo (Android)

APKs: [github.com/webdriverio/native-demo-app/releases](https://github.com/webdriverio/native-demo-app/releases)
(`android.wdio.native.app.v*.apk`). Or:

```bash
mobiflow apps install wdio
```

Demo login used by the E2E sample: `bob@example.com` / `s3cret`.

### Bitwarden (Android)

Play Store / F-Droid, or release APKs from
[bitwarden/android](https://github.com/bitwarden/android/releases).

```bash
adb install -r path/to/bitwarden.apk
```

### BrowserStack Wikipedia sample (Android)

Public APK: [WikipediaSample.apk](https://www.browserstack.com/app-automate/sample-apps/android/WikipediaSample.apk)

```bash
mobiflow apps install browserstack --download-only
```

iOS sample IPA: [BStackSampleApp.ipa](https://www.browserstack.com/app-automate/sample-apps/ios/BStackSampleApp.ipa)
(set `device.app_path` / case `appPath` for cloud upload).

### TestMu Proverbial (Android)

Public APK: [proverbial_android.apk](https://prod-mobile-artefacts.lambdatest.com/assets/docs/proverbial_android.apk)

```bash
mobiflow apps install testmu --download-only
```

iOS sample IPA: [proverbial_ios.ipa](https://prod-mobile-artefacts.lambdatest.com/assets/docs/proverbial_ios.ipa).

## Sample cases

```bash
mobiflow run cases/android_joplin_smoke.txt
mobiflow run cases/android_bitwarden_smoke.txt
mobiflow run cases/android_e2e_api_hooks.txt   # WDIO demo + API hooks
mobiflow run cases/example.txt   # Wikipedia (after apps install wikipedia)
mobiflow run cases/android_browserstack_smoke.txt   # needs BROWSERSTACK_* env
mobiflow run cases/android_testmu_smoke.txt         # needs TESTMU_* or LT_* env
```

Smoke cases stay account-light (launch + onboarding + home/login chrome).
Add vault/note credentials via a local `data/*.json` or `.env` — never commit secrets.
