# JACC Android / APKPure Build

This repository now includes an Android WebView wrapper in `android-app/`.

## App identity

- App name: Japan Auction Car Checker
- Package: `com.kyawmintun.jacc`
- Version: `1.0.0` (`versionCode` 1)
- Website: `https://kyawmintun08.github.io/Japan-Auction-Car-Checker/`

## Features

- Loads the existing JACC website inside an Android app.
- Keeps cookies and DOM storage for member login sessions.
- Opens Telegram and other external links in their installed apps.
- Handles Android back navigation.
- Shows loading progress and an offline retry screen.
- Blocks cleartext HTTP traffic.

## Build locally

Install Android Studio, open the `android-app` folder, allow Gradle sync, then build an APK.

For a test APK:

```bash
gradle assembleDebug
```

For an APKPure release, use a permanent private signing key. Never commit the key or passwords.

Create `android-app/keystore.properties` locally:

```properties
storeFile=../jacc-release.jks
storePassword=YOUR_STORE_PASSWORD
keyAlias=YOUR_KEY_ALIAS
keyPassword=YOUR_KEY_PASSWORD
```

Then run:

```bash
gradle assembleRelease
```

The release file will be under:

`android-app/app/build/outputs/apk/release/`

## GitHub Actions signing secrets

The workflow `.github/workflows/build-android-apk.yml` supports these repository secrets:

- `JACC_KEYSTORE_BASE64`
- `JACC_STORE_PASSWORD`
- `JACC_KEY_ALIAS`
- `JACC_KEY_PASSWORD`

Encode the keystore before adding it as a secret:

```bash
base64 -w 0 jacc-release.jks
```

Keep the same keystore permanently. APKPure updates must be signed with the same key.

## Before APKPure submission

1. Build and install the signed release APK on a real Android phone.
2. Test member login, password copy, Telegram links, back navigation, and offline retry.
3. Prepare a 512x512 store icon, phone screenshots, privacy policy URL, description, and release notes.
4. Upload only the signed release APK.
