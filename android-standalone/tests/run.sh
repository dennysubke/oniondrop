#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
classes_dir="$(mktemp -d)"
trap 'rm -rf "$classes_dir"' EXIT
java com.sun.tools.javac.Main --release 17 -d "$classes_dir" "$root_dir"/app/src/main/java/de/dennysubke/oniondrop/core/*.java "$root_dir/tests/CoreTest.java"
java -cp "$classes_dir" CoreTest
