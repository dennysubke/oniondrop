# F-Droid submission

OnionDrop 1.0.0 (`10000`) uses application ID `de.dennysubke.oniondrop.standalone` and is licensed GPL-3.0-or-later.

## Source build

The Android project is in `android-standalone/`. Its only Java dependency is ZXing 3.5.3 (Apache-2.0). Tor 0.4.9.12 and its native dependencies are compiled from the recursive `tor-android` submodule pinned to `cb04167d313cc3b5e1c1246111591aa57c2147cb`. No prebuilt Tor binary, Google Play Services, proprietary SDK, advertising or analytics service is required.

Use JDK 17, Gradle 8.11.1, Android SDK / Build Tools 35 and NDK 28.2.13676358. See `android-standalone/README.md` for the build commands. Native compilation belongs in the F-Droid `build` phase, after the source scan. `ONIONDROP_OFFLINE=1` prevents the native build script from fetching additional source during compilation. Submodules must already be initialized by F-Droid. Native license notices are collected into the APK from those exact checkouts.

## Submission files

Copy `fdroid/de.dennysubke.oniondrop.standalone.yml` to the `metadata/` directory of a current fdroiddata checkout. It pins a complete public source commit, so no unpublished version tag is required. Automatic updates are deliberately disabled for the first submission; enable them after a maintained release-tag convention is established.

Store text and the original icon are in `fastlane/metadata/android/{de-DE,en-US}/`. The submission bundle also provides these files in fdroiddata's per-application metadata layout, with emulator screenshots and validation records.

Run `fdroid lint de.dennysubke.oniondrop.standalone` and `fdroid build --verbose de.dennysubke.oniondrop.standalone:10000` in the F-Droid build environment. Open a merge request against fdroiddata with the metadata and store assets. Respond to the maintainers' review and build results. The provided recipe has not been accepted or built by the official F-Droid infrastructure yet.

## Signing and installation

The downloadable developer APK is a non-debug release signed with a persistent developer key. The private key is not committed to this repository or uploaded to GitHub Actions. CI signs a separate emulator-only copy with a temporary test key.

F-Droid normally builds and signs its own APK. Its signature will differ from the developer APK; switching distributions can therefore require exporting private app files, uninstalling the old package and reinstalling. Do not uninstall before exporting files you want to keep. A previous debug-signed alpha also cannot be updated in place with the new release key.

Reproducible builds using the developer's signature have not been established. This package does not claim that the developer APK is an official F-Droid release.

## References

- [Submitting to F-Droid](https://f-droid.org/en/docs/Submitting_to_F-Droid_Quick_Start_Guide/)
- [Build metadata reference](https://f-droid.org/en/docs/Build_Metadata_Reference/)
- [Inclusion policy](https://f-droid.org/en/docs/Inclusion_Policy/)
- [Reproducible builds](https://f-droid.org/en/docs/Reproducible_Builds/)
