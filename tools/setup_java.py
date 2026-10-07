"""Fetch the original Java dependencies from Maven Central, verify, then compile."""
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lib = ROOT / 'app/java/lib'
lib.mkdir(parents=True, exist_ok=True)
for item in json.loads((ROOT / 'demo/java-dependencies.json').read_text()):
    target = lib / item['name']
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == item['sha256']:
        continue
    raw = urllib.request.urlopen(item['url'], timeout=60).read()
    if hashlib.sha256(raw).hexdigest() != item['sha256']:
        raise RuntimeError('Dependency hash mismatch: ' + item['name'])
    target.write_bytes(raw)
classes = ROOT / 'app/java/classes'
classes.mkdir(exist_ok=True)
subprocess.run(['javac', '-encoding', 'UTF-8', '-cp', str(lib / '*'), '-d', str(classes),
                str(ROOT / 'app/java/LocalVbaReader.java')], check=True)
print('Java dependencies and compilation verified.')
