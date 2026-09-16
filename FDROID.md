# F-Droid submission notes

OnionDrop 1.0.0 is prepared so F-Droid can build the Android application from source.

- Application ID: `de.dennysubke.oniondrop.standalone`
- License: GPL-3.0-or-later
- Android project: `android-standalone/`
- NDK: `28.2.13676358`
- Native Tor source: Guardian Project `tor-android` pinned as a recursive Git submodule at commit `cb04167d313cc3b5e1c1246111591aa57c2147cb`
- Upstream store text: `fastlane/metadata/android/`
- Proposed fdroiddata build recipe: `fdroid/de.dennysubke.oniondrop.standalone.yml`

The main F-Droid repository does not accept a prebuilt developer APK as the canonical package. F-Droid checks out the tagged source, builds the app and signs the resulting APK itself. The APK produced by this repository's GitHub Actions workflow is intended for direct testing of the same source.

Before submitting the fdroiddata merge request, create/push the `v1.0.0` tag and verify the GitHub CI build and emulator smoke test are green. The metadata template can then be copied to fdroiddata's `metadata/` directory and adjusted if F-Droid CI requests environment-specific changes.
