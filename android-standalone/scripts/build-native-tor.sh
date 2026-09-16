#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
upstream_commit=cb04167d313cc3b5e1c1246111591aa57c2147cb
ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-${ANDROID_NDK:-}}}"
: "${ANDROID_NDK_HOME:?Set ANDROID_NDK_HOME, ANDROID_NDK_ROOT or ANDROID_NDK to Android NDK 28.2.13676358}"
export ANDROID_NDK_HOME

submodule_dir="$project_dir/third_party/tor-android"
fallback_dir="${ONIONDROP_TOR_BUILD_DIR:-$project_dir/.native-tor}"

if [ -e "$submodule_dir/.git" ]; then
  build_dir="$submodule_dir"
else
  if [ "${ONIONDROP_OFFLINE:-0}" = 1 ]; then echo "Initialize the pinned Tor submodules before the offline build." >&2; exit 1; fi
  build_dir="$fallback_dir"
  if ! git -C "$build_dir" rev-parse --git-dir >/dev/null 2>&1; then
    git clone https://github.com/guardianproject/tor-android.git "$build_dir"
  fi
fi

if [ "$(git -C "$build_dir" rev-parse HEAD)" != "$upstream_commit" ]; then
  git -C "$build_dir" checkout --detach "$upstream_commit"
fi
# In F-Droid/GitHub CI these are already fetched by recursive submodule checkout.
# Locally this command initializes any missing nested source dependencies.
if [ "${ONIONDROP_OFFLINE:-0}" != 1 ]; then git -C "$build_dir" submodule update --init --recursive; fi

make -C "$build_dir/external" -f build-tools
for abi in "${@:-arm64-v8a}"; do
  case "$abi" in arm64-v8a|x86_64) ;; *) echo "Unsupported ABI: $abi" >&2; exit 1;; esac
  APP_ABI="$abi" make -C "$build_dir/external" clean
  APP_ABI="$abi" make -C "$build_dir/external"
  mkdir -p "$project_dir/app/src/main/jniLibs/$abi"
  cp "$build_dir/external/lib/$abi/libtor.so" "$project_dir/app/src/main/jniLibs/$abi/libtor.so"
done
printf '%s\n' "$upstream_commit" > "$project_dir/app/src/main/jniLibs/TOR_SOURCE_COMMIT"
