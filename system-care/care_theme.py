"""AGFO System Care - renk temalari ve modern gorunum (ttkbootstrap) yukleyicisi.

Her tema 16 renkli bir paletle tanimlanir (ttkbootstrap'in tema bicimi). ttkbootstrap kuruluysa paletler ona
kaydedilir ve ttk bilesenleri onun cizimiyle gelir; kurulu degilse ayni paletler tkinter'in 'clam' temasiyla
kullanilir. Uygulamanin kendi tk bilesenleri (cerceve, etiket, gunluk) paletten turetilen "jetonlarla" boyanir.
Bu modul tkinter gerektirmez (testler Linux'ta tkinter'siz calisir).

Tokyo Gecesi, Nord, Dracula, Orman (Everforest), Gruvbox, One, Pastel (Catppuccin) ve Solarized paletleri
ttkbootstrap 2.2.7 katalogundan alinmistir (MIT). AGFO Gece / AGFO Acik / Yuksek karsitlik AGFO'nundur.
"""
import os
import pathlib
import sys

DEFAULT = 'agfo-gece'
TB_VERSION = '2.2.7'
TB_MIN_PYTHON = (3, 10)
COLOR_KEYS = ('primary', 'secondary', 'success', 'info', 'warning', 'danger', 'light', 'dark', 'bg', 'fg',
              'selectbg', 'selectfg', 'border', 'inputfg', 'inputbg', 'active')

THEMES = [{'key': 'agfo-gece',
  'label': 'AGFO Gece',
  'type': 'dark',
  'colors': {'primary': '#2f7fc1',
             'secondary': '#7d9bc1',
             'success': '#2e9d6a',
             'info': '#49b3ef',
             'warning': '#e2b356',
             'danger': '#d9534f',
             'light': '#ecf3ff',
             'dark': '#0a1425',
             'bg': '#12243b',
             'fg': '#ecf3ff',
             'selectbg': '#285475',
             'selectfg': '#ffffff',
             'border': '#2a4466',
             'inputfg': '#ecf3ff',
             'inputbg': '#0e1b2e',
             'active': '#192e48'}},
 {'key': 'agfo-acik',
  'label': 'AGFO Açık',
  'type': 'light',
  'colors': {'primary': '#1f5f99',
             'secondary': '#5b6b7f',
             'success': '#1f8a5b',
             'info': '#2b8fd6',
             'warning': '#b8730c',
             'danger': '#c43c3c',
             'light': '#f4f7fb',
             'dark': '#1d2b3a',
             'bg': '#ffffff',
             'fg': '#1d2b3a',
             'selectbg': '#cfe3f7',
             'selectfg': '#0b1f33',
             'border': '#cdd7e3',
             'inputfg': '#1d2b3a',
             'inputbg': '#ffffff',
             'active': '#e8eef6'}},
 {'key': 'tokyo-night-dark',
  'label': 'Tokyo Gecesi',
  'type': 'dark',
  'colors': {'primary': '#95b5f9',
             'secondary': '#c9aef9',
             'success': '#b1d888',
             'info': '#97d9ff',
             'warning': '#e6bf86',
             'danger': '#f991a5',
             'light': '#dddfe7',
             'dark': '#222637',
             'bg': '#1a1b26',
             'fg': '#c0caf5',
             'selectbg': '#787fa1',
             'selectfg': '#ffffff',
             'border': '#3f3f49',
             'inputfg': '#c0caf5',
             'inputbg': '#1f202d',
             'active': '#2a2b3d'}},
 {'key': 'nord-dark',
  'label': 'Nord Koyu',
  'type': 'dark',
  'colors': {'primary': '#7e9abd',
             'secondary': '#c3a5bd',
             'success': '#b5cba3',
             'info': '#a0cdd9',
             'warning': '#efd5a2',
             'danger': '#cc8188',
             'light': '#dbdde1',
             'dark': '#1e222a',
             'bg': '#2e3440',
             'fg': '#eceff4',
             'selectbg': '#707888',
             'selectfg': '#ffffff',
             'border': '#4f545f',
             'inputfg': '#eceff4',
             'inputbg': '#333946',
             'active': '#3d4554'}},
 {'key': 'dracula-dark',
  'label': 'Dracula',
  'type': 'dark',
  'colors': {'primary': '#caa9fa',
             'secondary': '#ff94d1',
             'success': '#73fb95',
             'info': '#a2edfd',
             'warning': '#ffc689',
             'danger': '#ff7777',
             'light': '#e0e3ed',
             'dark': '#272e42',
             'bg': '#282a36',
             'fg': '#f8f8f2',
             'selectbg': '#818eb6',
             'selectfg': '#ffffff',
             'border': '#4a4c56',
             'inputfg': '#f8f8f2',
             'inputbg': '#2d2f3d',
             'active': '#373a4b'}},
 {'key': 'everforest-dark',
  'label': 'Orman',
  'type': 'dark',
  'colors': {'primary': '#61a9d1',
             'secondary': '#e587c8',
             'success': '#a4b434',
             'info': '#5db996',
             'warning': '#e5b333',
             'danger': '#f97775',
             'light': '#e9ece9',
             'dark': '#3b403a',
             'bg': '#2d353b',
             'fg': '#d3c6aa',
             'selectbg': '#a9b2a7',
             'selectfg': '#000000',
             'border': '#4f555a',
             'inputfg': '#d3c6aa',
             'inputbg': '#323b41',
             'active': '#3c474f'}},
 {'key': 'gruvbox-dark',
  'label': 'Gruvbox',
  'type': 'dark',
  'colors': {'primary': '#6a9da0',
             'secondary': '#de7d3e',
             'success': '#adac48',
             'info': '#86b188',
             'warning': '#dfad4d',
             'danger': '#d6504a',
             'light': '#e9e6e3',
             'dark': '#3a342e',
             'bg': '#282828',
             'fg': '#ebdbb2',
             'selectbg': '#a89c90',
             'selectfg': '#000000',
             'border': '#4a4a4a',
             'inputfg': '#ebdbb2',
             'inputbg': '#2e2e2e',
             'active': '#3b3b3b'}},
 {'key': 'one-dark',
  'label': 'One Koyu',
  'type': 'dark',
  'colors': {'primary': '#6693f5',
             'secondary': '#b851b6',
             'success': '#73b472',
             'info': '#349dc9',
             'warning': '#cd9d34',
             'danger': '#e9786d',
             'light': '#ececed',
             'dark': '#404043',
             'bg': '#282c34',
             'fg': '#abb2bf',
             'selectbg': '#b3b4b9',
             'selectfg': '#000000',
             'border': '#4a4e54',
             'inputfg': '#abb2bf',
             'inputbg': '#2d313b',
             'active': '#383d49'}},
 {'key': 'catppuccin-light',
  'label': 'Pastel Açık',
  'type': 'light',
  'colors': {'primary': '#6d2ebf',
             'secondary': '#bb5ea2',
             'success': '#338022',
             'info': '#179299',
             'warning': '#df8e1d',
             'danger': '#a80c2e',
             'light': '#e8e9ec',
             'dark': '#383940',
             'bg': '#eff1f5',
             'fg': '#4c4f69',
             'selectbg': '#545661',
             'selectfg': '#ffffff',
             'border': '#c9cace',
             'inputfg': '#4c4f69',
             'inputbg': '#eff1f5',
             'active': '#dde1e9'}},
 {'key': 'nord-light',
  'label': 'Nord Açık',
  'type': 'light',
  'colors': {'primary': '#4b678a',
             'secondary': '#90728a',
             'success': '#829870',
             'info': '#88c0d0',
             'warning': '#ebcb8b',
             'danger': '#994e55',
             'light': '#dbdde1',
             'dark': '#1e222a',
             'bg': '#eceff4',
             'fg': '#2e3440',
             'selectbg': '#2e3440',
             'selectfg': '#ffffff',
             'border': '#c6c9cd',
             'inputfg': '#2e3440',
             'inputbg': '#eceff4',
             'active': '#d9dfe9'}},
 {'key': 'solarized-light',
  'label': 'Solarized Açık',
  'type': 'light',
  'colors': {'primary': '#1e6fa8',
             'secondary': '#565a9d',
             'success': '#6a7a00',
             'info': '#2aa198',
             'warning': '#b58900',
             'danger': '#b02826',
             'light': '#e6eaea',
             'dark': '#343b3c',
             'bg': '#f6f1e9',
             'fg': '#586e75',
             'selectbg': '#4f595a',
             'selectfg': '#ffffff',
             'border': '#cfcac4',
             'inputfg': '#586e75',
             'inputbg': '#f6f1e9',
             'active': '#ede4d4'}},
 {'key': 'yuksek-karsitlik',
  'label': 'Yüksek karşıtlık',
  'type': 'dark',
  'colors': {'primary': '#ffd400',
             'secondary': '#00e5ff',
             'success': '#3cff7a',
             'info': '#00e5ff',
             'warning': '#ffd400',
             'danger': '#ff5c5c',
             'light': '#ffffff',
             'dark': '#000000',
             'bg': '#000000',
             'fg': '#ffffff',
             'selectbg': '#ffd400',
             'selectfg': '#000000',
             'border': '#ffffff',
             'inputfg': '#ffffff',
             'inputbg': '#000000',
             'active': '#1f1f1f'}}]


def theme_keys():
    return [t['key'] for t in THEMES]


def theme_by_key(key):
    return next((t for t in THEMES if t['key'] == key), THEMES[0])


def label_to_key(label):
    return next((t['key'] for t in THEMES if t['label'] == label), DEFAULT)


# --------------------------------------------------------------------------- renk hesaplari
def _rgb(c):
    c = c.lstrip('#')
    if len(c) == 3:
        c = ''.join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return '#%02x%02x%02x' % tuple(max(0, min(255, round(v))) for v in rgb)


def mix(c1, c2, w):
    """w kadar c1, (1-w) kadar c2."""
    a, b = _rgb(c1), _rgb(c2)
    return _hex([a[i] * w + b[i] * (1 - w) for i in range(3)])


def luminance(c):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(c1, c2):
    l1, l2 = sorted((luminance(c1), luminance(c2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def ensure_contrast(color, bg, minimum):
    """Renk zemin uzerinde okunur olana kadar zemine gore koyulastirilir / acilir."""
    if contrast(color, bg) >= minimum:
        return color
    target = '#000000' if luminance(bg) > 0.4 else '#ffffff'
    for i in range(1, 21):
        c = mix(target, color, i / 20.0)
        if contrast(c, bg) >= minimum:
            return c
    return target


def text_on(bg):
    """Dugme yazisi: zemine en iyi karsitlik veren beyaz ya da koyu."""
    return '#ffffff' if contrast('#ffffff', bg) >= contrast('#111111', bg) else '#111111'


def tokens(key):
    """Uygulama jetonlari (care uygulamasinin tk bilesenlerinin kullandigi renkler)."""
    t = theme_by_key(key)
    c = t['colors']
    dark = t['type'] == 'dark'
    panel = c['bg']
    bg = mix('#000000', panel, 0.32) if dark else mix(c['fg'], panel, 0.06)
    if key == 'yuksek-karsitlik':
        bg = '#000000'
    panel2 = c['active'] if contrast(c['active'], panel) > 1.08 else mix(c['fg'], panel, 0.10)
    accent = ensure_contrast(c['info'] if dark else c['primary'], panel, 3.0)
    tok = {
        'THEME_KEY': key, 'DARK': dark,
        'BG': bg, 'PANEL': panel, 'PANEL2': panel2, 'FG': c['fg'],
        'MUTED': ensure_contrast(mix(c['fg'], panel, 0.66), panel, 4.5),
        'ACCENT': accent,
        'WARN': ensure_contrast(c['warning'], panel, 3.0), 'OK_C': ensure_contrast(c['success'], panel, 3.0),
        'BAD_C': ensure_contrast(c['danger'], panel, 3.0),
        'SEL': c['selectbg'], 'SEL_FG': c['selectfg'],
        'TREE_BG': c['inputbg'] if dark else '#ffffff' if luminance(panel) > 0.9 else c['inputbg'],
        'LOG_BG': mix('#000000', panel, 0.45) if dark else mix(c['fg'], panel, 0.03),
        'LOG_FG': c['fg'],
        'BTN': c['primary'], 'BTN_GO': c['success'], 'BTN_DANGER': c['danger'], 'BTN_GHOST': panel2,
        'DISABLED_FG': mix(c['fg'], panel, 0.45),
        'NAV_BG': mix('#000000', panel, 0.18) if dark else mix(c['fg'], panel, 0.035),
        'NAV_SEL': mix(c['primary'], panel, 0.28),
        'BANNER_BG': mix(c['success'], panel, 0.55 if dark else 0.85),
        'STOP_BG': mix(c['danger'], panel, 0.55),
        'BORDER': c['border'],
    }
    if key == 'yuksek-karsitlik':
        tok.update(NAV_BG='#000000', NAV_SEL='#333300', LOG_BG='#000000', TREE_BG='#000000')
    for k in ('BTN', 'BTN_GO', 'BTN_DANGER', 'BTN_GHOST', 'BANNER_BG', 'STOP_BG', 'NAV_SEL'):
        tok[k + '_FG'] = text_on(tok[k]) if k not in ('BTN_GHOST', 'NAV_SEL') else c['fg']
    tok['NAV_FG'] = ensure_contrast(c['fg'], tok['NAV_BG'], 4.5)
    tok['NAV_MUTED'] = ensure_contrast(mix(c['fg'], tok['NAV_BG'], 0.55), tok['NAV_BG'], 3.0)
    return _distinct(tok)


def _distinct(tok):
    """Her jeton farkli bir renk degeri tasir (gozle fark edilmeyecek 1-2 birimlik kaydirma). Tema degisirken
    bilesenin hangi jetonla boyandigi rengine bakilarak bulundugu icin iki jetonun ayni degeri paylasmamasi gerekir."""
    used = set()
    for k, v in tok.items():
        if not (isinstance(v, str) and v.startswith('#')):
            continue
        v = v.lower()
        r, g, b = _rgb(v)
        n = 0
        while v in used:                                       # 1, -1, 2, -2 ... birim (yon karsitligi bozmayacak kadar kucuk)
            n += 1
            d = (n + 1) // 2 * (1 if n % 2 else -1)
            v = _hex((r + d, g + d, b + d))
        used.add(v)
        tok[k] = v
    return tok


# --------------------------------------------------------------------------- ttkbootstrap
UI_LIB_DIRNAME = 'ui-lib'


def ui_lib_dir(app_data_dir):
    return pathlib.Path(app_data_dir) / UI_LIB_DIRNAME


def python_ok(version=None):
    return tuple((version or sys.version_info)[:2]) >= TB_MIN_PYTHON


def load_ttkbootstrap(lib_dir, enabled=True):
    """(modul | None, durum metni). Once AGFO ui-lib klasoru, sonra Python'un kendi paketleri denenir."""
    if not enabled:
        return None, 'kapalı (ayarlarda kapatıldı)'
    if not python_ok():
        return None, 'Python %d.%d+ gerekir (bu Python %d.%d)' % (TB_MIN_PYTHON + tuple(sys.version_info[:2]))
    lib = str(lib_dir)
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)
    try:
        import ttkbootstrap  # noqa: F401
        from ttkbootstrap.themes.legacy import theme_from_legacy_dict  # noqa: F401  (2.x API)
        return ttkbootstrap, 'etkin (ttkbootstrap %s)' % getattr(ttkbootstrap, '__version__', '?')
    except Exception as e:                                         # kurulu degil ya da uyumsuz surum
        return None, 'kurulu değil' if isinstance(e, ImportError) else 'yüklenemedi: %s' % e


def register_themes(style):
    """Tum paletleri ttkbootstrap'a kaydeder (bir kez)."""
    from ttkbootstrap.themes.legacy import theme_from_legacy_dict
    have = set(style.theme_names())
    for t in THEMES:
        name = 'agfo-' + t['key'] if not t['key'].startswith('agfo-') else t['key']
        if name not in have:
            style.register_theme(theme_from_legacy_dict(name, {'type': t['type'], 'colors': dict(t['colors'])}))


def tb_name(key):
    return key if key.startswith('agfo-') else 'agfo-' + key


def pip_install_cmd(python_exe, lib_dir):
    return [python_exe, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '--upgrade',
            '--target', str(lib_dir), 'ttkbootstrap==' + TB_VERSION]


def console_python(exe=None):
    """pythonw.exe ile calisiyorsak pip icin yanindaki python.exe."""
    exe = exe or sys.executable
    p = pathlib.Path(exe)
    if p.name.lower() == 'pythonw.exe':
        alt = p.with_name('python.exe')
        if alt.exists():
            return str(alt)
    return str(p)
