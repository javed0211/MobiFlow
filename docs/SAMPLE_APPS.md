# Sample FOSS apps

MobiFlow does **not** ship APK/IPA binaries in git or the npm package (Wikipedia’s
stable APK alone is ~90 MB). Instead, download on demand into local `builds/`
(gitignored).

| App | Android `appId` | iOS `appId` | Good for |
|-----|-----------------|-------------|----------|
| Wikipedia | `org.wikipedia` | `org.wikimedia.wikipedia` | Search, lists, navigation |
| Joplin | `net.cozic.joplin` | `net.cozic.joplin` | Notes, folders, search, settings |
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

# Download only (no install)
mobiflow apps install wikipedia --download-only

# Pin a device / use a local APK
mobiflow apps install wikipedia --device emulator-5554
mobiflow apps install wikipedia --apk path/to/wikipedia.apk
```

APKs are cached as `builds/wikipedia.apk` / `builds/joplin.apk`.

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

### Bitwarden (Android)

Play Store / F-Droid, or release APKs from
[bitwarden/android](https://github.com/bitwarden/android/releases).

```bash
adb install -r path/to/bitwarden.apk
```

## Sample cases

```bash
mobiflow run cases/android_joplin_smoke.txt
mobiflow run cases/android_bitwarden_smoke.txt
mobiflow run cases/example.txt   # Wikipedia (after apps install wikipedia)
```

Smoke cases stay account-light (launch + onboarding + home/login chrome).
Add vault/note credentials via a local `data/*.json` or `.env` — never commit secrets.
