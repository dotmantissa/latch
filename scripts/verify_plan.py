#!/usr/bin/env python3
"""Verify local planning and brand artifacts without creating a repository or running app mocks."""
from pathlib import Path
import hashlib
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
assert '/TASKS.md' in (ROOT / '.gitignore').read_text().splitlines()
assert (ROOT / 'TASKS.md').is_file()
for name in ['ARCHITECTURE.md', 'README.md', 'COPY.json', 'DESIGN_TOKENS.json', 'DESIGN_ROLLS.json']:
    assert (ROOT / name).is_file(), name

# Limit this check to planning assets; never traverse runtime or Git directories.
files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in {'.md', '.json'}]
for directory in ['assets', 'docs', 'research']:
    files.extend(p for p in (ROOT / directory).rglob('*') if p.is_file())
files.append(Path(__file__).resolve())
for p in files:
    assert not p.is_symlink(), f'Unexpected symlink: {p}'
    assert p.suffix.lower() not in {'.pem', '.key'}, f'Unexpected secret file: {p}'
    assert not p.name.startswith('.env'), f'Unexpected environment file: {p}'
    if p.suffix == '.json':
        json.loads(p.read_text())
    if p.suffix == '.md':
        body = p.read_text()
        assert body.count('```') % 2 == 0, f'Unclosed fence: {p}'
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', body):
            if target.startswith(('https://', 'http://', '#', 'mailto:')):
                continue
            assert (p.parent / target.split('#')[0]).is_file(), f'Broken link: {p}: {target}'
    if p.suffix in {'.md', '.json', '.svg', '.py'} and p.name != 'TASKS.md':
        assert all(line.rstrip() == line for line in p.read_text().splitlines()), f'Trailing whitespace: {p}'
    if p.suffix == '.svg':
        tree = ET.fromstring(p.read_text())
        assert tree.tag.endswith('svg')
        assert 'viewBox' in tree.attrib
        text = p.read_text().lower()
        assert '<script' not in text and 'javascript:' not in text and 'http://' not in text.replace('http://www.w3.org/2000/svg', '')

copy = json.loads((ROOT / 'COPY.json').read_text())
for key, value in copy.items():
    assert isinstance(value, str)
    assert not any(char in value for char in ['\u2014', '\u2013', '-']), f'Forbidden punctuation in owned copy: {key}'
    assert not any(0x1F000 <= ord(c) <= 0x1FAFF or 0x2600 <= ord(c) <= 0x27BF for c in value), f'Emoji/symbol copy: {key}'
    assert not re.search(r'(?<!\w)(AI.powered|revolutionary|seamless|magic)(?!\w)', value, re.I), key
readme = (ROOT / 'README.md').read_text()
visible_readme = re.sub(r'\]\([^)]*\)', ']', readme)
visible_readme = re.sub(r'^\|[\s:|\-]+\|$', '', visible_readme, flags=re.M)
assert not any(c in visible_readme for c in ['\u2014', '\u2013', '-']), 'README owned prose contains banned punctuation'
assert not any(0x1F000 <= ord(c) <= 0x1FAFF or 0x2600 <= ord(c) <= 0x27BF for c in visible_readme)

rolls = json.loads((ROOT / 'DESIGN_ROLLS.json').read_text())
tokens = json.loads((ROOT / 'DESIGN_TOKENS.json').read_text())
assert rolls['seed'] == tokens['seed'] == 1793714516810191212
assert set(rolls['axes']) == {'palette', 'layout', 'type', 'motion', 'device'}
assert [rolls['axes'][k]['roll'] for k in ['palette','layout','type','motion','device']] == [3,5,2,1,1]

def luminance(hex_color):
    channels = [int(hex_color[i:i+2], 16) / 255 for i in [1, 3, 5]]
    channels = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in channels]
    return sum(x * w for x, w in zip(channels, [.2126, .7152, .0722]))

def contrast(a,b):
    l1,l2 = sorted([luminance(a),luminance(b)],reverse=True)
    return (l1+.05)/(l2+.05)

contrast_results = {}
for name, theme in tokens['themes'].items():
    pairs = []
    for fg in ['text','muted','accent','success','warning','danger','info']:
        for bg in ['canvas','surface','subtle']:
            pairs.append((fg,bg,4.5))
    pairs += [('accentText','accent',4.5),('accentText','accentHover',4.5)]
    pairs += [('controlBorder',bg,3) for bg in ['canvas','surface','subtle']]
    result = {}
    for fg,bg,minimum in pairs:
        ratio = contrast(theme[fg],theme[bg]);result[f'{fg}/{bg}'] = round(ratio,2)
        assert ratio >= minimum, f'{name} {fg}/{bg}: {ratio:.2f} < {minimum}'
    contrast_results[name] = result

source_manifest = json.loads((ROOT / 'assets/ASSET_SOURCES.json').read_text())
for font in source_manifest['fonts']:
    data = (ROOT / font['file']).read_bytes()
    assert len(data) == font['bytes'] and hashlib.sha256(data).hexdigest() == font['sha256']
for size in [16,32,48,180,192,512]:
    data = (ROOT / f'assets/icons/icon-{size}.png').read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    assert int.from_bytes(data[16:20],'big') == size and int.from_bytes(data[20:24],'big') == size
ico = (ROOT / 'assets/icons/favicon.ico').read_bytes()
assert ico[:4] == b'\x00\x00\x01\x00' and int.from_bytes(ico[4:6],'little') == 3
report = {'status':'passed','scope':'Planning, copy, links, tokens and brand files only. No application or live-service acceptance performed.','files_checked':len(files),'owned_copy_strings':len(copy),'contrast':contrast_results}
(ROOT / 'PLAN_VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='contrast'},indent=2))
print('Functional token contrast checked for both themes; SVG/PNG/ICO and font hashes verified.')
