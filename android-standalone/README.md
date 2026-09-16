# OnionDrop for Android · 1.0.0

OnionDrop is a local-first Android app for sending and receiving files through a temporary Tor v3 onion service. Tor and the transfer server run directly on the phone; no Umbrel server, Orbot account, cloud account, analytics service or advertising SDK is required.

## Features

- Native Android interface with the original OnionDrop logo.
- Send selected files through a private onion link.
- Receive files through a separate private onion link without exposing an inbox listing.
- Copy, share and display links as QR codes.
- Export received files through Android's document picker.
- SHA-256 checksums and local file management.
- Foreground-service session with a 30-minute maximum lifetime and explicit stop controls.
- Tor 0.4.9.12 built from pinned Guardian Project source.
- Languages: German, English, Spanish, Italian, French, Chinese, Japanese and Russian. Choose a language from About → Language, or follow the system language. Android 13+ also exposes the same setting in system app settings.

## Storage and limits

Files are kept in OnionDrop's private app storage. The current limits are 250 MiB per file and 1 GiB / 100 files per send or receive area. App-private files are removed when OnionDrop is uninstalled, so received files that should be kept permanently must be exported first.

A sharing session lasts at most 30 minutes. Android background restrictions, power saving or network interruptions may end it sooner. Anyone who knows a complete send or receive link has the corresponding capability for the lifetime of that session; treat links as secrets.

## Build from source

Requirements:

- JDK 17
- Gradle 8.11.1 or a compatible Gradle version for Android Gradle Plugin 8.9.1
- Android SDK 35, Build Tools 35.0.0
- Android NDK 28.2.13676358
- `autoconf automake libtool autopoint gettext pkg-config build-essential po4a libzstd-dev`
- Git submodules initialized recursively

```bash
git clone --branch codex/android-release-review --recurse-submodules https://github.com/dennysubke/oniondrop.git
cd oniondrop/android-standalone
export ANDROID_NDK_HOME="$ANDROID_HOME/ndk/28.2.13676358"
bash scripts/build-native-tor.sh arm64-v8a x86_64
python3 scripts/collect-native-licenses.py third_party/tor-android app/src/main/assets/licenses/native
bash tests/run.sh
python3 tests/check-translations.py
gradle --no-daemon :app:assembleRelease :app:lintRelease
```

The source build refuses to create an app without the native Tor engine.

## F-Droid

The repository contains upstream Fastlane metadata and an F-Droid build-metadata template. F-Droid builds and signs its own APK from source; a developer/test APK is not the package submitted to the main F-Droid repository. See `FDROID.md` in the repository root.

## Tor source

Pinned Guardian Project tor-android commit:

`cb04167d313cc3b5e1c1246111591aa57c2147cb`

The native `libtor.so` is built from that source and its pinned submodules for `arm64-v8a` and `x86_64`.

## License

OnionDrop is GPL-3.0-or-later. Third-party notices are in `THIRD-PARTY-NOTICES.md`.
