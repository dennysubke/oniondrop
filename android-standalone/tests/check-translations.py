#!/usr/bin/env python3
"""Reject missing translations, broken formatting tokens and obsolete release text."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1] / 'app/src/main/res'
def read(path):
    values = {}
    for node in ET.parse(path).getroot():
        name = node.attrib['name']
        assert name not in values, (path, 'duplicate resource', name)
        if node.tag == 'plurals':
            forms = {item.attrib['quantity']: item.text or '' for item in node}
            assert len(forms) == len(node), (path, name, 'duplicate quantity')
            assert 'other' in forms, (path, name, 'missing fallback')
            values[name] = forms
        else:
            values[name] = node.text or ''
    return values
base = read(root / 'values/strings.xml')
required_quantities = {
    'en': {'one', 'other'}, 'de': {'one', 'other'},
    'es': {'one', 'many', 'other'}, 'fr': {'one', 'many', 'other'},
    'it': {'one', 'many', 'other'}, 'ru': {'one', 'few', 'many', 'other'},
    'zh': {'other'}, 'ja': {'other'},
}
for locale, quantities in required_quantities.items():
    strings = read(root / ('values' if locale == 'en' else 'values-' + locale) / 'strings.xml')
    assert set(strings) == set(base), (locale, set(base) - set(strings))
    for key, text in strings.items():
        assert type(text) is type(base[key]), (locale, key, 'resource type mismatch')
        expected = base[key]['other'] if isinstance(text, dict) else base[key]
        forms = text.values() if isinstance(text, dict) else [text]
        if isinstance(text, dict):
            assert set(text) == quantities, (locale, key, 'incorrect quantity coverage')
        for form in forms:
            assert form.strip(), (locale, key, 'empty translation')
            assert sorted(re.findall(r'%\d+\$[ds]', form)) == sorted(re.findall(r'%\d+\$[ds]', expected)), (locale, key)
    assert not re.search(r'alpha|eigenständig|original.logo', strings['about_message'], re.I), locale
print('PASS: all 8 languages contain all %d resources, complete quantity forms and matching format arguments.' % len(base))
