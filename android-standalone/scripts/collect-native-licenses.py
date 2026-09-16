#!/usr/bin/env python3
"""Copy license notices from the exact native source checkout into the APK."""
from pathlib import Path
import shutil
import subprocess
import sys

source = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).resolve()
target.mkdir(parents=True, exist_ok=True)
for component in ['.', 'external/tor', 'external/openssl', 'external/libevent', 'external/zlib', 'external/zstd']:
    root = source / component
    paths = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).decode().split('\0')
    selected = [p for p in paths if p and any(term in Path(p).name.lower() for term in ['license', 'copying', 'copyright', 'notice']) and (root / p).is_file()]
    if component == 'external/zlib':
        selected.append('zlib.h')
    if not selected:
        raise SystemExit('No license notices found for ' + component)
    for rel in selected:
        dest = target / ('tor-android' if component == '.' else Path(component).name) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, dest)
    print(component + ': ' + str(len(selected)) + ' license notices included')
