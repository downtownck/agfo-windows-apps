# -*- coding: utf-8 -*-
"""AGFO AI Editor - DOCX'i Word'de gorundugu gibi sayfalara cizer (DOCX -> PDF).

Sira: 1) bilgisayardaki Microsoft Word (gorunmez, arka planda acik tutulan tek bir Word; PowerShell COM koprusu)
      2) LibreOffice (soffice)
      3) hicbiri yoksa RenderUnavailable.
Sonuclar icerik ozetine gore onbellege alinir (ayni DOCX ikinci kez cizilmez).
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading

IS_WIN = sys.platform == 'win32'
CREATE_NO_WINDOW = 0x08000000

WORD_PS = r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
  $word = New-Object -ComObject Word.Application
  $word.Visible = $false
  $word.DisplayAlerts = 0
  try { $word.Options.SaveNormalPrompt = $false } catch {}
  try { $word.Options.UpdateLinksAtOpen = $false } catch {}
} catch {
  [Console]::Out.WriteLine('ERR ' + ($_.Exception.Message -replace "`r|`n", ' ')); [Console]::Out.Flush(); exit 2
}
[Console]::Out.WriteLine('READY'); [Console]::Out.Flush()
while ($true) {
  $line = [Console]::In.ReadLine()
  if ($line -eq $null -or $line -eq 'QUIT') { break }
  $parts = $line -split "`t"
  $doc = $null
  try {
    $doc = $word.Documents.Open($parts[0], $false, $true, $false)
    # 17 = PDF, 1 = wdExportCreateWordBookmarks
    $doc.ExportAsFixedFormat($parts[1], 17, $false, 0, 0, 1, 1, 0, $false, $true, 1, $true, $true, $false)
    $doc.Close(0)
    [Console]::Out.WriteLine('OK')
  } catch {
    if ($doc -ne $null) { try { $doc.Close(0) } catch {} }
    [Console]::Out.WriteLine('ERR ' + ($_.Exception.Message -replace "`r|`n", ' '))
  }
  [Console]::Out.Flush()
}
try { $word.Quit(0) } catch {}
'''


class RenderUnavailable(Exception):
    pass


class RenderError(Exception):
    pass


def _scrub_env():
    try:
        import agfo_editor_update as upd
        return upd.scrub_env()
    except Exception:  # pragma: no cover
        return dict(os.environ)


def word_installed() -> bool:
    if not IS_WIN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'Word.Application\CLSID'):
            return True
    except OSError:
        return False


def find_soffice():
    for name in ('soffice', 'libreoffice'):
        p = shutil.which(name)
        if p:
            return p
    if IS_WIN:
        for base in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)')):
            if base:
                p = pathlib.Path(base) / 'LibreOffice' / 'program' / 'soffice.exe'
                if p.is_file():
                    return str(p)
    return None


class _WordBridge:
    """Tek bir gorunmez Word; satir satir 'giris<TAB>cikis' komutu alir."""

    def __init__(self, work):
        self.work = work
        self.proc = None
        self.lock = threading.Lock()

    def _start(self):
        script = pathlib.Path(self.work) / 'agfo-word-render.ps1'
        script.write_text(WORD_PS, encoding='utf-8-sig')
        self.proc = subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=_scrub_env(),
            creationflags=CREATE_NO_WINDOW if IS_WIN else 0)
        line = self._readline(120)
        if line != 'READY':
            self.close()
            raise RenderUnavailable('Microsoft Word could not be started: %s' % (line or 'no answer'))

    def _readline(self, timeout):
        out = []

        def rd():
            out.append(self.proc.stdout.readline().decode('utf-8', 'replace').strip().lstrip('﻿'))
        th = threading.Thread(target=rd, daemon=True)
        th.start()
        th.join(timeout)
        if th.is_alive():
            return None
        return out[0] if out else ''

    def convert(self, src, dst, timeout=180):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            self.proc.stdin.write(('%s\t%s\n' % (src, dst)).encode('utf-8'))
            self.proc.stdin.flush()
            line = self._readline(timeout)
            if line is None:
                self.close(kill=True)
                raise RenderError('Word did not finish drawing the document in %d s.' % timeout)
            if line != 'OK':
                raise RenderError(line[4:] if line.startswith('ERR ') else line)

    def close(self, kill=False):
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            if kill:
                p.kill()
            else:
                p.stdin.write(b'QUIT\n')
                p.stdin.flush()
                p.wait(15)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


class Renderer:
    def __init__(self, cache_dir=None):
        base = pathlib.Path(cache_dir) if cache_dir else pathlib.Path(tempfile.gettempdir()) / 'agfo-render-cache'
        base.mkdir(parents=True, exist_ok=True)
        self.cache = base
        self.work = tempfile.mkdtemp(prefix='agfo-render-')
        self._word = _WordBridge(self.work) if word_installed() else None
        self._soffice = find_soffice()
        self.lock = threading.Lock()

    @property
    def engine(self):
        if self._word is not None:
            return 'Microsoft Word'
        if self._soffice:
            return 'LibreOffice'
        return None

    def to_pdf(self, docx) -> bytes:
        """docx: yol ya da bayt. PDF baytlarini dondurur."""
        data = docx if isinstance(docx, (bytes, bytearray)) else pathlib.Path(docx).read_bytes()
        key = hashlib.sha1(bytes(data)).hexdigest()
        hit = self.cache / (key + '.pdf')
        if hit.is_file() and hit.stat().st_size > 0:
            return hit.read_bytes()
        if self.engine is None:
            raise RenderUnavailable('Neither Microsoft Word nor LibreOffice was found on this computer.')
        with self.lock:
            src = pathlib.Path(self.work) / (key + '.docx')
            src.write_bytes(bytes(data))
            out = pathlib.Path(self.work) / (key + '.pdf')
            try:
                if self._word is not None:
                    try:
                        self._word.convert(str(src), str(out))
                    except (RenderError, RenderUnavailable, OSError):
                        if not self._soffice:
                            raise
                        self._soffice_convert(src)          # Word basaramazsa LibreOffice
                else:
                    self._soffice_convert(src)
                if not out.is_file():
                    raise RenderError('No PDF was produced.')
                pdf = out.read_bytes()
            finally:
                for f in (src, out):
                    try:
                        f.unlink()
                    except OSError:
                        pass
        tmp = hit.with_suffix('.tmp')
        tmp.write_bytes(pdf)
        os.replace(tmp, hit)
        self._trim_cache()
        return pdf

    def _soffice_convert(self, src):
        prof = pathlib.Path(self.work) / 'lo-profile'
        cmd = [self._soffice, '--headless', '--norestore', '--nologo', '-env:UserInstallation=' + prof.as_uri(),
               '--convert-to', 'pdf', '--outdir', str(src.parent), str(src)]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240, env=_scrub_env(),
                           creationflags=CREATE_NO_WINDOW if IS_WIN else 0)
        if r.returncode != 0:
            raise RenderError((r.stderr or r.stdout or b'').decode('utf-8', 'replace')[-400:] or 'LibreOffice failed')

    def _trim_cache(self, keep=40):
        files = sorted(self.cache.glob('*.pdf'), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[keep:]:
            try:
                f.unlink()
            except OSError:
                pass

    def close(self):
        if self._word is not None:
            self._word.close()
        shutil.rmtree(self.work, ignore_errors=True)


# ----------------------------------------------------------------------------- tiklama -> alan eslemesi
def _compact_map(text):
    """Harf/rakam disini atar; kompakt konum -> ozgun karakter konumu."""
    chars, idx = [], []
    for i, ch in enumerate(text):
        if ch.isalnum():
            chars.append(ch.lower())
            idx.append(i)
    return ''.join(chars), idx


def anchors(pdf_bytes, targets, snippet=28, with_rect=False):
    """targets: belge sirasinda [(hedef, gorunen_metin)]. Her hedefin metnini PDF metin akisinda SIRAYLA arar
    (ayni yer tutucu metni bircok kez gecse de sira dogru yeri verir). Donus: [(hedef, sayfa, x, y)] PDF noktasi,
    y yukaridan asagi. Bulunamayan hedef atlanir, imlec ilerlemez.
    with_rect=True: [(hedef, sayfa, x, y, (x0, y0, x1, y1), tamami_bu_sayfada)] - metnin bu sayfadaki kutusu."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_bytes)
    pages = []
    try:
        for pi in range(len(doc)):
            page = doc[pi]
            tp = page.get_textpage()
            n = tp.count_chars()
            text = tp.get_text_range(0, n) if n else ''
            comp, idx = _compact_map(text)
            boxes = {}
            h = page.get_height()
            pages.append((pi, tp, page, comp, idx, h, boxes))
        out = []
        cur_page, cur_pos = 0, 0
        keys = [_compact_map(str(sh or ''))[0][:snippet] for _t, sh in targets]
        for ti, (target, shown) in enumerate(targets):
            key = keys[ti]
            if len(key) < 3:
                continue
            # kisa/genel metinler ("Result", "Category") uzakta da gecer: arama penceresi metin uzunluguyla sinirlanir,
            # yoksa imlec ileri sicrar ve sonraki tum alanlar kaybolur
            window = 700 if len(key) < 8 else (5000 if len(key) < 16 else 40000)
            found, budget = None, window
            for pi in range(cur_page, len(pages)):
                comp = pages[pi][3]
                start = cur_pos if pi == cur_page else 0
                at = comp.find(key, start, start + budget + len(key))
                if at >= 0:
                    found = (pi, at)
                    break
                budget -= len(comp) - start
                if budget <= 0:
                    break
            if not found:
                continue
            pi, at = found
            # sicrama korumasi: kisa/genel bir metin ileride bulunduysa ve bir sonraki alanin metni imlec ile bu nokta
            # arasinda geciyorsa, bu eslesme yanlistir (or. bos hucrenin etiketi 'Country' sayfanin sonunda da var)
            if len(key) < 16 and (pi > cur_page or at - (cur_pos if pi == cur_page else 0) > 120):
                nk = next((k for k in keys[ti + 1:ti + 4] if len(k) >= 3), None)
                if nk:
                    lo = cur_pos if pi == cur_page else 0
                    if pages[pi][3].find(nk, lo, at) >= 0 or (pi > cur_page and pages[cur_page][3].find(nk, cur_pos) >= 0):
                        continue
            _p, tp, _page, comp, idx, h, _b = pages[pi]
            try:
                left, bottom, _right, top = tp.get_charbox(idx[at])
            except Exception:
                continue
            # metnin bu sayfadaki kismi: tum degerin ne kadari burada ardisik eslesiyor -> kutu (duzenleyici yeri)
            full, _ = _compact_map(str(shown or ''))
            n = len(key)
            while n < len(full) and at + n < len(comp) and comp[at + n] == full[n]:
                n += 1
            x0, y0, x1, y1 = float(left), float(h - top), float(_right), float(h - bottom)
            step = max(1, n // 400)                         # uzun kutularda her karakter yerine ornekleme
            for k in list(range(at, at + n, step)) + [at + n - 1]:
                try:
                    l2, b2, r2, t2 = tp.get_charbox(idx[k])
                except Exception:
                    continue
                x0, x1 = min(x0, l2), max(x1, r2)
                y0, y1 = min(y0, h - t2), max(y1, h - b2)
            out.append((target, pi, float(left), float(h - top), (x0, y0, x1, y1), n >= len(full)))
            cur_page, cur_pos = pi, at + n
        if not with_rect:
            return [a[:4] for a in out]
        return out
    finally:
        for _pi, tp, page, *_r in pages:
            try:
                tp.close()
                page.close()
            except Exception:
                pass
        doc.close()


def hit(found, page, x, y, pad=3):
    """Tiklanan nokta bir alanin kutusunun icindeyse o alan (en kucuk kutu); yoksa None."""
    best, area = None, None
    for a in found:
        if len(a) < 5 or a[1] != page:
            continue
        x0, y0, x1, y1 = a[4]
        if x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad:
            ar = (x1 - x0) * (y1 - y0)
            if area is None or ar < area:
                best, area = a, ar
    return best


def nearest_anchor(found, page, x, y):
    """Tiklanan noktaya (PDF noktasi) gore en uygun hedef: once kutusu noktayi iceren alan; yoksa ayni sayfada noktanin
    ustunde/hizasinda kalan en yakin baslangic."""
    h = hit(found, page, x, y)
    if h is not None:
        return h[0]
    best, score = None, None
    for a in found:
        target, pi, ax, ay = a[:4]
        if pi != page or ay > y + 6:
            continue
        s = (y - ay) + 0.35 * abs(x - ax)
        if score is None or s < score:
            best, score = target, s
    if best is None:
        prev = [a for a in found if a[1] < page]
        if prev:
            best = prev[-1][0]
    return best
