# Sample FOSS apps

MobiFlow does not ship app binaries. These open-source apps are good local targets
once installed on an emulator/simulator or cloud device.

| App | Android `appId` | iOS `appId` | Good for |
|-----|-----------------|-------------|----------|
| Wikipedia | `org.wikipedia` | `org.wikimedia.wikipedia` | Search, lists, navigation |
| Joplin | `net.cozic.joplin` | `net.cozic.joplin` | Notes, folders, search, settings |
| Bitwarden | `com.x8bit.bitwarden` | `com.8bit.bitwarden` | Login, vault, search, settings |
| Settings | `com.android.settings` | `com.apple.Preferences` | System UI (preinstalled) |

Name aliases (`joplin`, `bitwarden`, `wikipedia`, …) resolve automatically when
`appId` is omitted and the task text mentions the app.

## Install

### Joplin (Android)

APKs: [github.com/laurent22/joplin-android](https://github.com/laurent22/joplin-android/tags)

```bash
# Prefer the universal joplin-vX.Y.Z.apk (or match ABI: arm64-v8a / x86_64)
adb install -r path/to/joplin-vX.Y.Z.apk
```

Or set in config and use preflight install:

```yaml
device:
  platform: android
  app_path: builds/joplin.apk
run:
  preflight: [install]
```

iOS: App Store build, or build from [laurent22/joplin](https://github.com/laurent22/joplin) (`packages/app-mobile`).

### Bitwarden (Android)

Play Store / F-Droid, or release APKs from
[bitwarden/android](https://github.com/bitwarden/android/releases).

```bash
adb install -r path/to/bitwarden.apk
```

iOS: App Store (`com.8bit.bitwarden`), or build from the Bitwarden mobile monorepo.

## Sample cases

```bash
mobiflow run cases/android_joplin_smoke.txt
mobiflow run cases/android_bitwarden_smoke.txt
```

Smoke cases stay account-light (launch + onboarding + home/login chrome).
Add vault/note credentials via a local `data/*.json` or `.env` — never commit secrets.
