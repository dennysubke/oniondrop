#!/usr/bin/env python3
"""Reject missing translations, broken formatting tokens and obsolete release text."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1] / 'app/src/main/res'
def read(path):
    return {node.attrib['name']: node.text or '' for node in ET.parse(path).getroot()}
base = read(root / 'values/strings.xml')
for locale in ['de', 'es', 'fr', 'it', 'ru', 'zh', 'ja']:
    strings = read(root / ('values-' + locale) / 'strings.xml')
    assert set(strings) == set(base), (locale, set(base) - set(strings))
    for key, text in strings.items():
        assert sorted(re.findall(r'%\d+\$[ds]', text)) == sorted(re.findall(r'%\d+\$[ds]', base[key])), (locale, key)
    assert not re.search(r'alpha|eigenständig|original.logo', strings['about_message'], re.I), locale
print('PASS: all 8 languages contain all %d strings with matching format arguments.' % len(base))
