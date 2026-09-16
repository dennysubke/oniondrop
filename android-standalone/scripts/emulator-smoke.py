#!/usr/bin/env python3
"""Exercise the installable APK and its real bundled Tor on a disposable emulator."""
import pathlib
import re
import subprocess
import time
import xml.etree.ElementTree as ET

out = pathlib.Path('android-smoke')
out.mkdir(exist_ok=True)
package = 'de.dennysubke.oniondrop.standalone'

def adb(*args):
    return subprocess.check_output(['adb', *args], timeout=40)

def ui():
    adb('shell', 'uiautomator', 'dump', '/sdcard/oniondrop-window.xml')
    return adb('shell', 'cat', '/sdcard/oniondrop-window.xml').decode()

def screenshot(name):
    (out / (name + '.png')).write_bytes(adb('exec-out', 'screencap', '-p'))

def tap(label):
    for node in ET.fromstring(ui()).iter('node'):
        if node.get('text', '').strip() == label:
            x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.attrib['bounds']))
            adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))
            time.sleep(2)
            return
    raise RuntimeError('Visible action missing: ' + label)

try:
    adb('install', '-r', 'apk/OnionDrop-1.0.0.apk')
    adb('shell', 'pm', 'grant', package, 'android.permission.POST_NOTIFICATIONS')
    adb('logcat', '-c')
    adb('shell', 'am', 'start', '-W', '-n', package + '/de.dennysubke.oniondrop.MainActivity')
    time.sleep(3)
    screenshot('01-home')
    tap('Receive files')
    screenshot('02-receive')
    tap('Start receiving')
    deadline = time.monotonic() + 260
    while time.monotonic() < deadline:
        xml = ui()
        (out / 'last-window.xml').write_text(xml)
        if re.search(r'http://[a-z2-7]{56}\.onion/r/', xml):
            screenshot('03-onion-ready')
            print('PASS: APK launched and bundled Tor published a real onion receive link.')
            break
        time.sleep(5)
    else:
        raise RuntimeError('No published onion receive link within 260 seconds; inspect emulator diagnostics.')
finally:
    screenshot('last-screen')
    (out / 'logcat.txt').write_bytes(adb('logcat', '-d', '-t', '2000'))
    adb('shell', 'am', 'force-stop', package)
