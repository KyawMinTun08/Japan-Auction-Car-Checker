# JACC Flutter Hybrid App

Android-first Flutter WebView application for Japan Auction Car Checker.

## Included improvements

- Native APK/AAB wrapper around the existing JACC website
- JACC-only in-app navigation
- External links open in the correct device app
- Android back-button handling
- Loading progress indicator
- Offline and retry screen
- Secure per-installation ID foundation for one-device security
- Automatic GitHub Actions APK and AAB builds

## Local setup

```bash
cd flutter_app
flutter create . --platforms=android --org=com.jacc.app
flutter pub get
flutter run
```

## Website URL

The app currently opens:

```text
https://kyawmintun08.github.io/Japan-Auction-Car-Checker/?jacc_app=1
```

## One-device security

The app creates a secure installation ID and makes it available to the website as:

```js
localStorage.getItem('jacc_installation_id')
```

The Google Apps Script backend still needs to receive this value during login, store it against the member record, and reject a different installation ID until an administrator resets the registered device.

## Security

Never place the Telegram bot token, Google credentials, signing passwords, or private API secrets in Flutter or website source files. Keep secrets in Railway, Apps Script properties, or GitHub Actions secrets.

## Android build

The workflow `.github/workflows/build-flutter-app.yml` creates:

- `app-release.apk`
- `app-release.aab`

Unsigned or development signing is suitable for testing. Play Store publishing requires a permanent release keystore configured through GitHub Actions secrets.
