# -*- coding: utf-8 -*-
"""Create manual AGFO .update.zip releases; never bundle passwords or installer hooks."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agfo_updater as u


def build_update(source: Path, output: Path, notes: str) -> dict:
    source = Path(source)
    output = Path(output)
    version = u.current_version(source)
    files = []
    for path in source.glob('*.py*'):
        if u.valid_name(path.name) and path.is_file():
            files.append(path.name)
    for path in (source / 'assets').glob('*'):
        rel = 'assets/' + path.name
        if u.valid_name(rel) and path.is_file():
            files.append(rel)
    files.sort()
    if not u.REQUIRED <= set(files):
        raise ValueError('Gerekli ana uygulama dosyalari eksik.')
    if len(files) > u.MAX_FILES or len(notes) > 2500:
        raise ValueError('Paket boyutu/icerigi siniri asildi.')
    entries = {}
    contents = {}
    for name in files:
        value = (source / name).read_bytes()
        if len(value) > u.MAX_PAYLOAD_BYTES:
            raise ValueError('Dosya cok buyuk.')
        contents[name] = value
        entries[name] = {'sha256':hashlib.sha256(value).hexdigest(), 'size':len(value)}
    manifest = {'format':u.FORMAT,'app_id':u.APP_ID,'version':version,
                'notes':notes,'files':entries}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        z.writestr('update-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        for name in files:
            z.writestr('payload/'+name,contents[name])
    u.inspect_package(output)
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--notes',default='AGFO Multi-Subnet Scanner guncellemesi.')
    opts=parser.parse_args()
    data=build_update(opts.source,opts.output,opts.notes)
    print('Hazir:',opts.output, 'Surum:',data['version'], 'Dosya:',len(data['files']))
