#!/usr/bin/env python3
"""Test release APK layouts, language selection, Tor publication and real upload."""
import hashlib
import pathlib
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

out = pathlib.Path('android-smoke')
out.mkdir(exist_ok=True)
package = 'de.dennysubke.oniondrop.standalone'
peer = None

def adb(*args):
    return subprocess.check_output(['adb', *args], timeout=45)

def ui():
    adb('shell', 'uiautomator', 'dump', '/sdcard/oniondrop-window.xml')
    return adb('shell', 'cat', '/sdcard/oniondrop-window.xml').decode()

def screenshot(name):
    (out / (name + '.png')).write_bytes(adb('exec-out', 'screencap', '-p'))

def tap(label):
    for node in ET.fromstring(ui()).iter('node'):
        if node.get('text', '').strip().casefold() == label.casefold() or node.get('content-desc', '').strip().casefold() == label.casefold():
            x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.attrib['bounds']))
            adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))
            time.sleep(1)
            return
    raise RuntimeError('Visible action missing: ' + label)

def locale(tag):
    adb('shell', 'cmd', 'locale', 'set-app-locales', package, '--user', '0', '--locales', tag)
    time.sleep(2)

def nav_check(tag):
    resource = pathlib.Path('android-standalone/app/src/main/res') / ('values' if tag=='en' else 'values-'+tag) / 'strings.xml'
    strings = {n.attrib['name']: n.text for n in ET.parse(resource).getroot()}
    xml = ET.fromstring(ui())
    bounds = []
    for key in ['nav_overview', 'nav_send', 'nav_receive']:
        nodes = [n for n in xml.iter('node') if n.get('clickable')=='true' and n.get('content-desc')==strings[key]]
        assert len(nodes)==1, (tag,key,'missing navigation action')
        box = tuple(map(int,re.findall(r'\d+',nodes[0].attrib['bounds'])))
        assert box[2]-box[0]>0 and box[3]-box[1]>0,box
        bounds.append(box)
    assert max(b[1] for b in bounds)-min(b[1] for b in bounds)<=1, bounds
    assert max(b[3] for b in bounds)-min(b[3] for b in bounds)<=1, bounds
    assert bounds[0][2]<=bounds[1][0] and bounds[1][2]<=bounds[2][0],bounds
    print('PASS: aligned, non-overlapping navigation: '+tag)

try:
    adb('install', '-r', 'apk/OnionDrop-smoke.apk')
    adb('shell', 'pm', 'grant', package, 'android.permission.POST_NOTIFICATIONS')
    adb('logcat', '-c')
    adb('shell', 'am', 'start', '-W', '-n', package + '/de.dennysubke.oniondrop.MainActivity')
    time.sleep(3)
    locale('en')
    tap('About OnionDrop')
    screenshot('about-en')
    tap('Language')
    screenshot('language-picker')
    tap('Deutsch')
    assert 'Übersicht' in ui(), 'In-app language selection failed'
    for tag in ['de','en','es','fr','it','ru','zh','ja']:
        locale(tag)
        nav_check(tag)
        screenshot('home-'+tag)
    locale('ru')
    adb('shell', 'wm', 'size', '720x1280')
    adb('shell', 'wm', 'density', '360')
    adb('shell', 'settings', 'put', 'system', 'font_scale', '1.3')
    time.sleep(3)
    nav_check('ru')
    screenshot('small-screen-large-text-ru')
    adb('shell', 'wm', 'size', 'reset')
    adb('shell', 'wm', 'density', 'reset')
    adb('shell', 'settings', 'put', 'system', 'font_scale', '1.0')
    locale('en')
    tap('Receive files')
    screenshot('receive-en')
    tap('Start receiving')
    deadline = time.monotonic() + 260
    receive_url = None
    while time.monotonic() < deadline:
        xml = ui()
        (out / 'last-window.xml').write_text(xml)
        match = re.search(r'http://[a-z2-7]{56}\.onion/r/[A-Za-z0-9_-]+/', xml)
        if match:
            receive_url = match.group()
            screenshot('onion-ready')
            print('PASS: release APK published a real onion receive link.')
            break
        time.sleep(5)
    assert receive_url, 'Tor did not publish within 260 seconds'
    # A separate Tor client sends bytes through the real onion network.
    peer_log = open(out/'peer-tor.txt','w')
    peer = subprocess.Popen(['tor','--SocksPort','19050','--DataDirectory',tempfile.mkdtemp(prefix='oniondrop-peer-'),'--Log','notice stdout'],stdout=peer_log,stderr=subprocess.STDOUT)
    content=b'OnionDrop release end-to-end transfer test\n'
    (out/'smoke.txt').write_bytes(content)
    uploaded=False
    for attempt in range(12):
        result=subprocess.run(['curl','--silent','--show-error','--fail','--max-time','30','--socks5-hostname','127.0.0.1:19050','-H','X-OnionDrop-Upload: 1','--data-binary','@'+str(out/'smoke.txt'),receive_url+'upload?name=smoke.txt'],capture_output=True)
        if result.returncode==0:
            uploaded=True
            break
        time.sleep(5)
    assert uploaded, 'Real onion upload failed: '+result.stderr.decode()
    time.sleep(3)
    tap('Actions for smoke.txt')
    tap('Show SHA-256')
    expected=hashlib.sha256(content).hexdigest()
    assert expected in ui(), 'Received file SHA-256 does not match'
    screenshot('transfer-sha256-verified')
    print('PASS: independent Tor client uploaded a file; APK SHA-256 matches the sent bytes.')
finally:
    if peer:
        peer.terminate()
    screenshot('last-screen')
    (out / 'logcat.txt').write_bytes(adb('logcat', '-d', '-t', '2000'))
    adb('shell', 'am', 'force-stop', package)
