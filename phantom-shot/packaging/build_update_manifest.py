"""AGFO Phantom Shot - guncelleme paketi bildirimi (MANIFEST.json) uretici.

Kullanim:  python packaging/build_update_manifest.py <phantom-shot klasoru>
Paket kokune MANIFEST.json yazar (uygulama kimligi, surum, calisma dosyalarinin SHA-256 ozetleri).
Uygulamadaki "Guncelleme" penceresi paketi kurmadan once bu ozetleri dogrular.
Not: MANIFEST butunluk (bozulma/degisiklik) denetimidir; paketi kimin hazirladigini kanitlamaz.
Paketleri yalnizca guvendiginiz kaynaktan alin.
"""
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(root))
import phantom_core  # noqa: E402

man = phantom_core.build_manifest(root)
(root / 'MANIFEST.json').write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding='utf-8')
print('MANIFEST.json yazildi: surum %s, %d dosya' % (man['version'], len(man['files'])))
