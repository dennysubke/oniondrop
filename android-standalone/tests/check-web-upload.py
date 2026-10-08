#!/usr/bin/env python3
"""Run the generated upload script with each shipped language and a fake network."""
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.data = {}
        self.script = ''
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id') == 'upload':
            for name, value in attrs.items():
                if name.startswith('data-'):
                    parts = name[5:].split('-')
                    self.data[parts[0] + ''.join(p.title() for p in parts[1:])] = value
        if tag == 'script':
            self.in_script = True

    def handle_data(self, data):
        if self.in_script:
            self.script += data

    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_script = False


pages = []
for path in sorted(Path(sys.argv[1]).glob('*-receive.html')):
    page = Page()
    page.feed(path.read_text())
    pages.append({'language': path.name.split('-')[0], 'script': page.script, 'data': page.data})
assert len(pages) == 8
program = r'''
const vm = require('node:vm');
const assert = require('node:assert/strict');
const pages = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
let checks = 0;
async function run(page, files, responses) {
  const elements = {
    files: {files, value: 'chosen', disabled: false},
    send: {disabled: false}, status: {textContent: ''}, upload: {dataset: page.data}
  };
  const calls = [];
  const context = vm.createContext({document: {getElementById: id => elements[id]}, fetch: async (url, options) => {
    calls.push({url, options});
    const response = responses.shift();
    if (response === 'network') throw new TypeError('browser-specific English error');
    return response;
  }});
  vm.runInContext(page.script, context, {timeout: 1000});
  await elements.send.onclick();
  assert.equal(elements.send.disabled, false);
  assert.equal(elements.files.disabled, false);
  checks += 2;
  return {elements, calls, status: elements.status.textContent};
}
(async () => {
  for (const page of pages) {
    const m = page.data;
    let result = await run(page, [], []);
    assert.equal(result.status, m.selectFiles);
    assert.equal(result.calls.length, 0);
    result = await run(page, [{name: 'huge.bin', size: 262144001}], []);
    assert.equal(result.status, m.sent + ' 0. ' + m.tooLarge + ' huge.bin');
    assert.equal(result.calls.length, 0);
    const files = [{name: "a <script> '& ü.txt", size: 12}, {name: 'two.txt', size: 1}];
    result = await run(page, files, [{ok: true}, {ok: true}]);
    assert.equal(result.status, m.sent + ' 2');
    assert.equal(result.elements.files.value, '');
    assert.equal(result.calls.length, 2);
    assert.equal(result.calls[0].url, 'upload?name=' + encodeURIComponent(files[0].name));
    assert.equal(result.calls[0].options.credentials, 'omit');
    assert.equal(result.calls[0].options.redirect, 'error');
    assert.equal(result.calls[0].options.headers['X-OnionDrop-Upload'], '1');
    result = await run(page, files, [{ok: true}, {ok: false, status: 507}]);
    assert.equal(result.status, m.sent + ' 1. ' + m.failed + ' two.txt (HTTP 507)');
    assert.equal(result.elements.files.value, 'chosen');
    result = await run(page, files, ['network']);
    assert.equal(result.status, m.sent + ' 0. ' + m.networkFailed);
    assert.equal(result.calls.length, 1);
    checks += 15;
  }
  console.log(checks + ' localized JavaScript upload checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
subprocess.run(['node', '-e', program], input=json.dumps(pages), text=True, check=True)
