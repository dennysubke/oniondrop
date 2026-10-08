#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
classes_dir="$(mktemp -d)"
trap 'rm -rf "$classes_dir"' EXIT
java com.sun.tools.javac.Main --release 17 -d "$classes_dir" "$root_dir"/app/src/main/java/de/dennysubke/oniondrop/core/*.java "$root_dir"/tests/*.java
java -Doniondrop.res="$root_dir/app/src/main/res" -cp "$classes_dir" CoreTest
java -Doniondrop.res="$root_dir/app/src/main/res" -cp "$classes_dir" WebPageTest "$classes_dir/pages"
python3 "$root_dir/tests/check-web-upload.py" "$classes_dir/pages"
